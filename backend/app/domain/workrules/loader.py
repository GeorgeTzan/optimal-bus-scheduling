from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Mapping

from sqlalchemy import func

from app.domain.incidents.operations import Operations
from app.domain.incidents.operations_models import OperationalEvent, OperationalTripState
from app.domain.optimization.contracts import SolverProblem
from app.domain.scheduling.change_models import ScheduleChange
from app.domain.scheduling.driver_duties import current_publications
from app.domain.scheduling.models import Publication, RevisionAssignment, ScheduleRevision
from app.domain.scheduling.snapshots import RevisionSnapshot
from app.domain.timetables.display_clock import frozen_clock
from app.domain.timetables.models import Route, ServiceTemplate, Station
from app.domain.workforce.models import WorkforceDriver
from app.domain.workrules import service
from app.domain.workrules.budget import driver_budget
from app.domain.workrules.draft import touched_drivers
from app.domain.workrules.facts import DutyFacts, duty_parts
from app.domain.workrules.models import DriverRouteRule, DriverWorkBaseline, DriverWorkProfile, VehicleRouteRule, WorkRuleOverride
from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import Baseline, DriverProfile, DriverTimeline, Duty, DutyTrip
from db.models import KTEL

HISTORY_DAYS = 28
FUTURE_DAYS = 7
ANCESTOR_LIMIT = 20
DEFAULT_TZ = "Europe/Athens"
_cache: dict = {}
_cache_lock = threading.Lock()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class WorkContext:
    policy: WorkRulePolicy
    timelines: Mapping[str, DriverTimeline]
    overrides: frozenset[str]
    service_date: date
    day_origin_utc: datetime
    transfers: Mapping[tuple[str, str], int]
    tz: str = DEFAULT_TZ
    trip_routes: Mapping[str, tuple[int | None, bool, bool] | tuple[int | None, bool, bool, int]] = field(default_factory=dict)
    depots: frozenset[str] = frozenset()
    emergency_drivers: frozenset[str] = frozenset()
    delays: Mapping[str, int] = field(default_factory=dict)

    def transfer_minutes(self, origin: str, destination: str) -> int | None:
        return self.transfers.get((origin, destination))

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.to_dict(),
            "timelines": {k: v.to_dict() for k, v in sorted(self.timelines.items())},
            "overrides": sorted(self.overrides),
            "service_date": self.service_date.isoformat(),
            "day_origin_utc": self.day_origin_utc.isoformat(),
            "transfers": [[a, b, m] for (a, b), m in sorted(self.transfers.items())],
            "tz": self.tz,
            "trip_routes": {k: list(v) for k, v in sorted(self.trip_routes.items())},
            "depots": sorted(self.depots),
            "emergency_drivers": sorted(self.emergency_drivers),
            "delays": dict(sorted(self.delays.items())),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkContext:
        return cls(
            policy=WorkRulePolicy.from_dict(data["policy"]),
            timelines={k: DriverTimeline.from_dict(v) for k, v in data["timelines"].items()},
            overrides=frozenset(data["overrides"]),
            service_date=date.fromisoformat(data["service_date"]),
            day_origin_utc=datetime.fromisoformat(data["day_origin_utc"]),
            transfers={(a, b): m for a, b, m in data["transfers"]},
            tz=data["tz"],
            trip_routes={k: tuple(v) for k, v in data["trip_routes"].items()},
            depots=frozenset(data["depots"]),
            emergency_drivers=frozenset(data["emergency_drivers"]),
            delays=dict(data["delays"]),
        )


def _window(day: date) -> date:
    return min(day - timedelta(days=HISTORY_DAYS), date(day.year, 1, 1))


def _tz(db, tenant_id: int) -> str:
    return db.query(KTEL.timezone).filter_by(id=tenant_id).scalar() or DEFAULT_TZ


def _log(db, tenant_id: int, model, *conditions) -> tuple:
    return tuple(db.query(func.count(model.id), func.max(model.id)).filter(model.tenant_id == tenant_id, *conditions).one())


def _publications(db, tenant_id: int) -> tuple:
    return (
        *_log(db, tenant_id, Publication),
        db.query(func.max(Publication.publication_id)).filter(Publication.tenant_id == tenant_id).scalar(),
    )


