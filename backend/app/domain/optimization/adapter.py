from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot, ChainSnapshot
from app.domain.timetables.time_service import normalize_service_trip
from app.domain.timetables.connection_graph import linear_chains, connection_day_issues


@dataclass(frozen=True)
class SyntheticResourcePair:
    driver_id: int
    vehicle_id: int
    home_station: str
    bus_type: str
    id: Optional[str] = None
    available_windows: Optional[tuple] = None

    @property
    def resource_id(self) -> str:
        return self.id or f"PAIR_{self.driver_id}_{self.vehicle_id}"


@dataclass(frozen=True)
class OperationalSnapshot:
    tenant_id: int
    service_date: date
    pairings: List[SyntheticResourcePair]
    trips: List[Dict[str, Any]]
    snapshot_hash: str = ""
    transfer_durations: Dict[tuple[str, str], int] = field(default_factory=dict)
    source_data: Dict[str, Any] = field(default_factory=dict)
    timezone: str = "Europe/Athens"
    connections: tuple[tuple[str, str], ...] = ()
    availability_enforced: bool = False


def to_cv_problem(
    snapshot: OperationalSnapshot,
    iana_timezone: Optional[str] = None,
) -> SolverProblem:
    """
    Transforms an operational snapshot with pre-approved driver-vehicle pairings
    into an immutable SolverProblem for Christos Valouxis's CV Solver v1.
    Guarantees no mid-duty swap by strictly maintaining 1-to-1 paired resources.
    """
    iana_timezone = iana_timezone or snapshot.timezone
    resources: List[ResourceSnapshot] = []
    for pair in snapshot.pairings:
        if not isinstance(pair.bus_type,str) or not pair.bus_type.strip():
            raise ValueError("An actual vehicle type is required for each pairing")
        resources.append(
            ResourceSnapshot(
                resource_id=pair.resource_id,
                driver_id=str(pair.driver_id),
                bus_id=str(pair.vehicle_id),
                home_station=pair.home_station,
                bus_type=pair.bus_type,
                available_windows=pair.available_windows,
            )
        )

    trips: List[TripSnapshot] = []
    for raw in snapshot.trips:
        trip_id = str(raw["id"])
        origin = str(raw["origin"])
        dest = str(raw["destination"])
        start_str = str(raw["start_time"]).strip()
        end_str = str(raw["end_time"]).strip()

        # Parse HH:MM
        sh, sm = [int(p) for p in start_str.split(":")]
        eh, em = [int(p) for p in end_str.split(":")]

        start_dt = datetime(
            snapshot.service_date.year,
            snapshot.service_date.month,
            snapshot.service_date.day,
            sh, sm,
        )

        arrival_day = raw.get("arrival_day_offset")
        if type(arrival_day) is not int or arrival_day not in (0,1,2):
            raise ValueError("Choose an explicit arrival day offset (same day or next day)")
        end_date = snapshot.service_date + timedelta(days=arrival_day)
        end_dt = datetime(end_date.year,end_date.month,end_date.day,eh,em)
        allowed_types = raw.get("allowed_bus_types")
        if not isinstance(allowed_types,(list,tuple)) or not allowed_types or any(
            not isinstance(value,str) or not value.strip() for value in allowed_types):
            raise ValueError("Specify actual route vehicle eligibility types")

        instant = normalize_service_trip(
            local_start=start_dt,
            local_end=end_dt,
            iana_timezone=iana_timezone,
            service_date=snapshot.service_date,
            fold_start=raw.get("fold_start"),fold_end=raw.get("fold_end"),
        )

        trips.append(
            TripSnapshot(
                id=trip_id,
                start_station=origin,
                end_station=dest,
                start_minutes=instant.start_offset_minutes,
                end_minutes=instant.end_offset_minutes,
                duration_minutes=instant.duration_minutes,
                allowed_bus_types=tuple(allowed_types),
            )
        )

    all_stations = set()
    for t in trips:
        all_stations.add(t.start_station)
        all_stations.add(t.end_station)
    for r in resources:
        all_stations.add(r.home_station)

    stations=tuple(sorted(all_stations))
    matrix=[]
    for origin in stations:
        row=[]
        for destination in stations:
            if origin==destination:
                row.append(0)
                continue
            duration=snapshot.transfer_durations.get((origin,destination))
            if type(duration) is not int or duration<0:
                raise ValueError(f"Enter a verified transfer duration from {origin} to {destination}")
            row.append(duration)
        matrix.append(tuple(row))

    ids = {trip.id for trip in trips}
    if any(incoming not in ids or outgoing not in ids for incoming,outgoing in snapshot.connections):
        raise ValueError("A connection must refer to operating trips in this snapshot")
    chains = tuple(ChainSnapshot(chain) for chain in linear_chains(snapshot.connections))
    facts = {trip.id:{'trip_code':trip.id,'start':trip.start_minutes,'end':trip.end_minutes,'origin':trip.start_station,
                     'destination':trip.end_station,'types':trip.allowed_bus_types} for trip in trips}
    connection_issues = connection_day_issues(snapshot.connections,facts,{resource.bus_type for resource in resources},snapshot.transfer_durations)
    if connection_issues:raise ValueError(connection_issues[0]['message'])
    return SolverProblem(
        problem_id=f"PROB_{snapshot.tenant_id}_{snapshot.service_date.isoformat()}",
        tenant_id=str(snapshot.tenant_id),
        service_date=snapshot.service_date,
        trips=tuple(trips),
        resources=tuple(resources),
        chains=chains,
        stations=stations,
        transfer_matrix=tuple(matrix),
        availability_enforced=snapshot.availability_enforced,
    )
