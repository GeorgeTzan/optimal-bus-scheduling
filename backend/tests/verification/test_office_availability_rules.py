"""The independent verifier recomputes availability from frozen windows only; it never trusts a solver flag."""
from datetime import date
from app.domain.optimization.contracts import Assignment, ResourceSnapshot, SolverProblem, TripSnapshot
from app.domain.verification.verifier import HardRuleVerifier

OPEN = ((480, 1080),)


def verify(windows, trips, *, enforced=True, exempt=(), stations=('A', 'B', 'C'), matrix=None):
    resource = ResourceSnapshot('R1', 'D1', 'B1', 'A', available_windows=windows)
    matrix = matrix or ((0, 5, 30), (5, 0, 30), (30, 30, 0))
    problem = SolverProblem('P', '1', date(2026, 6, 1), tuple(trips), (resource,), (), stations=stations, transfer_matrix=matrix,
                            availability_enforced=enforced, availability_exempt_trip_ids=tuple(exempt))
    assignments = [Assignment('R1', trip.id, trip.start_minutes, trip.end_minutes, trip.start_station, trip.end_station) for trip in trips]
    return HardRuleVerifier().verify(problem, assignments)


def codes(report):
    return {violation.rule_id for violation in report.violations}


def trip(identifier, start, end, origin='A', destination='A'):
    return TripSnapshot(identifier, origin, destination, start, end, end - start)


def test_trip_outside_the_window_fails_and_the_boundary_is_allowed():
    assert 'RULE_AVAILABILITY_TRIP' in codes(verify(OPEN, [trip('T1', 420, 500)]))
    assert 'RULE_AVAILABILITY_TRIP' in codes(verify(OPEN, [trip('T1', 1000, 1081)]))
    assert 'RULE_AVAILABILITY_TRIP' not in codes(verify(OPEN, [trip('T1', 480, 540), trip('T2', 1020, 1080)]))


def test_a_trip_may_use_either_of_two_windows_but_not_the_gap_between_them():
    windows = ((480, 720), (840, 1080))
    assert 'RULE_AVAILABILITY_TRIP' not in codes(verify(windows, [trip('T1', 500, 600), trip('T2', 900, 960)]))
    assert 'RULE_AVAILABILITY_TRIP' in codes(verify(windows, [trip('T1', 700, 860)]))


def test_travel_must_fit_inside_one_window_not_across_an_absence():
    split = ((480, 720), (840, 1080))
    first, second = trip('T1', 600, 705, 'A', 'B'), trip('T2', 855, 900, 'C', 'C')
    assert 'RULE_AVAILABILITY_TRANSITION' in codes(verify(split, [first, second]))
    assert 'RULE_AVAILABILITY_TRANSITION' not in codes(verify(((480, 1080),), [first, second]))


def test_unknown_windows_fail_when_enforced_and_are_ignored_for_legacy_snapshots():
    assert 'RULE_AVAILABILITY_UNKNOWN' in codes(verify(None, [trip('T1', 500, 600)]))
    assert not {c for c in codes(verify(None, [trip('T1', 500, 600)], enforced=False)) if c.startswith('RULE_AVAILABILITY')}
    assert not {c for c in codes(verify(((0, 10),), [trip('T1', 500, 600)], enforced=False)) if c.startswith('RULE_AVAILABILITY')}


def test_a_known_empty_crew_rejects_any_assignment_and_an_exempt_trip_is_skipped():
    assert 'RULE_AVAILABILITY_TRIP' in codes(verify((), [trip('T1', 500, 600)]))
    assert 'RULE_AVAILABILITY_TRIP' not in codes(verify((), [trip('T1', 500, 600)], exempt=['T1']))
    assert 'RULE_AVAILABILITY_UNKNOWN' not in codes(verify(None, [trip('T1', 500, 600)], exempt=['T1']))


def test_travel_may_happen_anywhere_in_the_gap_inside_a_middle_working_window():
    windows = ((480, 500), (600, 700), (900, 1000))
    first, second = trip('T1', 480, 500, 'A', 'A'), trip('T2', 900, 960, 'C', 'C')  # travel A to C takes 30 minutes
    assert 'RULE_AVAILABILITY_TRANSITION' not in codes(verify(windows, [first, second]))
    assert 'RULE_AVAILABILITY_TRANSITION' in codes(verify(((480, 500), (900, 1000)), [first, second]))


def test_a_vehicle_handed_to_another_driver_needs_one_of_them_to_have_time_for_the_empty_transfer():
    def handover(second_window):
        resources = (ResourceSnapshot('R1', 'D1', 'B1', 'A', available_windows=((480, 520),)), ResourceSnapshot('R2', 'D2', 'B1', 'C', available_windows=second_window))
        first, second = trip('T1', 480, 520, 'A', 'A'), trip('T2', 840, 900, 'C', 'C')
        problem = SolverProblem('P', '1', date(2026, 6, 1), (first, second), resources, (), stations=('A', 'B', 'C'), transfer_matrix=((0, 5, 30), (5, 0, 30), (30, 30, 0)), availability_enforced=True)
        return HardRuleVerifier().verify(problem, [Assignment('R1', 'T1', 480, 520, 'A', 'A'), Assignment('R2', 'T2', 840, 900, 'C', 'C')])
    assert 'RULE_AVAILABILITY_TRANSITION' in codes(handover(((835, 900),)))  # the bus needs 30 minutes; neither driver is working then
    assert 'RULE_AVAILABILITY_TRANSITION' not in codes(handover(((800, 900),)))  # the second driver can fetch it
