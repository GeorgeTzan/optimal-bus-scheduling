"""Freeze calendar-day boundaries so a UI never assumes DST days have 24 hours."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def frozen_clock(service_date: date, zone_name: str):
    zone = ZoneInfo(zone_name)

    def midnight(offset):
        return datetime.combine(
            service_date + timedelta(days=offset), datetime.min.time(), tzinfo=zone
        ).astimezone(timezone.utc)

    start = midnight(0)
    return {
        "timezone": zone_name,
        "service_day_start_utc": start.isoformat(),
        "day_boundaries_minutes": [
            int((midnight(offset) - start).total_seconds() / 60) for offset in range(4)
        ],
    }
