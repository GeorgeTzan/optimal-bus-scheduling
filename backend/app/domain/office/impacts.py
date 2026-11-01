"""Derived, read-only view of work that current driver or vehicle availability puts at risk. Nothing here is stored or retired."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from db.models import KTEL
from app.domain.incidents.operations_models import OperationalEvent, OperationalTripState
from app.domain.office.availability import availability_for_resources
from app.domain.optimization.availability import availability_allows_trip, transfer_conflicts
from app.domain.optimization.contracts import ResourceSnapshot
from app.domain.scheduling.availability_review import frozen_horizon
from app.domain.scheduling.models import Publication, RevisionAssignment, ScheduleRevision
from app.domain.scheduling.snapshots import RevisionSnapshot, decode_problem

OPEN = ("draft", "approval_requested", "approved")


def operated_trip_ids(db, tenant_id: int, revision) -> set[str]:
    """Trips with a recorded departure or completion on this revision or its ancestors. A clock never establishes this."""
    lineage, seen, current = [], set(), revision
    while current is not None and current.revision_id not in seen and len(seen) < 1000:
        seen.add(current.revision_id)
        lineage.append(current.revision_id)
        current = db.query(ScheduleRevision).filter_by(tenant_id=tenant_id, revision_id=current.parent_revision_id).first() if current.parent_revision_id else None
    rows = (db.query(OperationalTripState.trip_id).join(OperationalEvent, (OperationalEvent.tenant_id == OperationalTripState.tenant_id) & (OperationalEvent.state_id == OperationalTripState.id))
            .filter(OperationalTripState.tenant_id == tenant_id, OperationalTripState.revision_id.in_(lineage), OperationalEvent.kind.in_(("departure", "completion"))).all())
    return {trip for (trip,) in rows}


def _crew(resource_id, driver, vehicle, windows):
    return ResourceSnapshot(resource_id, str(driver), str(vehicle), "", available_windows=windows)


def list_office_impacts(db, tenant_id: int, *, date_from: date, date_to: date, page: int, page_size: int) -> dict:
    snapshots = (db.query(RevisionSnapshot, ScheduleRevision).join(ScheduleRevision, (ScheduleRevision.tenant_id == RevisionSnapshot.tenant_id) & (ScheduleRevision.revision_id == RevisionSnapshot.revision_id))
                 .filter(RevisionSnapshot.tenant_id == tenant_id, RevisionSnapshot.source_data["source"].as_string() == "operational",
                         RevisionSnapshot.problem_data["service_date"].as_string().between(date_from.isoformat(), date_to.isoformat()))
                 .order_by(ScheduleRevision.created_at.desc()).limit(500).all())
    latest = {}  # service date -> (publication time, revision id)
    for snapshot, revision in snapshots:
        publication = db.query(Publication).filter_by(tenant_id=tenant_id, revision_id=revision.revision_id).order_by(Publication.published_at.desc()).first()
        if publication is not None:
            day = snapshot.problem_data["service_date"]
            if day not in latest or publication.published_at > latest[day][0]:
                latest[day] = (publication.published_at, revision.revision_id)
    rows = []
    for snapshot, revision in snapshots:
        day = snapshot.problem_data["service_date"]
        current_publication = latest.get(day)
        if revision.status == "published":
            if current_publication is None or current_publication[1] != revision.revision_id:
                continue
        elif revision.status not in OPEN or (current_publication is not None and revision.created_at <= current_publication[0]):
            continue
        problem = decode_problem(snapshot.problem_data)
        origin, end = frozen_horizon(snapshot.source_data, problem)
        drivers = {int(resource.driver_id) for resource in problem.resources}
        vehicles = {int(resource.bus_id) for resource in problem.resources}
        by_driver = availability_for_resources(db, tenant_id, [(driver, None) for driver in drivers], origin, end)
        by_vehicle = availability_for_resources(db, tenant_id, [(None, vehicle) for vehicle in vehicles], origin, end)
        minutes = lambda moment: int((moment - origin).total_seconds() // 60)
        windows = lambda found: None if found.windows is None else tuple((minutes(a), minutes(b)) for a, b in found.windows)
        trips = {trip.id: trip for trip in problem.trips}
        labels = {item["id"]: item.get("trip_code") for item in snapshot.source_data.get("trips", [])}
        resources = {resource.resource_id: resource for resource in problem.resources}
        operated = operated_trip_ids(db, tenant_id, revision)
        assignments = db.query(RevisionAssignment).filter_by(tenant_id=tenant_id, revision_id=revision.revision_id, is_cancelled=False).all()
        travel_blocked: dict[tuple[str, str], set[str]] = {}  # (kind, resource) -> trips whose connecting travel falls outside usable time
        for resource_id, resource in resources.items():
            mine = [trips[a.trip_id] for a in assignments if a.resource_id == resource_id and a.trip_id in trips]
            for kind, found in (("driver", windows(by_driver[(int(resource.driver_id), None)])), ("vehicle", windows(by_vehicle[(None, int(resource.bus_id))]))):
                if found is not None:
                    travel_blocked[(kind, resource_id)] = transfer_conflicts(_crew(resource_id, resource.driver_id, resource.bus_id, found), mine, problem.stations, problem.transfer_matrix)
        for assignment in assignments:
            resource, trip = resources.get(assignment.resource_id), trips.get(assignment.trip_id)
            if resource is None or trip is None:
                continue
            driver_windows = windows(by_driver[(int(resource.driver_id), None)])
            driver_unknown = driver_windows is None  # unknown working time blocks any repair, so it is work to review
            driver_blocked = driver_unknown or not availability_allows_trip(_crew(resource.resource_id, resource.driver_id, resource.bus_id, driver_windows), trip) or trip.id in travel_blocked.get(("driver", resource.resource_id), ())
            vehicle_windows = windows(by_vehicle[(None, int(resource.bus_id))])
            vehicle_blocked = vehicle_windows is not None and (not availability_allows_trip(_crew(resource.resource_id, resource.driver_id, resource.bus_id, vehicle_windows), trip) or trip.id in travel_blocked.get(("vehicle", resource.resource_id), ()))
            if driver_blocked or vehicle_blocked:
                start = origin + timedelta(minutes=trip.start_minutes)
                rows.append({"service_date": day, "status": revision.status, "revision_id": revision.revision_id, "resource_id": resource.resource_id,
                             "trip_id": trip.id, "trip_code": labels.get(trip.id), "driver_id": int(resource.driver_id), "vehicle_id": int(resource.bus_id),
                             "start_utc": start.astimezone(timezone.utc).isoformat(), "end_utc": (origin + timedelta(minutes=trip.end_minutes)).astimezone(timezone.utc).isoformat(),
                             "cause": "both" if driver_blocked and vehicle_blocked else "unknown" if driver_unknown else "driver" if driver_blocked else "vehicle", "operated": trip.id in operated})
    rows.sort(key=lambda row: (row["service_date"], row["start_utc"], row["trip_id"], row["revision_id"]))
    return {"items": rows[(page - 1) * page_size: page * page_size], "total": len(rows), "needs_review": len({(row["service_date"], row["trip_id"]) for row in rows if not row["operated"]}), "page": page, "page_size": page_size}


def impact_count(db, tenant_id: int, start_utc: datetime, end_utc: datetime | None) -> int:
    """How many trips need review for an absence or hold; the span is clipped to 31 days from its start."""
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=tenant_id).scalar())
    first = start_utc.astimezone(zone).date() - timedelta(days=1)  # an overnight trip can start the day before the absence
    last = min((end_utc - timedelta(microseconds=1)).astimezone(zone).date() if end_utc else first + timedelta(days=30), first + timedelta(days=30))
    return list_office_impacts(db, tenant_id, date_from=first, date_to=max(first, last), page=1, page_size=1)["needs_review"]


def impact_count_for_dates(db, tenant_id: int, first: date, last: date) -> int:
    """Trips needing review in the next 31 days that fall inside a date range, for example a retired working pattern."""
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=tenant_id).scalar())
    today = datetime.now(zone).date()
    first, last = max(first, today - timedelta(days=1)), min(last, today + timedelta(days=30))
    return list_office_impacts(db, tenant_id, date_from=first, date_to=last, page=1, page_size=1)["needs_review"] if first <= last else 0
