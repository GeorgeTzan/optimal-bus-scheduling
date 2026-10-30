"""Immutable problem inputs persisted with each imported reference revision."""
from dataclasses import asdict
from datetime import date, datetime, timedelta
from app.domain.timetables.display_clock import frozen_clock
from pathlib import Path
from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from db.database import Base
from app.domain.optimization.contracts import (
    SolverProblem, TripSnapshot, ResourceSnapshot, ChainSnapshot, SolverParametersSnapshot,
)
from app.domain.timetables.time_service import normalize_service_trip


class RevisionSnapshot(Base):
    __tablename__ = 'domain_revision_snapshots'
    revision_id = Column(String, ForeignKey('domain_schedule_revisions.revision_id'), primary_key=True)
    tenant_id = Column(Integer, ForeignKey('ktels.id'), nullable=False, index=True)
    problem_data = Column(JSON, nullable=False)
    source_data = Column(JSON, nullable=False)


def encode_problem(problem):
    data = asdict(problem)
    data['service_date'] = problem.service_date.isoformat()
    return data


def decode_problem(data):
    return SolverProblem(
        problem_id=data['problem_id'], tenant_id=data['tenant_id'], service_date=date.fromisoformat(data['service_date']),
        trips=tuple(TripSnapshot(**{**t, 'allowed_bus_types': tuple(t['allowed_bus_types'])}) for t in data['trips']),
        resources=tuple(ResourceSnapshot(**{**r, 'available_windows': None if r.get('available_windows') is None else tuple(tuple(w) for w in r['available_windows'])}) for r in data['resources']),
        chains=tuple(ChainSnapshot(tuple(c['trip_ids'])) for c in data['chains']),
        stations=tuple(data['stations']), transfer_matrix=tuple(tuple(r) for r in data['transfer_matrix']),
        parameters=SolverParametersSnapshot(**data['parameters']),
        availability_enforced=data.get('availability_enforced', False),
        availability_exempt_trip_ids=tuple(data.get('availability_exempt_trip_ids', ())),
    )


def import_reference_problem(tenant_id, service_date, revision_id):
    from dat_parser import get_full_data
    from services.legacy_loader import load_legacy_solution
    source = get_full_data()
    trips = []
    for t in source['trips']:
        midnight = datetime.combine(service_date, datetime.min.time())
        instant = normalize_service_trip(midnight + timedelta(minutes=t['start_minutes']),
                                        midnight + timedelta(minutes=t['end_minutes']),
                                        'Europe/Athens', service_date=service_date)
        trips.append(TripSnapshot(
            id=t['id'], start_station=t['startStation'], end_station=t['endStation'],
            start_minutes=instant.start_offset_minutes, end_minutes=instant.end_offset_minutes,
            duration_minutes=instant.duration_minutes,
            group=t.get('classification', {}).get('group', '000'),
            allowed_bus_types=tuple(t.get('classification', {}).get('allowedBusTypes', ['01'])),
        ))
    resources = tuple(ResourceSnapshot(r['busId'], r['driverId'], r['busId'], r['homeStation'],
                                      r.get('busAttributes', {}).get('type', '01')) for r in source['resources'])
    ids = {t.id for t in trips}
    chains = tuple(ChainSnapshot((c['incomingTripId'], c['outgoingTripId']))
                   for c in source.get('constraints', {}).get('mandatoryConnections', [])
                   if c['incomingTripId'] in ids and c['outgoingTripId'] in ids)
    problem = SolverProblem(revision_id, str(tenant_id), service_date, tuple(trips), resources, chains)
    legacy = load_legacy_solution(str(Path(__file__).resolve().parents[3] / 'shifts.dat'))
    return problem, source, legacy['assignments']


def display_metadata(snapshot):
    # The historical reference adapter explicitly normalized in Europe/Athens.
    # Operational snapshots always freeze their actual tenant timezone.
    keys = ('timezone', 'service_day_start_utc', 'day_boundaries_minutes')
    if all(key in snapshot.source_data for key in keys):
        return {key: snapshot.source_data[key] for key in keys}
    zone = snapshot.source_data.get('timezone') or 'Europe/Athens'
    computed = frozen_clock(date.fromisoformat(snapshot.problem_data['service_date']), zone)
    return {key: snapshot.source_data.get(key, value) for key, value in computed.items()}
