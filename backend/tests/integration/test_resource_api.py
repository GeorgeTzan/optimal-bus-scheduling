"""Canonical operational records through restricted PostgreSQL API roles."""
from tests.integration.test_identity import identity_setup,accept


def administrator(identity_setup,which='first'):
    response=accept(identity_setup['client'],identity_setup[which])
    return {'Authorization':'Bearer '+response.json()['access_token']}


def test_resources_are_real_versioned_and_tenant_scoped(identity_setup):
    client=identity_setup['client'];headers=administrator(identity_setup)
    station=client.post('/api/v1/stations',headers=headers,json={'name_el':'Κόρινθος','is_depot':True})
    assert station.status_code==201,station.text
    home=station.json()
    driver=client.post('/api/v1/drivers',headers=headers,json={'first_name':'Νίκος','last_name':'Δήμου','home_station_id':home['id']})
    assert driver.status_code==201,driver.text
    person=driver.json();assert person['code'] and person['version']==1
    vehicle=client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'ΚΡΑ-1234','bus_type':'01','home_station_id':home['id']})
    assert vehicle.status_code==201,vehicle.text
    assert vehicle.json()['capacity'] is None
    changed=client.patch('/api/v1/drivers/'+str(person['id']),headers=headers,json={'version':1,'phone':'2101234567'})
    assert changed.status_code==200 and changed.json()['version']==2
    stale=client.patch('/api/v1/drivers/'+str(person['id']),headers=headers,json={'version':1,'phone':'other'})
    assert stale.status_code==409
    listing=client.get('/api/v1/drivers?q=Νίκος&page_size=1',headers=headers)
    assert listing.status_code==200 and listing.json()['total']==1
    assert listing.json()['items'][0]['phone']=='2101234567'
    assert listing.json()['items'][0]['home_station']['name_el']=='Κόρινθος'
    other=administrator(identity_setup,'second')
    assert client.get('/api/v1/drivers/'+str(person['id']),headers=other).status_code==404
    assert client.post('/api/v1/drivers',headers=other,json={'first_name':'Other','last_name':'Person','home_station_id':home['id']}).status_code==422
    assert client.get('/api/v1/drivers',headers=other).json()['total']==0


def test_resource_validation_and_readiness_do_not_invent_data(identity_setup):
    client=identity_setup['client'];headers=administrator(identity_setup)
    before=client.get('/api/v1/setup/readiness',headers=headers)
    assert before.status_code==200,before.text
    assert before.json()['drivers']==0 and before.json()['can_generate_draft'] is False
    for payload in ({'first_name':' ','last_name':'Name'},{'first_name':'A','last_name':'B','tenant_id':999}):
        assert client.post('/api/v1/drivers',headers=headers,json=payload).status_code==422
    first=client.post('/api/v1/drivers',headers=headers,json={'code':'001','first_name':'A','last_name':'B'})
    assert first.status_code==201
    assert client.post('/api/v1/drivers',headers=headers,json={'code':'001','first_name':'C','last_name':'D'}).status_code==409
    assert client.patch('/api/v1/drivers/'+str(first.json()['id']),headers=headers,json={'version':1,'first_name':None}).status_code==422
    assert client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'ABC123','bus_type':'01','capacity':-3}).status_code==422
    assert client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'ABC123'}).status_code==422
    only_reference=client.post('/api/v1/vehicles',headers=headers,json={'code':'Bus A','bus_type':'02'})
    assert only_reference.status_code==201 and only_reference.json()['registration_plate'] is None
    assert client.get('/api/v1/setup/readiness',headers=headers).json()['drivers']==1
    archived=client.patch('/api/v1/drivers/'+str(first.json()['id']),headers=headers,json={'version':1,'is_active':False})
    assert archived.status_code==200
    assert client.get('/api/v1/drivers?active_only=true',headers=headers).json()['total']==0
    assert client.get('/api/v1/setup/readiness',headers=headers).json()['drivers']==0


def test_resource_permissions_are_enforced_on_server(identity_setup):
    from app.domain.identity.service import issue_invitation
    client=identity_setup['client'];invite=identity_setup['first']
    with identity_setup['owner_factory']() as db:
        viewer=issue_invitation(db,invite.tenant_id,'viewer-resource@example.org','viewer');db.commit()
    headers={'Authorization':'Bearer '+accept(client,viewer).json()['access_token']}
    assert client.get('/api/v1/drivers',headers=headers).status_code==200
    assert client.post('/api/v1/drivers',headers=headers,json={'first_name':'A','last_name':'B'}).status_code==403
    assert client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'ABC123','bus_type':'01'}).status_code==403


def test_station_archive_checks_and_concurrent_versions(identity_setup):
    from concurrent.futures import ThreadPoolExecutor
    client=identity_setup['client'];headers=administrator(identity_setup)
    station=client.post('/api/v1/stations',headers=headers,json={'name_el':'Depot'}).json()
    driver=client.post('/api/v1/drivers',headers=headers,json={'first_name':'First','last_name':'Driver','home_station_id':station['id']}).json()
    assert client.patch('/api/v1/stations/'+str(station['id']),headers=headers,json={'version':1,'is_active':False}).status_code==409
    def change(name):
        return client.patch('/api/v1/drivers/'+str(driver['id']),headers=headers,json={'version':1,'first_name':name}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(change,['First edit','Second edit']))==[200,409]
    assert client.patch('/api/v1/drivers/'+str(driver['id']),headers=headers,json={'version':2,'home_station_id':None}).status_code==200
    assert client.patch('/api/v1/stations/'+str(station['id']),headers=headers,json={'version':1,'is_active':False}).status_code==200
    response=client.post('/api/v1/vehicles',headers=headers,json={'registration_plate':'ABC123','bus_type':'01','home_station_id':station['id']})
    assert response.status_code==422


def test_station_used_by_active_timetable_cannot_be_archived(identity_setup):
    from app.domain.timetables.models import Route,ServiceTemplate
    client=identity_setup['client'];headers=administrator(identity_setup)
    a=client.post('/api/v1/stations',headers=headers,json={'name_el':'Origin'}).json()
    b=client.post('/api/v1/stations',headers=headers,json={'name_el':'Destination'}).json()
    with identity_setup['owner_factory']() as db:
        route=Route(tenant_id=identity_setup['first'].tenant_id,origin_station_id=a['id'],destination_station_id=b['id'])
        db.add(route);db.flush()
        db.add(ServiceTemplate(tenant_id=identity_setup['first'].tenant_id,route_id=route.id,trip_code='T1',departure_time='08:00',arrival_time='09:00',is_active=True));db.commit()
    response=client.patch('/api/v1/stations/'+str(a['id']),headers=headers,json={'version':1,'is_active':False})
    assert response.status_code==409,response.text
    assert response.json()['detail']['code']=='station_timetable_in_use'


def test_resource_natural_identity_is_enforced_by_database(restricted_databases):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    with restricted_databases['api'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id','1',true)"))
        connection.execute(text("INSERT INTO domain_vehicles(tenant_id,code,registration_plate,bus_type) VALUES (1,'A','abc123','01')"))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("INSERT INTO domain_vehicles(tenant_id,code,registration_plate,bus_type) VALUES (1,'B','ABC123','01')"))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("INSERT INTO domain_vehicles(tenant_id,code,bus_type,external_source) VALUES (1,'C','01','source-only')"))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("UPDATE domain_vehicles SET version=0 WHERE code='A'"))
