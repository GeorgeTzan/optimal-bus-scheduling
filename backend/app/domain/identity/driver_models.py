"""Insert-only record that a driver acknowledged one trip of one exact publication."""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, CheckConstraint
from db.database import Base


def now():
    return datetime.now(timezone.utc)


class DriverAcknowledgment(Base):
    __tablename__ = 'domain_driver_acknowledgments'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'), UniqueConstraint('tenant_id', 'publication_id', 'trip_id', 'driver_id'), UniqueConstraint('tenant_id', 'request_id', 'trip_id'),
        ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'acknowledged_by'], ['users.ktel_id', 'users.id']),
        ForeignKeyConstraint(['tenant_id', 'publication_id', 'revision_id'], ['domain_publications.tenant_id', 'domain_publications.publication_id', 'domain_publications.revision_id']),
        CheckConstraint('revision_version>0'))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    publication_id = Column(String, nullable=False)
    revision_id = Column(String, nullable=False)
    revision_version = Column(Integer, nullable=False)
    trip_id = Column(String, nullable=False)
    driver_id = Column(Integer, nullable=False)
    acknowledged_by = Column(Integer, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=False, default=now)
    request_id = Column(String(36), nullable=False)
