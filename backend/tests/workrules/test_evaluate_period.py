from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.workrules.evaluate import evaluate
from app.domain.workrules.findings import caused_by
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import Baseline, DriverProfile, DriverTimeline, Duty, DutyTrip

POLICY = build_policy({}, [], 0)
WARN = build_policy({}, ["overnight_rest_day", "no_consecutive_overnight", "shift_rotation"], 0)
MON = date(2026, 11, 9)
ATHENS = ZoneInfo("Europe/Athens")


def day(n):
    return MON + timedelta(days=n)


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


def at(d, minute):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(minutes=minute)


def local(d, minute):
    return datetime(d.year, d.month, d.day, tzinfo=ATHENS) + timedelta(minutes=minute)


def trip(tid, start, end, destination="A", long_route=False):
    return DutyTrip(tid, start, end, "A", destination, True, True, "V1", None, False, long_route)


def duty(d, *spans, destination="A", emergency=False, clock=at, long_route=False):
    trips = tuple(
        trip(f"{d.isoformat()}-{i}", clock(d, s), clock(d, e), destination if i == len(spans) - 1 else "A", long_route)
        for i, (s, e) in enumerate(spans)
    )
    return Duty("d1", d, trips, "published", emergency)


def timeline(*duties, known_from=MON, baseline=None, prof=None):
    return DriverTimeline("d1", prof or profile(), tuple(duties), baseline, known_from, {})


def baseline(**kw):
    base = dict(
        as_of=day(-1),
        overtime_minutes=0,
        last_duty_end=None,
        last_weekly_rest_end=None,
        last_weekly_rest_at_base=True,
        owed_rest_minutes=0,
    )
    base.update(kw)
    return Baseline(**base)


def no_transfer(a, b):
    return 0


def run(tl, first, last=None, policy=POLICY):
    return evaluate(tl, policy, (first, last or first), no_transfer)


def only(findings, rule_id):
    return [f for f in findings if f.rule_id == rule_id]


def test_rest_11h_blocks():
    tl = timeline(
        duty(day(0), (1180, 1320)),
        duty(day(1), (490, 900)),
        duty(day(2), (130, 400)),
    )
    f = only(run(tl, day(0), day(2)), "WR_DAILY_REST")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date, f[0].measured, f[0].limit) == ("legal", day(2), 660, 720)
    assert f[0].source == "PD 54/1998 Art. 5(2)"
    short = timeline(duty(day(0), (1180, 1320)), duty(day(1), (430, 600)))
    g = only(run(short, day(1)), "WR_DAILY_REST")
    assert len(g) == 1 and (g[0].measured, g[0].limit) == (540, 600)


def test_rest_10h_once_ok_twice_blocks():
    once = timeline(duty(day(0), (1180, 1320)), duty(day(1), (490, 700)))
    assert not only(run(once, day(0), day(6)), "WR_DAILY_REST")
    twice = timeline(
        duty(day(0), (1180, 1320)),
        duty(day(1), (490, 700)),
        duty(day(3), (1180, 1320)),
        duty(day(4), (490, 700)),
    )
    f = only(run(twice, day(0), day(6)), "WR_DAILY_REST")
    assert [(x.service_date, x.measured, x.limit) for x in f] == [(day(4), 600, 720)]


def regular(d):
    return duty(d, (400, 600), (800, 1100))


def uncompensated(last_day):
    return timeline(
        duty(day(0), (1200, 1320)),
        duty(day(1), (490, 700), (900, 1100)),
        *(regular(day(n)) for n in range(2, last_day + 1)),
    )


def test_reduced_rest_uncompensated():
    f = only(run(uncompensated(13), day(0), day(13)), "WR_REDUCED_REST_COMPENSATION")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date, f[0].measured, f[0].limit) == ("legal", day(13), 730, 840)


def test_compensation_skipped_when_following_week_unknown():
    assert not only(run(uncompensated(12), day(0), day(13)), "WR_REDUCED_REST_COMPENSATION")


