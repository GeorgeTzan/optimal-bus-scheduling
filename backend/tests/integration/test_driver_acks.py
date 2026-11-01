"""An acknowledgment names the exact publication, trip and driver; it never survives a changed publication."""
import uuid
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
import pytest
from tests.helpers.driver_portal import freeze_today, link_driver
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_impacts import change, driver_of
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
from tests.integration.test_schedule_changes import APPLY, transition

DUTIES, ACK = '/api/v1/driver/duties', '/api/v1/driver/acknowledgments'


def setup_day(identity_setup, monkeypatch, overlap=False):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=overlap)
    freeze_today(monkeypatch)
    mine = link_driver(identity_setup, headers, driver_of(revision, first))
    day = client.get(DUTIES, headers=mine).json()['days'][0]
    return client, headers, revision, first, other, mine, day


def ack(client, mine, publication, trips, request_id=None):
    return client.post(ACK, headers=mine, json={'request_id': request_id or str(uuid.uuid4()), 'publication_id': publication, 'trip_ids': trips})


def republish(client, headers, revision, patches):
    body, _ = change(client, headers, revision, [])
    body['patches'] = patches
    body['reviewed_not_started'] = [item['trip_id'] for item in patches]
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:300]
    successor = created.json()
    for action in ('request-approval', 'approve', 'publish'):
        successor = transition(client, headers, successor, action).json()
    return successor


def test_acknowledging_a_trip_is_recorded_for_the_exact_publication_and_survives_reload(identity_setup, monkeypatch):
    client, headers, revision, first, other, mine, day = setup_day(identity_setup, monkeypatch)
    trip = day['duties'][0]['trip_id']
    done = ack(client, mine, day['publication_id'], [trip])
    assert done.status_code == 200, done.text
    assert client.get(DUTIES, headers=mine).json()['days'][0]['duties'][0]['acknowledged'] is True
    with identity_setup['owner_factory']() as db:
        row = db.execute(text('SELECT publication_id, revision_id, revision_version, trip_id, driver_id FROM domain_driver_acknowledgments')).one()
    assert (row.publication_id, row.revision_id, row.revision_version, row.trip_id) == (day['publication_id'], day['revision_id'], day['revision_version'], trip)


def test_a_republished_day_needs_a_new_acknowledgment_and_the_old_publication_is_refused(identity_setup, monkeypatch):
    client, headers, revision, first, other, mine, day = setup_day(identity_setup, monkeypatch)
    trips = [item['trip_id'] for item in day['duties']]
    assert ack(client, mine, day['publication_id'], trips).status_code == 200
    republish(client, headers, revision, [{'trip_id': trips[0], 'operation': 'unassign'}])
    after = client.get(DUTIES, headers=mine).json()['days'][0]
    assert after['publication_id'] != day['publication_id'] and [item['trip_id'] for item in after['duties']] == [trips[1]]
    assert after['duties'][0]['acknowledged'] is False
    stale = ack(client, mine, day['publication_id'], [trips[1]])
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'publication_replaced'
    assert ack(client, mine, after['publication_id'], [trips[1]]).status_code == 200


def test_another_drivers_trip_is_refused_and_nothing_is_written(identity_setup, monkeypatch):
    client, headers, revision, first, other, mine, day = setup_day(identity_setup, monkeypatch, overlap=True)
    foreign = next(item['trip_id'] for item in revision['assignments'] if item['resource_id'] == other['resource_id'])
    own = day['duties'][0]['trip_id']
    refused = ack(client, mine, day['publication_id'], [own, foreign])
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'not_your_duty'
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_driver_acknowledgments')).scalar_one() == 0


def test_retries_replay_and_changed_details_are_refused_and_reading_never_writes(identity_setup, monkeypatch):
    client, headers, revision, first, other, mine, day = setup_day(identity_setup, monkeypatch)
    trips = [item['trip_id'] for item in day['duties']]
    request_id = str(uuid.uuid4())
    first_try = ack(client, mine, day['publication_id'], trips[:1], request_id)
    assert first_try.status_code == 200
    assert ack(client, mine, day['publication_id'], trips[:1], request_id).json() == first_try.json()
    changed = ack(client, mine, day['publication_id'], trips, request_id)
    assert changed.status_code == 409 and changed.json()['detail']['code'] == 'request_changed'
    again = ack(client, mine, day['publication_id'], trips[:1])  # a new request for an acknowledged trip keeps the first time
    assert again.json()['acknowledged'][0]['acknowledged_at'] == first_try.json()['acknowledged'][0]['acknowledged_at']
    client.get(DUTIES, headers=mine)
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_driver_acknowledgments')).scalar_one() == 1


def test_a_cancelled_trip_can_be_acknowledged_and_the_api_role_cannot_rewrite_history(identity_setup, monkeypatch, restricted_databases):
    client, headers, revision, first, other, mine, day = setup_day(identity_setup, monkeypatch)
    trip = day['duties'][0]['trip_id']
    republish(client, headers, revision, [{'trip_id': trip, 'operation': 'cancel', 'reason': 'Service withdrawn'}])
    after = client.get(DUTIES, headers=mine).json()['days'][0]
    assert ack(client, mine, after['publication_id'], [trip]).status_code == 200
    with identity_setup['owner_factory']() as db:
        tenant = db.execute(text('SELECT tenant_id FROM domain_driver_acknowledgments')).scalar_one()
    for statement in ("UPDATE domain_driver_acknowledgments SET trip_id='x'", 'DELETE FROM domain_driver_acknowledgments'):
        with restricted_databases['api'].connect() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:t,true)"), {'t': str(tenant)})
            with pytest.raises(ProgrammingError):
                connection.execute(text(statement))
