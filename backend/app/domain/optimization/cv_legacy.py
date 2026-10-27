"""
CV Legacy V0 Wrapper.
Maintains Christos Valouxis's original CV matheuristic as a tagged, immutable baseline (cv-legacy-v0).
Enforces input preflight validation and clean type conversion.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List

from app.domain.optimization.contracts import (
    SolverProblem,
    SolverConfig,
    SolverResult,
    Assignment,
    ProgressSink,
    SchedulingSolver,
)
from framework.problem import Problem
from framework.cv_solver import CustomSolver


class InvalidSolverInput(ValueError):
    """Raised when problem input is degenerate, empty, or structurally invalid."""
    pass


def validate_cv_input(problem: SolverProblem, *, minimum_resources: int = 6) -> None:
    """Preflight validation to prevent worker hangs or crashes on degenerate input."""
    if not problem.trips:
        raise InvalidSolverInput("trips cannot be empty")
    if not problem.resources:
        raise InvalidSolverInput("resources cannot be empty")
    if len(problem.resources) < minimum_resources:
        raise InvalidSolverInput(
            f"resources must contain at least {minimum_resources} resources for CV k-opt neighborhood search (got {len(problem.resources)})"
        )

    if problem.availability_enforced:
        if any(r.available_windows is None for r in problem.resources):
            raise InvalidSolverInput("every resource needs confirmed working time before availability can be enforced")
        if len({r.bus_id for r in problem.resources}) != len(problem.resources):
            raise InvalidSolverInput("availability enforcement requires one pairing per vehicle")

    seen_trip_ids = set()
    for t in problem.trips:
        if t.id in seen_trip_ids:
            raise InvalidSolverInput(f"duplicate trip id found: {t.id}")
        seen_trip_ids.add(t.id)

    seen_resource_ids = set()
    for r in problem.resources:
        if r.resource_id in seen_resource_ids:
            raise InvalidSolverInput(f"duplicate resource id found: {r.resource_id}")
        seen_resource_ids.add(r.resource_id)


def problem_snapshot_to_legacy_dict(problem: SolverProblem) -> Dict[str, Any]:
    """Converts an immutable SolverProblem snapshot into the dict expected by legacy Problem."""
    trips_data = [
        {
            "id": t.id,
            "startStation": t.start_station,
            "endStation": t.end_station,
            "start_minutes": t.start_minutes,
            "end_minutes": t.end_minutes,
            "time": {"durationMinutes": t.duration_minutes},
            "dayOffset": t.day_offset,
            "classification": {
                "group": t.group,
                "allowedBusTypes": list(t.allowed_bus_types),
            },
        }
        for t in problem.trips
    ]

    resources_data = [
        {
            "driverId": r.driver_id,
            "busId": r.bus_id,
            "homeStation": r.home_station,
            "currentStation": r.home_station,
            "busAttributes": {"type": r.bus_type},
            **({"availableWindows": [list(w) for w in r.available_windows]} if r.available_windows is not None else {}),
        }
        for r in problem.resources
    ]

    mandatory_connections = []
    for chain in problem.chains:
        for i in range(len(chain.trip_ids) - 1):
            mandatory_connections.append(
                {
                    "incomingTripId": chain.trip_ids[i],
                    "outgoingTripId": chain.trip_ids[i + 1],
                }
            )

    return {
        "trips": trips_data,
        "resources": resources_data,
        "constraints": {
            "mandatoryConnections": mandatory_connections,
        },
        "configuration": {
            "parameters": {
                "maxDutyMinutes": problem.parameters.max_duty_duration,
                "normalDutyMinutes": 600,
                "maxWorkMinutes": problem.parameters.max_driving_time,
                "driveTimeToBreakMinutes": problem.parameters.max_continuous_driving,
                "minBreakMinutes": problem.parameters.min_break_time,
                "transitMinutes": 30,
            }
        },
        "stationTransferMatrix": {
            "matrix": [list(row) for row in problem.transfer_matrix]
        },
        **({"availability": {"stations": list(problem.stations), "transfer": [list(row) for row in problem.transfer_matrix]}} if problem.availability_enforced else {}),
    }


class CVLegacyV0(SchedulingSolver):
    """
    Adapter for the original Christos Valouxis CV Solver.
    Uses constructive greedy warm-start and k-opt with CP-SAT subproblems.
    """

    @property
    def algorithm_id(self) -> str:
        return "cv-solver"

    @property
    def version(self) -> str:
        return "cv-legacy-v0"

    def solve(
        self,
        problem: SolverProblem,
        config: SolverConfig,
        progress: ProgressSink | None = None,
    ) -> SolverResult:
        if problem.availability_enforced:
            raise InvalidSolverInput("the original reference solver cannot honour availability; use the bounded solver")
        validate_cv_input(problem)

        legacy_dict = problem_snapshot_to_legacy_dict(problem)
        legacy_problem = Problem(legacy_dict)

        solver = CustomSolver()
        start_time = time.time()

        solution = solver.solve(
            legacy_problem,
            iterations=config.iterations,
        )
        elapsed = time.time() - start_time

        trip_map = {t.id: t for t in problem.trips}
        resource_by_bus = {r.bus_id: r for r in problem.resources}

        assignments: List[Assignment] = []
        for da in solution.assignments:
            bus_id = da.bus_id
            res = resource_by_bus.get(bus_id)
            res_id = res.resource_id if res else str(bus_id)

            for tid in da.assigned_trip_ids:
                t = trip_map.get(tid)
                if t:
                    assignments.append(
                        Assignment(
                            resource_id=res_id,
                            trip_id=t.id,
                            start_minutes=t.start_minutes,
                            end_minutes=t.end_minutes,
                            start_station=t.start_station,
                            end_station=t.end_station,
                        )
                    )

        return SolverResult(
            solver_id=self.algorithm_id,
            solver_version=self.version,
            assignments=tuple(assignments),
            unassigned_trip_ids=tuple(solution.unassigned_trips),
            metrics=solution.metrics,
            solve_time_seconds=elapsed,
            status="completed",
            diagnostics={
                "assigned_drivers_count": len(solution.assignments),
                "iterations_requested": config.iterations,
            },
        )
