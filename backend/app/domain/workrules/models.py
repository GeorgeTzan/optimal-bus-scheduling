from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from db.database import Base


def now():
    return datetime.now(timezone.utc)


class CompanyWorkRules(Base):
    __tablename__ = 'domain_company_work_rules'
    __table_args__ = (ForeignKeyConstraint(['tenant_id', 'updated_by'], ['users.ktel_id', 'users.id']), CheckConstraint('version>0'))
    tenant_id = Column(Integer, ForeignKey('ktels.id'), primary_key=True)
    overrides = Column(JSON, nullable=False, default=dict)
    warning_rules = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)


class DriverWorkProfile(Base):
    __tablename__ = 'domain_driver_work_profiles'
    __table_args__ = (ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']), CheckConstraint('version>0'))
    tenant_id = Column(Integer, ForeignKey('ktels.id'), primary_key=True)
    driver_id = Column(Integer, primary_key=True)
    overnight_allowed = Column(Boolean, nullable=False, default=True)
    split_shift_allowed = Column(Boolean, nullable=False, default=True)
    must_return_to_base = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)


class DriverRouteRule(Base):
    __tablename__ = 'domain_driver_route_rules'
    __table_args__ = (UniqueConstraint('tenant_id', 'driver_id', 'route_id'),
        ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'route_id'], ['domain_routes.tenant_id', 'domain_routes.id']),
        CheckConstraint("kind IN ('prefer','forbid')"))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    driver_id = Column(Integer, nullable=False)
    route_id = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)


class VehicleRouteRule(Base):
    __tablename__ = 'domain_vehicle_route_rules'
    __table_args__ = (UniqueConstraint('tenant_id', 'vehicle_id', 'route_id'),
        ForeignKeyConstraint(['tenant_id', 'vehicle_id'], ['domain_vehicles.tenant_id', 'domain_vehicles.id']),
        ForeignKeyConstraint(['tenant_id', 'route_id'], ['domain_routes.tenant_id', 'domain_routes.id']))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    vehicle_id = Column(Integer, nullable=False)
    route_id = Column(Integer, nullable=False)


class DriverWorkBaseline(Base):
    __tablename__ = 'domain_driver_work_baselines'
    __table_args__ = (ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'updated_by'], ['users.ktel_id', 'users.id']),
        CheckConstraint('overtime_minutes>=0'), CheckConstraint('owed_rest_minutes>=0'), CheckConstraint('version>0'))
    tenant_id = Column(Integer, ForeignKey('ktels.id'), primary_key=True)
    driver_id = Column(Integer, primary_key=True)
    as_of = Column(Date, nullable=False)
    overtime_minutes = Column(Integer, nullable=False, default=0)
    last_duty_end = Column(DateTime(timezone=True), nullable=True)
    last_weekly_rest_end = Column(DateTime(timezone=True), nullable=True)
    last_weekly_rest_at_base = Column(Boolean, nullable=False, default=False)
    owed_rest_minutes = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=True)


class WorkRuleOverride(Base):
    __tablename__ = 'domain_work_rule_overrides'
    __table_args__ = (UniqueConstraint('tenant_id', 'revision_id', 'finding_key'),
        ForeignKeyConstraint(['tenant_id', 'revision_id'], ['domain_schedule_revisions.tenant_id', 'domain_schedule_revisions.revision_id']),
        ForeignKeyConstraint(['tenant_id', 'actor_id'], ['users.ktel_id', 'users.id']))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    revision_id = Column(String, nullable=False)
    finding_key = Column(String, nullable=False)
    reason = Column(String(1000), nullable=False)
    actor_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
