"""A driver's own published duties, read only. Drafts, other crews and office notes never appear."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from db.models import KTEL
from app.domain.identity.driver_models import DriverAcknowledgment
from app.domain.scheduling.models import Publication, RevisionAssignment, ScheduleRevision
from app.domain.scheduling.snapshots import RevisionSnapshot

PAST_DAYS, FUTURE_DAYS = 1, 14


def current_publications(db, tenant_id: int, first: date, last: date) -> dict[str, tuple]:
    """Newest operational publication per service date: {date: (Publication, ScheduleRevision, RevisionSnapshot)}."""
    rows = (db.query(Publication, ScheduleRevision, RevisionSnapshot)
            .join(ScheduleRevision, (ScheduleRevision.tenant_id == Publication.tenant_id) & (ScheduleRevision.revision_id == Publication.revision_id))
            .join(RevisionSnapshot, (RevisionSnapshot.tenant_id == Publication.tenant_id) & (RevisionSnapshot.revision_id == Publication.revision_id))
            .filter(Publication.tenant_id == tenant_id, RevisionSnapshot.source_data['source'].as_string() == 'operational',
                    RevisionSnapshot.problem_data['service_date'].as_string().between(first.isoformat(), last.isoformat()))
            .order_by(Publication.published_at.desc(), Publication.id.desc()).all())
    newest: dict[str, tuple] = {}
    for publication, revision, snapshot in rows:
        newest.setdefault(snapshot.problem_data['service_date'], (publication, revision, snapshot))
    return newest


def _withdrawn_crews(db, tenant_id: int, revision, trip_ids: set[str], driver_id: int) -> dict[str, str]:
    """For trips cancelled in this revision: the vehicle label of the driver's crew, only where the nearest earlier PUBLISHED version still had the trip with this driver.
    Unpublished drafts never count, and a trip already taken off the driver in a published version gives no notice. Bounded walk, a few queries per day."""
    lineage, current = [], revision
    for _ in range(20):
        if not current.parent_revision_id:
            break
        current = db.query(ScheduleRevision).filter_by(tenant_id=tenant_id, revision_id=current.parent_revision_id).first()
        if current is None:
            break
        lineage.append(current.revision_id)
    published = {rid for (rid,) in db.query(Publication.revision_id).filter(Publication.tenant_id == tenant_id, Publication.revision_id.in_(lineage)).all()} if lineage else set()
    ordered = [rid for rid in lineage if rid in published]
    rows = {}
    if ordered:
        for row in db.query(RevisionAssignment).filter(RevisionAssignment.tenant_id == tenant_id, RevisionAssignment.revision_id.in_(ordered), RevisionAssignment.trip_id.in_(trip_ids)).all():
            rows[(row.revision_id, row.trip_id)] = row
    snapshots, result = {}, {}
    for trip_id in trip_ids:
        for rid in ordered:
            row = rows.get((rid, trip_id))
            if row is None:
                continue  # not part of that version at all; look further back
            if rid not in snapshots:
                snapshots[rid] = db.query(RevisionSnapshot).filter_by(tenant_id=tenant_id, revision_id=rid).first()
            snapshot = snapshots[rid]
            crews = {item['resource_id'] for item in snapshot.problem_data['resources'] if str(item['driver_id']) == str(driver_id)}
            if row.resource_id in crews:
                result[trip_id] = next((item.get('vehicle_label') for item in snapshot.source_data['resources'] if item['resource_id'] == row.resource_id), '') or ''
            break  # the nearest published version that had the trip decides
    return result


def driver_duties(db, tenant_id: int, driver_id: int, today: date | None = None) -> dict:
    zone_name = db.query(KTEL.timezone).filter_by(id=tenant_id).scalar()
    zone = ZoneInfo(zone_name)
    today = today or datetime.now(zone).date()
    found = current_publications(db, tenant_id, today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS))
    acknowledged = {(row.publication_id, row.trip_id) for row in db.query(DriverAcknowledgment).filter_by(tenant_id=tenant_id, driver_id=driver_id)
                    .filter(DriverAcknowledgment.publication_id.in_([item[0].publication_id for item in found.values()] or [''])).all()}  # only the publications shown, so the lookup never grows with history
    days = []
    for service_date in sorted(found):
        publication, revision, snapshot = found[service_date]
        crews = {item['resource_id'] for item in snapshot.problem_data['resources'] if str(item['driver_id']) == str(driver_id)}
        if not crews:
            continue
        origin = datetime.fromisoformat(snapshot.source_data['service_day_start_utc'])
        trips = {item['id']: item for item in snapshot.source_data['trips']}
        vehicles = {item['resource_id']: item.get('vehicle_label') for item in snapshot.source_data['resources']}
        rows = (db.query(RevisionAssignment).filter_by(tenant_id=tenant_id, revision_id=revision.revision_id)
                .filter(RevisionAssignment.resource_id.in_(crews)).all())
        # A cancelled trip loses its crew in the successor; the driver who had it still needs to see the cancellation.
        withdrawn = db.query(RevisionAssignment).filter_by(tenant_id=tenant_id, revision_id=revision.revision_id, resource_id='UNASSIGNED', is_cancelled=True).all()
        before = _withdrawn_crews(db, tenant_id, revision, {row.trip_id for row in withdrawn}, driver_id) if withdrawn else {}
        rows += [row for row in withdrawn if row.trip_id in before]
        duties = []
        for row in sorted(rows, key=lambda item: (item.start_minutes, item.trip_id)):
            trip = trips.get(row.trip_id, {})
            start, end = origin + timedelta(minutes=row.start_minutes), origin + timedelta(minutes=row.end_minutes)
            duties.append({'trip_id': row.trip_id, 'trip_code': trip.get('trip_code'), 'start_local': start.astimezone(zone).isoformat(), 'end_local': end.astimezone(zone).isoformat(),
                           'start_utc': start.astimezone(timezone.utc).isoformat(), 'end_utc': end.astimezone(timezone.utc).isoformat(),
                           'origin': trip.get('origin'), 'destination': trip.get('destination'), 'vehicle_label': vehicles.get(row.resource_id) if row.resource_id != 'UNASSIGNED' else before.get(row.trip_id),
                           'cancelled': bool(row.is_cancelled), 'acknowledged': (publication.publication_id, row.trip_id) in acknowledged})
        if duties:
            days.append({'service_date': service_date, 'publication_id': publication.publication_id, 'revision_id': revision.revision_id, 'revision_version': revision.version, 'duties': duties})
    return {'timezone': zone_name, 'days': days}
