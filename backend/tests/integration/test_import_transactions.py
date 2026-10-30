"""Restricted PostgreSQL integration for durable preview and atomic import ownership."""

import pytest
from sqlalchemy.orm import sessionmaker
from tests.integration.test_identity import identity_setup, accept


def test_resource_domain_saves_leave_transaction_commit_to_the_caller(
    identity_setup, restricted_databases
):
    from app.domain.resources.service import ResourceService
    from app.domain.resources.schemas import DriverCreate
    from app.domain.identity.tenant_session import set_tenant_scope
    from app.domain.workforce.models import WorkforceDriver

    tenant = identity_setup["first"].tenant_id
    factory = sessionmaker(bind=restricted_databases["api"])
    with factory() as db:
        set_tenant_scope(db, tenant)
        created = ResourceService(db, tenant, "drivers").create(
            DriverCreate(first_name="Atomic", last_name="Preview")
        )
        assert created["id"]
        db.rollback()
    with identity_setup["owner_factory"]() as db:
        assert (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=tenant, first_name="Atomic")
            .count()
            == 0
        )


def operator(identity_setup):
    client = identity_setup["client"]
    token = accept(client, identity_setup["first"]).json()["access_token"]
    return client, {"Authorization": "Bearer " + token}


def upload(client, headers, records, entity="drivers", content=None):
    from app.domain.imports.templates import generate_template

    return client.post(
        "/api/v1/imports",
        headers=headers,
        data={"entity": entity, "locale": "en"},
        files={
            "file": (
                "records.xlsx",
                (
                    content
                    if content is not None
                    else generate_template(entity, "en", records)
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_preview_is_persisted_without_writing_resources_and_retries_are_idempotent(
    identity_setup,
):
    from app.domain.workforce.models import WorkforceDriver

    client, headers = operator(identity_setup)
    records = [{"code": "00007", "first_name": "Νίκος", "last_name": "Δήμου"}]
    from app.domain.imports.templates import generate_template

    content = generate_template("drivers", "en", records)
    staged = upload(client, headers, records, content=content)
    assert staged.status_code == 201, staged.text
    preview = staged.json()
    assert preview["status"] == "ready" and preview["version"] == 1
    assert preview["summary"]["new"] == 1 and preview["row_count"] == 1
    tenant = identity_setup["first"].tenant_id
    with identity_setup["owner_factory"]() as db:
        assert db.query(WorkforceDriver).filter_by(tenant_id=tenant).count() == 0
    loaded = client.get("/api/v1/imports/" + preview["batch_id"], headers=headers)
    assert (
        loaded.status_code == 200
        and loaded.json()["rows"][0]["values"]["code"] == "00007"
    )
    # Fresh HTTP request/DB dependency; no per-process object is passed back to the service.
    duplicate = upload(client, headers, records, content=content)
    assert duplicate.status_code in (200, 201), duplicate.text
    assert duplicate.json()["batch_id"] == preview["batch_id"]
    committed = client.post(
        "/api/v1/imports/" + preview["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert committed.status_code == 200, committed.text
    result = committed.json()
    assert result["status"] == "committed" and result["result"]["new"] == 1
    retry = client.post(
        "/api/v1/imports/" + preview["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert retry.status_code == 200 and retry.json()["result"] == result["result"]
    with identity_setup["owner_factory"]() as db:
        rows = db.query(WorkforceDriver).filter_by(tenant_id=tenant).all()
        assert len(rows) == 1 and rows[0].code == "00007"


def test_invalid_complete_workbook_cannot_partially_create_any_resources(
    identity_setup,
):
    from app.domain.workforce.models import WorkforceDriver
    from app.domain.fleet.models import Vehicle

    client, headers = operator(identity_setup)
    staged = upload(
        client,
        headers,
        {
            "drivers": [{"first_name": "Nikos", "last_name": "Dimou"}],
            "vehicles": [{"registration_plate": "ABC-1234", "bus_type": ""}],
        },
        "all",
    )
    assert staged.status_code == 201, staged.text
    preview = staged.json()
    assert preview["status"] == "review" and preview["summary"]["invalid"] == 1
    response = client.post(
        "/api/v1/imports/" + preview["batch_id"] + "/commit",
        headers=headers,
        json={"version": preview["version"]},
    )
    assert response.status_code == 422, response.text
    with identity_setup["owner_factory"]() as db:
        tenant = identity_setup["first"].tenant_id
        assert db.query(WorkforceDriver).filter_by(tenant_id=tenant).count() == 0
        assert db.query(Vehicle).filter_by(tenant_id=tenant).count() == 0


def test_batch_correction_and_commit_check_saved_versions(identity_setup):
    client, headers = operator(identity_setup)
    staged = upload(client, headers, [{"code": "00001", "last_name": "Dimou"}])
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    row = batch["rows"][0]
    patch = {
        "version": 1,
        "rows": [{"row_id": row["row_id"], "values": {"first_name": "Nikos"}}],
    }
    corrected = client.patch(
        "/api/v1/imports/" + batch["batch_id"] + "/rows", headers=headers, json=patch
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["version"] == 2 and corrected.json()["status"] == "ready"
    assert (
        client.patch(
            "/api/v1/imports/" + batch["batch_id"] + "/rows",
            headers=headers,
            json=patch,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 2},
        ).status_code
        == 200
    )


def test_changed_target_requires_a_fresh_preview_and_omitted_rows_never_delete(
    identity_setup,
):
    from app.domain.workforce.models import WorkforceDriver

    client, headers = operator(identity_setup)
    for code, name in [("00001", "First"), ("00002", "Retain")]:
        response = client.post(
            "/api/v1/drivers",
            headers=headers,
            json={"code": code, "first_name": name, "last_name": "Driver"},
        )
        assert response.status_code == 201, response.text
    staged = upload(
        client,
        headers,
        [{"code": "00001", "first_name": "Changed", "last_name": "Driver"}],
    )
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    target = batch["rows"][0]["target"]["id"]
    response = client.patch(
        "/api/v1/drivers/" + str(target),
        headers=headers,
        json={"version": 1, "phone": "2101234567"},
    )
    assert response.status_code == 200, response.text
    stale = client.post(
        "/api/v1/imports/" + batch["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert stale.status_code == 409, stale.text
    refresh = client.post(
        "/api/v1/imports/" + batch["batch_id"] + "/refresh",
        headers=headers,
        json={"version": 1},
    )
    assert refresh.status_code == 200, refresh.text
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": refresh.json()["version"]},
        ).status_code
        == 200
    )
    with identity_setup["owner_factory"]() as db:
        rows = (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=identity_setup["first"].tenant_id)
            .order_by(WorkforceDriver.code)
            .all()
        )
        assert (
            len(rows) == 2
            and rows[0].first_name == "Changed"
            and rows[0].phone == "2101234567"
            and rows[1].first_name == "Retain"
        )


def test_missing_staff_refs_never_merge_people_by_name_without_a_decision(
    identity_setup,
):
    client, headers = operator(identity_setup)
    saved = client.post(
        "/api/v1/drivers",
        headers=headers,
        json={"code": "00001", "first_name": "Nikos", "last_name": "Dimou"},
    ).json()
    staged = upload(
        client,
        headers,
        [{"first_name": "Nikos", "last_name": "Dimou", "phone": "2101234567"}],
    )
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    row = batch["rows"][0]
    assert row["action"] == "resolve" and row["candidates"][0]["id"] == saved["id"]
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        ).status_code
        == 422
    )
    corrected = client.patch(
        "/api/v1/imports/" + batch["batch_id"] + "/rows",
        headers=headers,
        json={
            "version": 1,
            "rows": [
                {
                    "row_id": row["row_id"],
                    "resolution": {
                        "mode": "existing",
                        "target_id": saved["id"],
                        "target_version": 1,
                    },
                }
            ],
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["rows"][0]["target"]["id"] == saved["id"]
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": corrected.json()["version"]},
        ).status_code
        == 200
    )


def test_foreign_tenant_cannot_read_correct_commit_or_download_a_batch(identity_setup):
    client, headers = operator(identity_setup)
    staged = upload(client, headers, [{"first_name": "Nikos", "last_name": "Dimou"}])
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    row = batch["rows"][0]
    foreign = {
        "Authorization": "Bearer "
        + accept(client, identity_setup["second"]).json()["access_token"]
    }
    assert (
        client.get("/api/v1/imports/" + batch["batch_id"], headers=foreign).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/imports/" + batch["batch_id"] + "/errors.csv", headers=foreign
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/v1/imports/" + batch["batch_id"] + "/rows",
            headers=foreign,
            json={
                "version": 1,
                "rows": [{"row_id": row["row_id"], "values": {"first_name": "Other"}}],
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=foreign,
            json={"version": 1},
        ).status_code
        == 404
    )


def test_durable_import_tables_enforce_tenancy_identity_fks_and_append_only_audit(
    identity_setup, restricted_databases
):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.domain.imports.models import UploadBatch

    client, headers = operator(identity_setup)
    tenant = identity_setup["first"].tenant_id
    actor = client.get("/auth/me", headers=headers).json()["id"]
    driver = client.post(
        "/api/v1/drivers",
        headers=headers,
        json={"code": "001", "first_name": "Nikos", "last_name": "Dimou"},
    ).json()
    with identity_setup["owner_factory"]() as db:
        batch = UploadBatch(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            original_filename="test.xlsx",
            file_format="xlsx",
            file_bytes=1,
            checksum="0" * 64,
            source_kind="workbook",
            requested_entity="drivers",
            schema_version="ktel-import-v1",
            locale="en",
            source_locale="en",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(batch)
        db.commit()
        batch_id = batch.batch_id
    with restricted_databases["api"].begin() as connection:
        for table in (
            "domain_import_batches",
            "domain_import_rows",
            "domain_import_identities",
            "domain_import_audit",
        ):
            assert (
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                == 0
            )
        connection.execute(
            text("SELECT set_config('app.tenant_id',:tenant,true)"),
            {"tenant": str(tenant)},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM domain_import_batches")
            ).scalar_one()
            == 1
        )
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        """INSERT INTO domain_import_identities
                  (tenant_id,entity,source,external_key,driver_id,batch_id,created_by,created_at)
                  VALUES (:tenant,'drivers','test','foreign',22,:batch,:actor,now())"""
                    ),
                    {"tenant": tenant, "batch": batch_id, "actor": actor},
                )
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    text("UPDATE domain_import_audit SET event='forged' WHERE false")
                )
    with restricted_databases["worker"].begin() as connection:
        connection.execute(
            text("SELECT set_config('app.tenant_id',:tenant,true)"),
            {"tenant": str(tenant)},
        )
        with pytest.raises(DBAPIError):
            connection.execute(text("SELECT raw FROM domain_import_rows"))


def test_complete_workbook_commits_real_calendar_pairing_and_travel_inputs_together(
    identity_setup,
):
    client, headers = operator(identity_setup)
    records = {
        "stations": [
            {"code": "001", "name_el": "Αφετηρία", "is_depot": True},
            {"code": "002", "name_el": "Προορισμός"},
        ],
        "drivers": [
            {
                "code": "0001",
                "first_name": "Νίκος",
                "last_name": "Δήμου",
                "home_station": "001",
            }
        ],
        "vehicles": [
            {
                "code": "BUS001",
                "registration_plate": "KRA-1234",
                "bus_type": "02",
                "home_station": "001",
            }
        ],
        "timetable": [
            {
                "trip_code": "T001",
                "origin": "001",
                "destination": "002",
                "departure_time": "08:00",
                "arrival_time": "09:00",
                "arrival_day_offset": 0,
                "operating_weekdays": [0],
                "valid_from": "2026-01-01",
                "valid_until": "2028-12-31",
                "allowed_bus_types": ["02"],
            }
        ],
        "pairings": [
            {
                "service_date": "2026-06-01",
                "driver_ref": "0001",
                "vehicle_ref": "BUS001",
                "home_station": "001",
            }
        ],
        "transfers": [
            {"origin": "001", "destination": "002", "minutes": 30},
            {"origin": "002", "destination": "001", "minutes": 35},
        ],
    }
    staged = upload(client, headers, records, "all")
    assert staged.status_code == 201, staged.text
    preview = staged.json()
    assert preview["status"] == "ready", preview
    assert preview["row_count"] == 8 and preview["summary"]["new"] == 8
    committed = client.post(
        "/api/v1/imports/" + preview["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["result"]["new"] == 8
    timetable = client.get("/api/v1/timetables", headers=headers).json()["items"][0]
    assert (
        timetable["allowed_bus_types"] == ["02"]
        and timetable["origin"]["code"] == "001"
    )
    pair = client.get(
        "/api/v1/pairings?service_date=2026-06-01", headers=headers
    ).json()["items"][0]
    assert (
        pair["driver_name"] == "Νίκος Δήμου"
        and pair["is_confirmed"] is False
        and pair["needs_review"] is True
    )
    transfers = client.get("/api/v1/transfers", headers=headers).json()["items"]
    assert {item["minutes"] for item in transfers} == {30, 35}
    assert all(not item["needs_review"] for item in transfers)
    fleet = client.get("/api/v1/vehicles", headers=headers).json()["items"][0]
    assert fleet["capacity"] is None and fleet["bus_type"] == "02"
    # Existing independent canonical materializer/verifier gates still own day readiness.
    ready = client.get(
        "/api/v1/setup/readiness?service_date=2026-06-01", headers=headers
    ).json()
    assert ready["operating_trips"] == 1 and ready["inputs_ready"] is False
    from app.domain.imports.parsers import parse_upload

    exported = client.get(
        "/api/v1/imports/" + preview["batch_id"] + "/populated.xlsx", headers=headers
    )
    assert exported.status_code == 200, exported.text
    parsed = parse_upload(exported.content, "completed.xlsx", "all", "en")
    assert parsed.is_valid and len(parsed.rows) == 8
    replay = upload(client, headers, None, "all", content=exported.content)
    assert replay.status_code == 201, replay.text
    assert replay.json()["summary"]["new"] == 0
    assert replay.json()["summary"]["updated"] == 0


def test_unexpected_database_failure_rolls_back_earlier_import_writes_and_audit(
    identity_setup,
):
    from sqlalchemy import text
    from app.domain.workforce.models import WorkforceDriver
    from app.domain.imports.models import UploadBatch, ImportAudit

    client, headers = operator(identity_setup)
    existing = client.post(
        "/api/v1/drivers",
        headers=headers,
        json={"code": "OLD", "first_name": "Before", "last_name": "Driver"},
    )
    assert existing.status_code == 201
    staged = upload(
        client,
        headers,
        [
            {"code": "NEW", "first_name": "New", "last_name": "Driver"},
            {"code": "OLD", "first_name": "Forbidden", "last_name": "Driver"},
        ],
    )
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    assert batch["status"] == "ready"
    with identity_setup["owner_factory"]() as db:
        db.execute(
            text(
                "ALTER TABLE domain_drivers ADD CONSTRAINT test_reject_forbidden CHECK (first_name<>'Forbidden') NOT VALID"
            )
        )
        db.commit()
    response = client.post(
        "/api/v1/imports/" + batch["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert response.status_code == 409, response.text
    with identity_setup["owner_factory"]() as db:
        rows = (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=identity_setup["first"].tenant_id)
            .all()
        )
        assert len(rows) == 1 and rows[0].first_name == "Before"
        assert db.get(UploadBatch, batch["batch_id"]).status == "ready"
        assert (
            db.query(ImportAudit)
            .filter_by(batch_id=batch["batch_id"], event="committed")
            .count()
            == 0
        )


def test_bulk_write_requires_the_same_entity_permission_as_manual_entry(identity_setup):
    from app.domain.identity.service import issue_invitation

    client, headers = operator(identity_setup)
    with identity_setup["owner_factory"]() as db:
        invite = issue_invitation(
            db,
            identity_setup["first"].tenant_id,
            "import-dispatcher@example.org",
            "dispatcher",
        )
        db.commit()
    dispatcher = {
        "Authorization": "Bearer " + accept(client, invite).json()["access_token"]
    }
    response = upload(
        client, dispatcher, [{"first_name": "Nikos", "last_name": "Dimou"}]
    )
    assert response.status_code == 403, response.text
    assert client.get("/api/v1/drivers", headers=headers).json()["total"] == 0


def test_expiry_purge_removes_only_source_payload_and_keeps_committed_results(
    identity_setup,
):
    from sqlalchemy import text
    from app.domain.imports.service import ImportService
    from app.domain.imports.models import UploadBatch, UploadRow, ImportAudit
    from app.domain.workforce.models import WorkforceDriver
    from app.domain.identity.permissions import PERMISSIONS

    client, headers = operator(identity_setup)
    pending = upload(
        client,
        headers,
        [{"code": "PENDING", "first_name": "Pending", "last_name": "Driver"}],
    ).json()
    committed = upload(
        client,
        headers,
        [{"code": "SAVED", "first_name": "Saved", "last_name": "Driver"}],
    ).json()
    saved = client.post(
        "/api/v1/imports/" + committed["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert saved.status_code == 200, saved.text
    retained = upload(
        client, headers, [{"code": "KEEP", "first_name": "Keep", "last_name": "Driver"}]
    ).json()
    with identity_setup["owner_factory"]() as db:
        db.execute(
            text(
                "UPDATE domain_import_batches SET expires_at=now()-interval '1 day' WHERE batch_id IN (:a,:b)"
            ),
            {"a": pending["batch_id"], "b": committed["batch_id"]},
        )
        db.commit()
    # Expired data stops being accessible even before the scheduled physical cleanup runs.
    assert (
        client.get(
            "/api/v1/imports/" + pending["batch_id"], headers=headers
        ).status_code
        == 410
    )
    assert (
        client.get(
            "/api/v1/imports/" + committed["batch_id"] + "/errors.csv", headers=headers
        ).status_code
        == 410
    )
    with identity_setup["owner_factory"]() as db:
        source = ImportService(
            db, identity_setup["first"].tenant_id, None, PERMISSIONS["admin"]
        )
        assert source.purge_expired() == 2
        db.commit()
    retry = client.post(
        "/api/v1/imports/" + committed["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    )
    assert retry.status_code == 200 and retry.json()["result"] == saved.json()["result"]
    with identity_setup["owner_factory"]() as db:
        assert (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=identity_setup["first"].tenant_id)
            .count()
            == 1
        )
        assert db.query(UploadRow).filter_by(batch_id=retained["batch_id"]).count() == 1
        assert (
            db.query(UploadRow)
            .filter(
                UploadRow.batch_id.in_([pending["batch_id"], committed["batch_id"]])
            )
            .count()
            == 0
        )
        assert db.get(UploadBatch, pending["batch_id"]).status == "purged"
        assert db.get(UploadBatch, committed["batch_id"]).status == "committed"
        assert db.get(UploadBatch, committed["batch_id"]).original_filename == ""
        assert (
            db.query(ImportAudit)
            .filter_by(batch_id=committed["batch_id"], event="committed")
            .count()
            == 1
        )


def test_discard_does_not_delete_resources_or_prevent_a_fresh_upload(identity_setup):
    from app.domain.imports.templates import generate_template

    client, headers = operator(identity_setup)
    content = generate_template(
        "drivers", "en", [{"first_name": "Nikos", "last_name": "Dimou"}]
    )
    first = upload(client, headers, [], content=content).json()
    discarded = client.post(
        "/api/v1/imports/" + first["batch_id"] + "/discard",
        headers=headers,
        json={"version": 1},
    )
    assert discarded.status_code == 200, discarded.text
    assert (
        discarded.json()["status"] == "discarded"
        and not discarded.json()["raw_available"]
    )
    assert (
        client.post(
            "/api/v1/imports/" + first["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        ).status_code
        == 410
    )
    fresh = upload(client, headers, [], content=content)
    assert fresh.status_code == 201 and fresh.json()["batch_id"] != first["batch_id"]
    assert client.get("/api/v1/drivers", headers=headers).json()["total"] == 0


def asgi_scope(headers=()):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/imports",
        "raw_path": b"/api/v1/imports",
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=bounded-test"),
            *headers,
        ],
    }


@pytest.mark.asyncio
async def test_upload_authorizes_before_reading_any_file_bytes(identity_setup):
    from main import app

    reads = 0
    sent = []

    async def receive():
        nonlocal reads
        reads += 1
        raise AssertionError("Anonymous request body must not be consumed")

    async def send(message):
        sent.append(message)

    await app(asgi_scope(), receive, send)
    assert (
        reads == 0
        and next(
            item["status"] for item in sent if item["type"] == "http.response.start"
        )
        == 401
    )


@pytest.mark.asyncio
async def test_chunked_upload_is_bounded_before_multipart_spooling(
    identity_setup, monkeypatch
):
    from main import app
    from config import settings

    client, headers = operator(identity_setup)
    monkeypatch.setattr(settings, "IMPORT_MAX_UPLOAD_BYTES", 1024)
    reads = 0
    sent = []

    async def receive():
        nonlocal reads
        reads += 1
        assert reads < 32, "The upload stream was not bounded"
        return {"type": "http.request", "body": b"x" * 4096, "more_body": True}

    async def send(message):
        sent.append(message)

    auth = headers["Authorization"].encode()
    await app(asgi_scope([(b"authorization", auth)]), receive, send)
    assert (
        0 < reads < 20
        and next(
            item["status"] for item in sent if item["type"] == "http.response.start"
        )
        == 413
    )


def test_generated_preview_refs_are_stable_and_source_aliases_do_not_rename_people(
    identity_setup,
):
    from app.domain.workforce.models import WorkforceDriver

    client, headers = operator(identity_setup)
    first = upload(
        client, headers, [{"first_name": "Nikos", "last_name": "Dimou"}]
    ).json()
    reference = first["rows"][0]["proposed_ref"]
    assert reference
    loaded = client.get("/api/v1/imports/" + first["batch_id"], headers=headers).json()
    assert loaded["rows"][0]["proposed_ref"] == reference
    saved = client.post(
        "/api/v1/imports/" + first["batch_id"] + "/commit",
        headers=headers,
        json={"version": 1},
    ).json()
    identifier = saved["result"]["records"][0]["id"]
    second = upload(
        client,
        headers,
        [{"code": "EXTERNAL-07", "first_name": "Nikos", "last_name": "Dimou"}],
    ).json()
    assert second["rows"][0]["action"] == "resolve"
    resolved = client.patch(
        "/api/v1/imports/" + second["batch_id"] + "/rows",
        headers=headers,
        json={
            "version": 1,
            "rows": [
                {
                    "row_id": second["rows"][0]["row_id"],
                    "resolution": {
                        "mode": "existing",
                        "target_id": identifier,
                        "target_version": 1,
                    },
                }
            ],
        },
    ).json()
    assert (
        client.post(
            "/api/v1/imports/" + second["batch_id"] + "/commit",
            headers=headers,
            json={"version": resolved["version"]},
        ).status_code
        == 200
    )
    third = upload(
        client,
        headers,
        [{"code": "EXTERNAL-07", "first_name": "Updated", "last_name": "Dimou"}],
    ).json()
    assert third["rows"][0]["target"]["id"] == identifier and third["status"] == "ready"
    assert (
        client.post(
            "/api/v1/imports/" + third["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        ).status_code
        == 200
    )
    with identity_setup["owner_factory"]() as db:
        driver = db.get(WorkforceDriver, identifier)
        assert driver.code == reference and driver.first_name == "Updated"


def test_repeated_unreferenced_names_require_an_explicit_new_person_decision(
    identity_setup,
):
    client, headers = operator(identity_setup)
    batch = upload(
        client,
        headers,
        [
            {"first_name": "Nikos", "last_name": "Dimou"},
            {"first_name": "Nikos", "last_name": "Dimou"},
        ],
    ).json()
    assert batch["status"] == "review" and batch["summary"]["needs_match"] == 2
    refs = [row["proposed_ref"] for row in batch["rows"]]
    assert all(refs) and len(set(refs)) == 2
    corrected = client.patch(
        "/api/v1/imports/" + batch["batch_id"] + "/rows",
        headers=headers,
        json={
            "version": 1,
            "rows": [
                {"row_id": row["row_id"], "resolution": {"mode": "new"}}
                for row in batch["rows"]
            ],
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert (
        corrected.json()["status"] == "ready"
        and [row["proposed_ref"] for row in corrected.json()["rows"]] == refs
    )
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 2},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/drivers", headers=headers).json()["total"] == 2


def test_two_source_aliases_cannot_apply_conflicting_updates_to_one_person(
    identity_setup,
):
    client, headers = operator(identity_setup)
    target = client.post(
        "/api/v1/drivers",
        headers=headers,
        json={"code": "CANONICAL", "first_name": "Nikos", "last_name": "Dimou"},
    ).json()
    batch = upload(
        client,
        headers,
        [{"code": "EXTERNAL", "first_name": "Nikos", "last_name": "Dimou"}],
    ).json()
    matched = client.patch(
        "/api/v1/imports/" + batch["batch_id"] + "/rows",
        headers=headers,
        json={
            "version": 1,
            "rows": [
                {
                    "row_id": batch["rows"][0]["row_id"],
                    "resolution": {
                        "mode": "existing",
                        "target_id": target["id"],
                        "target_version": 1,
                    },
                }
            ],
        },
    ).json()
    assert (
        client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": matched["version"]},
        ).status_code
        == 200
    )
    conflict = upload(
        client,
        headers,
        [
            {"code": "CANONICAL", "first_name": "First update", "last_name": "Dimou"},
            {"code": "EXTERNAL", "first_name": "Second update", "last_name": "Dimou"},
        ],
    ).json()
    assert conflict["status"] == "review" and conflict["summary"]["invalid"] == 2
    assert all(
        any(issue["code"] == "duplicate_target" for issue in row["issues"])
        for row in conflict["rows"]
    )


def test_populated_download_preserves_committed_values_and_generated_references(
    identity_setup,
):
    from app.domain.imports.parsers import parse_upload
    from app.domain.workforce.models import WorkforceDriver

    client, headers = operator(identity_setup)
    original = client.post(
        "/api/v1/drivers",
        headers=headers,
        json={
            "code": "00009",
            "first_name": "Before",
            "last_name": "Driver",
            "phone": "2101234567",
        },
    )
    assert original.status_code == 201, original.text
    staged = upload(
        client,
        headers,
        [
            {"code": "00009", "first_name": "After", "last_name": "Driver"},
            {"first_name": "New", "last_name": "Person"},
        ],
    ).json()
    url = "/api/v1/imports/" + staged["batch_id"]
    assert client.get(url + "/populated.xlsx", headers=headers).status_code == 409
    staged = client.patch(
        url + "/rows",
        headers=headers,
        json={
            "version": staged["version"],
            "rows": [
                {"row_id": staged["rows"][1]["row_id"], "resolution": {"mode": "new"}}
            ],
        },
    ).json()
    saved = client.post(
        url + "/commit", headers=headers, json={"version": staged["version"]}
    )
    assert saved.status_code == 200, saved.text
    # A historical download describes this commit, even after later manual corrections.
    with identity_setup["owner_factory"]() as db:
        row = (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=identity_setup["first"].tenant_id, code="00009")
            .one()
        )
        row.first_name = "Later"
        db.commit()
    exported = client.get(url + "/populated.xlsx", headers=headers)
    assert exported.status_code == 200, exported.text
    parsed = parse_upload(exported.content, "saved.xlsx", "all", "en")
    assert parsed.is_valid
    assert len(parsed.rows) == 2
    first, second = parsed.rows
    assert first.values["code"] == "00009" and first.values["phone"] == "2101234567"
    assert first.values["first_name"] == "After"
    assert second.values["code"] and second.values["first_name"] == "New"


def test_simultaneous_save_retries_commit_once(identity_setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.domain.workforce.models import WorkforceDriver
    from app.domain.imports.models import ImportAudit

    client, headers = operator(identity_setup)
    batch = upload(
        client, headers, [{"code": "ONCE", "first_name": "One", "last_name": "Person"}]
    ).json()
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(save) for _ in range(2)]
        results = [request.result(timeout=30) for request in requests]
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json()["result"] == results[1].json()["result"]
    with identity_setup["owner_factory"]() as db:
        assert (
            db.query(WorkforceDriver)
            .filter_by(tenant_id=identity_setup["first"].tenant_id, code="ONCE")
            .count()
            == 1
        )
        assert (
            db.query(ImportAudit)
            .filter_by(batch_id=batch["batch_id"], event="committed")
            .count()
            == 1
        )


def test_expired_source_retry_waits_for_inflight_commit_without_purging_it(
    identity_setup, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread, main_thread
    from datetime import timedelta
    import time
    from app.domain.imports.models import UploadBatch, utcnow
    from app.domain.imports.service import ImportService
    from app.domain.imports.templates import generate_template

    client, headers = operator(identity_setup)
    content = generate_template(
        "drivers", "en", [{"code": "RACE", "first_name": "Safe", "last_name": "Retry"}]
    )
    batch = upload(client, headers, None, content=content).json()
    with identity_setup["owner_factory"]() as db:
        db.get(UploadBatch, batch["batch_id"]).expires_at = utcnow() + timedelta(
            milliseconds=500
        )
        db.commit()
    waiting = Event()
    original_lock = ImportService.lock

    def observed_lock(service):
        if current_thread() is not main_thread():
            waiting.set()
        return original_lock(service)

    with identity_setup["owner_factory"]() as db:
        source = ImportService(
            db,
            identity_setup["first"].tenant_id,
            client.get("/auth/me", headers=headers).json()["id"],
            {"imports.write", "drivers.write"},
        )
        saved = source.commit(batch["batch_id"], 1)
        result = saved.result_summary
        time.sleep(0.6)
        monkeypatch.setattr(ImportService, "lock", observed_lock)
        with ThreadPoolExecutor(max_workers=1) as pool:
            retry = pool.submit(upload, client, headers, None, content=content)
            try:
                assert waiting.wait(10)
            finally:
                db.commit()
            response = retry.result(timeout=20)
    assert response.status_code == 201, response.text
    assert response.json()["batch_id"] == batch["batch_id"]
    assert response.json()["status"] == "committed"
    assert response.json()["result"] == result
    assert response.json()["raw_available"] is True


def test_commit_identity_lookup_count_does_not_grow_with_uploaded_rows(
    identity_setup, restricted_databases
):
    from sqlalchemy import event

    client, headers = operator(identity_setup)
    batch = upload(
        client,
        headers,
        [
            {"code": f"REF{i}", "first_name": "Bulk", "last_name": str(i)}
            for i in range(12)
        ],
    ).json()
    reads = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "FROM domain_import_identities" in statement
        ):
            reads.append(1)

    engine = restricted_databases["api"]
    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = client.post(
            "/api/v1/imports/" + batch["batch_id"] + "/commit",
            headers=headers,
            json={"version": 1},
        )
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    assert (
        len(reads) <= 2
    ), f"Expected two catalog reads, observed {len(reads)} identity lookups"
