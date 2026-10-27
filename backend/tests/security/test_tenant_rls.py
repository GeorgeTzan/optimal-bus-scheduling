import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL, User, Schedule, Trip, Driver
from app.domain.identity.tenant_session import (
    tenant_transaction,
    system_worker_transaction,
    audit_tenant_schema,
    CrossTenantAccessError,
)


@pytest.fixture
def db_session():
    # Use SQLite for fast in-memory unit tests; dialect-aware session manager
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed two tenants
    ktel_a = KTEL(name="KTEL Korinthias", region="Peloponnese")
    ktel_b = KTEL(name="KTEL Patras", region="Achaea")
    session.add_all([ktel_a, ktel_b])
    session.commit()

    yield session
    session.close()


def test_schema_has_tenant_id_for_each_tenant_table():
    # Schema audit must verify that tenant-scoped tables have tenant_id column
    missing = audit_tenant_schema(Base.metadata)
    assert len(missing) == 0, f"Tables missing tenant_id column: {missing}"


def test_cross_tenant_query_empty(db_session):
    # Tenant A creates a schedule
    with tenant_transaction(db_session, tenant_id=1):
        s_a = Schedule(name="Corinth Morning Rush", ktel_id=1)
        db_session.add(s_a)
        db_session.commit()

    # Tenant B queries schedules - must be empty!
    with tenant_transaction(db_session, tenant_id=2):
        schedules_b = db_session.query(Schedule).filter(Schedule.ktel_id == 2).all()
        assert len(schedules_b) == 0


def test_cross_tenant_update_denied(db_session):
    # Tenant A creates a schedule
    with tenant_transaction(db_session, tenant_id=1):
        s_a = Schedule(name="Corinth Morning", ktel_id=1)
        db_session.add(s_a)
        db_session.commit()
        schedule_id = s_a.id

    # Tenant B attempts to update Tenant A's schedule
    with tenant_transaction(db_session, tenant_id=2):
        # The row is completely filtered out; update touches 0 rows
        affected = db_session.query(Schedule).filter(Schedule.id == schedule_id).update({"name": "Hacked Name"})
        db_session.commit()
        assert affected == 0

    # Verify Tenant A's schedule was NOT modified
    with tenant_transaction(db_session, tenant_id=1):
        s_check = db_session.query(Schedule).filter(Schedule.id == schedule_id).first()
        assert s_check is not None
        assert s_check.name == "Corinth Morning"


def test_worker_cannot_escape_tenant(db_session):
    # Seed schedules for both tenants
    s1 = Schedule(name="Corinth Line 1", ktel_id=1)
    s2 = Schedule(name="Patras Line 1", ktel_id=2)
    db_session.add_all([s1, s2])
    db_session.commit()

    # Worker executes in Tenant 1 context
    with tenant_transaction(db_session, tenant_id=1):
        # Querying all schedules automatically filters to Tenant 1 only
        visible_schedules = db_session.query(Schedule).all()
        assert len(visible_schedules) == 1
        assert visible_schedules[0].ktel_id == 1
        assert visible_schedules[0].name == "Corinth Line 1"
