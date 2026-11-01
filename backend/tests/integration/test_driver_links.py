"""A driver login is linked only through an invitation that names an existing driver record."""
import uuid
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import text
from app.domain.identity.mail import decrypt_payload
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_permissions import person

INVITE = '/api/v1/identity/invitations'
LINKS = '/api/v1/identity/driver-links'


def prepare(setup):
    """Driver 11 belongs to the signed-in organization, 22 to the other one, 33 is archived."""
    with setup['owner_factory']() as db:
        for identifier, tenant, active in ((11, setup['first'].tenant_id, True), (22, setup['second'].tenant_id, True), (33, setup['first'].tenant_id, False)):
            db.execute(text("INSERT INTO domain_drivers (id,tenant_id,code,first_name,last_name,is_active) VALUES (:i,:t,:c,'Test','Driver',:a) ON CONFLICT (id) DO UPDATE SET tenant_id=:t, is_active=:a"),
                       {'i': identifier, 't': tenant, 'c': f'L{identifier}', 'a': active})
        db.commit()
    admin, _ = person(setup, None, 'admin')
    return setup['client'], admin


def invite(client, headers, driver_id=11, email='driver@example.org', **extra):
    return client.post(INVITE, headers=headers, json={'email': email, 'role': 'driver', 'driver_id': driver_id, 'request_id': str(uuid.uuid4()), **extra})


def link_state(client, headers, driver_id=11):
    response = client.get(LINKS, headers=headers, params={'driver_ids': str(driver_id)})
    assert response.status_code == 200, response.text
    return response.json()['links'][str(driver_id)]


def token_for(setup, email):
    with setup['owner_factory']() as db:
        row = db.execute(text("SELECT encrypted_payload FROM domain_email_outbox WHERE kind='invitation' ORDER BY created_at DESC")).all()
    for (payload,) in row:
        data = decrypt_payload(payload)
        if data['to'] == email:
            return parse_qs(urlsplit(data['link']).fragment)['token'][0]
    raise AssertionError('no invitation mail queued for ' + email)


def accept(client, token, password='StrongTenantPassword123!'):
    return client.post('/auth/accept-invitation', json={'token': token, 'password': password, 'full_name': 'Nikos Driver'})


def test_invitation_with_a_driver_queues_mail_without_a_link_and_acceptance_links_the_login(identity_setup):
    client, admin = prepare(identity_setup)
    response = invite(client, admin)
    assert response.status_code == 202, response.text
    assert response.json()['delivery_status'] == 'not_configured' and 'token' not in response.json() and 'link' not in response.json()
    assert link_state(client, admin)['state'] == 'invited'
    accepted = accept(client, token_for(identity_setup, 'driver@example.org'))
    assert accepted.status_code == 200, accepted.text
    me = client.get('/auth/me', headers={'Authorization': 'Bearer ' + accepted.json()['access_token']})
    assert me.json()['role'] == 'driver'
    state = link_state(client, admin)
    assert state['state'] == 'linked' and state['email'] == 'driver@example.org'


def test_one_pending_invitation_per_driver_until_it_is_revoked(identity_setup):
    client, admin = prepare(identity_setup)
    first = invite(client, admin)
    assert first.status_code == 202
    again = invite(client, admin, email='other@example.org')
    assert again.status_code == 409 and again.json()['detail']['code'] == 'driver_invite_pending'
    pending = link_state(client, admin)
    revoked = client.post(f"{INVITE}/{pending['invitation_id']}/revoke", headers=admin, json={'request_id': str(uuid.uuid4())})
    assert revoked.status_code == 200, revoked.text
    assert accept(client, token_for(identity_setup, 'driver@example.org')).status_code == 400
    assert link_state(client, admin)['state'] == 'unlinked'
    assert invite(client, admin, email='other@example.org').status_code == 202


