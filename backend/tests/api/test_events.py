import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from db.models import KTEL, User
from main import app
from tests.support import create_test_access_token
from app.domain.events.outbox import OutboxService, OutboxEvent


@pytest.fixture
def test_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    ktel1 = KTEL(id=1, name="KTEL Achaias", region="Patras")
    ktel2 = KTEL(id=2, name="KTEL Korinthias", region="Korinthos")
    user1 = User(id=1, email="dispatcher@ktel-achaias.gr", hashed_password="pw", full_name="Dispatcher 1", is_active=True, ktel_id=1)
    user2 = User(id=2, email="dispatcher@ktel-korinthias.gr", hashed_password="pw", full_name="Dispatcher 2", is_active=True, ktel_id=2)
    session.add_all([ktel1, ktel2, user1, user2])
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    token_user1 = create_test_access_token(session,user1.id)
    token_user2 = create_test_access_token(session,user2.id)

    client = TestClient(app)

    yield {
        "client": client,
        "token1": token_user1,
        "token2": token_user2,
        "session": session,
    }

    app.dependency_overrides.clear()
    session.close()


def test_event_no_tenant_leak(test_setup):
    """
    Events emitted for tenant 1 are never received by tenant 2.
    """
    session = test_setup["session"]
    token2 = test_setup["token2"]
    client = test_setup["client"]

    outbox = OutboxService(session)
    outbox.emit(tenant_id=1, event_type="job.progress", job_id="JOB-1", payload={"progress_pct": 50})

    resp = client.get(
        "/events?cursor=0&once=true",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    content = resp.text
    assert "JOB-1" not in content


def test_replay_after_disconnect(test_setup):
    """
    When client reconnects with a cursor, only events after that cursor are replayed.
    """
    session = test_setup["session"]
    token1 = test_setup["token1"]
    client = test_setup["client"]

    outbox = OutboxService(session)
    e1 = outbox.emit(tenant_id=1, event_type="job.queued", job_id="JOB-10", payload={"status": "queued"})
    e2 = outbox.emit(tenant_id=1, event_type="job.progress", job_id="JOB-10", payload={"progress_pct": 25})
    e3 = outbox.emit(tenant_id=1, event_type="job.progress", job_id="JOB-10", payload={"progress_pct": 75})

    # Client already received up to e1.id, asks for events with cursor=e1.id
    resp = client.get(
        f"/events?cursor={e1.id}&once=true",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    content = resp.text
    # Should contain e2 and e3, but not e1
    assert f"id: {e1.id}" not in content
    assert f"id: {e2.id}" in content
    assert f"id: {e3.id}" in content


def test_event_payload_no_sensitive_internal_log(test_setup):
    """
    Event payloads are sanitized: sensitive internal keys or tracebacks are stripped.
    """
    session = test_setup["session"]
    token1 = test_setup["token1"]
    client = test_setup["client"]

    outbox = OutboxService(session)
    outbox.emit(
        tenant_id=1,
        event_type="job.failed",
        job_id="JOB-ERR",
        payload={
            "error": "Optimization timeout",
            "password": "secret_password",
            "traceback": "Traceback (most recent call last)... File /internal/path.py",
        },
    )

    resp = client.get(
        "/events?cursor=0&once=true",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    content = resp.text
    assert "secret_password" not in content
    assert "/internal/path.py" not in content
    assert "Optimization timeout" in content
