"""Durable reviewed imports. Callers commit once; domain writes never commit a prefix."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
import hashlib
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_
from app.domain.identity.tenant_session import set_tenant_scope
from app.domain.imports.contracts import ImportLimits, SCHEMA_VERSION, ImportRejected
from app.domain.imports.models import (
    UploadBatch,
    UploadRow,
    ImportIdentity,
    ImportAudit,
    TARGET_COLUMNS,
    utcnow,
)
from app.domain.imports.parsers import parse_upload
from app.domain.imports.revalidation import validate_saved_rows
from app.domain.imports.planning import ImportPlanner, json_ready
from app.domain.imports.catalog import Catalog, MODELS, SOURCE, ref_existing, ref_key
from app.domain.imports.issues import parser_issue, issue_view
from app.domain.imports.template_schema import SHEETS
from app.domain.resources.service import ResourceService
from app.domain.resources.schemas import (
    DriverCreate,
    DriverPatch,
    VehicleCreate,
    VehiclePatch,
    StationCreate,
    StationPatch,
)
from app.domain.timetables.operations import OperationsService
from app.domain.timetables.operational_schemas import (
    TimetableCreate,
    TimetablePatch,
    PairingCreate,
    PairingPatch,
    TransferCreate,
    TransferPatch,
)
from app.domain.timetables.models import DailyPairing, StationTransfer
from db.models import KTEL
from config import settings

PERMISSIONS = {
    "drivers": "drivers.write",
    "vehicles": "fleet.write",
    "stations": "timetable.write",
    "timetable": "timetable.write",
    "pairings": "schedule.write",
    "transfers": "timetable.write",
    "connections": "timetable.write",
}
CREATE = {
    "drivers": DriverCreate,
    "vehicles": VehicleCreate,
    "stations": StationCreate,
    "timetable": TimetableCreate,
}
PATCH = {
    "drivers": DriverPatch,
    "vehicles": VehiclePatch,
    "stations": StationPatch,
    "timetable": TimetablePatch,
}


def configured_limits():
    defaults = ImportLimits()
    rows = getattr(settings, "IMPORT_MAX_ROWS", defaults.max_rows)
    size = getattr(settings, "IMPORT_MAX_UPLOAD_BYTES", defaults.max_upload_bytes)
    if not 1 <= rows <= defaults.max_rows or not 1 <= size <= defaults.max_upload_bytes:
        raise RuntimeError(
            "Import limits must stay within the measured 5000-row / 5 MiB boundary"
        )
    return ImportLimits(max_rows=rows, max_upload_bytes=size)


def aware(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class ImportService:
    def __init__(self, db, tenant_id, actor_id, permissions, *, limits=None):
        set_tenant_scope(db, tenant_id)
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.permissions = set(permissions)
        self.limits = limits or configured_limits()

    def query(self, model):
        return self.db.query(model).filter(model.tenant_id == self.tenant_id)

    def require(self, permission):
        if permission not in self.permissions:
            raise HTTPException(
                403,
                {
                    "code": "import_permission",
                    "message": "Your role cannot make this change. Ask an administrator or choose records you can maintain.",
                },
            )

    def require_entities(self, entities):
        self.require("imports.write")
        for entity in entities:
            self.require(PERMISSIONS[entity])

    def lock(self):
        return self.db.query(KTEL).filter_by(id=self.tenant_id).with_for_update().one()

    def get(self, batch_id, lock=False):
        query = self.query(UploadBatch).filter_by(batch_id=batch_id)
        if lock:
            query = query.populate_existing().with_for_update()
        batch = query.first()
        if batch is None:
            raise HTTPException(404, "This upload was not found in your organization.")
        return batch

    def rows(self, batch):
        return (
            self.query(UploadRow)
            .filter_by(batch_id=batch.batch_id)
            .order_by(UploadRow.position)
            .all()
        )

    def check_mutable(self, batch, version):
        if (
            batch.status in ("discarded", "purged")
            or aware(batch.expires_at) <= utcnow()
        ):
            raise HTTPException(
                410,
                {
                    "code": "upload_expired",
                    "message": "This preview is no longer available. Upload the file again.",
                },
            )
        if batch.status == "committed":
            raise HTTPException(
                409,
                {
                    "code": "already_committed",
                    "message": "These changes are already saved.",
                },
            )
        if batch.version != version:
            raise HTTPException(
                409,
                {
                    "code": "stale_version",
                    "message": "Someone updated this preview. Reload it before saving.",
                },
            )

    def audit(self, batch, event, details):
        self.db.add(
            ImportAudit(
                tenant_id=self.tenant_id,
                batch_id=batch.batch_id,
                actor_id=self.actor_id,
                actor_type="retention" if self.actor_id is None else "user",
                event=event,
                batch_version=batch.version,
                details=json_ready(details),
            )
        )

    def stage(self, content, filename, entity, locale):
        self.require("imports.write")
        if entity not in (*SHEETS, "all") or locale not in ("en", "el"):
            raise HTTPException(422, "Choose a supported record type and language.")
        filename = PurePosixPath(filename.replace("\\", "/")).name
        file_format = PurePosixPath(filename).suffix.casefold().removeprefix(".")
        if file_format not in ("xlsx", "csv"):
            raise HTTPException(
                422,
                {
                    "code": "unsupported_format",
                    "message": "Upload an XLSX workbook or UTF-8 CSV template.",
                },
            )
        checksum = hashlib.sha256(content).hexdigest()
        source_kind = "workbook" if file_format == "xlsx" else entity

        def replay():
            return (
                self.query(UploadBatch)
                .filter_by(
                    checksum=checksum,
                    source_kind=source_kind,
                    schema_version=SCHEMA_VERSION,
                )
                .filter(UploadBatch.status.notin_(("discarded", "purged")))
                .first()
            )

        existing = replay()
        if existing is not None:
            self.require_entities(existing.entities)
            if existing.status == "committed" or aware(existing.expires_at) > utcnow():
                return existing, True
            # Expired previews never resurrect; retention frees their source key.
            self.lock()
            existing = self.get(existing.batch_id, lock=True)
            if existing.status == "committed" or aware(existing.expires_at) > utcnow():
                return existing, True
            self._purge_payload(existing)
        try:
            workbook = parse_upload(
                content, filename, entity, locale, limits=self.limits
            )
        except ImportRejected as error:
            raise HTTPException(
                422, {"code": error.code, "message": error.message}
            ) from None
        if not workbook.rows:
            raise HTTPException(
                422,
                {
                    "code": "empty_import",
                    "message": "Add at least one record below the template headings.",
                },
            )
        entities = list(dict.fromkeys(row.entity for row in workbook.rows))
        self.require_entities(entities)
        self.lock()
        existing = replay()
        if existing is not None:
            self.require_entities(existing.entities)
            return existing, True
        days = getattr(settings, "IMPORT_STAGING_DAYS", 7)
        if days < 1:
            raise RuntimeError("Import staging retention must be positive")
        batch = UploadBatch(
            tenant_id=self.tenant_id,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            original_filename="".join(
                char for char in filename if ord(char) >= 32 and ord(char) != 127
            )[:200],
            file_format=file_format,
            file_bytes=len(content),
            checksum=checksum,
            source_kind=source_kind,
            requested_entity=entity,
            schema_version=SCHEMA_VERSION,
            locale=locale,
            source_locale=workbook.source_locale,
            entities=entities,
            row_count=len(workbook.rows),
            file_issues=[
                asdict(issue) for issue in workbook.issues if issue.row in (None, 1)
            ],
            expires_at=utcnow() + timedelta(days=days),
        )
        self.db.add(batch)
        self.db.flush()
        for position, row in enumerate(workbook.rows):
            self.db.add(
                UploadRow(
                    tenant_id=self.tenant_id,
                    batch_id=batch.batch_id,
                    position=position,
                    entity=row.entity,
                    sheet=row.sheet,
                    row_number=row.row,
                    raw=row.raw,
                    cell_types=row.cell_types,
                    source_columns=row.columns,
                    source_cells=row.cells,
                    values=row.values,
                    issues=[parser_issue(issue, row.entity) for issue in row.issues],
                )
            )
        self.db.flush()
        self.build_preview(batch, self.rows(batch))
        self.audit(
            batch,
            "uploaded",
            {
                "row_count": batch.row_count,
                "entities": entities,
                "summary": batch.summary,
            },
        )
        self.db.flush()
        return batch, False

    def build_preview(self, batch, rows):
        with self.db.no_autoflush:
            planner = ImportPlanner(self.db, batch, rows)
            summary, snapshot, stations, aliases = planner.build()
        if summary["new_stations"]:
            self.require("timetable.write")
        for row in rows:
            row.plan = json_ready(row.plan)
        batch.summary = json_ready(summary)
        batch.source_snapshot = json_ready(snapshot)
        batch.station_plan = json_ready(stations)
        batch.status = (
            "ready"
            if not batch.file_issues
            and not summary["invalid"]
            and not summary["needs_match"]
            else "review"
        )
        batch.updated_at = utcnow()
        batch.updated_by = self.actor_id
        return planner, aliases

    def revalidate(self, batch, rows):
        validated, file_issues = validate_saved_rows(batch, rows, self.limits)
        for row, parsed in validated:
            row.raw = parsed.raw
            row.values = parsed.values
            row.cell_types = parsed.cell_types
            row.source_columns = parsed.columns
            row.source_cells = parsed.cells
            row.issues = [parser_issue(issue, row.entity) for issue in parsed.issues]
        batch.file_issues = [
            asdict(issue) for issue in file_issues if issue.row in (None, 1)
        ]
        return self.build_preview(batch, rows)

    def correct(self, batch_id, request):
        self.lock()
        batch = self.get(batch_id, lock=True)
        self.require_entities(batch.entities)
        self.check_mutable(batch, request.version)
        rows = self.rows(batch)
        by_id = {row.id: row for row in rows}
        for correction in request.rows:
            row = by_id.get(correction.row_id)
            if row is None:
                raise HTTPException(422, "Choose a row from this upload.")
            allowed = {column.key for column in SHEETS[row.entity][2]}
            if set(correction.values) - allowed:
                raise HTTPException(422, "Only template fields can be corrected.")
            if correction.resolution and correction.resolution.mode == "existing":
                if row.entity not in MODELS:
                    raise HTTPException(
                        422, "Choose references for this dated record instead."
                    )
                target = (
                    self.query(MODELS[row.entity])
                    .filter_by(id=correction.resolution.target_id)
                    .first()
                )
                if target is None:
                    raise HTTPException(
                        422, "Choose a saved record from your organization."
                    )
                if target.version != correction.resolution.target_version:
                    raise HTTPException(
                        409,
                        {
                            "code": "source_changed",
                            "message": "The selected record changed. Review it before matching.",
                        },
                    )
            row.raw = {**row.raw, **correction.values}
            row.cell_types = {
                **row.cell_types,
                **{
                    key: (
                        "b"
                        if type(value) is bool
                        else "n" if type(value) in (int, float) else "s"
                    )
                    for key, value in correction.values.items()
                },
            }
            if correction.resolution:
                row.resolution = correction.resolution.model_dump()
            elif {"code", "trip_code", "registration_plate"}.intersection(
                correction.values
            ):
                row.resolution = {}
        choices = dict(batch.station_resolutions)
        known_names = {
            name
            for row in rows
            for key, name in row.values.items()
            if key in ("home_station", "origin", "destination")
            and isinstance(name, str)
        }
        for choice in request.stations:
            self.require("timetable.write")
            if choice.name not in known_names:
                raise HTTPException(422, "Choose a station used by this upload.")
            if choice.mode == "existing":
                target = (
                    self.query(MODELS["stations"])
                    .filter_by(id=choice.target_id)
                    .first()
                )
                if target is None:
                    raise HTTPException(
                        422, "Choose a saved station from your organization."
                    )
                if target.version != choice.target_version:
                    raise HTTPException(
                        409,
                        {
                            "code": "source_changed",
                            "message": "The selected station changed. Review it again.",
                        },
                    )
            choices[choice.name] = choice.model_dump(exclude={"name"})
        batch.station_resolutions = choices
        self.revalidate(batch, rows)
        batch.version += 1
        self.audit(
            batch,
            "corrected",
            {
                "rows": [
                    {
                        "position": by_id[item.row_id].position,
                        "fields": sorted(item.values),
                        "matched": item.resolution is not None,
                    }
                    for item in request.rows
                ],
                "station_choices": len(request.stations),
                "summary": batch.summary,
            },
        )
        self.db.flush()
        return batch

    def refresh(self, batch_id, version):
        self.lock()
        batch = self.get(batch_id, lock=True)
        self.require_entities(batch.entities)
        self.check_mutable(batch, version)
        self.revalidate(batch, self.rows(batch))
        batch.version += 1
        self.audit(batch, "refreshed", {"summary": batch.summary})
        self.db.flush()
        return batch

    def resolve(self, ref, saved, planner):
        if ref_key(ref) in saved:
            return saved[ref_key(ref)]
        if "id" in ref:
            result = planner.catalog.records[ref["kind"]].get(ref["id"])
            if result is not None:
                return result
        raise HTTPException(
            422,
            {
                "code": "dependency_invalid",
                "message": "Correct the related row before saving this upload.",
            },
        )

    def commit(self, batch_id, version):
        self.lock()
        batch = self.get(batch_id, lock=True)
        self.require_entities(batch.entities)
        if batch.status == "committed":
            return batch
        self.check_mutable(batch, version)
        if batch.status != "ready":
            raise HTTPException(
                422,
                {
                    "code": "needs_review",
                    "message": "Correct or resolve the highlighted rows before saving.",
                },
            )
        catalog = Catalog(self.db, self.tenant_id)
        if not catalog.matches_snapshot(batch.source_snapshot):
            raise HTTPException(
                409,
                {
                    "code": "source_changed",
                    "message": "Saved records changed. Refresh this preview before saving.",
                },
            )
        rows = self.rows(batch)
        planner, aliases = self.revalidate(batch, rows)
        if batch.status != "ready":
            raise HTTPException(
                422,
                {
                    "code": "needs_review",
                    "message": "Review the updated validation before saving.",
                },
            )
        saved = {}
        mappings = []
        for station in {
            item.get("key"): item for item in batch.station_plan if item.get("key")
        }.values():
            self.require("timetable.write")
            dto = StationCreate(code=station["code"], name_el=station["name_el"])
            created = ResourceService(self.db, self.tenant_id, "stations").create(dto)
            target = self.query(MODELS["stations"]).filter_by(id=created["id"]).one()
            saved[ref_key(station["ref"])] = target
        ordered = sorted(
            rows,
            key=lambda row: (
                (
                    1
                    if row.entity == "stations"
                    and row.plan.get("payload", {}).get("is_active") is False
                    else 0
                ),
                {
                    "stations": 0,
                    "drivers": 1,
                    "vehicles": 2,
                    "timetable": 3,
                    "connections": 4,
                    "transfers": 5,
                    "pairings": 6,
                }[row.entity],
                0 if row.entity == "connections" and row.plan.get("payload", {}).get("is_active") is False else 1,
                row.position,
            ),
        )
        try:
            for row in ordered:
                plan = row.plan
                kind = row.entity
                payload = dict(plan["payload"])
                for column, ref in plan["relations"].items():
                    payload[column] = self.resolve(ref, saved, planner).id
                if kind in ("pairings", "transfers", "connections"):
                    target = self.apply_dated(row, payload, planner, saved)
                elif plan["action"] == "unchanged":
                    target = planner.catalog.records[kind][plan["target"]["id"]]
                elif plan["action"] == "new":
                    request = CREATE[kind].model_validate(payload)
                    result = (
                        OperationsService(
                            self.db, self.tenant_id, self.actor_id
                        ).create_template(request)
                        if kind == "timetable"
                        else ResourceService(self.db, self.tenant_id, kind).create(
                            request
                        )
                    )
                    target = self.query(MODELS[kind]).filter_by(id=result["id"]).one()
                else:
                    request = PATCH[kind].model_validate(
                        {"version": plan["target"]["version"], **payload}
                    )
                    result = (
                        OperationsService(
                            self.db, self.tenant_id, self.actor_id
                        ).update_template(plan["target"]["id"], request)
                        if kind == "timetable"
                        else ResourceService(self.db, self.tenant_id, kind).update(
                            plan["target"]["id"], request
                        )
                    )
                    target = self.query(MODELS[kind]).filter_by(id=result["id"]).one()
                saved[ref_key(plan["ref"])] = target
                if kind == 'connections':
                    reference = self.resolve(plan['relations']['incoming_template_id'],saved,planner).trip_code + ' → ' + self.resolve(plan['relations']['outgoing_template_id'],saved,planner).trip_code
                elif kind == 'timetable': reference = target.trip_code
                elif kind == 'pairings': reference = target.service_date.isoformat()
                elif kind == 'transfers': reference = row.values['origin'] + ' → ' + row.values['destination']
                else: reference = target.code
                mappings.append(
                    {
                        "entity": kind,
                        "row": row.row_number,
                        "row_id": row.id,
                        "id": target.id,
                        "reference": reference,
                        "operation": plan["action"],
                    }
                )
                row.plan = {
                    **plan,
                    "saved_id": target.id,
                    "saved_reference": reference,
                    "saved_version": target.version,
                }
            for alias in aliases:
                target = self.resolve(alias["ref"], saved, planner)
                # The tenant lock fences every alias writer; the catalog was read
                # under that lock and already validated against the source snapshot.
                current = planner.catalog.aliases.get((alias["entity"], alias["key"]))
                if current:
                    if current.target_id != target.id:
                        raise HTTPException(
                            409,
                            {
                                "code": "identity_changed",
                                "message": "A source reference was matched differently. Refresh before saving.",
                            },
                        )
                    continue
                self.db.add(
                    ImportIdentity(
                        tenant_id=self.tenant_id,
                        entity=alias["entity"],
                        source=SOURCE,
                        external_key=alias["key"],
                        batch_id=batch.batch_id,
                        created_by=self.actor_id,
                        **{TARGET_COLUMNS[alias["entity"]]: target.id},
                    )
                )
            self.db.flush()
            self.db.info.pop('reference_reservations',None)
        except ValidationError:
            raise HTTPException(
                422,
                {
                    "code": "needs_review",
                    "message": "A related record no longer meets its entry rules. Refresh and review this upload.",
                },
            ) from None
        from app.domain.imports.exports import capture_committed_rows

        capture_committed_rows(self, rows, saved)
        result = {**batch.summary, "records": mappings}
        pairings = [
            target for key, target in saved.items() if isinstance(target, DailyPairing)
        ]
        if pairings:
            result["pairings_need_confirmation"] = sum(
                OperationsService(self.db, self.tenant_id).pairing_view(target)[
                    "needs_review"
                ]
                for target in pairings
            )
        batch.result_summary = json_ready(result)
        batch.status = "committed"
        batch.version += 1
        batch.committed_at = utcnow()
        batch.updated_at = utcnow()
        batch.expires_at = utcnow() + timedelta(
            days=getattr(settings, "IMPORT_COMMITTED_RAW_DAYS", 30)
        )
        self.audit(
            batch,
            "committed",
            {
                "summary": {
                    key: value for key, value in result.items() if key != "records"
                },
                "records": mappings,
                "checksum": batch.checksum,
            },
        )
        self.db.flush()
        return batch

    def apply_dated(self, row, payload, planner, saved):
        if row.entity == "connections":
            from app.domain.timetables.connections import ConnectionService,ConnectionCreate,ConnectionPatch
            from app.domain.timetables.models import ServiceConnection
            plan = row.plan
            identifier = plan['target']['id'] if plan['target'] else None
            if plan['action'] == 'unchanged': return self.query(ServiceConnection).filter_by(id=identifier).one()
            service = ConnectionService(self.db,self.tenant_id,self.actor_id)
            if identifier:
                result = service.update(identifier,ConnectionPatch(version=plan['target']['version'],is_active=payload['is_active']))
            else:
                incoming=self.resolve(plan['relations']['incoming_template_id'],saved,planner)
                outgoing=self.resolve(plan['relations']['outgoing_template_id'],saved,planner)
                result=service.create(ConnectionCreate(**payload,incoming_template_version=incoming.version,outgoing_template_version=outgoing.version))
            return self.query(ServiceConnection).filter_by(id=result['id']).one()
        plan = row.plan
        ops = OperationsService(self.db, self.tenant_id, self.actor_id)
        model = DailyPairing if row.entity == "pairings" else StationTransfer
        identifier = plan["target"]["id"] if plan["target"] else None
        if plan["action"] == "unchanged":
            return self.query(model).filter_by(id=identifier).one()
        if row.entity == "pairings":
            driver = self.resolve(plan["relations"]["driver_id"], saved, planner)
            vehicle = self.resolve(plan["relations"]["vehicle_id"], saved, planner)
            home = self.resolve(plan["relations"]["home_station_id"], saved, planner)
            payload.update(
                driver_version=driver.version,
                vehicle_version=vehicle.version,
                home_station_version=home.version,
                confirm=False,
            )
            if identifier:
                payload.pop("service_date", None)
                request = PairingPatch.model_validate(
                    {"version": plan["target"]["version"], **payload}
                )
            else:
                request = PairingCreate.model_validate(payload)
            result = ops.save_pairing(request, identifier)
        else:
            if identifier:
                payload.pop("origin_station_id", None)
                payload.pop("destination_station_id", None)
                request = TransferPatch.model_validate(
                    {"version": plan["target"]["version"], **payload}
                )
            else:
                request = TransferCreate.model_validate(payload)
            result = ops.save_transfer(request, identifier)
        return self.query(model).filter_by(id=result["id"]).one()

    def raw_available(self, batch):
        return (
            batch.raw_purged_at is None
            and aware(batch.expires_at) > utcnow()
            and batch.status not in ("discarded", "purged")
        )

    def require_raw(self, batch):
        if not self.raw_available(batch):
            raise HTTPException(
                410,
                {
                    "code": "upload_expired",
                    "message": "The source copy has expired. Your saved records and import result are retained.",
                },
            )

    def purge_expired(self, *, limit=100, now=None):
        self.require("imports.write")
        self.lock()
        if not 1 <= limit <= 100:
            raise ValueError("Purge at most 100 batches per transaction")
        selected = (
            self.query(UploadBatch)
            .populate_existing()
            .filter(
                UploadBatch.raw_purged_at.is_(None),
                UploadBatch.expires_at <= (now or utcnow()),
            )
            .order_by(UploadBatch.expires_at, UploadBatch.batch_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .all()
        )
        for batch in selected:
            self._purge_payload(batch)
        return len(selected)

    def _purge_payload(self, batch):
        self.query(UploadRow).filter_by(batch_id=batch.batch_id).delete(
            synchronize_session=False
        )
        batch.station_plan = []
        batch.station_resolutions = {}
        batch.source_snapshot = {}
        batch.file_issues = []
        batch.raw_purged_at = utcnow()
        batch.original_filename = ""
        batch.status = "committed" if batch.status == "committed" else "purged"
        batch.version += 1
        self.audit(batch, "purged", {"canonical_records_deleted": 0})
        self.db.flush()

    def discard(self, batch_id, version):
        self.lock()
        batch = self.get(batch_id, lock=True)
        self.require_entities(batch.entities)
        if batch.status == "discarded":
            return batch
        self.check_mutable(batch, version)
        self._purge_payload(batch)
        batch.status = "discarded"
        self.audit(batch, "discarded", {"canonical_records_deleted": 0})
        self.db.flush()
        return batch

    def view(self, batch, *, page=1, page_size=25, action=None, locale=None):
        locale = locale or batch.locale
        raw_available = self.raw_available(batch)
        if not raw_available and batch.status in ("ready", "review"):
            self.require_raw(batch)
        source = self.query(UploadRow).filter_by(batch_id=batch.batch_id)
        if not raw_available:
            source = source.filter(UploadRow.id < 0)
        if action:
            source = source.filter(UploadRow.plan["action"].as_string() == action)
        total = source.count()
        rows = (
            source.order_by(UploadRow.position)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        def item(row):
            plan = row.plan
            return {
                "row_id": row.id,
                "entity": row.entity,
                "sheet": row.sheet,
                "row": row.row_number,
                "raw": row.raw,
                "values": row.values,
                "action": plan.get("action"),
                "target": plan.get("target"),
                "candidates": plan.get("candidates", []),
                "proposed_ref": plan.get("saved_reference")
                or (plan.get("target") or {}).get("reference")
                or plan.get("payload", {}).get("code")
                or row.planned_reference,
                "changed_fields": plan.get("changed_fields", []),
                "before": plan.get("before", {}),
                "proposed": plan.get("payload", {}),
                "relations": plan.get("relations", {}),
                "issues": [
                    issue_view(issue, locale) for issue in plan.get("issues", [])
                ],
            }

        return {
            "batch_id": batch.batch_id,
            "version": batch.version,
            "status": batch.status,
            "filename": batch.original_filename if raw_available else "",
            "file_format": batch.file_format,
            "schema_version": batch.schema_version,
            "source_locale": batch.source_locale,
            "row_count": batch.row_count,
            "summary": batch.summary,
            "result": batch.result_summary,
            "entities": batch.entities,
            "issues": (
                [issue_view(issue, locale) for issue in batch.file_issues]
                if raw_available
                else []
            ),
            "stations": batch.station_plan[:100] if raw_available else [],
            "station_count": len(batch.station_plan) if raw_available else 0,
            "created_at": batch.created_at,
            "expires_at": batch.expires_at,
            "raw_available": raw_available,
            "rows": [item(row) for row in rows],
            "rows_total": total,
            "page": page,
            "page_size": page_size,
        }
