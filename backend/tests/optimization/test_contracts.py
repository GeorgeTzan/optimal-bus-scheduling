import pytest
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
