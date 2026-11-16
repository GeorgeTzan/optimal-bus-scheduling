from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from app.domain.workrules.evaluate import evaluate
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import DriverProfile, DriverTimeline, Duty, DutyTrip

POLICY = build_policy({}, [], 0)
DAY = date(2026, 11, 9)


def profile(**kw):
    base = dict(
        home_station="A",
        overnight_allowed=True,
        split_shift_allowed=True,
        must_return_to_base=False,
        forbidden_routes=frozenset(),
        preferred_routes=frozenset(),
    )
    base.update(kw)
    return DriverProfile(**base)


def at(day, minute):
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minute)


def trip(tid, day, start, end, origin="A", destination="A", urban=False, long_route=True, route_id=None, vehicle="V1"):
    return DutyTrip(tid, at(day, start), at(day, end), origin, destination, True, True, vehicle, route_id, urban, long_route)


def duty(day, *trips, emergency=False):
    return Duty("d1", day, tuple(trips), "published", emergency)


def timeline(*duties, prof=None, fvr=None):
    return DriverTimeline("d1", prof or profile(), tuple(duties), None, DAY, fvr or {})


def no_transfer(a, b):
    return 0


def run(tl, day=DAY, policy=POLICY):
    return evaluate(tl, policy, (day, day), no_transfer)


def only(findings, rule_id):
    return [f for f in findings if f.rule_id == rule_id]


def test_daily_work_over_max():
    f = only(run(timeline(duty(DAY, trip("t", DAY, 360, 965, long_route=False)))), "WR_DAILY_WORK")
    assert len(f) == 1
    assert (f[0].kind, f[0].measured, f[0].limit) == ("legal", 615, 600)
    assert f[0].message_key == "workrules.WR_DAILY_WORK"
    assert f[0].source == "PD 54/1998 Art. 3(2), 6(3)"
    assert f[0].key == "WR_DAILY_WORK|d1|2026-11-09|t|615"


def test_emergency_duty_allows_660():
    d = duty(DAY, trip("t", DAY, 360, 990, long_route=False), emergency=True)
    assert not only(run(timeline(d)), "WR_DAILY_WORK")
    over = duty(DAY, trip("t", DAY, 360, 1030, long_route=False), emergency=True)
    f = only(run(timeline(over)), "WR_DAILY_WORK")
    assert len(f) == 1 and (f[0].measured, f[0].limit) == (680, 660)


def test_continuous_driving_290():
    f = only(run(timeline(duty(DAY, trip("t", DAY, 360, 650, long_route=False)))), "WR_CONTINUOUS_DRIVING")
    assert len(f) == 1
    assert (f[0].kind, f[0].measured, f[0].limit) == ("legal", 290, 270)
    assert f[0].hint == {"break_needed_by": "2026-11-09T10:30:00+00:00"}


def test_en_route_stop_counts_as_driver_break():
    def found(stop):
        return only(run(timeline(duty(DAY, replace(trip("t", DAY, 360, 660, long_route=False), en_route_break_minutes=stop)))), "WR_CONTINUOUS_DRIVING")
    assert [f.measured for f in found(0)] == [300]
    assert found(45) == []
    assert [f.measured for f in found(20)] == [280]


def test_break_needed_by_anchored_after_full_break():
    d = duty(DAY, trip("a", DAY, 360, 400), trip("b", DAY, 460, 770))
    f = only(run(timeline(d)), "WR_CONTINUOUS_DRIVING")
    assert len(f) == 1
    assert f[0].measured == 310
    assert f[0].hint == {"break_needed_by": "2026-11-09T12:10:00+00:00"}


def test_short_urban_duty_without_break_flagged():
    d = duty(DAY, trip("a", DAY, 360, 420, urban=True), trip("b", DAY, 425, 480, urban=True))
    assert len(only(run(timeline(d)), "WR_URBAN_BREAK")) == 1


def test_urban_without_30_break():
    d = duty(DAY, trip("a", DAY, 360, 500, urban=True), trip("b", DAY, 510, 650, urban=True))
    f = only(run(timeline(d)), "WR_URBAN_BREAK")
    assert len(f) == 1
    assert (f[0].kind, f[0].limit) == ("legal", 30)