def _cached(key, compute):
    slot = key[:2]
    with _cache_lock:
        held = _cache.get(slot)
    if held is not None and held[0] == key:
        return held[1]
    value = compute()
    with _cache_lock:
        _cache[slot] = (key, value)
    return value


def _earliest_published(db, tenant_id: int) -> str | None:
    day = func.min(RevisionSnapshot.problem_data["service_date"].as_string())
    return (
        db.query(day)
        .join(Publication, (Publication.tenant_id == RevisionSnapshot.tenant_id) & (Publication.revision_id == RevisionSnapshot.revision_id))
        .filter(RevisionSnapshot.tenant_id == tenant_id, RevisionSnapshot.source_data["source"].as_string() == "operational")
        .scalar()
    )


def _known_from(db, tenant_id: int, fallback: date) -> date:
    key = ("known_from", tenant_id, _publications(db, tenant_id))
    earliest = _cached(key, lambda: _earliest_published(db, tenant_id))
    return min(date.fromisoformat(earliest), fallback) if earliest else fallback


def _delays(db, tenant_id: int, found, rows) -> dict[tuple[str, str], int]:
    latest: dict[tuple[str, str], tuple[int, int]] = {}

    def note(key: tuple[str, str], event_id: int, minutes: int) -> None:
        if key not in latest or latest[key][0] < event_id:
            latest[key] = (event_id, minutes)

    for publication_id, trip_id, event_id, minutes in (
        db.query(OperationalTripState.publication_id, OperationalTripState.trip_id, OperationalEvent.id, OperationalEvent.delay_minutes)
        .join(OperationalEvent, (OperationalEvent.tenant_id == OperationalTripState.tenant_id) & (OperationalEvent.state_id == OperationalTripState.id))
        .filter(
            OperationalTripState.tenant_id == tenant_id,
            OperationalTripState.publication_id.in_([publication.publication_id for publication, _, _ in found]),
            OperationalEvent.kind == "delay",
        )
    ):
        note((publication_id, trip_id), event_id, minutes)
    successors = [entry for entry in found if entry[1].parent_revision_id]
    if successors:
        service_day = RevisionSnapshot.problem_data["service_date"].as_string()
        history = defaultdict(list)
        for publication, day in (
            db.query(Publication, service_day)
            .join(RevisionSnapshot, (RevisionSnapshot.tenant_id == Publication.tenant_id) & (RevisionSnapshot.revision_id == Publication.revision_id))
            .filter(
                Publication.tenant_id == tenant_id,
                RevisionSnapshot.source_data["source"].as_string() == "operational",
                service_day.in_({snapshot.problem_data["service_date"] for _, _, snapshot in successors}),
            )
        ):
            history[day].append(publication)
        operations = Operations(db, SimpleNamespace(ktel_id=tenant_id))
        for publication, revision, snapshot in successors:
            linked, _ = operations.linked_history(publication, rows[revision.revision_id], history[snapshot.problem_data["service_date"]])
            for trip_id, events in linked.items():
                for event in events:
                    if event["kind"] == "delay":
                        note((publication.publication_id, trip_id), event["id"], event["delay_minutes"])
    return {key: minutes for key, (_, minutes) in latest.items()}


def template_routes(db, tenant_id: int, templates: set) -> dict[Any, tuple[int, str, int]]:
    templates = templates - {None}
    return {
        template_id: (route_id, service_type, en_route_break)
        for template_id, route_id, service_type, en_route_break in db.query(ServiceTemplate.id, Route.id, Route.service_type, Route.en_route_break_minutes)
        .join(Route, (Route.tenant_id == ServiceTemplate.tenant_id) & (Route.id == ServiceTemplate.route_id))
        .filter(ServiceTemplate.tenant_id == tenant_id, ServiceTemplate.id.in_(templates))
    } if templates else {}


def route_facts(route: tuple[int, str, int] | None, distance_km: float | None, limit: int) -> tuple[int | None, bool, bool, int]:
    return (route[0] if route else None, route is not None and route[1] == "urban", distance_km is None or distance_km > limit, route[2] if route else 0)


