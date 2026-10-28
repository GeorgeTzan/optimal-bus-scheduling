import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL, User, Trip, Driver, Solution
from app.domain.identity.tenant_session import audit_tenant_schema
from app.domain.events.outbox import sanitize_payload, SENSITIVE_KEYS


def test_schema_has_tenant_isolation_for_all_operational_tables():
    """
    Every tenant-owned operational table must have a tenant_id or ktel_id column.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    missing = audit_tenant_schema(Base.metadata)
    assert len(missing) == 0


def test_secrets_redaction_audit():
    """
    Audit of payload sanitization: any dictionary with sensitive keys
    is purged before broadcast or persistence to logs/outbox.
    """
    raw_payload = {
        "event": "solver_finished",
        "user_email": "dispatcher@ktel.gr",
        "password": "plain_password_123",
        "hashed_password": "$2b$12$...hash...",
        "token": "eyJhbGciOi...",
        "api_key": "live_key_xyz",
        "traceback": "Traceback: File secret_server.py line 42",
        "nested": {
            "secret": "db_password",
            "safe_metric": 42.5,
        },
    }

    clean = sanitize_payload(raw_payload)

    # Verify sensitive keys purged
    for key in SENSITIVE_KEYS:
        assert key not in clean
    assert "secret" not in clean["nested"]
    assert clean["nested"]["safe_metric"] == 42.5
    assert clean["user_email"] == "dispatcher@ktel.gr"
