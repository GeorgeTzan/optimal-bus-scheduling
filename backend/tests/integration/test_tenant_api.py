from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from db.database import get_db
from main import app


def test_restricted_roles_support_auth_revision_edits_and_actual_worker(restricted_databases, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", True)
    from core.security import hash_password
    from db.tenant_schema import grant_runtime_access
    with restricted_databases['owner'].begin() as connection:
        grant_runtime_access(connection, restricted_databases['roles'][0], authenticate=True)
        for tenant in (1,2):
            connection.execute(text('''INSERT INTO users(id,ktel_id,email,hashed_password,full_name,is_active,is_admin)
                VALUES (:id,:tenant,:email,:password,'Tenant admin',true,true)'''),
                {'id':tenant,'tenant':tenant,'email':f'admin{tenant}@test.gr','password':hash_password('TenantPassword123!')})
        for tenant in (1,2):
            connection.execute(text("INSERT INTO domain_memberships(tenant_id,user_id,role,is_active,version,created_at) VALUES (:tenant,:tenant,'admin',true,1,now())"),{'tenant':tenant})
        connection.execute(text("SELECT setval(pg_get_serial_sequence('users','id'),2,true)"))
    factory=sessionmaker(bind=restricted_databases['api'])
    def request_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=request_db
    try:
        client=TestClient(app)
        headers=[]
        for tenant in (1,2):
            login=client.post('/auth/login',json={'email':f'admin{tenant}@test.gr','password':'TenantPassword123!'})
            assert login.status_code==200,login.text
            headers.append({'Authorization':'Bearer '+login.json()['access_token']})
        identity=client.get('/auth/me',headers=headers[0])
        assert identity.status_code==200,identity.text
        assert identity.json()['ktel_id']==1
        imported=client.post('/api/v1/scheduling/revisions/import-reference',headers=headers[0],json={'service_date':'2026-10-30'})
        assert imported.status_code==201,imported.text
        revision=imported.json()
        assert client.get('/api/v1/scheduling/revisions/active',headers=headers[1]).status_code==404
        row=revision['assignments'][0]
        patch={'version':revision['version'],'patches':[{'trip_id':row['trip_id'],'new_resource_id':row['resource_id'],'is_locked':True}]}
        url=f"/api/v1/scheduling/revisions/{revision['revision_id']}/patches"
        assert client.post(url,headers=headers[1],json=patch).status_code==404
        assert client.post(url,headers=headers[0],json=patch).status_code==200
        run=client.post('/optimization/runs',headers=headers[0],json={
            'snapshot_id':revision['revision_id'],'config':{'iterations':1,'time_limit_seconds':20}})
        assert run.status_code==202,run.text
        run_id=run.json()['run_id']
        assert client.get(f'/optimization/runs/{run_id}',headers=headers[1]).status_code==404
        from app.domain.jobs.worker import work_once
        worker_factory=sessionmaker(bind=restricted_databases['worker'])
        assert work_once(worker_factory,tenant_id=1,worker_id='restricted-worker')
        outcome=client.get(f'/optimization/runs/{run_id}',headers=headers[0]).json()
        assert outcome['status']=='completed',outcome
        candidates=client.get(f'/optimization/runs/{run_id}/candidates',headers=headers[0]).json()
        assert candidates['candidates']
        events=client.get('/events?once=true',headers=headers[0])
        assert events.status_code==200
        assert 'job.completed' in events.text
        assert run_id not in client.get('/events?once=true',headers=headers[1]).text
    finally:
        app.dependency_overrides.clear()
