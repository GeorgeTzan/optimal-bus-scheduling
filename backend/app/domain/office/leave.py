"""Leave: pending -> approved | rejected | cancelled. Authority comes only from approval routes."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from db.models import KTEL
from app.domain.identity.models import Membership
from app.domain.office.availability import require_drivers, resolve_interval
from app.domain.office.models import LeaveRequest
from app.domain.office.permissions import office_capabilities, require_office_permission, resolve_approver_routes
from app.domain.workforce.models import DriverAvailability


def leave_view(row, private=False):
    iso = lambda value: value.astimezone(timezone.utc).isoformat() if value else None
    view = {'id': row.id, 'version': row.version, 'driver_id': row.driver_id, 'state': row.state, 'start_utc': iso(row.start_utc), 'end_utc': iso(row.end_utc),
            'requested_by': row.requested_by, 'decided_by': row.decided_by, 'decision_basis': row.decision_basis,
            'stated_decision_maker': row.stated_decision_maker, 'decided_at': iso(row.decided_at)}
    if private:
        view.update(category=row.category, private_note=row.private_note, decision_note=row.decision_note, cancel_reason=row.cancel_reason)
    return view


def decision_options(db, user, leave):
    """Who the caller can act as for a pending or approved request: a route member, or staff recording an external contact's decision."""
    if leave.state not in ('pending', 'approved'):
        return None
    if db.query(Membership.driver_id).filter_by(tenant_id=user.ktel_id, id=user.membership_id).scalar() == leave.driver_id:
        return {'member': False, 'external': []}
    routes, manage = resolve_approver_routes(db, user.ktel_id, leave.driver_id), 'availability.manage' in office_capabilities(db, user)
    return {'member': any(route.membership_id == user.membership_id for route in routes),
            'external': [{'id': route.id, 'name': route.external_contact_name} for route in routes if route.external_contact_name and manage]}


def _create_leave(db, user, driver_id: int, req) -> LeaveRequest:
    if not require_drivers(db, user.ktel_id, {driver_id})[driver_id].is_active:
        raise HTTPException(409, {'code': 'driver_archived', 'message': 'This driver is archived.'})
    start, end = resolve_interval(req, db.query(KTEL.timezone).filter_by(id=user.ktel_id).scalar())
    row = LeaveRequest(tenant_id=user.ktel_id, driver_id=driver_id, start_utc=start, end_utc=end, category=req.category,
                       private_note=req.private_note, requested_by=user.id)
    db.add(row)
    db.flush()
    return row


def request_leave(db, user, req) -> LeaveRequest:
    require_office_permission(db, user, 'availability.manage')
    return _create_leave(db, user, req.driver_id, req)


def request_own_leave(db, user, driver_id: int, req) -> LeaveRequest:
    """The caller has already proved, through the session, that this is their own driver record."""
    return _create_leave(db, user, driver_id, req)


def cancel_own_pending_leave(db, user, driver_id: int, leave_id: int, req) -> LeaveRequest:
    leave = _locked_own(db, user, driver_id, leave_id, req.expected_version)
    if leave.state != 'pending':
        raise HTTPException(409, {'code': 'not_cancellable', 'message': 'Only a request that is still waiting can be cancelled here. Ask the office.'})
    leave.state, leave.cancelled_by, leave.cancelled_at, leave.cancel_reason, leave.version = 'cancelled', user.id, datetime.now(timezone.utc), 'Cancelled by the driver', leave.version + 1
    db.flush()
    return leave


def _locked_own(db, user, driver_id: int, leave_id: int, expected_version: int) -> LeaveRequest:
    row = db.query(LeaveRequest).filter_by(tenant_id=user.ktel_id, id=leave_id, driver_id=driver_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Leave request not found')
    if row.version != expected_version:
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This request changed. Reload before cancelling.'})
    return row


def _locked(db, user, leave_id: int, expected_version: int) -> LeaveRequest:
    row = db.query(LeaveRequest).filter_by(tenant_id=user.ktel_id, id=leave_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Leave request not found')
    if row.version != expected_version:
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This request changed. Refresh before deciding.'})
    return row


def _decider(db, user, leave, external_route_id):
    """Returns (basis, route_id, stated_decision_maker) or raises. Own leave is refused through the explicit driver link."""
    if db.query(Membership.driver_id).filter_by(tenant_id=user.ktel_id, id=user.membership_id).scalar() == leave.driver_id:
        raise HTTPException(403, {'code': 'own_leave', 'message': 'You cannot decide your own leave.'})
    routes = resolve_approver_routes(db, user.ktel_id, leave.driver_id)
    if not routes:
        raise HTTPException(409, {'code': 'approver_missing', 'message': 'No approver is configured for this driver.'})
    if external_route_id is None:
        if not any(route.membership_id == user.membership_id for route in routes):
            raise HTTPException(403, {'code': 'not_approver', 'message': 'You are not an approver for this driver.'})
        return 'member', None, None
    route = next((route for route in routes if route.id == external_route_id and route.external_contact_name), None)
    if route is None:
        raise HTTPException(422, 'Choose an external approver configured for this driver.')
    require_office_permission(db, user, 'availability.manage')
    return 'external', route.id, route.external_contact_name


def decide_leave(db, user, leave_id: int, req) -> LeaveRequest:
    leave = _locked(db, user, leave_id, req.expected_version)
    if leave.state != 'pending':
        raise HTTPException(409, {'code': 'not_pending', 'message': 'This request was already decided.'})
    basis, route_id, maker = _decider(db, user, leave, req.external_route_id)
    leave.state, leave.decided_by, leave.decision_basis, leave.external_route_id = req.decision, user.id, basis, route_id
    leave.stated_decision_maker, leave.decided_at, leave.decision_note, leave.version = maker, datetime.now(timezone.utc), req.note, leave.version + 1
    if req.decision == 'approved':
        db.add(DriverAvailability(tenant_id=user.ktel_id, driver_id=leave.driver_id, kind='unavailable', start_utc=leave.start_utc, end_utc=leave.end_utc,
                                  status='active', category='leave', source_leave_id=leave.id, recorded_by=user.id))
    db.flush()
    return leave


def cancel_leave(db, user, leave_id: int, req) -> LeaveRequest:
    leave = _locked(db, user, leave_id, req.expected_version)
    if leave.state == 'pending':
        require_office_permission(db, user, 'availability.manage')
    elif leave.state == 'approved':
        _decider(db, user, leave, req.external_route_id)
    else:
        raise HTTPException(409, {'code': 'not_cancellable', 'message': 'This request can no longer be cancelled.'})
    leave.state, leave.cancelled_by, leave.cancelled_at, leave.cancel_reason, leave.version = 'cancelled', user.id, datetime.now(timezone.utc), req.reason, leave.version + 1
    db.query(DriverAvailability).filter_by(tenant_id=user.ktel_id, source_leave_id=leave.id, status='active').update(
        {'status': 'retired', 'version': DriverAvailability.version + 1}, synchronize_session=False)
    db.flush()
    return leave


def list_leave(db, tenant_id: int, date_from: date, date_to: date, driver_id: int | None) -> list[LeaveRequest]:
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=tenant_id).scalar())
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    query = db.query(LeaveRequest).filter(LeaveRequest.tenant_id == tenant_id, LeaveRequest.start_utc < end, LeaveRequest.end_utc > start)
    if driver_id is not None:
        query = query.filter(LeaveRequest.driver_id == driver_id)
    return query.order_by(LeaveRequest.start_utc, LeaveRequest.id).limit(500).all()