def _depots(db, tenant_id: int, codes: set[str]) -> dict[str, bool]:
    return {
        code: bool(is_depot)
        for code, is_depot in db.query(Station.code, Station.is_depot).filter(Station.tenant_id == tenant_id, Station.code.in_(codes))
    } if codes else {}


def _draft_trips(db, tenant_id: int, policy: WorkRulePolicy, problem: SolverProblem, revision_id: str | None):
    source = db.query(RevisionSnapshot.source_data).filter_by(tenant_id=tenant_id, revision_id=revision_id).scalar() if revision_id else None
    labels = {t["id"]: t for t in (source or {}).get("trips", [])}
    routes = template_routes(db, tenant_id, {label.get("template_id") for label in labels.values()})
    limit = policy.value("eu_route_km")
    trip_routes = {}
    for trip in problem.trips:
        label = labels.get(trip.id, {})
        trip_routes[trip.id] = route_facts(routes.get(label.get("template_id")), label.get("distance_km"), limit)
    codes = set(problem.stations) | {code for trip in problem.trips for code in (trip.start_station, trip.end_station)}
    depots = frozenset(code for code, is_depot in _depots(db, tenant_id, codes).items() if is_depot)
    return trip_routes, depots


def _emergency(db, tenant_id: int, revision_id: str | None, problem: SolverProblem) -> frozenset[str]:
    if not revision_id:
        return frozenset()
    changes = db.query(ScheduleChange.changes).filter_by(tenant_id=tenant_id, successor_revision_id=revision_id, emergency=True).scalar()
    return touched_drivers(changes or (), {r.resource_id: str(r.driver_id) for r in problem.resources})


def _draft_delays(db, tenant_id: int, problem: SolverProblem) -> dict[str, int]:
    entry = current_publications(db, tenant_id, problem.service_date, problem.service_date).get(problem.service_date.isoformat())
    if entry is None:
        return {}
    publication, revision, _ = entry
    rows = db.query(RevisionAssignment).filter(
        RevisionAssignment.tenant_id == tenant_id,
        RevisionAssignment.revision_id == revision.revision_id,
        RevisionAssignment.is_cancelled.is_(False),
    ).all()
    delays = _delays(db, tenant_id, [entry], {revision.revision_id: rows})
    trips = {t.id: (t.start_minutes, t.end_minutes, t.start_station, t.end_station) for t in problem.trips}
    return {
        row.trip_id: delays[(publication.publication_id, row.trip_id)]
        for row in rows
        if (publication.publication_id, row.trip_id) in delays
        and trips.get(row.trip_id) == (row.start_minutes, row.end_minutes, row.start_station, row.end_station)
    }


def _with_prior(timelines, duties, policy: WorkRulePolicy, transfer_minutes, year: int):
    out = {}
    for driver_id, timeline in timelines.items():
        normal = emergency = 0
        baseline = timeline.baseline
        for duty, facts in duty_parts(duties.get(driver_id, ()), timeline.profile, policy, transfer_minutes):
            if duty.service_date.year != year or (baseline and duty.service_date <= baseline.as_of):
                continue
            minutes = facts.overtime_minutes
            if duty.emergency:
                emergency += minutes
            else:
                normal += minutes
        out[driver_id] = replace(timeline, prior_year=year, prior_overtime=normal, prior_emergency_overtime=emergency)
    return out


