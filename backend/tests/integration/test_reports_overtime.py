import uuid
from datetime import date
from tests.integration.test_identity import identity_setup
from tests.integration.test_schedule_changes import APPLY
from tests.integration.test_work_rules_gates import FIRST, SECOND, OVERTIME_DAY, assign, change_request, draft, driver_of, fleet, publish

JUNE = ('2026-06-01', '2026-06-02', '2026-06-03')
BOTH = {'T1': FIRST, 'T2': FIRST}


def published_june(setup, before=None, plans=None, days=JUNE):
    client, headers, made, vehicle = fleet(setup, OVERTIME_DAY, days=days)
    drafts = [draft(client, headers, day) for day in days]
    first, second = driver_of(drafts[0], FIRST), driver_of(drafts[0], SECOND)
    if before:
        before(client, headers, first, second)
    published = [publish(client, headers, assign(client, headers, revision, (plans or {}).get(day, BOTH))) for day, revision in zip(days, drafts)]
    return client, headers, first, second, published


def put_baseline(client, headers, driver_id, as_of, minutes):
    body = {'expected_version': 0, 'as_of': as_of, 'overtime_minutes': minutes, 'last_duty_end': None,
            'last_weekly_rest_end': None, 'last_weekly_rest_at_base': False, 'owed_rest_minutes': 0}
    saved = client.put(f"/api/v1/work-rules/drivers/{driver_id}/baseline", headers=headers, json=body)
    assert saved.status_code == 200, saved.text[:400]


def store_baseline(setup, driver_id, as_of, minutes):
    from app.domain.workrules.models import DriverWorkBaseline
    with setup['owner_factory']() as db:
        tenant = setup['first'].tenant_id
        row = db.query(DriverWorkBaseline).filter_by(tenant_id=tenant, driver_id=driver_id).first()
        if row is None:
            row = DriverWorkBaseline(tenant_id=tenant, driver_id=driver_id, version=1)
            db.add(row)
        row.as_of, row.overtime_minutes = as_of, minutes
        db.commit()


def report(setup, today, month=date(2026, 6, 1)):
    from app.domain.reports.overtime import overtime_report
    with setup['owner_factory']() as db:
        return overtime_report(db, setup['first'].tenant_id, month, today)


def overtime_of(setup, driver_id, days, emergency=False):
    from app.domain.workrules.loader import published_duty_facts
    with setup['owner_factory']() as db:
        _, facts = published_duty_facts(db, setup['first'].tenant_id, date(2026, 1, 1), date(2026, 12, 31))
    return sum(f.overtime_minutes for d, f in facts[str(driver_id)] if d.service_date.isoformat() in days and d.emergency == emergency)


def row_of(rows, driver_id):
    return next(r for r in rows if r['driver_id'] == driver_id)


def test_cap_used_matches_driver_week(identity_setup):
    from app.domain.workrules.loader import driver_week
    client, headers, first, second, _ = published_june(identity_setup)
    rep = report(identity_setup, date(2026, 7, 15))
    row = row_of(rep['cap'], first)
    with identity_setup['owner_factory']() as db:
        week = driver_week(db, identity_setup['first'].tenant_id, first, date(2026, 6, 30))
    assert rep['as_of'] == '2026-06-30' and rep['limit'] == 7200 and rep['absolute_limit'] == 10800 and rep['published_days'] == 3
    assert row['used'] == week['overtime_year_minutes'] == overtime_of(identity_setup, first, JUNE)
    assert row['used'] > 0 and row['planned'] == 0 and row['status'] == 'within'
    assert row['remaining'] == 7200 - row['used'] and row['projection_month'] is None and row['active'] is True
    assert row['name'] == FIRST and row['code']


def test_current_month_splits_past_and_planned(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup)
    rep = report(identity_setup, date(2026, 6, 2))
    row = row_of(rep['cap'], first)
    assert rep['as_of'] == '2026-06-02'
    assert row['used'] == overtime_of(identity_setup, first, JUNE[:2]) and row['planned'] == overtime_of(identity_setup, first, JUNE[2:])
    assert row['planned'] > 0 and row['remaining'] == 7200 - row['used'] - row['planned']


def test_baseline_inside_month_counted_once(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup, before=lambda c, h, d, _: put_baseline(c, h, d, '2026-06-01', 6000))
    row = row_of(report(identity_setup, date(2026, 7, 15))['cap'], first)
    assert row['used'] == 6000 + overtime_of(identity_setup, first, JUNE[1:]) and row['status'] == 'close'


def test_reached_and_projection(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup)
    store_baseline(identity_setup, first, date(2026, 6, 1), 7200)
    row = row_of(report(identity_setup, date(2026, 7, 15))['cap'], first)
    assert row['status'] == 'reached' and row['remaining'] == 0 and row['projection_month'] is None
    june = overtime_of(identity_setup, first, JUNE)
    store_baseline(identity_setup, first, date(2026, 5, 31), 3000)
    rep = report(identity_setup, date(2026, 7, 15))
    row = row_of(rep['cap'], first)
    assert row['status'] == 'within' and row['used'] == 3000 + june and row['projection_month'] is None
    assert rep['cap'][0]['driver_id'] == first
    store_baseline(identity_setup, first, date(2026, 5, 31), 7200 - 2 * june)
    row = row_of(report(identity_setup, date(2026, 7, 15))['cap'], first)
    assert row['used'] == 7200 - june and row['projection_month'] == '2026-07'


