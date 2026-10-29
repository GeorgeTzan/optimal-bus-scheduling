"""Optional through-service links persist and become independently verified chains."""
from tests.integration.test_identity import identity_setup
from tests.integration.test_canonical_studio import prepared_customer


def following_service(client, headers, first, code='T002', departure='10:00', arrival='11:00'):
    payload = {key: first[key] for key in ('arrival_day_offset','operating_weekdays','valid_from','valid_until','allowed_bus_types')}
    payload.update(trip_code=code, origin_station_id=first['destination']['id'], destination_station_id=first['origin']['id'], departure_time=departure, arrival_time=arrival)
    response = client.post('/api/v1/timetables', headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def link_request(incoming, outgoing):
    return {'incoming_template_id': incoming['id'], 'outgoing_template_id': outgoing['id'],
            'incoming_template_version': incoming['version'], 'outgoing_template_version': outgoing['version']}


def test_connections_persist_as_real_chains_and_changed_rules_stale_existing_drafts(identity_setup):
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client, headers, first)
    created = client.post('/api/v1/connections', headers=headers, json=link_request(first, second))
    assert created.status_code == 201, created.text
    connection = created.json()
    assert connection['incoming']['trip_code'] == 'T001' and connection['outgoing']['trip_code'] == 'T002'
    assert client.get('/api/v1/connections', headers=headers).json()['items'][0]['id'] == connection['id']
    revision = client.post('/api/v1/scheduling/revisions', headers=headers, json={'service_date':'2026-06-01'})
    assert revision.status_code == 201, revision.text[:500]
    data = revision.json()
    trip_ids = {row['trip_code']: row['id'] for row in data['source_trips']}
    assert data['problem']['chains'] == [{'trip_ids':[trip_ids['T001'],trip_ids['T002']]}]
    patched = client.post('/api/v1/scheduling/revisions/'+data['revision_id']+'/patches', headers=headers, json={'version':1,
        'patches':[{'trip_id':trip_ids['T001'],'new_resource_id':data['problem']['resources'][0]['resource_id']}]})
    assert patched.status_code == 200
    assert any(issue['rule_id'] == 'RULE_MANDATORY_CHAIN' for issue in patched.json()['verification']['violations'])
    archived = client.patch('/api/v1/connections/'+str(connection['id']), headers=headers, json={'version':1,'is_active':False})
    assert archived.status_code == 200
    assert client.get('/api/v1/scheduling/revisions/'+data['revision_id'], headers=headers).json()['source_review_required'] is True


def test_branching_cyclic_and_stale_connection_changes_are_rejected(identity_setup):
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client, headers, first)
    third = following_service(client, headers, first, 'T003','12:00','13:00')
    created = client.post('/api/v1/connections', headers=headers, json=link_request(first, second))
    assert created.status_code == 201, created.text
    branch = client.post('/api/v1/connections', headers=headers, json=link_request(first, third))
    assert branch.status_code == 422 and branch.json()['detail']['code'] == 'connection_branch'
    cycle = client.post('/api/v1/connections', headers=headers, json=link_request(second, first))
    assert cycle.status_code == 422 and cycle.json()['detail']['code'] == 'connection_cycle'
    stale = client.patch('/api/v1/connections/'+str(created.json()['id']), headers=headers, json={'version':2,'is_active':False})
    assert stale.status_code == 409


def test_connection_workbook_is_reviewed_committed_and_exported_with_real_trip_refs(identity_setup):
    from app.domain.imports.templates import generate_template
    from app.domain.imports.parsers import parse_upload
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client, headers, first)
    content = generate_template('connections','en',[{'incoming_ref':'T001','outgoing_ref':'T002'}])
    staged = client.post('/api/v1/imports', headers=headers, data={'entity':'connections','locale':'en'},
        files={'file':('connections.xlsx',content)})
    assert staged.status_code == 201, staged.text[:500]
    batch = staged.json();assert batch['status'] == 'ready' and batch['summary']['new'] == 1
    assert client.get('/api/v1/connections', headers=headers).json()['total'] == 0
    saved = client.post('/api/v1/imports/'+batch['batch_id']+'/commit', headers=headers, json={'version':batch['version']})
    assert saved.status_code == 200, saved.text[:500]
    assert client.get('/api/v1/connections', headers=headers).json()['total'] == 1
    download = client.get('/api/v1/imports/'+batch['batch_id']+'/populated.xlsx', headers=headers)
    assert download.status_code == 200
    parsed = parse_upload(download.content,'complete.xlsx','all','en')
    assert parsed.is_valid and parsed.rows[0].values['incoming_ref'] == 'T001'
    assert parsed.rows[0].values['outgoing_ref'] == 'T002'


