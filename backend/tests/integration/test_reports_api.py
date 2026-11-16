import uuid
from datetime import date
from tests.integration.test_identity import identity_setup
from tests.integration.test_office_permissions import person
from tests.integration.test_reports_coverage import published_day
from tests.integration.test_schedule_changes import APPLY
from tests.integration.test_work_rules_gates import change_request, publish, trip

MONTHLY = '/api/v1/reports/monthly'
JUNE = date(2026, 6, 1)


def management(setup):
    return person(setup, 'management@example.org', 'management')[0]


def monthly(setup, headers, month):
    return setup['client'].get(MONTHLY, headers=headers, params={'month': month})


def test_access_by_role(identity_setup):
    for role, code in (('management', 200), ('admin', 200), ('dispatcher', 403), ('viewer', 403), ('fleet_manager', 403)):
        headers, _ = person(identity_setup, f'{role}@example.org', role)
        assert monthly(identity_setup, headers, '2026-06').status_code == code
        assert identity_setup['client'].get('/api/v1/reports/coverage/line?month=2026-06&line=none', headers=headers).status_code == code
    assert identity_setup['client'].get(f'{MONTHLY}?month=2026-06').status_code in (401, 403)


def test_month_parameter_validation(identity_setup):
    headers = management(identity_setup)
    for bad in ('2026-13', '2026-6', 'abc', '2099-01', '2020-01', '2026-00', '2026-06-01'):
        assert monthly(identity_setup, headers, bad).status_code == 422, bad
        assert identity_setup['client'].get('/api/v1/reports/coverage/line', headers=headers, params={'month': bad, 'line': 'none'}).status_code == 422, bad
    assert identity_setup['client'].get(MONTHLY, headers=headers).status_code == 422


def test_parse_month_bounds():
    from fastapi import HTTPException
    from app.domain.reports.service import parse_month
    today = date(2026, 11, 15)
    assert parse_month('2026-11', today) == date(2026, 11, 1)
    assert parse_month('2024-01', today) == date(2024, 1, 1)
    for bad in ('2026-12', '2023-12', '2026-1', ' 2026-06', '2026-06\n'):
        try:
            parse_month(bad, today)
        except HTTPException as error:
            assert error.status_code == 422
        else:
            raise AssertionError(bad)


def test_empty_month_returns_empty_sections(identity_setup):
    body = monthly(identity_setup, management(identity_setup), '2026-05').json()
    assert body['month'] == '2026-05' and body['timezone'] == 'Europe/Athens'
    assert body['coverage'] == [] and body['overtime']['monthly'] == [] and body['overtime']['published_days'] == 0
    assert body['last_export'] is None and body['changed_since_export'] is False


def test_changed_since_export_flips_after_republish(identity_setup):
    from db.models import User
    from app.domain.reports.models import ReportExport
    from app.domain.reports.service import fingerprint
    client, headers, vehicle, published = published_day(identity_setup)
    mgmt = management(identity_setup)
    tenant = identity_setup['first'].tenant_id
    with identity_setup['owner_factory']() as db:
        user = db.query(User).filter_by(email='management@example.org').one()
        before = fingerprint(db, tenant, JUNE)
        assert before == fingerprint(db, tenant, JUNE) and len(before) == 64
        assert before != fingerprint(db, identity_setup['second'].tenant_id, JUNE)
        db.add(ReportExport(tenant_id=tenant, month=JUNE, format='xlsx', generated_by=user.id, fingerprint=before))
        db.commit()
        name = user.full_name or user.email
    body = monthly(identity_setup, mgmt, '2026-06').json()
    assert body['changed_since_export'] is False
    assert body['last_export']['format'] == 'xlsx' and body['last_export']['by'] == name and body['last_export']['generated_at']
    assert body['overtime']['published_days'] == 1 and len(body['coverage']) == 1
    assert monthly(identity_setup, mgmt, '2026-07').json()['last_export'] is None
    cancelled = trip(published, 'T2')
    request = {**change_request(client, headers, published, {}), 'reviewed_not_started': [cancelled],
               'patches': [{'trip_id': cancelled, 'operation': 'cancel', 'reason': 'Road closed'}], 'request_id': str(uuid.uuid4())}
    applied = client.post(APPLY, headers=headers, json=request)
    assert applied.status_code == 201, applied.text[:600]
    publish(client, headers, applied.json())
    body = monthly(identity_setup, mgmt, '2026-06').json()
    assert body['changed_since_export'] is True and body['last_export']['format'] == 'xlsx'
    with identity_setup['owner_factory']() as db:
        assert fingerprint(db, tenant, JUNE) != before


def test_changed_since_export_flips_after_recorded_delay(identity_setup):
    from tests.integration.test_reports_files import get_export
    from tests.integration.test_work_rules_loader import report_delay
    client, headers, vehicle, published = published_day(identity_setup)
    mgmt = management(identity_setup)
    assert get_export(identity_setup, mgmt, 'xlsx', 'en').status_code == 200
    assert monthly(identity_setup, mgmt, '2026-06').json()['changed_since_export'] is False
    report_delay(client, headers, trip(published, 'T1'), 40)
    body = monthly(identity_setup, mgmt, '2026-06').json()
    assert body['changed_since_export'] is True and body['last_export']['format'] == 'xlsx'
    assert monthly(identity_setup, mgmt, '2026-07').json()['changed_since_export'] is False


def test_line_drilldown_route(identity_setup):
    published_day(identity_setup)
    mgmt = management(identity_setup)
    client = identity_setup['client']
    empty = client.get('/api/v1/reports/coverage/line?month=2026-06&line=none', headers=mgmt)
    assert empty.status_code == 200 and empty.json() == []
    line = monthly(identity_setup, mgmt, '2026-06').json()['coverage'][0]['line']
    days = client.get('/api/v1/reports/coverage/line', headers=mgmt, params={'month': '2026-06', 'line': line})
    assert days.status_code == 200 and [day['uncovered'] for day in days.json()] == [['T2']]
    assert client.get('/api/v1/reports/coverage/line?month=2026-06', headers=mgmt).status_code == 422
