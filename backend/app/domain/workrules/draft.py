from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from app.domain.optimization.contracts import Assignment, SolverProblem
from app.domain.workrules.timeline import Duty, DutyTrip

if TYPE_CHECKING:
    from app.domain.workrules.loader import WorkContext

UNKNOWN_ROUTE = (None, False, True)


def touched_drivers(changes: Iterable[Mapping[str, Any]], drivers: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        drivers[resource]
        for item in changes
        for resource in (item.get("original_resource_id"), item.get("new_resource_id"))
        if resource in drivers
    )


def draft_duties(work: WorkContext, problem: SolverProblem, assignments: Iterable[Assignment]) -> dict[str, Duty]:
    resources = {r.resource_id: r for r in problem.resources}
    trips = {t.id: t for t in problem.trips}
    grouped = defaultdict(list)
    for assignment in assignments:
        resource, trip = resources.get(assignment.resource_id), trips.get(assignment.trip_id)
        if resource is not None and trip is not None:
            grouped[str(resource.driver_id)].append((trip, resource))
    duties = {}
    for driver_id, items in grouped.items():
        items.sort(key=lambda pair: (pair[0].start_minutes, pair[0].id))
        built = []
        previous = None
        for trip, resource in items:
            planned = draft_trip(work, trip, str(resource.bus_id))
            start = planned.start if previous is None else max(planned.start, previous)
            end = start + (planned.end - planned.start) + timedelta(minutes=work.delays.get(trip.id, 0))
            previous = end
            built.append(replace(planned, start=start, end=end))
        duties[driver_id] = Duty(driver_id, work.service_date, tuple(built), "draft", driver_id in work.emergency_drivers)
    return duties


def draft_trip(work: WorkContext, trip, vehicle_id: str) -> DutyTrip:
    route_id, urban, long_route = work.trip_routes.get(trip.id, UNKNOWN_ROUTE)
    return DutyTrip(
        trip_id=trip.id,
        start=work.day_origin_utc + timedelta(minutes=trip.start_minutes),
        end=work.day_origin_utc + timedelta(minutes=trip.end_minutes),
        origin=trip.start_station,
        destination=trip.end_station,
        origin_is_depot=trip.start_station in work.depots,
        destination_is_depot=trip.end_station in work.depots,
        vehicle_id=vehicle_id,
        route_id=route_id,
        urban=urban,
        long_route=long_route,
    )
