"""Daily reporting is explicit, publication-bound and append-only under real RLS."""
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.integration.test_identity import identity_setup, accept
from tests.integration.test_canonical_studio import prepared_customer

DAY='2026-06-01'
URL='/api/v1/operations'


def published_customer(setup):
    client,headers,template,pairing,driver=prepared_customer(setup)
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':DAY})
    assert response.status_code==201,response.text
    revision=response.json()
    response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches',headers=headers,json={
        'version':revision['version'],'patches':[{'trip_id':revision['assignments'][0]['trip_id'],'new_resource_id':revision['source_resources'][0]['resource_id']}]})
    assert response.status_code==200,response.text
    revision=response.json()
    for action in ('request-approval','approve','publish'):
        response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/'+action,headers=headers,json={'version':revision['version']})
        assert response.status_code==200,response.text
        revision=response.json()
    return client,headers,revision


def board(client,headers,**params):
    response=client.get(URL+'/day',headers=headers,params={'service_date':DAY,**params})
    assert response.status_code==200,response.text[:500]
    return response.json()


def report_payload(data,**fields):
    return {'publication_id':data['publication']['publication_id'],'trip_id':data['items'][0]['trip_id'],
            'expected_version':data['items'][0]['version'],'request_id':str(uuid.uuid4()),
            'kind':'delay','description':'Driver reported roadworks.','delay_minutes':12,**fields}


def test_draft_days_have_no_operations_and_reads_do_not_invent_departures(identity_setup):
    client,headers,revision=published_customer(identity_setup)
    data=board(client,headers)
    assert data['total']==1 and data['items'][0]['reported_status']=='planned'
    assert data['items'][0]['version']==0 and data['items'][0]['events']==[]
    assert data['items'][0]['trip']['trip_code']=='T001'
    assert data['items'][0]['resource']['driver_name']=='Νίκος Δήμου'
    assert board(client,headers,q='nonexistent')['total']==0
    assert board(client,headers,open_only=True)['total']==0
    response=client.get(URL+'/day?service_date=2026-06-02',headers=headers)
    assert response.status_code==200 and response.json()['publication'] is None
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT count(*) FROM domain_operational_trip_states')).scalar_one()==0


def test_report_resolve_and_exact_retries_preserve_published_history(identity_setup):
    client,headers,revision=published_customer(identity_setup)
    data=board(client,headers);payload=report_payload(data)
    saved=client.post(URL+'/reports',headers=headers,json=payload)
    assert saved.status_code==201,saved.text
    event=saved.json()
    retry=client.post(URL+'/reports',headers=headers,json=payload)
    assert retry.status_code==201 and retry.json()==event
    assert client.post(URL+'/reports',headers=headers,json={**payload,'description':'Different content'}).status_code==409
    current=board(client,headers)
    assert current['open_count']==1 and current['items'][0]['version']==1
    assert current['items'][0]['reported_status']=='planned'
    assert current['items'][0]['events'][0]['actor_name']=='KTEL administrator'
    stale=client.post(URL+'/reports',headers=headers,json={**payload,'request_id':str(uuid.uuid4())})
    assert stale.status_code==409
    resolved={'expected_version':1,'request_id':str(uuid.uuid4()),'note':'Driver confirmed the road is clear.'}
    response=client.post(URL+'/reports/'+str(event['id'])+'/resolve',headers=headers,json=resolved)
    assert response.status_code==201,response.text
    assert client.post(URL+'/reports/'+str(event['id'])+'/resolve',headers=headers,json=resolved).json()==response.json()
    assert client.post(URL+'/reports/'+str(event['id'])+'/resolve',headers=headers,json={**resolved,'expected_version':2,'request_id':str(uuid.uuid4())}).status_code==409
    current=board(client,headers)
    assert current['open_count']==0 and len(current['items'][0]['events'])==2 and current['items'][0]['version']==2
    assert current['items'][0]['events'][0]['description']==payload['description']
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision
    # Departure/completion require actual explicit reports, never a planned clock.
    for kind,version in (('departure',2),('completion',3)):
        update=report_payload(current,kind=kind,expected_version=version,delay_minutes=None,description='Confirmed by telephone.')
        assert client.post(URL+'/reports',headers=headers,json=update).status_code==201
        assert board(client,headers)['items'][0]['reported_status']==kind


