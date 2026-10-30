from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Session

from db.database import Base


SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "secret",
    "api_key",
    "traceback",
    "stack_trace",
}


def sanitize_payload(obj: Any) -> Any:
    """Recursively removes sensitive credentials and internal tracebacks from event payloads."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS:
                continue
            sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj


class OutboxEvent(Base):
    __tablename__ = "domain_outbox_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    job_id = Column(String, index=True, nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class OutboxService:
    def __init__(self, db: Session):
        self.db = db

    def emit(
        self,
        tenant_id: int,
        event_type: str,
        job_id: Optional[str],
        payload: Dict[str, Any],
    ) -> OutboxEvent:
        clean_payload = sanitize_payload(payload)
        event = OutboxEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            job_id=job_id,
            payload=clean_payload,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()
        return event

    def get_events_after(
        self,
        tenant_id: int,
        cursor: int = 0,
        limit: int = 100,
    ) -> List[OutboxEvent]:
        return (
            self.db.query(OutboxEvent)
            .filter(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.id > cursor,
            )
            .order_by(OutboxEvent.id.asc())
            .limit(limit)
            .all()
        )
