from dataclasses import replace
import pytest
from tests.verification.test_verifier import base_problem
from app.domain.optimization.contracts import Assignment
from app.domain.verification.verifier import verify_schedule


def assignment(trip,**changes):
    values=dict(resource_id='R1',trip_id=trip.id,start_minutes=trip.start_minutes,end_minutes=trip.end_minutes,
                start_station=trip.start_station,end_station=trip.end_station)
    return Assignment(**{**values,**changes})


def test_candidate_cannot_hide_overlap_by_forging_assignment_times(base_problem):
    first,_,overlapping=base_problem.trips
    report=verify_schedule(base_problem,[assignment(first),assignment(overlapping,start_minutes=700,end_minutes=850)])
    assert not report.valid
    assert {'RULE_ASSIGNMENT_SNAPSHOT','RULE_NO_TEMPORAL_OVERLAP'}<=set(v.rule_id for v in report.violations)


def test_candidate_cannot_replace_authoritative_route_stations(base_problem):
    trip=base_problem.trips[0]
    report=verify_schedule(base_problem,[assignment(trip,end_station='FAKE')])
    assert not report.valid
    assert 'RULE_ASSIGNMENT_SNAPSHOT' in [v.rule_id for v in report.violations]


@pytest.mark.parametrize('matrix',[(),((0,),),((0,10,20),('unknown',0,15),(20,15,0)),((0,10,20),(-1,0,15),(20,15,0))])
def test_unknown_or_invalid_transfer_is_never_assumed_zero(base_problem,matrix):
    first,second,_=base_problem.trips
    second=replace(second,start_station='ATHENS')
    problem=replace(base_problem,trips=(first,second),transfer_matrix=matrix)
    report=verify_schedule(problem,[assignment(first),assignment(second)])
    assert not report.valid
    assert 'RULE_UNKNOWN_TRANSFER' in [v.rule_id for v in report.violations]