def _published(db, tenant_id: int, policy: WorkRulePolicy, drivers: set[str], first: date, last: date, skip: date | None):
    found = [entry for day, entry in sorted(current_publications(db, tenant_id, first, last).items()) if skip is None or day != skip.isoformat()]
    transfers: dict[tuple[str, str], int] = {}
    duties: dict[str, list[Duty]] = defaultdict(list)
    if not found:
        return duties, transfers
    revisions = [revision.revision_id for _, revision, _ in found]
    rows = defaultdict(list)
    for row in db.query(RevisionAssignment).filter(
        RevisionAssignment.tenant_id == tenant_id,
        RevisionAssignment.revision_id.in_(revisions),
        RevisionAssignment.is_cancelled.is_(False),
    ).all():
        rows[row.revision_id].append(row)
    delays = _delays(db, tenant_id, found, rows)
    emergency = {
        revision_id: changes
        for revision_id, changes in db.query(ScheduleChange.successor_revision_id, ScheduleChange.changes).filter(
            ScheduleChange.tenant_id == tenant_id,
            ScheduleChange.successor_revision_id.in_(revisions),
            ScheduleChange.emergency.is_(True),
        )
    }
    routes = template_routes(db, tenant_id, {trip.get("template_id") for _, _, snapshot in found for trip in snapshot.source_data.get("trips", [])})
    depots = _depots(db, tenant_id, {code for group in rows.values() for row in group for code in (row.start_station, row.end_station)})
    limit = policy.value("eu_route_km")
    for publication, revision, snapshot in found:
        source = snapshot.source_data
        for item in source.get("transfers", []):
            transfers[(item["origin_station_code"], item["destination_station_code"])] = item["minutes"]
        crews = {r["resource_id"]: r for r in snapshot.problem_data["resources"] if str(r["driver_id"]) in drivers}
        if not crews:
            continue
        origin = _utc(datetime.fromisoformat(source["service_day_start_utc"]))
        labels = {t["id"]: t for t in source.get("trips", [])}
        planned = defaultdict(list)
        for row in rows[revision.revision_id]:
            crew = crews.get(row.resource_id)
            if crew is not None:
                planned[str(crew["driver_id"])].append((row, crew))
        trips = defaultdict(list)
        for driver_id, group in planned.items():
            group.sort(key=lambda pair: (pair[0].start_minutes, pair[0].trip_id))
            previous = None
            for row, crew in group:
                label = labels.get(row.trip_id, {})
                route_id, urban, long_route, en_route_break = route_facts(routes.get(label.get("template_id")), label.get("distance_km"), limit)
                start = origin + timedelta(minutes=row.start_minutes)
                if previous is not None:
                    start = max(start, previous)
                end = start + timedelta(minutes=row.end_minutes - row.start_minutes + delays.get((publication.publication_id, row.trip_id), 0))
                previous = end
                trips[driver_id].append(
                    DutyTrip(
                        trip_id=row.trip_id,
                        start=start,
                        end=end,
                        origin=row.start_station,
                        destination=row.end_station,
                        origin_is_depot=depots.get(row.start_station, False),
                        destination_is_depot=depots.get(row.end_station, False),
                        vehicle_id=str(crew["bus_id"]),
                        route_id=route_id,
                        urban=urban,
                        long_route=long_route,
                        en_route_break_minutes=en_route_break,
                    )
                )
        day = date.fromisoformat(snapshot.problem_data["service_date"])
        touched = touched_drivers(emergency.get(revision.revision_id, ()), {r["resource_id"]: str(r["driver_id"]) for r in snapshot.problem_data["resources"]})
        for driver_id, items in trips.items():
            duties[driver_id].append(Duty(driver_id, day, tuple(items), "published", driver_id in touched))
    return duties, transfers


