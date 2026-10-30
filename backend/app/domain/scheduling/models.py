from datetime import datetime, date, timezone
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, JSON, UniqueConstraint
from sqlalchemy.orm import relationship

from db.database import Base


class SchedulingPeriod(Base):
    __tablename__ = "domain_scheduling_periods"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScheduleRevision(Base):
    __tablename__ = "domain_schedule_revisions"

    id = Column(Integer, primary_key=True, index=True)
    revision_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    period_id = Column(Integer, ForeignKey("domain_scheduling_periods.id"), index=True, nullable=False)
    parent_revision_id = Column(String, index=True, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String, default="draft", index=True, nullable=False)  # draft, approval_requested, approved, published, archived
    author = Column(String, nullable=False)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    assignments = relationship("RevisionAssignment", back_populates="revision", cascade="all, delete-orphan")


class RevisionAssignment(Base):
    __tablename__ = "domain_revision_assignments"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    revision_id = Column(String, ForeignKey("domain_schedule_revisions.revision_id"), index=True, nullable=False)
    trip_id = Column(String, index=True, nullable=False)
    resource_id = Column(String, index=True, nullable=False)
    start_minutes = Column(Integer, nullable=False)
    end_minutes = Column(Integer, nullable=False)
    start_station = Column(String, nullable=False)
    end_station = Column(String, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    cancellation_reason = Column(String(1000), nullable=True)

    revision = relationship("ScheduleRevision", back_populates="assignments")


class ApprovalRequest(Base):
    __tablename__ = "domain_approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    revision_id = Column(String, ForeignKey("domain_schedule_revisions.revision_id"), index=True, nullable=False)
    requested_by = Column(String, nullable=False)
    status = Column(String, default="pending", index=True, nullable=False)  # pending, approved, rejected
    reviewer = Column(String, nullable=True)
    review_comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime, nullable=True)


class Publication(Base):
    __table_args__=(UniqueConstraint("tenant_id","publication_id","revision_id",name="uq_publication_revision_identity"),)
    __tablename__ = "domain_publications"

    id = Column(Integer, primary_key=True, index=True)
    publication_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    revision_id = Column(String, ForeignKey("domain_schedule_revisions.revision_id"), index=True, nullable=False)
    published_by = Column(String, nullable=False)
    verification_report = Column(JSON, default=dict, nullable=False)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SchedulingAuditLog(Base):
    __tablename__ = "domain_scheduling_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    revision_id = Column(String, index=True, nullable=False)
    action = Column(String, index=True, nullable=False)
    actor = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
