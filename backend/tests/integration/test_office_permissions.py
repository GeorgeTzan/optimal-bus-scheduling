"""Office authority is explicit per member, off by default, tenant-bound and revocable."""
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.integration.test_identity import identity_setup, accept

GRANTS = '/api/v1/office/grants'
ROUTES = '/api/v1/office/approval-routes'
CAPABILITIES = '/api/v1/office/capabilities'


def bearer(response):
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def person(setup, email, role, tenant='first'):
    from app.domain.identity.service import issue_invitation
    invite = setup[tenant]
    if email is not None:
        with setup['owner_factory']() as db:
            invite = issue_invitation(db, setup[tenant].tenant_id, email, role)
            db.commit()
    headers = bearer(accept(setup['client'], invite))
    email = email or {'first': 'first@example.org', 'second': 'second@example.org'}[tenant]
    with setup['owner_factory']() as db:
        membership = db.execute(text('SELECT m.id FROM domain_memberships m JOIN users u ON u.id=m.user_id WHERE u.email=:e'), {'e': email}).scalar_one()
    return headers, membership


def driver(setup, tenant_id, code):
    with setup['owner_factory']() as db:
        value = db.execute(text("INSERT INTO domain_drivers (tenant_id,code,first_name,last_name,is_active) VALUES (:t,:c,'Test','Driver',true) RETURNING id"), {'t': tenant_id, 'c': code}).scalar_one()
        db.commit()
    return value


def grant(client, headers, membership, capability='availability.manage', active=True, expected=None, request_id=None):
    return client.put(GRANTS, headers=headers, json={'request_id': request_id or str(uuid.uuid4()), 'membership_id': membership,
                                                     'capability': capability, 'is_active': active, 'expected_version': expected})


