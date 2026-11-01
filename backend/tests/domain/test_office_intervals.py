"""Half-open UTC intervals and explicit wall-clock resolution for office records."""
from datetime import datetime, timezone
import pytest
from app.domain.office.intervals import merge, normalize_office_interval, overlaps, subtract
from app.domain.timetables.time_service import AmbiguousLocalTimeError, NonExistentLocalTimeError

ZONE = 'Europe/Athens'


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


def test_adjacent_intervals_do_not_overlap_and_merge():
    first, second = (utc(2026, 11, 2, 8), utc(2026, 11, 2, 9)), (utc(2026, 11, 2, 9), utc(2026, 11, 2, 10))
    assert not overlaps(first, second) and not overlaps(second, first)
    assert merge([second, first]) == [(utc(2026, 11, 2, 8), utc(2026, 11, 2, 10))]


def test_contained_and_partial_overlap_subtract_correctly():
    outer = (utc(2026, 11, 2, 8), utc(2026, 11, 2, 12))
    inner = (utc(2026, 11, 2, 10), utc(2026, 11, 2, 11))
    partial = (utc(2026, 11, 2, 11), utc(2026, 11, 2, 13))
    assert overlaps(outer, inner) and overlaps(outer, partial)
    assert subtract([outer], [inner]) == [(outer[0], inner[0]), (inner[1], outer[1])]
    assert subtract([outer], [partial]) == [(outer[0], partial[0])]
    assert subtract([outer], [outer]) == []
    assert subtract([outer], [(utc(2026, 11, 2, 12), utc(2026, 11, 2, 14))]) == [outer]


def test_overnight_leap_day_and_year_rollover_in_athens():
    assert normalize_office_interval(datetime(2028, 2, 28, 22), datetime(2028, 2, 29, 6), ZONE, None, None) == (utc(2028, 2, 28, 20), utc(2028, 2, 29, 4))
    assert normalize_office_interval(datetime(2026, 12, 31, 22), datetime(2027, 1, 1, 6), ZONE, None, None) == (utc(2026, 12, 31, 20), utc(2027, 1, 1, 4))


def test_open_end_stays_open_and_inverted_interval_is_rejected():
    assert normalize_office_interval(datetime(2026, 11, 2, 8), None, ZONE, None, None) == (utc(2026, 11, 2, 6), None)
    for end in (datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 7)):
        with pytest.raises(ValueError):
            normalize_office_interval(datetime(2026, 11, 2, 8), end, ZONE, None, None)


def test_dst_gap_and_fold_need_explicit_resolution():
    with pytest.raises(NonExistentLocalTimeError) as gap:
        normalize_office_interval(datetime(2027, 3, 28, 3, 30), datetime(2027, 3, 28, 12), ZONE, None, None)
    assert gap.value.issues[0]['field'] == 'start_local'
    with pytest.raises(AmbiguousLocalTimeError):
        normalize_office_interval(datetime(2027, 10, 31, 3, 30), datetime(2027, 10, 31, 12), ZONE, None, None)
    assert normalize_office_interval(datetime(2027, 10, 31, 3, 30), datetime(2027, 10, 31, 12), ZONE, 0, None)[0] == utc(2027, 10, 31, 0, 30)
    assert normalize_office_interval(datetime(2027, 10, 31, 3, 30), datetime(2027, 10, 31, 12), ZONE, 1, None)[0] == utc(2027, 10, 31, 1, 30)
