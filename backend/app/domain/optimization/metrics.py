from dataclasses import dataclass, field
from typing import Optional, Tuple
from app.domain.optimization.contracts import SolverProblem, SolverResult


@dataclass(frozen=True)
class CandidateMetrics:
    total_driving_minutes: int
    total_idle_minutes: int
    total_deadhead_minutes: Optional[int]
    resource_count: int
    assigned_trips_count: int
    unassigned_trips_count: int
    unassigned_trip_ids: Tuple[str, ...]
    fuel_liters_estimate: Optional[float] = None
    deadhead_kilometers: Optional[float] = None


def calculate_metrics(problem: SolverProblem, result: SolverResult) -> CandidateMetrics:
    """
    Computes honest, independent metrics for a solver candidate solution.
    Unmeasured metrics (such as fuel consumption or unmapped deadhead km)
    are returned as None rather than falsely claiming 0.
    """
    # Group assignments by resource
    by_resource = {}
    for a in result.assignments:
        by_resource.setdefault(a.resource_id, []).append(a)

    total_driving = 0
    total_idle = 0

    for res_id, assigns in by_resource.items():
        sorted_assigns = sorted(assigns, key=lambda x: x.start_minutes)
        for i, a in enumerate(sorted_assigns):
            total_driving += (a.end_minutes - a.start_minutes)
            if i > 0:
                prev = sorted_assigns[i - 1]
                gap = a.start_minutes - prev.end_minutes
                if gap > 0:
                    total_idle += gap

    return CandidateMetrics(
        total_driving_minutes=total_driving,
        total_idle_minutes=total_idle,
        total_deadhead_minutes=None,
        resource_count=len(by_resource),
        assigned_trips_count=len(result.assignments),
        unassigned_trips_count=len(result.unassigned_trip_ids),
        unassigned_trip_ids=tuple(result.unassigned_trip_ids),
        fuel_liters_estimate=None,
        deadhead_kilometers=None,
    )
