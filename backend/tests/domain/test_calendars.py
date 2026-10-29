"""Operational calendar boundaries, with explicit test data rather than guessed defaults."""
from datetime import date
import pytest
from app.domain.optimization.adapter import OperationalSnapshot,SyntheticResourcePair,to_cv_problem


def raw_trip(**changes):
    return {'id':'T1','origin':'A','destination':'B','start_time':'23:30','end_time':'01:15',
            'arrival_day_offset':1,'allowed_bus_types':['02'],**changes}


def snapshot(day,trip,configured_transfers=True):
    return OperationalSnapshot(1,day,[SyntheticResourcePair(1,1,'A',bus_type='02')],[trip],
        transfer_durations={('A','B'):30,('B','A'):35} if configured_transfers else {})


@pytest.mark.parametrize('day',[date(2026,1,31),date(2026,12,31),date(2028,2,29)])
def test_overnight_calendar_rollover_uses_calendar_delta(day):
    problem=to_cv_problem(snapshot(day,raw_trip()))
    assert problem.trips[0].duration_minutes==105
    assert problem.trips[0].end_minutes==25*60+15


def test_explicit_next_day_arrival_is_preserved_even_when_clock_time_is_later():
    problem=to_cv_problem(snapshot(date(2026,6,1),raw_trip(start_time='08:00',end_time='09:00',arrival_day_offset=1)))
    assert problem.trips[0].duration_minutes==25*60


def test_dst_fold_resolution_is_not_discarded_by_adapter():
    problem=to_cv_problem(snapshot(date(2026,10,25),raw_trip(start_time='03:10',end_time='03:40',arrival_day_offset=0,fold_start=0,fold_end=1)))
    assert problem.trips[0].duration_minutes==90


def test_adapter_requires_explicit_arrival_day_instead_of_guessing():
    trip=raw_trip();trip.pop('arrival_day_offset')
    with pytest.raises(ValueError,match='arrival day'):
        to_cv_problem(snapshot(date(2026,6,1),trip))


def test_adapter_requires_actual_vehicle_and_route_eligibility_types():
    pair=SyntheticResourcePair(1,1,'A',bus_type='02')
    source=OperationalSnapshot(1,date(2026,6,1),[pair],[raw_trip()],
        transfer_durations={('A','B'):30,('B','A'):35})
    problem=to_cv_problem(source)
    assert problem.resources[0].bus_type=='02'
    assert problem.trips[0].allowed_bus_types==('02',)
    assert problem.transfer_matrix==((0,30),(35,0))


def test_adapter_rejects_unconfigured_transfer_instead_of_zero_minutes():
    with pytest.raises(ValueError,match='transfer'):
        to_cv_problem(snapshot(date(2026,6,1),raw_trip(),configured_transfers=False))
