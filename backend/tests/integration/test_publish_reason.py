import uuid
from sqlalchemy import text
from tests.integration.test_identity import identity_setup
from tests.integration.test_schedule_changes import APPLY
from tests.integration.test_work_rules_gates import (
    FIRST, MONDAY, OVERTIME_DAY, REVISIONS, act, assign, change_request, draft, fleet)


def approved_day(setup, plan):
    client, headers, made, vehicle = fleet(setup, OVERTIME_DAY)
    revision = assign(client, headers, draft(client, headers, MONDAY), plan)
    for action in ('request-approval', 'approve'):
        response = act(client, headers, revision, action)
        assert response.status_code == 200, response.text[:400]
        revision = response.json()
    return client, headers, revision


def publish_with(client, headers, revision, **fields):
    return client.post(f"{REVISIONS}/{revision['revision_id']}/publish", headers=headers, json={'version': revision['version'], **fields})


def stored(setup, revision):
    with setup['owner_factory']() as db:
        return db.execute(text('SELECT uncovered_reason, uncovered_note FROM domain_publications WHERE revision_id=:r'),
                          {'r': revision['revision_id']}).one()


def test_publish_with_uncovered_trips_requires_a_reason(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST})
    response = publish_with(client, headers, approved)
    assert response.status_code == 422 and response.json()['detail']['code'] == 'uncovered_reason_required'
    assert response.json()['detail']['uncovered'] == 1


def test_other_needs_a_note(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST})
    response = publish_with(client, headers, approved, uncovered_reason='other')
    assert response.status_code == 422 and response.json()['detail']['code'] == 'uncovered_note_required'
    assert publish_with(client, headers, approved, uncovered_reason='other', uncovered_note='   ').status_code == 422
    assert publish_with(client, headers, approved, uncovered_reason='other', uncovered_note='Strike').status_code == 200


def test_reason_is_stored_and_audited(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST})
    assert publish_with(client, headers, approved, uncovered_reason='driver_leave').status_code == 200
    assert stored(identity_setup, approved).uncovered_reason == 'driver_leave'
    with identity_setup['owner_factory']() as db:
        details = db.execute(text("SELECT details FROM domain_scheduling_audit_logs WHERE action='publish' AND revision_id=:r ORDER BY id DESC LIMIT 1"),
                             {'r': approved['revision_id']}).scalar_one()
    assert details['uncovered_reason'] == 'driver_leave'


def test_fully_covered_day_ignores_the_fields(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST, 'T2': FIRST})
    assert publish_with(client, headers, approved, uncovered_reason='no_driver', uncovered_note='x').status_code == 200
    row = stored(identity_setup, approved)
    assert row.uncovered_reason is None and row.uncovered_note is None


def test_urgent_change_successor_needs_a_reason(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST, 'T2': FIRST})
    published = publish_with(client, headers, approved).json()
    request = change_request(client, headers, published, {'T2': FIRST})
    request['patches'] = [{'trip_id': request['patches'][0]['trip_id'], 'operation': 'unassign'}]
    applied = client.post(APPLY, headers=headers, json={**request, 'request_id': str(uuid.uuid4())})
    assert applied.status_code == 201, applied.text[:600]
    successor = applied.json()
    for action in ('request-approval', 'approve'):
        successor = act(client, headers, successor, action).json()
    response = publish_with(client, headers, successor)
    assert response.status_code == 422 and response.json()['detail']['code'] == 'uncovered_reason_required'
    assert publish_with(client, headers, successor, uncovered_reason='no_vehicle').status_code == 200


def test_unknown_reason_is_rejected(identity_setup):
    client, headers, approved = approved_day(identity_setup, {'T1': FIRST})
    assert publish_with(client, headers, approved, uncovered_reason='weather').status_code == 422
