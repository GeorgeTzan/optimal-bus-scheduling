import uuid
from datetime import timedelta
from tests.integration.test_identity import identity_setup, accept
from tests.integration.test_operational_snapshots import setup_operator, template_payload
from tests.integration.test_schedule_changes import APPLY, PREVIEW
from tests.integration.test_work_rules_api import route_of

MONDAY, TUESDAY = '2026-06-01', '2026-06-02'
REVISIONS = '/api/v1/scheduling/revisions'
BREACH = (('a', 'b', {'trip_code': 'LATE', 'departure_time': '21:10', 'arrival_time': '22:10', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
          ('a', 'b', {'trip_code': 'EARLY', 'departure_time': '06:00', 'arrival_time': '07:00', 'arrival_day_offset': 0, 'operating_weekdays': [1]}))
EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
OVERTIME_DAY = (('a', 'b', {'trip_code': 'T1', 'departure_time': '07:00', 'arrival_time': '11:00', 'arrival_day_offset': 0, 'operating_weekdays': EVERY_DAY}),
                ('b', 'a', {'trip_code': 'T2', 'departure_time': '11:45', 'arrival_time': '16:00', 'arrival_day_offset': 0, 'operating_weekdays': EVERY_DAY}))
TWO_CREWS = (('a', 'b', {'trip_code': 'T1', 'departure_time': '05:00', 'arrival_time': '09:00', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
             ('b', 'a', {'trip_code': 'T2', 'departure_time': '09:45', 'arrival_time': '13:45', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
             ('a', 'b', {'trip_code': 'T3', 'departure_time': '14:30', 'arrival_time': '15:20', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
             ('a', 'b', {'trip_code': 'T4', 'departure_time': '06:00', 'arrival_time': '10:00', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
             ('b', 'a', {'trip_code': 'T5', 'departure_time': '10:45', 'arrival_time': '14:45', 'arrival_day_offset': 0, 'operating_weekdays': [0]}))
LONG_DAY = (('a', 'b', {'trip_code': 'T1', 'departure_time': '05:00', 'arrival_time': '09:00', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
            ('b', 'a', {'trip_code': 'T2', 'departure_time': '09:45', 'arrival_time': '13:45', 'arrival_day_offset': 0, 'operating_weekdays': [0]}),
            ('a', 'b', {'trip_code': 'T3', 'departure_time': '14:30', 'arrival_time': '15:20', 'arrival_day_offset': 0, 'operating_weekdays': [0]}))


def fleet(setup, templates, days=(MONDAY, TUESDAY)):
    from tests.helpers.working_time import give_working_time
    client, headers, create, a, b, driver, vehicle = setup_operator(setup)
    stations = {'a': a, 'b': b}
    for first, second, minutes in ((a, b, 30), (b, a, 35)):
        create('transfers', {'origin_station_id': first['id'], 'destination_station_id': second['id'], 'minutes': minutes})
    second_driver = create('drivers', {'code': 'SECOND', 'first_name': 'Maria', 'last_name': 'Kosta', 'home_station_id': a['id']})
    second_vehicle = create('vehicles', {'code': 'SECOND', 'registration_plate': 'ZZZ-1234', 'bus_type': '02', 'home_station_id': a['id']})
    for day in days:
        for person, bus in ((driver, vehicle), (second_driver, second_vehicle)):
            create('pairings', {'driver_id': person['id'], 'vehicle_id': bus['id'], 'home_station_id': a['id'], 'service_date': day, 'confirm': True,
                                'driver_version': person['version'], 'vehicle_version': bus['version'], 'home_station_version': a['version']})
    give_working_time(client, headers)
    made = [create('timetables', template_payload(stations[o], stations[d], **fields)) for o, d, fields in templates]
    return client, headers, made, vehicle


def draft(client, headers, day):
    response = client.post(REVISIONS, headers=headers, json={'service_date': day})
    assert response.status_code == 201, response.text[:400]
    return response.json()


def crew(revision, name):
    return next(r['resource_id'] for r in revision['source_resources'] if r['driver_name'] == name)


FIRST, SECOND = 'Νίκος Δήμου', 'Maria Kosta'


def trip(revision, code):
    return next(t['id'] for t in revision['source_trips'] if t['trip_code'] == code)


def patches(revision, plan):
    return [{'trip_id': trip(revision, code), 'new_resource_id': crew(revision, name)} for code, name in plan.items()]


def assign(client, headers, revision, plan):
    response = client.post(f"{REVISIONS}/{revision['revision_id']}/patches", headers=headers,
                           json={'version': revision['version'], 'patches': patches(revision, plan)})
    assert response.status_code == 200, response.text[:400]
    return response.json()


def act(client, headers, revision, action):
    return client.post(f"{REVISIONS}/{revision['revision_id']}/{action}", headers=headers, json={'version': revision['version']})


def publish(client, headers, revision):
    for action in ('request-approval', 'approve', 'publish'):
        response = act(client, headers, revision, action)
        assert response.status_code == 200, response.text[:600]
        revision = response.json()
    return revision


def found(verification, rule_id):
    return [v for v in verification['violations'] if v['rule_id'] == rule_id]


def published_monday(setup, templates, plan):
    client, headers, made, vehicle = fleet(setup, templates)
    monday = publish(client, headers, assign(client, headers, draft(client, headers, MONDAY), plan))
    return client, headers, made, vehicle, monday


def change_request(client, headers, revision, plan, **extra):
    from tests.integration.test_daily_operations import board
    publication = board(client, headers, service_date=revision['problem']['service_date'])['publication']['publication_id']
    items = patches(revision, plan)
    return {'publication_id': publication, 'version': revision['version'], 'reason': 'Driver called in sick this morning.',
            'reviewed_not_started': [item['trip_id'] for item in items], 'patches': items, **extra}


def dispatcher(setup, client):
    from app.domain.identity.service import issue_invitation
    with setup['owner_factory']() as db:
        invite = issue_invitation(db, setup['first'].tenant_id, f'dispatcher-{uuid.uuid4().hex[:6]}@example.org', 'dispatcher')
        db.commit()
    return {'Authorization': 'Bearer ' + accept(client, invite).json()['access_token']}


def test_rest_breach_blocks_every_gate(identity_setup):
    from app.domain.jobs.models import Job
    from app.domain.jobs.worker import _candidate
    from app.domain.optimization.contracts import Assignment, SolverConfig
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules.loader import WorkContext
    client, headers, made, vehicle, monday = published_monday(identity_setup, BREACH, {'LATE': FIRST})
    tuesday = draft(client, headers, TUESDAY)
    preview = client.post(f"{REVISIONS}/{tuesday['revision_id']}/patches/preview", headers=headers,
                          json={'version': tuesday['version'], 'patches': patches(tuesday, {'EARLY': FIRST})})
    assert preview.status_code == 200, preview.text[:400]
    [rest] = found(preview.json()['verification'], 'WR_DAILY_REST')
    assert rest['severity'] == 'ERROR' and not preview.json()['verification']['valid']
    assert rest['hint']['rest_until'].endswith('+00:00') and rest['finding_key']
    queued = client.post('/optimization/runs', headers=headers, json={'snapshot_id': tuesday['revision_id'], 'config': {'iterations': 1, 'time_limit_seconds': 10}})
    assert queued.status_code == 202, queued.text[:400]
    with identity_setup['owner_factory']() as db:
        work = WorkContext.from_dict(db.query(Job).filter_by(job_id=queued.json()['run_id']).one().config['work_context'])
    problem = decode_problem(tuesday['problem'])
    early = next(t for t in problem.trips if t.id == trip(tuesday, 'EARLY'))
    candidate = _candidate(problem, [Assignment(crew(tuesday, FIRST), early.id, early.start_minutes, early.end_minutes, early.start_station, early.end_station)],
                           SolverConfig(seed=1, time_limit_seconds=10), 1, work=work)
    assert candidate['verification']['valid'] is False and found(candidate['verification'], 'WR_DAILY_REST')
    tuesday = assign(client, headers, tuesday, {'EARLY': FIRST})
    assert found(tuesday['verification'], 'WR_DAILY_REST')[0]['severity'] == 'ERROR'
    for action in ('request-approval', 'approve', 'publish'):
        response = act(client, headers, tuesday, action)
        assert response.status_code == 422, (action, response.text[:400])
        detail = response.json()['detail']
        assert detail['code'] == 'verification_failed' and found(detail['verification'], 'WR_DAILY_REST')


def test_schedule_change_preview_reports_rest_breach(identity_setup):
    client, headers, made, vehicle, monday = published_monday(identity_setup, BREACH, {'LATE': FIRST})
    tuesday = publish(client, headers, assign(client, headers, draft(client, headers, TUESDAY), {'EARLY': SECOND}))
    request = change_request(client, headers, tuesday, {'EARLY': FIRST})
    preview = client.post(PREVIEW, headers=headers, json=request)
    assert preview.status_code == 200, preview.text[:400]
    assert found(preview.json()['verification'], 'WR_DAILY_REST')[0]['severity'] == 'ERROR'
    applied = client.post(APPLY, headers=headers, json={**request, 'request_id': str(uuid.uuid4())})
    assert applied.status_code == 422 and applied.json()['detail']['code'] == 'verification_failed'


def test_emergency_change_allows_eleven_hour_duty(identity_setup, monkeypatch):
    from app.domain.identity.permissions import PERMISSIONS
    from app.domain.scheduling.change_models import ScheduleChange
    client, headers, made, vehicle, monday = published_monday(identity_setup, LONG_DAY, {'T1': FIRST, 'T2': FIRST, 'T3': SECOND})
    request = change_request(client, headers, monday, {'T3': FIRST})
    normal = client.post(PREVIEW, headers=headers, json=request).json()['verification']
    [daily] = found(normal, 'WR_DAILY_WORK')
    assert daily['severity'] == 'ERROR' and 600 < daily['measured'] <= 660
    urgent = client.post(PREVIEW, headers=headers, json={**request, 'emergency': True})
    assert urgent.status_code == 200 and not found(urgent.json()['verification'], 'WR_DAILY_WORK'), urgent.text[:600]
    monkeypatch.setitem(PERMISSIONS, 'dispatcher', PERMISSIONS['dispatcher'] - {'schedule.publish'})
    restricted = dispatcher(identity_setup, client)
    denied = client.post(PREVIEW, headers=restricted, json={**request, 'emergency': True})
    assert denied.status_code == 403 and denied.json()['detail']['code'] == 'emergency_not_allowed'
    assert client.post(APPLY, headers=restricted, json={**request, 'emergency': True, 'request_id': str(uuid.uuid4())}).status_code == 403
    applied = client.post(APPLY, headers=headers, json={**request, 'emergency': True, 'request_id': str(uuid.uuid4())})
    assert applied.status_code == 201, applied.text[:600]
    successor = applied.json()
    assert successor['verification']['valid'] and not found(successor['verification'], 'WR_DAILY_WORK')
    with identity_setup['owner_factory']() as db:
        assert db.query(ScheduleChange).filter_by(successor_revision_id=successor['revision_id']).one().emergency
    assert act(client, headers, successor, 'request-approval').status_code == 200


def test_override_endpoint(identity_setup):
    client, headers, made, vehicle, monday = published_monday(identity_setup, BREACH, {'LATE': FIRST})
    forbidden = client.put(f"/api/v1/work-rules/vehicles/{vehicle['id']}/forbidden-routes", headers=headers, json={'route_ids': [route_of(identity_setup, made[1])]})
    assert forbidden.status_code == 200, forbidden.text[:400]
    tuesday = assign(client, headers, draft(client, headers, TUESDAY), {'EARLY': FIRST})
    [legal] = found(tuesday['verification'], 'WR_DAILY_REST')
    [warning] = found(tuesday['verification'], 'WR_FORBIDDEN_VEHICLE_ROUTE')
    url = f"{REVISIONS}/{tuesday['revision_id']}/work-rule-overrides"
    rejected = client.post(url, headers=headers, json={'finding_key': legal['finding_key'], 'reason': 'Accepted by the depot.'})
    assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'legal_finding'
    unknown = client.post(url, headers=headers, json={'finding_key': 'WR_NOPE|1|2026-06-02||None', 'reason': 'Accepted.'})
    assert unknown.status_code == 404 and unknown.json()['detail']['code'] == 'finding_not_found'
    assert client.post(url, headers=dispatcher(identity_setup, client), json={'finding_key': warning['finding_key'], 'reason': 'Accepted.'}).status_code == 403
    assert client.post(url, headers=headers, json={'finding_key': warning['finding_key'], 'reason': ''}).status_code == 422
    body = {'finding_key': warning['finding_key'], 'reason': 'Vehicle cleared for this route today.'}
    saved = client.post(url, headers=headers, json=body)
    assert saved.status_code == 200, saved.text[:400]
    assert saved.json()['finding_key'] == warning['finding_key'] and saved.json()['reason'] == body['reason']
    assert client.post(url, headers=headers, json=body).json() == saved.json()
    current = client.get(f"{REVISIONS}/{tuesday['revision_id']}", headers=headers).json()
    assert not found(current['verification'], 'WR_FORBIDDEN_VEHICLE_ROUTE') and found(current['verification'], 'WR_DAILY_REST')
    from app.domain.office.models import OfficeAudit
    with identity_setup['owner_factory']() as db:
        assert db.query(OfficeAudit).filter_by(tenant_id=identity_setup['first'].tenant_id, entity='work_rule_override').count() == 1


def context_for(setup, revision, day=None):
    from dataclasses import replace
    from datetime import date
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules.loader import load_work_context
    problem = decode_problem(revision['problem'])
    if day:
        problem = replace(problem, service_date=date.fromisoformat(day))
    with setup['owner_factory']() as db:
        return load_work_context(db, setup['first'].tenant_id, problem, None if day else revision['revision_id'])


def driver_of(revision, name):
    return next(r['driver_id'] for r in revision['source_resources'] if r['driver_name'] == name)


def test_emergency_applies_only_to_touched_drivers(identity_setup):
    client, headers, made, vehicle, monday = published_monday(identity_setup, TWO_CREWS, {'T1': FIRST, 'T2': FIRST, 'T4': SECOND, 'T5': SECOND})
    request = {**change_request(client, headers, monday, {'T3': FIRST}), 'emergency': True}
    applied = client.post(APPLY, headers=headers, json={**request, 'request_id': str(uuid.uuid4())})
    assert applied.status_code == 201, applied.text[:600]
    publish(client, headers, applied.json())
    ctx = context_for(identity_setup, monday, TUESDAY)
    first, second = str(driver_of(monday, FIRST)), str(driver_of(monday, SECOND))
    assert [d.emergency for d in ctx.timelines[first].duties] == [True]
    assert [d.emergency for d in ctx.timelines[second].duties] == [False]
    week = lambda driver: client.get(f"/api/v1/work-rules/drivers/{driver}/week", headers=headers, params={'date': MONDAY}).json()
    assert week(first)['overtime_year_minutes'] == 0 and week(second)['overtime_year_minutes'] > 0


def test_recorded_delay_shifts_urgent_change_draft(identity_setup):
    from tests.integration.test_work_rules_loader import report_delay
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules.draft import draft_duties
    from app.domain.optimization.contracts import Assignment
    client, headers, made, vehicle, monday = published_monday(identity_setup, LONG_DAY, {'T1': FIRST, 'T2': FIRST})
    request = change_request(client, headers, monday, {'T3': SECOND})
    assert not found(client.post(PREVIEW, headers=headers, json=request).json()['verification'], 'WR_CONTINUOUS_DRIVING')
    report_delay(client, headers, trip(monday, 'T1'), 40)
    ctx = context_for(identity_setup, monday)
    assert ctx.delays == {trip(monday, 'T1'): 40}
    problem = decode_problem(monday['problem'])
    rows = [Assignment(crew(monday, FIRST), t.id, t.start_minutes, t.end_minutes, t.start_station, t.end_station)
            for t in problem.trips if t.id in (trip(monday, 'T1'), trip(monday, 'T2'))]
    first_trip = draft_duties(ctx, problem, rows)[str(driver_of(monday, FIRST))].trips[0]
    planned = next(t for t in problem.trips if t.id == trip(monday, 'T1'))
    assert first_trip.end - first_trip.start == timedelta(minutes=planned.end_minutes - planned.start_minutes + 40)
    preview = client.post(PREVIEW, headers=headers, json=request).json()['verification']
    assert found(preview, 'WR_CONTINUOUS_DRIVING')[0]['severity'] == 'ERROR' and not preview['valid']


def test_february_overtime_counts_in_november(identity_setup):
    february, november = '2026-02-10', '2026-11-10'
    client, headers, made, vehicle = fleet(identity_setup, OVERTIME_DAY, days=(february, november))
    winter = publish(client, headers, assign(client, headers, draft(client, headers, february), {'T1': FIRST, 'T2': FIRST}))
    autumn = draft(client, headers, november)
    ctx = context_for(identity_setup, autumn)
    timeline = ctx.timelines[str(driver_of(autumn, FIRST))]
    assert timeline.duties == () and timeline.prior_year == 2026 and timeline.prior_overtime > 0
    rules = client.get('/api/v1/work-rules', headers=headers).json()
    saved = client.put('/api/v1/work-rules', headers=headers, json={'expected_version': rules['company_version'],
                                                                   'overrides': {'overtime_year': timeline.prior_overtime + 10}})
    assert saved.status_code == 200, saved.text[:400]
    preview = client.post(f"{REVISIONS}/{autumn['revision_id']}/patches/preview", headers=headers,
                          json={'version': autumn['version'], 'patches': patches(autumn, {'T1': FIRST, 'T2': FIRST})})
    [overtime] = found(preview.json()['verification'], 'WR_OVERTIME_YEAR')
    assert overtime['severity'] == 'ERROR' and overtime['measured'] == 2 * timeline.prior_overtime


def test_operational_problem_carries_route_facts_and_worker_budgets(identity_setup):
    from app.domain.jobs.models import Job
    from app.domain.optimization.cv_bounded import CVBoundedV1
    from app.domain.optimization.contracts import SolverConfig
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules.loader import WorkContext, attach_work_context
    client, headers, made, vehicle, monday = published_monday(identity_setup, BREACH, {'LATE': FIRST})
    tuesday = draft(client, headers, TUESDAY)
    problem = decode_problem(tuesday['problem'])
    early = next(t for t in problem.trips if t.id == trip(tuesday, 'EARLY'))
    assert early.route_id == route_of(identity_setup, made[1]) and early.origin_is_depot and not early.destination_is_depot
    assert not early.urban and early.long_route is True
    queued = client.post('/optimization/runs', headers=headers, json={'snapshot_id': tuesday['revision_id'], 'config': {'iterations': 1, 'time_limit_seconds': 10}})
    assert queued.status_code == 202, queued.text[:400]
    with identity_setup['owner_factory']() as db:
        work = WorkContext.from_dict(db.query(Job).filter_by(job_id=queued.json()['run_id']).one().config['work_context'])
    attached = attach_work_context(problem, work)
    first = next(r.driver_id for r in problem.resources if r.resource_id == crew(tuesday, FIRST))
    budget = next(b for b in attached.driver_budgets if b['driver_id'] == first)
    assert budget['earliest_start_minutes'] > early.start_minutes
    result = CVBoundedV1().solve(attached, SolverConfig(seed=1, time_limit_seconds=10, iterations=1))
    assert all(a.resource_id != crew(tuesday, FIRST) for a in result.assignments if a.trip_id == early.id)
