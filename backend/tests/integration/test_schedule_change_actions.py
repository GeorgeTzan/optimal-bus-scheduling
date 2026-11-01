"""Cancellation is distinct from unassignment and remains in publication history."""
import uuid
from tests.integration.test_identity import identity_setup
from tests.integration.test_daily_operations import published_customer,board
from tests.integration.test_schedule_changes import PREVIEW,APPLY,request_for,transition


def test_cancelled_trip_remains_visible_and_is_excluded_from_active_coverage(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision)
    request['patches']=[{'trip_id':request['patches'][0]['trip_id'],'operation':'cancel','reason':'Service suspended by dispatcher.'}]
    preview=client.post(PREVIEW,headers=headers,json=request)
    assert preview.status_code==200,preview.text[:400]
    assert preview.json()['changes'][0]['operation']=='cancel'
    result=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())})
    assert result.status_code==201,result.text[:400]
    successor=result.json();trip=request['patches'][0]['trip_id']
    assert next(row for row in successor['assignments'] if row['trip_id']==trip)['is_cancelled'] is True
    assert all(row['id']!=trip for row in successor['problem']['trips'])
    assert trip not in successor['verification']['unassigned_trips']
    assert next(row for row in successor['source_trips'] if row['id']==trip)['cancellation_reason']=='Service suspended by dispatcher.'
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,successor,action);assert response.status_code==200,response.text[:400];successor=response.json()
    latest=board(client,headers)
    assert latest['items'][0]['is_cancelled'] is True
    assert latest['items'][0]['cancellation_reason']=='Service suspended by dispatcher.'
    historical=board(client,headers,publication_id=request['publication_id'])
    assert historical['items'][0]['is_cancelled'] is False


def test_cancellation_requires_reason_and_does_not_accept_incompatible_fields(identity_setup):
    client,headers,revision=published_customer(identity_setup);request=request_for(client,headers,revision);trip=request['patches'][0]['trip_id']
    for patch in ({'trip_id':trip,'operation':'cancel'}, {'trip_id':trip,'operation':'cancel','reason':'   '},
                  {'trip_id':trip,'operation':'cancel','reason':'Closed','new_resource_id':'UNASSIGNED'}):
        assert client.post(PREVIEW,headers=headers,json={**request,'patches':[patch]}).status_code==422
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision


def customer_with_two_confirmed_crews(setup,overlap=False):
    from tests.integration.test_canonical_studio import prepared_customer
    from tests.integration.test_operational_snapshots import template_payload
    client,headers,template,_,_=prepared_customer(setup);origin=template['origin'];destination=template['destination']
    def create(path,data):
        response=client.post('/api/v1/'+path,headers=headers,json=data);assert response.status_code==201,response.text[:400];return response.json()
    other_driver=create('drivers',{'code':'SECOND','first_name':'Maria','last_name':'Kosta','home_station_id':origin['id']})
    other_vehicle=create('vehicles',{'code':'SECOND','registration_plate':'ZZZ-1234','bus_type':'02','home_station_id':origin['id']})
    create('pairings',{'driver_id':other_driver['id'],'vehicle_id':other_vehicle['id'],'home_station_id':origin['id'],'service_date':'2026-06-01',
        'confirm':True,'driver_version':other_driver['version'],'vehicle_version':other_vehicle['version'],'home_station_version':origin['version']})
    from tests.helpers.working_time import give_working_time
    give_working_time(client,headers,[other_driver['id']])
    create('timetables',template_payload(origin,destination,trip_code='T002',departure_time='08:15' if overlap else '10:00',arrival_time='09:15' if overlap else '11:00',arrival_day_offset=0))
    response=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'});assert response.status_code==201,response.text[:400];revision=response.json()
    first=next(resource for resource in revision['source_resources'] if resource['driver_name']=='Νίκος Δήμου')
    other=next(resource for resource in revision['source_resources'] if resource['driver_name']=='Maria Kosta')
    response=client.post('/api/v1/scheduling/revisions/'+revision['revision_id']+'/patches',headers=headers,json={'version':revision['version'],
        'patches':[{'trip_id':item['trip_id'],'new_resource_id':(other['resource_id'] if overlap and index else first['resource_id'])} for index,item in enumerate(revision['assignments'])]})
    assert response.status_code==200,response.text[:400];revision=response.json()
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,revision,action);assert response.status_code==200,response.text[:400];revision=response.json()
    return client,headers,revision,first,other


