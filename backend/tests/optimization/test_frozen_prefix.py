from datetime import date
import pytest

from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot, Assignment
from app.domain.incidents.recovery_spike import (
    split_operated_future,
    build_recovery_input,
    RecoveryProblemInput,
)


@pytest.fixture
def sample_schedule():
    trips = (
        TripSnapshot(id="T1", start_station="Patras", end_station="Athens", start_minutes=480, end_minutes=660, duration_minutes=180),   # 08:00 - 11:00
        TripSnapshot(id="T2", start_station="Athens", end_station="Patras", start_minutes=720, end_minutes=900, duration_minutes=180),   # 12:00 - 15:00
        TripSnapshot(id="T3", start_station="Patras", end_station="Aigio", start_minutes=960, end_minutes=1020, duration_minutes=60),   # 16:00 - 17:00
        TripSnapshot(id="T4", start_station="Patras", end_station="Athens", start_minutes=540, end_minutes=720, duration_minutes=180),   # 09:00 - 12:00
        TripSnapshot(id="T5", start_station="Athens", end_station="Patras", start_minutes=780, end_minutes=960, duration_minutes=180),   # 13:00 - 16:00
    )
    resources = (
        ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="Patras"),
        ResourceSnapshot(resource_id="R2", driver_id="D2", bus_id="B2", home_station="Patras"),
        ResourceSnapshot(resource_id="RESERVE_1", driver_id="D_RES", bus_id="B_RES", home_station="Patras"),
    )
    assignments = (
        Assignment(resource_id="R1", trip_id="T1", start_minutes=480, end_minutes=660, start_station="Patras", end_station="Athens"),
        Assignment(resource_id="R1", trip_id="T2", start_minutes=720, end_minutes=900, start_station="Athens", end_station="Patras"),
        Assignment(resource_id="R1", trip_id="T3", start_minutes=960, end_minutes=1020, start_station="Patras", end_station="Aigio"),
        Assignment(resource_id="R2", trip_id="T4", start_minutes=540, end_minutes=720, start_station="Patras", end_station="Athens"),
        Assignment(resource_id="R2", trip_id="T5", start_minutes=780, end_minutes=960, start_station="Athens", end_station="Patras"),
    )
    problem = SolverProblem(
        problem_id="P_RECOVERY",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=trips,
        resources=resources,
        chains=(),
    )
    return {"problem": problem, "assignments": assignments}


def test_split_operated_future(sample_schedule):
    """
    Given an operational timestamp (e.g. 11:30 = 690 minutes),
    trips with start_minutes < 690 belong to the immutable frozen prefix.
    """
    assignments = sample_schedule["assignments"]
    frozen, future = split_operated_future(assignments, as_of_minutes=690)

    # T1 (start 480) and T4 (start 540) are frozen
    frozen_trip_ids = {a.trip_id for a in frozen}
    assert frozen_trip_ids == {"T1", "T4"}

    # T2 (start 720), T5 (start 780), T3 (start 960) are future remainder
    future_trip_ids = {a.trip_id for a in future}
    assert future_trip_ids == {"T2", "T5", "T3"}


def test_mid_duty_breakdown_preserves_past(sample_schedule):
    """
    At 12:30 (750 minutes), bus R1 suffers an engine breakdown at Athens station.
    - Past trips (T1 on R1) remain permanently frozen on R1.
    - Future trips (T3) on R1 must be re-scheduled to an available reserve resource.
    - Ongoing/broken trip T2 (12:00-15:00) is marked disrupted.
    """
    problem = sample_schedule["problem"]
    assignments = sample_schedule["assignments"]

    recovery_input = build_recovery_input(
        problem=problem,
        assignments=assignments,
        as_of_minutes=750,
        disabled_resource_ids={"R1"},
        locked_trip_ids=set(),
    )

    # Past trip T1 is frozen on R1
    assert any(a.trip_id == "T1" and a.resource_id == "R1" for a in recovery_input.frozen_assignments)

    # Future active resources exclude R1
    active_res_ids = {r.resource_id for r in recovery_input.future_problem.resources}
    assert "R1" not in active_res_ids
    assert "RESERVE_1" in active_res_ids

    # Unassigned or candidate trips to re-optimize include T3
    future_trip_ids = {t.id for t in recovery_input.future_problem.trips}
    assert "T3" in future_trip_ids


def test_locked_assignment_cannot_move(sample_schedule):
    """
    A future trip explicitly locked by the dispatcher (e.g. VIP or state contract)
    cannot be moved to another resource during recovery.
    """
    problem = sample_schedule["problem"]
    assignments = sample_schedule["assignments"]

    recovery_input = build_recovery_input(
        problem=problem,
        assignments=assignments,
        as_of_minutes=690,
        disabled_resource_ids=set(),
        locked_trip_ids={"T5"},  # T5 locked on R2
    )

    # T5 is preserved on R2 in locked assignments
    assert any(a.trip_id == "T5" and a.resource_id == "R2" for a in recovery_input.locked_assignments)


def test_unavailable_replacement_returns_infeasible_proposal(sample_schedule):
    """
    If all resources break down and no reserve is available, recovery input
    identifies that trips cannot be covered rather than silently vanishing.
    """
    problem = sample_schedule["problem"]
    assignments = sample_schedule["assignments"]

    # All resources disabled
    recovery_input = build_recovery_input(
        problem=problem,
        assignments=assignments,
        as_of_minutes=690,
        disabled_resource_ids={"R1", "R2", "RESERVE_1"},
        locked_trip_ids=set(),
    )

    assert len(recovery_input.future_problem.resources) == 0
    assert len(recovery_input.orphaned_trip_ids) > 0
