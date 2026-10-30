"""Synthetic parser capacity probe; no database writes or production customer records.

Run: uv run python -m tests.performance.benchmark_imports --entity timetable --format xlsx --rows 5000 --long-text
Reports the whole process peak RSS, including template generation, as a conservative measurement.
"""

import argparse
import io
import json
import resource
import time
import zipfile
from app.domain.imports.templates import generate_template
from app.domain.imports.parsers import parse_upload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--entity", choices=("drivers", "timetable"), default="timetable"
    )
    parser.add_argument("--format", choices=("xlsx", "csv"), default="xlsx")
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--long-text", action="store_true")
    args = parser.parse_args()
    records = []
    for number in range(args.rows):
        if args.entity == "drivers":
            row = {
                "code": f"{number:06d}",
                "first_name": "Ν" * 160 if args.long_text else "Νίκος",
                "last_name": "Δ" * 160 if args.long_text else "Δήμου",
            }
        else:
            row = {
                "trip_code": f"T{number:06d}",
                "origin": "Α" * 160 if args.long_text else "Αφετηρία",
                "destination": "Π" * 160 if args.long_text else "Προορισμός",
                "departure_time": "08:00",
                "arrival_time": "09:30",
                "arrival_day_offset": 0,
                "operating_weekdays": [0, 1, 2, 3, 4],
                "valid_from": "2026-01-01",
                "valid_until": "2028-12-31",
                "allowed_bus_types": ["02"],
            }
        records.append(row)
    generated = time.perf_counter()
    content = generate_template(args.entity, "el", records, file_format=args.format)
    generation = time.perf_counter() - generated
    expanded = len(content)
    if args.format == "xlsx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            expanded = sum(member.file_size for member in archive.infolist())
    started = time.perf_counter()
    result = parse_upload(content, "capacity." + args.format, args.entity, "el")
    elapsed = time.perf_counter() - started
    assert result.is_valid and len(result.rows) == args.rows
    print(
        json.dumps(
            {
                "entity": args.entity,
                "format": args.format,
                "rows": len(result.rows),
                "long_text": args.long_text,
                "upload_bytes": len(content),
                "expanded_bytes": expanded,
                "generation_seconds": round(generation, 3),
                "parse_seconds": round(elapsed, 3),
                "peak_process_rss_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
