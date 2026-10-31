from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from db.database import Base


class Incident(Base):
    __tablename__ = "domain_incidents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    incident_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=True, index=True)
    trip_id = Column(String, nullable=True, index=True)
    description = Column(String, nullable=False)
    reported_by = Column(String, nullable=False)
    status = Column(String, default="open", index=True, nullable=False)  # open, resolving, resolved, cancelled
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)


class RecoveryProposal(Base):
    __tablename__ = "domain_recovery_proposals"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    incident_id = Column(Integer, ForeignKey("domain_incidents.id"), nullable=False, index=True)
    as_of_minutes = Column(Integer, nullable=False)
    reassignments = Column(JSON, default=list, nullable=False)
    status = Column(String, default="pending_approval", index=True, nullable=False)  # pending_approval, approved, rejected
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
