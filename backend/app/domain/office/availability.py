"""Driver availability: dated periods and the usable-window calculation shared by readiness, snapshots and recovery."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import or_
from db.models import KTEL
from app.domain.identity.models import Membership
from app.domain.office.intervals import Interval, normalize_office_interval, subtract
from app.domain.office.models import DriverWorkingPattern, LeaveRequest
from app.domain.fleet.models import VehicleAvailability
from app.domain.timetables.time_service import LocalTimeResolutionError
from app.domain.workforce.models import DriverAvailability, WorkforceDriver


@dataclass(frozen=True)
class ResourceAvailability:
    windows: tuple[Interval, ...] | None  # None = unknown, () = known empty
    blockers: tuple[dict, ...]
    warnings: tuple[dict, ...]
    findings: tuple[dict, ...]
    fingerprint: str


def require_drivers(db, tenant_id: int, ids) -> dict[int, WorkforceDriver]:
    rows = {row.id: row for row in db.query(WorkforceDriver).filter(WorkforceDriver.tenant_id == tenant_id, WorkforceDriver.id.in_(list(ids)))}
    if set(ids) - set(rows):
        raise HTTPException(404, 'Driver not found')
    return rows


def resolve_interval(item, zone: str):
    try:
        return normalize_office_interval(item.start_local, item.end_local, zone, item.fold_start, item.fold_end)
    except LocalTimeResolutionError as error:
        raise HTTPException(422, {'code': error.code, 'issues': error.issues, 'message': str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, {'code': 'invalid_interval', 'message': str(error)}) from error


def refuse_own_absence(db, user, row) -> None:
    """The member an absence concerns cannot change or retire it; the link is the explicit driver link, never a name match."""
    if row.kind == 'unavailable' and db.query(Membership.driver_id).filter_by(tenant_id=user.ktel_id, id=user.membership_id).scalar() == row.driver_id:
        raise HTTPException(403, {'code': 'own_absence', 'message': 'You cannot change or retire your own absence.'})


def save_periods(db, user, items) -> list[DriverAvailability]:
    """Create or update dated periods. All items succeed or the caller's transaction rolls back."""
    tenant_id, actor_id = user.ktel_id, user.id
    drivers = require_drivers(db, tenant_id, {item.driver_id for item in items})
    zone = db.query(KTEL.timezone).filter_by(id=tenant_id).scalar()
    rows = []
    for item in items:
        if item.status == 'active' and not drivers[item.driver_id].is_active:
            raise HTTPException(409, {'code': 'driver_archived', 'message': 'This driver is archived.'})
        start, end = resolve_interval(item, zone)
        values = dict(kind=item.kind, start_utc=start, end_utc=end, status=item.status, category=item.category)
        if item.period_id is None:
            row = DriverAvailability(tenant_id=tenant_id, driver_id=item.driver_id, recorded_by=actor_id, **values)
            db.add(row)
        else:
            row = db.query(DriverAvailability).filter_by(tenant_id=tenant_id, id=item.period_id).populate_existing().with_for_update().first()
            if row is None:
                raise HTTPException(404, 'Period not found')
            if row.source_leave_id is not None:
                raise HTTPException(409, {'code': 'linked_to_leave', 'message': 'Change this absence by cancelling the leave request.'})
            refuse_own_absence(db, user, row)
            if row.driver_id != item.driver_id:
                raise HTTPException(422, 'A period cannot move to another driver.')
            if row.version != item.expected_version:
                raise HTTPException(409, {'code': 'version_conflict', 'message': 'This period changed. Refresh before editing.'})
            for name, value in values.items():
                setattr(row, name, value)
            row.recorded_by, row.recorded_at, row.version = actor_id, datetime.now(timezone.utc), row.version + 1
        rows.append(row)
    db.flush()
    return rows


def retire_period(db, user, period_id: int, expected_version: int) -> DriverAvailability:
    row = db.query(DriverAvailability).filter_by(tenant_id=user.ktel_id, id=period_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Period not found')
    if row.source_leave_id is not None:
        raise HTTPException(409, {'code': 'linked_to_leave', 'message': 'Change this absence by cancelling the leave request.'})
    refuse_own_absence(db, user, row)
    if row.version != expected_version or row.status != 'active':
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This period changed. Refresh before editing.'})
    row.status, row.recorded_by, row.recorded_at, row.version = 'retired', user.id, datetime.now(timezone.utc), row.version + 1
    db.flush()
    return row


def list_periods(db, tenant_id: int, date_from: date, date_to: date, driver_id: int | None) -> list[DriverAvailability]:
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=tenant_id).scalar())
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    query = db.query(DriverAvailability).filter(DriverAvailability.tenant_id == tenant_id, DriverAvailability.status == 'active',
                                                DriverAvailability.start_utc < end, or_(DriverAvailability.end_utc.is_(None), DriverAvailability.end_utc > start))
    if driver_id is not None:
        query = query.filter(DriverAvailability.driver_id == driver_id)
    return query.order_by(DriverAvailability.start_utc, DriverAvailability.id).limit(500).all()


