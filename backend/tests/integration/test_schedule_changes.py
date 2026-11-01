"""A published schedule is never edited while preparing a reviewed successor."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from tests.integration.test_identity import identity_setup,accept
from tests.integration.test_daily_operations import published_customer,board,report_payload

PREVIEW='/api/v1/scheduling/changes/preview'
APPLY='/api/v1/scheduling/changes'

def request_for(client,headers,revision):
    published=board(client,headers)
    return {'publication_id':published['publication']['publication_id'],'version':revision['version'],
        'reason':'Driver unavailable; checking alternative coverage.',
        'reviewed_not_started':[revision['assignments'][0]['trip_id']],
        'patches':[{'trip_id':revision['assignments'][0]['trip_id'],'new_resource_id':'UNASSIGNED'}]}

def test_preview_is_read_only_and_successor_retries_are_idempotent(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    with identity_setup['owner_factory']() as db:
        before=db.execute(text('SELECT count(*) FROM domain_schedule_revisions')).scalar_one()
    preview=client.post(PREVIEW,headers=headers,json=request)
    assert preview.status_code==200,preview.text[:400]
    value=preview.json();assert value['base_revision_id']==revision['revision_id']
    assert value['changes'][0]['trip_id']==request['patches'][0]['trip_id']
    assert value['changes'][0]['original_resource_id']==revision['assignments'][0]['resource_id']
    assert value['changes'][0]['new_resource_id']=='UNASSIGNED'
    with identity_setup['owner_factory']() as db:assert db.execute(text('SELECT count(*) FROM domain_schedule_revisions')).scalar_one()==before
    body={**request,'request_id':str(uuid.uuid4())}
    result=client.post(APPLY,headers=headers,json=body);assert result.status_code==201,result.text[:400]
    successor=result.json();assert successor['revision_id']!=revision['revision_id'] and successor['status']=='draft'
    assert successor['assignments'][0]['resource_id']=='UNASSIGNED'
    assert successor['problem']['trips']==revision['problem']['trips']
    assert client.post(APPLY,headers=headers,json=body).json()==successor
    assert client.post(APPLY,headers=headers,json={**body,'reason':'Different reason'}).status_code==409
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision
    assert board(client,headers)['publication']['publication_id']==request['publication_id']


def test_invalid_stale_and_unauthorized_changes_never_create_prefix_writes(identity_setup):
    from app.domain.identity.service import issue_invitation
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    for bad in ({**request,'version':revision['version']-1},{**request,'patches':[request['patches'][0],{'trip_id':'unknown','new_resource_id':'UNASSIGNED'}]},
                {**request,'reviewed_not_started':[]},{**request,'reason':' '}):
        assert client.post(PREVIEW,headers=headers,json=bad).status_code in (409,422)
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert client.post(PREVIEW,headers=foreign,json=request).status_code==404
    with identity_setup['owner_factory']() as db:
        invite=issue_invitation(db,identity_setup['first'].tenant_id,'schedule-change-reader@example.org','viewer');db.commit()
    viewer={'Authorization':'Bearer '+accept(client,invite).json()['access_token']}
    assert client.post(PREVIEW,headers=viewer,json=request).status_code==403
    assert client.post(APPLY,headers=viewer,json={**request,'request_id':str(uuid.uuid4())}).status_code==403
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision


def test_explicit_departure_or_completion_protects_operated_work(identity_setup):
    client,headers,revision=published_customer(identity_setup);data=board(client,headers);request=request_for(client,headers,revision)
    report=report_payload(data,kind='departure',delay_minutes=None,description='Confirmed departed by telephone.')
    assert client.post('/api/v1/operations/reports',headers=headers,json=report).status_code==201
    assert client.post(PREVIEW,headers=headers,json=request).status_code==409
    assert client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())}).status_code==409


def test_concurrent_requests_with_one_id_have_one_successor(identity_setup):
    client,headers,revision=published_customer(identity_setup);body={**request_for(client,headers,revision),'request_id':str(uuid.uuid4())}
    def submit(_):return client.post(APPLY,headers=headers,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(submit,range(2)))
    assert [response.status_code for response in responses]==[201,201]
    assert responses[0].json()['revision_id']==responses[1].json()['revision_id']


def transition(client,headers,revision,action):
    return client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/'+action,headers=headers,json={'version':revision['version']})


def test_a_newer_publication_blocks_an_already_prepared_successor(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    first=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())}).json()
    second=client.post(APPLY,headers=headers,json={**request,'reason':'Another dispatcher prepared a draft','request_id':str(uuid.uuid4())}).json()
    assert first['revision_id']!=second['revision_id']
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,first,action);assert response.status_code==200,response.text[:400];first=response.json()
    rejected=transition(client,headers,second,'request-approval')
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='newer_publication'
    assert client.get('/api/v1/scheduling/revisions/'+second['revision_id'],headers=headers).json()['status']=='draft'


def test_departure_report_after_preparation_blocks_approval_and_unreviewed_patches(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    draft=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())}).json()
    patch=client.post('/api/v1/scheduling/revisions/'+draft['revision_id']+'/patches',headers=headers,json={
        'version':draft['version'],'patches':[{'trip_id':draft['assignments'][0]['trip_id'],'new_resource_id':revision['assignments'][0]['resource_id']}]})
    assert patch.status_code==409
    data=board(client,headers);report=report_payload(data,kind='departure',delay_minutes=None,description='Driver confirmed departure.')
    assert client.post('/api/v1/operations/reports',headers=headers,json=report).status_code==201
    rejected=transition(client,headers,draft,'request-approval')
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='operated_trip'


def test_changed_source_cannot_be_changed(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    station=revision['source_trips'][0]['origin']
    response=client.patch('/api/v1/stations/'+str(station['id']),headers=headers,json={'version':station['version'],'name_el':'Νέο όνομα'})
    assert response.status_code==200,response.text[:400]
    rejected=client.post(PREVIEW,headers=headers,json=request)
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='source_changed'
    assert client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())}).status_code==409


def test_locked_assignment_cannot_be_reassigned_in_successor(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client,headers,_,_,_=prepared_customer(identity_setup)
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'});revision=response.json()
    response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches',headers=headers,json={
        'version':revision['version'],'patches':[{'trip_id':revision['assignments'][0]['trip_id'],'new_resource_id':revision['source_resources'][0]['resource_id'],'is_locked':True}]})
    assert response.status_code==200;revision=response.json()
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,revision,action);assert response.status_code==200,response.text[:400];revision=response.json()
    request=request_for(client,headers,revision)
    rejected=client.post(PREVIEW,headers=headers,json=request)
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='locked_trip'


def test_change_history_is_append_only_for_api_and_inaccessible_to_worker(identity_setup,restricted_databases):
    import pytest
    from sqlalchemy.exc import DBAPIError
    client,headers,revision=published_customer(identity_setup)
    body={**request_for(client,headers,revision),'request_id':str(uuid.uuid4())}
    assert client.post(APPLY,headers=headers,json=body).status_code==201
    tenant=str(identity_setup['first'].tenant_id)
    for statement in ("UPDATE domain_schedule_changes SET reason='rewritten'",'DELETE FROM domain_schedule_changes'):
        with restricted_databases['api'].begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':tenant})
            with pytest.raises(DBAPIError):connection.execute(text(statement))
    with restricted_databases['worker'].begin() as connection:
        with pytest.raises(DBAPIError):connection.execute(text('SELECT * FROM domain_schedule_changes'))


def test_draft_patch_preview_is_read_only_and_checks_version_and_tenant(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client,headers,_,_,_=prepared_customer(identity_setup)
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'});revision=response.json()
    trip=revision['assignments'][0];body={'version':revision['version'],'patches':[{'trip_id':trip['trip_id'],'new_resource_id':revision['source_resources'][0]['resource_id']}]}
    url='/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches/preview'
    preview=client.post(url,headers=headers,json=body);assert preview.status_code==200,preview.text[:400]
    assert preview.json()['changes'][0]['new_resource_id']==body['patches'][0]['new_resource_id']
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision
    assert client.post(url,headers=headers,json={**body,'version':revision['version']+1}).status_code==409
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert client.post(url,headers=foreign,json=body).status_code==404


def test_draft_preview_and_save_reject_changed_sources(identity_setup):
    from tests.integration.test_canonical_studio import prepared_customer
    client,headers,template,_,_=prepared_customer(identity_setup)
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'});revision=response.json()
    body={'version':revision['version'],'patches':[{'trip_id':revision['assignments'][0]['trip_id'],'new_resource_id':revision['source_resources'][0]['resource_id']}]}
    station=template['origin'];changed=client.patch('/api/v1/stations/'+str(station['id']),headers=headers,json={'version':station['version'],'name_el':'Updated'})
    assert changed.status_code==200
    path='/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches'
    for url in (path+'/preview',path):
        response=client.post(url,headers=headers,json=body);assert response.status_code==409 and response.json()['detail']['code']=='source_changed'
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()['version']==revision['version']