def test_replace_driver_for_selected_trip_retains_bus_with_explicit_confirmed_crew(identity_setup):
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup)
    request=request_for(client,headers,revision);trip=revision['assignments'][0]['trip_id']
    request['reviewed_not_started']=[trip]
    request['patches']=[{'trip_id':trip,'operation':'replace_driver','replacement_resource_id':other['resource_id'],
        'driver_version':other['driver_version'],'vehicle_version':first['vehicle_version'],'confirm_replacement':True}]
    preview=client.post(PREVIEW,headers=headers,json=request);assert preview.status_code==200,preview.text[:400]
    change=preview.json()['changes'][0];assert change['operation']=='replace_driver'
    result=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())});assert result.status_code==201,result.text[:400]
    successor=result.json();new_resource=next(row for row in successor['problem']['resources'] if row['resource_id']==change['new_resource_id'])
    old_resource=next(row for row in revision['problem']['resources'] if row['resource_id']==first['resource_id'])
    replacement=next(row for row in revision['problem']['resources'] if row['resource_id']==other['resource_id'])
    assert new_resource['driver_id']==replacement['driver_id'] and new_resource['bus_id']==old_resource['bus_id']
    assert next(row for row in successor['assignments'] if row['trip_id']==trip)['resource_id']==new_resource['resource_id']
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()==revision
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,successor,action);assert response.status_code==200,response.text[:400];successor=response.json()


def test_driver_replacement_requires_explicit_review_and_current_identity_versions(identity_setup):
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup);request=request_for(client,headers,revision)
    trip=revision['assignments'][0]['trip_id'];request['reviewed_not_started']=[trip]
    patch={'trip_id':trip,'operation':'replace_driver','replacement_resource_id':other['resource_id'],
        'driver_version':other['driver_version'],'vehicle_version':first['vehicle_version'],'confirm_replacement':True}
    for bad in ({**patch,'confirm_replacement':False},{**patch,'driver_version':99},{**patch,'replacement_resource_id':'unknown'}):
        assert client.post(PREVIEW,headers=headers,json={**request,'patches':[bad]}).status_code in (409,422)


def test_replace_driver_for_all_selected_trips_reuses_one_reviewed_crew(identity_setup):
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup);request=request_for(client,headers,revision)
    trips=[item['trip_id'] for item in revision['assignments']];request['reviewed_not_started']=trips
    request['patches']=[{'trip_id':trip,'operation':'replace_driver','replacement_resource_id':other['resource_id'],
        'driver_version':other['driver_version'],'vehicle_version':first['vehicle_version'],'confirm_replacement':True} for trip in trips]
    result=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())});assert result.status_code==201,result.text[:400]
    successor=result.json();assert len({item['resource_id'] for item in successor['assignments']})==1
    assert len([item for item in successor['problem']['resources'] if item['resource_id'].startswith('CREW_')])==1


def test_driver_replacement_conflict_is_visible_and_blocks_saving(identity_setup):
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup,overlap=True);request=request_for(client,headers,revision)
    trip=revision['assignments'][0]['trip_id'];request['reviewed_not_started']=[trip]
    request['patches']=[{'trip_id':trip,'operation':'replace_driver','replacement_resource_id':other['resource_id'],
        'driver_version':other['driver_version'],'vehicle_version':first['vehicle_version'],'confirm_replacement':True}]
    preview=client.post(PREVIEW,headers=headers,json=request);assert preview.status_code==200,preview.text[:400]
    assert 'RULE_DRIVER_OVERLAP' in {item['rule_id'] for item in preview.json()['verification']['violations']}
    rejected=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())})
    assert rejected.status_code==422 and rejected.json()['detail']['code']=='verification_failed'


def test_reviewed_revision_crew_has_tenant_bound_foreign_keys_and_append_only_grants(identity_setup,restricted_databases):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup);request=request_for(client,headers,revision)
    trip=revision['assignments'][0]['trip_id'];request['reviewed_not_started']=[trip]
    request['patches']=[{'trip_id':trip,'operation':'replace_driver','replacement_resource_id':other['resource_id'],
        'driver_version':other['driver_version'],'vehicle_version':first['vehicle_version'],'confirm_replacement':True}]
    response=client.post(APPLY,headers=headers,json={**request,'request_id':str(uuid.uuid4())});assert response.status_code==201,response.text[:400]
    successor=response.json();tenant=identity_setup['first'].tenant_id
    with identity_setup['owner_factory']() as db:
        row=db.execute(text('SELECT * FROM domain_revision_crews WHERE tenant_id=:tenant AND revision_id=:revision'),{'tenant':tenant,'revision':successor['revision_id']}).mappings().one()
        assert row['driver_id']==other['driver_id'] and row['vehicle_id']==first['vehicle_id'] and row['confirmed_by']>0
        with pytest.raises(DBAPIError):
            with db.begin_nested():db.execute(text('''INSERT INTO domain_revision_crews (tenant_id,revision_id,resource_id,driver_id,vehicle_id,driver_version,vehicle_version,confirmed_by,confirmed_at)
                VALUES (:tenant,:revision,'BAD',:driver,:vehicle,1,1,:actor,now())'''),{'tenant':tenant,'revision':successor['revision_id'],'driver':9999999,'vehicle':first['vehicle_id'],'actor':row['confirmed_by']})
    with restricted_databases['api'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(tenant)})
        with pytest.raises(DBAPIError):connection.execute(text('DELETE FROM domain_revision_crews'))
    with restricted_databases['worker'].begin() as connection:
        with pytest.raises(DBAPIError):connection.execute(text('SELECT * FROM domain_revision_crews'))
