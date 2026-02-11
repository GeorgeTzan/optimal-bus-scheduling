import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Set
from services.legality_checker import SolverParameters, ConstraintsData


@dataclass
class Trip:
    id: str
    start_station: str
    end_station: str
    start_minutes: int
    end_minutes: int
    duration_minutes: int
    day_offset: int
    group: str
    allowed_bus_types: List[str]
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trip":
        return cls(
            id=d["id"],
            start_station=d.get("startStation", ""),
            end_station=d.get("endStation", ""),
            start_minutes=d.get("start_minutes", 0),
            end_minutes=d.get("end_minutes", 0),
            duration_minutes=d.get("time", {}).get("durationMinutes", 0),
            day_offset=d.get("dayOffset", 0),
            group=d.get("classification", {}).get("group", "000"),
            allowed_bus_types=d.get("classification", {}).get("allowedBusTypes", []),
            raw=d,
        )


@dataclass
class Driver:
    driver_id: str
    bus_id: str
    home_station: str
    current_station: str
    bus_type: str
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Driver":
        return cls(
            driver_id=d.get("driverId", ""),
            bus_id=d.get("busId", ""),
            home_station=d.get("homeStation", ""),
            current_station=d.get("currentStation", ""),
            bus_type=d.get("busAttributes", {}).get("type", "01"),
            raw=d,
        )


@dataclass
class Chain:
    trip_ids: List[str]

    @property
    def head(self) -> str:
        return self.trip_ids[0]

    @property
    def tail(self) -> str:
        return self.trip_ids[-1]

    def __len__(self) -> int:
        return len(self.trip_ids)


@dataclass
class Parameters:
    max_duty_minutes: int
    normal_duty_minutes: int
    max_work_minutes: int
    drive_time_to_break: int
    min_break_time: int
    transit_minutes: int

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "Parameters":
        p = config.get("parameters", {})
        return cls(
            max_duty_minutes=p.get("maxDutyMinutes", 900),
            normal_duty_minutes=p.get("normalDutyMinutes", 600),
            max_work_minutes=p.get("maxWorkMinutes", 720),
            drive_time_to_break=p.get("driveTimeToBreakMinutes", 270),
            min_break_time=p.get("minBreakMinutes", 30),
            transit_minutes=p.get("transitMinutes", 30),
        )


class Problem:
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self._trips = [Trip.from_dict(t) for t in data.get("trips", [])]
        self._drivers = [Driver.from_dict(r) for r in data.get("resources", [])]
        self._parameters = Parameters.from_dict(data.get("configuration", {}))
        self._chains = self._build_chains()

    @classmethod
    def from_json(cls, path: str) -> "Problem":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def trips(self) -> List[Trip]:
        return self._trips

    @property
    def drivers(self) -> List[Driver]:
        return self._drivers

    @property
    def parameters(self) -> Parameters:
        return self._parameters

    @property
    def chains(self) -> List[Chain]:
        return self._chains

    @property
    def constraints(self) -> Dict[str, Any]:
        return self._data.get("constraints", {})

    @property
    def station_transfer_matrix(self) -> List[List[str]]:
        return self._data.get("stationTransferMatrix", {}).get("matrix", [])

    @property
    def raw(self) -> Dict[str, Any]:
        return self._data

    @property
    def solver_params(self) -> SolverParameters:
        return SolverParameters.from_data(self._data)

    @property
    def constraints_data(self) -> ConstraintsData:
        return ConstraintsData.from_data(self._data)

    @property
    def num_trips(self) -> int:
        return len(self._trips)

    @property
    def num_drivers(self) -> int:
        return len(self._drivers)

    @property
    def num_chains(self) -> int:
        return len(self._chains)

    def trip_by_id(self, trip_id: str) -> Trip:
        for t in self._trips:
            if t.id == trip_id:
                return t
        raise KeyError(f"Trip '{trip_id}' not found")

    def driver_by_bus(self, bus_id: str) -> Driver:
        for d in self._drivers:
            if d.bus_id == bus_id:
                return d
        raise KeyError(f"Driver with bus '{bus_id}' not found")

    def _build_chains(self) -> List[Chain]:
        constraints = self._data.get("constraints", {})
        all_pairs: List[Tuple[str, str]] = []

        for seq in constraints.get("mandatorySequences", []):
            ids = seq.get("tripIds", []) if isinstance(seq, dict) else seq
            for i in range(len(ids) - 1):
                all_pairs.append((ids[i], ids[i + 1]))

        for joint in constraints.get("mandatoryConnections", []):
            u = joint.get("incomingTripId")
            v = joint.get("outgoingTripId")
            if u and v:
                all_pairs.append((u, v))

        if not all_pairs:
            return []

        forward: Dict[str, str] = {}
        has_predecessor: Set[str] = set()
        for u, v in all_pairs:
            forward[u] = v
            has_predecessor.add(v)

        heads = [u for u in forward if u not in has_predecessor]

        chains: List[Chain] = []
        visited: Set[str] = set()
        for head in heads:
            ids = []
            cur = head
            while cur and cur not in visited:
                ids.append(cur)
                visited.add(cur)
                cur = forward.get(cur)
            if len(ids) > 1:
                chains.append(Chain(trip_ids=ids))

        return chains

    def __repr__(self) -> str:
        return f"Problem(trips={self.num_trips}, drivers={self.num_drivers}, chains={self.num_chains})"
