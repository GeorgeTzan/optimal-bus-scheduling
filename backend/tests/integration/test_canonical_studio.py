"""Customer-owned dated inputs reach Studio without any bundled operational fixture."""

import pytest
from tests.integration.test_identity import identity_setup, accept
from tests.integration.test_operational_snapshots import (
    setup_operator,
    template_payload,
)


def prepared_customer(identity_setup, service_date="2026-06-01", working_time=True):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(
        identity_setup
    )
    template = create(
        "timetables",
        template_payload(
            origin,
            destination,
            departure_time="08:00",
            arrival_time="09:00",
            arrival_day_offset=0,
        ),
    )
    pairing = create(
        "pairings",
        {
            "driver_id": driver["id"],
            "vehicle_id": vehicle["id"],
            "home_station_id": origin["id"],
            "service_date": service_date,
            "confirm": True,
            "driver_version": 1,
            "vehicle_version": 1,
            "home_station_version": 1,
        },
    )
    for first, second, minutes in (
        (origin, destination, 30),
        (destination, origin, 35),
    ):
        create(
            "transfers",
            {
                "origin_station_id": first["id"],
                "destination_station_id": second["id"],
                "minutes": minutes,
            },
        )
    if working_time:
        from tests.helpers.working_time import give_working_time
        give_working_time(client, headers)
    return client, headers, template, pairing, driver


def test_customer_inputs_create_a_persisted_initially_unassigned_revision(
    identity_setup,
):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    assert (
        client.get(
            "/api/v1/scheduling/revisions/active?service_date=2026-06-01",
            headers=headers,
        ).status_code
        == 404
    )
    response = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert response.status_code == 201, response.text
    revision = response.json()
    assert revision["source_kind"] == "operational"
    assert revision["problem"]["service_date"] == "2026-06-01"
    assert len(revision["assignments"]) == len(revision["source_trips"]) == 1
    assert revision["assignments"][0]["resource_id"] == "UNASSIGNED"
    assert revision["source_trips"][0]["trip_code"] == "T001"
    assert revision["source_trips"][0]["origin"]["name_el"] == "Αφετηρία"
    assert revision["source_resources"][0]["driver_name"] == "Νίκος Δήμου"
    assert revision["problem"]["resources"][0]["bus_type"] == "02"
    loaded = client.get(
        "/api/v1/scheduling/revisions/active?service_date=2026-06-01", headers=headers
    )
    assert loaded.status_code == 200 and loaded.json() == revision
    assert (
        client.get(
            "/api/v1/scheduling/revisions/active?service_date=2026-06-02",
            headers=headers,
        ).status_code
        == 404
    )
    other = {
        "Authorization": "Bearer "
        + accept(client, identity_setup["second"]).json()["access_token"]
    }
    assert (
        client.get(
            "/api/v1/scheduling/revisions/active?service_date=2026-06-01", headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/patches",
            headers=other,
            json={
                "version": 1,
                "patches": [
                    {
                        "trip_id": revision["assignments"][0]["trip_id"],
                        "new_resource_id": "UNASSIGNED",
                    }
                ],
            },
        ).status_code
        == 404
    )


def test_unprepared_service_day_returns_actionable_readiness_without_creating_a_revision(
    identity_setup,
):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(
        identity_setup
    )
    create(
        "timetables",
        template_payload(
            origin,
            destination,
            departure_time="08:00",
            arrival_time="09:00",
            arrival_day_offset=0,
        ),
    )
    response = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "day_not_ready"
    assert any(
        issue["code"] == "pairings_required"
        for issue in response.json()["detail"]["issues"]
    )
    assert response.json()["detail"]["next_step"] == "planning"
    assert (
        client.get("/api/v1/scheduling/revisions/active", headers=headers).status_code
        == 404
    )