def availability_for_resources(db, tenant_id: int, identities, start_utc: datetime, end_utc: datetime) -> dict:
    """identities: (driver_id, vehicle_id) pairs. Missing driver working time is unknown, never available. Crew usable = driver windows minus vehicle blockers."""
    zone_name = db.query(KTEL.timezone).filter_by(id=tenant_id).scalar()
    zone = ZoneInfo(zone_name)

    def local(moment):
        return moment.astimezone(zone).date()

    first, last = local(start_utc), local(end_utc - timedelta(microseconds=1))
    drivers = {driver for driver, _ in identities if driver is not None}
    patterns = db.query(DriverWorkingPattern).filter(
        DriverWorkingPattern.tenant_id == tenant_id, DriverWorkingPattern.driver_id.in_(drivers), DriverWorkingPattern.status == 'active',
        DriverWorkingPattern.valid_from <= last, DriverWorkingPattern.valid_until >= first - timedelta(days=1)).all() if drivers else []
    fetch_from = datetime.combine(first - timedelta(days=1), time.min, tzinfo=zone)
    fetch_to = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)  # a dated window starting later that day still replaces the pattern
    periods = db.query(DriverAvailability).filter(
        DriverAvailability.tenant_id == tenant_id, DriverAvailability.driver_id.in_(drivers), DriverAvailability.status == 'active',
        DriverAvailability.start_utc < fetch_to, or_(DriverAvailability.end_utc.is_(None), DriverAvailability.end_utc > fetch_from)).all() if drivers else []

    pending = db.query(LeaveRequest).filter(LeaveRequest.tenant_id == tenant_id, LeaveRequest.driver_id.in_(drivers), LeaveRequest.state == 'pending',
                                            LeaveRequest.start_utc < end_utc, LeaveRequest.end_utc > start_utc).all() if drivers else []

    def for_driver(driver_id):
        rows = [row for row in periods if row.driver_id == driver_id]
        mine = [row for row in patterns if row.driver_id == driver_id]
        dated = [row for row in rows if row.kind == 'available']
        dated_days = {local(row.start_utc) for row in dated}
        base: list[Interval] = [(row.start_utc, row.end_utc) for row in dated]
        known, unresolved, findings = set(dated_days), set(), []
        day = first - timedelta(days=1)
        while day <= last:
            for pattern in () if day in dated_days else mine:
                if not pattern.valid_from <= day <= pattern.valid_until:
                    continue
                known.add(day)
                if not (pattern.weekday_mask >> day.weekday()) & 1 or (day < first and not pattern.ends_next_day):
                    continue
                finish = day + timedelta(days=1) if pattern.ends_next_day else day
                try:
                    start, end = normalize_office_interval(datetime.combine(day, pattern.local_start), datetime.combine(finish, pattern.local_end), zone_name, None, None)
                    base.append((start, end))
                except LocalTimeResolutionError as error:
                    unresolved.add(day)
                    findings.append({'code': 'working_window_needs_resolution', 'date': day.isoformat(), 'pattern_id': pattern.id, 'message': str(error)})
            day += timedelta(days=1)
        if first - timedelta(days=1) in unresolved:
            unresolved.add(first)
        blocking = [row for row in rows if row.kind == 'unavailable' and row.start_utc < end_utc and (row.end_utc is None or row.end_utc > start_utc)]
        blockers = [(row.start_utc, row.end_utc or end_utc) for row in blocking]
        clipped = [(max(start, start_utc), min(end, end_utc)) for start, end in base if start < end_utc and end > start_utc]
        unknown = [d.isoformat() for d in (first + timedelta(days=n) for n in range((last - first).days + 1)) if d not in known or d in unresolved]
        if not subtract([(start_utc, end_utc)], blockers):
            windows = ()
        elif unknown:
            windows = None
            findings.append({'code': 'working_time_unknown', 'dates': unknown})
        else:
            windows = tuple(subtract(clipped, blockers))
        source = sorted([('pattern', row.id, row.version) for row in mine] + [('period', row.id, row.version) for row in rows])
        return ResourceAvailability(windows, tuple({'period_id': row.id, 'start_utc': row.start_utc.isoformat(), 'end_utc': row.end_utc.isoformat() if row.end_utc else None} for row in blocking),
                                    tuple({'leave_id': row.id, 'start_utc': row.start_utc.isoformat(), 'end_utc': row.end_utc.isoformat()} for row in pending if row.driver_id == driver_id),
                                    tuple(findings), hashlib.sha256(json.dumps([zone_name, source]).encode()).hexdigest())

    cache = {driver: for_driver(driver) for driver in drivers}
    vehicles = {vehicle for _, vehicle in identities if vehicle is not None}
    vehicle_rows = db.query(VehicleAvailability).filter(
        VehicleAvailability.tenant_id == tenant_id, VehicleAvailability.vehicle_id.in_(vehicles), VehicleAvailability.status.in_(('active', 'released')),
        VehicleAvailability.start_utc < end_utc, or_(VehicleAvailability.end_utc.is_(None), VehicleAvailability.end_utc > start_utc)).all() if vehicles else []

    def combine(driver_id, vehicle_id):
        base = cache.get(driver_id)
        rows = [row for row in vehicle_rows if row.vehicle_id == vehicle_id]
        blocks = [(row.start_utc, row.end_utc or end_utc) for row in rows]
        if blocks and not subtract([(start_utc, end_utc)], blocks):
            windows = ()
        elif base is None:
            windows = tuple(subtract([(start_utc, end_utc)], blocks))
        else:
            windows = None if base.windows is None else tuple(subtract(list(base.windows), blocks))
        source = sorted(('vehicle_period', row.id, row.version, row.status) for row in rows)
        return ResourceAvailability(
            windows, (base.blockers if base else ()) + tuple({'vehicle_period_id': row.id, 'start_utc': row.start_utc.isoformat(), 'end_utc': row.end_utc.isoformat() if row.end_utc else None} for row in rows),
            base.warnings if base else (), base.findings if base else (),
            hashlib.sha256(json.dumps([base.fingerprint if base else None, source]).encode()).hexdigest())

    return {identity: combine(*identity) for identity in identities if identity[0] is not None or identity[1] is not None}
