from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.integration.test_platform_access import platform_setup
from tests.integration.test_platform_customers import accept,operator_client

HEALTH_COLUMNS=['tenant_id','last_sign_in','drivers','vehicles','timetables','published_days_30d','solver_failed_7d','mail_failed_7d','uncovered_share_latest']
NOW=datetime.now(timezone.utc).replace(microsecond=0)


def days_ago(days):
    return NOW-timedelta(days=days)


def insert(connection,table,rows):
    for row in rows:
        names=','.join(row)
        values=','.join(':'+name for name in row)
        connection.execute(text(f'INSERT INTO {table}({names}) VALUES ({values})'),row)


def seed_busy_tenant(owner,tenant):
    with owner.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role=replica"))
        insert(connection,'domain_drivers',[{'tenant_id':tenant,'code':f'H{i}','first_name':'N','last_name':'N','is_active':active} for i,active in enumerate((True,True,True,False))])
        insert(connection,'domain_vehicles',[{'tenant_id':tenant,'code':f'V{i}','bus_type':'coach','is_active':active} for i,active in enumerate((True,True,False))])
        insert(connection,'domain_service_templates',[{'tenant_id':tenant,'route_id':1,'trip_code':f'T{i}','departure_time':'08:00','arrival_time':'09:00','is_active':active} for i,active in enumerate((True,True,True,True,False))])
        connection.execute(text("INSERT INTO domain_scheduling_periods(id,tenant_id,name,start_date,end_date) VALUES (:id,:t,'p','2026-01-01','2026-12-31')"),{'id':tenant*10,'t':tenant})
        insert(connection,'domain_schedule_revisions',[{'revision_id':f'{tenant}-{name}','tenant_id':tenant,'period_id':tenant*10,'version':1,'status':status,'author':'a'}
                                                       for name,status in (('old','published'),('latest','published'),('earlier','published'),('draft','draft'))])
        insert(connection,'domain_revision_snapshots',[{'revision_id':f'{tenant}-{name}','tenant_id':tenant,'problem_data':'{}','source_data':'{"source":"operational"}'} for name in ('old','latest','earlier')])
        insert(connection,'domain_publications',[{'publication_id':f'{tenant}-pub-{name}','tenant_id':tenant,'revision_id':f'{tenant}-{name}','published_by':'a','verification_report':'{}','published_at':(NOW-timedelta(days=age)).replace(tzinfo=None)}
                                                 for name,age in (('old',40),('latest',2),('earlier',5))])
        assignments=[('latest',f'a{i}','R1',False) for i in range(4)]+[('latest','u1','UNASSIGNED',False),('latest','c1','UNASSIGNED',True)]+[('earlier',f'b{i}','UNASSIGNED',False) for i in range(3)]
        insert(connection,'domain_revision_assignments',[{'tenant_id':tenant,'revision_id':f'{tenant}-{rev}','trip_id':trip,'resource_id':resource,'start_minutes':0,'end_minutes':1,'start_station':'A','end_station':'B','is_locked':False,'is_cancelled':cancelled,'cancellation_reason':'x' if cancelled else None} for rev,trip,resource,cancelled in assignments])
        insert(connection,'domain_jobs',[{'job_id':f'{tenant}-j{i}','tenant_id':tenant,'snapshot_id':'s','solver_version':'v','attempt_token':0,'status':status,'created_at':(NOW-timedelta(days=age)).replace(tzinfo=None),'updated_at':(NOW-timedelta(days=age)).replace(tzinfo=None)}
                                         for i,(status,age) in enumerate((('failed',1),('failed',6),('failed',10),('completed',1),('cancelled',1)))])
        insert(connection,'domain_identity_tokens',[{'id':f'{tenant}-tok','tenant_id':tenant,'token_hash':f'{tenant}-hash','kind':'invitation','email':'x@example.org','role':'viewer','expires_at':NOW,'created_at':NOW}])
        insert(connection,'domain_email_outbox',[{'id':f'{tenant}-m{i}','tenant_id':tenant,'identity_token_id':f'{tenant}-tok','kind':'invitation','encrypted_payload':'x','delivery_status':status,'attempts':1,'attempt_token':0,'created_at':NOW-timedelta(days=age)}
                                                 for i,(status,age) in enumerate((('failed',1),('failed',3),('failed',9),('sent',1),('queued',1)))])


def health(engine):
    with engine.connect() as connection:
        result=connection.execute(text('SELECT * FROM public.platform_customer_health()'))
        rows=[dict(row) for row in result.mappings()]
        return list(result.keys()),{row['tenant_id']:row for row in rows}


def test_counts_are_exact_for_a_busy_tenant(platform_setup):
    tenant=platform_setup['first'].tenant_id
    seed_busy_tenant(platform_setup['owner'],tenant)
    accept(platform_setup['first'].token)
    with platform_setup['owner'].begin() as connection:
        connection.execute(text('UPDATE domain_auth_sessions SET created_at=:at WHERE tenant_id=:t'),{'at':days_ago(3),'t':tenant})
    columns,rows=health(platform_setup['platform'])
    row=rows[tenant]
    assert columns==HEALTH_COLUMNS
    assert (row['drivers'],row['vehicles'],row['timetables'],row['published_days_30d'],row['solver_failed_7d'],row['mail_failed_7d'])==(3,2,4,2,2,2)
    assert float(row['uncovered_share_latest'])==pytest.approx(0.2)
    assert row['last_sign_in']==days_ago(3)