def test_source_retry_preserves_edits_and_source_changes_create_new_immutable_history(
    identity_setup,
):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    created = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert created.status_code == 201, created.text
    original = created.json()
    trip = original["assignments"][0]["trip_id"]
    resource = original["problem"]["resources"][0]["resource_id"]
    patched = client.post(
        "/api/v1/scheduling/revisions/" + original["revision_id"] + "/patches",
        headers=headers,
        json={
            "version": 1,
            "patches": [
                {"trip_id": trip, "new_resource_id": resource, "is_locked": True}
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["verification"]["valid"] is True
    retried = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert retried.status_code == 201 and retried.json() == patched.json()
    current = patched.json()
    for action in ("request-approval", "approve", "publish"):
        outcome = client.post(
            "/api/v1/scheduling/revisions/" + original["revision_id"] + "/" + action,
            headers=headers,
            json={"version": current["version"]},
        )
        assert outcome.status_code == 200, outcome.text
        current = outcome.json()
    assert current["status"] == "published"
    changed = client.patch(
        "/api/v1/drivers/" + str(driver["id"]),
        headers=headers,
        json={"version": 1, "first_name": "Changed"},
    )
    assert changed.status_code == 200, changed.text
    historical = client.get(
        "/api/v1/scheduling/revisions/" + original["revision_id"], headers=headers
    )
    assert historical.status_code == 200 and historical.json() == current
    newer = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    )
    assert newer.status_code == 201, newer.text
    assert newer.json()["revision_id"] != original["revision_id"]
    assert newer.json()["source_resources"][0]["driver_name"] == "Changed Δήμου"
    assert newer.json()["assignments"][0]["resource_id"] == "UNASSIGNED"
    assert (
        client.get(
            "/api/v1/scheduling/revisions/" + original["revision_id"], headers=headers
        ).json()
        == current
    )


def test_customer_snapshot_runs_through_the_restricted_cv_worker(
    identity_setup, restricted_databases
):
    from sqlalchemy.orm import sessionmaker
    from app.domain.jobs.worker import work_once

    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    ).json()
    queued = client.post(
        "/optimization/runs",
        headers=headers,
        json={
            "snapshot_id": revision["revision_id"],
            "config": {"iterations": 1, "time_limit_seconds": 10},
        },
    )
    assert queued.status_code == 202, queued.text
    identifier = queued.json()["run_id"]
    assert work_once(
        sessionmaker(bind=restricted_databases["worker"]),
        identity_setup["first"].tenant_id,
        "canonical-worker",
    )
    outcome = client.get("/optimization/runs/" + identifier, headers=headers)
    assert (
        outcome.status_code == 200 and outcome.json()["status"] == "completed"
    ), outcome.text[:500]
    assert outcome.json()["snapshot_id"] == revision["revision_id"]
    candidates = client.get(
        "/optimization/runs/" + identifier + "/candidates", headers=headers
    ).json()["candidates"]
    assert candidates and candidates[-1]["verification"]["valid"] is True
    assert candidates[-1]["metrics"]["assigned_trips_count"] == 1
    assert (
        candidates[-1]["assignments"][0]["resource_id"]
        == revision["problem"]["resources"][0]["resource_id"]
    )
    assert (
        client.get(
            "/api/v1/scheduling/revisions/" + revision["revision_id"], headers=headers
        ).json()["assignments"][0]["resource_id"]
        == "UNASSIGNED"
    )


def test_frozen_display_metadata_contains_actual_local_clocks_and_timezone(
    identity_setup,
):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    ).json()
    assert revision["timezone"] == "Europe/Athens"
    assert revision["service_day_start_utc"] == "2026-05-31T21:00:00+00:00"
    trip = revision["source_trips"][0]
    assert trip["departure_local"] == "08:00" and trip["arrival_local"] == "09:00"
    assert trip["arrival_day_offset"] == 0


