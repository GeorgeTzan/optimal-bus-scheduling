from datetime import datetime,timezone
import pytest
from tests.integration.test_identity import identity_setup,accept


def setup_operator(identity_setup):
    client=identity_setup['client'];headers={'Authorization':'Bearer '+accept(client,identity_setup['first']).json()['access_token']}
    def create(path,payload):
        response=client.post('/api/v1/'+path,headers=headers,json=payload)
        assert response.status_code==201,response.text
        return response.json()
    a=create('stations',{'name_el':'Αφετηρία','is_depot':True})
    b=create('stations',{'name_el':'Προορισμός'})
    driver=create('drivers',{'first_name':'Νίκος','last_name':'Δήμου','home_station_id':a['id']})
    vehicle=create('vehicles',{'registration_plate':'ABC-123','bus_type':'02','home_station_id':a['id']})
    return client,headers,create,a,b,driver,vehicle


def template_payload(a,b,**changes):
    return {'trip_code':'T001','origin_station_id':a['id'],'destination_station_id':b['id'],
        'departure_time':'23:30','arrival_time':'01:15','arrival_day_offset':1,
        'operating_weekdays':[0,1,2,3,4,5,6],'valid_from':'2026-01-01','valid_until':'2028-12-31',
        'allowed_bus_types':['02'],**changes}


def test_materialization_is_idempotent_versioned_and_preserves_old_dated_inputs(identity_setup):
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    template=create('timetables',template_payload(a,b))
    def materialize(version):
        return client.post('/api/v1/timetables/materialize',headers=headers,json={
            'service_date':'2026-12-31','template_versions':{str(template['id']):version}})
    first=materialize(1);assert first.status_code==200,first.text
    trip=first.json()['trips'][0]
    assert trip['duration_minutes']==105
    assert trip['end_utc'].startswith('2026-12-31T23:15:00')
    assert materialize(1).json()['trips'][0]['id']==trip['id']
    changed=client.patch('/api/v1/timetables/'+str(template['id']),headers=headers,json={'version':1,'arrival_time':'01:30'})
    assert changed.status_code==200 and changed.json()['version']==2
    assert materialize(1).status_code==409
    current=materialize(2).json()['trips'][0]
    assert current['id']!=trip['id'] and current['duration_minutes']==120
    from app.domain.timetables.models import TripInstance
    with identity_setup['owner_factory']() as db:
        original=db.get(TripInstance,trip['id'])
        assert original.end_utc.astimezone(timezone.utc).hour==23 and original.end_utc.minute==15
        assert original.source_hash==trip['source_hash']
    create('timetables/'+str(template['id'])+'/exceptions',{'service_date':'2026-12-31','action':'cancel'})
    assert materialize(2).json()['trips']==[]


def test_dst_choice_is_explicit_dated_and_survives_reload(identity_setup):
    client,headers,create,a,b,_,_=setup_operator(identity_setup)
    template=create('timetables',template_payload(a,b,departure_time='03:10',arrival_time='03:40',arrival_day_offset=0))
    payload={'service_date':'2026-10-25','template_versions':{str(template['id']):1}}
    before=client.post('/api/v1/timetables/materialize',headers=headers,json=payload)
    assert before.status_code==422,before.text
    assert before.json()['detail']['issues'][0]['code']=='ambiguous_local_time'
    assert {issue['field'] for issue in before.json()['detail']['issues']}=={'departure_time','arrival_time'}
    create('timetables/'+str(template['id'])+'/exceptions',{'service_date':'2026-10-25','action':'inherit','fold_start':0,'fold_end':1})
    after=client.post('/api/v1/timetables/materialize',headers=headers,json=payload)
    assert after.status_code==200 and after.json()['trips'][0]['duration_minutes']==90
    again=client.post('/api/v1/timetables/materialize',headers=headers,json=payload)
    assert again.json()['trips'][0]['id']==after.json()['trips'][0]['id']
    gap=client.post('/api/v1/timetables/materialize',headers=headers,json={**payload,'service_date':'2026-03-29'})
    assert gap.status_code==422 and gap.json()['detail']['issues'][0]['code']=='nonexistent_local_time'


