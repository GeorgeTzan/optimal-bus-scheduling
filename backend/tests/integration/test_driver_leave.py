"""A driver requests and cancels only their own leave; the office decides through the existing approval routes."""
import uuid
from sqlalchemy import text
from tests.helpers.driver_portal import link_driver
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_impacts import driver_of
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews

LEAVE = '/api/v1/driver/leave-requests'
WINDOW = {'date_from': '2026-06-01', 'date_to': '2026-06-30'}


def body(**extra):
    return {'request_id': str(uuid.uuid4()), 'start_local': '2026-06-10T00:00:00', 'end_local': '2026-06-12T00:00:00', 'category': 'annual', 'private_note': 'Family event', **extra}


def start(identity_setup, overlap=True):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=overlap)
    me = client.get('/api/v1/identity/members', headers=headers).json()['members'][0]['id']
    assert client.post('/api/v1/office/approval-routes', headers=headers, json={'request_id': str(uuid.uuid4()), 'membership_id': me}).status_code == 201
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    return client, headers, revision, first, other, mine


def test_a_driver_request_is_pending_then_decided_by_the_office_and_shown_truthfully_after_reload(identity_setup):
    client, headers, revision, first, other, mine = start(identity_setup)
    created = client.post(LEAVE, headers=mine, json=body())
    assert created.status_code == 201, created.text
    assert created.json()['state'] == 'pending' and created.json()['driver_id'] == driver_of(revision, first)
    pending = client.get(LEAVE, headers=mine, params=WINDOW).json()['items']
    assert [(row['state'], row['category'], row['private_note']) for row in pending] == [('pending', 'annual', 'Family event')]
    office = client.get('/api/v1/office/leave-requests', headers=headers, params=WINDOW).json()['items']
    decided = client.post(f"/api/v1/office/leave-requests/{office[0]['id']}/decision", headers=headers,
                          json={'request_id': str(uuid.uuid4()), 'expected_version': office[0]['version'], 'decision': 'approved', 'note': None})
    assert decided.status_code == 200, decided.text
    assert client.get(LEAVE, headers=mine, params=WINDOW).json()['items'][0]['state'] == 'approved'
    with identity_setup['owner_factory']() as db:
        assert db.execute(text("SELECT count(*) FROM domain_driver_availabilities WHERE source_leave_id IS NOT NULL AND status='active'")).scalar_one() == 1


def test_a_driver_may_cancel_only_own_pending_requests_and_never_choose_another_driver(identity_setup):
    client, headers, revision, first, other, mine = start(identity_setup)
    spoofed = client.post(LEAVE, headers=mine, json=body(driver_id=driver_of(revision, other)))
    assert spoofed.status_code == 422
    created = client.post(LEAVE, headers=mine, json=body()).json()
    foreign = client.post('/api/v1/office/leave-requests', headers=headers, json={'request_id': str(uuid.uuid4()), 'driver_id': driver_of(revision, other),
        'start_local': '2026-06-20T00:00:00', 'end_local': '2026-06-21T00:00:00', 'category': 'sick'})
    assert foreign.status_code in (201, 403), foreign.text
    cancel = lambda leave_id, version: client.post(f'{LEAVE}/{leave_id}/cancel', headers=mine, json={'request_id': str(uuid.uuid4()), 'expected_version': version})
    if foreign.status_code == 201:
        assert cancel(foreign.json()['id'], foreign.json()['version']).status_code == 404
    done = cancel(created['id'], created['version'])
    assert done.status_code == 200 and done.json()['state'] == 'cancelled', done.text
    approved = client.post(LEAVE, headers=mine, json=body(start_local='2026-06-15T00:00:00', end_local='2026-06-16T00:00:00')).json()
    office = next(row for row in client.get('/api/v1/office/leave-requests', headers=headers, params=WINDOW).json()['items'] if row['id'] == approved['id'])
    client.post(f"/api/v1/office/leave-requests/{approved['id']}/decision", headers=headers, json={'request_id': str(uuid.uuid4()), 'expected_version': office['version'], 'decision': 'approved', 'note': None})
    late = cancel(approved['id'], office['version'] + 1)
    assert late.status_code == 409 and late.json()['detail']['code'] == 'not_cancellable'
    assert all(row['driver_id'] == driver_of(revision, first) for row in client.get(LEAVE, headers=mine, params=WINDOW).json()['items'])


def test_retries_replay_ranges_are_bounded_and_office_routes_stay_closed_to_a_driver(identity_setup):
    client, headers, revision, first, other, mine = start(identity_setup)
    payload = body()
    first_try = client.post(LEAVE, headers=mine, json=payload)
    assert client.post(LEAVE, headers=mine, json=payload).json() == first_try.json()
    changed = client.post(LEAVE, headers=mine, json={**payload, 'category': 'sick'})
    assert changed.status_code == 409 and changed.json()['detail']['code'] == 'request_changed'
    assert client.post(LEAVE, headers=mine, json=body(end_local='2028-01-01T00:00:00')).status_code == 422
    assert client.get(LEAVE, headers=mine, params={'date_from': '2026-01-01', 'date_to': '2026-12-31'}).status_code == 422
    assert client.post('/api/v1/office/leave-requests', headers=mine, json={**body(), 'driver_id': driver_of(revision, first)}).status_code == 403
    assert client.get('/api/v1/office/impacts', headers=mine, params={'date_from': '2026-06-01', 'date_to': '2026-06-01'}).status_code == 403
