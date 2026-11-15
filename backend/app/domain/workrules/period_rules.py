from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Callable, Iterator

from app.domain.workrules.facts import DutyFacts
from app.domain.workrules.findings import COMPANY, RESTRICTION, WorkRuleFinding, finding
from app.domain.workrules.legal import LEGAL_LIMITS, PD
from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import DriverTimeline, Duty

ROTATION = f"{PD} Art. 8"
AFTERNOON = time(14, 0)
PARTIAL = {"partial": "true"}


@dataclass(frozen=True)
class Item:
    duty: Duty
    facts: DutyFacts
    ids: tuple[str, ...]


@dataclass(frozen=True)
class Rest:
    index: int
    start: datetime
    item: Item
    minutes: int


def _minutes(start: datetime, end: datetime) -> int:
    return int((end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() // 60)


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _source(rule_id: str) -> str:
    return LEGAL_LIMITS[rule_id].source


def _partial(timeline: DriverTimeline, day: date) -> dict[str, str] | None:
    return PARTIAL if timeline.baseline is None and day < timeline.known_from else None


def _rests(timeline: DriverTimeline, items: list[Item]) -> list[Rest]:
    baseline = timeline.baseline
    out: list[Rest] = []
    for index, item in enumerate(items):
        if index:
            start: datetime | None = items[index - 1].facts.end
        else:
            start = baseline.last_duty_end if baseline else None
        if start is not None:
            out.append(Rest(index, start, item, _minutes(start, item.facts.start)))
    return out


def _daily_rest(
    rests: list[Rest], policy: WorkRulePolicy
) -> tuple[list[WorkRuleFinding], list[tuple[int, date, int]]]:
    full, reduced = policy.value("daily_rest"), policy.value("daily_rest_reduced")
    allowance = policy.value("reduced_rests_per_week")
    used: dict[date, int] = defaultdict(int)
    out: list[WorkRuleFinding] = []
    debts: list[tuple[int, date, int]] = []
    for rest in rests:
        if rest.minutes >= full:
            continue
        week = _week(rest.item.duty.service_date)
        if rest.minutes >= reduced and used[week] < allowance:
            used[week] += 1
            debts.append((rest.index + 1, week + timedelta(days=7), full - rest.minutes))
            continue
        rule = "daily_rest" if rest.minutes >= reduced else "daily_rest_reduced"
        limit = policy.value(rule)
        hint = {"rest_until": _utc(rest.start + timedelta(minutes=limit))}
        out.append(
            finding("WR_DAILY_REST", "legal", rest.item.duty, rest.item.ids, rest.minutes, limit, _source(rule), hint)
        )
    return out, debts


def _compensation(
    timeline: DriverTimeline,
    items: list[Item],
    rests: list[Rest],
    policy: WorkRulePolicy,
    debts: list[tuple[int, date, int]],
    zone: tzinfo,
) -> list[WorkRuleFinding]:
    baseline = timeline.baseline
    if baseline and baseline.owed_rest_minutes > 0:
        first = next((i for i, it in enumerate(items) if it.duty.service_date > baseline.as_of), len(items))
        debts = [*debts, (first, _week(baseline.as_of) + timedelta(days=7), baseline.owed_rest_minutes)]
    known_through = max((d.service_date for d in timeline.duties), default=None)
    out: list[WorkRuleFinding] = []
    for first, monday, owed in debts:
        sunday = monday + timedelta(days=6)
        if known_through is None or timeline.known_from > monday or known_through < sunday:
            continue
        week = [it for it in items if monday <= it.duty.service_date <= sunday]
        if not week:
            continue
        need = policy.value("daily_rest") + owed
        deadline = datetime.combine(sunday + timedelta(days=1), time(), zone)
        best = max(
            (
                min(r.minutes, _minutes(r.start, deadline))
                for r in rests
                if r.index >= first and _minutes(r.start, deadline) >= 0
            ),
            default=0,
        )
        if best < need:
            last = week[-1]
            out.append(
                finding(
                    "WR_REDUCED_REST_COMPENSATION",
                    "legal",
                    last.duty,
                    last.ids,
                    best,
                    need,
                    _source("daily_rest_reduced"),
                )
            )
    return out


def _by_week(items: list[Item]) -> dict[date, list[Item]]:
    groups: dict[date, list[Item]] = defaultdict(list)
    for item in items:
        groups[_week(item.duty.service_date)].append(item)
    return groups


def _over(group: list[Item], value: Callable[[Item], int], limit: int, start: int = 0) -> Iterator[tuple[Item, int]]:
    running = start
    for item in group:
        added = value(item)
        running += added
        if added > 0 and running > limit:
            yield item, running


def _weekly_sums(timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy) -> list[WorkRuleFinding]:
    checks: tuple[tuple[str, str, Callable[[Item], int], dict[str, str] | None], ...] = (
        ("WR_WEEKLY_WORK", "weekly_work_max", lambda i: i.facts.work_minutes, None),
        ("WR_WEEKLY_DRIVING", "weekly_driving_eu", lambda i: i.facts.long_route_driving_minutes, None),
        ("WR_INTERRUPTIONS", "interruptions_per_week", lambda i: i.facts.interruptions, {"measure": "count"}),
        (
            "WR_INTERRUPTIONS",
            "interruption_minutes_per_week",
            lambda i: i.facts.interruption_minutes,
            {"measure": "minutes"},
        ),
    )
    out: list[WorkRuleFinding] = []
    weeks = _by_week(items)
    for monday, group in weeks.items():
        for rule_id, limit_id, value, extra in checks:
            limit = policy.value(limit_id)
            hint = {**(extra or {}), **(_partial(timeline, monday) or {})}
            for item, running in _over(group, value, limit):
                out.append(finding(rule_id, "legal", item.duty, item.ids, running, limit, _source(limit_id), hint))
        previous = sum(i.facts.long_route_driving_minutes for i in weeks.get(monday - timedelta(days=7), []))
        limit = policy.value("fortnight_driving_eu")
        hint = _partial(timeline, monday - timedelta(days=7))
        for item, running in _over(group, lambda i: i.facts.long_route_driving_minutes, limit, previous):
            out.append(
                finding("WR_FORTNIGHT_DRIVING", "legal", item.duty, item.ids, running, limit, _source("fortnight_driving_eu"), hint)
            )
    return out


def _seed(timeline: DriverTimeline, items: list[Item], weekly: int, zone: tzinfo) -> int:
    baseline = timeline.baseline
    if baseline is None or baseline.last_weekly_rest_end is None or baseline.last_duty_end is None:
        return 0
    if _minutes(baseline.last_weekly_rest_end, baseline.last_duty_end) <= 0:
        return 0
    if items and _minutes(baseline.last_duty_end, items[0].facts.start) >= weekly:
        return 0
    rest_day = baseline.last_weekly_rest_end.astimezone(zone).date()
    return (baseline.last_duty_end.astimezone(zone).date() - rest_day).days + 1


def _weekly_rest(
    timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy, zone: tzinfo
) -> list[WorkRuleFinding]:
    weekly, limit = policy.value("weekly_rest"), policy.value("workdays_before_weekly_rest")
    source = _source("weekly_rest")
    baseline = timeline.baseline
    anchor = baseline.last_weekly_rest_end if baseline else None
    out: list[WorkRuleFinding] = []
    streak: list[Item] = []
    partial = anchor is None
    seed = _seed(timeline, items, weekly, zone)

    def close() -> None:
        nonlocal seed
        hint = PARTIAL if partial else None
        days = list(dict.fromkeys(item.duty.service_date for item in streak))
        firsts = {item.duty.service_date: item for item in reversed(streak)}
        for position, day in enumerate(days, seed + 1):
            if position > limit:
                item = firsts[day]
                out.append(finding("WR_WEEKLY_REST", "legal", item.duty, item.ids, position, limit, source, hint))
        streak.clear()
        seed = 0

    for index, item in enumerate(items):
        if index:
            previous = items[index - 1]
            gap: int | None = _minutes(previous.facts.end, item.facts.start)
        else:
            previous = None
            gap = _minutes(baseline.last_duty_end, item.facts.start) if baseline and baseline.last_duty_end else None
        crossed = anchor is not None and previous is not None and previous.facts.start < anchor <= item.facts.start
        if (gap is not None and gap >= weekly) or crossed:
            close()
            partial = False
            if gap is not None and gap >= weekly and previous is not None and previous.facts.ends_away_from_base:
                out.append(
                    finding("WR_WEEKLY_REST_BASE", "legal", previous.duty, previous.ids, gap, weekly, source)
                )
        streak.append(item)
    close()
    return out


def _sunday_rest(
    timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy, zone: tzinfo
) -> list[WorkRuleFinding]:
    weekly, weeks = policy.value("weekly_rest"), policy.value("sunday_rest_every_weeks")
    baseline = timeline.baseline
    lead = baseline.last_duty_end if baseline and baseline.last_duty_end else None
    if lead is None:
        lead = datetime.combine(timeline.known_from, time(), zone)
    ends = [lead, *(i.facts.end for i in items)]
    starts: list[datetime | None] = [*(i.facts.start for i in items), None]
    spans = [(s, e) for s, e in zip(ends, starts) if e is None or _minutes(s, e) >= weekly]
    known = timeline.known_from
    if baseline and baseline.last_weekly_rest_end:
        rest_end = baseline.last_weekly_rest_end
        spans.append((rest_end - timedelta(minutes=weekly), rest_end))
        known = min(known, rest_end.astimezone(zone).date())
    busy = {i.duty.service_date for i in items}

    def off(sunday: date) -> bool:
        if sunday in busy:
            return False
        begin = datetime.combine(sunday, time(), zone)
        finish = datetime.combine(sunday + timedelta(days=1), time(), zone)
        return any(
            _minutes(s, begin) >= 0 and (e is None or _minutes(finish, e) >= 0) for s, e in spans
        )

    out: list[WorkRuleFinding] = []
    for item in {i.duty.service_date: i for i in reversed(items)}.values():
        monday = _week(item.duty.service_date)
        first = monday - timedelta(days=7 * (weeks - 1))
        if first < known:
            continue
        if not any(off(first + timedelta(days=7 * k + 6)) for k in range(weeks)):
            out.append(
                finding("WR_SUNDAY_REST", "legal", item.duty, item.ids, None, weeks, _source("sunday_rest_every_weeks"))
            )
    return out


def _overtime(timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy) -> list[WorkRuleFinding]:
    baseline = timeline.baseline
    out: list[WorkRuleFinding] = []
    for rule_id, limit_id, emergency in (
        ("WR_OVERTIME_YEAR", "overtime_year", False),
        ("WR_OVERTIME_YEAR_ABSOLUTE", "overtime_year_absolute", True),
    ):
        limit = policy.value(limit_id)
        years: dict[int, list[Item]] = defaultdict(list)
        for item in items:
            if baseline and item.duty.service_date <= baseline.as_of:
                continue
            if item.duty.emergency and not emergency:
                continue
            years[item.duty.service_date.year].append(item)
        for year, group in years.items():
            start = (baseline.overtime_minutes if baseline and baseline.as_of.year == year else 0) + timeline.prior(
                year, emergency
            )
            hint = _partial(timeline, date(year, 1, 1))
            for item, running in _over(group, lambda i: i.facts.overtime_minutes, limit, start):
                out.append(finding(rule_id, "legal", item.duty, item.ids, running, limit, _source(limit_id), hint))
    return out


def _warnings(
    timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy, zone: tzinfo
) -> list[WorkRuleFinding]:
    rules = policy.warning_rules
    by_date = {i.duty.service_date: i for i in items}
    out: list[WorkRuleFinding] = []
    for item in items:
        if not item.facts.ends_away_from_base:
            continue
        if not timeline.profile.overnight_allowed:
            out.append(finding("WR_OVERNIGHT_NOT_ALLOWED", "warning", item.duty, item.ids, None, None, RESTRICTION))
        following = by_date.get(item.duty.service_date + timedelta(days=1))
        if following is None:
            continue
        if "overnight_rest_day" in rules:
            out.append(finding("WR_OVERNIGHT_REST_DAY", "warning", following.duty, following.ids, None, None, COMPANY))
        if "no_consecutive_overnight" in rules and following.facts.ends_away_from_base:
            out.append(
                finding("WR_OVERNIGHT_CONSECUTIVE", "warning", following.duty, following.ids, None, None, COMPANY)
            )
    if "shift_rotation" in rules:
        late: dict[date, Item] = {}
        for item in items:
            if item.facts.start.astimezone(zone).time() >= AFTERNOON:
                late.setdefault(_week(item.duty.service_date), item)
        for monday, item in late.items():
            if monday - timedelta(days=7) in late:
                out.append(finding("WR_SHIFT_ROTATION", "warning", item.duty, item.ids, None, None, ROTATION))
    return out


def period_findings(
    timeline: DriverTimeline, items: list[Item], policy: WorkRulePolicy, zone: tzinfo
) -> Iterator[WorkRuleFinding]:
    rests = _rests(timeline, items)
    daily, debts = _daily_rest(rests, policy)
    yield from daily
    yield from _compensation(timeline, items, rests, policy, debts, zone)
    yield from _weekly_sums(timeline, items, policy)
    yield from _weekly_rest(timeline, items, policy, zone)
    yield from _sunday_rest(timeline, items, policy, zone)
    yield from _overtime(timeline, items, policy)
    yield from _warnings(timeline, items, policy, zone)
