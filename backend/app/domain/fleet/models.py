from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, ForeignKey, ForeignKeyConstraint, DateTime, JSON

from db.database import Base


class Vehicle(Base):
    version = Column(Integer, nullable=False, default=1)
    external_source = Column(String, nullable=True)
    external_key = Column(String, nullable=True)
    __tablename__ = "domain_vehicles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    code = Column(String, nullable=False, default=lambda: "V-"+uuid4().hex[:8].upper())
    registration_plate = Column(String, index=True, nullable=True)
    bus_type = Column(String, nullable=False, default="standard_12m")
    capacity = Column(Integer, nullable=True, default=None)
    home_station_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    properties = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))



class VehicleAvailability(Base):
    """Planned maintenance reservations (finite) and actual out-of-service holds (open until an explicit release). Written only by office services."""
    __tablename__ = "domain_vehicle_availabilities"
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "recorded_by"], ["users.ktel_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "released_by"], ["users.ktel_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "cancelled_by"], ["users.ktel_id", "users.id"]),
        CheckConstraint("kind IN ('planned_maintenance','out_of_service')"), CheckConstraint("status IN ('active','released','cancelled')"),
        CheckConstraint("kind<>'planned_maintenance' OR end_utc IS NOT NULL"), CheckConstraint("end_utc IS NULL OR end_utc > start_utc"),
        CheckConstraint("status<>'released' OR (kind='out_of_service' AND released_at IS NOT NULL AND released_by IS NOT NULL)"), CheckConstraint("version>0"))

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    vehicle_id = Column(Integer, ForeignKey("domain_vehicles.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    start_utc = Column(DateTime(timezone=True), nullable=False)
    end_utc = Column(DateTime(timezone=True), nullable=True)
    estimated_end_utc = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="active")
    responsible_label = Column(String(200), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    released_by = Column(Integer, nullable=True)
    release_note = Column(String(500), nullable=True)
    cancelled_by = Column(Integer, nullable=True)
    cancel_reason = Column(String(1000), nullable=True)
    recorded_by = Column(Integer, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    version = Column(Integer, nullable=False, default=1)