def _timelines(db, tenant_id: int, policy: WorkRulePolicy, homes: Mapping[str, str], first: date, last: date, skip: date | None, fallback: date):
    duties, transfers = _published(db, tenant_id, policy, set(homes), first, last, skip)
    ids = [int(d) for d in homes if d.isdigit()]
    profiles = {str(r.driver_id): r for r in db.query(DriverWorkProfile).filter(DriverWorkProfile.tenant_id == tenant_id, DriverWorkProfile.driver_id.in_(ids))} if ids else {}
    baselines = {str(r.driver_id): r for r in db.query(DriverWorkBaseline).filter(DriverWorkBaseline.tenant_id == tenant_id, DriverWorkBaseline.driver_id.in_(ids))} if ids else {}
    preferred, forbidden = defaultdict(set), defaultdict(set)
    for rule in db.query(DriverRouteRule).filter(DriverRouteRule.tenant_id == tenant_id, DriverRouteRule.driver_id.in_(ids)) if ids else ():
        (preferred if rule.kind == "prefer" else forbidden)[str(rule.driver_id)].add(rule.route_id)
    vehicles = defaultdict(set)
    for rule in db.query(VehicleRouteRule).filter(VehicleRouteRule.tenant_id == tenant_id):
        vehicles[str(rule.vehicle_id)].add(rule.route_id)
    vehicle_routes = {k: frozenset(v) for k, v in vehicles.items()}
    known = _known_from(db, tenant_id, fallback)
    timelines = {}
    for driver_id, home in homes.items():
        row = profiles.get(driver_id)
        base = baselines.get(driver_id)
        baseline = None if base is None else Baseline(
            as_of=base.as_of,
            overtime_minutes=base.overtime_minutes,
            last_duty_end=_utc(base.last_duty_end),
            last_weekly_rest_end=_utc(base.last_weekly_rest_end),
            last_weekly_rest_at_base=base.last_weekly_rest_at_base,
            owed_rest_minutes=base.owed_rest_minutes,
        )
        timelines[driver_id] = DriverTimeline(
            driver_id=driver_id,
            profile=DriverProfile(
                home_station=home,
                overnight_allowed=row.overnight_allowed if row else True,
                split_shift_allowed=row.split_shift_allowed if row else True,
                must_return_to_base=row.must_return_to_base if row else False,
                forbidden_routes=frozenset(forbidden[driver_id]),
                preferred_routes=frozenset(preferred[driver_id]),
            ),
            duties=tuple(sorted(duties.get(driver_id, ()), key=lambda d: d.service_date)),
            baseline=baseline,
            known_from=base.as_of + timedelta(days=1) if base else known,
            forbidden_vehicle_routes=vehicle_routes,
        )
    return timelines, transfers


def _overrides(db, tenant_id: int, revision_id: str | None) -> frozenset[str]:
    lineage: list[str] = []
    current = revision_id
    while current and current not in lineage and len(lineage) < ANCESTOR_LIMIT:
        lineage.append(current)
        current = db.query(ScheduleRevision.parent_revision_id).filter_by(tenant_id=tenant_id, revision_id=current).scalar()
    if not lineage:
        return frozenset()
    return frozenset(
        key for (key,) in db.query(WorkRuleOverride.finding_key).filter(
            WorkRuleOverride.tenant_id == tenant_id, WorkRuleOverride.revision_id.in_(lineage)
        )
    )


def _prior_fingerprint(db, tenant_id: int) -> tuple:
    return (
        _publications(db, tenant_id),
        _log(db, tenant_id, OperationalEvent, OperationalEvent.kind == "delay"),
        _log(db, tenant_id, ScheduleChange, ScheduleChange.emergency.is_(True)),
        tuple(sorted(db.query(Station.code, Station.is_depot).filter(Station.tenant_id == tenant_id).all())),
        tuple(
            sorted(
                db.query(ServiceTemplate.id, Route.id, Route.service_type, Route.en_route_break_minutes)
                .join(Route, (Route.tenant_id == ServiceTemplate.tenant_id) & (Route.id == ServiceTemplate.route_id))
                .filter(ServiceTemplate.tenant_id == tenant_id)
                .all()
            )
        ),
    )


def _prior_published(db, tenant_id: int, policy: WorkRulePolicy, drivers: set[str], first: date, last: date):
    key = ("prior", tenant_id, first, last, frozenset(drivers), policy.value("eu_route_km"), _prior_fingerprint(db, tenant_id))
    return _cached(key, lambda: _published(db, tenant_id, policy, drivers, first, last, None))


def load_work_context(db, tenant_id: int, problem: SolverProblem, revision_id: str | None) -> WorkContext:
    day = problem.service_date
    tz = _tz(db, tenant_id)
    policy = service.company_policy(db, tenant_id)
    homes: dict[str, str] = {}
    for resource in problem.resources:
        homes.setdefault(str(resource.driver_id), resource.home_station)
    window = day - timedelta(days=HISTORY_DAYS)
    timelines, transfers = _timelines(db, tenant_id, policy, homes, window, day + timedelta(days=FUTURE_DAYS), day, day)
    year_start = date(day.year, 1, 1)
    prior, prior_transfers = _prior_published(db, tenant_id, policy, set(homes), year_start, window - timedelta(days=1)) if year_start < window else ({}, {})
    transfers = {**prior_transfers, **transfers}
    for i, origin in enumerate(problem.stations):
        for j, destination in enumerate(problem.stations):
            if i < len(problem.transfer_matrix) and j < len(problem.transfer_matrix[i]):
                transfers[(origin, destination)] = problem.transfer_matrix[i][j]
    trip_routes, depots = _draft_trips(db, tenant_id, policy, problem, revision_id)
    return WorkContext(
        policy=policy,
        timelines=_with_prior(timelines, prior, policy, lambda a, b: transfers.get((a, b)), day.year),
        overrides=_overrides(db, tenant_id, revision_id),
        service_date=day,
        day_origin_utc=_utc(datetime.fromisoformat(frozen_clock(day, tz)["service_day_start_utc"])),
        transfers=transfers,
        tz=tz,
        trip_routes=trip_routes,
        depots=depots,
        emergency_drivers=_emergency(db, tenant_id, revision_id, problem),
        delays=_draft_delays(db, tenant_id, problem),
    )