def test_board_and_reports_are_capability_and_tenant_scoped(identity_setup):
    from app.domain.identity.service import issue_invitation
    client,headers,revision=published_customer(identity_setup)
    data=board(client,headers);payload=report_payload(data)
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert board(client,foreign)['publication'] is None
    assert client.get(URL+'/day',headers=foreign,params={'service_date':DAY,'publication_id':payload['publication_id']}).status_code==404
    assert client.post(URL+'/reports',headers=foreign,json=payload).status_code==404
    for role,read_status in (('viewer',200),('driver',403)):
        with identity_setup['owner_factory']() as db:
            invitation=issue_invitation(db,identity_setup['first'].tenant_id,role+'-ops@example.org',role);db.commit()
        restricted={'Authorization':'Bearer '+accept(client,invitation).json()['access_token']}
        assert client.get(URL+'/day?service_date='+DAY,headers=restricted).status_code==read_status
        assert client.post(URL+'/reports',headers=restricted,json=payload).status_code==403
    assert client.post(URL+'/reports',headers=headers,json={**payload,'trip_id':'foreign-trip'}).status_code==404


def test_report_contract_rejects_unknown_and_inapplicable_fields(identity_setup):
    client,headers,revision=published_customer(identity_setup);payload=report_payload(board(client,headers))
    for patch in ({'delay_minutes':None},{'delay_minutes':True},{'delay_minutes':-1},{'description':'   '},{'kind':'gps'},{'tenant_id':2},{'kind':'note','delay_minutes':12}):
        assert client.post(URL+'/reports',headers=headers,json={**payload,**patch}).status_code==422
    assert board(client,headers)['items'][0]['version']==0


def test_runtime_history_is_append_only_worker_has_no_access_and_fks_bind_trip_to_publication(identity_setup,restricted_databases):
    client,headers,revision=published_customer(identity_setup);payload=report_payload(board(client,headers))
    assert client.post(URL+'/reports',headers=headers,json=payload).status_code==201
    tenant=identity_setup['first'].tenant_id
    for statement in ('UPDATE domain_operational_events SET description=\'rewritten\'', 'DELETE FROM domain_operational_events'):
        with restricted_databases['api'].begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(tenant)})
            with pytest.raises(DBAPIError):connection.execute(text(statement))
    with restricted_databases['worker'].begin() as connection:
        with pytest.raises(DBAPIError):connection.execute(text('SELECT * FROM domain_operational_trip_states'))
    with identity_setup['owner_factory']() as db:
        state=db.execute(text('SELECT tenant_id,publication_id,revision_id,trip_id FROM domain_operational_trip_states')).mappings().one()
        # Even the owner cannot bind a different revision/trip or tenant physically.
        for changes in ({'trip_id':'made-up'},{'revision_id':'other-revision'},{'tenant_id':identity_setup['second'].tenant_id}):
            with pytest.raises(DBAPIError):
                with db.begin_nested():
                    db.execute(text('INSERT INTO domain_operational_trip_states (tenant_id,publication_id,revision_id,trip_id,version) VALUES (:tenant_id,:publication_id,:revision_id,:trip_id,1)'),dict(state)|changes)
        hints=db.execute(text("SELECT job_id,payload FROM domain_outbox_events WHERE event_type='operations.updated'")).all()
        assert len(hints)==1 and hints[0].job_id is None
        assert set(hints[0].payload)=={'publication_id','trip_id','version'}


def publish_revision(client,headers):
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':DAY})
    assert response.status_code==201,response.text
    revision=response.json()
    response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches',headers=headers,json={
        'version':revision['version'],'patches':[{'trip_id':revision['assignments'][0]['trip_id'],'new_resource_id':revision['source_resources'][0]['resource_id']}]})
    assert response.status_code==200,response.text
    revision=response.json()
    for action in ('request-approval','approve','publish'):
        response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/'+action,headers=headers,json={'version':revision['version']})
        assert response.status_code==200,response.text
        revision=response.json()
    return revision


