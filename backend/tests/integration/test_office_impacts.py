"""An approved absence shows the work that needs repair, never changes history, and never blocks its own repair."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from tests.helpers.working_time import approve_leave
from tests.integration.test_daily_operations import board, report_payload
from tests.integration.test_identity import identity_setup
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
from tests.integration.test_schedule_changes import APPLY, PREVIEW, transition

IMPACTS = '/api/v1/office/impacts'
DAY = {'date_from': '2026-06-01', 'date_to': '2026-06-01'}


def driver_of(revision, resource):
    return int(next(item['driver_id'] for item in revision['problem']['resources'] if item['resource_id'] == resource['resource_id']))


def change(client, headers, revision, moves, **extra):
    publication = board(client, headers)['publication']['publication_id']
    trips = [item['trip_id'] for item in revision['assignments']]
    body = {'publication_id': publication, 'version': revision['version'], 'reason': 'Driver on leave; moving the work.', 'reviewed_not_started': [t for t, _ in moves],
            'patches': [{'trip_id': trip, 'new_resource_id': target} for trip, target in moves], **extra}
    return body, trips


def test_leave_on_a_published_day_shows_impacts_and_its_repair_is_creatable_and_publishable(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    approved = approve_leave(client, headers, driver_of(revision, first))
    assert approved['impact_count'] == 2
    impacts = client.get(IMPACTS, headers=headers, params=DAY).json()
    assert impacts['total'] == 2 and impacts['needs_review'] == 2
    assert {row['cause'] for row in impacts['items']} == {'driver'} and {row['status'] for row in impacts['items']} == {'published'}
    body, trips = change(client, headers, revision, [(item['trip_id'], other['resource_id']) for item in revision['assignments']])
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:600]
    successor = created.json()
    for action in ('request-approval', 'approve', 'publish'):
        response = transition(client, headers, successor, action)
        assert response.status_code == 200, response.text[:400]
        successor = response.json()
    assert client.get(IMPACTS, headers=headers, params=DAY).json()['total'] == 0
    with identity_setup['owner_factory']() as db:
        assert db.execute(text("SELECT count(*) FROM domain_revision_assignments WHERE revision_id=:r AND resource_id=:x"), {'r': revision['revision_id'], 'x': first['resource_id']}).scalar_one() == 2


def test_an_exemption_cannot_be_supplied_by_a_caller(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    body, _ = change(client, headers, revision, [(revision['assignments'][0]['trip_id'], 'UNASSIGNED')], availability_exempt_trip_ids=[revision['assignments'][0]['trip_id']])
    assert client.post(PREVIEW, headers=headers, json=body).status_code == 422


def test_an_already_operated_trip_stays_valid_in_a_repair_and_is_not_counted_as_needing_review(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    data = board(client, headers)
    departed = data['items'][0]['trip_id']
    assert client.post('/api/v1/operations/reports', headers=headers, json=report_payload(data, kind='departure', delay_minutes=None, description='Left on time.')).status_code == 201
    approve_leave(client, headers, driver_of(revision, first))
    impacts = client.get(IMPACTS, headers=headers, params=DAY).json()
    assert {row['trip_id']: row['operated'] for row in impacts['items']}[departed] is True and impacts['needs_review'] == 1
    remaining = next(item['trip_id'] for item in revision['assignments'] if item['trip_id'] != departed)
    body, _ = change(client, headers, revision, [(remaining, other['resource_id'])])
    created = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:600]


def test_a_replacement_crew_is_checked_against_the_underlying_driver_availability(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    approve_leave(client, headers, driver_of(revision, other))
    trip = revision['assignments'][1]['trip_id']
    publication = board(client, headers)['publication']['publication_id']
    body = {'publication_id': publication, 'version': revision['version'], 'reason': 'Replace the driver', 'reviewed_not_started': [trip], 'request_id': str(uuid.uuid4()),
            'patches': [{'trip_id': trip, 'operation': 'replace_driver', 'replacement_resource_id': other['resource_id'], 'driver_version': other['driver_version'],
                         'vehicle_version': first['vehicle_version'], 'confirm_replacement': True}]}
    refused = client.post(APPLY, headers=headers, json=body)
    assert refused.status_code == 422
    assert 'RULE_AVAILABILITY_TRIP' in {v['rule_id'] for v in refused.json()['detail']['verification']['violations']}


def test_cancelling_leave_rechecks_without_restoring_assignments(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    approved = approve_leave(client, headers, driver_of(revision, first))
    body, _ = change(client, headers, revision, [(item['trip_id'], other['resource_id']) for item in revision['assignments']])
    successor = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4())}).json()
    for action in ('request-approval', 'approve', 'publish'):
        successor = transition(client, headers, successor, action).json()
    cancelled = client.post(f"/api/v1/office/leave-requests/{approved['id']}/cancel", headers=headers, json={'request_id': str(uuid.uuid4()), 'expected_version': approved['version'], 'reason': 'Plans changed'})
    assert cancelled.status_code == 200 and cancelled.json()['impact_count'] == 0
    latest = client.get('/api/v1/scheduling/revisions/' + successor['revision_id'], headers=headers).json()
    assert {item['resource_id'] for item in latest['assignments']} == {other['resource_id']}


def test_a_stale_draft_cannot_be_patched_approved_or_published_and_says_how_to_repair(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': revision['assignments'][0]['trip_id'], 'new_resource_id': revision['source_resources'][0]['resource_id']}]}).json()
    requested = transition(client, headers, revision, 'request-approval').json()
    approve_leave(client, headers, driver['id'])
    for action in ('approve', 'publish'):
        refused = transition(client, headers, requested, action)
        assert refused.status_code == 409 and refused.json()['detail']['code'] == 'availability_changed'
    assert client.get('/api/v1/scheduling/revisions/' + requested['revision_id'], headers=headers).json()['source_review_required'] is True
    patch = client.post(f"/api/v1/scheduling/revisions/{requested['revision_id']}/patches", headers=headers, json={'version': requested['version'], 'patches': [
        {'trip_id': requested['assignments'][0]['trip_id'], 'new_resource_id': 'UNASSIGNED'}]})
    assert patch.status_code == 409 and patch.json()['detail']['code'] == 'availability_changed'


def test_a_locked_trip_is_released_only_for_an_availability_conflict_and_the_release_is_audited(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': revision['assignments'][0]['trip_id'], 'new_resource_id': revision['source_resources'][0]['resource_id'], 'is_locked': True}]}).json()
    for action in ('request-approval', 'approve', 'publish'):
        revision = transition(client, headers, revision, action).json()
    trip = revision['assignments'][0]['trip_id']
    publication = board(client, headers)['publication']['publication_id']
    body = lambda **patch: {'publication_id': publication, 'version': revision['version'], 'reason': 'Driver unavailable', 'reviewed_not_started': [trip],
                            'patches': [{'trip_id': trip, 'operation': 'unassign', **patch}]}
    assert client.post(PREVIEW, headers=headers, json=body()).json()['detail']['code'] == 'locked_trip'
    assert client.post(PREVIEW, headers=headers, json=body(unlock=True)).json()['detail']['code'] == 'unlock_without_conflict'
    approve_leave(client, headers, driver['id'])
    assert client.post(PREVIEW, headers=headers, json=body()).json()['detail']['code'] == 'locked_trip'
    created = client.post(APPLY, headers=headers, json={**body(unlock=True), 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:600]
    with identity_setup['owner_factory']() as db:
        assert db.execute(text("SELECT details->'unlocked_trips' FROM domain_scheduling_audit_logs WHERE action='create_published_successor'")).scalar_one() == [trip]
        assert db.execute(text("SELECT is_locked FROM domain_revision_assignments WHERE revision_id=:r"), {'r': created.json()['revision_id']}).scalar_one() is False


def test_impacts_are_bounded_read_only_and_show_no_private_fields(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    approve_leave(client, headers, driver_of(revision, first))
    assert client.get(IMPACTS, headers=headers, params={'date_from': '2026-06-01', 'date_to': '2026-07-15'}).status_code == 422
    counts = "SELECT (SELECT count(*) FROM domain_schedule_revisions),(SELECT count(*) FROM domain_revision_snapshots),(SELECT count(*) FROM domain_office_audit),(SELECT count(*) FROM domain_operational_trip_states)"
    with identity_setup['owner_factory']() as db:
        before = db.execute(text(counts)).one()
    rows = client.get(IMPACTS, headers=headers, params=DAY).json()['items']
    assert rows and not {'category', 'private_note', 'note'} & set().union(*(row.keys() for row in rows))
    with identity_setup['owner_factory']() as db:
        assert db.execute(text(counts)).one() == before


def test_an_office_write_and_a_publication_step_do_not_deadlock(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': revision['assignments'][0]['trip_id'], 'new_resource_id': revision['source_resources'][0]['resource_id']}]}).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        office = pool.submit(approve_leave, client, headers, driver['id'])
        step = pool.submit(transition, client, headers, revision, 'request-approval')
        assert office.result(timeout=60)['state'] == 'approved'
        assert step.result(timeout=60).status_code in (200, 409)


def published_with_overnight_trip(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    from tests.integration.test_operational_snapshots import template_payload
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    created = client.post('/api/v1/timetables', headers=headers, json=template_payload(template['origin'], template['destination'], trip_code='T002'))
    assert created.status_code == 201, created.text[:300]
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    resource = revision['source_resources'][0]['resource_id']
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': item['trip_id'], 'new_resource_id': resource} for item in revision['assignments']]}).json()
    for action in ('request-approval', 'approve', 'publish'):
        revision = transition(client, headers, revision, action).json()
    return client, headers, revision, driver


def test_an_overnight_trip_that_starts_before_an_absence_is_counted(identity_setup):
    client, headers, revision, driver = published_with_overnight_trip(identity_setup)
    approved = approve_leave(client, headers, driver['id'], '2026-06-02T00:00:00', '2026-06-03T00:00:00')
    assert approved['impact_count'] == 1
    rows = client.get(IMPACTS, headers=headers, params=DAY).json()['items']
    assert [row['trip_code'] for row in rows] == ['T002']


def test_unknown_working_time_is_an_impact_and_retiring_a_pattern_reports_it(identity_setup):
    from tests.integration.test_daily_operations import published_customer
    client, headers, revision = published_customer(identity_setup)
    assert client.get(IMPACTS, headers=headers, params=DAY).json()['total'] == 0
    for row in client.get('/api/v1/office/working-patterns', headers=headers).json()['items']:
        retired = client.post(f"/api/v1/office/working-patterns/{row['id']}/retire", headers=headers, json={'request_id': str(uuid.uuid4()), 'expected_version': row['version']})
        assert retired.status_code == 200 and 'impact_count' in retired.json()
    impacts = client.get(IMPACTS, headers=headers, params=DAY).json()
    assert impacts['needs_review'] == 1 and impacts['items'][0]['cause'] == 'unknown'


def test_a_lock_can_be_released_when_the_crews_working_time_became_unknown(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': revision['assignments'][0]['trip_id'], 'new_resource_id': revision['source_resources'][0]['resource_id'], 'is_locked': True}]}).json()
    for action in ('request-approval', 'approve', 'publish'):
        revision = transition(client, headers, revision, action).json()
    for row in client.get('/api/v1/office/working-patterns', headers=headers).json()['items']:
        assert client.post(f"/api/v1/office/working-patterns/{row['id']}/retire", headers=headers, json={'request_id': str(uuid.uuid4()), 'expected_version': row['version']}).status_code == 200
    trip = revision['assignments'][0]['trip_id']
    body = {'publication_id': board(client, headers)['publication']['publication_id'], 'version': revision['version'], 'reason': 'Working time withdrawn', 'reviewed_not_started': [trip],
            'patches': [{'trip_id': trip, 'operation': 'unassign', 'unlock': True}]}
    assert client.post(PREVIEW, headers=headers, json=body).status_code == 200


def test_a_solver_run_is_refused_for_a_draft_whose_availability_changed(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    approve_leave(client, headers, driver['id'])
    refused = client.post('/optimization/runs', headers=headers, json={'snapshot_id': revision['revision_id']})
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'availability_changed'


def test_two_absent_drivers_are_repaired_in_one_reviewed_change(identity_setup):
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup, overlap=True)
    by_crew = {item['resource_id']: item['trip_id'] for item in revision['assignments']}
    approve_leave(client, headers, driver_of(revision, first))
    approve_leave(client, headers, driver_of(revision, other))
    assert client.get(IMPACTS, headers=headers, params=DAY).json()['needs_review'] == 2
    one_only, _ = change(client, headers, revision, [(by_crew[first['resource_id']], 'UNASSIGNED')])
    refused = client.post(APPLY, headers=headers, json={**one_only, 'request_id': str(uuid.uuid4())})
    assert refused.status_code == 422 and 'RULE_AVAILABILITY_TRIP' in {v['rule_id'] for v in refused.json()['detail']['verification']['violations']}
    both, _ = change(client, headers, revision, [(trip, 'UNASSIGNED') for trip in by_crew.values()])
    created = client.post(APPLY, headers=headers, json={**both, 'request_id': str(uuid.uuid4())})
    assert created.status_code == 201, created.text[:500]
    successor = created.json()
    for action in ('request-approval', 'approve', 'publish'):
        response = transition(client, headers, successor, action)
        assert response.status_code == 200, response.text[:300]
        successor = response.json()
    assert client.get(IMPACTS, headers=headers, params=DAY).json()['total'] == 0


def test_a_chained_trip_is_repaired_together_with_its_partner(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    from tests.integration.test_connections import following_service, link_request
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client, headers, first)
    assert client.post('/api/v1/connections', headers=headers, json=link_request(first, second)).status_code == 201
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'}).json()
    ids = {row['trip_code']: row['id'] for row in revision['source_trips']}
    resource = revision['source_resources'][0]['resource_id']
    revision = client.post(f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches", headers=headers, json={'version': revision['version'], 'patches': [
        {'trip_id': trip, 'new_resource_id': resource} for trip in ids.values()]}).json()
    for action in ('request-approval', 'approve', 'publish'):
        revision = transition(client, headers, revision, action).json()
    approve_leave(client, headers, driver['id'], '2026-06-01T09:30:00', '2026-06-01T12:00:00')
    rows = client.get(IMPACTS, headers=headers, params=DAY).json()['items']
    assert [row['trip_code'] for row in rows] == ['T002']
    body = {'publication_id': board(client, headers)['publication']['publication_id'], 'version': revision['version'], 'reason': 'Return leg is on leave.'}
    alone = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4()), 'reviewed_not_started': [ids['T002']], 'patches': [{'trip_id': ids['T002'], 'operation': 'unassign'}]})
    assert alone.status_code == 422 and 'RULE_MANDATORY_CHAIN' in {v['rule_id'] for v in alone.json()['detail']['verification']['violations']}
    both = client.post(APPLY, headers=headers, json={**body, 'request_id': str(uuid.uuid4()), 'reviewed_not_started': list(ids.values()),
        'patches': [{'trip_id': trip, 'operation': 'cancel', 'reason': 'Return leg is on leave.'} for trip in ids.values()]})
    assert both.status_code == 201, both.text[:500]


def test_saving_a_working_pattern_reports_the_trips_it_puts_at_risk(identity_setup):
    from tests.integration.test_daily_operations import published_customer
    client, headers, revision = published_customer(identity_setup)
    existing = client.get('/api/v1/office/working-patterns', headers=headers).json()['items'][0]
    saved = client.post('/api/v1/office/working-patterns', headers=headers, json={'request_id': str(uuid.uuid4()), 'items': [{
        'driver_id': existing['driver_id'], 'weekday_mask': existing['weekday_mask'], 'local_start': existing['local_start'], 'local_end': existing['local_end'],
        'ends_next_day': existing['ends_next_day'], 'valid_from': existing['valid_from'], 'valid_until': existing['valid_until']}]})
    assert saved.status_code == 200, saved.text[:300]
    assert isinstance(saved.json()['impact_count'], int)