def test_an_already_linked_archived_or_foreign_driver_and_a_non_driver_role_are_refused(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    assert accept(client, token_for(identity_setup, 'driver@example.org')).status_code == 200
    linked = invite(client, admin, email='second@example.org')
    assert linked.status_code == 409 and linked.json()['detail']['code'] == 'driver_already_linked'
    archived = invite(client, admin, driver_id=33, email='old@example.org')
    assert archived.status_code == 409 and archived.json()['detail']['code'] == 'driver_archived'
    assert invite(client, admin, driver_id=22, email='foreign@example.org').status_code == 404
    assert client.post(INVITE, headers=admin, json={'email': 'v@example.org', 'role': 'viewer', 'driver_id': 11}).status_code == 422


def test_unlinking_ends_the_drivers_sessions_and_allows_a_new_invitation(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    accepted = accept(client, token_for(identity_setup, 'driver@example.org'))
    driver_headers = {'Authorization': 'Bearer ' + accepted.json()['access_token']}
    assert client.get('/auth/me', headers=driver_headers).status_code == 200
    unlinked = client.post('/api/v1/identity/drivers/11/unlink', headers=admin, json={'request_id': str(uuid.uuid4())})
    assert unlinked.status_code == 200, unlinked.text
    assert client.get('/auth/me', headers=driver_headers).status_code == 401
    assert link_state(client, admin)['state'] == 'unlinked'
    assert invite(client, admin, email='newphone@example.org').status_code == 202


def test_an_existing_account_email_fails_at_acceptance_and_the_driver_stays_invited(identity_setup):
    client, admin = prepare(identity_setup)
    refused = invite(client, admin, email='first@example.org')  # a member of this organization is refused up front
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'member_exists'
    from tests.integration.test_identity import accept as accept_admin
    assert accept_admin(client, identity_setup['second']).status_code == 200  # the other organization's administrator now has an account
    assert invite(client, admin, email='second@example.org').status_code == 202  # another organization's email looks like any new one
    assert accept(client, token_for(identity_setup, 'second@example.org')).status_code == 409  # and is refused when accepted
    assert link_state(client, admin)['state'] == 'invited'


def test_retries_replay_and_changed_details_are_refused_and_only_administrators_manage_links(identity_setup):
    client, admin = prepare(identity_setup)
    request_id = str(uuid.uuid4())
    body = {'email': 'driver@example.org', 'role': 'driver', 'driver_id': 11, 'request_id': request_id}
    first = client.post(INVITE, headers=admin, json=body)
    assert first.status_code == 202
    assert client.post(INVITE, headers=admin, json=body).json() == first.json()
    changed = client.post(INVITE, headers=admin, json={**body, 'email': 'else@example.org'})
    assert changed.status_code == 409 and changed.json()['detail']['code'] == 'request_changed'
    viewer, _ = person(identity_setup, 'viewer@example.org', 'viewer')
    assert invite(client, viewer, email='x@example.org').status_code == 403
    assert client.get(LINKS, headers=viewer, params={'driver_ids': '11'}).status_code == 403
    assert client.post('/api/v1/identity/drivers/11/unlink', headers=viewer, json={'request_id': str(uuid.uuid4())}).status_code == 403


def test_an_unlinked_login_can_be_linked_again_through_a_new_invitation_to_the_same_email(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    first = accept(client, token_for(identity_setup, 'driver@example.org'), 'StrongTenantPassword123!')
    assert first.status_code == 200
    assert client.post('/api/v1/identity/drivers/11/unlink', headers=admin, json={'request_id': str(uuid.uuid4())}).status_code == 200
    assert invite(client, admin).status_code == 202
    again = accept(client, token_for(identity_setup, 'driver@example.org'), 'AnotherStrongPassword123!')
    assert again.status_code == 200, again.text
    assert link_state(client, admin)['state'] == 'linked'
    assert client.get('/api/v1/driver/me', headers={'Authorization': 'Bearer ' + again.json()['access_token']}).status_code == 200
    assert client.post('/auth/login', json={'email': 'driver@example.org', 'password': 'StrongTenantPassword123!'}).status_code == 401
    assert client.post('/auth/login', json={'email': 'driver@example.org', 'password': 'AnotherStrongPassword123!'}).status_code == 200


def test_an_invitation_cannot_be_accepted_after_its_driver_was_archived(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    with identity_setup['owner_factory']() as db:
        db.execute(text('UPDATE domain_drivers SET is_active=false WHERE id=11'))
        db.commit()
    refused = accept(client, token_for(identity_setup, 'driver@example.org'))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'driver_archived'
    assert link_state(client, admin)['state'] in ('invited', 'unlinked')
