"""A generously bounded capacity regression for the actual supported workbook size."""

import time
from app.domain.imports.templates import generate_template


def test_populated_5000_service_template_export_avoids_quadratic_row_scanning():
    rows = [
        {
            "trip_code": f"T{index:05d}",
            "origin": "Origin",
            "destination": "Destination",
            "departure_time": "08:00",
            "arrival_time": "09:30",
            "arrival_day_offset": 0,
            "operating_weekdays": [0, 1, 2, 3, 4],
            "valid_from": "2026-01-01",
            "valid_until": "2028-12-31",
            "allowed_bus_types": ["02"],
        }
        for index in range(5000)
    ]
    started = time.perf_counter()
    content = generate_template("timetable", "en", rows)
    assert len(content) > 1000
    assert time.perf_counter() - started < 10
