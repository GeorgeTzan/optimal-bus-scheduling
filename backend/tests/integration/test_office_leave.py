"""Leave moves pending -> approved/rejected/cancelled only through configured routes, with one linked blocker."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_availability import PATTERNS, PERIODS, pattern, period, save, usable
from tests.integration.test_office_permissions import ROUTES, driver, grant, person

LEAVE = '/api/v1/office/leave-requests'
WINDOW = {'date_from': '2026-11-01', 'date_to': '2026-11-30'}


@pytest.fixture
def env(identity_setup):
    client, tenant = identity_setup['client'], identity_setup['first'].tenant_id
    admin, _ = person(identity_setup, None, 'admin')
    staff, staff_member = person(identity_setup, 'staff@example.org', 'dispatcher')
    boss, boss_member = person(identity_setup, 'boss@example.org', 'viewer')
    assert grant(client, admin, staff_member).status_code == 200
    a, b = driver(identity_setup, tenant, 'A1'), driver(identity_setup, tenant, 'B1')
    default = client.post(ROUTES, headers=admin, json={'request_id': str(uuid.uuid4()), 'membership_id': boss_member})
    assert default.status_code == 201
    return {'client': client, 'tenant': tenant, 'setup': identity_setup, 'admin': admin, 'staff': staff, 'staff_member': staff_member,
            'boss': boss, 'boss_member': boss_member, 'driver': a, 'other': b}


def ask(env, driver_id=None, headers=None, **changes):
    body = {'request_id': str(uuid.uuid4()), 'driver_id': driver_id or env['driver'], 'start_local': '2026-11-10T00:00:00',
            'end_local': '2026-11-12T00:00:00', 'category': 'annual', 'private_note': 'family matter', **changes}
    return env['client'].post(LEAVE, headers=headers or env['staff'], json=body)


def decide(env, leave, decision='approved', headers=None, **changes):
    body = {'request_id': str(uuid.uuid4()), 'expected_version': leave['version'], 'decision': decision, 'note': None, **changes}
    return env['client'].post(f"{LEAVE}/{leave['id']}/decision", headers=headers or env['boss'], json=body)


def cancel(env, leave, headers=None, **changes):
    body = {'request_id': str(uuid.uuid4()), 'expected_version': leave['version'], 'reason': 'Plans changed', **changes}
    return env['client'].post(f"{LEAVE}/{leave['id']}/cancel", headers=headers or env['boss'], json=body)


def link_driver(env, member, driver_id):
    with env['setup']['owner_factory']() as db:
        db.execute(text('UPDATE domain_memberships SET driver_id=:d WHERE id=:m'), {'d': driver_id, 'm': member})
        db.commit()


def rows(env, sql):
    with env['setup']['owner_factory']() as db:
        return db.execute(text(sql)).all()


def test_staff_enters_request_for_driver_without_private_fields(env):
    created = ask(env)
    assert created.status_code == 201, created.text[:300]
    value = created.json()
    assert value['state'] == 'pending' and value['driver_id'] == env['driver'] and 'private_note' not in value and 'category' not in value
    nobody, _ = person(env['setup'], 'nobody@example.org', 'dispatcher')
    assert ask(env, headers=nobody).status_code == 403
    assert ask(env, end_local='2026-11-10T00:00:00').status_code == 422
    assert ask(env, end_local=None).status_code == 422
    assert ask(env, driver_id=driver(env['setup'], env['setup']['second'].tenant_id, 'Z1')).status_code == 404
    with env['setup']['owner_factory']() as db:
        db.execute(text('UPDATE domain_drivers SET is_active=false WHERE id=:d'), {'d': env['other']})
        db.commit()
    assert ask(env, driver_id=env['other']).status_code == 409


def test_without_any_route_the_request_stays_pending_with_approver_missing(env):
    client, admin = env['client'], env['admin']
    route = client.get(ROUTES, headers=admin).json()['routes'][0]
    assert client.patch(f"{ROUTES}/{route['id']}", headers=admin, json={'request_id': str(uuid.uuid4()), 'expected_version': route['version'], 'is_active': False}).status_code == 200
    leave = ask(env).json()
    for headers in (env['boss'], env['admin']):
        rejected = decide(env, leave, headers=headers)
        assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'approver_missing'
    assert rows(env, 'SELECT state FROM domain_leave_requests') == [('pending',)]


def test_only_a_member_on_the_drivers_route_decides_and_titles_do_not_help(env):
    client = env['client']
    other, other_member = person(env['setup'], 'other@example.org', 'viewer')
    specific = client.post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['driver'], 'membership_id': other_member})
    assert specific.status_code == 201
    leave_a, leave_b = ask(env).json(), ask(env, driver_id=env['other']).json()
    assert decide(env, leave_b, headers=other).status_code == 403
    assert decide(env, leave_a, headers=env['boss']).status_code == 403
    assert decide(env, leave_a, headers=env['admin']).status_code == 403
    assert decide(env, leave_a, headers=env['staff']).status_code == 403
    assert decide(env, leave_a, headers=other).status_code == 200
    assert decide(env, leave_b, headers=env['boss']).status_code == 200


def test_own_leave_is_refused_through_the_explicit_driver_link(env):
    link_driver(env, env['boss_member'], env['driver'])
    leave = ask(env).json()
    refused = decide(env, leave)
    assert refused.status_code == 403 and refused.json()['detail']['code'] == 'own_leave'
    assert rows(env, 'SELECT state FROM domain_leave_requests') == [('pending',)]


def test_external_decision_records_recorder_and_stated_decision_maker(env):
    external = env['client'].post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['driver'], 'external_contact_name': 'Bus owner Nikos'}).json()
    leave = ask(env).json()
    nobody, _ = person(env['setup'], 'nobody@example.org', 'dispatcher')
    assert decide(env, leave, headers=nobody, external_route_id=external['id']).status_code == 403
    assert decide(env, leave, headers=env['staff'], external_route_id=external['id'] + 99).status_code == 422
    assert decide(env, leave, headers=env['boss'], external_route_id=external['id']).status_code == 403
    done = decide(env, leave, headers=env['staff'], external_route_id=external['id'])
    assert done.status_code == 200, done.text[:300]
    assert done.json()['decision_basis'] == 'external' and done.json()['stated_decision_maker'] == 'Bus owner Nikos'
    assert rows(env, "SELECT decided_by IS NOT NULL, stated_decision_maker FROM domain_leave_requests") == [(True, 'Bus owner Nikos')]
    link_driver(env, env['staff_member'], env['other'])
    second = ask(env, driver_id=env['other']).json()
    other_route = env['client'].post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['other'], 'external_contact_name': 'Owner B'}).json()
    assert decide(env, second, headers=env['staff'], external_route_id=other_route['id']).status_code == 403


def test_approval_creates_one_linked_blocker_and_rejection_creates_none(env):
    assert save(env, PATTERNS, [pattern(env['driver'])]).status_code == 200
    rejected = decide(env, ask(env).json(), 'rejected')
    assert rejected.status_code == 200 and rows(env, 'SELECT count(*) FROM domain_driver_availabilities WHERE source_leave_id IS NOT NULL') == [(0,)]
    assert 'impact_count' not in rejected.json()
    approved = decide(env, ask(env).json())
    assert approved.status_code == 200 and approved.json()['state'] == 'approved'
    assert rows(env, "SELECT kind,category,status FROM domain_driver_availabilities WHERE source_leave_id IS NOT NULL") == [('unavailable', 'leave', 'active')]
    window = (datetime(2026, 11, 9, 22, tzinfo=timezone.utc), datetime(2026, 11, 12, 22, tzinfo=timezone.utc))
    assert usable(env, *window).windows == ((datetime(2026, 11, 12, 6, tzinfo=timezone.utc), datetime(2026, 11, 12, 14, tzinfo=timezone.utc)),)
    assert decide(env, approved.json()).status_code == 409


def test_pending_leave_is_a_warning_and_never_a_blocker(env):
    assert save(env, PATTERNS, [pattern(env['driver'])]).status_code == 200
    before = usable(env, datetime(2026, 11, 10, 0, tzinfo=timezone.utc), datetime(2026, 11, 11, 0, tzinfo=timezone.utc))
    leave = ask(env).json()
    after = usable(env, datetime(2026, 11, 10, 0, tzinfo=timezone.utc), datetime(2026, 11, 11, 0, tzinfo=timezone.utc))
    assert after.windows == before.windows and after.windows and after.fingerprint == before.fingerprint
    assert [item['leave_id'] for item in after.warnings] == [leave['id']] and 'category' not in after.warnings[0]


def test_cancel_retires_only_its_blocker_and_needs_decision_authority(env):
    save(env, PERIODS, [period(env['driver'], 'unavailable', '2026-11-11T00:00:00', '2026-11-11T12:00:00')])
    approved = decide(env, ask(env).json()).json()
    assert cancel(env, approved, headers=env['staff']).status_code == 403
    assert cancel(env, approved, headers=env['admin']).status_code == 403
    cancelled = cancel(env, approved)
    assert cancelled.status_code == 200 and cancelled.json()['state'] == 'cancelled'
    assert rows(env, 'SELECT status FROM domain_driver_availabilities ORDER BY id') == [('active',), ('retired',)]
    assert rows(env, 'SELECT state, decided_by IS NOT NULL, cancel_reason FROM domain_leave_requests') == [('cancelled', True, 'Plans changed')]
    pending = ask(env).json()
    assert cancel(env, pending, headers=env['staff']).status_code == 200


def test_linked_period_cannot_be_edited_directly(env):
    decide(env, ask(env).json())
    linked = rows(env, 'SELECT id, version FROM domain_driver_availabilities WHERE source_leave_id IS NOT NULL')[0]
    edit = {**period(env['driver'], 'unavailable', '2026-11-10T00:00:00', '2026-11-11T00:00:00'), 'period_id': linked[0], 'expected_version': linked[1], 'status': 'retired'}
    refused = save(env, PERIODS, [edit])
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'linked_to_leave'


def test_retry_with_changed_payload_conflicts_and_concurrent_decisions_have_one_outcome(env):
    leave = ask(env).json()
    request_id = str(uuid.uuid4())
    first = decide(env, leave, request_id=request_id, note='ok')
    assert first.status_code == 200 and decide(env, leave, request_id=request_id, note='ok').json() == first.json()
    assert decide(env, leave, request_id=request_id, note='different').status_code == 409
    racing = ask(env).json()

    def submit(decision):
        return decide(env, racing, decision).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(submit, ['approved', 'rejected']))
    assert codes == [200, 409]
    assert rows(env, "SELECT count(*) FROM domain_driver_availabilities WHERE source_leave_id=%d" % racing['id'])[0][0] <= 1


def test_forced_failure_after_approval_leaves_no_orphan_blocker(env, monkeypatch):
    leave = ask(env).json()

    def explode(*args, **kwargs):
        raise RuntimeError('simulated failure')
    monkeypatch.setattr('app.api.office.office_record', explode)
    with pytest.raises(RuntimeError):
        decide(env, leave)
    monkeypatch.undo()
    assert rows(env, 'SELECT state FROM domain_leave_requests') == [('pending',)]
    assert rows(env, 'SELECT count(*) FROM domain_driver_availabilities') == [(0,)]


def test_reads_are_scoped_to_routes_and_private_fields_need_notes_access_or_a_route(env):
    client = env['client']
    narrow, narrow_member = person(env['setup'], 'narrow@example.org', 'viewer')
    assert client.post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['other'], 'membership_id': narrow_member}).status_code == 201
    ask(env), ask(env, driver_id=env['other'])
    seen = lambda headers: client.get(LEAVE, headers=headers, params=WINDOW)
    everyone = seen(env['staff']).json()['items']
    assert len(everyone) == 2 and all('private_note' not in item and 'category' not in item for item in everyone)
    boss_items = seen(env['boss']).json()['items']
    assert len(boss_items) == 1 and boss_items[0]['driver_id'] == env['driver'] and boss_items[0]['private_note'] == 'family matter'
    assert boss_items[0]['decision'] == {'member': True, 'external': []} and everyone[0]['decision'] == {'member': False, 'external': []}
    narrow_items = seen(narrow).json()['items']
    assert [item['driver_id'] for item in narrow_items] == [env['other']] and narrow_items[0]['category'] == 'annual'
    outsider, _ = person(env['setup'], 'outsider@example.org', 'viewer')
    assert seen(outsider).status_code == 403
    assert client.put('/api/v1/office/grants', headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'membership_id': env['staff_member'],
                                                                             'capability': 'office.notes.read', 'is_active': True, 'expected_version': None}).status_code == 200
    assert all(item['private_note'] == 'family matter' for item in seen(env['staff']).json()['items'])
    assert client.get(PERIODS, headers=outsider, params=WINDOW).status_code == 403
    assert client.get(PERIODS, headers=env['boss'], params=WINDOW).status_code == 200


def test_routes_to_deactivated_members_are_ignored_so_the_next_route_or_a_clear_error_applies(env):
    gone, gone_member = person(env['setup'], 'gone@example.org', 'viewer')
    assert env['client'].post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['driver'], 'membership_id': gone_member}).status_code == 201
    with env['setup']['owner_factory']() as db:
        db.execute(text('UPDATE domain_memberships SET is_active=false WHERE id=:m'), {'m': gone_member})
        db.commit()
    assert decide(env, ask(env).json()).status_code == 200
    default = env['client'].get(ROUTES, headers=env['admin']).json()['routes'][0]
    assert env['client'].patch(f"{ROUTES}/{default['id']}", headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'expected_version': default['version'], 'is_active': False}).status_code == 200
    refused = decide(env, ask(env).json(), headers=env['admin'])
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'approver_missing'


def test_period_reads_return_only_covered_drivers_and_hide_category_without_notes_access(env):
    save(env, PERIODS, [period(env['driver'], 'unavailable', '2026-11-05T08:00:00', '2026-11-05T12:00:00', category='sick'),
                        period(env['other'], 'unavailable', '2026-11-05T08:00:00', '2026-11-05T12:00:00', category='training')])
    narrow, narrow_member = person(env['setup'], 'narrow@example.org', 'viewer')
    assert env['client'].post(ROUTES, headers=env['admin'], json={'request_id': str(uuid.uuid4()), 'driver_id': env['other'], 'membership_id': narrow_member}).status_code == 201
    seen = lambda headers: env['client'].get(PERIODS, headers=headers, params=WINDOW).json()['items']
    everyone = seen(env['staff'])
    assert len(everyone) == 2 and all('category' not in item for item in everyone)
    covered = seen(narrow)
    assert [item['driver_id'] for item in covered] == [env['other']] and covered[0]['category'] == 'training'
