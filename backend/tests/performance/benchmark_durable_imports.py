"""Explicit PostgreSQL boundary probe; run with pytest -s on this file."""

import time
import os
import resource
from tests.integration.test_identity import identity_setup
from tests.integration.conftest import postgres_engine, restricted_databases
from tests.integration.test_import_transactions import operator, upload


def test_five_thousand_driver_rows_stage_commit_and_export(identity_setup, monkeypatch):
    row_count = int(os.getenv("KTEL_IMPORT_PROBE_ROWS", "5000"))
    from config import settings

    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", row_count)
    client, headers = operator(identity_setup)
    rows = [
        {"code": f"D{i:06}", "first_name": "Οδηγός", "last_name": f"Δοκιμή {i}"}
        for i in range(row_count)
    ]
    started = time.perf_counter()
    staged = upload(client, headers, rows)
    assert staged.status_code == 201, staged.text[:500]
    batch = staged.json()
    assert batch["status"] == "ready" and batch["summary"]["new"] == row_count
    previewed = time.perf_counter()
    saved = client.post(
        "/api/v1/imports/" + batch["batch_id"] + "/commit",
        headers=headers,
        json={"version": batch["version"]},
    )
    assert saved.status_code == 200, saved.text[:500]
    assert saved.json()["result"]["new"] == row_count
    committed = time.perf_counter()
    export = client.get(
        "/api/v1/imports/" + batch["batch_id"] + "/populated.xlsx", headers=headers
    )
    assert export.status_code == 200
    print(
        {
            "rows": row_count,
            "stage_seconds": round(previewed - started, 3),
            "commit_seconds": round(committed - previewed, 3),
            "export_seconds": round(time.perf_counter() - committed, 3),
            "process_peak_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
            ),
        }
    )