def test_rest_across_dst_spring():
    sat, sun = date(2026, 3, 28), date(2026, 3, 29)
    wed, thu = date(2026, 3, 25), date(2026, 3, 26)
    tl = timeline(
        duty(wed, (1200, 1320), clock=local),
        duty(thu, (490, 700), clock=local),
        duty(sat, (1200, 1320), clock=local),
        duty(sun, (610, 800), clock=local),
        known_from=date(2026, 3, 23),
    )
    f = only(run(tl, sun), "WR_DAILY_REST")
    assert len(f) == 1
    assert (f[0].measured, f[0].limit) == (660, 720)


def test_weekly_work_46h_blocks():
    tl = timeline(*(duty(day(n), (360, 902)) for n in range(5)))
    f = only(run(tl, day(0), day(6)), "WR_WEEKLY_WORK")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date, f[0].measured, f[0].limit) == ("legal", day(4), 2760, 2700)


def test_six_workdays_without_weekly_rest():
    six = [duty(day(n), (360, 480)) for n in range(6)]
    f = only(run(timeline(*six), day(0), day(6)), "WR_WEEKLY_REST")
    assert len(f) == 1
    assert (f[0].service_date, f[0].measured, f[0].limit) == (day(5), 6, 5)
    assert f[0].hint.get("partial") == "true"
    known = timeline(*six, baseline=baseline(last_weekly_rest_end=at(day(0), 0)))
    g = only(run(known, day(0), day(6)), "WR_WEEKLY_REST")
    assert len(g) == 1 and "partial" not in g[0].hint
    five = timeline(*six[:5], duty(day(7), (360, 480)))
    assert not only(run(five, day(0), day(7)), "WR_WEEKLY_REST")


def test_weekly_rest_away_from_base():
    tl = timeline(duty(day(0), (360, 480), destination="B"), duty(day(3), (360, 480)))
    f = only(run(tl, day(0), day(6)), "WR_WEEKLY_REST_BASE")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date) == ("legal", day(0))
    near = timeline(duty(day(0), (360, 480), destination="B"), duty(day(1), (360, 480)))
    assert not only(run(near, day(0), day(6)), "WR_WEEKLY_REST_BASE")


def four_week_pattern(skip=()):
    first = MON - timedelta(days=21)
    days = [first + timedelta(days=w * 7 + d) for w in range(4) for d in range(2, 7)]
    return timeline(*(duty(d, (360, 480)) for d in days if d not in skip), known_from=first)


def test_no_sunday_off_in_four_weeks():
    f = only(run(four_week_pattern(), day(0), day(6)), "WR_SUNDAY_REST")
    assert {x.service_date for x in f} == {day(2), day(3), day(4), day(5), day(6)}
    assert all(x.kind == "legal" for x in f)
    assert not only(run(four_week_pattern(skip={MON - timedelta(days=8)}), day(0), day(6)), "WR_SUNDAY_REST")


def test_sunday_rest_skipped_without_history():
    tl = four_week_pattern()
    short = replace(tl, duties=tl.duties[5:], known_from=MON - timedelta(days=14))
    assert not only(run(short, day(0), day(6)), "WR_SUNDAY_REST")


def test_fourth_interruption_in_week():
    tl = timeline(*(duty(day(n), (360, 420), (500, 560)) for n in range(4)))
    f = only(run(tl, day(0), day(6)), "WR_INTERRUPTIONS")
    assert len(f) == 1
    assert (f[0].service_date, f[0].measured, f[0].limit) == (day(3), 4, 3)


def test_overtime_year_uses_baseline():
    tl = timeline(duty(day(0), (360, 890)), baseline=baseline(overtime_minutes=7150))
    f = only(run(tl, day(0)), "WR_OVERTIME_YEAR")
    assert len(f) == 1
    assert (f[0].kind, f[0].measured, f[0].limit) == ("legal", 7210, 7200)
    before = timeline(duty(day(0), (360, 890)), baseline=baseline(overtime_minutes=7150, as_of=day(0)))
    assert not only(run(before, day(0)), "WR_OVERTIME_YEAR")


