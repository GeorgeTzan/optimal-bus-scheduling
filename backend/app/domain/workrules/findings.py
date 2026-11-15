from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Mapping, Sequence

from app.domain.workrules.legal import LEGAL_LIMITS
from app.domain.workrules.timeline import Duty

RULE_LIMITS = {
    "WR_DAILY_WORK": "daily_work_max",
    "WR_CONTINUOUS_DRIVING": "continuous_driving",
    "WR_URBAN_BREAK": "urban_break",
    "WR_DAILY_DRIVING": "daily_driving_eu",
    "WR_DAILY_REST": "daily_rest",
    "WR_REDUCED_REST_COMPENSATION": "daily_rest",
    "WR_WEEKLY_WORK": "weekly_work_max",
    "WR_WEEKLY_DRIVING": "weekly_driving_eu",
    "WR_INTERRUPTIONS": "interruptions_per_week",
    "WR_FORTNIGHT_DRIVING": "fortnight_driving_eu",
    "WR_WEEKLY_REST": "workdays_before_weekly_rest",
    "WR_WEEKLY_REST_BASE": "weekly_rest",
    "WR_SUNDAY_REST": "sunday_rest_every_weeks",
    "WR_OVERTIME_YEAR": "overtime_year",
    "WR_OVERTIME_YEAR_ABSOLUTE": "overtime_year_absolute",
}
COMPANY = "Company rule"
RESTRICTION = "Driver restriction"


@dataclass(frozen=True)
class WorkRuleFinding:
    rule_id: str
    kind: Literal["legal", "warning", "info"]
    driver_id: str
    service_date: date
    trip_ids: tuple[str, ...]
    measured: int | None
    limit: int | None
    source: str
    hint: Mapping[str, str]
    message_key: str

    @property
    def key(self) -> str:
        return f"{self.rule_id}|{self.driver_id}|{self.service_date}|{','.join(self.trip_ids)}|{self.measured}"


def finding(
    rule_id: str,
    kind: Literal["legal", "warning", "info"],
    duty: Duty,
    trip_ids: tuple[str, ...],
    measured: int | None,
    limit: int | None,
    source: str,
    hint: Mapping[str, str] | None = None,
) -> WorkRuleFinding:
    return WorkRuleFinding(
        rule_id,
        kind,
        duty.driver_id,
        duty.service_date,
        trip_ids,
        measured,
        limit,
        source,
        hint or {},
        f"workrules.{rule_id}",
    )


def caused_by(
    with_draft: Sequence[WorkRuleFinding], without_draft: Sequence[WorkRuleFinding]
) -> tuple[WorkRuleFinding, ...]:
    baseline = {_slot(f): f.measured for f in without_draft}
    return tuple(f for f in with_draft if _slot(f) not in baseline or worse(f.rule_id, baseline[_slot(f)], f.measured))


def _slot(f: WorkRuleFinding) -> tuple[str, str, date, str | None, tuple[str, ...]]:
    return f.rule_id, f.driver_id, f.service_date, f.hint.get("measure"), f.trip_ids


def lower_is_worse(rule_id: str) -> bool:
    limit = RULE_LIMITS.get(rule_id)
    return limit is not None and LEGAL_LIMITS[limit].direction == "min"


def worse(rule_id: str, before: int | None, after: int | None) -> bool:
    if lower_is_worse(rule_id):
        return before is not None and after is not None and after < before
    return (before or 0) < (after or 0)
