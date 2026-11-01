"""Administrators change roles and status safely: audited, replayable, never on themselves, never to an unlinked driver."""
import uuid
from sqlalchemy import text
from tests.helpers.driver_portal import link_driver
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_permissions import person

MEMBERS = '/api/v1/identity/members'


def members(client, admin):
    return {row['email']: row for row in client.get(MEMBERS, headers=admin).json()['members']}


def patch(client, admin, member, **fields):
    return client.patch(f"{MEMBERS}/{member['id']}", headers=admin, json={'version': member['version'], **fields})


def audit_count(setup):
    with setup['owner_factory']() as db:
        return db.execute(text("SELECT count(*) FROM domain_office_audit WHERE entity='member'")).scalar_one()


def test_a_role_change_is_audited_replayable_and_ends_the_members_sessions(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    staff, _ = person(identity_setup, 'staff@example.org', 'dispatcher')
    target = members(client, admin)['staff@example.org']
    request_id = str(uuid.uuid4())
    first = patch(client, admin, target, role='viewer', request_id=request_id)
    assert first.status_code == 200 and first.json()['role'] == 'viewer' and first.json()['version'] == target['version'] + 1
    assert client.get('/auth/me', headers=staff).status_code == 401
    assert audit_count(identity_setup) == 1
    assert patch(client, admin, target, role='viewer', request_id=request_id).json() == first.json() and audit_count(identity_setup) == 1
    changed = patch(client, admin, target, role='management', request_id=request_id)
    assert changed.status_code == 409 and changed.json()['detail']['code'] == 'request_changed'


def test_a_change_that_changes_nothing_writes_nothing(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    person(identity_setup, 'staff@example.org', 'dispatcher')
    target = members(client, admin)['staff@example.org']
    same = patch(client, admin, target, role='dispatcher')
    assert same.status_code == 200 and same.json()['version'] == target['version'] and audit_count(identity_setup) == 0


def test_an_administrator_cannot_change_their_own_role_or_status(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    me = members(client, admin)['first@example.org']
    for fields in ({'role': 'viewer'}, {'is_active': False}):
        refused = patch(client, admin, me, **fields)
        assert refused.status_code == 403 and refused.json()['detail']['code'] == 'own_membership'


def test_a_member_cannot_become_a_driver_without_a_record_and_a_linked_driver_loses_the_link_when_changed(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    person(identity_setup, 'staff@example.org', 'dispatcher')
    refused = patch(client, admin, members(client, admin)['staff@example.org'], role='driver')
    assert refused.status_code == 422 and refused.json()['detail']['code'] == 'driver_needs_record'
    with identity_setup['owner_factory']() as db:
        db.execute(text("INSERT INTO domain_drivers (id,tenant_id,code,first_name,last_name,is_active) VALUES (11,:t,'L11','Test','Driver',true) ON CONFLICT (id) DO UPDATE SET tenant_id=:t, is_active=true"), {'t': identity_setup['first'].tenant_id})
        db.commit()
    link_driver(identity_setup, admin, 11, email='driver@example.org')
    driver = members(client, admin)['driver@example.org']
    assert driver['driver_id'] == 11
    moved = patch(client, admin, driver, role='viewer')
    assert moved.status_code == 200 and moved.json()['driver_id'] is None


def test_one_administrator_always_remains_and_a_demoted_admins_stale_session_cannot_act(identity_setup):
    client = identity_setup['client']
    first, _ = person(identity_setup, None, 'admin')
    second, _ = person(identity_setup, 'second-admin@example.org', 'admin')
    rows = members(client, first)
    assert patch(client, first, rows['second-admin@example.org'], role='viewer').status_code == 200
    stale = client.patch(f"{MEMBERS}/{rows['first@example.org']['id']}", headers=second, json={'version': rows['first@example.org']['version'], 'role': 'viewer'})
    assert stale.status_code == 401
    assert [row['role'] for row in members(client, first).values() if row['is_active']].count('admin') == 1


def test_a_deactivated_member_cannot_sign_in_and_stops_being_a_leave_approver_and_non_admins_are_refused(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    staff, staff_id = person(identity_setup, 'staff@example.org', 'dispatcher')
    target = members(client, admin)['staff@example.org']
    assert client.post('/api/v1/office/approval-routes', headers=admin, json={'request_id': str(uuid.uuid4()), 'membership_id': staff_id}).status_code == 201
    assert patch(client, admin, target, is_active=False).status_code == 200
    assert client.post('/auth/login', json={'email': 'staff@example.org', 'password': 'StrongTenantPassword123!'}).status_code in (401, 403)
    from app.domain.office.permissions import resolve_approver_routes
    with identity_setup['owner_factory']() as db:
        assert resolve_approver_routes(db, identity_setup['first'].tenant_id, 11) == []
    viewer, _ = person(identity_setup, 'viewer@example.org', 'viewer')
    assert client.patch(f"{MEMBERS}/{target['id']}", headers=viewer, json={'version': 1, 'role': 'viewer'}).status_code == 403
