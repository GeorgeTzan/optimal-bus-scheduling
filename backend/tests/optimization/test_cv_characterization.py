import json
from pathlib import Path
from datetime import date
from unittest.mock import patch

from app.domain.optimization.contracts import (
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    SolverConfig,
)
from app.domain.optimization.cv_legacy import CVLegacyV0


def test_cv_warm_start_calls_constructive_heuristic():
    trips = tuple(
        TripSnapshot(
            id=f"T{i}",
            start_station="A" if i % 2 == 0 else "B",
            end_station="B" if i % 2 == 0 else "A",
            start_minutes=300 + i * 30,
            end_minutes=325 + i * 30,
            duration_minutes=25,
        )
        for i in range(1, 7)
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
        problem_id="p-warm",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=trips,
        resources=resources,
        chains=(),
        stations=("A", "B"),
        transfer_matrix=((0, 5), (5, 0)),
    )
    solver = CVLegacyV0()
    config = SolverConfig(seed=123, time_limit_seconds=10, cp_sat_workers=1, iterations=1)

    # Verify that GreedySASolver is called during the first iteration (warm start)
    with patch("framework.cv_solver.GreedySASolver") as mock_greedy_cls:
        mock_greedy_inst = mock_greedy_cls.return_value
        # When called, pass through to actual execution or verify instantiation
        mock_greedy_inst.solve.side_effect = lambda p: None
        try:
            solver.solve(problem, config)
        except Exception:
            pass
        mock_greedy_cls.assert_called_with(use_sa=False)


def test_legacy_cv_properties_on_fixture():
    # Look for canonical data.json (root or backend)
    candidate_paths = [Path("../data.json"), Path("data.json")]
    data_path = None
    for p in candidate_paths:
        if p.exists() and p.stat().st_size > 0:
            data_path = p
            break

    assert data_path is not None, "Non-empty data.json fixture must be present for characterization"

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Take a representative slice of 20 trips and 8 resources for bounded characterization
    raw_trips = data.get("trips", [])[:20]
    raw_resources = data.get("resources", [])[:8]

    trips = tuple(
        TripSnapshot(
            id=t["id"],
            start_station=t.get("startStation", "A"),
            end_station=t.get("endStation", "B"),
            start_minutes=t.get("start_minutes", 0),
            end_minutes=t.get("end_minutes", 0),
            duration_minutes=t.get("time", {}).get("durationMinutes", 0),
            day_offset=t.get("dayOffset", 0),
            allowed_bus_types=tuple(t.get("classification", {}).get("allowedBusTypes", ["01"])),
        )
        for t in raw_trips
    )

    resources = tuple(
        ResourceSnapshot(
            resource_id=r.get("busId", f"R{i}"),
            driver_id=r.get("driverId", f"D{i}"),
            bus_id=r.get("busId", f"B{i}"),
            home_station=r.get("homeStation", "A"),
            bus_type=r.get("busAttributes", {}).get("type", "01"),
        )
        for i, r in enumerate(raw_resources)
    )

    matrix = data.get("stationTransferMatrix", {}).get("matrix", [])
    matrix_tuple = tuple(tuple(row) for row in matrix)

    problem = SolverProblem(
        problem_id="p-characterization",
        tenant_id="tenant-pilot",
        service_date=date(2026, 11, 1),
        trips=trips,
        resources=resources,
        chains=(),
        transfer_matrix=matrix_tuple,
    )

    solver = CVLegacyV0()
    config = SolverConfig(seed=42, time_limit_seconds=15, cp_sat_workers=1, iterations=1)
    result = solver.solve(problem, config)

    # Characterization invariants
    assert result.solver_id == "cv-solver"
    assert result.solver_version == "cv-legacy-v0"
    assert result.status == "completed"
    assert result.solve_time_seconds > 0.0

    # All 20 trips accounted for
    all_assigned = {a.trip_id for a in result.assignments}
    all_unassigned = set(result.unassigned_trip_ids)
    assert all_assigned | all_unassigned == {t.id for t in trips}
    assert all_assigned.isdisjoint(all_unassigned)

    # Diagnostics recorded
    assert result.diagnostics["assigned_drivers_count"] > 0
    assert result.diagnostics["iterations_requested"] == 1
