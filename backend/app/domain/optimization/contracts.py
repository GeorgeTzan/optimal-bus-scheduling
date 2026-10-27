"""
Optimization Domain Contracts (v2).
Provides typed, immutable contracts and protocols for the scheduling optimization engine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SolverConfig:
    seed: int
    time_limit_seconds: int
    cp_sat_workers: int = 1
    iterations: int = 5


@dataclass(frozen=True)
class TripSnapshot:
    id: str
    start_station: str
    end_station: str
    start_minutes: int
    end_minutes: int
    duration_minutes: int
    day_offset: int = 0
    group: str = "000"
    allowed_bus_types: tuple[str, ...] = ("01",)


@dataclass(frozen=True)
class ResourceSnapshot:
    resource_id: str
    driver_id: str
    bus_id: str
    home_station: str
    bus_type: str = "01"
    # Usable windows in minutes from the frozen service-day origin. None = legacy/unknown, () = known empty.
    available_windows: tuple[tuple[int, int], ...] | None = None


@dataclass(frozen=True)
class ChainSnapshot:
    trip_ids: tuple[str, ...]

    @property
    def head(self) -> str:
        return self.trip_ids[0]

    @property
    def tail(self) -> str:
        return self.trip_ids[-1]


@dataclass(frozen=True)
class SolverParametersSnapshot:
    max_driving_time: int = 900
    max_continuous_driving: int = 270
    min_break_time: int = 30
    min_rest_time: int = 720
    max_duty_duration: int = 600


@dataclass(frozen=True)
class SolverProblem:
    problem_id: str
    tenant_id: str
    service_date: date
    trips: tuple[TripSnapshot, ...]
    resources: tuple[ResourceSnapshot, ...]
    chains: tuple[ChainSnapshot, ...]
    stations: tuple[str, ...] = field(default_factory=tuple)
    transfer_matrix: tuple[tuple[int, ...], ...] = field(default_factory=tuple)
    parameters: SolverParametersSnapshot = field(default_factory=SolverParametersSnapshot)
    # New canonical problems enforce availability for every trip except protected, already-operated work chosen by the server.
    availability_enforced: bool = False
    availability_exempt_trip_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assignment:
    resource_id: str
    trip_id: str
    start_minutes: int
    end_minutes: int
    start_station: str
    end_station: str


@dataclass(frozen=True)
class SolverResult:
    solver_id: str
    solver_version: str
    assignments: tuple[Assignment, ...]
    unassigned_trip_ids: tuple[str, ...]
    metrics: dict[str, Any]
    solve_time_seconds: float
    status: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProgressSink(Protocol):
    def update(
        self,
        iteration: int,
        max_iterations: int,
        current_cost: float,
        best_cost: float,
        message: str = "",
    ) -> None:
        ...


@runtime_checkable
class SchedulingSolver(Protocol):
    @property
    def algorithm_id(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    def solve(
        self,
        problem: SolverProblem,
        config: SolverConfig,
        progress: ProgressSink | None = None,
    ) -> SolverResult:
        ...
