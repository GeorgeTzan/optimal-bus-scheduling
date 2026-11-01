"""Pending invitations can be listed, resent and revoked; the old link and its queued mail never survive a resend."""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from tests.integration.test_driver_links import accept, prepare, token_for
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_permissions import person

INVITE, LIST = '/api/v1/identity/invitations', '/api/v1/identity/invitations'


def invite(client, admin, email='staff@example.org', role='dispatcher', **extra):
    return client.post(INVITE, headers=admin, json={'email': email, 'role': role, 'request_id': str(uuid.uuid4()), **extra})


def listed(client, admin):
    response = client.get(LIST, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()['invitations']


def mail_status(setup, invitation_id):
    with setup['owner_factory']() as db:
        return db.execute(text('SELECT delivery_status FROM domain_email_outbox WHERE identity_token_id=:i'), {'i': invitation_id}).scalar_one()


def test_pending_invitations_are_listed_with_delivery_status_and_no_secret_and_old_expired_ones_drop_off(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    rows = listed(client, admin)
    assert [(row['email'], row['role'], row['delivery_status'], row['expired']) for row in rows] == [('staff@example.org', 'dispatcher', 'not_configured', False)]
    assert 'token' not in str(rows) and 'link' not in str(rows)
    with identity_setup['owner_factory']() as db:
        for email, days in (('recent@example.org', 5), ('old@example.org', 31)):
            db.execute(text("INSERT INTO domain_identity_tokens (id,tenant_id,token_hash,kind,email,role,expires_at,created_at) VALUES (:i,:t,:h,'invitation',:e,'viewer',:x,:x)"),
                       {'i': str(uuid.uuid4()), 't': identity_setup['first'].tenant_id, 'h': uuid.uuid4().hex, 'e': email, 'x': datetime.now(timezone.utc) - timedelta(days=days)})
        db.commit()
    by_email = {row['email']: row for row in listed(client, admin)}
    assert by_email['recent@example.org']['expired'] is True and 'old@example.org' not in by_email and 'staff@example.org' in by_email


def test_resend_replaces_the_link_and_discards_the_old_queued_mail(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    old = listed(client, admin)[0]
    old_token = token_for(identity_setup, 'staff@example.org')
    resent = client.post(f"{INVITE}/{old['id']}/resend", headers=admin, json={'request_id': str(uuid.uuid4())})
    assert resent.status_code == 202 and 'token' not in str(resent.json()), resent.text
    assert mail_status(identity_setup, old['id']) == 'discarded'
    assert accept(client, old_token).status_code == 400
    rows = listed(client, admin)
    assert len(rows) == 1 and rows[0]['id'] != old['id']
    assert accept(client, token_for(identity_setup, 'staff@example.org')).status_code == 200


def test_revoke_discards_the_queued_mail_and_resend_is_refused_for_a_linked_or_archived_driver(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin, email='driver@example.org', role='driver', driver_id=11).status_code == 202
    row = listed(client, admin)[0]
    assert client.post(f"{INVITE}/{row['id']}/revoke", headers=admin, json={'request_id': str(uuid.uuid4())}).status_code == 200
    assert mail_status(identity_setup, row['id']) == 'discarded' and listed(client, admin) == []
    assert invite(client, admin, email='driver@example.org', role='driver', driver_id=11).status_code == 202
    pending = listed(client, admin)[0]
    with identity_setup['owner_factory']() as db:
        db.execute(text('UPDATE domain_drivers SET is_active=false WHERE id=11'))
        db.commit()
    archived = client.post(f"{INVITE}/{pending['id']}/resend", headers=admin, json={'request_id': str(uuid.uuid4())})
    assert archived.status_code == 409 and archived.json()['detail']['code'] == 'driver_archived'
    assert client.post(f"{INVITE}/{uuid.uuid4()}/resend", headers=admin, json={'request_id': str(uuid.uuid4())}).status_code == 404


def test_driver_role_needs_a_record_and_existing_members_are_refused_while_other_organizations_look_like_new_emails(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin, email='d@example.org', role='driver').status_code == 422
    person(identity_setup, 'member@example.org', 'viewer')
    exists = invite(client, admin, email='Member@Example.org')
    assert exists.status_code == 409 and exists.json()['detail']['code'] == 'member_exists'
    members = {row['email']: row for row in client.get('/api/v1/identity/members', headers=admin).json()['members']}
    assert client.patch(f"/api/v1/identity/members/{members['member@example.org']['id']}", headers=admin, json={'version': members['member@example.org']['version'], 'is_active': False}).status_code == 200
    assert invite(client, admin, email='member@example.org').json()['detail']['code'] == 'member_exists'  # a deactivated member too
    assert invite(client, admin, email='second@example.org').status_code == 202  # the other organization's admin: same answer as any new email


def test_replay_and_permissions(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    row = listed(client, admin)[0]
    request_id = str(uuid.uuid4())
    first = client.post(f"{INVITE}/{row['id']}/resend", headers=admin, json={'request_id': request_id})
    assert client.post(f"{INVITE}/{row['id']}/resend", headers=admin, json={'request_id': request_id}).json() == first.json()
    viewer, _ = person(identity_setup, 'viewer@example.org', 'viewer')
    assert client.get(LIST, headers=viewer).status_code == 403
    assert client.post(f"{INVITE}/{row['id']}/resend", headers=viewer, json={'request_id': str(uuid.uuid4())}).status_code == 403


def test_a_stale_revoke_of_an_already_replaced_invitation_is_refused(identity_setup):
    client, admin = prepare(identity_setup)
    assert invite(client, admin).status_code == 202
    old = listed(client, admin)[0]
    assert client.post(f"{INVITE}/{old['id']}/resend", headers=admin, json={'request_id': str(uuid.uuid4())}).status_code == 202
    stale = client.post(f"{INVITE}/{old['id']}/revoke", headers=admin, json={'request_id': str(uuid.uuid4())})
    assert stale.status_code == 404 and len(listed(client, admin)) == 1


def test_a_deactivated_driver_login_is_not_invited_again_but_asked_to_be_reactivated(identity_setup):
    from tests.integration.test_driver_links import invite as driver_invite
    client, admin = prepare(identity_setup)
    assert driver_invite(client, admin).status_code == 202
    assert accept(client, token_for(identity_setup, 'driver@example.org')).status_code == 200
    assert client.post('/api/v1/identity/drivers/11/unlink', headers=admin, json={'request_id': str(uuid.uuid4())}).status_code == 200
    member = {row['email']: row for row in client.get('/api/v1/identity/members', headers=admin).json()['members']}['driver@example.org']
    assert client.patch(f"/api/v1/identity/members/{member['id']}", headers=admin, json={'version': member['version'], 'is_active': False}).status_code == 200
    refused = driver_invite(client, admin)
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'member_exists'
