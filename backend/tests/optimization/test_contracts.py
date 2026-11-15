import pytest
import json
from datetime import date
from app.domain.optimization.contracts import (
    SolverConfig,
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    ChainSnapshot,
    Assignment,
    SolverResult,
    SchedulingSolver,
    ProgressSink,
)


def test_solver_config_immutability():
    config = SolverConfig(seed=42, time_limit_seconds=30, cp_sat_workers=2, iterations=3)
    assert config.seed == 42
    assert config.time_limit_seconds == 30
    assert config.cp_sat_workers == 2
    assert config.iterations == 3
    with pytest.raises(Exception):
        config.seed = 99  # type: ignore


def test_solver_problem_and_snapshots():
    trip = TripSnapshot(
        id="T1",
        start_station="ATHENS",
        end_station="PATRAS",
        start_minutes=480,
        end_minutes=660,
        duration_minutes=180,
        day_offset=0,
        allowed_bus_types=("01",),
    )
    resource = ResourceSnapshot(
        resource_id="R1",
        driver_id="D1",
        bus_id="B1",
        home_station="ATHENS",
        bus_type="01",
    )
    chain = ChainSnapshot(trip_ids=("T1",))

    problem = SolverProblem(
        problem_id="prob-1",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(trip,),
        resources=(resource,),
        chains=(chain,),
        stations=("ATHENS", "PATRAS"),
        transfer_matrix=((0, 15), (15, 0)),
    )

    assert problem.problem_id == "prob-1"
    assert len(problem.trips) == 1
    assert len(problem.resources) == 1
    assert problem.trips[0].id == "T1"

    with pytest.raises(Exception):
        problem.problem_id = "modified"  # type: ignore


def test_solver_result_and_assignment():
    assignment = Assignment(
        resource_id="R1",
        trip_id="T1",
        start_minutes=480,
        end_minutes=660,
        start_station="ATHENS",
        end_station="PATRAS",
    )
    result = SolverResult(
        solver_id="cv-solver",
        solver_version="1.0.0",
        assignments=(assignment,),
        unassigned_trip_ids=(),
        metrics={"totalDrivingTime": 180},
        solve_time_seconds=1.25,
        status="completed",
    )
    assert result.solver_id == "cv-solver"
    assert len(result.assignments) == 1
    assert result.assignments[0].trip_id == "T1"
    assert result.unassigned_trip_ids == ()


BUDGET = {
    "driver_id": "D1", "earliest_start_minutes": 600, "latest_end_minutes": 2880, "max_work_minutes": 540,
    "max_long_route_driving_minutes": 480, "continuous_driving_minutes": 270, "overnight_allowed": True,
    "split_shift_allowed": False, "must_return_to_base": True, "forbidden_route_ids": [3], "preferred_route_ids": [4],
    "forbidden_vehicle_route_ids": {"B1": [5]},
}


def test_old_snapshot_with_parameters_decodes():
    from app.domain.scheduling.snapshots import decode_problem
    stored = {
        "problem_id": "old", "tenant_id": "1", "service_date": "2026-06-01",
        "trips": [{"id": "T1", "start_station": "A", "end_station": "B", "start_minutes": 480, "end_minutes": 540,
                   "duration_minutes": 60, "day_offset": 0, "group": "000", "allowed_bus_types": ["01"]}],
        "resources": [{"resource_id": "R1", "driver_id": "D1", "bus_id": "B1", "home_station": "A", "bus_type": "01"}],
        "chains": [], "stations": ["A", "B"], "transfer_matrix": [[0, 30], [30, 0]],
        "parameters": {"max_driving_time": 900, "max_continuous_driving": 270, "min_break_time": 30,
                       "min_rest_time": 720, "max_duty_duration": 600},
    }
    problem = decode_problem(stored)
    assert not hasattr(problem, "parameters")
    assert problem.work_policy is None and problem.driver_budgets == ()
    [trip] = problem.trips
    assert (trip.route_id, trip.urban, trip.long_route, trip.origin_is_depot, trip.destination_is_depot) == (None, False, True, False, False)


def test_problem_round_trip_with_budgets():
    from app.domain.scheduling.snapshots import decode_problem, encode_problem
    from app.domain.workrules.policy import build_policy
    trip = TripSnapshot("T1", "A", "B", 480, 540, 60, route_id=7, urban=True, long_route=False, origin_is_depot=True)
    problem = SolverProblem("P", "1", date(2026, 6, 1), (trip,), (ResourceSnapshot("R1", "D1", "B1", "A"),), (),
                            ("A", "B"), ((0, 30), (30, 0)), work_policy=build_policy({}, [], 3).to_dict(), driver_budgets=(BUDGET,))
    decoded = decode_problem(json.loads(json.dumps(encode_problem(problem))))
    assert decoded == problem
    assert decoded.trips[0].route_id == 7 and decoded.trips[0].urban and not decoded.trips[0].long_route


def test_registry_single_allowlist():
    from app.domain.optimization import registry
    assert registry.ALLOWED_PRODUCTION_SOLVERS == frozenset({"cv-legacy-v0", "cv-bounded-v1"})
    assert isinstance(registry.ALLOWED_PRODUCTION_SOLVERS, frozenset)
    assert registry.ALLOWED_PRODUCTION_SOLVERS == frozenset(registry._PRODUCTION_SOLVERS)
    assert registry.list_available_solvers() == ["cv-bounded-v1", "cv-legacy-v0"]
    assert not hasattr(registry, "register_solver")
    assert all(not cls.__module__.startswith("framework") for cls in registry._PRODUCTION_SOLVERS.values())
