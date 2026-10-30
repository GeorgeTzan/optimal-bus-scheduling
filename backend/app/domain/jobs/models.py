from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON
from db.database import Base


class Job(Base):
    __tablename__ = "domain_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    snapshot_id = Column(String, nullable=False)
    solver_version = Column(String, nullable=False, default="cv-bounded-v1")
    config = Column(JSON, default=dict)
    idempotency_key = Column(String, index=True, nullable=True)
    status = Column(String, default="queued", index=True)  # queued, claimed, running, completed, failed, cancelled
    attempt_token = Column(Integer, default=0, nullable=False)
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    heartbeat_at = Column(DateTime, nullable=True)
    progress_pct = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    result_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
