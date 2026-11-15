from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

LEGAL_RULES_VERSION = "gr-pd54-1998+eu561-2026-11"

PD = "PD 54/1998"
EU = "EU 561/2006"


@dataclass(frozen=True)
class Limit:
    rule_id: str
    value: int
    direction: Literal["max", "min", "fixed"]
    source: str


_LIMITS = (
    Limit("daily_work_normal", 480, "fixed", f"{PD} Art. 3(1)"),
    Limit("daily_work_max", 600, "max", f"{PD} Art. 3(2), 6(3)"),
    Limit("daily_work_emergency", 660, "max", f"{PD} Art. 6(4)-(5)"),
    Limit("overtime_year", 7200, "max", f"{PD} Art. 6(3)"),
    Limit("overtime_year_absolute", 10800, "max", f"{PD} Art. 6(3), 6(5)"),
    Limit("weekly_work_normal", 2400, "fixed", f"{PD} Art. 3"),
    Limit("weekly_work_max", 2700, "max", f"{PD} Art. 3"),
    Limit("continuous_driving", 270, "max", f"{PD} Art. 4(2); {EU} Art. 7"),
    Limit("break_full", 45, "min", f"{PD} Art. 4(2)-(3); {EU} Art. 7"),
    Limit("break_split_first", 15, "min", f"{PD} Art. 4(2)-(3); {EU} Art. 7"),
    Limit("break_split_second", 30, "min", f"{PD} Art. 4(2)-(3); {EU} Art. 7"),
    Limit("urban_break", 30, "min", f"{PD} Art. 4(4)"),
    Limit("daily_driving_eu", 540, "max", f"{EU} Art. 6"),
    Limit("daily_driving_eu_extended", 600, "max", f"{EU} Art. 6"),
    Limit("daily_driving_extensions_per_week", 2, "max", f"{EU} Art. 6"),
    Limit("weekly_driving_eu", 3360, "max", f"{EU} Art. 6"),
    Limit("fortnight_driving_eu", 5400, "max", f"{EU} Art. 6"),
    Limit("daily_rest", 720, "min", f"{PD} Art. 5(2)"),
    Limit("daily_rest_reduced", 600, "min", f"{PD} Art. 5(2)"),
    Limit("reduced_rests_per_week", 1, "max", f"{PD} Art. 5(2)"),
    Limit("weekly_rest", 2880, "min", f"{PD} Art. 2(ε), 5(2)"),
    Limit("workdays_before_weekly_rest", 5, "max", f"{PD} Art. 2(ε), 5(2)"),
    Limit("sunday_rest_every_weeks", 4, "max", f"{PD} Art. 2(ε), 5(2)"),
    Limit("interruptions_per_week", 3, "max", f"{PD} Art. 2(η), 5(1)"),
    Limit("interruption_minutes_per_week", 540, "max", f"{PD} Art. 2(η), 5(1)"),
    Limit("interruption_threshold", 60, "fixed", f"{PD} Art. 2(η), 5(1)"),
    Limit("break_piece_threshold", 15, "fixed", f"{PD} Art. 4(2)-(3); {EU} Art. 7"),
    Limit("vehicle_check", 10, "fixed", f"{PD} Art. 3(3)-(4)"),
    Limit("dead_run_out", 15, "fixed", f"{PD} Art. 3(3)-(4)"),
    Limit("dead_run_back", 10, "fixed", f"{PD} Art. 3(3)-(4)"),
    Limit("eu_route_km", 50, "fixed", f"{EU} Art. 3(a)"),
)

LEGAL_LIMITS: Mapping[str, Limit] = MappingProxyType({limit.rule_id: limit for limit in _LIMITS})

WARNING_RULES = frozenset({"overnight_rest_day", "no_consecutive_overnight", "shift_rotation"})