def test_baseline_after_as_of_is_ignored(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup, before=lambda c, h, d, _: put_baseline(c, h, d, '2026-06-01', 3000))
    row = row_of(report(identity_setup, date(2026, 7, 15), month=date(2026, 5, 1))['cap'], first)
    assert row['used'] == 0 and row['planned'] == 0 and row['absolute_total'] == 0 and row['projection_month'] is None
    assert row_of(report(identity_setup, date(2026, 7, 15))['cap'], first)['used'] == 3000 + overtime_of(identity_setup, first, JUNE[1:])


def test_emergency_in_absolute_only(identity_setup):
    client, headers, first, second, published = published_june(identity_setup, plans={JUNE[1]: {'T1': SECOND, 'T2': FIRST}})
    request = {**change_request(client, headers, published[1], {'T1': FIRST}), 'emergency': True}
    applied = client.post(APPLY, headers=headers, json={**request, 'request_id': str(uuid.uuid4())})
    assert applied.status_code == 201, applied.text[:600]
    publish(client, headers, applied.json())
    row = row_of(report(identity_setup, date(2026, 7, 15))['cap'], first)
    assert row['emergency'] == overtime_of(identity_setup, first, JUNE[1:2], emergency=True) > 0
    assert row['used'] == overtime_of(identity_setup, first, JUNE)
    assert row['absolute_total'] == row['used'] + row['planned'] + row['emergency']


def test_unknown_history_is_flagged_not_zeroed(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup, before=lambda c, h, _, d: put_baseline(c, h, d, '2025-12-31', 0))
    rep = report(identity_setup, date(2026, 7, 15))
    assert rep['known_from'] == '2026-06-01'
    assert row_of(rep['cap'], first)['history_complete'] is False and row_of(rep['cap'], first)['used'] > 0
    assert row_of(rep['cap'], second)['history_complete'] is True


def test_monthly_comparison_and_year_average(identity_setup):
    client, headers, first, second, _ = published_june(identity_setup)
    rep = report(identity_setup, date(2026, 7, 15))
    m = row_of(rep['monthly'], first)
    assert m['days'] == 3 and m['overtime'] == overtime_of(identity_setup, first, JUNE) and m['work'] > m['overtime']
    assert m['year_average'] is None and m['name'] == FIRST
    assert all(r['driver_id'] != second for r in rep['monthly'])
    july = row_of(report(identity_setup, date(2026, 8, 15), month=date(2026, 7, 1))['cap'], first)
    assert july['used'] == overtime_of(identity_setup, first, JUNE)
    assert report(identity_setup, date(2026, 8, 15), month=date(2026, 7, 1))['monthly'] == []


def test_year_average_skips_months_without_publication(identity_setup):
    may = '2026-05-04'
    client, headers, first, second, _ = published_june(identity_setup, days=(may, *JUNE))
    rep = report(identity_setup, date(2026, 7, 15))
    m = row_of(rep['monthly'], first)
    assert m['days'] == 3 and m['year_average'] == overtime_of(identity_setup, first, (may,)) > 0
    assert rep['known_from'] == may and rep['published_days'] == 3
    assert row_of(report(identity_setup, date(2026, 5, 20))['monthly'], first)['year_average'] is None


def test_inactive_driver_with_overtime_still_listed(identity_setup):
    from app.domain.workforce.models import WorkforceDriver
    client, headers, first, second, _ = published_june(identity_setup)
    with identity_setup['owner_factory']() as db:
        db.query(WorkforceDriver).filter(WorkforceDriver.id.in_([first, second])).update({'is_active': False}, synchronize_session=False)
        db.commit()
    rep = report(identity_setup, date(2026, 7, 15))
    assert row_of(rep['cap'], first)['active'] is False
    assert all(r['driver_id'] != second for r in rep['cap'])


def test_zero_limit_reports_reached_without_error(identity_setup):
    from app.domain.workrules.models import CompanyWorkRules
    client, headers, first, second, _ = published_june(identity_setup)
    with identity_setup['owner_factory']() as db:
        tenant = identity_setup['first'].tenant_id
        row = db.query(CompanyWorkRules).filter_by(tenant_id=tenant).first()
        if row is None:
            row = CompanyWorkRules(tenant_id=tenant, version=1, warning_rules=[])
            db.add(row)
        row.overrides = {'overtime_year': 0}
        db.commit()
    rep = report(identity_setup, date(2026, 7, 15))
    busy, idle = row_of(rep['cap'], first), row_of(rep['cap'], second)
    assert rep['limit'] == 0 and busy['used'] > 0
    assert busy['status'] == 'reached' and busy['remaining'] == 0 and busy['projection_month'] is None
    assert idle['used'] == 0 and idle['status'] == 'within'
    assert rep['cap'][0]['driver_id'] == first
    from tests.integration.test_office_permissions import person
    mgmt = person(identity_setup, 'management@example.org', 'management')[0]
    assert identity_setup['client'].get('/api/v1/reports/monthly?month=2026-06', headers=mgmt).status_code == 200
    assert identity_setup['client'].get('/api/v1/reports/export?month=2026-06&format=pdf&lang=el', headers=mgmt).status_code == 200
