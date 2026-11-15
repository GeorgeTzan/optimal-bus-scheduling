from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping

from app.domain.workrules.evaluate import evaluate
from app.domain.workrules.facts import DutyFacts, duty_parts
from app.domain.workrules.findings import WorkRuleFinding, caused_by
from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import DriverTimeline, Duty

HORIZON_MINUTES = 2880


@dataclass(frozen=True)
class DriverDayBudget:
    driver_id: str
    earliest_start_minutes: int
    latest_end_minutes: int
    max_work_minutes: int
    max_long_route_driving_minutes: int
    continuous_driving_minutes: int
    overnight_allowed: bool
    split_shift_allowed: bool
    must_return_to_base: bool
    forbidden_route_ids: tuple[int, ...]
    preferred_route_ids: tuple[int, ...]
    forbidden_vehicle_route_ids: Mapping[str, tuple[int, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "driver_id": self.driver_id,
            "earliest_start_minutes": self.earliest_start_minutes,
            "latest_end_minutes": self.latest_end_minutes,
            "max_work_minutes": self.max_work_minutes,
            "max_long_route_driving_minutes": self.max_long_route_driving_minutes,
            "continuous_driving_minutes": self.continuous_driving_minutes,
            "overnight_allowed": self.overnight_allowed,
            "split_shift_allowed": self.split_shift_allowed,
            "must_return_to_base": self.must_return_to_base,
            "forbidden_route_ids": list(self.forbidden_route_ids),
            "preferred_route_ids": list(self.preferred_route_ids),
            "forbidden_vehicle_route_ids": {k: list(v) for k, v in sorted(self.forbidden_vehicle_route_ids.items())},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DriverDayBudget:
        return cls(
            driver_id=data["driver_id"],
            earliest_start_minutes=data["earliest_start_minutes"],
            latest_end_minutes=data["latest_end_minutes"],
            max_work_minutes=data["max_work_minutes"],
            max_long_route_driving_minutes=data["max_long_route_driving_minutes"],
            continuous_driving_minutes=data["continuous_driving_minutes"],
            overnight_allowed=data["overnight_allowed"],
            split_shift_allowed=data["split_shift_allowed"],
            must_return_to_base=data["must_return_to_base"],
            forbidden_route_ids=tuple(data["forbidden_route_ids"]),
            preferred_route_ids=tuple(data["preferred_route_ids"]),
            forbidden_vehicle_route_ids={k: tuple(v) for k, v in data["forbidden_vehicle_route_ids"].items()},
        )


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _relative(instant: datetime, origin: datetime) -> int:
    return int((instant - origin).total_seconds() // 60)


def driver_budget(
    timeline: DriverTimeline,
    policy: WorkRulePolicy,
    day: date,
    day_origin_utc: datetime,
    transfer_minutes: Callable[[str, str], int | None],
) -> DriverDayBudget:
    others = duty_parts([d for d in timeline.duties if d.service_date != day], timeline.profile, policy, transfer_minutes)
    others.sort(key=lambda pair: pair[1].start)
    rest = policy.value("daily_rest")

    before = [pair for pair in others if pair[0].service_date < day]
    after = [pair for pair in others if pair[0].service_date > day and pair[0].provenance == "published"]
    baseline = timeline.baseline
    if before:
        earliest = max(0, _relative(before[-1][1].end, day_origin_utc) + rest)
    elif baseline and baseline.last_duty_end:
        earliest = max(0, _relative(baseline.last_duty_end, day_origin_utc) + rest)
    else:
        earliest = 0
    latest = _relative(after[0][1].start, day_origin_utc) - rest if after else HORIZON_MINUTES

    week = _week(day)
    this_week = [pair for pair in others if _week(pair[0].service_date) == week]
    prev_week = [pair for pair in others if _week(pair[0].service_date) == week - timedelta(days=7)]

    weekly_work = sum(f.work_minutes for _, f in this_week)
    overtime_used = baseline.overtime_minutes if baseline and baseline.as_of.year == day.year else 0
    overtime_used += timeline.prior(day.year, False)
    overtime_used += sum(
        f.overtime_minutes
        for d, f in others
        if d.service_date.year == day.year and not d.emergency and not (baseline and d.service_date <= baseline.as_of)
    )
    max_work = max(
        0,
        min(
            policy.value("daily_work_max"),
            policy.value("weekly_work_max") - weekly_work,
            policy.value("overtime_year") - overtime_used + policy.value("daily_work_normal"),
        ),
    )

    base_driving = policy.value("daily_driving_eu")
    extensions = sum(1 for _, f in this_week if f.long_route_driving_minutes > base_driving)
    daily_driving = (
        policy.value("daily_driving_eu_extended")
        if extensions < policy.value("daily_driving_extensions_per_week")
        else base_driving
    )
    week_driving = sum(f.long_route_driving_minutes for _, f in this_week)
    prev_driving = sum(f.long_route_driving_minutes for _, f in prev_week)
    max_driving = max(
        0,
        min(
            daily_driving,
            policy.value("weekly_driving_eu") - week_driving,
            policy.value("fortnight_driving_eu") - prev_driving - week_driving,
        ),
    )

    profile = timeline.profile
    return DriverDayBudget(
        driver_id=timeline.driver_id,
        earliest_start_minutes=earliest,
        latest_end_minutes=latest,
        max_work_minutes=max_work,
        max_long_route_driving_minutes=max_driving,
        continuous_driving_minutes=policy.value("continuous_driving"),
        overnight_allowed=profile.overnight_allowed,
        split_shift_allowed=profile.split_shift_allowed,
        must_return_to_base=profile.must_return_to_base,
        forbidden_route_ids=tuple(sorted(profile.forbidden_routes)),
        preferred_route_ids=tuple(sorted(profile.preferred_routes)),
        forbidden_vehicle_route_ids={
            vehicle: tuple(sorted(routes)) for vehicle, routes in sorted(timeline.forbidden_vehicle_routes.items())
        },
    )


def legal_duty(
    duty: Duty,
    timeline: DriverTimeline,
    policy: WorkRulePolicy,
    transfer_minutes: Callable[[str, str], int | None],
    *,
    tz: str = "Europe/Athens",
) -> tuple[bool, tuple[WorkRuleFinding, ...]]:
    day = duty.service_date
    focus = (day, day + timedelta(days=7))
    with_draft = evaluate(timeline.with_day(day, duty), policy, focus, transfer_minutes, tz=tz)
    without_draft = evaluate(timeline.with_day(day, None), policy, focus, transfer_minutes, tz=tz)
    caused = tuple(f for f in caused_by(with_draft, without_draft) if f.kind == "legal")
    return not caused, caused
