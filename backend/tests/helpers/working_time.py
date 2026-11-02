"""Test fixtures state working time explicitly, the way an organization must before a draft can be created."""
import uuid


def give_working_time(client, headers, driver_ids=None, *, valid_from='2026-01-01', valid_until='2026-12-31'):
    """Grant the signed-in administrator `availability.manage` and record all-day working patterns for the drivers."""
    me = client.get('/api/v1/identity/members', headers=headers).json()['members'][0]['id']
    granted = client.put('/api/v1/office/grants', headers=headers, json={'request_id': str(uuid.uuid4()), 'membership_id': me,
                                                                          'capability': 'availability.manage', 'is_active': True, 'expected_version': None})
    assert granted.status_code in (200, 409), granted.text
    if driver_ids is None:
        driver_ids = [row['id'] for row in client.get('/api/v1/drivers', headers=headers, params={'page_size': 100}).json()['items']]
    if not driver_ids:
        return
    saved = client.post('/api/v1/office/working-patterns', headers=headers, json={'request_id': str(uuid.uuid4()), 'items': [
        {'driver_id': driver, 'weekday_mask': 127, 'local_start': '00:00', 'local_end': '23:59', 'ends_next_day': True,
         'valid_from': valid_from, 'valid_until': valid_until} for driver in driver_ids]})
    assert saved.status_code == 200, saved.text


def approve_leave(client, headers, driver_id, start='2026-06-01T00:00:00', end='2026-06-02T00:00:00'):
    """The administrator becomes the default leave approver and approves one absence for the driver."""
    me = client.get('/api/v1/identity/members', headers=headers).json()['members'][0]['id']
    routes = client.get('/api/v1/office/approval-routes', headers=headers).json()['routes']
    if not routes:
        assert client.post('/api/v1/office/approval-routes', headers=headers, json={'request_id': str(uuid.uuid4()), 'membership_id': me}).status_code == 201
    leave = client.post('/api/v1/office/leave-requests', headers=headers, json={'request_id': str(uuid.uuid4()), 'driver_id': driver_id,
        'start_local': start, 'end_local': end, 'category': 'annual'})
    assert leave.status_code == 201, leave.text
    decided = client.post(f"/api/v1/office/leave-requests/{leave.json()['id']}/decision", headers=headers, json={
        'request_id': str(uuid.uuid4()), 'expected_version': leave.json()['version'], 'decision': 'approved', 'note': None})
    assert decided.status_code == 200, decided.text
    return decided.json()