def test_emergency_overtime_only_absolute():
    tl = timeline(duty(day(0), (360, 890), emergency=True), baseline=baseline(overtime_minutes=7150))
    assert not only(run(tl, day(0)), "WR_OVERTIME_YEAR")
    assert not only(run(tl, day(0)), "WR_OVERTIME_YEAR_ABSOLUTE")
    high = timeline(duty(day(0), (360, 890), emergency=True), baseline=baseline(overtime_minutes=10790))
    f = only(run(high, day(0)), "WR_OVERTIME_YEAR_ABSOLUTE")
    assert len(f) == 1 and (f[0].measured, f[0].limit) == (10850, 10800)


def test_overnight_then_work_next_day_warning():
    tl = timeline(duty(day(0), (360, 480), destination="B"), duty(day(1), (360, 480)))
    f = only(run(tl, day(0), day(1), WARN), "WR_OVERNIGHT_REST_DAY")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date, f[0].source) == ("warning", day(1), "Company rule")
    assert not only(run(tl, day(0), day(1)), "WR_OVERNIGHT_REST_DAY")


def test_consecutive_overnights_warning():
    tl = timeline(duty(day(0), (360, 480), destination="B"), duty(day(1), (360, 480), destination="B"))
    f = only(run(tl, day(0), day(1), WARN), "WR_OVERNIGHT_CONSECUTIVE")
    assert [(x.kind, x.service_date) for x in f] == [("warning", day(1))]


def test_overnight_not_allowed_warning():
    d = duty(day(0), (360, 480), destination="B")
    f = only(run(timeline(d, prof=profile(overnight_allowed=False)), day(0)), "WR_OVERNIGHT_NOT_ALLOWED")
    assert len(f) == 1
    assert (f[0].kind, f[0].source) == ("warning", "Driver restriction")
    assert not only(run(timeline(d), day(0)), "WR_OVERNIGHT_NOT_ALLOWED")


def test_shift_rotation_uses_local_clock():
    tl = timeline(duty(day(2), (760, 900)), duty(day(8), (760, 900)), duty(day(9), (760, 900)))
    f = only(run(tl, day(0), day(13), WARN), "WR_SHIFT_ROTATION")
    assert len(f) == 1
    assert (f[0].kind, f[0].service_date, f[0].source) == ("warning", day(8), "PD 54/1998 Art. 8")
    assert not only(evaluate(tl, WARN, (day(0), day(13)), no_transfer, tz="UTC"), "WR_SHIFT_ROTATION")
    assert not only(run(tl, day(0), day(13)), "WR_SHIFT_ROTATION")


def test_no_history_no_baseline_is_info_not_block():
    f = run(timeline(duty(day(0), (360, 480))), day(0))
    assert [(x.rule_id, x.kind, x.service_date) for x in f] == [("WR_HISTORY_UNKNOWN", "info", day(0))]
    known = timeline(duty(day(0), (360, 480)), known_from=day(-28))
    assert not run(known, day(0))


def test_baseline_last_duty_end_drives_rest():
    tl = timeline(duty(day(0), (360, 480)), baseline=baseline(last_duty_end=at(day(-1), 1320)))
    f = only(run(tl, day(0)), "WR_DAILY_REST")
    assert len(f) == 1
    assert (f[0].service_date, f[0].measured, f[0].limit) == (day(0), 470, 600)
    assert not only(run(timeline(duty(day(0), (360, 480))), day(0)), "WR_DAILY_REST")


