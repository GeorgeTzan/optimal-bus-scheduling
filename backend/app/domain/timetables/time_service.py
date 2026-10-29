from dataclasses import dataclass
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional


class LocalTimeResolutionError(ValueError):
    code='local_time_resolution'
    def __init__(self,message,*,param_name=None,local_dt=None,timezone_name=None):
        super().__init__(message)
        self.issues=[{'code':self.code,'field':'departure_time' if param_name=='start' else 'arrival_time',
                     'clock_time':local_dt.strftime('%H:%M') if local_dt else None,
                     'date':local_dt.date().isoformat() if local_dt else None,
                     'timezone':timezone_name,'message':message}]


class AmbiguousLocalTimeError(LocalTimeResolutionError):
    """A repeated clock needs an explicit earlier/later occurrence."""
    code='ambiguous_local_time'


class NonExistentLocalTimeError(LocalTimeResolutionError):
    """A skipped clock must be corrected, not assigned an invented instant."""
    code='nonexistent_local_time'


@dataclass(frozen=True)
class TripInstant:
    start_utc: datetime
    end_utc: datetime
    service_date: date
    duration_minutes: int
    start_offset_minutes: int
    end_offset_minutes: int


def _resolve_wall_clock(dt: datetime, tz: ZoneInfo, fold: Optional[int], param_name: str) -> datetime:
    """Validates and converts a local wall clock datetime to timezone-aware with DST checks."""
    if dt.tzinfo is not None:
        # Already tz-aware
        return dt.astimezone(timezone.utc)

    dt_f0 = dt.replace(tzinfo=tz, fold=0)
    dt_f1 = dt.replace(tzinfo=tz, fold=1)
    
    off0 = dt_f0.utcoffset()
    off1 = dt_f1.utcoffset()

    # PEP 495: In a gap (spring forward), off0 < off1
    if off0 is not None and off1 is not None and off0 < off1:
        raise NonExistentLocalTimeError(
            f"Local {param_name} time {dt.strftime('%Y-%m-%d %H:%M:%S')} does not exist in {tz.key} "
            f"due to daylight saving spring forward leap.",
            param_name=param_name,local_dt=dt,timezone_name=tz.key
        )

    # PEP 495: In an overlap (fall back), off0 > off1
    if off0 is not None and off1 is not None and off0 > off1:
        if fold is None:
            raise AmbiguousLocalTimeError(
                f"Local {param_name} time {dt.strftime('%Y-%m-%d %H:%M:%S')} is ambiguous in {tz.key}. "
                f"Specify fold=0 (earlier occurrence) or fold=1 (later occurrence).",
                param_name=param_name,local_dt=dt,timezone_name=tz.key
            )
        dt_with_fold = dt.replace(fold=fold)
    else:
        dt_with_fold = dt

    tz_aware = dt_with_fold.replace(tzinfo=tz)
    return tz_aware.astimezone(timezone.utc)


def normalize_service_trip(
    local_start: datetime,
    local_end: datetime,
    iana_timezone: str = "Europe/Athens",
    fold_start: Optional[int] = None,
    fold_end: Optional[int] = None,
    service_date: Optional[date] = None,
) -> TripInstant:
    """
    Normalizes local start and end times into authoritative UTC instants, calculating
    true elapsed physical duration and service-day offsets preserving DST reality.
    """
    tz = ZoneInfo(iana_timezone)
    resolved={};errors=[]
    for name,value,fold in (('start',local_start,fold_start),('end',local_end,fold_end)):
        try:resolved[name]=_resolve_wall_clock(value,tz,fold,name)
        except LocalTimeResolutionError as error:errors.append(error)
    if errors:
        first=errors[0]
        first.issues=[issue for error in errors for issue in error.issues]
        raise first
    start_utc=resolved['start'];end_utc=resolved['end']

    if end_utc < start_utc:
        raise ValueError(f"Trip end ({end_utc.isoformat()}) cannot be before start ({start_utc.isoformat()})")

    duration_seconds = (end_utc - start_utc).total_seconds()
    duration_minutes = int(round(duration_seconds / 60))

    if service_date is None:
        service_date = local_start.date()

    # Local midnight instant in UTC for the service date
    local_midnight = datetime(service_date.year, service_date.month, service_date.day, 0, 0, tzinfo=tz)
    local_midnight_utc = local_midnight.astimezone(timezone.utc)

    start_offset_minutes = int(round((start_utc - local_midnight_utc).total_seconds() / 60))
    end_offset_minutes = start_offset_minutes + duration_minutes

    return TripInstant(
        start_utc=start_utc,
        end_utc=end_utc,
        service_date=service_date,
        duration_minutes=duration_minutes,
        start_offset_minutes=start_offset_minutes,
        end_offset_minutes=end_offset_minutes,
    )


def make_cv_day_offsets(
    trips: List[TripInstant],
    service_date: date,
    iana_timezone: str = "Europe/Athens",
) -> List[Dict[str, Any]]:
    """
    Computes CV Solver input offsets for a list of trips relative to a service date.
    """
    results = []
    for trip in trips:
        results.append({
            "service_date": str(service_date),
            "start_offset": trip.start_offset_minutes,
            "end_offset": trip.end_offset_minutes,
            "duration": trip.duration_minutes,
            "start_utc": trip.start_utc.isoformat(),
            "end_utc": trip.end_utc.isoformat(),
        })
    return results