def test_grants_default_off_and_admin_has_no_implicit_grant(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    dispatcher, _ = person(identity_setup, 'dispatch@example.org', 'dispatcher')
    for headers in (admin, dispatcher):
        assert client.get(CAPABILITIES, headers=headers).json() == {'capabilities': [], 'timezone': 'Europe/Athens'}
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_office_grants')).scalar_one() == 0


def test_only_members_manage_can_grant_and_revocation_applies_next_request(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    dispatcher, member = person(identity_setup, 'dispatch@example.org', 'dispatcher')
    assert grant(client, dispatcher, member).status_code == 403
    created = grant(client, admin, member)
    assert created.status_code == 200, created.text[:300]
    assert created.json()['version'] == 1
    assert client.get(CAPABILITIES, headers=dispatcher).json()['capabilities'] == ['availability.manage']
    revoked = grant(client, admin, member, active=False, expected=1)
    assert revoked.status_code == 200 and revoked.json()['version'] == 2
    assert client.get(CAPABILITIES, headers=dispatcher).json()['capabilities'] == []
    assert grant(client, admin, member, expected=1).status_code == 409


def test_capability_outside_allowlist_rejected(identity_setup):
    admin, member = person(identity_setup, None, 'admin')
    for capability in ('members.manage', 'schedule.approve', 'anything'):
        assert grant(identity_setup['client'], admin, member, capability).status_code == 422


def test_foreign_tenant_references_fail_in_api_and_database(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    _, foreign_member = person(identity_setup, None, 'admin', tenant='second')
    foreign_driver = driver(identity_setup, identity_setup['second'].tenant_id, 'F1')
    assert grant(client, admin, foreign_member).status_code in (404, 422)
    body = {'request_id': str(uuid.uuid4()), 'driver_id': foreign_driver, 'external_contact_name': 'Owner'}
    assert client.post(ROUTES, headers=admin, json=body).status_code in (404, 422)
    with identity_setup['owner_factory']() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO domain_office_grants (tenant_id,membership_id,capability,granted_by,granted_at) VALUES (:t,:m,'availability.manage',(SELECT id FROM users WHERE ktel_id=:t LIMIT 1),now())"),
                       {'t': identity_setup['first'].tenant_id, 'm': foreign_member})


def test_route_requires_exactly_one_approver_kind(identity_setup):
    client = identity_setup['client']
    admin, member = person(identity_setup, None, 'admin')
    base = {'request_id': str(uuid.uuid4())}
    assert client.post(ROUTES, headers=admin, json={**base, 'membership_id': member, 'external_contact_name': 'Owner'}).status_code == 422
    assert client.post(ROUTES, headers=admin, json=base).status_code == 422
    assert client.post(ROUTES, headers=admin, json={**base, 'membership_id': member}).status_code == 201
    with identity_setup['owner_factory']() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO domain_leave_approval_routes (tenant_id,created_by,created_at) VALUES (:t,(SELECT id FROM users WHERE ktel_id=:t LIMIT 1),now())"),
                       {'t': identity_setup['first'].tenant_id})


def test_missing_route_is_empty_and_driver_route_overrides_default(identity_setup):
    from app.domain.office.permissions import resolve_approver_routes
    client = identity_setup['client']
    tenant = identity_setup['first'].tenant_id
    admin, member = person(identity_setup, None, 'admin')
    covered, other = driver(identity_setup, tenant, 'A1'), driver(identity_setup, tenant, 'A2')
    with identity_setup['owner_factory']() as db:
        assert resolve_approver_routes(db, tenant, covered) == []
    default = client.post(ROUTES, headers=admin, json={'request_id': str(uuid.uuid4()), 'membership_id': member}).json()
    specific = client.post(ROUTES, headers=admin, json={'request_id': str(uuid.uuid4()), 'driver_id': covered, 'external_contact_name': 'Bus owner'}).json()
    with identity_setup['owner_factory']() as db:
        assert [row.id for row in resolve_approver_routes(db, tenant, covered)] == [specific['id']]
        assert [row.id for row in resolve_approver_routes(db, tenant, other)] == [default['id']]
    retired = client.patch(f"{ROUTES}/{specific['id']}", headers=admin, json={'request_id': str(uuid.uuid4()), 'expected_version': 1, 'is_active': False})
    assert retired.status_code == 200
    with identity_setup['owner_factory']() as db:
        assert [row.id for row in resolve_approver_routes(db, tenant, covered)] == [default['id']]


def test_audit_retry_returns_original_and_changed_payload_conflicts(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    _, member = person(identity_setup, 'dispatch@example.org', 'dispatcher')
    request_id = str(uuid.uuid4())
    first = grant(client, admin, member, request_id=request_id)
    again = grant(client, admin, member, request_id=request_id)
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    assert grant(client, admin, member, active=False, expected=1, request_id=request_id).status_code == 409
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_office_audit')).scalar_one() == 1
        assert db.execute(text('SELECT version FROM domain_office_grants')).scalar_one() == 1


def test_runtime_roles_cannot_rewrite_audit_and_worker_cannot_read_office_tables(identity_setup, restricted_databases):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    _, member = person(identity_setup, 'dispatch@example.org', 'dispatcher')
    assert grant(client, admin, member).status_code == 200
    tenant = str(identity_setup['first'].tenant_id)
    for statement in ('UPDATE domain_office_audit SET entity=\'x\'', 'DELETE FROM domain_office_audit'):
        with restricted_databases['api'].connect() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:t,true)"), {'t': tenant})
            with pytest.raises(ProgrammingError):
                connection.execute(text(statement))
    for table in ('domain_office_grants', 'domain_leave_approval_routes', 'domain_office_audit'):
        with restricted_databases['worker'].connect() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:t,true)"), {'t': tenant})
            with pytest.raises(ProgrammingError):
                connection.execute(text(f'SELECT count(*) FROM {table}'))


def test_grants_of_a_deactivated_member_can_still_be_revoked_but_not_issued(identity_setup):
    client = identity_setup['client']
    admin, _ = person(identity_setup, None, 'admin')
    _, member = person(identity_setup, 'leaver@example.org', 'dispatcher')
    assert grant(client, admin, member).status_code == 200
    with identity_setup['owner_factory']() as db:
        db.execute(text('UPDATE domain_memberships SET is_active=false WHERE id=:m'), {'m': member})
        db.commit()
    assert grant(client, admin, member, 'maintenance.manage').status_code == 404
    assert grant(client, admin, member, active=False, expected=1).status_code == 200
