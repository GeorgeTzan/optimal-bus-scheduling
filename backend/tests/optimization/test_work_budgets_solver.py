from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.optimization.contracts import ResourceSnapshot, SolverConfig, SolverProblem, TripSnapshot
from app.domain.optimization.cv_bounded import CVBoundedV1
from app.domain.verification.rules import Severity
from app.domain.verification.verifier import HardRuleVerifier
from app.domain.workrules.budget import DriverDayBudget, driver_budget
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
