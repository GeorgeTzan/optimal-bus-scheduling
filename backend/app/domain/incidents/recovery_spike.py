from dataclasses import dataclass, field
from typing import Sequence, Set, Tuple, List, Optional

from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot, Assignment


@dataclass(frozen=True)
class RecoveryProblemInput:
    as_of_minutes: int
    frozen_assignments: Tuple[Assignment, ...]
    locked_assignments: Tuple[Assignment, ...]
    disrupted_trip_ids: Tuple[str, ...]
    orphaned_trip_ids: Tuple[str, ...]
    future_problem: SolverProblem


def split_operated_future(
    assignments: Sequence[Assignment],
    as_of_minutes: int,
) -> Tuple[List[Assignment], List[Assignment]]:
    """
    Partitions assignments into:
    - frozen: trips already started or finished prior to as_of_minutes (immutable operational history).
    - future: trips starting at or after as_of_minutes (candidates for disruption recovery).
    """
    frozen: List[Assignment] = []
    future: List[Assignment] = []

    for a in assignments:
        if a.start_minutes < as_of_minutes:
            frozen.append(a)
        else:
            future.append(a)

    return frozen, future


def build_recovery_input(
    problem: SolverProblem,
    assignments: Sequence[Assignment],
    as_of_minutes: int,
    disabled_resource_ids: Set[str],
    locked_trip_ids: Set[str],
) -> RecoveryProblemInput:
    """
    Constructs an isolated recovery subproblem for disruption response:
    - Permanently preserves operated history (frozen prefix).
    - Preserves locked assignments.
    - Excludes damaged/disabled vehicles and unavailable drivers.
    - Gathers orphaned future trips requiring re-optimization.
    """
    frozen, future = split_operated_future(assignments, as_of_minutes)

    # Detect ongoing trips running during the disruption on broken resources
    disrupted_trip_ids: List[str] = []
    for a in assignments:
        if a.resource_id in disabled_resource_ids:
            if a.start_minutes <= as_of_minutes < a.end_minutes:
                disrupted_trip_ids.append(a.trip_id)

    # Filter resources that are still operational
    active_resources: List[ResourceSnapshot] = [
        r for r in problem.resources if r.resource_id not in disabled_resource_ids
    ]

    # Filter locked assignments in the future
    locked_future: List[Assignment] = []
    for a in future:
        if a.trip_id in locked_trip_ids:
            locked_future.append(a)

    locked_future_trip_ids = {a.trip_id for a in locked_future}

    # Trips that need rescheduling in the future
    problem_trip_map = {t.id: t for t in problem.trips}
    future_trips_to_solve: List[TripSnapshot] = []
    orphaned_trip_ids: List[str] = []

    for a in future:
        if a.trip_id in locked_future_trip_ids:
            continue
        if a.resource_id in disabled_resource_ids:
            # Broken resource in future -> must be rescued
            if a.trip_id in problem_trip_map:
                future_trips_to_solve.append(problem_trip_map[a.trip_id])
        else:
            # Ongoing viable trip
            if a.trip_id in problem_trip_map:
                future_trips_to_solve.append(problem_trip_map[a.trip_id])

    if len(active_resources) == 0:
        # All resources disabled, future trips cannot be recovered
        orphaned_trip_ids = [t.id for t in future_trips_to_solve]
        future_trips_to_solve = []

    future_problem = SolverProblem(
        problem_id=f"{problem.problem_id}_RECOVERY_{as_of_minutes}",
        tenant_id=problem.tenant_id,
        service_date=problem.service_date,
        trips=tuple(future_trips_to_solve),
        resources=tuple(active_resources),
        chains=(),
    )

    return RecoveryProblemInput(
        as_of_minutes=as_of_minutes,
        frozen_assignments=tuple(frozen),
        locked_assignments=tuple(locked_future),
        disrupted_trip_ids=tuple(disrupted_trip_ids),
        orphaned_trip_ids=tuple(orphaned_trip_ids),
        future_problem=future_problem,
    )