def test_empty_tenant_reports_zeros_and_no_sign_in(platform_setup):
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("INSERT INTO ktels(id,name) VALUES (900,'Empty')"))
    _,rows=health(platform_setup['platform'])
    row=rows[900]
    assert (row['drivers'],row['vehicles'],row['timetables'],row['published_days_30d'],row['solver_failed_7d'],row['mail_failed_7d'])==(0,)*6
    assert row['last_sign_in'] is None and row['uncovered_share_latest'] is None


def test_function_exposes_aggregates_without_names_or_emails(platform_setup):
    columns,_=health(platform_setup['platform'])
    assert columns==HEALTH_COLUMNS
    assert not [name for name in columns if any(word in name for word in ('name','email','trip','code','plate'))]


def test_one_tenant_never_includes_anothers_numbers(platform_setup):
    first,second=platform_setup['first'].tenant_id,platform_setup['second'].tenant_id
    seed_busy_tenant(platform_setup['owner'],first)
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role=replica"))
        insert(connection,'domain_drivers',[{'tenant_id':second,'code':'S1','first_name':'N','last_name':'N','is_active':True}])
        insert(connection,'domain_jobs',[{'job_id':'second-j','tenant_id':second,'snapshot_id':'s','solver_version':'v','attempt_token':0,'status':'failed','created_at':NOW.replace(tzinfo=None),'updated_at':NOW.replace(tzinfo=None)}])
    _,rows=health(platform_setup['platform'])
    assert (rows[second]['drivers'],rows[second]['vehicles'],rows[second]['solver_failed_7d'],rows[second]['mail_failed_7d'],rows[second]['published_days_30d'])==(1,0,1,0,0)
    assert rows[second]['uncovered_share_latest'] is None
    assert (rows[first]['drivers'],rows[first]['solver_failed_7d']) == (3,2)


def test_panel_role_still_cannot_read_tenant_tables(platform_setup):
    with platform_setup['platform'].begin() as connection:
        for table in ('domain_drivers','domain_vehicles','domain_service_templates','domain_schedule_revisions','domain_publications','domain_revision_assignments','domain_jobs','domain_email_outbox','domain_auth_sessions'):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(f'SELECT count(*) FROM {table}'))
        assert connection.execute(text('SELECT count(*) FROM public.platform_customer_health()')).scalar_one()>=4
    for engine in (platform_setup['api'],platform_setup['worker']):
        with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text('SELECT * FROM public.platform_customer_health()'))


def test_endpoints_return_health_for_one_customer_and_in_the_list(platform_setup):
    tenant=platform_setup['first'].tenant_id
    seed_busy_tenant(platform_setup['owner'],tenant)
    client,_=operator_client(platform_setup)
    single=client.get(f'/api/v1/platform/customers/{tenant}/health')
    assert single.status_code==200,single.text
    body=single.json()
    assert set(body)==set(HEALTH_COLUMNS)
    assert (body['drivers'],body['vehicles'],body['timetables'],body['published_days_30d'],body['solver_failed_7d'],body['mail_failed_7d'])==(3,2,4,2,2,2)
    assert body['uncovered_share_latest']==pytest.approx(0.2)
    listed={customer['id']:customer for customer in client.get('/api/v1/platform/customers').json()}
    assert listed[tenant]['health']==body
    assert listed[platform_setup['second'].tenant_id]['health']['drivers']==0
    assert client.get('/api/v1/platform/customers/999999/health').status_code==404


def test_health_endpoints_need_an_operator_session(platform_setup):
    tenant,bearer=accept(platform_setup['first'].token)
    client=platform_setup['client']
    client.cookies.clear()
    assert client.get(f"/api/v1/platform/customers/{platform_setup['first'].tenant_id}/health").status_code==401
    assert tenant.get(f"/api/v1/platform/customers/{platform_setup['first'].tenant_id}/health").status_code==401


def test_uncovered_share_ignores_publications_that_are_not_operational(platform_setup):
    tenant=platform_setup['first'].tenant_id
    seed_busy_tenant(platform_setup['owner'],tenant)
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role=replica"))
        insert(connection,'domain_schedule_revisions',[{'revision_id':f'{tenant}-ref','tenant_id':tenant,'period_id':tenant*10,'version':1,'status':'published','author':'a'}])
        insert(connection,'domain_revision_snapshots',[{'revision_id':f'{tenant}-ref','tenant_id':tenant,'problem_data':'{}','source_data':'{"source":"reference"}'}])
        insert(connection,'domain_publications',[{'publication_id':f'{tenant}-pub-ref','tenant_id':tenant,'revision_id':f'{tenant}-ref','published_by':'a','verification_report':'{}','published_at':(NOW-timedelta(days=1)).replace(tzinfo=None)}])
        insert(connection,'domain_revision_assignments',[{'tenant_id':tenant,'revision_id':f'{tenant}-ref','trip_id':'r1','resource_id':'UNASSIGNED','start_minutes':0,'end_minutes':1,'start_station':'A','end_station':'B','is_locked':False,'is_cancelled':False,'cancellation_reason':None}])
    _,rows=health(platform_setup['platform'])
    assert float(rows[tenant]['uncovered_share_latest'])==pytest.approx(0.2)
