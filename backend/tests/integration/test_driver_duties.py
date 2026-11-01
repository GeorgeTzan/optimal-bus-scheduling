"""A driver sees only own published duties; nothing else, and never by choosing an id."""
import uuid
from tests.helpers.driver_portal import freeze_today, link_driver
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_impacts import change, driver_of
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
from tests.integration.test_schedule_changes import APPLY, transition

DUTIES = '/api/v1/driver/duties'


def test_a_driver_sees_only_own_published_trips_with_local_times(identity_setup, monkeypatch):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=True)
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    body = client.get(DUTIES, headers=mine)
    assert body.status_code == 200, body.text
    days = body.json()['days']
    assert len(days) == 1 and days[0]['service_date'] == '2026-06-01'
    own = {item['trip_id'] for item in revision['assignments'] if item['resource_id'] == first['resource_id']}
    assert {item['trip_id'] for item in days[0]['duties']} == own and own
    duty = days[0]['duties'][0]
    assert duty['start_local'].endswith('+03:00') and duty['origin']['code'] and duty['acknowledged'] is False and duty['cancelled'] is False
    assert 'driver_name' not in str(days) and days[0]['publication_id']


def test_a_caller_supplied_driver_id_is_ignored_and_other_roles_and_unlinked_drivers_are_refused(identity_setup, monkeypatch):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=True)
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    own = {item['trip_id'] for item in revision['assignments'] if item['resource_id'] == first['resource_id']}
    other_id = driver_of(revision, other)
    spoofed = client.get(DUTIES, headers=mine, params={'driver_id': other_id})
    assert {item['trip_id'] for item in spoofed.json()['days'][0]['duties']} == own
    assert client.get(DUTIES, headers=headers).status_code == 403  # an administrator is not a driver
    assert client.get('/api/v1/driver/me', headers=headers).json()['detail']['code'] == 'not_a_driver'
    client.post('/api/v1/identity/drivers/%d/unlink' % driver_of(revision, first), headers=headers, json={'request_id': str(uuid.uuid4())})
    assert client.get(DUTIES, headers=mine).status_code == 401  # sessions ended
    again = link_driver(identity_setup, headers, driver_of(revision, first), email='again@example.org')
    assert client.get('/api/v1/driver/me', headers=again).json()['driver_name']


def test_an_unpublished_successor_never_appears_and_a_republish_replaces_the_day_without_duplicates(identity_setup, monkeypatch):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)  # both trips on the first crew
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    trips = [item['trip_id'] for item in revision['assignments']]
    seen = lambda: [item['trip_id'] for item in client.get(DUTIES, headers=mine).json()['days'][0]['duties']]
    assert sorted(seen()) == sorted(trips)
    body, _ = change(client, headers, revision, [])
    body['patches'] = [{'trip_id': trips[0], 'operation': 'unassign'}]
    body['reviewed_not_started'] = [trips[0]]
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:300]
    assert sorted(seen()) == sorted(trips)  # the draft successor is invisible
    successor = created.json()
    for action in ('request-approval', 'approve', 'publish'):
        successor = transition(client, headers, successor, action).json()
    assert seen() == [trips[1]]  # only the current publication counts, each trip once


def test_cancelled_trips_are_shown_as_cancelled(identity_setup, monkeypatch):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=True)
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    trip = next(item['trip_id'] for item in revision['assignments'] if item['resource_id'] == first['resource_id'])
    body, _ = change(client, headers, revision, [])
    body['patches'] = [{'trip_id': trip, 'operation': 'cancel', 'reason': 'Service withdrawn'}]
    body['reviewed_not_started'] = [trip]
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:300]
    successor = created.json()
    for action in ('request-approval', 'approve', 'publish'):
        successor = transition(client, headers, successor, action).json()
    shown = {item['trip_id']: item for item in client.get(DUTIES, headers=mine).json()['days'][0]['duties']}
    assert shown[trip]['cancelled'] is True


def test_a_cancellation_reaches_only_the_driver_it_was_last_published_for(identity_setup, monkeypatch):
    from tests.integration.test_driver_acks import republish
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)  # both trips on the first crew
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    trips = [item['trip_id'] for item in revision['assignments']]
    second = republish(client, headers, revision, [{'trip_id': trips[0], 'operation': 'unassign'}])  # published without the trip for this driver
    republish(client, headers, second, [{'trip_id': trips[0], 'operation': 'cancel', 'reason': 'Service withdrawn'}])
    shown = {item['trip_id']: item for item in client.get(DUTIES, headers=mine).json()['days'][0]['duties']}
    assert set(shown) == {trips[1]}  # the trip was already taken off this driver before it was cancelled: no notice for them
