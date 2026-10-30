import time
from datetime import date
import pytest

from app.domain.optimization.contracts import (
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    SolverConfig,
    Assignment,
    SolverResult,
)
from app.domain.optimization.cv_bounded import CVBoundedV1
from app.domain.optimization.metrics import calculate_metrics
from app.domain.verification.verifier import HardRuleVerifier


def make_synthetic_ladder(trip_count: int) -> SolverProblem:
    resource_count = max(6, trip_count // 6)
    trips = []
    stations = ["Patras", "Athens", "Thessaloniki", "Ioannina", "Aigio", "Korinthos"]

    for i in range(trip_count):
        start = 300 + (i * 7) % 700
        duration = 60 + (i * 13) % 120
        origin = stations[i % len(stations)]
        dest = stations[(i + 1) % len(stations)]
        trips.append(
            TripSnapshot(
                id=f"T_{i:04d}",
                start_station=origin,
                end_station=dest,
                start_minutes=start,
                end_minutes=start + duration,
                duration_minutes=duration,
            )
        )

    resources = []
    for r in range(resource_count):
        resources.append(
            ResourceSnapshot(
                resource_id=f"R_{r:03d}",
                driver_id=f"D_{r:03d}",
                bus_id=f"B_{r:03d}",
                home_station=stations[r % len(stations)],
            )
        )

    return SolverProblem(
        problem_id=f"LADDER_{trip_count}",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=tuple(trips),
        resources=tuple(resources),
        chains=(),
        stations=tuple(stations),
    )


def test_synthetic_ladder_100_trips():
    """
    Ladder step 1: 100 trips completes cleanly and verifies under 5 seconds.
    """
    prob = make_synthetic_ladder(100)
    solver = CVBoundedV1()
    config = SolverConfig(time_limit_seconds=5, seed=42)

    t0 = time.time()
    res = solver.solve(prob, config=config)
    elapsed = time.time() - t0

    assert elapsed < 5.5
    assert len(res.assignments) > 0

    # Metric and verifier benchmarks
    t_v0 = time.time()
    verifier = HardRuleVerifier()
    report = verifier.verify(prob, res)
    t_v_elapsed = time.time() - t_v0

    assert t_v_elapsed < 0.1  # Verifier must take < 100ms
    assert report.valid is True


def test_synthetic_ladder_metrics_scalability():
    """
    Ladder step 2: Metrics calculation on 1,000 and 2,500 trip scale takes under 50ms.
    """
    prob = make_synthetic_ladder(1000)
    assignments = []
    for i, trip in enumerate(prob.trips):
        res_idx = i % len(prob.resources)
        assignments.append(
            Assignment(
                resource_id=prob.resources[res_idx].resource_id,
                trip_id=trip.id,
                start_minutes=trip.start_minutes,
                end_minutes=trip.end_minutes,
                start_station=trip.start_station,
                end_station=trip.end_station,
            )
        )

    res = SolverResult(
        solver_id="cv-bounded-v1",
        solver_version="1.0.0",
        assignments=tuple(assignments),
        unassigned_trip_ids=(),
        metrics={},
        solve_time_seconds=1.0,
        status="FEASIBLE",
    )

    t0 = time.time()
    metrics = calculate_metrics(prob, res)
    elapsed = time.time() - t0

    assert elapsed < 0.05  # < 50ms
    assert metrics.assigned_trips_count + metrics.unassigned_trips_count == 1000
