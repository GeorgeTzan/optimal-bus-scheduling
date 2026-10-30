import csv
import io
import json
import re
from datetime import datetime, date, time
from typing import List, Dict, Any, Tuple
from app.domain.imports.legacy_staging import StagedRow


class ValidationError(Exception):
    """Raised when an import batch fails validation during commit."""

    pass


TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def _parse_hh_mm(val: str) -> Tuple[int, int]:
    val = val.strip()
    match = TIME_PATTERN.match(val)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    # Try 4-digit format "0830"
    if len(val) == 4 and val.isdigit():
        h, m = int(val[:2]), int(val[2:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    raise ValueError(f"Invalid time format: '{val}'. Expected HH:MM or HHMM.")


def parse_and_validate_rows(
    content: bytes | str,
    file_format: str,
    service_date: date,
) -> Tuple[List[StagedRow], List[str]]:
    """
    Parses raw content into StagedRows and performs strict validation:
    - required headers / fields
    - time format parsing
    - duplicate ID detection
    """
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    staged_rows: List[StagedRow] = []
    global_issues: List[str] = []

    raw_items: List[Dict[str, Any]] = []

    fmt = file_format.lower()
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(text.strip()))
        for row in reader:
            raw_items.append(dict(row))
    elif fmt == "json":
        data = json.loads(text)
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict) and "trips" in data:
            raw_items = data["trips"]
        else:
            raise ValidationError(
                "JSON root must be a list of trip objects or contain a 'trips' list."
            )
    elif fmt == "dat":
        # Legacy .DAT parsing
        lines = text.splitlines()
        in_trips = False
        for line in lines:
            line = line.strip()
            if line == "[ListOfDrom]":
                in_trips = True
                continue
            if line.startswith("[") and in_trips:
                in_trips = False
                break
            if in_trips and line:
                parts = line.split()
                if len(parts) >= 10:
                    raw_items.append(
                        {
                            "trip_code": parts[0],
                            "origin": parts[1],
                            "destination": parts[2],
                            "start_time": parts[8],
                            "end_time": parts[9],
                        }
                    )
    else:
        raise ValidationError(
            f"Unsupported import format: '{file_format}'. Supported: csv, json, dat."
        )

    seen_trip_codes = set()
    duplicate_codes = set()

    for idx, raw in enumerate(raw_items, start=1):
        row_errors: List[str] = []
        parsed: Dict[str, Any] = {}

        trip_code = str(raw.get("trip_code") or raw.get("id") or "").strip()
        origin = str(raw.get("origin") or raw.get("start_station") or "").strip()
        destination = str(
            raw.get("destination") or raw.get("end_station") or ""
        ).strip()
        start_str = str(raw.get("start_time") or "").strip()
        end_str = str(raw.get("end_time") or "").strip()

        if not trip_code:
            row_errors.append("Missing required field: trip_code")
        else:
            if trip_code in seen_trip_codes:
                duplicate_codes.add(trip_code)
                row_errors.append(f"Duplicate trip_code: '{trip_code}'")
            seen_trip_codes.add(trip_code)

        if not origin:
            row_errors.append("Missing required field: origin")
        if not destination:
            row_errors.append("Missing required field: destination")

        start_h, start_m = None, None
        end_h, end_m = None, None

        try:
            start_h, start_m = _parse_hh_mm(start_str)
        except ValueError as e:
            row_errors.append(f"Invalid start_time: {str(e)}")

        try:
            end_h, end_m = _parse_hh_mm(end_str)
        except ValueError as e:
            row_errors.append(f"Invalid end_time: {str(e)}")

        if start_h is not None and end_h is not None:
            parsed = {
                "trip_code": trip_code,
                "origin": origin,
                "destination": destination,
                "start_hour": start_h,
                "start_minute": start_m,
                "end_hour": end_h,
                "end_minute": end_m,
                "service_date": service_date,
            }

        staged_rows.append(
            StagedRow(
                row_index=idx,
                raw_data=raw,
                parsed_data=parsed if not row_errors else None,
                errors=row_errors,
                is_valid=len(row_errors) == 0,
            )
        )

    if duplicate_codes:
        global_issues.append(
            f"Found {len(duplicate_codes)} duplicate trip codes: {sorted(list(duplicate_codes))[:5]}"
        )

    return staged_rows, global_issues
