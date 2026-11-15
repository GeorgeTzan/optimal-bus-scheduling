from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from app.domain.workrules.facts import DutyFacts, duty_parts
from app.domain.workrules.findings import COMPANY, RESTRICTION, WorkRuleFinding
from app.domain.workrules.findings import finding as _finding
from app.domain.workrules.legal import LEGAL_LIMITS
from app.domain.workrules.period_rules import Item, period_findings
from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import DriverTimeline, Duty

HISTORY_DAYS = 28


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _extensions_used(
    timeline: DriverTimeline,
    duty: Duty,
    policy: WorkRulePolicy,
    transfer_minutes: Callable[[str, str], int | None],
) -> int:
    week = _week(duty.service_date)
    base = policy.value("daily_driving_eu")
    others = [d for d in timeline.duties if _week(d.service_date) == week]
    return sum(
        1
        for other, facts in duty_parts(others, timeline.profile, policy, transfer_minutes)
        if other.trips != duty.trips and facts.long_route_driving_minutes > base
    )


def _evaluate_duty(
    timeline: DriverTimeline,
    duty: Duty,
    facts: DutyFacts,
    policy: WorkRulePolicy,
    transfer_minutes: Callable[[str, str], int | None],
) -> list[WorkRuleFinding]:
    out: list[WorkRuleFinding] = []
    ids = tuple(t.trip_id for t in duty.trips)
    profile = timeline.profile

    work_id = "daily_work_emergency" if duty.emergency else "daily_work_max"
    work_limit = policy.value(work_id)
    if facts.work_minutes > work_limit:
        out.append(
            _finding("WR_DAILY_WORK", "legal", duty, ids, facts.work_minutes, work_limit, LEGAL_LIMITS[work_id].source)
        )

    continuous = policy.value("continuous_driving")
    if facts.longest_driving_without_break > continuous:
        needed = facts.longest_run_start + timedelta(minutes=continuous)
        out.append(
            _finding(
                "WR_CONTINUOUS_DRIVING",
                "legal",
                duty,
                ids,
                facts.longest_driving_without_break,
                continuous,
                LEGAL_LIMITS["continuous_driving"].source,
                {"break_needed_by": needed.astimezone(timezone.utc).isoformat()},
            )
        )

    if facts.urban and not facts.urban_break_taken:
        out.append(
            _finding("WR_URBAN_BREAK", "legal", duty, ids, 0, policy.value("urban_break"), LEGAL_LIMITS["urban_break"].source)
        )

    extended = policy.value("daily_driving_eu_extended")
    if _extensions_used(timeline, duty, policy, transfer_minutes) < policy.value("daily_driving_extensions_per_week"):
        driving_id, driving_limit = "daily_driving_eu_extended", extended
    else:
        driving_id, driving_limit = "daily_driving_eu", policy.value("daily_driving_eu")
    if facts.long_route_driving_minutes > driving_limit:
        out.append(
            _finding(
                "WR_DAILY_DRIVING",
                "legal",
                duty,
                ids,
                facts.long_route_driving_minutes,
                driving_limit,
                LEGAL_LIMITS[driving_id].source,
            )
        )

    if facts.interruptions > 0 and not profile.split_shift_allowed:
        out.append(_finding("WR_SPLIT_SHIFT", "warning", duty, ids, facts.interruptions, None, COMPANY))

    if profile.must_return_to_base and facts.ends_away_from_base:
        out.append(_finding("WR_MUST_RETURN_BASE", "warning", duty, ids, None, None, RESTRICTION))

    banned = tuple(t.trip_id for t in duty.trips if t.route_id in profile.forbidden_routes)
    if banned:
        out.append(_finding("WR_FORBIDDEN_DRIVER_ROUTE", "warning", duty, banned, None, None, RESTRICTION))

    vehicle = tuple(
        t.trip_id
        for t in duty.trips
        if t.route_id is not None and t.route_id in timeline.forbidden_vehicle_routes.get(t.vehicle_id, frozenset())
    )
    if vehicle:
        out.append(_finding("WR_FORBIDDEN_VEHICLE_ROUTE", "warning", duty, vehicle, None, None, RESTRICTION))

    return out


def evaluate(
    timeline: DriverTimeline,
    policy: WorkRulePolicy,
    focus: tuple[date, date],
    transfer_minutes: Callable[[str, str], int | None],
    *,
    tz: str = "Europe/Athens",
) -> tuple[WorkRuleFinding, ...]:
    items = [
        Item(d, facts, tuple(t.trip_id for t in d.trips))
        for d, facts in duty_parts(timeline.duties, timeline.profile, policy, transfer_minutes)
    ]
    items.sort(key=lambda i: i.facts.start)
    findings: list[WorkRuleFinding] = []
    for item in items:
        if focus[0] <= item.duty.service_date <= focus[1]:
            findings.extend(_evaluate_duty(timeline, item.duty, item.facts, policy, transfer_minutes))
    findings.extend(
        f
        for f in period_findings(timeline, items, policy, ZoneInfo(tz))
        if focus[0] <= f.service_date <= focus[1]
    )
    if timeline.baseline is None and focus[0] - timedelta(days=HISTORY_DAYS) < timeline.known_from:
        findings.append(
            WorkRuleFinding(
                "WR_HISTORY_UNKNOWN",
                "info",
                timeline.driver_id,
                focus[0],
                (),
                None,
                None,
                "Driver history",
                {"known_from": timeline.known_from.isoformat()},
                "workrules.WR_HISTORY_UNKNOWN",
            )
        )
    findings.sort(key=lambda f: (f.service_date, f.rule_id, f.trip_ids))
    return tuple(findings)
