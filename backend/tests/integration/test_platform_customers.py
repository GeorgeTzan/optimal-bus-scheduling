from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from main import app
from db.tenant_schema import PLATFORM_FUNCTIONS
from tests.integration.test_platform_access import platform_setup,sign_in

TENANT_PASSWORD='StrongTenantPassword123!'


def operator_client(setup):
    client=setup['client']
    assert sign_in(client,setup['secret']).status_code==204
    return client,{'X-CSRF-Token':client.cookies.get('ktel_platform_csrf')}


def accept(token):
    client=TestClient(app)
    response=client.post('/auth/accept-invitation',json={'token':token,'password':TENANT_PASSWORD,'full_name':'KTEL administrator'})
    assert response.status_code==200,response.text
    return client,{'Authorization':'Bearer '+response.json()['access_token']}


def ktel(owner,tenant_id):
    with owner.connect() as connection:
        return connection.execute(text('SELECT * FROM ktels WHERE id=:id'),{'id':tenant_id}).mappings().first()


def actions(owner):
    with owner.connect() as connection:
        return connection.execute(text('SELECT action FROM platform_audit ORDER BY id')).scalars().all()


def test_panel_creates_customer_whose_first_admin_can_accept(platform_setup):
    client,csrf=operator_client(platform_setup)
    body={'name':'  Panel KTEL  ','region':'Crete','timezone':'Europe/Athens','status':'trial','trial_ends_on':'2026-12-31','admin_email':'Boss@Example.org'}
    assert client.post('/api/v1/platform/customers',json=body).status_code==403
    created=client.post('/api/v1/platform/customers',json=body,headers=csrf)
    assert created.status_code==201,created.text
    assert created.headers['cache-control']=='no-store'
    data=created.json()
    link=data['invitation_link']
    assert '#token=' in link
    row=ktel(platform_setup['owner'],data['id'])
    assert (row['name'],row['region'],row['status'],str(row['trial_ends_on']))==('Panel KTEL','Crete','trial','2026-12-31')
    with platform_setup['owner'].connect() as connection:
        token=connection.execute(text('SELECT email,role,kind,token_hash FROM domain_identity_tokens WHERE tenant_id=:id'),{'id':data['id']}).mappings().one()
        outbox=connection.execute(text('SELECT kind,encrypted_payload FROM domain_email_outbox WHERE tenant_id=:id'),{'id':data['id']}).mappings().one()
    secret=link.split('#token=')[1]
    assert (token['email'],token['role'],token['kind'])==('boss@example.org','admin','invitation')
    assert token['token_hash']!=secret
    from app.domain.identity.mail import decrypt_payload
    assert decrypt_payload(outbox['encrypted_payload'])['link']==link
    tenant,_=accept(secret)
    me=tenant.get('/auth/me')
    assert me.status_code==200 and me.json()['ktel_id']==data['id'] and me.json()['role']=='admin'
    listed=client.get('/api/v1/platform/customers')
    assert listed.status_code==200
    assert {'id':data['id'],'name':'Panel KTEL','region':'Crete','status':'trial','trial_ends_on':'2026-12-31','plan_note':None}.items()<=next(
        customer for customer in listed.json() if customer['id']==data['id']).items()
    assert actions(platform_setup['owner'])==['login','customer_created']


def test_failed_create_leaves_no_organization_behind(platform_setup,monkeypatch):
    from app.domain.platform import customers
    original=customers.invitation_rows
    def broken(*args,**kwargs):
        rows=original(*args,**kwargs)
        rows.email.encrypted_payload=None
        return rows
    monkeypatch.setattr(customers,'invitation_rows',broken)
    client,csrf=operator_client(platform_setup)
    with pytest.raises(DBAPIError):
        client.post('/api/v1/platform/customers',headers=csrf,json={'name':'Half KTEL','timezone':'Europe/Athens','status':'active','admin_email':'half@example.org'})
    with platform_setup['owner'].connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ktels WHERE name='Half KTEL'")).scalar_one()==0
        assert connection.execute(text("SELECT count(*) FROM domain_identity_tokens WHERE email='half@example.org'")).scalar_one()==0
    assert actions(platform_setup['owner'])==['login']


def test_duplicate_or_invalid_customer_is_refused(platform_setup):
    client,csrf=operator_client(platform_setup)
    duplicate=client.post('/api/v1/platform/customers',headers=csrf,json={'name':'First KTEL','timezone':'Europe/Athens','status':'active','admin_email':'dup@example.org'})
    assert duplicate.status_code==409
    zone=client.post('/api/v1/platform/customers',headers=csrf,json={'name':'Zone KTEL','timezone':'Mars/Olympus','status':'active','admin_email':'zone@example.org'})
    assert zone.status_code==422
    suspended=client.post('/api/v1/platform/customers',headers=csrf,json={'name':'Closed KTEL','timezone':'Europe/Athens','status':'suspended','admin_email':'closed@example.org'})
    assert suspended.status_code==422


