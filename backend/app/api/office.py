from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from api.deps import get_current_user
from db.models import KTEL
from db.database import get_db
from app.domain.identity.models import Membership
from app.domain.identity.permissions import require_permission
from app.domain.office.audit import lock_organization, office_record, office_replay
from app.domain.office.availability import list_periods, retire_period, save_periods
from app.domain.identity.permissions import require_permission as require_role_permission
from app.domain.office.impacts import impact_count, impact_count_for_dates, list_office_impacts
from app.domain.office.leave import cancel_leave, decide_leave, decision_options, leave_view, list_leave, request_leave
from app.domain.office.maintenance import cancel_vehicle_period, list_vehicle_periods, release_vehicle_period, save_vehicle_period, vehicle_period_view
from app.domain.office.models import ApprovalRoute, DriverWorkingPattern, OfficeGrant
from app.domain.office.patterns import retire_pattern, save_patterns
from app.domain.office.permissions import office_capabilities, read_scope, require_office_permission
from app.domain.office.schemas import GrantSet, LeaveCancel, LeaveCreate, LeaveDecision, PatternBatch, PeriodBatch, Retire, RouteCreate, RoutePatch, VehicleCancel, VehiclePeriodSave, VehicleRelease
from app.domain.workforce.models import WorkforceDriver

router = APIRouter(prefix='/api/v1/office', tags=['office'])


def grant_view(row):
    return {'id': row.id, 'membership_id': row.membership_id, 'capability': row.capability, 'is_active': row.is_active, 'version': row.version}


def route_view(row):
    return {'id': row.id, 'driver_id': row.driver_id, 'membership_id': row.membership_id,
            'external_contact_name': row.external_contact_name, 'is_active': row.is_active, 'version': row.version}


