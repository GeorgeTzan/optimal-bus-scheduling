import uuid
from datetime import date, datetime, timezone
from sqlalchemy import text
from tests.integration.test_identity import identity_setup
from tests.integration.test_schedule_changes import APPLY
from tests.integration.test_work_rules_gates import FIRST, MONDAY, OVERTIME_DAY, assign, change_request, draft, fleet, publish, trip

JUNE = date(2026, 6, 1)


def published_day(setup, organization='first'):
    client, headers, made, vehicle = fleet({**setup, 'first': setup[organization]}, OVERTIME_DAY, days=(MONDAY,))
    return client, headers, vehicle, publish(client, headers, assign(client, headers, draft(client, headers, MONDAY), {'T1': FIRST}))


def report(setup, organization='first'):
    from app.domain.reports.coverage import coverage_report
    with setup['owner_factory']() as db:
        return coverage_report(db, setup[organization].tenant_id, JUNE)


def days_of(setup, line):
    from app.domain.reports.coverage import line_days
    with setup['owner_factory']() as db:
        return line_days(db, setup['first'].tenant_id, JUNE, line)


def codes(setup):
    from app.domain.timetables.models import Station
    with setup['owner_factory']() as db:
        return [code for (code,) in db.query(Station.code).filter_by(tenant_id=setup['first'].tenant_id).order_by(Station.id)]


def test_counts_per_line_both_directions_one_line(identity_setup):
    published_day(identity_setup)
    a, b = codes(identity_setup)
    [row] = report(identity_setup)
    assert (row['scheduled'], row['covered'], row['uncovered'], row['cancelled']) == (2, 1, 1, 0)
    assert row['rate'] == 0.5 and row['reasons'] == {'no_driver': 1}
    assert row['stations'] == sorted([a, b]) and row['line'] == '-'.join(sorted([a, b]))
    assert sorted(names[0] for names in row['names']) == ['Αφετηρία', 'Προορισμός']
    assert report(identity_setup) == report(identity_setup)


def test_latest_publication_wins_after_change(identity_setup):
    client, headers, vehicle, published = published_day(identity_setup)
    a, b = codes(identity_setup)
    cancelled = trip(published, 'T2')
    request = {**change_request(client, headers, published, {}), 'reviewed_not_started': [cancelled],
               'patches': [{'trip_id': cancelled, 'operation': 'cancel', 'reason': 'Road closed'}], 'request_id': str(uuid.uuid4())}
    applied = client.post(APPLY, headers=headers, json=request)
    assert applied.status_code == 201, applied.text[:600]
    publish(client, headers, applied.json())
    [row] = report(identity_setup)
    assert (row['scheduled'], row['covered'], row['uncovered'], row['cancelled']) == (2, 1, 0, 1)
    assert row['rate'] == 1.0 and row['reasons'] == {}
    [day] = days_of(identity_setup, row['line'])
    assert day['uncovered'] == [] and day['cancelled'] == [{'trip_code': 'T2', 'reason': 'Road closed'}]
    assert day['direction'] == f'{b}→{a}' and day['reason'] is None and day['context'] is None


def test_old_days_show_unrecorded_with_context(identity_setup):
    from db.models import User
    from app.domain.fleet.models import VehicleAvailability
    from app.domain.workforce.models import DriverAvailability, WorkforceDriver
    client, headers, vehicle, published = published_day(identity_setup)
    tenant = identity_setup['first'].tenant_id
    start, end = datetime(2026, 5, 31, 12, tzinfo=timezone.utc), datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    with identity_setup['owner_factory']() as db:
        db.execute(text('UPDATE domain_publications SET uncovered_reason=NULL WHERE tenant_id=:tenant'), {'tenant': tenant})
        user = db.query(User.id).filter_by(ktel_id=tenant).first()[0]
        driver = db.query(WorkforceDriver.id).filter_by(tenant_id=tenant).first()[0]
        db.add(DriverAvailability(tenant_id=tenant, driver_id=driver, kind='unavailable', category='sick', start_utc=start, end_utc=end, recorded_by=user))
        db.add(DriverAvailability(tenant_id=tenant, driver_id=driver, kind='unavailable', category='sick', status='retired', start_utc=start, end_utc=end, recorded_by=user))
        db.add(DriverAvailability(tenant_id=tenant, driver_id=driver, kind='unavailable', category='sick', start_utc=datetime(2026, 6, 10, tzinfo=timezone.utc), recorded_by=user))
        db.add(VehicleAvailability(tenant_id=tenant, vehicle_id=vehicle['id'], kind='out_of_service', start_utc=start, recorded_by=user))
        db.add(VehicleAvailability(tenant_id=tenant, vehicle_id=vehicle['id'], kind='out_of_service', status='cancelled', start_utc=start, recorded_by=user, cancelled_by=user))
        db.add(VehicleAvailability(tenant_id=tenant, vehicle_id=vehicle['id'], kind='out_of_service', status='released', start_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
                                   released_at=datetime(2026, 5, 20, tzinfo=timezone.utc), released_by=user, recorded_by=user))
        db.commit()
    [row] = report(identity_setup)
    assert row['reasons'] == {'unrecorded': 1}
    [day] = days_of(identity_setup, row['line'])
    assert day['reason'] is None and day['note'] is None and day['context'] == {'drivers_unavailable': 1, 'vehicles_out': 1}


def test_drilldown_splits_direction(identity_setup):
    published_day(identity_setup)
    a, b = codes(identity_setup)
    [row] = report(identity_setup)
    days = days_of(identity_setup, row['line'])
    assert [(d['date'], d['direction'], d['uncovered']) for d in days] == [('2026-06-01', f'{b}→{a}', ['T2'])]
    assert days[0]['reason'] == 'no_driver' and days[0]['context'] is None and days[0]['cancelled'] == [] and days[0]['published_by']
    assert days_of(identity_setup, 'none') == []


def test_other_tenant_data_never_included(identity_setup):
    published_day(identity_setup)
    before = report(identity_setup)
    days = days_of(identity_setup, before[0]['line'])
    assert report(identity_setup, 'second') == []
    published_day(identity_setup, 'second')
    assert report(identity_setup) == before
    [other] = report(identity_setup, 'second')
    assert other['scheduled'] == 2 and other['uncovered'] == 1
    assert days_of(identity_setup, before[0]['line']) == days and len(days) == 1


def test_route_with_unknown_station_is_skipped():
    from app.domain.reports.coverage import _route_ends

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_):
            return self

        def all(self):
            return self.rows

    class Db:
        def __init__(self):
            self.answers = [[(1, 10, 20), (2, 10, 99)], [(10, 'A'), (20, 'B')]]

        def query(self, *_):
            return Rows(self.answers.pop(0))

    assert _route_ends(Db(), 1, {1, 2}) == {1: ('A', 'B')}