def test_newer_publication_does_not_rebind_reports_or_frozen_names(identity_setup):
    client,headers,revision=published_customer(identity_setup);old=board(client,headers);payload=report_payload(old)
    assert client.post(URL+'/reports',headers=headers,json=payload).status_code==201
    stations=client.get('/api/v1/stations',headers=headers).json()['items']
    origin=next(station for station in stations if station['id']==old['items'][0]['trip']['origin']['id'])
    assert client.patch('/api/v1/stations/'+str(origin['id']),headers=headers,json={'version':origin['version'],'name_el':'Νέα αφετηρία'}).status_code==200
    # Review the changed source explicitly before publishing a different snapshot.
    pairs=client.get('/api/v1/pairings?service_date='+DAY,headers=headers).json()['items']
    pair=pairs[0]
    assert client.patch('/api/v1/pairings/'+str(pair['id']),headers=headers,json={
        'version':pair['version'],'confirm':True,'driver_version':pair['driver_version'],'vehicle_version':pair['vehicle_version'],'home_station_version':pair['home_station_version']}).status_code==200
    directions=client.get('/api/v1/transfers/editor?service_date='+DAY,headers=headers).json()['items'][0]
    edits=[]
    for key in ('forward','reverse'):
        row=directions[key]
        edits.append({field:row[field] for field in ('origin_station_id','destination_station_id','origin_version','destination_version','minutes')}|{'expected_version':row['version']})
    assert client.post('/api/v1/transfers/editor',headers=headers,json={'items':edits}).status_code==200
    newer=publish_revision(client,headers)
    assert newer['revision_id']!=revision['revision_id']
    latest=board(client,headers)
    assert latest['open_count']==1 and latest['items'][0]['events']==[]
    assert latest['items'][0]['linked_events'][0]['source_publication']['publication_id']==payload['publication_id']
    historical=board(client,headers,publication_id=payload['publication_id'])
    assert historical['newer_publication'] and historical['open_count']==1
    assert historical['items'][0]['trip']['origin']['name_el']=='Αφετηρία'
    assert latest['items'][0]['trip']['origin']['name_el']=='Νέα αφετηρία'
    # A form opened on the old publication stays on it after a newer publication.
    assert client.post(URL+'/reports',headers=headers,json={**payload,'request_id':str(uuid.uuid4()),'expected_version':1,'description':'Still belongs to the old schedule.'}).status_code==201
    latest=board(client,headers)
    assert latest['open_count']==2 and latest['items'][0]['events']==[]
    assert all(item['source_publication']['publication_id']==payload['publication_id'] for item in latest['items'][0]['linked_events'])
    assert board(client,headers,publication_id=payload['publication_id'])['open_count']==2


def test_concurrent_reports_and_retries_have_one_durable_outcome(identity_setup):
    from concurrent.futures import ThreadPoolExecutor
    client,headers,revision=published_customer(identity_setup);payload=report_payload(board(client,headers))
    def post(body):return client.post(URL+'/reports',headers=headers,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(post,[payload,{**payload,'request_id':str(uuid.uuid4())}]))
    assert sorted(response.status_code for response in responses)==[201,409]
    current=board(client,headers)
    assert current['items'][0]['version']==1 and len(current['items'][0]['events'])==1
    retry=report_payload(current,description='Second report, sent twice concurrently.')
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(post,[retry,retry]))
    assert all(response.status_code==201 for response in responses)
    assert responses[0].json()==responses[1].json()
    assert len(board(client,headers)['items'][0]['events'])==2
    # Cookie-authenticated writes still need the actual CSRF token.
    assert client.post(URL+'/reports',json={**retry,'request_id':str(uuid.uuid4()),'expected_version':2}).status_code==403


def test_trip_id_filter_selects_exact_frozen_trip_and_obeys_tenant_scope(identity_setup):
    client,headers,revision=published_customer(identity_setup)
    data=board(client,headers);trip=data['items'][0]['trip_id']
    assert board(client,headers,trip_id=trip)['total']==1
    assert board(client,headers,trip_id='not-the-trip')['total']==0
    assert board(client,headers,trip_id=trip,q='not-a-match')['total']==0
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert board(client,foreign,trip_id=trip)['total']==0
