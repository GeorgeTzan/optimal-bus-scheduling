import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from tests.integration.test_identity import identity_setup
from tests.integration.test_daily_operations import board
from tests.integration.test_office_impacts import change, driver_of
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
from tests.integration.test_schedule_changes import APPLY

RULES = '/api/v1/work-rules'


def problem_for(revision, day):
    from app.domain.scheduling.snapshots import decode_problem
    return replace(decode_problem(revision['problem']), service_date=date.fromisoformat(day))


def context(setup, revision, day='2026-06-02', revision_id=None, tenant_id=None):
    from app.domain.workrules.loader import load_work_context
    with setup['owner_factory']() as db:
        return load_work_context(db, tenant_id or setup['first'].tenant_id, problem_for(revision, day), revision_id)


def own_trips(revision, crew):
    return sorted(item['trip_id'] for item in revision['assignments'] if item['resource_id'] == crew['resource_id'])


def duty_end(ctx, duty):
    from app.domain.workrules.facts import duty_facts
    timeline = ctx.timelines[duty.driver_id]
    return duty_facts(duty, timeline.profile, ctx.policy, ctx.transfer_minutes).end


def test_published_previous_day_in_timeline(identity_setup):
    from app.domain.workrules.loader import WorkContext
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    ctx = context(identity_setup, revision)
    driver = str(driver_of(revision, first))
    assert ctx.tz == 'Europe/Athens' and ctx.service_date == date(2026, 6, 2)
    assert ctx.day_origin_utc == datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc)
    duties = ctx.timelines[driver].duties
    assert [(d.service_date, d.provenance, d.emergency) for d in duties] == [(date(2026, 6, 1), 'published', False)]
    trips = duties[0].trips
    assert sorted(t.trip_id for t in trips) == own_trips(revision, first)
    assert trips[0].start == datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc) and trips[0].origin_is_depot
    assert not trips[0].destination_is_depot and trips[0].route_id and not trips[0].urban and trips[0].long_route
    assert ctx.timelines[str(driver_of(revision, other))].duties == ()
    assert ctx.timelines[driver].profile.home_station == trips[0].origin
    assert ctx.transfer_minutes(trips[0].destination, trips[1].origin) is not None
    assert WorkContext.from_dict(ctx.to_dict()) == ctx
    same_day = context(identity_setup, revision, '2026-06-01')
    assert same_day.timelines[driver].duties == ()


def test_cancelled_trip_excluded(identity_setup):
    from tests.integration.test_driver_acks import republish
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    trips = own_trips(revision, first)
    successor = republish(client, headers, revision, [{'trip_id': trips[0], 'operation': 'cancel', 'reason': 'Service withdrawn'}])
    ctx = context(identity_setup, successor)
    duties = ctx.timelines[str(driver_of(revision, first))].duties
    assert [t.trip_id for t in duties[0].trips] == [trips[1]]


def report_delay(client, headers, trip_id, minutes):
    data = board(client, headers)
    item = next(row for row in data['items'] if row['trip_id'] == trip_id)
    saved = client.post('/api/v1/operations/reports', headers=headers, json={
        'publication_id': data['publication']['publication_id'], 'trip_id': trip_id, 'expected_version': item['version'],
        'request_id': str(uuid.uuid4()), 'kind': 'delay', 'description': 'Roadworks.', 'delay_minutes': minutes})
    assert saved.status_code == 201, saved.text


