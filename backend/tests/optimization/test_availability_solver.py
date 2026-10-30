"""CV must never assign into an absence; the original reference solver stays unmodified and refuses availability problems."""
from datetime import date
import pytest
from app.domain.optimization.contracts import Assignment, ChainSnapshot, ResourceSnapshot, SolverConfig, SolverProblem, TripSnapshot
from app.domain.optimization.cv_bounded import CVBoundedV1
from app.domain.optimization.cv_legacy import CVLegacyV0, InvalidSolverInput, validate_cv_input
from app.domain.verification.verifier import HardRuleVerifier

CONFIG = SolverConfig(seed=1, time_limit_seconds=20, iterations=2)


def problem(windows, *, trips=None, chains=(), resources=None):
    trips = trips or (TripSnapshot('T1', 'A', 'A', 480, 540, 60), TripSnapshot('T2', 'A', 'A', 600, 660, 60))
    resources = resources or (ResourceSnapshot('R1', 'D1', 'B1', 'A', available_windows=windows),)
    return SolverProblem('P', '1', date(2026, 6, 1), tuple(trips), tuple(resources), tuple(chains), stations=('A',), transfer_matrix=((0,),),
                         availability_enforced=True)


def assigned(result):
    return {assignment.trip_id for assignment in result.assignments}


def test_cv_never_assigns_a_trip_into_an_absence():
    result = CVBoundedV1().solve(problem(((570, 700),)), CONFIG)
    assert assigned(result) == {'T2'} and result.unassigned_trip_ids == ('T1',)
    assert HardRuleVerifier().verify(problem(((570, 700),)), result).valid


def test_a_known_empty_crew_receives_nothing():
    result = CVBoundedV1().solve(problem(()), CONFIG)
    assert assigned(result) == set() and set(result.unassigned_trip_ids) == {'T1', 'T2'}


def test_a_forged_assignment_into_the_absence_fails_independent_verification():
    forged = [Assignment('R1', 'T1', 480, 540, 'A', 'A')]
    report = HardRuleVerifier().verify(problem(((570, 700),)), forged)
    assert not report.valid and 'RULE_AVAILABILITY_TRIP' in {v.rule_id for v in report.violations}


def test_a_mandatory_chain_broken_by_an_absence_is_left_unassigned_not_split():
    chained = problem(((570, 700),), chains=[ChainSnapshot(('T1', 'T2'))])
    result = CVBoundedV1().solve(chained, CONFIG)
    assert assigned(result) == set() and set(result.unassigned_trip_ids) == {'T1', 'T2'}
    assert not {v.rule_id for v in HardRuleVerifier().verify(chained, result).violations} & {'RULE_AVAILABILITY_TRIP', 'RULE_AVAILABILITY_TRANSITION'}


def test_the_original_reference_solver_refuses_availability_problems():
    with pytest.raises(InvalidSolverInput):
        CVLegacyV0().solve(problem(((0, 1440),)), CONFIG)


def test_enforced_problems_need_windows_and_unique_vehicles():
    with pytest.raises(InvalidSolverInput):
        validate_cv_input(problem(None), minimum_resources=1)
    shared = (ResourceSnapshot('R1', 'D1', 'B1', 'A', available_windows=((0, 1440),)), ResourceSnapshot('R2', 'D2', 'B1', 'A', available_windows=((0, 1440),)))
    with pytest.raises(InvalidSolverInput):
        validate_cv_input(problem(None, resources=shared), minimum_resources=1)
