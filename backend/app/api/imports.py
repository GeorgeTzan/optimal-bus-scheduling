"""Authenticated, bounded uploads and durable reviewed import operations."""

import csv
import io
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.requests import Request as BufferedRequest
from starlette.responses import Response
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.imports.service import ImportService, configured_limits, PERMISSIONS
from app.domain.imports.schemas import BatchCorrection, VersionRequest
from app.domain.imports.models import UploadBatch
from app.domain.imports.templates import generate_template, escape_csv
from app.domain.imports.template_schema import SHEETS

router = APIRouter(prefix="/api/v1/imports", tags=["Reviewed imports"])


def service(db, user):
    return ImportService(db, user.ktel_id, user.id, user.permissions)


def saved(db, source, batch, **view_options):
    db.commit()
    return source.view(batch, **view_options)


@router.get("/capabilities")
def capabilities(
    locale: Literal["en", "el"] = "en", user=Depends(require_permission("imports.read"))
):
    limits = configured_limits()
    return {
        "schema_version": "ktel-import-v1",
        "formats": ["xlsx", "csv"],
        "entities": list(SHEETS),
        "columns": {
            kind: [
                {
                    "key": column.key,
                    "label": column.label(locale),
                    "required": column.required,
                    "kind": column.kind,
                }
                for column in schema[2]
            ]
            for kind, schema in SHEETS.items()
        },
        "write_entities": [
            kind for kind in SHEETS if PERMISSIONS[kind] in user.permissions
        ],
        "limits": limits.__dict__,
    }


