from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, or_

from app.domain.fleet.models import VehicleAvailability
from app.domain.reports.overtime import _month_end
from app.domain.scheduling.driver_duties import current_publications
from app.domain.scheduling.models import RevisionAssignment
from app.domain.timetables.models import Route, Station
from app.domain.workforce.models import DriverAvailability
from app.domain.workrules.loader import template_routes
from db.models import User

NO_LINE = "none"
UNASSIGNED = "UNASSIGNED"


def _route_ends(db, tenant_id: int, route_ids: set[int]) -> dict[int, tuple[str, str]]:
    if not route_ids:
        return {}
    routes = db.query(Route.id, Route.origin_station_id, Route.destination_station_id).filter(Route.tenant_id == tenant_id, Route.id.in_(route_ids)).all()
    codes = dict(db.query(Station.id, Station.code).filter(Station.tenant_id == tenant_id, Station.id.in_({station for _, *ends in routes for station in ends})).all())
    return {route_id: (codes[origin], codes[destination]) for route_id, origin, destination in routes if origin in codes and destination in codes}


def _state(row) -> str:
    return "cancelled" if row.is_cancelled else "uncovered" if row.resource_id == UNASSIGNED else "covered"


def month_trips(db, tenant_id: int, month: date, found: dict | None = None) -> list[dict]:
    if found is None:
        found = current_publications(db, tenant_id, month, _month_end(month))
    first, last = month.isoformat(), _month_end(month).isoformat()
    found = {day: entry for day, entry in found.items() if first <= day <= last}
    routes = template_routes(db, tenant_id, {trip.get("template_id") for _, _, snapshot in found.values() for trip in snapshot.source_data.get("trips", [])})
    ends = _route_ends(db, tenant_id, {route[0] for route in routes.values()})
    assignments = defaultdict(list)
    if found:
        for row in db.query(RevisionAssignment).filter(RevisionAssignment.tenant_id == tenant_id, RevisionAssignment.revision_id.in_([revision.revision_id for _, revision, _ in found.values()])):
            assignments[row.revision_id].append(row)
    result = []
    for service_date in sorted(found):
        publication, revision, snapshot = found[service_date]
        labels = {trip["id"]: trip for trip in snapshot.source_data.get("trips", [])}
        for row in sorted(assignments[revision.revision_id], key=lambda item: (item.start_minutes, item.trip_id)):
            label = labels.get(row.trip_id)
            if label is None and row.is_cancelled and row.resource_id == UNASSIGNED:
                continue
            route = routes.get((label or {}).get("template_id"))
            pair = ends.get(route[0]) if route else None
            result.append({
                "date": service_date,
                "publication": publication,
                "snapshot": snapshot,
                "line": "-".join(sorted(pair)) if pair else NO_LINE,
                "stations": sorted(pair) if pair else [],
                "direction": "→".join(pair or (row.start_station, row.end_station)),
                "trip_code": (label or {}).get("trip_code") or row.trip_id,
                "state": _state(row),
                "reason": row.cancellation_reason,
            })
    return result


def coverage_report(db, tenant_id: int, month: date, trips: list[dict] | None = None) -> list[dict]:
    lines: dict[str, dict] = {}
    for trip in month_trips(db, tenant_id, month) if trips is None else trips:
        line = lines.setdefault(trip["line"], {"line": trip["line"], "stations": trip["stations"], "covered": 0, "uncovered": 0, "cancelled": 0, "reasons": defaultdict(int)})
        line[trip["state"]] += 1
        if trip["state"] == "uncovered":
            line["reasons"][trip["publication"].uncovered_reason or "unrecorded"] += 1
    codes = {code for line in lines.values() for code in line["stations"]}
    names = {
        code: [name_el, name_en]
        for code, name_el, name_en in db.query(Station.code, Station.name_el, Station.name_en).filter(Station.tenant_id == tenant_id, Station.code.in_(codes))
    } if codes else {}
    report = []
    for key in sorted(lines):
        line = lines[key]
        attempted = line["covered"] + line["uncovered"]
        report.append({
            "line": key,
            "stations": line["stations"],
            "names": [names[code] for code in line["stations"]],
            "scheduled": attempted + line["cancelled"],
            "covered": line["covered"],
            "uncovered": line["uncovered"],
            "cancelled": line["cancelled"],
            "rate": line["covered"] / attempted if attempted else None,
            "reasons": dict(line["reasons"]),
        })
    report.sort(key=lambda row: row["uncovered"] + row["cancelled"], reverse=True)
    return report


def _context(db, tenant_id: int, snapshot) -> dict[str, int]:
    start = datetime.fromisoformat(snapshot.source_data["service_day_start_utc"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=24)
    drivers = db.query(func.count(func.distinct(DriverAvailability.driver_id))).filter(
        DriverAvailability.tenant_id == tenant_id, DriverAvailability.kind == "unavailable", DriverAvailability.status == "active",
        DriverAvailability.start_utc < end, or_(DriverAvailability.end_utc.is_(None), DriverAvailability.end_utc > start)).scalar()
    vehicles = db.query(func.count(func.distinct(VehicleAvailability.vehicle_id))).filter(
        VehicleAvailability.tenant_id == tenant_id, VehicleAvailability.kind.in_(("planned_maintenance", "out_of_service")),
        or_(VehicleAvailability.status == "active", and_(VehicleAvailability.status == "released", VehicleAvailability.released_at > start)),
        VehicleAvailability.start_utc < end, or_(VehicleAvailability.end_utc.is_(None), VehicleAvailability.end_utc > start)).scalar()
    return {"drivers_unavailable": drivers, "vehicles_out": vehicles}


def line_days(db, tenant_id: int, month: date, line: str, trips: list[dict] | None = None, contexts: dict[str, dict[str, int]] | None = None) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for trip in month_trips(db, tenant_id, month) if trips is None else trips:
        if trip["line"] != line or trip["state"] == "covered":
            continue
        group = groups.setdefault((trip["date"], trip["direction"]), {"publication": trip["publication"], "snapshot": trip["snapshot"], "uncovered": [], "cancelled": []})
        if trip["state"] == "uncovered":
            group["uncovered"].append(trip["trip_code"])
        else:
            group["cancelled"].append({"trip_code": trip["trip_code"], "reason": trip["reason"]})
    publishers = {group["publication"].published_by for group in groups.values()}
    users = {
        str(user_id): full_name or email
        for user_id, full_name, email in db.query(User.id, User.full_name, User.email).filter(User.ktel_id == tenant_id, User.id.in_([int(p) for p in publishers if p.isdigit()]))
    } if publishers else {}
    if contexts is None:
        contexts = {}
    days = []
    for (service_date, direction), group in sorted(groups.items()):
        publication = group["publication"]
        context = None
        if publication.uncovered_reason is None and group["uncovered"]:
            if service_date not in contexts:
                contexts[service_date] = _context(db, tenant_id, group["snapshot"])
            context = contexts[service_date]
        days.append({
            "date": service_date,
            "direction": direction,
            "uncovered": group["uncovered"],
            "cancelled": group["cancelled"],
            "reason": publication.uncovered_reason,
            "note": publication.uncovered_note,
            "published_by": users.get(publication.published_by, publication.published_by),
            "context": context,
        })
    return days
