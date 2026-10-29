from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
import pytest

from app.domain.timetables.time_service import (
    TripInstant,
    AmbiguousLocalTimeError,
    NonExistentLocalTimeError,
    normalize_service_trip,
    make_cv_day_offsets,
)


def test_spring_forward_athens():
    """
    On 2026-03-29 in Europe/Athens:
    Clocks skip from 03:00 to 04:00 (UTC+2 to UTC+3).
    A trip departing at 02:00 local time and arriving at 05:00 local time:
    Physical duration is 2.0 hours (120 minutes), NOT 3 hours (180 minutes)!
    """
    trip = normalize_service_trip(
        local_start=datetime(2026, 3, 29, 2, 0),
        local_end=datetime(2026, 3, 29, 5, 0),
        iana_timezone="Europe/Athens",
    )
    
    assert trip.duration_minutes == 120
    assert trip.service_date == date(2026, 3, 29)
    # Start offset: midnight Athens (2026-03-29 00:00 EET = 2026-03-28 22:00 UTC)
    # Trip start: 2026-03-29 02:00 EET = 2026-03-29 00:00 UTC
    # Elapsed minutes = 120
    assert trip.start_offset_minutes == 120
    assert trip.end_offset_minutes == 240

    # Trip starting after spring forward at 04:30
    trip_after = normalize_service_trip(
        local_start=datetime(2026, 3, 29, 4, 30),
        local_end=datetime(2026, 3, 29, 6, 0),
        iana_timezone="Europe/Athens",
    )
    # Naive minutes: 4 * 60 + 30 = 270.
    # But 1 hour was skipped (03:00-04:00), so true elapsed minutes is 210!
    assert trip_after.start_offset_minutes == 210
    assert trip_after.duration_minutes == 90
    assert trip_after.end_offset_minutes == 300


def test_spring_forward_non_existent_time_raises():
    """Local time 03:30 on 2026-03-29 does not exist in Europe/Athens."""
    with pytest.raises(NonExistentLocalTimeError):
        normalize_service_trip(
            local_start=datetime(2026, 3, 29, 3, 30),
            local_end=datetime(2026, 3, 29, 5, 0),
            iana_timezone="Europe/Athens",
        )


def test_fall_back_ambiguous_time_requires_disambiguation():
    """
    On 2026-10-25 in Europe/Athens:
    Clocks fall back at 04:00 to 03:00 (UTC+3 to UTC+2).
    03:30 occurs twice. Calling without fold or disambiguation must raise AmbiguousLocalTimeError.
    Calling with fold=0 (earlier, EEST UTC+3) or fold=1 (later, EET UTC+2) disambiguates.
    """
    ambiguous_time = datetime(2026, 10, 25, 3, 30)
    with pytest.raises(AmbiguousLocalTimeError):
        normalize_service_trip(
            local_start=ambiguous_time,
            local_end=datetime(2026, 10, 25, 6, 0),
            iana_timezone="Europe/Athens",
            fold_start=None,
        )

    # First occurrence (fold=0, UTC+3, UTC=00:30)
    t0 = normalize_service_trip(
        local_start=ambiguous_time,
        local_end=datetime(2026, 10, 25, 5, 0),
        iana_timezone="Europe/Athens",
        fold_start=0,
    )
    # Midnight 2026-10-25 00:00 EEST = 2026-10-24 21:00 UTC
    # 03:30 fold=0 = 2026-10-25 00:30 UTC -> elapsed minutes = 210
    assert t0.start_offset_minutes == 210

    # Second occurrence (fold=1, UTC+2, UTC=01:30)
    t1 = normalize_service_trip(
        local_start=ambiguous_time,
        local_end=datetime(2026, 10, 25, 5, 0),
        iana_timezone="Europe/Athens",
        fold_start=1,
    )
    # 03:30 fold=1 = 2026-10-25 01:30 UTC -> elapsed minutes = 270 (60 minutes later!)
    assert t1.start_offset_minutes == 270
    assert t1.start_offset_minutes - t0.start_offset_minutes == 60


def test_overnight_service():
    """
    A service trip starting at 22:30 and ending at 02:00 next day.
    Belongs to the operational service date of departure.
    End offset extends beyond 1440 minutes.
    """
    trip = normalize_service_trip(
        local_start=datetime(2026, 5, 10, 22, 30),
        local_end=datetime(2026, 5, 11, 2, 0),
        iana_timezone="Europe/Athens",
    )

    assert trip.service_date == date(2026, 5, 10)
    assert trip.duration_minutes == 210
    assert trip.start_offset_minutes == 22 * 60 + 30  # 1350
    assert trip.end_offset_minutes == 1350 + 210  # 1560 (> 1440)


def test_make_cv_day_offsets():
    """
    Batch conversion of TripInstants into CV day offsets.
    Guarantees elapsed time continuity.
    """
    t1 = normalize_service_trip(
        local_start=datetime(2026, 6, 1, 8, 0),
        local_end=datetime(2026, 6, 1, 10, 0),
        iana_timezone="Europe/Athens",
    )
    t2 = normalize_service_trip(
        local_start=datetime(2026, 6, 1, 10, 30),
        local_end=datetime(2026, 6, 1, 12, 30),
        iana_timezone="Europe/Athens",
    )

    offsets = make_cv_day_offsets([t1, t2], service_date=date(2026, 6, 1))
    assert len(offsets) == 2
    assert offsets[0]["start_offset"] == 480
    assert offsets[0]["end_offset"] == 600
    assert offsets[1]["start_offset"] == 630
    assert offsets[1]["end_offset"] == 750
