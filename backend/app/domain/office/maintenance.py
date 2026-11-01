"""Vehicle maintenance: finite planned reservations and open out-of-service holds ended only by explicit release."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import or_
from db.models import KTEL
from app.domain.fleet.models import Vehicle, VehicleAvailability
from app.domain.office.availability import resolve_interval
from app.domain.office.intervals import normalize_office_interval
from app.domain.office.permissions import require_office_permission
from app.domain.timetables.time_service import LocalTimeResolutionError


def vehicle_period_view(row):
    iso = lambda value: value.astimezone(timezone.utc).isoformat() if value else None
    return {'id': row.id, 'version': row.version, 'vehicle_id': row.vehicle_id, 'kind': row.kind, 'status': row.status, 'start_utc': iso(row.start_utc),
            'end_utc': iso(row.end_utc), 'estimated_end_utc': iso(row.estimated_end_utc), 'responsible_label': row.responsible_label,
            'released_at': iso(row.released_at), 'release_note': row.release_note}


def _instant(value, zone, fold, field):
    try:
        return normalize_office_interval(value, None, zone, fold, None)[0]
    except LocalTimeResolutionError as error:
        for issue in error.issues:
            issue['field'] = field
        raise HTTPException(422, {'code': error.code, 'issues': error.issues, 'message': str(error)}) from error


def _locked(db, user, period_id: int, expected_version: int) -> VehicleAvailability:
    row = db.query(VehicleAvailability).filter_by(tenant_id=user.ktel_id, id=period_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Vehicle period not found')
    if row.version != expected_version:
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This period changed. Refresh before editing.'})
    return row


def save_vehicle_period(db, user, req) -> VehicleAvailability:
    require_office_permission(db, user, 'maintenance.manage')
    vehicle = db.query(Vehicle).filter_by(tenant_id=user.ktel_id, id=req.vehicle_id).first()
    if vehicle is None:
        raise HTTPException(404, 'Vehicle not found')
    if not vehicle.is_active:
        raise HTTPException(409, {'code': 'vehicle_archived', 'message': 'This vehicle is archived.'})
    zone = db.query(KTEL.timezone).filter_by(id=user.ktel_id).scalar()
    start, end = resolve_interval(req, zone)
    estimate = _instant(req.estimated_end_local, zone, req.fold_estimate, 'estimated_end_local') if req.estimated_end_local else None
    if estimate is not None and estimate <= start:
        raise HTTPException(422, {'code': 'invalid_interval', 'message': 'The estimated return must be after the start.'})
    values = dict(start_utc=start, end_utc=end, estimated_end_utc=estimate, responsible_label=req.responsible_label)
    if req.period_id is None:
        row = VehicleAvailability(tenant_id=user.ktel_id, vehicle_id=req.vehicle_id, kind=req.kind, status='active', recorded_by=user.id, **values)
        db.add(row)
    else:
        row = _locked(db, user, req.period_id, req.expected_version)
        if row.status != 'active':
            raise HTTPException(409, {'code': 'not_active', 'message': 'Only an active period can be changed.'})
        if row.vehicle_id != req.vehicle_id or row.kind != req.kind:
            raise HTTPException(422, 'A period cannot change vehicle or kind.')
        if row.kind == 'out_of_service' and row.start_utc != start:  # moving a hold's start later would lift it without a release
            require_office_permission(db, user, 'maintenance.release')
        for name, value in values.items():
            setattr(row, name, value)
        row.recorded_by, row.recorded_at, row.version = user.id, datetime.now(timezone.utc), row.version + 1
    db.flush()
    return row


def release_vehicle_period(db, user, period_id: int, req) -> VehicleAvailability:
    """Records an operational decision; it is not a mechanical certification."""
    require_office_permission(db, user, 'maintenance.release')
    row = _locked(db, user, period_id, req.expected_version)
    if row.kind != 'out_of_service' or row.status != 'active':
        raise HTTPException(409, {'code': 'not_an_active_hold', 'message': 'Only an active out-of-service period can be released.'})
    at = _instant(req.released_at_local, db.query(KTEL.timezone).filter_by(id=user.ktel_id).scalar(), req.fold_released, 'released_at_local')
    if at <= row.start_utc or at > datetime.now(timezone.utc):
        raise HTTPException(422, {'code': 'invalid_release_time', 'message': 'The release must be after the start and not in the future.'})
    row.status, row.end_utc, row.released_at, row.released_by, row.release_note, row.version = 'released', at, at, user.id, req.note, row.version + 1
    db.flush()
    return row


def cancel_vehicle_period(db, user, period_id: int, req) -> VehicleAvailability:
    """Cancelling an entry made in error is not a release. A hold needs the release grant; a reservation needs the manage grant."""
    row = _locked(db, user, period_id, req.expected_version)
    require_office_permission(db, user, 'maintenance.release' if row.kind == 'out_of_service' else 'maintenance.manage')
    if row.status != 'active':
        raise HTTPException(409, {'code': 'not_active', 'message': 'Only an active period can be cancelled.'})
    row.status, row.cancelled_by, row.cancel_reason, row.version = 'cancelled', user.id, req.reason, row.version + 1
    db.flush()
    return row


def list_vehicle_periods(db, user, date_from: date, date_to: date, vehicle_id: int | None) -> list[VehicleAvailability]:
    require_office_permission(db, user, 'maintenance.manage')
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=user.ktel_id).scalar())
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    query = db.query(VehicleAvailability).filter(VehicleAvailability.tenant_id == user.ktel_id, VehicleAvailability.status.in_(('active', 'released')),
                                                 VehicleAvailability.start_utc < end, or_(VehicleAvailability.end_utc.is_(None), VehicleAvailability.end_utc > start))
    if vehicle_id is not None:
        query = query.filter(VehicleAvailability.vehicle_id == vehicle_id)
    return query.order_by(VehicleAvailability.start_utc, VehicleAvailability.id).limit(500).all()
