from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, ForeignKey, ForeignKeyConstraint, DateTime, Date, JSON
from sqlalchemy.orm import relationship

from db.database import Base


class WorkforceDriver(Base):
    version = Column(Integer, nullable=False, default=1)
    external_source = Column(String, nullable=True)
    external_key = Column(String, nullable=True)
    __tablename__ = "domain_drivers"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    code = Column(String, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    license_number = Column(String, nullable=True)
    home_station_id = Column(Integer, nullable=True)
    max_daily_driving_minutes = Column(Integer, default=540)
    max_continuous_driving_minutes = Column(Integer, default=270)
    min_daily_rest_minutes = Column(Integer, default=660)
    is_active = Column(Boolean, default=True)
    properties = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    qualifications = relationship("DriverQualification", back_populates="driver", cascade="all, delete-orphan")


Driver = WorkforceDriver


class DriverAvailability(Base):
    """Dated working or unavailable time. Missing rows mean unknown, never available. Written only by office services."""
    __tablename__ = "domain_driver_availabilities"
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "recorded_by"], ["users.ktel_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "source_leave_id"], ["domain_leave_requests.tenant_id", "domain_leave_requests.id"]),
        CheckConstraint("kind IN ('available','unavailable')"), CheckConstraint("status IN ('active','retired')"),
        CheckConstraint("category IS NULL OR category IN ('sick','training','other','leave')"),
        CheckConstraint("kind='unavailable' OR (end_utc IS NOT NULL AND category IS NULL)"),
        CheckConstraint("end_utc IS NULL OR end_utc > start_utc"), CheckConstraint("version>0"))

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    driver_id = Column(Integer, ForeignKey("domain_drivers.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    start_utc = Column(DateTime(timezone=True), nullable=False)
    end_utc = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="active")
    category = Column(String, nullable=True)
    source_leave_id = Column(Integer, nullable=True)
    recorded_by = Column(Integer, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    version = Column(Integer, nullable=False, default=1)


class DriverQualification(Base):
    __tablename__ = "domain_driver_qualifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    driver_id = Column(Integer, ForeignKey("domain_drivers.id"), nullable=False, index=True)
    qualification_code = Column(String, nullable=False)
    valid_until = Column(Date, nullable=True)

    driver = relationship("WorkforceDriver", back_populates="qualifications")
