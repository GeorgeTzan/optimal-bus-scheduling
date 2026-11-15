from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Literal, Mapping


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass(frozen=True)
class DutyTrip:
    trip_id: str
    start: datetime
    end: datetime
    origin: str
    destination: str
    origin_is_depot: bool
    destination_is_depot: bool
    vehicle_id: str
    route_id: int | None
    urban: bool
    long_route: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "trip_id": self.trip_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "origin": self.origin,
            "destination": self.destination,
            "origin_is_depot": self.origin_is_depot,
            "destination_is_depot": self.destination_is_depot,
            "vehicle_id": self.vehicle_id,
            "route_id": self.route_id,
            "urban": self.urban,
            "long_route": self.long_route,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DutyTrip:
        return cls(
            trip_id=data["trip_id"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            origin=data["origin"],
            destination=data["destination"],
            origin_is_depot=data["origin_is_depot"],
            destination_is_depot=data["destination_is_depot"],
            vehicle_id=data["vehicle_id"],
            route_id=data["route_id"],
            urban=data["urban"],
            long_route=data["long_route"],
        )


@dataclass(frozen=True)
class Duty:
    driver_id: str
    service_date: date
    trips: tuple[DutyTrip, ...]
    provenance: Literal["published", "draft"]
    emergency: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "driver_id": self.driver_id,
            "service_date": self.service_date.isoformat(),
            "trips": [t.to_dict() for t in self.trips],
            "provenance": self.provenance,
            "emergency": self.emergency,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Duty:
        return cls(
            driver_id=data["driver_id"],
            service_date=date.fromisoformat(data["service_date"]),
            trips=tuple(DutyTrip.from_dict(t) for t in data["trips"]),
            provenance=data["provenance"],
            emergency=data.get("emergency", False),
        )


@dataclass(frozen=True)
class Baseline:
    as_of: date
    overtime_minutes: int
    last_duty_end: datetime | None
    last_weekly_rest_end: datetime | None
    last_weekly_rest_at_base: bool
    owed_rest_minutes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "overtime_minutes": self.overtime_minutes,
            "last_duty_end": _iso(self.last_duty_end),
            "last_weekly_rest_end": _iso(self.last_weekly_rest_end),
            "last_weekly_rest_at_base": self.last_weekly_rest_at_base,
            "owed_rest_minutes": self.owed_rest_minutes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Baseline:
        return cls(
            as_of=date.fromisoformat(data["as_of"]),
            overtime_minutes=data["overtime_minutes"],
            last_duty_end=_dt(data["last_duty_end"]),
            last_weekly_rest_end=_dt(data["last_weekly_rest_end"]),
            last_weekly_rest_at_base=data["last_weekly_rest_at_base"],
            owed_rest_minutes=data["owed_rest_minutes"],
        )


@dataclass(frozen=True)
class DriverProfile:
    home_station: str
    overnight_allowed: bool
    split_shift_allowed: bool
    must_return_to_base: bool
    forbidden_routes: frozenset[int]
    preferred_routes: frozenset[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_station": self.home_station,
            "overnight_allowed": self.overnight_allowed,
            "split_shift_allowed": self.split_shift_allowed,
            "must_return_to_base": self.must_return_to_base,
            "forbidden_routes": sorted(self.forbidden_routes),
            "preferred_routes": sorted(self.preferred_routes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DriverProfile:
        return cls(
            home_station=data["home_station"],
            overnight_allowed=data["overnight_allowed"],
            split_shift_allowed=data["split_shift_allowed"],
            must_return_to_base=data["must_return_to_base"],
            forbidden_routes=frozenset(data["forbidden_routes"]),
            preferred_routes=frozenset(data["preferred_routes"]),
        )


@dataclass(frozen=True)
class DriverTimeline:
    driver_id: str
    profile: DriverProfile
    duties: tuple[Duty, ...]
    baseline: Baseline | None
    known_from: date
    forbidden_vehicle_routes: Mapping[str, frozenset[int]]
    prior_year: int | None = None
    prior_overtime: int = 0
    prior_emergency_overtime: int = 0

    def prior(self, year: int, emergency: bool) -> int:
        if self.prior_year != year:
            return 0
        return self.prior_overtime + (self.prior_emergency_overtime if emergency else 0)

    def with_day(self, day: date, duty: Duty | None) -> DriverTimeline:
        kept = [d for d in self.duties if d.service_date != day]
        if duty is not None:
            kept.append(duty)
        kept.sort(key=lambda d: d.service_date)
        return replace(self, duties=tuple(kept))

    def to_dict(self) -> dict[str, Any]:
        return {
            "driver_id": self.driver_id,
            "profile": self.profile.to_dict(),
            "duties": [d.to_dict() for d in self.duties],
            "baseline": None if self.baseline is None else self.baseline.to_dict(),
            "known_from": self.known_from.isoformat(),
            "forbidden_vehicle_routes": {
                k: sorted(v) for k, v in sorted(self.forbidden_vehicle_routes.items())
            },
            "prior_year": self.prior_year,
            "prior_overtime": self.prior_overtime,
            "prior_emergency_overtime": self.prior_emergency_overtime,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DriverTimeline:
        baseline = data["baseline"]
        return cls(
            driver_id=data["driver_id"],
            profile=DriverProfile.from_dict(data["profile"]),
            duties=tuple(Duty.from_dict(d) for d in data["duties"]),
            baseline=None if baseline is None else Baseline.from_dict(baseline),
            known_from=date.fromisoformat(data["known_from"]),
            forbidden_vehicle_routes={
                k: frozenset(v) for k, v in data["forbidden_vehicle_routes"].items()
            },
            prior_year=data.get("prior_year"),
            prior_overtime=data.get("prior_overtime", 0),
            prior_emergency_overtime=data.get("prior_emergency_overtime", 0),
        )
