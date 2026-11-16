from tests.integration.test_identity import identity_setup, accept
from tests.integration.test_operational_snapshots import setup_operator, template_payload

RULES = '/api/v1/work-rules'


def administrator(identity_setup, which='first'):
    response = accept(identity_setup['client'], identity_setup[which])
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def route_of(identity_setup, template):
    from app.domain.timetables.models import Route
    with identity_setup['owner_factory']() as db:
        return db.query(Route).filter_by(origin_station_id=template['origin']['id'], destination_station_id=template['destination']['id']).one().id


def test_get_defaults(identity_setup):
    client = identity_setup['client']
    headers = administrator(identity_setup)
    body = client.get(RULES, headers=headers)
    assert body.status_code == 200, body.text
    data = body.json()
    assert data['legal_version'] == 'gr-pd54-1998+eu561-2026-11' and data['company_version'] == 0
    limit = next(item for item in data['limits'] if item['rule_id'] == 'daily_work_max')
    assert limit == {'rule_id': 'daily_work_max', 'legal': 600, 'value': 600, 'direction': 'max', 'source': limit['source']}
    assert data['warning_rules'] == []
    assert data['warning_catalogue'] == ['no_consecutive_overnight', 'overnight_rest_day', 'shift_rotation']


def test_put_stricter_saves_and_audits(identity_setup):
    client = identity_setup['client']
    headers = administrator(identity_setup)
    saved = client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': {'daily_work_max': 570, 'daily_rest': 780}, 'warning_rules': ['shift_rotation']})
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data['company_version'] == 1 and data['warning_rules'] == ['shift_rotation']
    assert {item['rule_id']: item['value'] for item in data['limits']}['daily_work_max'] == 570
    assert client.get(RULES, headers=headers).json() == data
    stale = client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': {}, 'warning_rules': []})
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'stale_version'
    from app.domain.office.models import OfficeAudit
    with identity_setup['owner_factory']() as db:
        rows = db.query(OfficeAudit).filter_by(entity='work_rules').all()
        assert len(rows) == 1 and rows[0].actor_id


def test_put_looser_422(identity_setup):
    client = identity_setup['client']
    headers = administrator(identity_setup)
    looser = client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': {'daily_work_max': 700}, 'warning_rules': []})
    assert looser.status_code == 422
    assert looser.json()['detail'] == {'code': 'looser_than_law', 'message': looser.json()['detail']['message'], 'rule_id': 'daily_work_max', 'legal': 600}
    for overrides in ({'nonsense': 5}, {'daily_work_max': 'x'}, {'daily_work_max': 0}, {'daily_work_max': 5.5}):
        assert client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': overrides, 'warning_rules': []}).status_code == 422
    assert client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': {}, 'warning_rules': ['nope']}).status_code == 422
    assert client.get(RULES, headers=headers).json()['company_version'] == 0


def test_put_requires_organization_manage(identity_setup):
    from app.domain.identity.service import issue_invitation
    client = identity_setup['client']
    invite = identity_setup['first']
    with identity_setup['owner_factory']() as db:
        dispatcher = issue_invitation(db, invite.tenant_id, 'dispatcher-rules@example.org', 'dispatcher')
        db.commit()
    headers = {'Authorization': 'Bearer ' + accept(client, dispatcher).json()['access_token']}
    assert client.get(RULES, headers=headers).status_code == 200
    assert client.put(RULES, headers=headers, json={'expected_version': 0, 'overrides': {}, 'warning_rules': []}).status_code == 403


