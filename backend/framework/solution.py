from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DriverAssignment:
    driver_id: str
    bus_id: str
    home_station: str
    assigned_trip_ids: List[str]
    total_driving_time: int
    total_idle_time: int
    base_mismatch: int

    @property
    def num_trips(self) -> int:
        return len(self.assigned_trip_ids)

    @property
    def is_used(self) -> bool:
        return self.num_trips > 0


class Solution:
    def __init__(
        self,
        solver_name: str,
        bus_states: List[Dict[str, Any]],
        unassigned_trips: List[str],
        metrics: Dict[str, Any],
        solve_time: float = 0.0,
        raw: Dict[str, Any] = None,
    ):
        self.solver_name = solver_name
        self.unassigned_trips = unassigned_trips
        self.metrics = metrics
        self.solve_time = solve_time
        self.raw = raw or {}

        self.assignments: List[DriverAssignment] = []
        for bs in bus_states:
            self.assignments.append(
                DriverAssignment(
                    driver_id=bs.get("driverId", ""),
                    bus_id=bs.get("busId", ""),
                    home_station=bs.get("homeStation", ""),
                    assigned_trip_ids=bs.get("assignedTrips", []),
                    total_driving_time=bs.get("totalDrivingTime", 0),
                    total_idle_time=bs.get("totalIdleTime", 0),
                    base_mismatch=bs.get("baseMismatch", 0),
                )
            )

    @property
    def total_trips(self) -> int:
        return self.metrics.get("totalTrips", self.num_assigned + self.num_unassigned)

    @property
    def num_assigned(self) -> int:
        return sum(a.num_trips for a in self.assignments)

    @property
    def num_unassigned(self) -> int:
        return len(self.unassigned_trips)

    @property
    def buses_used(self) -> int:
        return sum(1 for a in self.assignments if a.is_used)

    @property
    def total_idle(self) -> int:
        return self.metrics.get(
            "totalIdleTime",
            self.metrics.get(
                "totalIdle", sum(a.total_idle_time for a in self.assignments)
            ),
        )

    @property
    def total_driving(self) -> int:
        return self.metrics.get(
            "totalDrivingTime", sum(a.total_driving_time for a in self.assignments)
        )

    @property
    def total_transfer(self) -> int:
        return self.metrics.get(
            "totalTransferTime", self.metrics.get("totalTransfer", 0)
        )

    @property
    def base_mismatch(self) -> int:
        return self.metrics.get(
            "baseMismatchCount",
            self.metrics.get(
                "baseMismatch", sum(a.base_mismatch for a in self.assignments)
            ),
        )

    @property
    def total_over_8h(self) -> int:
        if "totalOver8h" in self.metrics:
            return self.metrics["totalOver8h"]
        sa = self.raw.get("sa", {}).get("bestMetrics", {})
        return sa.get("totalOver8h", 0)

    @property
    def fairness(self) -> float:
        if "fairness" in self.metrics:
            return self.metrics["fairness"]
        sa = self.raw.get("sa", {}).get("bestMetrics", {})
        return sa.get("fairness", 0.0)

    def summary(self) -> Dict[str, Any]:
        return {
            "solver": self.solver_name,
            "time (s)": round(self.solve_time, 3),
            "assigned": self.num_assigned,
            "unassigned": self.num_unassigned,
            "buses used": self.buses_used,
            "idle (min)": self.total_idle,
            "driving (min)": self.total_driving,
            "transfer (min)": self.total_transfer,
            "over 8h (min)": self.total_over_8h,
            "base mismatch": self.base_mismatch,
            "fairness": round(self.fairness, 1),
        }

    def to_dict(self) -> Dict[str, Any]:
        return (
            self.raw
            if self.raw
            else {
                "solverName": self.solver_name,
                "solveTime": self.solve_time,
                "metrics": self.metrics,
                "unassignedTrips": self.unassigned_trips,
            }
        )

    def __repr__(self) -> str:
        return (
            f"Solution(solver='{self.solver_name}', "
            f"assigned={self.num_assigned}/{self.total_trips}, "
            f"time={self.solve_time:.3f}s)"
        )


def compare(solutions: List[Solution]) -> str:
    if not solutions:
        return "No solutions to compare."

    summaries = [s.summary() for s in solutions]
    keys = list(summaries[0].keys())

    col_w = max(20, max(len(str(v)) for s in summaries for v in s.values()) + 2)
    label_w = max(len(k) for k in keys) + 2

    header = f"{'Metric':<{label_w}}"
    for s in summaries:
        header += f" | {s['solver']:>{col_w}}"
    sep = "-" * len(header)

    lines = [sep, header, sep]
    for key in keys:
        if key == "solver":
            continue
        row = f"{key:<{label_w}}"
        for s in summaries:
            val = s[key]
            if isinstance(val, float):
                row += f" | {val:>{col_w}.2f}"
            else:
                row += f" | {str(val):>{col_w}}"
        lines.append(row)
    lines.append(sep)

    return "\n".join(lines)