def test_connection_graph_preview_blocks_the_whole_workbook_without_creating_prefix_rows(identity_setup):
    from app.domain.imports.templates import generate_template
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client, headers, first)
    assert client.post('/api/v1/connections', headers=headers, json=link_request(first,second)).status_code == 201
    records={'timetable':[{'trip_code':'T003','origin':first['origin']['code'],'destination':first['destination']['code'],
        'departure_time':'12:00','arrival_time':'13:00','arrival_day_offset':0,'operating_weekdays':first['operating_weekdays'],
        'valid_from':first['valid_from'],'valid_until':first['valid_until'],'allowed_bus_types':['02']}],
        'connections':[{'incoming_ref':'T001','outgoing_ref':'T003'}]}
    staged=client.post('/api/v1/imports',headers=headers,data={'entity':'all','locale':'en'},files={'file':('graph.xlsx',generate_template('all','en',records))})
    assert staged.status_code == 201, staged.text[:500]
    batch=staged.json();assert batch['status']=='review'
    assert any(issue['code']=='connection_branch' for row in batch['rows'] for issue in row['issues'])
    assert client.post('/api/v1/imports/'+batch['batch_id']+'/commit',headers=headers,json={'version':batch['version']}).status_code == 422
    assert client.get('/api/v1/timetables',headers=headers).json()['total']==2


def test_connection_foreign_keys_rls_and_worker_privileges_form_a_second_boundary(identity_setup,restricted_databases):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.exc import IntegrityError,ProgrammingError
    from app.domain.timetables.models import ServiceConnection
    from app.domain.identity.tenant_session import set_tenant_scope
    from tests.integration.test_identity import accept
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client,headers,first)
    own=client.post('/api/v1/connections',headers=headers,json=link_request(first,second)).json()
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert client.get('/api/v1/connections',headers=foreign).json()['total']==0
    assert client.patch('/api/v1/connections/'+str(own['id']),headers=foreign,json={'version':1,'is_active':False}).status_code==404
    station=client.post('/api/v1/stations',headers=foreign,json={'name_el':'Foreign'}).json()
    payload={key:first[key] for key in ('departure_time','arrival_time','arrival_day_offset','operating_weekdays','valid_from','valid_until','allowed_bus_types')}
    payload.update(trip_code='FOREIGN',origin_station_id=station['id'],destination_station_id=station['id'])
    distant=client.post('/api/v1/timetables',headers=foreign,json=payload)
    assert distant.status_code==201,distant.text[:500]
    blocked = client.post('/api/v1/connections',headers=headers,json=link_request(second,distant.json()))
    assert blocked.status_code == 422 and blocked.json()['detail']['code'] == 'record_unavailable'
    with identity_setup['owner_factory']() as db:
        db.add(ServiceConnection(tenant_id=identity_setup['first'].tenant_id,incoming_template_id=second['id'],outgoing_template_id=distant.json()['id']))
        with pytest.raises(IntegrityError):db.flush()
        db.rollback()
    with sessionmaker(bind=restricted_databases['api'])() as db:
        set_tenant_scope(db,identity_setup['second'].tenant_id)
        assert db.execute(text('SELECT count(*) FROM domain_service_connections')).scalar_one()==0
    with sessionmaker(bind=restricted_databases['worker'])() as db:
        set_tenant_scope(db,identity_setup['first'].tenant_id)
        with pytest.raises(ProgrammingError):db.execute(text('SELECT count(*) FROM domain_service_connections'))


def test_connection_can_reference_a_template_created_in_the_same_atomic_workbook(identity_setup):
    from app.domain.imports.templates import generate_template
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    records={'timetable':[{'trip_code':'T002','origin':first['destination']['code'],'destination':first['origin']['code'],
        'departure_time':'10:00','arrival_time':'11:00','arrival_day_offset':0,'operating_weekdays':first['operating_weekdays'],
        'valid_from':first['valid_from'],'valid_until':first['valid_until'],'allowed_bus_types':['02']}],
        'connections':[{'incoming_ref':'T001','outgoing_ref':'T002'}]}
    staged=client.post('/api/v1/imports',headers=headers,data={'entity':'all','locale':'en'},files={'file':('through-service.xlsx',generate_template('all','en',records))})
    assert staged.status_code==201,staged.text[:500]
    batch=staged.json();assert batch['status']=='ready' and batch['summary']['new']==2
    saved=client.post('/api/v1/imports/'+batch['batch_id']+'/commit',headers=headers,json={'version':batch['version']})
    assert saved.status_code==200,saved.text[:500]
    links=client.get('/api/v1/connections',headers=headers).json()['items']
    assert len(links)==1 and links[0]['outgoing']['trip_code']=='T002'


def test_day_readiness_explains_an_impossible_connection_before_optimization(identity_setup):
    client, headers, first, pairing, driver = prepared_customer(identity_setup)
    second = following_service(client,headers,first,departure='08:30',arrival='09:30')
    assert client.post('/api/v1/connections',headers=headers,json=link_request(first,second)).status_code==201
    ready=client.get('/api/v1/setup/readiness?service_date=2026-06-01',headers=headers)
    assert ready.status_code==200 and ready.json()['inputs_ready'] is False
    assert any(issue['code']=='connection_time_conflict' for issue in ready.json()['issues'])
    blocked=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'})
    assert blocked.status_code==422 and blocked.json()['detail']['code']=='day_not_ready'
