"""New operational drafts freeze usable windows (v2); a driver with unknown working time blocks draft creation with one clear next step."""
import uuid
from sqlalchemy import text
from tests.helpers.working_time import give_working_time
from tests.integration.test_canonical_studio import prepared_customer
from tests.integration.test_identity import identity_setup
from app.domain.scheduling.snapshots import decode_problem


def test_unknown_working_time_blocks_the_draft_and_names_the_driver(identity_setup):
    client, headers, template, pairing, driver = prepared_customer(identity_setup, working_time=False)
    readiness = client.get('/api/v1/timetables/operational-readiness', headers=headers, params={'service_date': '2026-06-01'})
    codes = {issue['code'] for issue in readiness.json()['issues']} if readiness.status_code == 200 else set()
    created = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'})
    assert created.status_code == 422, created.text[:300]
    body = created.json()['detail']
    assert body['code'] in ('day_not_ready', 'working_windows_required')
    assert 'working_windows_required' in codes | {issue.get('code') for issue in body.get('issues', [])} | {body['code']}


def test_a_draft_freezes_v2_windows_and_enforcement_with_provenance(identity_setup):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    created = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'})
    assert created.status_code == 201, created.text[:300]
    with identity_setup['owner_factory']() as db:
        problem_data, source = db.execute(text('SELECT problem_data, source_data FROM domain_revision_snapshots WHERE revision_id=:r'), {'r': created.json()['revision_id']}).one()
    problem = decode_problem(problem_data)
    assert source['source_schema_version'] == 'ktel-operational-v2' and problem.availability_enforced
    window = problem.resources[0].available_windows
    assert window and all(isinstance(a, int) and isinstance(b, int) and a < b for a, b in window)
    assert source['availability']['fingerprint'] and 'availability' not in source['source_versions']
    assert problem.trips[0].start_minutes >= window[0][0] and problem.trips[0].end_minutes <= window[-1][1]


def test_recording_or_rejecting_pending_leave_keeps_the_same_draft(identity_setup):
    client, headers, template, pairing, driver = prepared_customer(identity_setup)
    first = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'})
    assert first.status_code == 201, first.text[:300]
    me = client.get('/api/v1/identity/members', headers=headers).json()['members'][0]['id']
    assert client.post('/api/v1/office/approval-routes', headers=headers, json={'request_id': str(uuid.uuid4()), 'membership_id': me}).status_code == 201
    leave = client.post('/api/v1/office/leave-requests', headers=headers, json={'request_id': str(uuid.uuid4()), 'driver_id': driver['id'],
        'start_local': '2026-06-01T00:00:00', 'end_local': '2026-06-02T00:00:00', 'category': 'annual'})
    assert leave.status_code == 201, leave.text[:300]
    pending = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'})
    assert pending.json()['revision_id'] == first.json()['revision_id']
    rejected = client.post(f"/api/v1/office/leave-requests/{leave.json()['id']}/decision", headers=headers, json={
        'request_id': str(uuid.uuid4()), 'expected_version': leave.json()['version'], 'decision': 'rejected', 'note': 'Not possible'})
    assert rejected.status_code == 200, rejected.text[:300]
    again = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date': '2026-06-01'})
    assert again.json()['revision_id'] == first.json()['revision_id']