@pytest.mark.parametrize(
    "service_date,boundaries,start",
    [
        ("2026-10-25", [0, 1500, 2940, 4380], 540),
        ("2026-03-29", [0, 1380, 2820, 4260], 420),
    ],
)
def test_frozen_timeline_day_windows_follow_the_actual_athens_clock_change(
    identity_setup, service_date, boundaries, start
):
    client, headers, template, pairing, driver = prepared_customer(
        identity_setup, service_date
    )
    response = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": service_date},
    )
    assert response.status_code == 201, response.text[:500]
    assert response.json()["day_boundaries_minutes"] == boundaries
    assert response.json()["source_trips"][0]["departure_local"] == "08:00"
    assert response.json()["problem"]["trips"][0]["start_minutes"] == start


def test_changed_operational_inputs_flag_a_draft_and_block_approval(identity_setup):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    ).json()
    patched = client.post(
        "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/patches",
        headers=headers,
        json={
            "version": 1,
            "patches": [
                {
                    "trip_id": revision["assignments"][0]["trip_id"],
                    "new_resource_id": revision["problem"]["resources"][0][
                        "resource_id"
                    ],
                }
            ],
        },
    ).json()
    assert patched["verification"]["valid"] is True
    changed = client.patch(
        "/api/v1/drivers/" + str(driver["id"]),
        headers=headers,
        json={"version": 1, "first_name": "Changed"},
    )
    assert changed.status_code == 200
    loaded = client.get(
        "/api/v1/scheduling/revisions/" + revision["revision_id"], headers=headers
    ).json()
    assert loaded["source_review_required"] is True
    blocked = client.post(
        "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/request-approval",
        headers=headers,
        json={"version": patched["version"]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "source_changed"


def test_new_operating_trip_requires_review_without_a_get_materializing_it(
    identity_setup,
):
    from app.domain.timetables.models import TripInstance

    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    ).json()
    second = {
        key: template[key]
        for key in (
            "trip_code",
            "departure_time",
            "arrival_time",
            "arrival_day_offset",
            "operating_weekdays",
            "valid_from",
            "valid_until",
            "allowed_bus_types",
        )
    }
    second.update(
        trip_code="T002",
        origin_station_id=template["origin"]["id"],
        destination_station_id=template["destination"]["id"],
    )
    assert (
        client.post("/api/v1/timetables", headers=headers, json=second).status_code
        == 201
    )
    loaded = client.get(
        "/api/v1/scheduling/revisions/" + revision["revision_id"], headers=headers
    )
    assert loaded.status_code == 200 and loaded.json()["source_review_required"] is True
    with identity_setup["owner_factory"]() as db:
        assert (
            db.query(TripInstance)
            .filter_by(tenant_id=identity_setup["first"].tenant_id)
            .count()
            == 1
        )


def test_source_change_after_approval_blocks_publication(identity_setup):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post(
        "/api/v1/scheduling/revisions",
        headers=headers,
        json={"service_date": "2026-06-01"},
    ).json()
    revision = client.post(
        "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/patches",
        headers=headers,
        json={
            "version": 1,
            "patches": [
                {
                    "trip_id": revision["assignments"][0]["trip_id"],
                    "new_resource_id": revision["problem"]["resources"][0][
                        "resource_id"
                    ],
                }
            ],
        },
    ).json()
    for action in ("request-approval", "approve"):
        response = client.post(
            "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/" + action,
            headers=headers,
            json={"version": revision["version"]},
        )
        assert response.status_code == 200
        revision = response.json()
    assert (
        client.patch(
            "/api/v1/drivers/" + str(driver["id"]),
            headers=headers,
            json={"version": 1, "first_name": "Changed"},
        ).status_code
        == 200
    )
    blocked = client.post(
        "/api/v1/scheduling/revisions/" + revision["revision_id"] + "/publish",
        headers=headers,
        json={"version": revision["version"]},
    )
    assert (
        blocked.status_code == 409
        and blocked.json()["detail"]["code"] == "source_changed"
    )
    current = client.get(
        "/api/v1/scheduling/revisions/" + revision["revision_id"], headers=headers
    ).json()
    assert current["status"] == "approved" and current["source_review_required"] is True
