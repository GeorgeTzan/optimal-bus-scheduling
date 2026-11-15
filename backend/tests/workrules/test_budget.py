from datetime import date, datetime, timedelta, timezone

from app.domain.workrules.budget import DriverDayBudget, driver_budget, legal_duty
from app.domain.workrules.findings import WorkRuleFinding, caused_by
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import Baseline, DriverProfile, DriverTimeline, Duty, DutyTrip

POLICY = build_policy({}, [], 0)
MON = date(2026, 11, 9)


def day(n):
    return MON + timedelta(days=n)


def at(d, minute):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(minutes=minute)


def no_transfer(a, b):
    return 0


def profile(**kw):
    base = dict(
        home_station="A",
        overnight_allowed=True,
        split_shift_allowed=True,
        must_return_to_base=False,
        forbidden_routes=frozenset({7, 3}),
        preferred_routes=frozenset({9}),
    )
    base.update(kw)
    return DriverProfile(**base)


def duty(d, start, end, long_route=False):
    t = DutyTrip(f"{d}-0", at(d, start), at(d, end), "A", "A", True, True, "V1", None, False, long_route)
    return Duty("d1", d, (t,), "published")


def timeline(*duties, baseline=None):
    return DriverTimeline("d1", profile(), tuple(duties), baseline, MON, {"V1": frozenset({2, 1})})


def budget(tl, d=day(1)):
    return driver_budget(tl, POLICY, d, at(d, 0), no_transfer)


def test_earliest_start_after_rest():
    tl = timeline(duty(day(0), 1000, 1330))
    assert budget(tl).earliest_start_minutes == 610


def test_latest_end_before_next_published():
    tl = timeline(duty(day(2), 480, 900))
    b = budget(tl)
    assert b.latest_end_minutes == (480 - 10) + 1440 - 720
    assert budget(timeline()).latest_end_minutes == 2880


def test_weekly_remaining_caps_work():
    tl = timeline(*(duty(day(n), 0, 560) for n in (0, 2, 3, 4)))
    work = 560 + 10
    assert budget(tl).max_work_minutes == min(600, 2700 - 4 * work)
    assert budget(timeline()).max_work_minutes == 600


def test_yearly_overtime_caps_work():
    tl = timeline(baseline=Baseline(day(-1), 7200, None, None, True, 0))
    assert budget(tl).max_work_minutes == 480
    tl = timeline(baseline=Baseline(day(-1), 9000, None, None, True, 0))
    assert budget(tl).max_work_minutes == 0


def test_driving_budget():
    tl = timeline(*(duty(day(n), 0, 560, True) for n in (0, 2, 3)))
    assert budget(tl).max_long_route_driving_minutes == 540
    tl = timeline(*(duty(day(n), 0, 300, True) for n in (0, 2, 3, 4)))
    assert budget(tl).max_long_route_driving_minutes == 600


def test_budget_copies_profile():
    b = budget(timeline())
    assert b.forbidden_route_ids == (3, 7)
    assert b.preferred_route_ids == (9,)
    assert b.forbidden_vehicle_route_ids == {"V1": (1, 2)}
    assert b.continuous_driving_minutes == 270


def test_budget_round_trip():
    b = budget(timeline(duty(day(0), 800, 1000)))
    assert DriverDayBudget.from_dict(b.to_dict()) == b


def test_legal_duty_rejects_rest_breach():
    tl = timeline(duty(day(0), 1000, 1400))
    ok, caused = legal_duty(duty(day(1), 400, 700), tl, POLICY, no_transfer)
    assert not ok
    assert any(f.rule_id == "WR_DAILY_REST" for f in caused)


def test_legal_duty_accepts_clean():
    ok, caused = legal_duty(duty(day(1), 600, 800), timeline(), POLICY, no_transfer)
    assert ok and caused == ()


def f(rule, measured, d=day(0), driver="d1"):
    return WorkRuleFinding(rule, "legal", driver, d, (), measured, None, "s", {}, "k")


def test_caused_by():
    old = [f("A", 5), f("B", 5)]
    new = [f("A", 5), f("B", 9), f("C", 1), f("A", 1, d=day(1))]
    assert [(x.rule_id, x.service_date) for x in caused_by(new, old)] == [("B", day(0)), ("C", day(0)), ("A", day(1))]
    assert caused_by([f("A", None)], [f("A", None)]) == ()
    assert caused_by([f("A", 1)], [f("A", None)]) != ()


def test_latest_end_ignores_draft_duties():
    d = duty(day(2), 480, 900)
    draft = Duty(d.driver_id, d.service_date, d.trips, "draft")
    assert budget(timeline(draft)).latest_end_minutes == 2880
