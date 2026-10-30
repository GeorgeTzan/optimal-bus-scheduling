"""Isolated reference-fixture adapter; never mounted as a customer import API."""

import uuid
from datetime import datetime, date, time
from typing import Dict, Optional, List
from sqlalchemy.orm import Session

from app.domain.imports.legacy_staging import ImportBatch, ImportPreview, ImportResult
from app.domain.imports.legacy_validation import (
    parse_and_validate_rows,
    ValidationError,
)
from app.domain.timetables.models import Station, TripInstance
from app.domain.timetables.time_service import normalize_service_trip
from app.domain.identity.tenant_session import tenant_transaction


class LegacyReferenceImportService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self._batches = db.info.setdefault("legacy_reference_imports", {})

    def stage_import(
        self,
        content: bytes | str,
        file_format: str = "csv",
        service_date: date | str = "2026-06-01",
    ) -> ImportBatch:
        if isinstance(service_date, str):
            parsed_date = datetime.strptime(service_date, "%Y-%m-%d").date()
        else:
            parsed_date = service_date

        staged_rows, issues = parse_and_validate_rows(content, file_format, parsed_date)
        valid_count = sum(1 for r in staged_rows if r.is_valid)
        error_count = sum(len(r.errors) for r in staged_rows)

        batch_id = str(uuid.uuid4())
        batch = ImportBatch(
            batch_id=batch_id,
            tenant_id=self.tenant_id,
            file_format=file_format,
            service_date=parsed_date,
            status="staged" if error_count == 0 else "validated",
            total_rows=len(staged_rows),
            valid_rows=valid_count,
            error_count=error_count,
            staged_rows=staged_rows,
        )
        self._batches[batch_id] = batch
        return batch

    def preview_import(self, batch_id: str) -> ImportPreview:
        batch = self._batches.get(batch_id)
        if not batch:
            raise KeyError(f"Import batch '{batch_id}' not found.")
        if batch.tenant_id != self.tenant_id:
            raise PermissionError(
                "Access denied: import batch belongs to another tenant."
            )

        sample_rows = [r.raw_data for r in batch.staged_rows[:5]]
        all_issues = []
        for r in batch.staged_rows:
            all_issues.extend(r.errors)

        return ImportPreview(
            batch_id=batch.batch_id,
            total_rows=batch.total_rows,
            valid_rows=batch.valid_rows,
            error_count=batch.error_count,
            is_valid=batch.error_count == 0,
            sample_rows=sample_rows,
            issues=all_issues,
        )

    def commit_import(
        self, batch_id: str, expected_version: Optional[int] = None
    ) -> ImportResult:
        batch = self._batches.get(batch_id)
        if not batch:
            raise KeyError(f"Import batch '{batch_id}' not found.")
        if batch.tenant_id != self.tenant_id:
            raise PermissionError(
                "Access denied: import batch belongs to another tenant."
            )

        if batch.error_count > 0 or batch.valid_rows != batch.total_rows:
            raise ValidationError(
                f"Cannot commit batch with {batch.error_count} validation errors."
            )

        with tenant_transaction(self.db, tenant_id=self.tenant_id):
            # Resolve or create stations
            station_map: Dict[str, Station] = {}
            existing_stations = (
                self.db.query(Station).filter(Station.tenant_id == self.tenant_id).all()
            )
            for s in existing_stations:
                station_map[s.code] = s
                station_map[s.name_el] = s
                station_map[s.name_en] = s

            for staged in batch.staged_rows:
                p = staged.parsed_data
                if not p:
                    continue

                origin_name = p["origin"]
                dest_name = p["destination"]

                # Ensure origin station exists
                if origin_name not in station_map:
                    new_st = Station(
                        tenant_id=self.tenant_id,
                        code=origin_name[:10].upper(),
                        name_el=origin_name,
                        name_en=origin_name,
                    )
                    self.db.add(new_st)
                    self.db.flush()
                    station_map[origin_name] = new_st

                # Ensure dest station exists
                if dest_name not in station_map:
                    new_st = Station(
                        tenant_id=self.tenant_id,
                        code=dest_name[:10].upper(),
                        name_el=dest_name,
                        name_en=dest_name,
                    )
                    self.db.add(new_st)
                    self.db.flush()
                    station_map[dest_name] = new_st

                # Normalize times to UTC instants
                start_dt = datetime(
                    batch.service_date.year,
                    batch.service_date.month,
                    batch.service_date.day,
                    p["start_hour"],
                    p["start_minute"],
                )
                # Check for cross-midnight arrival
                end_day = batch.service_date.day
                if (p["end_hour"], p["end_minute"]) < (
                    p["start_hour"],
                    p["start_minute"],
                ):
                    # Next day
                    end_day += 1

                end_dt = datetime(
                    batch.service_date.year,
                    batch.service_date.month,
                    end_day,
                    p["end_hour"],
                    p["end_minute"],
                )

                instant = normalize_service_trip(
                    local_start=start_dt,
                    local_end=end_dt,
                    iana_timezone="Europe/Athens",
                    service_date=batch.service_date,
                )

                trip = TripInstance(
                    tenant_id=self.tenant_id,
                    trip_code=p["trip_code"],
                    service_date=batch.service_date,
                    origin_station_id=station_map[origin_name].id,
                    destination_station_id=station_map[dest_name].id,
                    start_utc=instant.start_utc,
                    end_utc=instant.end_utc,
                    properties={"raw_data": staged.raw_data},
                )
                self.db.add(trip)

            batch.status = "committed"
            self.db.flush()

        return ImportResult(
            batch_id=batch.batch_id,
            committed_rows=batch.total_rows,
            service_date=batch.service_date,
        )