@router.get('/capabilities')
def capabilities(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {'capabilities': office_capabilities(db, user), 'timezone': db.query(KTEL.timezone).filter_by(id=user.ktel_id).scalar()}


@router.get('/grants')
def list_grants(user=Depends(require_permission('members.manage')), db: Session = Depends(get_db)):
    return {'grants': [grant_view(row) for row in db.query(OfficeGrant).filter_by(tenant_id=user.ktel_id).order_by(OfficeGrant.id)]}


@router.put('/grants')
def set_grant(req: GrantSet, user=Depends(require_permission('members.manage')), db: Session = Depends(get_db)):
    payload = req.model_dump(mode='json')
    lock_organization(db, user.ktel_id)
    previous = office_replay(db, user.ktel_id, user.id, str(req.request_id), payload)
    if previous is not None:
        return previous
    member = db.query(Membership).filter_by(tenant_id=user.ktel_id, id=req.membership_id).first()
    if member is None or (req.is_active and not member.is_active):  # a deactivated member's grants can still be revoked
        raise HTTPException(404, 'Organization member not found')
    row = db.query(OfficeGrant).filter_by(tenant_id=user.ktel_id, membership_id=req.membership_id, capability=req.capability).populate_existing().with_for_update().first()
    if row is None and req.expected_version is None:
        row = OfficeGrant(tenant_id=user.ktel_id, membership_id=req.membership_id, capability=req.capability, is_active=req.is_active, granted_by=user.id)
        db.add(row)
    elif row is not None and req.expected_version == row.version:
        row.is_active, row.granted_by, row.granted_at, row.version = req.is_active, user.id, datetime.now(timezone.utc), row.version + 1
    else:
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This grant changed. Refresh before editing.'})
    db.flush()
    response = grant_view(row)
    office_record(db, user.ktel_id, user.id, str(req.request_id), 'grant', 'set', payload, response)
    db.commit()
    return response


@router.get('/approval-routes')
def list_routes(user=Depends(require_permission('members.manage')), db: Session = Depends(get_db)):
    return {'routes': [route_view(row) for row in db.query(ApprovalRoute).filter_by(tenant_id=user.ktel_id).order_by(ApprovalRoute.id)]}


@router.post('/approval-routes', status_code=201)
def create_route(req: RouteCreate, user=Depends(require_permission('members.manage')), db: Session = Depends(get_db)):
    payload = req.model_dump(mode='json')
    lock_organization(db, user.ktel_id)
    previous = office_replay(db, user.ktel_id, user.id, str(req.request_id), payload)
    if previous is not None:
        return previous
    if req.driver_id is not None and db.query(WorkforceDriver.id).filter_by(tenant_id=user.ktel_id, id=req.driver_id).first() is None:
        raise HTTPException(404, 'Driver not found')
    if req.membership_id is not None and db.query(Membership.id).filter_by(tenant_id=user.ktel_id, id=req.membership_id, is_active=True).first() is None:
        raise HTTPException(404, 'Organization member not found')
    row = ApprovalRoute(tenant_id=user.ktel_id, driver_id=req.driver_id, membership_id=req.membership_id,
                        external_contact_name=req.external_contact_name, created_by=user.id)
    db.add(row)
    db.flush()
    response = route_view(row)
    office_record(db, user.ktel_id, user.id, str(req.request_id), 'approval_route', 'create', payload, response)
    db.commit()
    return response


@router.patch('/approval-routes/{route_id}')
def update_route(route_id: int, req: RoutePatch, user=Depends(require_permission('members.manage')), db: Session = Depends(get_db)):
    payload = {**req.model_dump(mode='json'), 'route_id': route_id}
    lock_organization(db, user.ktel_id)
    previous = office_replay(db, user.ktel_id, user.id, str(req.request_id), payload)
    if previous is not None:
        return previous
    row = db.query(ApprovalRoute).filter_by(tenant_id=user.ktel_id, id=route_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Approval route not found')
    if row.version != req.expected_version:
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This route changed. Refresh before editing.'})
    row.is_active, row.version = req.is_active, row.version + 1
    db.flush()
    response = route_view(row)
    office_record(db, user.ktel_id, user.id, str(req.request_id), 'approval_route', 'update', payload, response)
    db.commit()
    return response


def pattern_view(row):
    return {'id': row.id, 'version': row.version, 'driver_id': row.driver_id, 'weekday_mask': row.weekday_mask,
            'local_start': row.local_start.strftime('%H:%M'), 'local_end': row.local_end.strftime('%H:%M'), 'ends_next_day': row.ends_next_day,
            'valid_from': row.valid_from.isoformat(), 'valid_until': row.valid_until.isoformat(), 'status': row.status}


def period_view(row, private=False):
    view = {'id': row.id, 'version': row.version, 'driver_id': row.driver_id, 'kind': row.kind, 'status': row.status,
            'start_utc': row.start_utc.astimezone(timezone.utc).isoformat(), 'end_utc': row.end_utc.astimezone(timezone.utc).isoformat() if row.end_utc else None}
    return {**view, 'category': row.category} if private else view


def run_once(db, user, req, entity, action, work, extra=None):
    """Shared write path: organization lock, idempotent replay, one atomic unit of work, audit, commit."""
    payload = {**req.model_dump(mode='json'), **(extra or {})}
    lock_organization(db, user.ktel_id)
    previous = office_replay(db, user.ktel_id, user.id, str(req.request_id), payload)
    if previous is not None:
        return previous
    response = work()
    office_record(db, user.ktel_id, user.id, str(req.request_id), entity, action, payload, response)
    db.commit()
    return response


def save_items(db, user, req, entity, save, view, extras=None):
    require_office_permission(db, user, 'availability.manage')

    def work():
        rows = save(db, user, req.items)
        return {'items': [view(row) for row in rows], **(extras(rows) if extras else {})}
    return run_once(db, user, req, entity, 'save', work)


def with_impacts(db, user, view, start, end):
    """Mutation responses say how many trips now need review. Nothing is moved, cancelled or published."""
    return {**view, 'impact_count': impact_count(db, user.ktel_id, start, end)}


@router.get('/working-patterns')
def list_patterns(driver_id: int | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_office_permission(db, user, 'availability.manage')
    query = db.query(DriverWorkingPattern).filter_by(tenant_id=user.ktel_id, status='active')
    if driver_id is not None:
        query = query.filter_by(driver_id=driver_id)
    return {'items': [pattern_view(row) for row in query.order_by(DriverWorkingPattern.id).limit(500)]}


@router.post('/working-patterns')
def save_working_patterns(req: PatternBatch, user=Depends(get_current_user), db: Session = Depends(get_db)):
    today_window = lambda _rows: {'impact_count': impact_count_for_dates(db, user.ktel_id, date.min, date.max)}  # a pattern edit can shrink any day, so check the whole next 31 days
    return save_items(db, user, req, 'working_pattern', save_patterns, pattern_view, today_window)


@router.get('/driver-periods')
def get_driver_periods(date_from: date, date_to: date = Query(), driver_id: int | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    can_read, can_see_private = read_scope(db, user)
    if not 0 <= (date_to - date_from).days <= 62:
        raise HTTPException(422, 'Choose a date range of at most 62 days.')
    return {'items': [period_view(row, can_see_private(row.driver_id)) for row in list_periods(db, user.ktel_id, date_from, date_to, driver_id) if can_read(row.driver_id)]}


@router.post('/driver-periods')
def save_driver_periods(req: PeriodBatch, user=Depends(get_current_user), db: Session = Depends(get_db)):
    def extras(rows):
        blocking = [row for row in rows if row.status == 'active']
        exact = impact_count(db, user.ktel_id, min(row.start_utc for row in blocking), None if any(row.end_utc is None for row in blocking) else max(row.end_utc for row in blocking)) if blocking else 0
        return {'impact_count': max(exact, impact_count_for_dates(db, user.ktel_id, date.min, date.max))}  # an edit can also move a window away from days outside the new interval
    return save_items(db, user, req, 'driver_period', save_periods, period_view, extras)


@router.get('/leave-requests')
def get_leave_requests(date_from: date, date_to: date = Query(), driver_id: int | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    can_read, can_see_private = read_scope(db, user)
    if not 0 <= (date_to - date_from).days <= 62:
        raise HTTPException(422, 'Choose a date range of at most 62 days.')
    return {'items': [{**leave_view(row, can_see_private(row.driver_id)), 'decision': decision_options(db, user, row)}
                      for row in list_leave(db, user.ktel_id, date_from, date_to, driver_id) if can_read(row.driver_id)]}


@router.post('/leave-requests', status_code=201)
def create_leave_request(req: LeaveCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'leave_request', 'create', lambda: leave_view(request_leave(db, user, req)))


@router.post('/leave-requests/{leave_id}/decision')
def decide_leave_request(leave_id: int, req: LeaveDecision, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'leave_request', req.decision, lambda: (lambda row: with_impacts(db, user, leave_view(row), row.start_utc, row.end_utc) if row.state == 'approved' else leave_view(row))(decide_leave(db, user, leave_id, req)), {'leave_id': leave_id})


@router.post('/leave-requests/{leave_id}/cancel')
def cancel_leave_request(leave_id: int, req: LeaveCancel, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'leave_request', 'cancel', lambda: (lambda row: with_impacts(db, user, leave_view(row), row.start_utc, row.end_utc))(cancel_leave(db, user, leave_id, req)), {'leave_id': leave_id})


@router.get('/vehicle-periods')
def get_vehicle_periods(date_from: date, date_to: date = Query(), vehicle_id: int | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_office_permission(db, user, 'maintenance.manage')
    if not 0 <= (date_to - date_from).days <= 62:
        raise HTTPException(422, 'Choose a date range of at most 62 days.')
    return {'items': [vehicle_period_view(row) for row in list_vehicle_periods(db, user, date_from, date_to, vehicle_id)]}


@router.post('/vehicle-periods')
def save_vehicle_period_route(req: VehiclePeriodSave, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'vehicle_period', 'save', lambda: (lambda row: with_impacts(db, user, vehicle_period_view(row), row.start_utc, row.end_utc))(save_vehicle_period(db, user, req)))


@router.post('/vehicle-periods/{period_id}/release')
def release_vehicle_period_route(period_id: int, req: VehicleRelease, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'vehicle_period', 'release', lambda: (lambda row: with_impacts(db, user, vehicle_period_view(row), row.start_utc, row.end_utc))(release_vehicle_period(db, user, period_id, req)), {'period_id': period_id})


@router.post('/vehicle-periods/{period_id}/cancel')
def cancel_vehicle_period_route(period_id: int, req: VehicleCancel, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return run_once(db, user, req, 'vehicle_period', 'cancel', lambda: (lambda row: with_impacts(db, user, vehicle_period_view(row), row.start_utc, row.end_utc))(cancel_vehicle_period(db, user, period_id, req)), {'period_id': period_id})


@router.post('/working-patterns/{pattern_id}/retire')
def retire_working_pattern(pattern_id: int, req: Retire, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_office_permission(db, user, 'availability.manage')
    return run_once(db, user, req, 'working_pattern', 'retire', lambda: (lambda row: {**pattern_view(row), 'impact_count': impact_count_for_dates(db, user.ktel_id, row.valid_from, row.valid_until)})(retire_pattern(db, user, pattern_id, req.expected_version)), {'pattern_id': pattern_id})


@router.post('/driver-periods/{period_id}/retire')
def retire_driver_period(period_id: int, req: Retire, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_office_permission(db, user, 'availability.manage')
    return run_once(db, user, req, 'driver_period', 'retire', lambda: (lambda row: with_impacts(db, user, period_view(row), row.start_utc, row.end_utc))(retire_period(db, user, period_id, req.expected_version)), {'period_id': period_id})


@router.get('/impacts')
def get_impacts(date_from: date, date_to: date = Query(), page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
                user=Depends(require_role_permission('schedule.read')), db: Session = Depends(get_db)):
    """Read-only. Shows trips in the latest publication and open drafts that current availability puts at risk; it never changes anything."""
    if not 0 <= (date_to - date_from).days <= 30:
        raise HTTPException(422, 'Choose a date range of at most 31 days.')
    return list_office_impacts(db, user.ktel_id, date_from=date_from, date_to=date_to, page=page, page_size=page_size)
