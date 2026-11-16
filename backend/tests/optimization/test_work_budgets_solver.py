from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.optimization.contracts import Assignment, ResourceSnapshot, SolverConfig, SolverProblem, TripSnapshot
from app.domain.optimization.cv_bounded import BoundedCustomSolver, CVBoundedV1, DutyRules, _duty, _timeline, fill_gaps
from app.domain.optimization.cv_legacy import problem_snapshot_to_legacy_dict
from framework.problem import Problem
from app.domain.verification.rules import Severity
from app.domain.verification.verifier import HardRuleVerifier
from app.domain.workrules.budget import DriverDayBudget, driver_budget, legal_duty
from app.domain.workrules.loader import WorkContext, attach_work_context
from app.domain.workrules.policy import build_policy
from app.domain.workrules.timeline import DriverProfile, DriverTimeline, Duty, DutyTrip

ZONE = ZoneInfo("Europe/Athens")
DAY = date(2026, 6, 2)
POLICY = build_policy({}, [], 0)
CONFIG = SolverConfig(seed=3, time_limit_seconds=20, iterations=2)


def origin(day):
    return datetime.combine(day, time(), tzinfo=ZONE).astimezone(timezone.utc)


def trip(trip_id, start_station, end_station, start, end):
    return TripSnapshot(trip_id, start_station, end_station, start, end, end - start, route_id=7,
                        origin_is_depot=start_station == "A", destination_is_depot=end_station == "A")


def published(driver, day, start, end):
    leg = DutyTrip(f"P{driver}{day}", origin(day) + timedelta(minutes=start), origin(day) + timedelta(minutes=end),
                   "A", "A", True, True, "V9", 7, False, True)
    return Duty(driver, day, (leg,), "published")


def context(problem, *duties):
    profile = DriverProfile("A", True, True, False, frozenset(), frozenset())
    drivers = {r.driver_id for r in problem.resources}
    timelines = {
        d: DriverTimeline(d, profile, tuple(x for x in duties if x.driver_id == d), None, DAY - timedelta(days=60), {})
        for d in drivers
    }
    return WorkContext(
        policy=POLICY,
        timelines=timelines,
        overrides=frozenset(),
        service_date=DAY,
        day_origin_utc=origin(DAY),
        transfers={("A", "B"): 30, ("B", "A"): 30},
        trip_routes={t.id: (7, False, True) for t in problem.trips},
        depots=frozenset({"A"}),
    )


def problem(trips, drivers=("1", "2")):
    resources = tuple(ResourceSnapshot(f"PAIR_{d}", d, f"V{d}", "A") for d in drivers)
    return SolverProblem("P", "1", DAY, tuple(trips), resources, (), ("A", "B"), ((0, 30), (30, 0)))


def budget(driver, **values):
    base = dict(driver_id=driver, earliest_start_minutes=0, latest_end_minutes=2880, max_work_minutes=600,
                max_long_route_driving_minutes=600, continuous_driving_minutes=270, overnight_allowed=True,
                split_shift_allowed=True, must_return_to_base=False, forbidden_route_ids=(),
                preferred_route_ids=(), forbidden_vehicle_route_ids={})
    return DriverDayBudget(**{**base, **values}).to_dict()


def test_attach_work_context_sets_policy_and_budgets():
    built = problem((trip("T1", "A", "A", 480, 540),), drivers=("1", "2", "1"))
    built = SolverProblem(built.problem_id, built.tenant_id, DAY, built.trips,
                          built.resources[:2] + (ResourceSnapshot("PAIR_3", "1", "V3", "A"),), (), built.stations, built.transfer_matrix)
    ctx = context(built, published("1", DAY - timedelta(days=1), 1260, 1380))
    attached = attach_work_context(built, ctx)
    assert attached.work_policy == POLICY.to_dict()
    assert [b["driver_id"] for b in attached.driver_budgets] == ["1", "2"]
    expected = driver_budget(ctx.timelines["1"], POLICY, DAY, ctx.day_origin_utc, ctx.transfer_minutes).to_dict()
    assert attached.driver_budgets[0] == expected
    assert expected["earliest_start_minutes"] >= 1380 + 720 - 1440
    assert attached.trips == built.trips and attached.resources == built.resources


def test_cv_respects_earliest_start():
    trips = (trip("T1", "A", "A", 360, 420), trip("T2", "A", "A", 480, 540), trip("T3", "A", "A", 660, 720))
    built = problem(trips)
    built = SolverProblem(built.problem_id, built.tenant_id, DAY, trips, built.resources, (), built.stations, built.transfer_matrix,
                          work_policy=POLICY.to_dict(), driver_budgets=(budget("1", earliest_start_minutes=600), budget("2")))
    result = CVBoundedV1().solve(built, CONFIG)
    early = [a for a in result.assignments if a.resource_id == "PAIR_1" and a.start_minutes < 600]
    assert early == []
    assert {a.trip_id for a in result.assignments} | set(result.unassigned_trip_ids) == {"T1", "T2", "T3"}


