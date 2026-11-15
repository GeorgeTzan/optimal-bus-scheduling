from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.optimization.contracts import Assignment, ResourceSnapshot, SolverProblem, TripSnapshot
from app.domain.verification.rules import RuleSet, Severity
from app.domain.verification.verifier import HardRuleVerifier, verify_schedule
from app.domain.workrules.evaluate import evaluate
from app.domain.workrules.loader import WorkContext
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import DriverProfile, DriverTimeline, Duty, DutyTrip

ZONE = ZoneInfo("Europe/Athens")
DAY = date(2026, 6, 2)
POLICY = build_policy({}, [], 0)


def origin(day):
    return datetime.combine(day, time(), tzinfo=ZONE).astimezone(timezone.utc)


def published(day, start, end, trip_id=None, destination="B"):
    trip = DutyTrip(trip_id or f"P{day}", origin(day) + timedelta(minutes=start), origin(day) + timedelta(minutes=end),
                    "A", destination, True, destination == "A", "V1", 7, False, True)
    return Duty("1", day, (trip,), "published")


def worked(day, *spans):
    trips = tuple(
        DutyTrip(f"P{day}-{i}", origin(day) + timedelta(minutes=a), origin(day) + timedelta(minutes=b),
                 "A" if i % 2 == 0 else "B", "B" if i % 2 == 0 else "A", i % 2 == 0, i % 2 == 1, "V1", 7, False, True)
        for i, (a, b) in enumerate(spans)
    )
    return Duty("1", day, trips, "published")


def context(*duties, overrides=(), vehicle_routes=None, emergency=(), delays=None, drivers=("1",)):
    profile = DriverProfile("A", True, True, False, frozenset(), frozenset())
    timelines = {
        d: DriverTimeline(d, profile, tuple(sorted((x for x in duties if x.driver_id == d), key=lambda x: x.service_date)), None,
                          DAY - timedelta(days=60), vehicle_routes or {})
        for d in drivers
    }
    return WorkContext(
        policy=POLICY,
        timelines=timelines,
        overrides=frozenset(overrides),
        service_date=DAY,
        day_origin_utc=origin(DAY),
        transfers={("A", "B"): 30, ("B", "A"): 30},
        trip_routes={"T1": (7, False, True), "T2": (7, False, True)},
        depots=frozenset({"A"}),
        emergency_drivers=frozenset(emergency),
        delays=delays or {},
    )


def problem(*spans):
    trips = tuple(TripSnapshot(f"T{i + 1}", "A" if i % 2 == 0 else "B", "B" if i % 2 == 0 else "A", a, b, b - a,
                               allowed_bus_types=("01",)) for i, (a, b) in enumerate(spans))
    resources = (ResourceSnapshot("R1", "1", "V1", "A"),)
    built = SolverProblem("P", "1", DAY, trips, resources, (), ("A", "B"), ((0, 30), (30, 0)))
    return built, [Assignment("R1", t.id, t.start_minutes, t.end_minutes, t.start_station, t.end_station) for t in trips]


def work(report, rule_id):
    return [v for v in report.violations if v.rule_id == rule_id]


def test_rest_breach_is_error():
    built, assignments = problem((360, 420))
    report = HardRuleVerifier().verify(built, assignments, context(published(DAY - timedelta(days=1), 1270, 1330)))
    [rest] = work(report, "WR_DAILY_REST")
    assert rest.severity == Severity.ERROR and not rest.preexisting and not report.valid
    assert rest.entity_type == "Driver" and rest.entity_ids == ["1", "T1"]
    assert rest.service_date == DAY.isoformat() and rest.measured < rest.limit and rest.kind == "legal"
    assert rest.finding_key.startswith("WR_DAILY_REST|1|2026-06-02|T1|")
    assert rest.message_key == "workrules.WR_DAILY_REST" and rest.source
    assert datetime.fromisoformat(rest.hint["rest_until"]).tzinfo is not None
    assert report.rule_version == "v2.5-workrules+gr-pd54-1998+eu561-2026-11+company-v0"


def test_preexisting_violation_is_warning():
    built, assignments = problem((480, 540))
    ctx = context(published(DAY + timedelta(days=1), 1270, 1330), published(DAY + timedelta(days=2), 360, 420))
    report = HardRuleVerifier().verify(built, assignments, ctx)
    [rest] = work(report, "WR_DAILY_REST")
    assert rest.severity == Severity.WARNING and rest.preexisting
    assert rest.service_date == (DAY + timedelta(days=2)).isoformat()
    assert report.valid


def test_draft_worsens_existing_is_error():
    days = [DAY + timedelta(days=n) for n in (-1, 1, 2, 3, 4)]
    ctx = context(*(worked(d, (420, 660), (705, 960)) for d in days))
    built, assignments = problem((480, 540))
    focus = (DAY, DAY + timedelta(days=7))
    [before] = [f for f in evaluate(ctx.timelines["1"], POLICY, focus, ctx.transfer_minutes) if f.rule_id == "WR_WEEKLY_WORK"]
    report = HardRuleVerifier().verify(built, assignments, ctx)
    [weekly] = work(report, "WR_WEEKLY_WORK")
    assert weekly.severity == Severity.ERROR and not weekly.preexisting
    assert weekly.service_date == before.service_date.isoformat() and weekly.measured > before.measured
    assert not report.valid


