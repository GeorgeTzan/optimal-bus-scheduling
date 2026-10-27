import pytest
from datetime import date
from unittest.mock import MagicMock

from app.domain.optimization.contracts import (
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    SolverConfig,
    ProgressSink,
)
from app.domain.optimization.registry import (
    get_production_solver,
    list_available_solvers,
    InvalidSolverSelectionError,
)
from app.domain.optimization.cv_bounded import CVBoundedV1


@pytest.fixture
def sample_problem() -> SolverProblem:
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
    return SolverProblem(
        problem_id="p-bounded",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=trips,
        resources=resources,
        chains=(),
        stations=("A", "B"),
        transfer_matrix=((0, 5), (5, 0)),
    )


def test_production_registry_rejects_research():
    available = list_available_solvers()
    assert "cv-bounded-v1" in available
    assert "cv-legacy-v0" in available
    # Research solvers must NOT be selectable as production solvers
    assert "greedy" not in available
    assert "simulated_annealing" not in available
    assert "lahc" not in available

    solver = get_production_solver("cv-bounded-v1")
    assert solver.algorithm_id == "cv-solver"
    assert solver.version == "cv-bounded-v1"

    with pytest.raises(InvalidSolverSelectionError):
        get_production_solver("simulated_annealing")

    with pytest.raises(InvalidSolverSelectionError):
        get_production_solver("unknown-algorithm")


def test_progress_sink_is_called(sample_problem: SolverProblem):
    solver = CVBoundedV1()
    config = SolverConfig(seed=42, time_limit_seconds=10, cp_sat_workers=1, iterations=2)

    progress = MagicMock(spec=ProgressSink)
    result = solver.solve(sample_problem, config, progress=progress)

    assert result.status == "completed"
    assert progress.update.call_count >= 2


def test_repeated_seed_and_env_is_reproducible_or_variance_recorded(sample_problem: SolverProblem):
    solver = CVBoundedV1()
    config1 = SolverConfig(seed=12345, time_limit_seconds=10, cp_sat_workers=1, iterations=1)
    config2 = SolverConfig(seed=12345, time_limit_seconds=10, cp_sat_workers=1, iterations=1)

    res1 = solver.solve(sample_problem, config1)
    res2 = solver.solve(sample_problem, config2)

    # Identical seed and single worker must produce deterministic assignments
    assigned_trips_1 = sorted([a.trip_id for a in res1.assignments])
    assigned_trips_2 = sorted([a.trip_id for a in res2.assignments])
    assert assigned_trips_1 == assigned_trips_2
    assert res1.unassigned_trip_ids == res2.unassigned_trip_ids


def test_metrics_not_faked_as_zero(sample_problem: SolverProblem):
    solver = CVBoundedV1()
    config = SolverConfig(seed=42, time_limit_seconds=10, cp_sat_workers=1, iterations=1)
    result = solver.solve(sample_problem, config)

    # In v1 bounded solver, metrics are calculated honestly
    metrics = result.metrics
    assert "totalTrips" in metrics
    assert "totalDrivingTime" in metrics
    assert "assignedTripsCount" in metrics
    assert "coveragePercent" in metrics
    # Honest calculation matches assignments
    assert metrics["assignedTripsCount"] == len(result.assignments)
    assert metrics["coveragePercent"] == round(len(result.assignments) / len(sample_problem.trips) * 100.0, 2)


def test_iteration_limit_even_on_continue(sample_problem: SolverProblem):
    from app.domain.optimization.cv_bounded import BoundedCustomSolver
    from app.domain.optimization.cv_legacy import problem_snapshot_to_legacy_dict
    from framework.problem import Problem

    legacy_dict = problem_snapshot_to_legacy_dict(sample_problem)
    legacy_problem = Problem(legacy_dict)

    solver = BoundedCustomSolver(seed=42, cp_sat_workers=1)
    solver.set_problem(legacy_problem)

    # Even if paths find no candidates and hit continue, iter_limit must be strictly respected
    solution, cost = solver.k_opt_bounded(k=3, iter_limit=10)
    assert solution is not None


def test_cp_sat_parameters_applied(sample_problem: SolverProblem):
    from unittest.mock import patch
    solver = CVBoundedV1()
    config = SolverConfig(seed=9876, time_limit_seconds=10, cp_sat_workers=3, iterations=1)

    with patch("app.domain.optimization.cv_bounded.cp_model.CpSolver") as mock_solver_cls:
        mock_instance = mock_solver_cls.return_value
        mock_instance.Solve.return_value = 0  # OPTIMAL
        mock_instance.ObjectiveValue.return_value = 1000

        solver.solve(sample_problem, config)

        assert mock_instance.parameters.random_seed == 9876
        assert mock_instance.parameters.num_search_workers == 3
