from datetime import date
import pytest
from app.domain.optimization.contracts import (
    SolverProblem,
    TripSnapshot,
    ResourceSnapshot,
    ChainSnapshot,
    Assignment,
)
from app.domain.verification.rules import RuleSet
from app.domain.verification.verifier import verify_schedule


@pytest.fixture
def base_problem() -> SolverProblem:
    t1 = TripSnapshot(
        id="T1",
        start_station="ATHENS",
        end_station="CORINTH",
        start_minutes=480,
        end_minutes=540,
        duration_minutes=60,
    )
    t2 = TripSnapshot(
        id="T2",
        start_station="CORINTH",
        end_station="PATRAS",
        start_minutes=560,
        end_minutes=680,
        duration_minutes=120,
    )
    t3 = TripSnapshot(
        id="T3",
        start_station="ATHENS",
        end_station="PATRAS",
        start_minutes=500,
        end_minutes=650,
        duration_minutes=150,
    )
    r1 = ResourceSnapshot(
        resource_id="R1",
        driver_id="D1",
        bus_id="B1",
        home_station="ATHENS",
    )
    r2 = ResourceSnapshot(
        resource_id="R2",
        driver_id="D2",
        bus_id="B2",
        home_station="ATHENS",
    )
    return SolverProblem(
        problem_id="p1",
        tenant_id="tenant-1",
        service_date=date(2026, 11, 1),
        trips=(t1, t2, t3),
        resources=(r1, r2),
        chains=(),
        stations=("ATHENS", "CORINTH", "PATRAS"),
        transfer_matrix=((0, 10, 20), (10, 0, 15), (20, 15, 0)),
    )


def test_rejects_duplicate_trip(base_problem: SolverProblem):
    # Trip T1 assigned to both R1 and R2
    assignments = [
        Assignment(
            resource_id="R1",
            trip_id="T1",
            start_minutes=480,
            end_minutes=540,
            start_station="ATHENS",
            end_station="CORINTH",
        ),
        Assignment(
            resource_id="R2",
            trip_id="T1",
            start_minutes=480,
            end_minutes=540,
            start_station="ATHENS",
            end_station="CORINTH",
        ),
    ]
    report = verify_schedule(base_problem, assignments, RuleSet())
    assert not report.valid
    duplicate_violations = [v for v in report.violations if v.rule_id == "RULE_UNIQUE_TRIP"]
    assert len(duplicate_violations) > 0
    assert "T1" in duplicate_violations[0].entity_ids


def test_rejects_overlapping_trips(base_problem: SolverProblem):
    # Resource R1 assigned T1 (480-540) and T3 (500-650) which overlap temporally
    assignments = [
        Assignment(
            resource_id="R1",
            trip_id="T1",
            start_minutes=480,
            end_minutes=540,
            start_station="ATHENS",
            end_station="CORINTH",
        ),
        Assignment(
            resource_id="R1",
            trip_id="T3",
            start_minutes=500,
            end_minutes=650,
            start_station="ATHENS",
            end_station="PATRAS",
        ),
    ]
    report = verify_schedule(base_problem, assignments, RuleSet())
    assert not report.valid
    overlap_violations = [v for v in report.violations if v.rule_id == "RULE_NO_TEMPORAL_OVERLAP"]
    assert len(overlap_violations) > 0


def test_rejects_broken_chain(base_problem: SolverProblem):
    # Add a mandatory chain: T1 -> T2
    problem_with_chain = SolverProblem(
        problem_id=base_problem.problem_id,
        tenant_id=base_problem.tenant_id,
        service_date=base_problem.service_date,
        trips=base_problem.trips,
        resources=base_problem.resources,
        chains=(ChainSnapshot(trip_ids=("T1", "T2")),),
        stations=base_problem.stations,
        transfer_matrix=base_problem.transfer_matrix,
    )
    # T1 assigned to R1, T2 assigned to R2 -> Broken chain!
    assignments = [
        Assignment(
            resource_id="R1",
            trip_id="T1",
            start_minutes=480,
            end_minutes=540,
            start_station="ATHENS",
            end_station="CORINTH",
        ),
        Assignment(
            resource_id="R2",
            trip_id="T2",
            start_minutes=560,
            end_minutes=680,
            start_station="CORINTH",
            end_station="PATRAS",
        ),
    ]
    report = verify_schedule(problem_with_chain, assignments, RuleSet())
    assert not report.valid
    chain_violations = [v for v in report.violations if v.rule_id == "RULE_MANDATORY_CHAIN"]
    assert len(chain_violations) > 0


def test_reports_unassigned_without_falsely_claiming_valid_full_coverage(base_problem: SolverProblem):
    # Only T1 and T2 assigned; T3 is unassigned
    assignments = [
        Assignment(
            resource_id="R1",
            trip_id="T1",
            start_minutes=480,
            end_minutes=540,
            start_station="ATHENS",
            end_station="CORINTH",
        ),
        Assignment(
            resource_id="R1",
            trip_id="T2",
            start_minutes=560,
            end_minutes=680,
            start_station="CORINTH",
            end_station="PATRAS",
        ),
    ]
    # With require_full_coverage=True, must be invalid
    rules_full = RuleSet(require_full_coverage=True)
    report_full = verify_schedule(base_problem, assignments, rules_full)
    assert not report_full.valid
    assert "T3" in report_full.unassigned_trips
    coverage_violations = [v for v in report_full.violations if v.rule_id == "RULE_REQUIRED_COVERAGE"]
    assert len(coverage_violations) > 0

    # With require_full_coverage=False, validity depends on other rules, but unassigned_trips accurately reported
    rules_partial = RuleSet(require_full_coverage=False)
    report_partial = verify_schedule(base_problem, assignments, rules_partial)
    assert report_partial.valid
    assert report_partial.unassigned_trips == ["T3"]
    assert report_partial.coverage_percent == pytest.approx(66.67, 0.01)