def test_delay_shifts_end(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    driver = str(driver_of(revision, first))
    before = context(identity_setup, revision)
    duty = before.timelines[driver].duties[0]
    report_delay(client, headers, duty.trips[-1].trip_id, 40)
    after = context(identity_setup, revision)
    delayed = after.timelines[driver].duties[0]
    assert duty_end(after, delayed) - duty_end(before, duty) == timedelta(minutes=40)


def test_delay_survives_republish(identity_setup):
    from tests.integration.test_driver_acks import republish
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    driver = str(driver_of(revision, first))
    duty = context(identity_setup, revision).timelines[driver].duties[0]
    early, late = duty.trips
    report_delay(client, headers, late.trip_id, 40)
    successor = republish(client, headers, revision, [{'trip_id': early.trip_id, 'new_resource_id': other['resource_id']}])
    ctx = context(identity_setup, successor)
    moved = ctx.timelines[driver].duties[0]
    assert [t.trip_id for t in moved.trips] == [late.trip_id]
    assert moved.trips[0].start == late.start and moved.trips[0].end == late.end + timedelta(minutes=40)


def test_middle_delay_cascades(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    driver = str(driver_of(revision, first))
    early, late = context(identity_setup, revision).timelines[driver].duties[0].trips
    report_delay(client, headers, early.trip_id, 90)
    first_trip, second_trip = context(identity_setup, revision).timelines[driver].duties[0].trips
    assert first_trip.start == early.start and first_trip.end == early.end + timedelta(minutes=90)
    assert second_trip.start == first_trip.end and second_trip.end - second_trip.start == late.end - late.start
    report_delay(client, headers, early.trip_id, 20)
    first_trip, second_trip = context(identity_setup, revision).timelines[driver].duties[0].trips
    assert first_trip.end == early.end + timedelta(minutes=20) and (second_trip.start, second_trip.end) == (late.start, late.end)


def test_ancestor_override_applies(identity_setup):
    from app.domain.workrules.models import WorkRuleOverride
    from db.models import User
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    trips = own_trips(revision, first)
    body, _ = change(client, headers, revision, [])
    body['patches'] = [{'trip_id': trips[0], 'operation': 'unassign'}]
    body['reviewed_not_started'] = [trips[0]]
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:300]
    successor = created.json()
    tenant = identity_setup['first'].tenant_id
    with identity_setup['owner_factory']() as db:
        actor = db.query(User.id).filter_by(ktel_id=tenant).first()[0]
        db.add(WorkRuleOverride(tenant_id=tenant, revision_id=revision['revision_id'], finding_key='WR_SPLIT_SHIFT|11|2026-06-02', reason='Agreed', actor_id=actor))
        db.add(WorkRuleOverride(tenant_id=tenant, revision_id=successor['revision_id'], finding_key='WR_MUST_RETURN_BASE|11|2026-06-02', reason='Agreed', actor_id=actor))
        db.commit()
    ctx = context(identity_setup, successor, revision_id=successor['revision_id'])
    assert ctx.overrides == frozenset({'WR_SPLIT_SHIFT|11|2026-06-02', 'WR_MUST_RETURN_BASE|11|2026-06-02'})
    assert context(identity_setup, revision, revision_id=revision['revision_id']).overrides == frozenset({'WR_SPLIT_SHIFT|11|2026-06-02'})
    assert context(identity_setup, revision).overrides == frozenset()


def test_other_tenant_publications_ignored(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    driver = str(driver_of(revision, first))
    assert context(identity_setup, revision).timelines[driver].duties
    foreign = context(identity_setup, revision, tenant_id=identity_setup['second'].tenant_id)
    assert all(timeline.duties == () for timeline in foreign.timelines.values())
    assert foreign.timelines[driver].baseline is None


def test_week_endpoint_totals(identity_setup):
    from tests.integration.test_work_rules_api import administrator
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    url = f"{RULES}/drivers/{driver_of(revision, first)}/week"
    body = client.get(url, headers=headers, params={'date': '2026-06-01'})
    assert body.status_code == 200, body.text
    assert body.json() == {'work_minutes': 200, 'weekly_max': 2700, 'overtime_year_minutes': 0, 'overtime_year_max': 7200,
                           'last_duty_end': '2026-06-01T08:10:00+00:00', 'last_weekly_rest': None}
    later = client.get(url, headers=headers, params={'date': '2026-06-08'}).json()
    assert later['work_minutes'] == 0 and later['last_duty_end'] == '2026-06-01T08:10:00+00:00'
    idle = client.get(f"{RULES}/drivers/{driver_of(revision, other)}/week", headers=headers, params={'date': '2026-06-01'}).json()
    assert idle['work_minutes'] == 0 and idle['last_duty_end'] is None
    foreign = administrator(identity_setup, 'second')
    assert client.get(url, headers=foreign, params={'date': '2026-06-01'}).status_code == 404