@router.get("/templates/{entity}")
def template(
    entity: str,
    locale: Literal["en", "el"] = "en",
    format: Literal["xlsx", "csv"] = "xlsx",
    user=Depends(require_permission("resources.read")),
):
    if entity not in (*SHEETS, "all") or entity == "all" and format == "csv":
        raise HTTPException(422, "Choose a supported template.")
    content = generate_template(
        entity, locale, file_format=format, limits=configured_limits()
    )
    return Response(
        content,
        media_type=(
            "text/csv; charset=utf-8"
            if format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="ktel-import-v1-{entity}-{locale}.{format}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("", status_code=201)
async def upload(
    request: Request,
    user=Depends(require_permission("imports.write")),
    db: Session = Depends(get_db),
):
    # Declaring Request rather than File/Form makes authorization happen before body parsing.
    # Bound streaming before the multipart parser creates any temporary upload files.
    limits = configured_limits()
    maximum = limits.max_upload_bytes + 65536
    declared = request.headers.get("content-length")
    if declared:
        try:
            length = int(declared)
        except ValueError:
            raise HTTPException(400, "Invalid upload length.") from None
        if length < 0:
            raise HTTPException(400, "Invalid upload length.")
        if length > maximum:
            raise HTTPException(
                413,
                {
                    "code": "upload_limit",
                    "message": "The file is too large. Split it into smaller files.",
                },
            )
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum:
            raise HTTPException(
                413,
                {
                    "code": "upload_limit",
                    "message": "The file is too large. Split it into smaller files.",
                },
            )
        body.extend(chunk)
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    buffered = BufferedRequest(request.scope, receive=receive)
    async with buffered.form(
        max_files=1, max_fields=2, max_part_size=limits.max_upload_bytes
    ) as form:
        if set(form) - {"file", "entity", "locale"}:
            raise HTTPException(
                422, "Only the file, record type and language belong in an upload."
            )
        file = form.get("file")
        entity = form.get("entity", "drivers")
        locale = form.get("locale", "en")
        if not isinstance(file, UploadFile) or not file.filename:
            raise HTTPException(422, "Choose a file to upload.")
        if not isinstance(entity, str) or not isinstance(locale, str):
            raise HTTPException(422, "Choose a record type and language.")
        content = await file.read(limits.max_upload_bytes + 1)
        if len(content) > limits.max_upload_bytes:
            raise HTTPException(
                413,
                {
                    "code": "upload_limit",
                    "message": "The file is too large. Split it into smaller files.",
                },
            )
        source = service(db, user)

        def stage():
            batch, _ = source.stage(content, file.filename, entity, locale)
            return saved(db, source, batch)

        return await run_in_threadpool(stage)


@router.get("")
def listing(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user=Depends(require_permission("imports.read")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    query = source.query(UploadBatch)
    total = query.count()
    batches = (
        query.order_by(UploadBatch.created_at.desc(), UploadBatch.batch_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "batch_id": batch.batch_id,
                "version": batch.version,
                "status": batch.status,
                "filename": (
                    batch.original_filename if source.raw_available(batch) else ""
                ),
                "row_count": batch.row_count,
                "summary": batch.summary,
                "created_at": batch.created_at,
                "expires_at": batch.expires_at,
            }
            for batch in batches
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{batch_id}")
def detail(
    batch_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    action: Literal["new", "update", "unchanged", "invalid", "resolve"] | None = None,
    locale: Literal["en", "el"] | None = None,
    user=Depends(require_permission("imports.read")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    return source.view(
        source.get(batch_id),
        page=page,
        page_size=page_size,
        action=action,
        locale=locale,
    )


@router.patch("/{batch_id}/rows")
def correct(
    batch_id: str,
    request: BatchCorrection,
    user=Depends(require_permission("imports.write")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    return saved(db, source, source.correct(batch_id, request))


@router.post("/{batch_id}/refresh")
def refresh(
    batch_id: str,
    request: VersionRequest,
    user=Depends(require_permission("imports.write")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    return saved(db, source, source.refresh(batch_id, request.version))


@router.post("/{batch_id}/commit")
def commit(
    batch_id: str,
    request: VersionRequest,
    user=Depends(require_permission("imports.write")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    return saved(db, source, source.commit(batch_id, request.version))


@router.post("/{batch_id}/discard")
def discard(
    batch_id: str,
    request: VersionRequest,
    user=Depends(require_permission("imports.write")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    return saved(db, source, source.discard(batch_id, request.version))


@router.get("/{batch_id}/errors.csv")
def errors(
    batch_id: str,
    locale: Literal["en", "el"] | None = None,
    user=Depends(require_permission("imports.read")),
    db: Session = Depends(get_db),
):
    from app.domain.imports.issues import issue_view

    source = service(db, user)
    batch = source.get(batch_id)
    source.require_raw(batch)
    language = locale or batch.locale
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Sheet", "Row", "Cell", "Column", "Issue", "Original value"])
    for issue in batch.file_issues:
        value = issue_view(issue, language)
        writer.writerow(
            [
                escape_csv(value.get(key) or "")
                for key in ("sheet", "row", "cell", "column", "message")
            ]
            + [""]
        )
    for row in source.rows(batch):
        for issue in row.plan.get("issues", []):
            value = issue_view(issue, language)
            original = row.raw.get(value.get("field"))
            if original is None:
                original = next(
                    (
                        item["value"]
                        for item in row.raw.get("_unmapped_columns", [])
                        if item["cell"] == value.get("cell")
                    ),
                    "",
                )
            writer.writerow(
                [
                    escape_csv(value.get(key) or "")
                    for key in ("sheet", "row", "cell", "column", "message")
                ]
                + [escape_csv(original if original is not None else "")]
            )
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="ktel-import-{batch.batch_id}-errors.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{batch_id}/populated.xlsx")
def populated(
    batch_id: str,
    locale: Literal["en", "el"] | None = None,
    user=Depends(require_permission("imports.read")),
    db: Session = Depends(get_db),
):
    source = service(db, user)
    batch = source.get(batch_id)
    source.require_raw(batch)
    if batch.status != "committed":
        raise HTTPException(
            409,
            {
                "code": "not_committed",
                "message": "Save the reviewed upload before downloading its completed workbook.",
            },
        )
    records = {entity: [] for entity in SHEETS}
    for row in source.rows(batch):
        records[row.entity].append(row.plan["after_export"])
    content = generate_template(
        "all", locale or batch.source_locale, records, limits=configured_limits()
    )
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="ktel-import-{batch.batch_id}-completed.xlsx"',
            "Cache-Control": "private, no-store",
        },
    )
