from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, text
from db.database import Base

REASONS = ('no_driver', 'driver_leave', 'no_vehicle', 'work_rules', 'other')


def now():
    return datetime.now(timezone.utc)


class ReportExport(Base):
    __tablename__ = 'domain_report_exports'
    __table_args__ = (ForeignKeyConstraint(['tenant_id', 'generated_by'], ['users.ktel_id', 'users.id']),
                      CheckConstraint("format IN ('xlsx','pdf')"),
                      Index('ix_domain_report_exports_month', 'tenant_id', 'month', text('generated_at DESC')))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), index=True, nullable=False)
    month = Column(Date, nullable=False)
    format = Column(String(8), nullable=False)
    generated_by = Column(Integer, nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    fingerprint = Column(String, nullable=False)