def attach_work_context(problem: SolverProblem, ctx: WorkContext) -> SolverProblem:
    drivers = dict.fromkeys(str(r.driver_id) for r in problem.resources)
    budgets = [
        driver_budget(ctx.timelines[d], ctx.policy, ctx.service_date, ctx.day_origin_utc, ctx.transfer_minutes)
        for d in drivers
        if d in ctx.timelines
    ]
    return replace(problem, work_policy=ctx.policy.to_dict(), driver_budgets=tuple(b.to_dict() for b in budgets))


def published_duty_facts(db, tenant_id: int, first: date, last: date) -> tuple[dict[str, DriverTimeline], dict[str, list[tuple[Duty, DutyFacts]]]]:
    policy = service.company_policy(db, tenant_id)
    codes = dict(db.query(Station.id, Station.code).filter(Station.tenant_id == tenant_id))
    homes = {str(row.id): codes.get(row.home_station_id) or "" for row in db.query(WorkforceDriver).filter(WorkforceDriver.tenant_id == tenant_id)}
    timelines, transfers = _timelines(db, tenant_id, policy, homes, first, last, None, first)
    facts = {key: duty_parts(timeline.duties, timeline.profile, policy, lambda a, b: transfers.get((a, b))) for key, timeline in timelines.items()}
    return timelines, facts


def driver_week(db, tenant_id: int, driver_id: int, day: date) -> dict[str, Any]:
    row = service.driver(db, tenant_id, driver_id)
    home = db.query(Station.code).filter_by(tenant_id=tenant_id, id=row.home_station_id).scalar() if row.home_station_id else None
    policy = service.company_policy(db, tenant_id)
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    key = str(driver_id)
    timelines, transfers = _timelines(db, tenant_id, policy, {key: home or ""}, _window(monday), sunday, None, day)
    timeline = timelines[key]
    baseline = timeline.baseline
    facts = sorted(
        duty_parts(timeline.duties, timeline.profile, policy, lambda a, b: transfers.get((a, b))),
        key=lambda pair: pair[1].start,
    )
    overtime = baseline.overtime_minutes if baseline and baseline.as_of.year == day.year else 0
    overtime += sum(
        f.overtime_minutes
        for d, f in facts
        if d.service_date.year == day.year and d.service_date <= sunday and not d.emergency and not (baseline and d.service_date <= baseline.as_of)
    )
    past = [f for d, f in facts if d.service_date <= day]
    last_end = past[-1].end if past else baseline.last_duty_end if baseline else None
    weekly = policy.value("weekly_rest")
    rest = baseline.last_weekly_rest_end if baseline else None
    previous = baseline.last_duty_end if baseline else None
    for d, f in facts:
        if d.service_date > day or (baseline and d.service_date <= baseline.as_of):
            continue
        if previous is not None and (f.start - previous).total_seconds() // 60 >= weekly:
            rest = f.start if rest is None else max(rest, f.start)
        previous = f.end
    return {
        "work_minutes": sum(f.work_minutes for d, f in facts if monday <= d.service_date <= sunday),
        "weekly_max": policy.value("weekly_work_max"),
        "overtime_year_minutes": overtime,
        "overtime_year_max": policy.value("overtime_year"),
        "last_duty_end": None if last_end is None else last_end.isoformat(),
        "last_weekly_rest": None if rest is None else rest.isoformat(),
    }