def test_overridden_warning_removed():
    built, assignments = problem((480, 540))
    plain = HardRuleVerifier().verify(built, assignments, context(vehicle_routes={"V1": frozenset({7})}))
    [warning] = work(plain, "WR_FORBIDDEN_VEHICLE_ROUTE")
    assert warning.severity == Severity.WARNING and plain.valid
    overridden = HardRuleVerifier().verify(built, assignments, context(overrides={warning.finding_key}, vehicle_routes={"V1": frozenset({7})}))
    assert work(overridden, "WR_FORBIDDEN_VEHICLE_ROUTE") == []


def test_draft_breaks_next_day_rest_reported_on_draft():
    built, assignments = problem((1270, 1330))
    ctx = context(published(DAY + timedelta(days=1), 360, 420, "NEXT"))
    report = HardRuleVerifier().verify(built, assignments, ctx)
    [rest] = work(report, "WR_DAILY_REST")
    assert rest.severity == Severity.ERROR and not rest.preexisting and not report.valid
    assert rest.service_date == (DAY + timedelta(days=1)).isoformat() and rest.entity_ids == ["1", "NEXT"]
    assert "2026-06-02" in rest.message


def test_emergency_duty_allows_eleven_hours():
    built, assignments = problem((300, 540), (585, 825), (870, 920))
    normal = HardRuleVerifier().verify(built, assignments, context())
    [daily] = work(normal, "WR_DAILY_WORK")
    assert daily.severity == Severity.ERROR and 600 < daily.measured <= 660
    assert work(HardRuleVerifier().verify(built, assignments, context(emergency={"1"})), "WR_DAILY_WORK") == []


def test_no_work_context_keeps_old_behaviour():
    built, assignments = problem((360, 420))
    report = verify_schedule(built, assignments)
    assert report.valid and report.violations == [] and report.rule_version == "v2.5-workrules"
    assert HardRuleVerifier().verify(built, assignments).rule_version == RuleSet().version == "v2.5-workrules"
    for retired in ("max_continuous_driving_minutes", "max_daily_driving_minutes", "min_break_minutes"):
        assert not hasattr(RuleSet(), retired)


def test_emergency_is_per_driver():
    spans = ((300, 540), (585, 825), (870, 920))
    trips = tuple(TripSnapshot(f"{r}{i}", "A" if i % 2 == 0 else "B", "B" if i % 2 == 0 else "A", a, b, b - a)
                  for r in "AB" for i, (a, b) in enumerate(spans))
    resources = (ResourceSnapshot("RA", "1", "V1", "A"), ResourceSnapshot("RB", "2", "V2", "A"))
    built = SolverProblem("P", "1", DAY, trips, resources, (), ("A", "B"), ((0, 30), (30, 0)))
    assignments = [Assignment("R" + t.id[0], t.id, t.start_minutes, t.end_minutes, t.start_station, t.end_station) for t in trips]
    report = HardRuleVerifier().verify(built, assignments, context(emergency={"1"}, drivers=("1", "2")))
    [daily] = work(report, "WR_DAILY_WORK")
    assert daily.entity_ids[0] == "2" and daily.severity == Severity.ERROR and 600 < daily.measured <= 660


def test_recorded_delay_shifts_draft_and_cascades():
    from app.domain.workrules.draft import draft_duties
    built, assignments = problem((300, 540), (585, 640))
    [first, second] = draft_duties(context(delays={"T1": 40}), built, assignments)["1"].trips
    assert first.end == origin(DAY) + timedelta(minutes=580) and second.start == origin(DAY) + timedelta(minutes=585)
    [first, second] = draft_duties(context(delays={"T1": 60}), built, assignments)["1"].trips
    assert second.start == first.end == origin(DAY) + timedelta(minutes=600) and second.end == second.start + timedelta(minutes=55)
    ctx = context(delays={"T1": 40})
    plain = HardRuleVerifier().verify(built, assignments, context())
    delayed = HardRuleVerifier().verify(built, assignments, ctx)
    assert not work(plain, "WR_CONTINUOUS_DRIVING")
    assert work(delayed, "WR_CONTINUOUS_DRIVING")[0].severity == Severity.ERROR


def test_prior_overtime_matches_full_history():
    from dataclasses import replace
    from app.domain.workrules.facts import duty_facts
    strict = build_policy({"overtime_year": 100}, [], 1)
    february = worked(date(2026, 2, 10), (420, 660), (705, 960))
    full = context(february)
    timeline = full.timelines["1"]
    minutes = duty_facts(february, timeline.profile, strict, full.transfer_minutes).overtime_minutes
    windowed = replace(timeline, duties=(), prior_year=2026, prior_overtime=minutes)
    built, assignments = problem((420, 660), (705, 960))
    focus = (DAY, DAY + timedelta(days=7))
    for prior in (timeline, windowed):
        found = [f for f in evaluate(prior.with_day(DAY, draft_duty(full, built, assignments)), strict, focus, full.transfer_minutes)
                 if f.rule_id == "WR_OVERTIME_YEAR"]
        assert [(f.service_date, f.measured) for f in found] == [(DAY, 2 * minutes)]


def draft_duty(work_context, built, assignments):
    from app.domain.workrules.draft import draft_duties
    return draft_duties(work_context, built, assignments)["1"]
