"""
Independent Verification Rules for KTEL Scheduling.
Versioned hard rules for canonical schedule inputs.
Zero dependency on legacy legality_checker.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class Violation:
    rule_id: str
    rule_name: str
    severity: Severity
    message: str
    entity_type: str
    entity_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleSet:
    version: str = "v2.4-availability"
    require_full_coverage: bool = False
    enforce_unique_trips: bool = True
    enforce_no_temporal_overlap: bool = True
    enforce_mandatory_chains: bool = True
    enforce_station_continuity: bool = True
    max_continuous_driving_minutes: int = 270
    max_daily_driving_minutes: int = 540
    min_break_minutes: int = 45


@dataclass(frozen=True)
class VerificationReport:
    valid: bool
    rule_version: str
    violations: list[Violation]

    @property
    def is_feasible(self) -> bool:
        return self.valid
    coverage_percent: float
    unassigned_trips: list[str]
    assigned_trips_count: int
    total_trips_count: int
