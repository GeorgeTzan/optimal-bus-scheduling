"""Planned maintenance reservations and actual out-of-service holds stay distinct; only an explicit release ends a hold."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_availability import PATTERNS, pattern, save
from tests.integration.test_office_permissions import driver, grant, person

VEHICLE_PERIODS = '/api/v1/office/vehicle-periods'


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


def vehicle(setup, tenant_id, code):
    with setup['owner_factory']() as db:
        value = db.execute(text("INSERT INTO domain_vehicles (tenant_id,code,bus_type,is_active) VALUES (:t,:c,'standard_12m',true) RETURNING id"), {'t': tenant_id, 'c': code}).scalar_one()
        db.commit()
    return value


@pytest.fixture
def env(identity_setup):
    client, tenant = identity_setup['client'], identity_setup['first'].tenant_id
    admin, _ = person(identity_setup, None, 'admin')
    night, night_member = person(identity_setup, 'night@example.org', 'dispatcher')
    fleet, fleet_member = person(identity_setup, 'fleet@example.org', 'fleet_manager')
    for member, capabilities in ((night_member, ['maintenance.manage']), (fleet_member, ['maintenance.manage', 'maintenance.release'])):
        for capability in capabilities:
            assert grant(client, admin, member, capability).status_code == 200
    return {'client': client, 'tenant': tenant, 'setup': identity_setup, 'admin': admin, 'night': night, 'fleet': fleet,
            'vehicle': vehicle(identity_setup, tenant, 'BUS1'), 'driver': driver(identity_setup, tenant, 'W1')}


def hold(env, kind='out_of_service', start='2026-10-01T08:00:00', end=None, headers=None, **changes):
    body = {'request_id': str(uuid.uuid4()), 'vehicle_id': env['vehicle'], 'kind': kind, 'start_local': start, 'end_local': end, **changes}
    return env['client'].post(VEHICLE_PERIODS, headers=headers or env['night'], json=body)


def release(env, row, at='2026-10-05T08:00:00', headers=None, **changes):
    body = {'request_id': str(uuid.uuid4()), 'expected_version': row['version'], 'released_at_local': at, 'note': 'Repaired and checked by the workshop', **changes}
    return env['client'].post(f"{VEHICLE_PERIODS}/{row['id']}/release", headers=headers or env['fleet'], json=body)


def cancel(env, row, headers=None):
    body = {'request_id': str(uuid.uuid4()), 'expected_version': row['version'], 'reason': 'Entered by mistake'}
    return env['client'].post(f"{VEHICLE_PERIODS}/{row['id']}/cancel", headers=headers or env['night'], json=body)


def free(env, start, end, driver_id=None):
    from app.domain.office.availability import availability_for_resources
    key = (driver_id, env['vehicle'])
    with env['setup']['owner_factory']() as db:
        return availability_for_resources(db, env['tenant'], [key], start, end)[key]


def test_planned_reservation_needs_a_finite_end_and_a_hold_stays_open(env):
    assert hold(env, 'planned_maintenance').status_code == 422
    assert hold(env, 'out_of_service', end='2026-10-02T08:00:00').status_code == 422
    planned = hold(env, 'planned_maintenance', end='2026-10-02T08:00:00')
    assert planned.status_code == 200 and planned.json()['end_utc'] is not None
    open_hold = hold(env).json()
    assert open_hold['end_utc'] is None and open_hold['status'] == 'active'


def test_estimate_passing_never_releases_a_hold(env):
    created = hold(env, estimated_end_local='2026-10-03T08:00:00', responsible_label='Workshop A')
    assert created.status_code == 200 and created.json()['estimated_end_utc'] is not None
    assert free(env, utc(2026, 10, 20), utc(2026, 10, 21)).windows == ()


def test_release_needs_its_own_grant_and_a_real_past_time_after_the_start(env):
    row = hold(env).json()
    assert release(env, row, headers=env['night']).status_code == 403
    assert release(env, row, at='2026-09-30T08:00:00').status_code == 422
    assert release(env, row, at='2099-01-01T08:00:00').status_code == 422
    done = release(env, row)
    assert done.status_code == 200 and done.json()['status'] == 'released' and done.json()['end_utc'] == '2026-10-05T05:00:00+00:00'
    assert release(env, done.json()).status_code == 409
    planned = hold(env, 'planned_maintenance', end='2026-10-02T08:00:00').json()
    assert release(env, planned).status_code == 409


def test_releasing_one_hold_leaves_an_overlapping_hold_blocking(env):
    first, second = hold(env).json(), hold(env, start='2026-10-02T08:00:00').json()
    assert release(env, first).status_code == 200
    assert free(env, utc(2026, 10, 6), utc(2026, 10, 7)).windows == ()
    assert release(env, second, at='2026-10-06T12:00:00').status_code == 200
    assert free(env, utc(2026, 10, 10), utc(2026, 10, 11)).windows == ((utc(2026, 10, 10), utc(2026, 10, 11)),)
    assert free(env, utc(2026, 10, 6, 6), utc(2026, 10, 6, 8)).windows == ()


def test_cancel_is_not_release_and_each_kind_needs_its_own_authority(env):
    planned, open_hold = hold(env, 'planned_maintenance', end='2026-10-02T08:00:00').json(), hold(env).json()
    assert cancel(env, open_hold).status_code == 403
    assert cancel(env, planned).status_code == 200
    mistaken = cancel(env, open_hold, headers=env['fleet'])
    assert mistaken.status_code == 200 and mistaken.json()['status'] == 'cancelled'
    with env['setup']['owner_factory']() as db:
        assert db.execute(text("SELECT status, released_at IS NULL, cancel_reason FROM domain_vehicle_availabilities ORDER BY id")).all() == [
            ('cancelled', True, 'Entered by mistake'), ('cancelled', True, 'Entered by mistake')]
    assert free(env, utc(2026, 10, 20), utc(2026, 10, 21)).windows is not None


def test_driver_and_vehicle_constraints_intersect(env):
    with env['setup']['owner_factory']() as db:
        member = db.execute(text("SELECT m.id FROM domain_memberships m JOIN users u ON u.id=m.user_id WHERE u.email='first@example.org'")).scalar_one()
    assert grant(env['client'], env['admin'], member).status_code == 200
    assert save({**env, 'staff': env['admin']}, PATTERNS, [pattern(env['driver'], valid_from='2026-10-01', valid_until='2026-12-31')]).status_code == 200
    assert free(env, utc(2026, 10, 12, 0), utc(2026, 10, 12, 23), env['driver']).windows == ((utc(2026, 10, 12, 5), utc(2026, 10, 12, 13)),)
    assert hold(env, 'planned_maintenance', start='2026-10-12T10:00:00', end='2026-10-12T12:00:00').status_code == 200
    assert free(env, utc(2026, 10, 12, 0), utc(2026, 10, 12, 23), env['driver']).windows == ((utc(2026, 10, 12, 5), utc(2026, 10, 12, 7)), (utc(2026, 10, 12, 9), utc(2026, 10, 12, 13)))
    assert hold(env, start='2026-10-12T00:00:00').status_code == 200
    assert free(env, utc(2026, 10, 12, 0), utc(2026, 10, 12, 23), env['driver']).windows == ()


def test_stale_versions_foreign_and_archived_vehicles_are_refused(env):
    row = hold(env, 'planned_maintenance', end='2026-10-02T08:00:00').json()
    update = {'request_id': str(uuid.uuid4()), 'vehicle_id': env['vehicle'], 'kind': 'planned_maintenance', 'start_local': '2026-10-01T08:00:00',
              'end_local': '2026-10-03T08:00:00', 'period_id': row['id'], 'expected_version': row['version']}
    extended = env['client'].post(VEHICLE_PERIODS, headers=env['night'], json=update)
    assert extended.status_code == 200 and extended.json()['version'] == 2
    assert env['client'].post(VEHICLE_PERIODS, headers=env['night'], json={**update, 'request_id': str(uuid.uuid4())}).status_code == 409
    assert hold(env, **{'vehicle_id': vehicle(env['setup'], env['setup']['second'].tenant_id, 'FOREIGN')}).status_code == 404
    with env['setup']['owner_factory']() as db:
        db.execute(text('UPDATE domain_vehicles SET is_active=false WHERE id=:v'), {'v': env['vehicle']})
        db.commit()
    assert hold(env).status_code == 409


def test_archiving_a_vehicle_with_an_active_period_is_refused_until_it_ends(env):
    row = hold(env).json()
    archive = lambda: env['client'].patch(f"/api/v1/vehicles/{env['vehicle']}", headers=env['admin'], json={'version': 1, 'is_active': False})
    refused = archive()
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'active_office_periods'
    assert release(env, row).status_code == 200
    assert archive().status_code == 200


def test_vehicle_periods_are_readable_only_with_the_maintenance_grant(env):
    hold(env)
    outsider, _ = person(env['setup'], 'outsider@example.org', 'viewer')
    query = {'date_from': '2026-10-01', 'date_to': '2026-10-31'}
    assert env['client'].get(VEHICLE_PERIODS, headers=outsider, params=query).status_code == 403
    items = env['client'].get(VEHICLE_PERIODS, headers=env['night'], params=query).json()['items']
    assert len(items) == 1 and items[0]['kind'] == 'out_of_service'
    assert hold(env, headers=outsider).status_code == 403


def test_a_hold_cannot_be_lifted_by_moving_its_start_without_the_release_grant(env):
    row = hold(env).json()
    update = {'request_id': str(uuid.uuid4()), 'vehicle_id': env['vehicle'], 'kind': 'out_of_service', 'start_local': '2026-10-01T08:00:00',
              'period_id': row['id'], 'expected_version': row['version'], 'estimated_end_local': '2026-10-09T08:00:00'}
    send = lambda headers, **changes: env['client'].post(VEHICLE_PERIODS, headers=headers, json={**update, 'request_id': str(uuid.uuid4()), **changes})
    assert send(env['night'], start_local='2099-01-01T08:00:00', estimated_end_local=None).status_code == 403
    changed = send(env['night'])
    assert changed.status_code == 200 and changed.json()['estimated_end_utc'] is not None
    assert send(env['fleet'], start_local='2026-10-02T08:00:00', expected_version=changed.json()['version']).status_code == 200
