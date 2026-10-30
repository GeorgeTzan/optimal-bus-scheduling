"""Failure-first regressions for the final independent foundation review."""
import pytest
from sqlalchemy import text
from tests.integration.test_identity import identity_setup, accept
from tests.integration.test_import_transactions import operator, upload
from tests.integration.test_canonical_studio import prepared_customer
from tests.integration.test_connections import following_service


def save_alias(client, headers, entity, values, target):
    batch=upload(client,headers,[values],entity).json()
    changed=client.patch('/api/v1/imports/'+batch['batch_id']+'/rows',headers=headers,json={
        'version':batch['version'],'rows':[{'row_id':batch['rows'][0]['row_id'],
        'resolution':{'mode':'existing','target_id':target['id'],'target_version':target['version']}}]})
    assert changed.status_code==200,changed.text[:500]
    committed=client.post('/api/v1/imports/'+batch['batch_id']+'/commit',headers=headers,json={'version':changed.json()['version']})
    assert committed.status_code==200,committed.text[:500]


def test_manual_generated_and_explicit_refs_reserve_archived_person_aliases(identity_setup):
    client,headers=operator(identity_setup)
    first=client.post('/api/v1/drivers',headers=headers,json={'code':'D00001','first_name':'Nikos','last_name':'Dimos'}).json()
    save_alias(client,headers,'drivers',{'code':'D00002','first_name':'Nikos','last_name':'Dimos'},first)
    assert client.patch('/api/v1/drivers/'+str(first['id']),headers=headers,json={'version':1,'is_active':False}).status_code==200
    created=client.post('/api/v1/drivers',headers=headers,json={'first_name':'Eleni','last_name':'Other'})
    assert created.status_code==201 and created.json()['code']=='D00003'
    explicit=client.post('/api/v1/drivers',headers=headers,json={'code':'D00002','first_name':'Maria','last_name':'Other'})
    assert explicit.status_code==409 and explicit.json()['detail']['code']=='reference_reserved'
    changed=client.patch('/api/v1/drivers/'+str(created.json()['id']),headers=headers,json={'version':1,'code':'D00002'})
    assert changed.status_code==409 and changed.json()['detail']['code']=='reference_reserved'


def test_vehicle_registration_and_timetable_manual_edits_cannot_reuse_import_aliases(identity_setup):
    client,headers,first,pairing,driver=prepared_customer(identity_setup)
    vehicle=client.get('/api/v1/vehicles',headers=headers).json()['items'][0]
    save_alias(client,headers,'vehicles',{'code':vehicle['code'],'registration_plate':'OLD-456','bus_type':'02'},vehicle)
    assert client.patch('/api/v1/vehicles/'+str(vehicle['id']),headers=headers,json={'version':2,'registration_plate':vehicle['registration_plate']}).status_code==200
    blocked=client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'old-456','bus_type':'02'})
    assert blocked.status_code==409 and blocked.json()['detail']['code']=='reference_reserved'
    payload={key:first[key] for key in ('departure_time','arrival_time','arrival_day_offset','operating_weekdays','valid_from','valid_until','allowed_bus_types')}
    payload.update(trip_code='HISTORICAL',origin=first['origin']['code'],destination=first['destination']['code'])
    save_alias(client,headers,'timetable',payload,first)
    second=following_service(client,headers,first)
    blocked=client.patch('/api/v1/timetables/'+str(second['id']),headers=headers,json={'version':1,'trip_code':'HISTORICAL'})
    assert blocked.status_code==409 and blocked.json()['detail']['code']=='reference_reserved'


def test_related_import_rejects_existing_alias_canonical_collision_instead_of_choosing_person(identity_setup):
    from app.domain.workforce.models import WorkforceDriver
    client,headers,first,pairing,driver=prepared_customer(identity_setup)
    save_alias(client,headers,'drivers',{'code':'ALIAS','first_name':driver['first_name'],'last_name':driver['last_name']},driver)
    with identity_setup['owner_factory']() as db:
        db.add(WorkforceDriver(tenant_id=identity_setup['first'].tenant_id,code='ALIAS',first_name='Different',last_name='Person',is_active=True,version=1));db.commit()
    vehicle=client.get('/api/v1/vehicles',headers=headers).json()['items'][0]
    batch=upload(client,headers,[{'service_date':'2026-06-02','driver_ref':'ALIAS','vehicle_ref':vehicle['code'],'home_station':first['origin']['code']}],'pairings')
    assert batch.status_code==201,batch.text[:500]
    assert batch.json()['status']=='review'
    assert any(issue['code']=='identity_conflict' for row in batch.json()['rows'] for issue in row['issues'])