def test_suspension_ends_sessions_blocks_sign_in_and_reactivation_restores_it(platform_setup):
    tenant_id=platform_setup['first'].tenant_id
    tenant,bearer=accept(platform_setup['first'].token)
    client,csrf=operator_client(platform_setup)
    suspended=client.patch(f'/api/v1/platform/customers/{tenant_id}',headers=csrf,json={'status':'suspended'})
    assert suspended.status_code==200,suspended.text
    assert suspended.json()['status']=='suspended'
    assert tenant.get('/auth/me').status_code==401
    assert TestClient(app).get('/auth/me',headers=bearer).status_code==401
    with platform_setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM domain_auth_sessions WHERE tenant_id=:id AND revoked_at IS NULL'),{'id':tenant_id}).scalar_one()==0
    login=TestClient(app).post('/auth/login',json={'email':'first@example.org','password':TENANT_PASSWORD})
    assert login.status_code==403
    assert login.json()['detail']['code']=='organization_suspended'
    wrong=TestClient(app).post('/auth/login',json={'email':'first@example.org','password':'wrong-password-123'})
    assert wrong.status_code==401
    assert client.patch(f'/api/v1/platform/customers/{tenant_id}',headers=csrf,json={'status':'active'}).status_code==200
    again=TestClient(app)
    assert again.post('/auth/login',json={'email':'first@example.org','password':TENANT_PASSWORD}).status_code==200
    assert again.get('/auth/me').status_code==200
    assert actions(platform_setup['owner'])==['login','customer_suspended','customer_reactivated']


def test_live_session_of_a_suspended_organization_is_refused_on_cookie_and_bearer(platform_setup):
    tenant_id=platform_setup['first'].tenant_id
    tenant,bearer=accept(platform_setup['first'].token)
    bearer_client=TestClient(app)
    for status in ('suspended','cancelled'):
        with platform_setup['owner'].begin() as connection:
            connection.execute(text('UPDATE ktels SET status=:status WHERE id=:id'),{'status':status,'id':tenant_id})
        for response in (tenant.get('/auth/me'),bearer_client.get('/auth/me',headers=bearer)):
            assert response.status_code==403
            assert response.json()['detail']['code']=='organization_suspended'
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='trial' WHERE id=:id"),{'id':tenant_id})
    assert tenant.get('/auth/me').status_code==200
    assert bearer_client.get('/auth/me',headers=bearer).status_code==200


def test_subscription_fields_are_updated_and_audited(platform_setup):
    tenant_id=platform_setup['second'].tenant_id
    client,csrf=operator_client(platform_setup)
    updated=client.patch(f'/api/v1/platform/customers/{tenant_id}',headers=csrf,json={'plan_note':'Annual plan','trial_ends_on':'2027-01-15','region':'Attica'})
    assert updated.status_code==200,updated.text
    assert {k:updated.json()[k] for k in ('plan_note','trial_ends_on','region','status')}=={'plan_note':'Annual plan','trial_ends_on':'2027-01-15','region':'Attica','status':'active'}
    cleared=client.patch(f'/api/v1/platform/customers/{tenant_id}',headers=csrf,json={'trial_ends_on':None})
    assert cleared.json()['trial_ends_on'] is None and cleared.json()['plan_note']=='Annual plan'
    assert client.patch('/api/v1/platform/customers/999999',headers=csrf,json={'plan_note':'x'}).status_code==404
    assert actions(platform_setup['owner'])==['login','customer_updated','customer_updated']


def test_tenant_credentials_cannot_reach_customer_routes(platform_setup):
    tenant,bearer=accept(platform_setup['first'].token)
    assert tenant.get('/api/v1/platform/customers').status_code==401
    assert TestClient(app).get('/api/v1/platform/customers',headers=bearer).status_code==401
    response=tenant.patch(f"/api/v1/platform/customers/{platform_setup['first'].tenant_id}",json={'status':'active'},
                          headers={'X-CSRF-Token':tenant.cookies.get('ktel_csrf')})
    assert response.status_code==401


def test_panel_role_cannot_read_tenant_tables_directly(platform_setup):
    with platform_setup['platform'].begin() as connection:
        for table in ('users','domain_drivers','domain_auth_sessions','ktels','domain_identity_tokens','domain_email_outbox'):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(f'SELECT count(*) FROM {table}'))
        assert len(connection.execute(text('SELECT * FROM public.platform_list_customers()')).all())==4


def test_tenant_roles_cannot_change_subscription_state(platform_setup):
    tenant_id=platform_setup['first'].tenant_id
    for engine in (platform_setup['api'],platform_setup['worker']):
        with engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(tenant_id)})
            for statement in ("UPDATE ktels SET status='active'","UPDATE ktels SET trial_ends_on=NULL","UPDATE ktels SET plan_note='free'",
                              "UPDATE ktels SET name='Renamed'","SELECT public.platform_set_status(:tenant,'active')",
                              'SELECT * FROM public.platform_list_customers()',"SELECT public.platform_update_customer(:tenant,'x',NULL,NULL)"):
                with pytest.raises(DBAPIError):
                    with connection.begin_nested():
                        connection.execute(text(statement),{'tenant':tenant_id})
    with platform_setup['api'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(tenant_id)})
        assert connection.execute(text('UPDATE ktels SET support_access_until=NULL')).rowcount==1
        assert connection.execute(text('SELECT status FROM ktels')).scalar_one()=='active'
    with platform_setup['worker'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(tenant_id)})
        assert connection.execute(text('SELECT status FROM ktels')).scalar_one()=='active'
        with pytest.raises(DBAPIError):
            connection.execute(text('SELECT name FROM ktels'))


