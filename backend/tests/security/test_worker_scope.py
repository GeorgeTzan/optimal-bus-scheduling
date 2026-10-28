import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL, Schedule
from app.domain.identity.tenant_session import (
    tenant_transaction,
    system_worker_transaction,
    CrossTenantAccessError,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    sess = Session()

    k1 = KTEL(name="KTEL Korinthias", region="Peloponnese")
    k2 = KTEL(name="KTEL Thessalonikis", region="Macedonia")
    sess.add_all([k1, k2])
    sess.commit()

    s1 = Schedule(name="Corinth Line 1", ktel_id=1)
    s2 = Schedule(name="Thessaloniki Line 1", ktel_id=2)
    sess.add_all([s1, s2])
    sess.commit()

    yield sess
    sess.close()


def test_system_worker_requires_explicit_tenant_scope(session):
    # A worker marker must never grant cross-tenant data access.
    with pytest.raises(CrossTenantAccessError):
        with system_worker_transaction(session):
            session.query(Schedule).all()


def test_worker_switches_to_tenant_scope_cleanly(session):
    # Supervisor claims job for Tenant 1, then immediately drops privileges into Tenant 1 context
    with tenant_transaction(session, tenant_id=1):
        visible = session.query(Schedule).all()
        assert len(visible) == 1
        assert visible[0].ktel_id == 1

    # Supervisor claims job for Tenant 2, then drops privileges into Tenant 2 context
    with tenant_transaction(session, tenant_id=2):
        visible = session.query(Schedule).all()
        assert len(visible) == 1
        assert visible[0].ktel_id == 2
