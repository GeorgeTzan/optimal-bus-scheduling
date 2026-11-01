"""Per-member office authority, leave approval routing and append-only office history."""
from datetime import datetime, timezone
from typing import Literal, get_args
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Time, UniqueConstraint
from db.database import Base

Capability = Literal['availability.manage', 'maintenance.manage', 'maintenance.release', 'office.notes.read']
CAPABILITIES = get_args(Capability)


def now():
    return datetime.now(timezone.utc)


class OfficeGrant(Base):
    __tablename__ = 'domain_office_grants'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'), UniqueConstraint('tenant_id', 'membership_id', 'capability'),
        ForeignKeyConstraint(['tenant_id', 'membership_id'], ['domain_memberships.tenant_id', 'domain_memberships.id']),
        ForeignKeyConstraint(['tenant_id', 'granted_by'], ['users.ktel_id', 'users.id']),
        CheckConstraint('capability IN (' + ','.join(f"'{value}'" for value in CAPABILITIES) + ')'), CheckConstraint('version>0'))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    membership_id = Column(Integer, nullable=False)
    capability = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    granted_by = Column(Integer, nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=now)
    version = Column(Integer, nullable=False, default=1)


class DriverWorkingPattern(Base):
    """A repeating weekly working time, valid for a bounded date range. weekday_mask: bit 0 Monday .. bit 6 Sunday."""
    __tablename__ = 'domain_driver_working_patterns'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'),
        ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'recorded_by'], ['users.ktel_id', 'users.id']),
        CheckConstraint('weekday_mask BETWEEN 1 AND 127'), CheckConstraint('valid_until >= valid_from AND valid_until - valid_from <= 366'),
        CheckConstraint('ends_next_day OR local_end > local_start'), CheckConstraint("status IN ('active','retired')"), CheckConstraint('version>0'))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    driver_id = Column(Integer, nullable=False)
    weekday_mask = Column(Integer, nullable=False)
    local_start = Column(Time, nullable=False)
    local_end = Column(Time, nullable=False)
    ends_next_day = Column(Boolean, nullable=False, default=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    status = Column(String, nullable=False, default='active')
    recorded_by = Column(Integer, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=now)
    version = Column(Integer, nullable=False, default=1)


class ApprovalRoute(Base):
    """Who may decide leave: a member, or an external contact recorded by staff. A null driver is the organization default."""
    __tablename__ = 'domain_leave_approval_routes'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'),
        ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'membership_id'], ['domain_memberships.tenant_id', 'domain_memberships.id']),
        ForeignKeyConstraint(['tenant_id', 'created_by'], ['users.ktel_id', 'users.id']),
        CheckConstraint('(membership_id IS NULL) <> (external_contact_name IS NULL)'), CheckConstraint('version>0'))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    driver_id = Column(Integer, nullable=True)
    membership_id = Column(Integer, nullable=True)
    external_contact_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    version = Column(Integer, nullable=False, default=1)


class OfficeAudit(Base):
    """Append-only history that doubles as the idempotency record for office writes."""
    __tablename__ = 'domain_office_audit'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'), UniqueConstraint('tenant_id', 'request_id'),
        ForeignKeyConstraint(['tenant_id', 'actor_id'], ['users.ktel_id', 'users.id']))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    entity = Column(String, nullable=False)
    action = Column(String, nullable=False)
    actor_id = Column(Integer, nullable=False)
    request_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    response_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class LeaveRequest(Base):
    """pending -> approved | rejected | cancelled. The subject driver is distinct from the recorder and from the decider."""
    __tablename__ = 'domain_leave_requests'
    __table_args__ = (UniqueConstraint('tenant_id', 'id'),
        ForeignKeyConstraint(['tenant_id', 'driver_id'], ['domain_drivers.tenant_id', 'domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id', 'requested_by'], ['users.ktel_id', 'users.id']),
        ForeignKeyConstraint(['tenant_id', 'decided_by'], ['users.ktel_id', 'users.id']),
        ForeignKeyConstraint(['tenant_id', 'cancelled_by'], ['users.ktel_id', 'users.id']),
        ForeignKeyConstraint(['tenant_id', 'external_route_id'], ['domain_leave_approval_routes.tenant_id', 'domain_leave_approval_routes.id']),
        CheckConstraint("state IN ('pending','approved','rejected','cancelled')"), CheckConstraint("category IN ('annual','sick','unpaid','other')"),
        CheckConstraint("decision_basis IS NULL OR decision_basis IN ('member','external')"), CheckConstraint('end_utc > start_utc'), CheckConstraint('version>0'))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    driver_id = Column(Integer, nullable=False)
    start_utc = Column(DateTime(timezone=True), nullable=False)
    end_utc = Column(DateTime(timezone=True), nullable=False)
    category = Column(String, nullable=False)
    private_note = Column(String(500), nullable=True)
    state = Column(String, nullable=False, default='pending')
    requested_by = Column(Integer, nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=now)
    decided_by = Column(Integer, nullable=True)
    decision_basis = Column(String, nullable=True)
    external_route_id = Column(Integer, nullable=True)
    stated_decision_maker = Column(String(200), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(String(500), nullable=True)
    cancelled_by = Column(Integer, nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(String(1000), nullable=True)
    version = Column(Integer, nullable=False, default=1)
