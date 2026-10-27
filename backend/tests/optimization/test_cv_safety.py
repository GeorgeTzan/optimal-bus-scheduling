from datetime import date
import pytest
from app.domain.optimization.contracts import (
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    SolverConfig,
)
from app.domain.optimization.cv_legacy import (
    CVLegacyV0,
    InvalidSolverInput,
    validate_cv_input,
)


def test_empty_resources_rejected_preflight():
    t1 = TripSnapshot(
        id="T1",
        start_station="A",
        end_station="B",
        start_minutes=100,
        end_minutes=200,
        duration_minutes=100,
    )
    problem = SolverProblem(
        problem_id="prob-empty-res",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(t1,),
        resources=(),  # empty resources!
        chains=(),
    )
    with pytest.raises(InvalidSolverInput, match="resources cannot be empty"):
        validate_cv_input(problem)


def test_fewer_than_six_resources_rejected_preflight():
    t1 = TripSnapshot(
        id="T1",
        start_station="A",
        end_station="B",
        start_minutes=100,
        end_minutes=200,
        duration_minutes=100,
    )
    r1 = ResourceSnapshot(
        resource_id="R1",
        driver_id="D1",
        bus_id="B1",
        home_station="A",
    )
    problem = SolverProblem(
        problem_id="prob-few-res",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(t1,),
        resources=(r1,),  # only 1 resource!
        chains=(),
    )
    with pytest.raises(InvalidSolverInput, match="at least 6 resources"):
        validate_cv_input(problem)


def test_zero_or_duplicate_trip_ids_rejected():
    resources = tuple(
        ResourceSnapshot(
            resource_id=f"R{i}",
            driver_id=f"D{i}",
            bus_id=f"B{i}",
            home_station="A",
        )
        for i in range(1, 7)
    )
    # Zero trips
    problem_zero = SolverProblem(
        problem_id="prob-zero-trips",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(),  # empty trips!
        resources=resources,
        chains=(),
    )
    with pytest.raises(InvalidSolverInput, match="trips cannot be empty"):
        validate_cv_input(problem_zero)

    # Duplicate trip IDs
    t1 = TripSnapshot(
        id="T1",
        start_station="A",
        end_station="B",
        start_minutes=100,
        end_minutes=200,
        duration_minutes=100,
    )
    t1_dup = TripSnapshot(
        id="T1",  # duplicate ID!
        start_station="B",
        end_station="C",
        start_minutes=250,
        end_minutes=350,
        duration_minutes=100,
    )
    problem_dup = SolverProblem(
        problem_id="prob-dup-trips",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(t1, t1_dup),
        resources=resources,
        chains=(),
    )
    with pytest.raises(InvalidSolverInput, match="duplicate trip"):
        validate_cv_input(problem_dup)


def test_result_partitions_assigned_unassigned():
    # Construct a problem with 3 trips and 6 resources
    t1 = TripSnapshot(
        id="T1",
        start_station="A",
        end_station="B",
        start_minutes=60,
        end_minutes=120,
        duration_minutes=60,
    )
    t2 = TripSnapshot(
        id="T2",
        start_station="B",
        end_station="A",
        start_minutes=150,
        end_minutes=210,
        duration_minutes=60,
    )
    t3 = TripSnapshot(
        id="T3",
        start_station="A",
        end_station="B",
        start_minutes=80,  # overlaps with T1!
        end_minutes=140,
        duration_minutes=60,
    )
    resources = tuple(
        ResourceSnapshot(
            resource_id=f"R{i}",
            driver_id=f"D{i}",
            bus_id=f"B{i}",
            home_station="A",
        )
        for i in range(1, 7)
    )
    problem = SolverProblem(
        problem_id="p-part",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(t1, t2, t3),
        resources=resources,
        chains=(),
        stations=("A", "B"),
        transfer_matrix=((0, 10), (10, 0)),
    )
    solver = CVLegacyV0()
    config = SolverConfig(seed=42, time_limit_seconds=10, cp_sat_workers=1, iterations=1)
    result = solver.solve(problem, config)

    all_problem_trips = {"T1", "T2", "T3"}
    assigned_trips = {a.trip_id for a in result.assignments}
    unassigned_trips = set(result.unassigned_trip_ids)

    # Intersection must be empty (no trip both assigned and unassigned)
    assert assigned_trips.isdisjoint(unassigned_trips)
    # Union must equal all problem trips (no lost trips)
    assert assigned_trips | unassigned_trips == all_problem_trips