def test_weekly_rest_streak_seeded_from_baseline():
    seed = baseline(last_weekly_rest_end=at(day(-4), 0), last_duty_end=at(day(-1), 1200))
    tl = timeline(*(duty(day(n), (360, 480)) for n in range(3)), baseline=seed)
    f = only(run(tl, day(0), day(6)), "WR_WEEKLY_REST")
    assert [(x.service_date, x.measured, x.limit) for x in f] == [(day(1), 6, 5), (day(2), 7, 5)]
    assert all("partial" not in x.hint for x in f)


def test_compensation_counts_rest_starting_before_week_end():
    tl = timeline(
        duty(day(5), (1200, 1260)),
        duty(day(6), (430, 1100)),
        *(regular(day(n)) for n in range(7, 10)),
        regular(day(14)),
    )
    assert not only(run(tl, day(0), day(14)), "WR_REDUCED_REST_COMPENSATION")


def caused(tl, d, draft, rule_id):
    focus = (d, d + timedelta(days=7))
    with_draft = evaluate(tl.with_day(d, draft), POLICY, focus, no_transfer)
    without_draft = evaluate(tl.with_day(d, None), POLICY, focus, no_transfer)
    return only(caused_by(with_draft, without_draft), rule_id), only(with_draft, rule_id)


def overtime_duty(d):
    return duty(d, (360, 890))


def test_overtime_already_over_baseline_draft_adds_more_blocks():
    tl = timeline(overtime_duty(day(0)), baseline=baseline(overtime_minutes=7150))
    new, _ = caused(tl, day(1), overtime_duty(day(1)), "WR_OVERTIME_YEAR")
    assert [(f.service_date, f.measured) for f in new] == [(day(1), 7270)]


def test_overtime_prior_aggregate_over_cap_draft_adds_more_blocks():
    tl = replace(timeline(known_from=day(-28)), prior_year=MON.year, prior_overtime=7300)
    new, _ = caused(tl, day(0), overtime_duty(day(0)), "WR_OVERTIME_YEAR")
    assert [(f.service_date, f.measured) for f in new] == [(day(0), 7360)]
    both = replace(tl, baseline=baseline(overtime_minutes=100))
    new, _ = caused(both, day(0), overtime_duty(day(0)), "WR_OVERTIME_YEAR")
    assert [(f.service_date, f.measured) for f in new] == [(day(0), 7460)]


def test_absolute_overtime_already_over_draft_adds_more_blocks():
    tl = timeline(overtime_duty(day(0)), baseline=baseline(overtime_minutes=10790))
    new, _ = caused(tl, day(1), duty(day(1), (360, 890), emergency=True), "WR_OVERTIME_YEAR_ABSOLUTE")
    assert [(f.service_date, f.measured) for f in new] == [(day(1), 10910)]


def test_overtime_already_over_draft_adds_nothing_is_preexisting():
    tl = timeline(overtime_duty(day(2)), baseline=baseline(overtime_minutes=7300))
    new, seen = caused(tl, day(0), duty(day(0), (360, 480)), "WR_OVERTIME_YEAR")
    assert not new
    assert [(f.service_date, f.measured) for f in seen] == [(day(2), 7360)]


def test_weekly_work_already_over_draft_adds_more_blocks():
    tl = timeline(*(duty(day(n), (360, 962)) for n in range(5)))
    new, _ = caused(tl, day(5), duty(day(5), (360, 600)), "WR_WEEKLY_WORK")
    assert [f.service_date for f in new] == [day(5)]
    assert new[0].measured > 3010


def test_weekly_work_already_over_draft_next_week_is_not_caused():
    tl = timeline(*(duty(day(n), (360, 962)) for n in range(5)), duty(day(9), (360, 600)))
    new, _ = caused(tl, day(7), duty(day(7), (360, 600)), "WR_WEEKLY_WORK")
    assert not new


def test_weekly_driving_already_over_draft_adds_more_blocks():
    tl = timeline(*(duty(day(n), (360, 630), (675, 1005), long_route=True) for n in range(6)))
    new, _ = caused(tl, day(6), duty(day(6), (360, 480), long_route=True), "WR_WEEKLY_DRIVING")
    assert [f.service_date for f in new] == [day(6)]