def test_legacy_mixed_case_email_can_login_and_request_reset_without_rewriting_account(identity_setup):
    from db.models import User
    from app.domain.identity.models import IdentityToken
    client=identity_setup['client'];accept(client,identity_setup['first'])
    tenant=identity_setup['first'].tenant_id
    with identity_setup['owner_factory']() as db:
        user=db.query(User).filter_by(ktel_id=tenant).one();user.email='Nikos@example.org';db.commit();identifier=user.id
    for email in ('Nikos@example.org','nikos@example.org'):
        response=client.post('/auth/login',json={'email':email,'password':'StrongTenantPassword123!'})
        assert response.status_code==200,response.text[:500]
    response=client.post('/auth/password-reset/request',json={'email':'nikos@example.org'})
    assert response.status_code==202,response.text[:500]
    with identity_setup['owner_factory']() as db:
        assert db.get(User,identifier).email=='Nikos@example.org'
        assert db.query(IdentityToken).filter_by(user_id=identifier,kind='reset').count()==1


@pytest.mark.parametrize('kind',['vehicles','timetable'])
def test_related_import_refuses_vehicle_and_timetable_alias_collisions(identity_setup,kind):
    client,headers,first,pairing,driver=prepared_customer(identity_setup)
    vehicle=client.get('/api/v1/vehicles',headers=headers).json()['items'][0]
    if kind=='vehicles':
        from app.domain.fleet.models import Vehicle
        save_alias(client,headers,'vehicles',{'code':vehicle['code'],'registration_plate':'OLD-456','bus_type':'02'},vehicle)
        assert client.patch('/api/v1/vehicles/'+str(vehicle['id']),headers=headers,json={'version':2,'registration_plate':vehicle['registration_plate']}).status_code==200
        with identity_setup['owner_factory']() as db:
            db.add(Vehicle(tenant_id=identity_setup['first'].tenant_id,code='OTHER',registration_plate='OLD-456',bus_type='02',is_active=True,version=1));db.commit()
        entity='pairings';values={'service_date':'2026-06-02','driver_ref':driver['code'],'vehicle_ref':'OLD-456','home_station':first['origin']['code']}
    else:
        from app.domain.timetables.models import ServiceTemplate
        payload={key:first[key] for key in ('departure_time','arrival_time','arrival_day_offset','operating_weekdays','valid_from','valid_until','allowed_bus_types')}
        payload.update(trip_code='HISTORICAL',origin=first['origin']['code'],destination=first['destination']['code'])
        save_alias(client,headers,'timetable',payload,first)
        second=following_service(client,headers,first)
        third=following_service(client,headers,first,code='T003',departure='12:00',arrival='13:00')
        with identity_setup['owner_factory']() as db:
            db.get(ServiceTemplate,second['id']).trip_code='HISTORICAL';db.commit()
        entity='connections';values={'incoming_ref':'HISTORICAL','outgoing_ref':third['trip_code']}
    response=upload(client,headers,[values],entity)
    assert response.status_code==201,response.text[:500]
    assert response.json()['status']=='review'
    assert any(issue['code']=='identity_conflict' for row in response.json()['rows'] for issue in row['issues'])


def test_reservation_cache_expires_with_transaction_and_tenant_scope(identity_setup,restricted_databases):
    from sqlalchemy.orm import sessionmaker
    from app.domain.identity.tenant_session import set_tenant_scope
    from app.domain.resources.reference_reservations import is_reserved
    client,headers=operator(identity_setup)
    person=client.post('/api/v1/drivers',headers=headers,json={'code':'D00001','first_name':'Nikos','last_name':'Dimos'}).json()
    values={'code':'D00002','first_name':'Nikos','last_name':'Dimos'}
    save_alias(client,headers,'drivers',values,person)
    tenant=identity_setup['first'].tenant_id
    with sessionmaker(bind=restricted_databases['api'])() as db:
        set_tenant_scope(db,tenant)
        assert is_reserved(db,tenant,'drivers','D00002') is True
        assert is_reserved(db,tenant,'drivers','D00004') is False
        db.commit()
        save_alias(client,headers,'drivers',{**values,'code':'D00004'},person)
        set_tenant_scope(db,tenant)
        assert is_reserved(db,tenant,'drivers','D00004') is True
        db.commit()
        from app.domain.identity.tenant_session import CrossTenantAccessError
        other=identity_setup['second'].tenant_id
        with pytest.raises(CrossTenantAccessError):set_tenant_scope(db,other)
    with sessionmaker(bind=restricted_databases['api'])() as db:
        set_tenant_scope(db,other)
        assert is_reserved(db,other,'drivers','D00004') is False