def test_profile_prefer_and_forbid_same_route_422(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    template = create('timetables', template_payload(origin, destination))
    route = route_of(identity_setup, template)
    url = f"{RULES}/drivers/{driver['id']}/profile"
    assert client.get(url, headers=headers).json()['version'] == 0
    body = {'expected_version': 0, 'overnight_allowed': False, 'split_shift_allowed': True, 'must_return_to_base': True,
            'preferred_route_ids': [route], 'forbidden_route_ids': [route]}
    assert client.put(url, headers=headers, json=body).status_code == 422
    saved = client.put(url, headers=headers, json={**body, 'forbidden_route_ids': []})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {'driver_id': driver['id'], 'version': 1, 'overnight_allowed': False, 'split_shift_allowed': True,
                            'must_return_to_base': True, 'preferred_route_ids': [route], 'forbidden_route_ids': []}
    flipped = client.put(url, headers=headers, json={**body, 'expected_version': 1, 'preferred_route_ids': [], 'forbidden_route_ids': [route]})
    assert flipped.json()['forbidden_route_ids'] == [route] and flipped.json()['preferred_route_ids'] == []
    assert client.put(url, headers=headers, json={**body, 'expected_version': 1, 'forbidden_route_ids': [], 'preferred_route_ids': [9999]}).status_code == 422
    forbidden = f"{RULES}/vehicles/{vehicle['id']}/forbidden-routes"
    assert client.put(forbidden, headers=headers, json={'route_ids': [route]}).json()['route_ids'] == [route]
    assert client.get(forbidden, headers=headers).json()['route_ids'] == [route]
    assert client.put(forbidden, headers=headers, json={'route_ids': []}).json()['route_ids'] == []


def test_baseline_locked_after_publication(identity_setup):
    from tests.integration.test_office_impacts import driver_of
    from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    url = f"{RULES}/drivers/{driver_of(revision, first)}/baseline"
    body = {'expected_version': 0, 'as_of': '2026-05-31', 'overtime_minutes': 120, 'last_duty_end': '2026-05-30T18:00:00Z',
            'last_weekly_rest_end': None, 'last_weekly_rest_at_base': True, 'owed_rest_minutes': 0}
    for as_of in ('2026-05-31', '2026-06-01'):
        locked = client.put(url, headers=headers, json={**body, 'as_of': as_of})
        assert locked.status_code == 409 and locked.json()['detail']['code'] == 'baseline_locked'
    saved = client.put(url, headers=headers, json={**body, 'as_of': '2026-06-02'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['version'] == 1 and saved.json()['overtime_minutes'] == 120 and saved.json()['as_of'] == '2026-06-02'
    assert client.get(url, headers=headers).json() == saved.json()
    free = f"{RULES}/drivers/{driver_of(revision, other)}/baseline"
    assert client.put(free, headers=headers, json=body).status_code == 200


def test_stored_baseline_before_publication_stays_locked(identity_setup):
    from datetime import date
    from app.domain.workrules.models import DriverWorkBaseline
    from tests.integration.test_office_impacts import driver_of
    from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    driver_id = driver_of(revision, first)
    with identity_setup['owner_factory']() as db:
        db.add(DriverWorkBaseline(tenant_id=identity_setup['first'].tenant_id, driver_id=driver_id, as_of=date(2026, 5, 20),
                                  overtime_minutes=600, version=1))
        db.commit()
    url = f"{RULES}/drivers/{driver_id}/baseline"
    body = {'expected_version': 1, 'as_of': '2026-07-01', 'overtime_minutes': 0, 'last_duty_end': None,
            'last_weekly_rest_end': None, 'last_weekly_rest_at_base': False, 'owed_rest_minutes': 0}
    for change in ({}, {'as_of': '2026-05-20'}):
        locked = client.put(url, headers=headers, json={**body, **change})
        assert locked.status_code == 409 and locked.json()['detail']['code'] == 'baseline_locked'
    assert client.get(url, headers=headers).json()['overtime_minutes'] == 600


def test_baseline_as_of_must_be_past_and_instants_aware(identity_setup):
    from datetime import date, timedelta
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    url = f"{RULES}/drivers/{driver['id']}/baseline"
    body = {'expected_version': 0, 'as_of': '2026-05-31', 'overtime_minutes': 0, 'last_duty_end': None,
            'last_weekly_rest_end': None, 'last_weekly_rest_at_base': False, 'owed_rest_minutes': 0}
    for future in (date.today() + timedelta(days=2), date(2099, 1, 1)):
        rejected = client.put(url, headers=headers, json={**body, 'as_of': future.isoformat()})
        assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'baseline_as_of_not_past'
    for key in ('last_duty_end', 'last_weekly_rest_end'):
        assert client.put(url, headers=headers, json={**body, key: '2026-05-30T18:00:00'}).status_code == 422
    assert client.get(url, headers=headers).json()['version'] == 0
    assert client.put(url, headers=headers, json=body).status_code == 200


def test_other_tenant_cannot_read(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    other = administrator(identity_setup, 'second')
    for path in (f"/drivers/{driver['id']}/profile", f"/drivers/{driver['id']}/baseline", f"/vehicles/{vehicle['id']}/forbidden-routes"):
        assert client.get(RULES + path, headers=other).status_code == 404
    assert client.put(f"{RULES}/vehicles/{vehicle['id']}/forbidden-routes", headers=other, json={'route_ids': []}).status_code == 404


def test_route_service_type_roundtrip(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    template = create('timetables', template_payload(origin, destination, service_type='urban'))
    assert template['service_type'] == 'urban'
    assert client.get(f"/api/v1/timetables/{template['id']}", headers=headers).json()['service_type'] == 'urban'
    changed = client.patch(f"/api/v1/timetables/{template['id']}", headers=headers, json={'version': template['version'], 'service_type': 'intercity'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['service_type'] == 'intercity'
    assert create('timetables', template_payload(origin, destination, trip_code='T002'))['service_type'] == 'intercity'
    assert client.post('/api/v1/timetables', headers=headers, json={**template_payload(origin, destination, trip_code='T003'), 'service_type': 'metro'}).status_code == 422


def test_route_en_route_break_roundtrip(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    template = create('timetables', template_payload(origin, destination, en_route_break_minutes=45))
    assert template['en_route_break_minutes'] == 45
    url = f"/api/v1/timetables/{template['id']}"
    assert client.get(url, headers=headers).json()['en_route_break_minutes'] == 45
    changed = client.patch(url, headers=headers, json={'version': template['version'], 'en_route_break_minutes': 30})
    assert changed.status_code == 200, changed.text
    assert changed.json()['en_route_break_minutes'] == 30
    too_long = client.patch(url, headers=headers, json={'version': changed.json()['version'], 'en_route_break_minutes': 105})
    assert too_long.status_code == 422 and too_long.json()['detail']['code'] == 'en_route_break_too_long'
    shorter = client.patch(url, headers=headers, json={'version': changed.json()['version'], 'departure_time': '01:00', 'arrival_day_offset': 0})
    assert shorter.status_code == 422 and shorter.json()['detail']['code'] == 'en_route_break_too_long'
    assert create('timetables', template_payload(origin, destination, trip_code='T002'))['en_route_break_minutes'] == 0
    for value in (-1, 241):
        assert client.post('/api/v1/timetables', headers=headers, json=template_payload(origin, destination, trip_code='T003', en_route_break_minutes=value)).status_code == 422


def test_routes_listing(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    template = create('timetables', template_payload(origin, destination, service_type='urban'))
    routes = client.get(f"{RULES}/routes", headers=headers).json()['routes']
    assert [r['id'] for r in routes] == [route_of(identity_setup, template)]
    assert routes[0]['service_type'] == 'urban' and routes[0]['origin']['code'] == origin['code']


def test_routes_listing_excludes_other_tenant(identity_setup):
    client, headers, create, origin, destination, driver, vehicle = setup_operator(identity_setup)
    create('timetables', template_payload(origin, destination))
    other = administrator(identity_setup, 'second')
    assert client.get(f"{RULES}/routes", headers=other).json() == {'routes': []}
    assert len(client.get(f"{RULES}/routes", headers=headers).json()['routes']) == 1