def test_weekly_driving_already_over_draft_without_long_route_is_preexisting():
    tl = timeline(*(duty(day(n), (360, 630), (675, 1005), long_route=True) for n in range(6)))
    new, _ = caused(tl, day(6), duty(day(6), (360, 480)), "WR_WEEKLY_DRIVING")
    assert not new


def test_interruptions_already_over_draft_adds_more_blocks():
    tl = timeline(*(duty(day(n), (360, 420), (500, 560)) for n in range(4)))
    new, _ = caused(tl, day(4), duty(day(4), (360, 420), (500, 560)), "WR_INTERRUPTIONS")
    assert {f.hint.get("measure") for f in new} >= {"count"}
    assert all(f.service_date == day(4) for f in new)
    none, _ = caused(tl, day(4), duty(day(4), (360, 560)), "WR_INTERRUPTIONS")
    assert not none


def test_weekly_rest_streak_already_over_draft_extends_blocks():
    tl = timeline(*(duty(day(n), (360, 480)) for n in range(6)), known_from=day(-28))
    new, _ = caused(tl, day(6), duty(day(6), (360, 480)), "WR_WEEKLY_REST")
    assert [(f.service_date, f.measured) for f in new] == [(day(6), 7)]


NO_SPLIT = profile(split_shift_allowed=False)


def morning_evening(d, gap):
    return duty(d, (360, 600), (600 + gap, 600 + gap + 160))


def test_rest_length_gap_ends_the_duty():
    tl = timeline(morning_evening(day(0), 640), known_from=day(-28), prof=NO_SPLIT)
    f = run(tl, day(0))
    assert not only(f, "WR_SPLIT_SHIFT")
    assert not only(f, "WR_INTERRUPTIONS")
    assert not only(f, "WR_DAILY_REST")


def test_gap_just_below_reduced_rest_is_interruption():
    tl = timeline(morning_evening(day(0), 609), known_from=day(-28), prof=NO_SPLIT)
    f = run(tl, day(0))
    assert [x.measured for x in only(f, "WR_SPLIT_SHIFT")] == [1]
    assert not only(f, "WR_DAILY_REST")


def test_stricter_reduced_rest_keeps_gap_as_interruption():
    strict = build_policy({"daily_rest_reduced": 660}, [], 1)
    tl = timeline(morning_evening(day(0), 640), known_from=day(-28), prof=NO_SPLIT)
    assert only(run(tl, day(0), policy=strict), "WR_SPLIT_SHIFT")


def test_second_same_day_rest_in_week_uses_up_reduced_allowance():
    tl = timeline(morning_evening(day(0), 640), morning_evening(day(2), 640), known_from=day(-28))
    f = only(run(tl, day(0), day(6)), "WR_DAILY_REST")
    assert [(x.service_date, x.measured, x.limit) for x in f] == [(day(2), 630, 720)]
    assert not only(run(tl, day(0), day(6)), "WR_INTERRUPTIONS")


def test_split_day_counts_as_one_working_day():
    six = [morning_evening(day(n), 640) if n == 2 else duty(day(n), (360, 480)) for n in range(5)]
    tl = timeline(*six, baseline=baseline(last_weekly_rest_end=at(day(0), 0)))
    assert not only(run(tl, day(0), day(6)), "WR_WEEKLY_REST")


def test_with_day_replaces_a_split_day():
    tl = timeline(regular(day(0)), morning_evening(day(1), 640), duty(day(2), (300, 480)), known_from=day(-28))
    assert only(run(tl, day(2)), "WR_DAILY_REST")
    plain = tl.with_day(day(1), duty(day(1), (360, 600)))
    assert not only(run(plain, day(2)), "WR_DAILY_REST")
    assert not only(run(tl.with_day(day(1), None), day(2)), "WR_DAILY_REST")