def test_urban_with_30_break_ok():
    d = duty(DAY, trip("a", DAY, 360, 500, urban=True), trip("b", DAY, 535, 650, urban=True))
    assert not only(run(timeline(d)), "WR_URBAN_BREAK")


def test_short_route_not_eu_limited():
    d = duty(
        DAY,
        trip("a", DAY, 360, 600, long_route=False),
        trip("b", DAY, 660, 900, long_route=False),
        trip("c", DAY, 960, 1000, long_route=False),
    )
    assert not only(run(timeline(d)), "WR_DAILY_DRIVING")


def test_daily_driving_over_extended():
    d = duty(
        DAY,
        trip("a", DAY, 300, 560),
        trip("b", DAY, 610, 870),
        trip("c", DAY, 920, 1060),
    )
    f = only(run(timeline(d)), "WR_DAILY_DRIVING")
    assert len(f) == 1
    assert (f[0].measured, f[0].limit) == (660, 600)


def test_third_extension_in_week_blocks():
    def long_day(day, minutes):
        return duty(day, trip("t" + day.isoformat(), day, 300, 300 + minutes // 2), trip("u" + day.isoformat(), day, 300 + minutes // 2 + 45, 300 + minutes + 45))

    mon, tue, wed = DAY, DAY + timedelta(days=1), DAY + timedelta(days=2)
    tl = timeline(long_day(mon, 600), long_day(tue, 600), long_day(wed, 560))
    f = only(evaluate(tl, POLICY, (wed, wed), no_transfer), "WR_DAILY_DRIVING")
    assert len(f) == 1
    assert (f[0].kind, f[0].measured, f[0].limit) == ("legal", 560, 540)
    second = timeline(long_day(mon, 600), long_day(wed, 560))
    assert not only(evaluate(second, POLICY, (wed, wed), no_transfer), "WR_DAILY_DRIVING")


def test_split_shift_warning_only_when_not_allowed():
    d = duty(DAY, trip("a", DAY, 360, 420), trip("b", DAY, 600, 660))
    f = only(run(timeline(d, prof=profile(split_shift_allowed=False))), "WR_SPLIT_SHIFT")
    assert len(f) == 1 and f[0].kind == "warning"
    assert not only(run(timeline(d)), "WR_SPLIT_SHIFT")


def test_must_return_to_base():
    d = duty(DAY, trip("a", DAY, 360, 420, destination="B"))
    f = only(run(timeline(d, prof=profile(must_return_to_base=True))), "WR_MUST_RETURN_BASE")
    assert len(f) == 1 and f[0].kind == "warning"
    assert not only(run(timeline(d)), "WR_MUST_RETURN_BASE")


def test_forbidden_route_warning():
    d = duty(DAY, trip("a", DAY, 360, 420, route_id=7), trip("b", DAY, 430, 480, route_id=8))
    f = only(run(timeline(d, prof=profile(forbidden_routes=frozenset({7})))), "WR_FORBIDDEN_DRIVER_ROUTE")
    assert len(f) == 1 and f[0].kind == "warning" and f[0].trip_ids == ("a",)


def test_forbidden_vehicle_route_warning():
    d = duty(DAY, trip("a", DAY, 360, 420, route_id=7, vehicle="V1"), trip("b", DAY, 430, 480, route_id=7, vehicle="V2"))
    f = only(run(timeline(d, fvr={"V1": frozenset({7})})), "WR_FORBIDDEN_VEHICLE_ROUTE")
    assert len(f) == 1 and f[0].trip_ids == ("a",)


def test_focus_filters_and_sorts():
    other = DAY + timedelta(days=1)
    bad = lambda day: duty(day, trip("t" + day.isoformat(), day, 360, 965, long_route=False))
    tl = timeline(bad(DAY), bad(other))
    assert [f.service_date for f in only(evaluate(tl, POLICY, (DAY, other), no_transfer), "WR_DAILY_WORK")] == [DAY, other]
    assert {f.service_date for f in run(tl, other)} == {other}
