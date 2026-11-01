"""Working patterns and dated driver periods produce explicit usable windows, unknowns and findings."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_permissions import driver, grant, person

PATTERNS = '/api/v1/office/working-patterns'
PERIODS = '/api/v1/office/driver-periods'


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


@pytest.fixture
def office(identity_setup):
    client, tenant = identity_setup['client'], identity_setup['first'].tenant_id
    admin, _ = person(identity_setup, None, 'admin')
    staff, member = person(identity_setup, 'office@example.org', 'dispatcher')
    assert grant(client, admin, member).status_code == 200
    return {'client': client, 'tenant': tenant, 'staff': staff, 'admin': admin, 'driver': driver(identity_setup, tenant, 'W1'), 'setup': identity_setup}


def pattern(driver_id, **changes):
    return {'driver_id': driver_id, 'weekday_mask': 127, 'local_start': '08:00', 'local_end': '16:00', 'ends_next_day': False,
            'valid_from': '2026-11-01', 'valid_until': '2027-10-31', **changes}


def period(driver_id, kind, start, end, **changes):
    return {'driver_id': driver_id, 'kind': kind, 'start_local': start, 'end_local': end, 'category': 'other' if kind == 'unavailable' else None, **changes}


def save(office, path, items, headers=None, request_id=None):
    return office['client'].post(path, headers=headers or office['staff'], json={'request_id': request_id or str(uuid.uuid4()), 'items': items})


def usable(office, start, end, driver_id=None):
    from app.domain.office.availability import availability_for_resources
    key = (driver_id or office['driver'], None)
    with office['setup']['owner_factory']() as db:
        return availability_for_resources(db, office['tenant'], [key], start, end)[key]


def test_missing_basis_is_unknown_not_available(office):
    result = usable(office, utc(2026, 11, 2, 6), utc(2026, 11, 2, 10))
    assert result.windows is None and [item['code'] for item in result.findings] == ['working_time_unknown']


def test_pattern_gives_windows_and_unavailable_subtracts_half_open(office):
    assert save(office, PATTERNS, [pattern(office['driver'])]).status_code == 200
    assert save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-03T08:00:00', '2026-11-03T10:00:00')]).status_code == 200
    result = usable(office, utc(2026, 11, 3, 0), utc(2026, 11, 3, 23))
    assert result.windows == ((utc(2026, 11, 3, 8), utc(2026, 11, 3, 14)),)
    assert len(result.blockers) == 1


def test_known_empty_when_blockers_cover_horizon_and_retire_restores_unknown(office):
    created = save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T00:00:00', None, category='sick')])
    assert created.status_code == 200
    item = created.json()['items'][0]
    assert 'category' not in item
    assert usable(office, utc(2026, 11, 3), utc(2026, 11, 4)).windows == ()
    retire = save(office, PERIODS, [{**period(office['driver'], 'unavailable', '2026-11-02T00:00:00', None, category='sick'),
                                      'period_id': item['id'], 'expected_version': item['version'], 'status': 'retired'}])
    assert retire.status_code == 200
    assert usable(office, utc(2026, 11, 3), utc(2026, 11, 4)).windows is None


def test_overnight_pattern_from_previous_date_covers_after_midnight_trip(office):
    assert save(office, PATTERNS, [pattern(office['driver'], local_start='22:00', local_end='06:00', ends_next_day=True)]).status_code == 200
    start, end = utc(2026, 11, 2, 23), utc(2026, 11, 3, 0)
    assert usable(office, start, end).windows == ((start, end),)


@pytest.mark.parametrize('day,clock,valid,horizon', [
    ('2027-03-28', '03:30', ('2027-03-01', '2027-03-31'), (utc(2027, 3, 27, 22), utc(2027, 3, 28, 21))),
    ('2027-10-31', '03:30', ('2027-10-01', '2027-10-31'), (utc(2027, 10, 30, 21), utc(2027, 10, 31, 22)))])
def test_pattern_in_dst_gap_or_fold_yields_finding_then_dated_window_resolves_it(office, day, clock, valid, horizon):
    assert save(office, PATTERNS, [pattern(office['driver'], weekday_mask=64, local_start=clock, local_end='05:00', valid_from=valid[0], valid_until=valid[1])]).status_code == 200
    result = usable(office, *horizon)
    assert result.windows is None
    assert [(item['code'], item['date']) for item in result.findings if item['code'] == 'working_window_needs_resolution'] == [('working_window_needs_resolution', day)]
    assert save(office, PERIODS, [period(office['driver'], 'available', day + 'T06:00:00', day + 'T12:00:00')]).status_code == 200
    result = usable(office, *horizon)
    assert result.windows is not None and len(result.windows) == 1 and not result.findings


def test_open_end_only_for_unavailable_and_naive_local_times_only(office):
    assert save(office, PERIODS, [period(office['driver'], 'available', '2026-11-02T08:00:00', None)]).status_code == 422
    assert save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T08:00:00+00:00', None)]).status_code == 422
    assert save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T08:00:00', '2026-11-02T08:00:00')]).status_code == 422
    assert save(office, PERIODS, [period(office['driver'], 'unavailable', '2027-03-28T03:30:00', '2027-03-28T12:00:00')]).status_code == 422


def test_pattern_validity_batch_size_and_rollback_bounds(office):
    assert save(office, PATTERNS, [pattern(office['driver'], valid_until='2027-11-02')]).status_code == 200
    assert save(office, PATTERNS, [pattern(office['driver'], valid_until='2027-11-03')]).status_code == 422
    assert save(office, PATTERNS, [pattern(office['driver'], weekday_mask=0)]).status_code == 422
    assert save(office, PATTERNS, [pattern(office['driver'])] * 101).status_code == 422
    foreign = driver(office['setup'], office['setup']['second'].tenant_id, 'X1')
    with office['setup']['owner_factory']() as db:
        before = db.execute(text('SELECT count(*) FROM domain_driver_working_patterns')).scalar_one()
    assert save(office, PATTERNS, [pattern(office['driver'], valid_from='2028-01-01', valid_until='2028-02-01'), pattern(foreign)]).status_code == 404
    with office['setup']['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_driver_working_patterns')).scalar_one() == before


def test_stale_version_conflicts_and_leaves_audit_unchanged(office):
    first = save(office, PATTERNS, [pattern(office['driver'])]).json()['items'][0]
    update = {**pattern(office['driver'], local_end='17:00'), 'pattern_id': first['id'], 'expected_version': first['version']}
    assert save(office, PATTERNS, [update]).json()['items'][0]['version'] == 2
    with office['setup']['owner_factory']() as db:
        before = db.execute(text('SELECT count(*) FROM domain_office_audit')).scalar_one()
    assert save(office, PATTERNS, [update]).status_code == 409
    with office['setup']['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_office_audit')).scalar_one() == before


def test_availability_writes_and_reads_require_the_grant(office):
    nobody, _ = person(office['setup'], 'nobody@example.org', 'dispatcher')
    assert save(office, PATTERNS, [pattern(office['driver'])], headers=nobody).status_code == 403
    assert save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T08:00:00', None)], headers=nobody).status_code == 403
    query = {'date_from': '2026-11-01', 'date_to': '2026-11-30'}
    assert office['client'].get(PERIODS, headers=nobody, params=query).status_code == 403
    assert office['client'].get(PERIODS, headers=office['staff'], params=query).status_code == 200
    assert office['client'].get(PERIODS, headers=office['staff'], params={'date_from': '2026-01-01', 'date_to': '2026-12-31'}).status_code == 422


def test_retire_endpoints_need_the_version_and_the_grant_and_refuse_linked_absences(office):
    pattern_row = save(office, PATTERNS, [pattern(office['driver'])]).json()['items'][0]
    period_row = save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T08:00:00', None)]).json()['items'][0]
    nobody, _ = person(office['setup'], 'nobody@example.org', 'dispatcher')
    body = lambda row, **changes: {'request_id': str(uuid.uuid4()), 'expected_version': row['version'], **changes}
    for path, row in ((PATTERNS, pattern_row), (PERIODS, period_row)):
        assert office['client'].post(f"{path}/{row['id']}/retire", headers=nobody, json=body(row)).status_code == 403
        assert office['client'].post(f"{path}/{row['id']}/retire", headers=office['staff'], json=body(row, expected_version=row['version'] + 1)).status_code == 409
        retired = office['client'].post(f"{path}/{row['id']}/retire", headers=office['staff'], json=body(row))
        assert retired.status_code == 200 and retired.json()['status'] == 'retired' and retired.json()['version'] == row['version'] + 1
        assert office['client'].post(f"{path}/{row['id']}/retire", headers=office['staff'], json=body(retired.json())).status_code == 409
    with office['setup']['owner_factory']() as db:
        db.execute(text("INSERT INTO domain_leave_requests (tenant_id,driver_id,start_utc,end_utc,category,requested_by,requested_at) SELECT :t,:d,now(),now()+interval '1 day','annual',id,now() FROM users WHERE ktel_id=:t LIMIT 1"), {'t': office['tenant'], 'd': office['driver']})
        leave = db.execute(text('SELECT id FROM domain_leave_requests')).scalar_one()
        linked = db.execute(text("INSERT INTO domain_driver_availabilities (tenant_id,driver_id,kind,start_utc,end_utc,category,source_leave_id,recorded_by,recorded_at) SELECT :t,:d,'unavailable',now(),now()+interval '1 day','leave',:l,id,now() FROM users WHERE ktel_id=:t LIMIT 1 RETURNING id"), {'t': office['tenant'], 'd': office['driver'], 'l': leave}).scalar_one()
        db.commit()
    refused = office['client'].post(f"{PERIODS}/{linked}/retire", headers=office['staff'], json={'request_id': str(uuid.uuid4()), 'expected_version': 1})
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'linked_to_leave'


def test_a_dated_window_later_the_same_day_still_replaces_the_weekly_pattern(office):
    assert save(office, PATTERNS, [pattern(office['driver'])]).status_code == 200
    assert save(office, PERIODS, [period(office['driver'], 'available', '2026-11-03T13:00:00', '2026-11-03T20:00:00')]).status_code == 200
    before = usable(office, utc(2026, 11, 2, 22), utc(2026, 11, 3, 10))
    assert before.windows == ()
    assert [blocker for blocker in before.blockers] == []


def test_an_absence_cannot_be_changed_or_retired_by_the_member_it_concerns(office):
    mine, mine_member = person(office['setup'], 'self@example.org', 'dispatcher')
    assert grant(office['client'], office['admin'], mine_member).status_code == 200
    with office['setup']['owner_factory']() as db:
        db.execute(text('UPDATE domain_memberships SET driver_id=:d WHERE id=:m'), {'d': office['driver'], 'm': mine_member})
        db.commit()
    row = save(office, PERIODS, [period(office['driver'], 'unavailable', '2026-11-02T08:00:00', None)]).json()['items'][0]
    retire = lambda headers: office['client'].post(f"{PERIODS}/{row['id']}/retire", headers=headers, json={'request_id': str(uuid.uuid4()), 'expected_version': row['version']})
    refused = retire(mine)
    assert refused.status_code == 403 and refused.json()['detail']['code'] == 'own_absence'
    edit = {**period(office['driver'], 'available', '2026-11-02T08:00:00', '2026-11-02T09:00:00'), 'period_id': row['id'], 'expected_version': row['version']}
    assert save(office, PERIODS, [edit], headers=mine).status_code == 403
    assert save(office, PERIODS, [{**edit, 'kind': 'unavailable', 'category': 'other', 'status': 'retired'}], headers=mine).status_code == 403
    assert retire(office['staff']).status_code == 200
