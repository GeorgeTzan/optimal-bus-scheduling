"""Bundled fixtures and deliberate error routes are never normal customer operations."""

from config import settings
from tests.integration.test_identity import identity_setup, accept


def test_normal_customer_cannot_retrieve_or_run_the_shared_bundled_fixture(
    identity_setup, monkeypatch
):
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", False, raising=False)
    client = identity_setup["client"]
    headers = {
        "Authorization": "Bearer "
        + accept(client, identity_setup["first"]).json()["access_token"]
    }
    for path in (
        "/data",
        "/trips",
        "/drivers",
        "/schedule",
        "/sentry-debug",
        "/trigger-test-error",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, (path, response.status_code)
    for path in ("/solve", "/solve/cv", "/solve/legacy", "/solve/lahc"):
        response = client.post(path, headers=headers, json={})
        assert response.status_code == 404, (path, response.status_code)
    assert (
        client.post(
            "/api/v1/scheduling/revisions/import-reference",
            headers=headers,
            json={"service_date": "2026-06-01"},
        ).status_code
        == 404
    )


def test_existing_reference_is_explicit_read_only_history_outside_reference_tools(
    identity_setup, monkeypatch
):
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", True, raising=False)
    client = identity_setup["client"]
    headers = {
        "Authorization": "Bearer "
        + accept(client, identity_setup["first"]).json()["access_token"]
    }
    imported = client.post(
        "/api/v1/scheduling/revisions/import-reference",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert imported.status_code == 201, imported.text
    revision = imported.json()
    assert (
        client.get("/api/v1/scheduling/revisions/active", headers=headers).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/scheduling/revisions/active?source_kind=reference_archive",
            headers=headers,
        ).json()["revision_id"]
        == revision["revision_id"]
    )
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", False)
    assert (
        client.get(
            "/api/v1/scheduling/revisions/" + revision["revision_id"], headers=headers
        ).status_code
        == 200
    )
    row = revision["assignments"][0]
    blocked = client.post(
        "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/patches",
        headers=headers,
        json={
            "version": 1,
            "patches": [
                {
                    "trip_id": row["trip_id"],
                    "new_resource_id": row["resource_id"],
                    "is_locked": True,
                }
            ],
        },
    )
    assert blocked.status_code == 409, blocked.text[:500]
    assert (
        client.post(
            "/optimization/runs",
            headers=headers,
            json={"snapshot_id": revision["revision_id"]},
        ).status_code
        == 409
    )
    other = {
        "Authorization": "Bearer "
        + accept(client, identity_setup["second"]).json()["access_token"]
    }
    assert (
        client.get(
            "/api/v1/scheduling/revisions/active?source_kind=reference_archive",
            headers=other,
        ).status_code
        == 404
    )