def test_cv_result_has_no_legal_findings_or_leaves_unassigned():
    trips = (
        trip("T1", "A", "B", 360, 480),
        trip("T2", "B", "A", 500, 620),
        trip("T3", "A", "A", 640, 940),
        trip("T4", "A", "B", 700, 820),
        trip("T5", "B", "A", 840, 960),
        trip("T6", "A", "B", 1000, 1100),
    )
    built = problem(trips, drivers=("1", "2", "3"))
    ctx = context(built, published("1", DAY - timedelta(days=1), 1260, 1380))
    attached = attach_work_context(built, ctx)
    result = CVBoundedV1().solve(attached, CONFIG)
    assigned = {a.trip_id for a in result.assignments}
    assert assigned.isdisjoint(result.unassigned_trip_ids)
    assert assigned | set(result.unassigned_trip_ids) == {t.id for t in trips}
    assert "T3" in result.unassigned_trip_ids
    assert assigned
    report = HardRuleVerifier().verify(attached, result, ctx)
    legal = [v for v in report.violations if v.kind == "legal" and v.severity == Severity.ERROR]
    assert legal == []


def test_cv_drops_work_beyond_the_driver_budget():
    trips = (trip("T1", "A", "A", 360, 480), trip("T2", "A", "A", 500, 620))
    built = problem(trips, drivers=("1",))
    built = SolverProblem(built.problem_id, built.tenant_id, DAY, trips, built.resources, (), built.stations, built.transfer_matrix,
                          work_policy=POLICY.to_dict(), driver_budgets=(budget("1", max_work_minutes=200),))
    result = CVBoundedV1().solve(built, CONFIG)
    assert len(result.assignments) == 1 and len(result.unassigned_trip_ids) == 1


def with_budgets(trips, *budgets):
    built = problem(trips, drivers=tuple(b["driver_id"] for b in budgets))
    return SolverProblem(built.problem_id, built.tenant_id, DAY, trips, built.resources, (), built.stations, built.transfer_matrix,
                         work_policy=POLICY.to_dict(), driver_budgets=budgets)


def duties(built, result):
    resources = {r.resource_id: r for r in built.resources}
    grouped = {}
    for a in sorted(result.assignments, key=lambda a: a.start_minutes):
        grouped.setdefault(resources[a.resource_id].driver_id, []).append((a.resource_id, a.trip_id))
    return grouped


def assert_no_rule_findings(built, result):
    budgets = {b["driver_id"]: DriverDayBudget.from_dict(b) for b in built.driver_budgets}
    resources = {r.resource_id: r for r in built.resources}
    for driver, legs in duties(built, result).items():
        duty = _duty(built, driver, resources, legs)
        timeline = _timeline(built, driver, "A", budgets[driver])
        ok, caused = legal_duty(duty, timeline, POLICY, lambda a, b: 0 if a == b else 30, kinds=("legal", "warning"))
        assert ok, caused


def test_cv_never_leaves_must_return_driver_away_from_base():
    trips = (trip("T1", "A", "B", 360, 480), trip("T2", "B", "A", 500, 620), trip("T3", "A", "B", 700, 820))
    built = with_budgets(trips, budget("1", must_return_to_base=True))
    result = CVBoundedV1().solve(built, CONFIG)
    trip_map = {t.id: t for t in trips}
    for legs in duties(built, result).values():
        assert trip_map[legs[-1][1]].end_station == "A"
    assert {"T1", "T2"} <= {a.trip_id for a in result.assignments}
    assert_no_rule_findings(built, result)


def test_cv_never_gives_split_duty_to_driver_without_split_shifts():
    trips = (trip("T1", "A", "A", 360, 480), trip("T2", "A", "A", 900, 1000))
    built = with_budgets(trips, budget("1", split_shift_allowed=False))
    result = CVBoundedV1().solve(built, CONFIG)
    assert len(result.assignments) == 1 and len(result.unassigned_trip_ids) == 1
    assert_no_rule_findings(built, result)


def test_cv_covers_trip_with_another_driver_when_first_choice_breaks_rules():
    trips = (trip("T1", "A", "B", 360, 480),)
    built = with_budgets(trips, budget("1", must_return_to_base=True), budget("2"))
    result = CVBoundedV1().solve(built, CONFIG)
    assert [(a.resource_id, a.trip_id) for a in result.assignments] == [("PAIR_2", "T1")]
    assert_no_rule_findings(built, result)


def test_uncovered_trip_is_added_to_a_duty_it_fits():
    trips = (trip("T1", "A", "B", 360, 480), trip("T2", "B", "A", 500, 620))
    built = with_budgets(trips, budget("1"))
    solver = BoundedCustomSolver()
    solver.set_problem(Problem(problem_snapshot_to_legacy_dict(built)))
    solver.rules = DutyRules(built)
    first = Assignment("PAIR_1", "T1", 360, 480, "A", "B")
    filled = fill_gaps(solver, built, [first])
    assert [(a.resource_id, a.trip_id) for a in filled] == [("PAIR_1", "T1"), ("PAIR_1", "T2")]