def test_refreshed_grants_narrow_a_broad_ktels_grant(platform_setup):
    from db.tenant_schema import grant_runtime_access
    api_role,worker_role=platform_setup['roles']
    with platform_setup['owner'].begin() as connection:
        connection.execute(text(f'GRANT ALL ON ktels TO "{api_role}", "{worker_role}"'))
        grant_runtime_access(connection,api_role,authenticate=True)
        grant_runtime_access(connection,worker_role)
        def column(role,name,privilege):
            return connection.execute(text("SELECT has_column_privilege(:role,'ktels',:column,:privilege)"),{'role':role,'column':name,'privilege':privilege}).scalar_one()
        assert not connection.execute(text("SELECT has_table_privilege(:role,'ktels','SELECT')"),{'role':api_role}).scalar_one()
        assert {name for name in ('id','name','region','timezone','status','created_at','support_access_until','plan_note','trial_ends_on') if column(api_role,name,'SELECT')}=={'id','name','region','timezone','status','created_at','support_access_until'}
        for name in ('status','trial_ends_on','plan_note','name','timezone','region','id','created_at'):
            assert not column(api_role,name,'UPDATE'),name
        assert column(api_role,'support_access_until','UPDATE')
        assert {name for name in ('id','name','status','plan_note','trial_ends_on') if column(worker_role,name,'SELECT')}=={'id','status'}
        assert not any(column(worker_role,name,'UPDATE') for name in ('status','support_access_until'))
        for role in (api_role,worker_role):
            for function in PLATFORM_FUNCTIONS:
                assert not connection.execute(text("SELECT has_function_privilege(:role,to_regprocedure(:function),'EXECUTE')"),{'role':role,'function':function}).scalar_one()


def test_refresh_removes_hand_granted_platform_function_access(platform_setup):
    from db.tenant_schema import grant_runtime_access
    api_role,worker_role=platform_setup['roles']
    with platform_setup['owner'].begin() as connection:
        for role in (api_role,worker_role):
            connection.execute(text(f'GRANT EXECUTE ON FUNCTION public.platform_list_customers() TO "{role}"'))
        grant_runtime_access(connection,api_role,authenticate=True)
        grant_runtime_access(connection,worker_role)
        for role in (api_role,worker_role):
            for function in PLATFORM_FUNCTIONS:
                assert not connection.execute(text("SELECT has_function_privilege(:role,to_regprocedure(:function),'EXECUTE')"),{'role':role,'function':function}).scalar_one()


def test_worker_does_not_claim_jobs_of_a_suspended_organization(platform_setup):
    from app.domain.jobs.repository import JobRepository
    from app.domain.jobs.worker import work_once
    from app.domain.scheduling.models import ScheduleRevision,SchedulingPeriod
    from app.domain.scheduling.snapshots import RevisionSnapshot
    from app.domain.identity.tenant_session import tenant_transaction
    tenant_id=platform_setup['first'].tenant_id
    with platform_setup['owner_factory']() as db:
        with tenant_transaction(db,tenant_id):
            period=SchedulingPeriod(tenant_id=tenant_id,name='Suspension',start_date=date(2026,10,30),end_date=date(2026,10,30))
            db.add(period);db.flush()
            db.add(ScheduleRevision(revision_id='suspension-snap',tenant_id=tenant_id,period_id=period.id,author='1'));db.flush()
            db.add(RevisionSnapshot(revision_id='suspension-snap',tenant_id=tenant_id,problem_data={},source_data={}));db.flush()
            job_id=JobRepository(db).enqueue_job(tenant_id,'suspension-snap').job_id
            db.commit()
    worker_factory=sessionmaker(bind=platform_setup['worker'])
    for status in ('suspended','cancelled'):
        with platform_setup['owner'].begin() as connection:
            connection.execute(text('UPDATE ktels SET status=:status WHERE id=:id'),{'status':status,'id':tenant_id})
        assert work_once(worker_factory,tenant_id,'suspended-worker') is False
        with platform_setup['owner'].connect() as connection:
            assert connection.execute(text('SELECT status,claimed_by FROM domain_jobs WHERE job_id=:id'),{'id':job_id}).one()==('queued',None)
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='active' WHERE id=:id"),{'id':tenant_id})
    assert work_once(worker_factory,tenant_id,'active-worker') is True
    with platform_setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT status FROM domain_jobs WHERE job_id=:id'),{'id':job_id}).scalar_one()!='queued'