def test_pairings_and_transfer_inputs_are_real_and_tenant_scoped(identity_setup):
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    from tests.helpers.working_time import give_working_time;give_working_time(client,headers)
    template=create('timetables',template_payload(a,b,departure_time='08:00',arrival_time='09:00',arrival_day_offset=0))
    pairing=create('pairings',{'driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
        'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    assert pairing['is_confirmed'] is True and pairing['needs_review'] is False
    other=create('drivers',{'first_name':'Other','last_name':'Driver'})
    duplicate=client.post('/api/v1/pairings',headers=headers,json={'driver_id':other['id'],'vehicle_id':vehicle['id'],
        'home_station_id':a['id'],'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    assert duplicate.status_code==409
    for origin,destination,minutes in [(a,b,30),(b,a,35)]:
        create('transfers',{'origin_station_id':origin['id'],'destination_station_id':destination['id'],'minutes':minutes})
    from app.domain.timetables.operations import build_operational_snapshot
    from app.domain.optimization.adapter import to_cv_problem
    with identity_setup['owner_factory']() as db:
        source=build_operational_snapshot(db,identity_setup['first'].tenant_id,'2026-06-01')
        problem=to_cv_problem(source)
        assert problem.resources[0].bus_type=='02'
        assert problem.trips[0].allowed_bus_types==('02',)
        assert source.source_data['resources'][0]['driver_name']=='Νίκος Δήμου'
        assert problem.transfer_matrix==((0,30),(35,0))
    other_headers={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert client.get('/api/v1/pairings?service_date=2026-06-01',headers=other_headers).json()['items']==[]
    assert client.post('/api/v1/pairings',headers=other_headers,json={'driver_id':driver['id'],'vehicle_id':vehicle['id'],
        'home_station_id':a['id'],'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1}).status_code==422


def test_new_operational_tables_enforce_rls_and_composite_references(restricted_databases):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.exc import DBAPIError
    from db.models import User
    from app.domain.fleet.models import Vehicle
    from app.domain.timetables.models import Station
    with sessionmaker(bind=restricted_databases['owner'])() as db:
        for tenant,identifier in [(1,11),(2,22)]:
            db.add(Station(id=identifier,tenant_id=tenant,code='BASE',name_el='Base',name_en='Base'))
            db.add(Vehicle(id=identifier,tenant_id=tenant,code='BUS',registration_plate='BUS',bus_type='02'))
            db.add(User(id=identifier,ktel_id=tenant,email=f'boundary{tenant}@example.org',hashed_password='not-a-login',is_active=True))
        db.commit()
    with restricted_databases['api'].begin() as connection:
        for table in ('domain_service_exceptions','domain_daily_pairings','domain_station_transfers'):
            assert connection.execute(text(f'SELECT count(*) FROM {table}')).scalar_one()==0
        connection.execute(text("SELECT set_config('app.tenant_id','1',true)"))
        for driver,vehicle,home in [(22,11,11),(11,22,11),(11,11,22)]:
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text('''INSERT INTO domain_daily_pairings
                        (tenant_id,service_date,driver_id,vehicle_id,home_station_id,is_active,is_confirmed,version,created_at)
                        VALUES (1,'2026-06-01',:driver,:vehicle,:home,true,false,1,now())'''),
                        {'driver':driver,'vehicle':vehicle,'home':home})
        connection.execute(text('''INSERT INTO domain_daily_pairings
            (tenant_id,service_date,driver_id,vehicle_id,home_station_id,is_active,is_confirmed,version,created_at)
            VALUES (1,'2026-06-01',11,11,11,true,false,1,now())'''))
        connection.execute(text("SELECT set_config('app.tenant_id','2',true)"))
        assert connection.execute(text('SELECT count(*) FROM domain_daily_pairings')).scalar_one()==0


def test_materialization_is_atomic_when_one_service_needs_dst_review(identity_setup):
    from app.domain.timetables.models import TripInstance
    client,headers,create,a,b,_,_=setup_operator(identity_setup)
    first=create('timetables',template_payload(a,b,departure_time='08:00',arrival_time='09:00',arrival_day_offset=0))
    second=create('timetables',template_payload(a,b,trip_code='DST',departure_time='03:10',arrival_time='03:40',arrival_day_offset=0))
    response=client.post('/api/v1/timetables/materialize',headers=headers,json={'service_date':'2026-10-25',
        'template_versions':{str(first['id']):1,str(second['id']):1}})
    assert response.status_code==422
    with identity_setup['owner_factory']() as db:
        assert db.query(TripInstance).filter_by(tenant_id=identity_setup['first'].tenant_id).count()==0


def test_pairing_review_depends_on_planning_changes_and_copy_needs_confirmation(identity_setup):
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    pair=create('pairings',{'driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
        'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    assert client.patch('/api/v1/drivers/'+str(driver['id']),headers=headers,json={'version':1,'phone':'2101234567'}).status_code==200
    assert client.get('/api/v1/pairings?service_date=2026-06-01',headers=headers).json()['items'][0]['needs_review'] is False
    assert client.patch('/api/v1/vehicles/'+str(vehicle['id']),headers=headers,json={'version':1,'bus_type':'03'}).status_code==200
    assert client.get('/api/v1/pairings?service_date=2026-06-01',headers=headers).json()['items'][0]['needs_review'] is True
    copied=client.post('/api/v1/pairings/copy',headers=headers,json={'from_date':'2026-06-01','to_date':'2026-06-02'})
    assert copied.status_code==201,copied.text
    assert copied.json()['items'][0]['is_confirmed'] is False
    assert copied.json()['items'][0]['needs_review'] is True
    assert client.post('/api/v1/pairings/copy',headers=headers,json={'from_date':'2026-06-01','to_date':'2026-06-02'}).status_code==409


def test_explicit_cancellation_can_exclude_a_legacy_calendar_needing_review(identity_setup):
    from app.domain.timetables.models import ServiceTemplate
    client,headers,create,a,b,_,_=setup_operator(identity_setup)
    template=create('timetables',template_payload(a,b))
    with identity_setup['owner_factory']() as db:
        db.get(ServiceTemplate,template['id']).operating_weekdays=None;db.commit()
    create('timetables/'+str(template['id'])+'/exceptions',{'service_date':'2026-06-01','action':'cancel'})
    response=client.post('/api/v1/timetables/materialize',headers=headers,json={'service_date':'2026-06-01','template_versions':{str(template['id']):1}})
    assert response.status_code==200 and response.json()['trips']==[]


def test_empty_patch_cannot_silently_unconfirm_a_pairing(identity_setup):
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    row=create('pairings',{'driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
        'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    response=client.patch('/api/v1/pairings/'+str(row['id']),headers=headers,json={'version':1})
    assert response.status_code==422,response.text
    current=client.get('/api/v1/pairings?service_date=2026-06-01',headers=headers).json()['items'][0]
    assert current['version']==1 and current['is_confirmed'] is True


def test_snapshot_provenance_includes_transfer_changes_and_keeps_old_inputs(identity_setup):
    from app.domain.timetables.operations import build_operational_snapshot
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    from tests.helpers.working_time import give_working_time;give_working_time(client,headers)
    create('timetables',template_payload(a,b,departure_time='08:00',arrival_time='09:00',arrival_day_offset=0))
    create('pairings',{'driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
        'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    forward=create('transfers',{'origin_station_id':a['id'],'destination_station_id':b['id'],'minutes':30,'source_note':'Test operator note'})
    create('transfers',{'origin_station_id':b['id'],'destination_station_id':a['id'],'minutes':35})
    with identity_setup['owner_factory']() as db:
        original=build_operational_snapshot(db,identity_setup['first'].tenant_id,'2026-06-01');db.commit()
    change=client.patch('/api/v1/transfers/'+str(forward['id']),headers=headers,json={'version':1,'minutes':45})
    assert change.status_code==200,change.text
    with identity_setup['owner_factory']() as db:
        current=build_operational_snapshot(db,identity_setup['first'].tenant_id,'2026-06-01')
    assert original.snapshot_hash!=current.snapshot_hash
    assert original.source_data['transfers'][0]['minutes']==30
    assert current.source_data['transfers'][0]['minutes']==45
    assert change.json()['source_note']=='Test operator note'


def test_tenant_audit_covers_new_operational_relationships(restricted_databases):
    from sqlalchemy import inspect,text
    from db.tenant_schema import audit_database_tenancy
    with restricted_databases['owner'].begin() as connection:
        key=next(fk for fk in inspect(connection).get_foreign_keys('domain_daily_pairings') if fk['constrained_columns']==['tenant_id','driver_id'])
        quoted=connection.dialect.identifier_preparer.quote(key['name'])
        connection.execute(text(f'ALTER TABLE domain_daily_pairings DROP CONSTRAINT {quoted}'))
        issues=audit_database_tenancy(connection)
        assert any('domain_daily_pairings' in issue and 'foreign key' in issue for issue in issues),issues


def test_audit_rejects_policy_that_mentions_tenant_function_but_allows_every_row(restricted_databases):
    from sqlalchemy import text
    from db.tenant_schema import audit_database_tenancy
    with restricted_databases['owner'].begin() as connection:
        connection.execute(text('DROP POLICY tenant_isolation ON domain_drivers'))
        connection.execute(text('''CREATE POLICY tenant_isolation ON domain_drivers FOR ALL
            USING(tenant_id=public.ktel_current_tenant() OR true)
            WITH CHECK(tenant_id=public.ktel_current_tenant() OR true)'''))
        issues=audit_database_tenancy(connection)
        assert any('domain_drivers' in issue and 'policy' in issue for issue in issues),issues


def test_day_readiness_is_read_only_and_reports_actual_saved_inputs(identity_setup):
    from app.domain.timetables.models import TripInstance
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    from tests.helpers.working_time import give_working_time;give_working_time(client,headers)
    template=create('timetables',template_payload(a,b,departure_time='08:00',arrival_time='09:00',arrival_day_offset=0))
    create('pairings',{'driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
        'service_date':'2026-06-01','confirm':True,'driver_version':1,'vehicle_version':1,'home_station_version':1})
    url='/api/v1/setup/readiness?service_date=2026-06-01'
    incomplete=client.get(url,headers=headers)
    assert incomplete.status_code==200,incomplete.text
    assert incomplete.json()['inputs_ready'] is False
    assert len(incomplete.json()['missing_transfers'])==2
    for origin,destination,minutes in [(a,b,30),(b,a,35)]:
        create('transfers',{'origin_station_id':origin['id'],'destination_station_id':destination['id'],'minutes':minutes})
    ready=client.get(url,headers=headers).json()
    assert ready['inputs_ready'] is True and ready['day_prepared'] is False
    assert ready['timezone']=='Europe/Athens'
    with identity_setup['owner_factory']() as db:
        assert db.query(TripInstance).filter_by(tenant_id=identity_setup['first'].tenant_id).count()==0
    prepared=client.post('/api/v1/timetables/materialize',headers=headers,json={'service_date':'2026-06-01','template_versions':{str(template['id']):1}})
    assert prepared.status_code==200
    assert client.get(url,headers=headers).json()['day_prepared'] is True
    saved=client.get('/api/v1/timetables/dated-trips?service_date=2026-06-01',headers=headers)
    assert saved.status_code==200,saved.text
    assert saved.json()['items'][0]['departure_local']=='08:00'
    assert saved.json()['items'][0]['arrival_local']=='09:00'


def test_travel_time_batch_is_atomic_and_reports_only_persisted_rows(identity_setup):
    from app.domain.timetables.models import StationTransfer
    client,headers,create,a,b,_,_=setup_operator(identity_setup)
    items=[{'origin_station_id':a['id'],'destination_station_id':b['id'],'minutes':30},
           {'origin_station_id':b['id'],'destination_station_id':a['id'],'minutes':35}]
    duplicated=client.post('/api/v1/transfers/batch',headers=headers,json={'items':[items[0],items[0]]})
    assert duplicated.status_code==409,duplicated.text
    with identity_setup['owner_factory']() as db:
        assert db.query(StationTransfer).filter_by(tenant_id=identity_setup['first'].tenant_id).count()==0
    saved=client.post('/api/v1/transfers/batch',headers=headers,json={'items':items})
    assert saved.status_code==201 and len(saved.json()['items'])==2


def test_upcoming_pairing_blocks_resource_archive_until_removed(identity_setup):
    from datetime import date,timedelta
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    future=(date.today()+timedelta(days=7)).isoformat()
    pairing=create('pairings',{'service_date':future,'driver_id':driver['id'],'vehicle_id':vehicle['id'],
        'home_station_id':b['id'],'driver_version':1,'vehicle_version':1,'home_station_version':1,'confirm':True})
    for kind,row in [('drivers',driver),('vehicles',vehicle),('stations',b)]:
        response=client.patch(f"/api/v1/{kind}/{row['id']}",headers=headers,json={'version':1,'is_active':False})
        assert response.status_code==409,response.text
        assert response.json()['detail']['code']=='upcoming_pairings'
    removed=client.patch(f"/api/v1/pairings/{pairing['id']}",headers=headers,json={'version':1,'is_active':False})
    assert removed.status_code==200,removed.text
    for kind,row in [('drivers',driver),('vehicles',vehicle),('stations',b)]:
        response=client.patch(f"/api/v1/{kind}/{row['id']}",headers=headers,json={'version':1,'is_active':False})
        assert response.status_code==200,response.text


def test_operational_permissions_and_foreign_templates_are_enforced(identity_setup):
    from app.domain.identity.service import issue_invitation
    client,headers,create,a,b,driver,vehicle=setup_operator(identity_setup)
    template=create('timetables',template_payload(a,b))
    with identity_setup['owner_factory']() as db:
        invitation=issue_invitation(db,identity_setup['first'].tenant_id,'viewer-operations@example.org','viewer')
        db.commit()
    viewer={'Authorization':'Bearer '+accept(client,invitation).json()['access_token']}
    assert client.get('/api/v1/timetables',headers=viewer).status_code==200
    writes=[('/timetables',template_payload(a,b)),('/timetables/materialize',{'service_date':'2026-06-01','template_versions':{str(template['id']):1}}),
        ('/pairings',{'service_date':'2026-06-01','driver_id':driver['id'],'vehicle_id':vehicle['id'],'home_station_id':a['id'],
            'driver_version':1,'vehicle_version':1,'home_station_version':1,'confirm':True}),
        ('/transfers/batch',{'items':[{'origin_station_id':a['id'],'destination_station_id':b['id'],'minutes':30}]}),
        (f"/timetables/{template['id']}/exceptions",{'service_date':'2026-06-01','action':'cancel'})]
    for path,payload in writes:
        response=client.post('/api/v1'+path,headers=viewer,json=payload)
        assert response.status_code==403,response.text
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert client.get(f"/api/v1/timetables/{template['id']}",headers=foreign).status_code==404
    assert client.patch(f"/api/v1/timetables/{template['id']}",headers=foreign,json={'version':1,'trip_code':'FOREIGN'}).status_code==404
    assert client.post(f"/api/v1/timetables/{template['id']}/exceptions",headers=foreign,json={'service_date':'2026-06-01','action':'cancel'}).status_code==404
    assert client.post('/api/v1/timetables',headers=foreign,json=template_payload(a,b)).status_code==422
