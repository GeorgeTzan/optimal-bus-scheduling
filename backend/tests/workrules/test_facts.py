from dataclasses import replace
from datetime import date, datetime, timezone

from app.domain.workrules.facts import Gap, duty_facts
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import (
    Baseline,
    DriverProfile,
    DriverTimeline,
    Duty,
    DutyTrip,
)

POLICY = build_policy({}, [], 0)
PROFILE = DriverProfile("A", True, True, False, frozenset({1}), frozenset({2}))


def utc(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)


def trip(tid, start, end, origin="A", destination="A", od=False, dd=False, urban=False, long_route=False):
    return DutyTrip(tid, start, end, origin, destination, od, dd, "v1", 1, urban, long_route)


def duty(*trips):
    return Duty("d1", date(2026, 3, 2), tuple(trips), "draft")


def no_transfer(a, b):
    return None


def facts(d, transfer=no_transfer, profile=PROFILE):
    return duty_facts(d, profile, POLICY, transfer)


def test_single_trip_allowances():
    f = facts(duty(trip("t", utc(2, 8), utc(2, 9))))
    assert f.start == utc(2, 7, 35)
    assert f.end == utc(2, 9, 10)
    assert f.work_minutes == 95


def test_depot_skips_dead_run():
    f = facts(duty(trip("t", utc(2, 8), utc(2, 9), od=True)))
    assert f.start == utc(2, 7, 50)


def test_gap_classification():
    d = duty(
        trip("a", utc(2, 8), utc(2, 9)),
        trip("b", utc(2, 9, 10), utc(2, 10)),
        trip("c", utc(2, 10, 40), utc(2, 11)),
        trip("d", utc(2, 12, 30), utc(2, 13)),
    )
    f = facts(d)
    assert [g.kind for g in f.gaps] == ["work", "break", "interruption"]
    assert f.interruptions == 1
    assert f.interruption_minutes == 90


def test_boundary_gaps():
    d = duty(
        trip("a", utc(2, 8), utc(2, 9)),
        trip("b", utc(2, 9, 15), utc(2, 10)),
        trip("c", utc(2, 11), utc(2, 12)),
    )
    assert [g.kind for g in facts(d).gaps] == ["break", "break"]


def test_transfer_counts_as_driving():
    d = duty(
        trip("a", utc(2, 8), utc(2, 9), destination="B"),
        trip("b", utc(2, 9, 50), utc(2, 10), origin="C"),
    )
    f = facts(d, transfer=lambda a, b: 20)
    assert f.driving_minutes == 60 + 20 + 10 + 25
    assert f.gaps[0].kind == "break"
    assert f.gaps[0].start == utc(2, 9, 20)


def test_unknown_transfer_is_driving():
    d = duty(
        trip("a", utc(2, 8), utc(2, 9), destination="B"),
        trip("b", utc(2, 9, 50), utc(2, 10), origin="C"),
    )
    f = facts(d)
    assert f.driving_minutes == 60 + 50 + 10 + 25


def test_continuous_driving_reset_by_split_break():
    d = duty(
        trip("a", utc(2, 8), utc(2, 10), od=True),
        trip("b", utc(2, 10, 15), utc(2, 12, 15)),
        trip("c", utc(2, 12, 45), utc(2, 14, 45), dd=True),
    )
    assert facts(d).longest_driving_without_break == 240


def test_full_break_resets():
    d = duty(
        trip("a", utc(2, 8), utc(2, 10), od=True),
        trip("b", utc(2, 10, 45), utc(2, 12, 45), dd=True),
    )
    assert facts(d).longest_driving_without_break == 120


def test_urban_break():
    d = duty(
        trip("a", utc(2, 8), utc(2, 9), urban=True),
        trip("b", utc(2, 9, 30), utc(2, 10), urban=True),
    )
    f = facts(d)
    assert f.urban and f.urban_break_taken


def test_overtime():
    f = facts(duty(trip("t", utc(2, 8), utc(2, 16, 25))))
    assert f.work_minutes == 540
    assert f.overtime_minutes == 60


def test_cross_midnight_duty():
    f = facts(duty(trip("t", utc(2, 23), utc(3, 1, 30), od=True, dd=True)))
    assert f.driving_minutes == 150


def test_dst_october():
    start = datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc)
    end = datetime(2026, 10, 25, 2, 30, tzinfo=timezone.utc)
    f = facts(duty(trip("t", start, end, od=True, dd=True)))
    assert f.driving_minutes == 180


def test_long_route_driving():
    f = facts(duty(trip("t", utc(2, 8), utc(2, 9), long_route=True)))
    assert f.long_route_driving_minutes == 60


def test_ends_away_from_base():
    away = facts(duty(trip("t", utc(2, 8), utc(2, 9), destination="B")))
    home = facts(duty(trip("t", utc(2, 8), utc(2, 9))))
    assert away.ends_away_from_base is True
    assert home.ends_away_from_base is False


def test_timeline_round_trip_and_with_day():
    d = duty(trip("t", utc(2, 8), utc(2, 9)))
    baseline = Baseline(date(2026, 3, 1), 30, utc(1, 20), None, True, 0)
    tl = DriverTimeline("d1", PROFILE, (d,), baseline, date(2026, 2, 1), {"v1": frozenset({3, 4})})
    assert DriverTimeline.from_dict(tl.to_dict()) == tl
    assert tl.with_day(date(2026, 3, 2), None).duties == ()
    assert tl.with_day(date(2026, 3, 3), d).duties[-1] is d


def long_trip(stop, od=True, dd=True):
    return replace(trip("t", utc(2, 8), utc(2, 13), od=od, dd=dd), en_route_break_minutes=stop)


def test_long_trip_without_stop_runs_continuously():
    f = facts(duty(long_trip(0)))
    assert f.longest_driving_without_break == 300
    assert f.driving_minutes == 300


def test_full_en_route_stop_resets_continuous_driving():
    plain, stopped = facts(duty(long_trip(0, False, False))), facts(duty(long_trip(45, False, False)))
    assert stopped.driving_minutes == 255 + 25
    assert stopped.longest_driving_without_break == 15 + 127
    assert stopped.work_minutes == plain.work_minutes
    assert stopped.gaps == (Gap(utc(2, 10, 7), utc(2, 10, 52), "break"),)
    assert stopped.interruptions == 0


def test_short_en_route_stop_is_only_a_first_piece():
    f = facts(duty(long_trip(20)))
    assert f.longest_driving_without_break == 280
    assert f.work_minutes == facts(duty(long_trip(0))).work_minutes


def test_long_en_route_stop_counts_as_work_not_interruption():
    plain, stopped = facts(duty(long_trip(0))), facts(duty(long_trip(90)))
    assert stopped.work_minutes == plain.work_minutes
    assert stopped.interruptions == 0
    assert stopped.longest_driving_without_break == 105


def test_short_en_route_stop_completes_a_split_break():
    d = duty(trip("a", utc(2, 6), utc(2, 7), od=True, dd=True), replace(long_trip(30), start=utc(2, 7, 20), end=utc(2, 12, 20)))
    assert facts(d).longest_driving_without_break == 60 + 135


def test_stored_trip_without_stop_loads_as_zero():
    stored = trip("t", utc(2, 8), utc(2, 9)).to_dict()
    stored.pop("en_route_break_minutes")
    assert DutyTrip.from_dict(stored).en_route_break_minutes == 0
