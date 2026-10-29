from datetime import date
import pytest
from pydantic import ValidationError
from app.domain.timetables.calendar import CalendarRule,CalendarException,resolve_service_day
from app.domain.timetables.time_service import AmbiguousLocalTimeError,NonExistentLocalTimeError


def rule(**changes):
    return CalendarRule(valid_from=date(2026,1,1),valid_until=date(2028,12,31),
        operating_weekdays=[0,1,2,3,4],departure_time='08:00',arrival_time='09:00',arrival_day_offset=0,**changes)


def test_recurring_weekdays_and_date_range_are_actual_rules():
    calendar=rule()
    assert resolve_service_day(calendar,date(2026,6,1),'Europe/Athens').duration_minutes==60
    assert resolve_service_day(calendar,date(2026,6,7),'Europe/Athens') is None
    assert resolve_service_day(calendar,date(2029,1,1),'Europe/Athens') is None


def test_cancel_and_extra_service_are_explicit_and_do_not_mutate_template():
    calendar=rule()
    assert resolve_service_day(calendar,date(2026,6,1),'Europe/Athens',CalendarException(action='cancel')) is None
    assert resolve_service_day(calendar,date(2026,6,7),'Europe/Athens',CalendarException(action='run')).duration_minutes==60
    assert resolve_service_day(calendar,date(2026,6,7),'Europe/Athens') is None
    with pytest.raises(ValueError,match='validity'):
        resolve_service_day(calendar,date(2029,1,1),'Europe/Athens',CalendarException(action='run'))


def test_dated_override_and_overnight_rollover_use_calendar_arithmetic():
    calendar=rule()
    exception=CalendarException(action='run',departure_time='23:30',arrival_time='01:15',arrival_day_offset=1)
    trip=resolve_service_day(calendar,date(2026,12,31),'Europe/Athens',exception)
    assert trip.end_utc.date()==date(2026,12,31)  # 01:15 Athens on Jan 1 is 23:15 UTC Dec 31.
    assert trip.duration_minutes==105
    assert calendar.departure_time=='08:00'


def test_dst_gap_blocks_materialization_and_fold_needs_a_dated_choice():
    calendar=rule()
    with pytest.raises(NonExistentLocalTimeError):
        resolve_service_day(calendar,date(2026,3,29),'Europe/Athens',CalendarException(action='run',departure_time='03:10',arrival_time='04:00'))
    with pytest.raises(AmbiguousLocalTimeError):
        resolve_service_day(calendar,date(2026,10,25),'Europe/Athens',CalendarException(action='run',departure_time='03:10',arrival_time='03:40'))
    trip=resolve_service_day(calendar,date(2026,10,25),'Europe/Athens',CalendarException(action='run',departure_time='03:10',arrival_time='03:40',fold_start=0,fold_end=1))
    assert trip.duration_minutes==90


@pytest.mark.parametrize('changes',[
    {'operating_weekdays':[]},{'operating_weekdays':[7]},{'operating_weekdays':[True]},
    {'operating_weekdays':[0,0]},{'departure_time':'24:00'},
    {'valid_from':date(2030,1,1)},{'arrival_day_offset':True},
])
def test_invalid_calendar_never_becomes_operational(changes):
    values=dict(valid_from=date(2026,1,1),valid_until=date(2028,12,31),operating_weekdays=[0],
                departure_time='08:00',arrival_time='09:00',arrival_day_offset=0)
    with pytest.raises(ValidationError):CalendarRule(**{**values,**changes})
