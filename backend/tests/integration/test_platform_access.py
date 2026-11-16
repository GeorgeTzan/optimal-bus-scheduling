import secrets
import stat
import time
import uuid
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from db.database import get_db
from main import app

OPERATOR_EMAIL='ops@example.org'
OPERATOR_PASSWORD='OperatorPassword-2026!'


def create_platform_role(connection):
    from db.tenant_schema import grant_platform_access
    role='ktel_test_platform_'+uuid.uuid4().hex[:16]
    password=secrets.token_urlsafe(24)
    connection.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD :password NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'),{'password':password})
    grant_platform_access(connection,role)
    return role,password


def drop_role(engine,role):
    with engine.begin() as connection:
        if connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
            connection.execute(text(f'DROP OWNED BY "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))


@pytest.fixture
def platform_setup(restricted_databases):
    from app.api.platform import get_platform_db
    from app.domain.identity.service import provision_organization
    from app.domain.platform.service import create_operator
    owner=restricted_databases['owner']
    owner_factory=sessionmaker(bind=owner)
    with owner_factory() as db:
        first=provision_organization(db,name='First KTEL',admin_email='first@example.org')
        second=provision_organization(db,name='Second KTEL',admin_email='second@example.org')
    with owner.begin() as connection:
        role,password=create_platform_role(connection)
    platform_engine=create_engine(owner.url.set(username=role,password=password))
    platform_factory=sessionmaker(bind=platform_engine)
    with platform_factory() as db:
        secret=create_operator(db,email=OPERATOR_EMAIL.upper(),password=OPERATOR_PASSWORD)
    api_factory=sessionmaker(bind=restricted_databases['api'])
    def tenant_database():
        with api_factory() as db:
            yield db
    def platform_database():
        with platform_factory() as db:
            yield db
    app.dependency_overrides[get_db]=tenant_database
    app.dependency_overrides[get_platform_db]=platform_database
    try:
        yield {'client':TestClient(app),'owner':owner,'owner_factory':owner_factory,'platform':platform_engine,
               'platform_role':role,'secret':secret,'first':first,'second':second,**restricted_databases}
    finally:
        app.dependency_overrides.clear()
        platform_engine.dispose()
        drop_role(owner,role)


def current_code(secret):
    from app.domain.platform import totp
    return totp.code(secret,int(time.time())//30)


def sign_in(client,secret,**overrides):
    body={'email':OPERATOR_EMAIL,'password':OPERATOR_PASSWORD,'code':current_code(secret),**overrides}
    return client.post('/api/v1/platform/auth/login',json=body)


def audit_rows(owner):
    with owner.connect() as connection:
        return connection.execute(text('SELECT operator_id,tenant_id,action,detail,ip FROM platform_audit ORDER BY id')).mappings().all()


def test_password_and_code_sign_in_sets_panel_cookie_and_csrf(platform_setup):
    client=platform_setup['client']
    response=sign_in(client,platform_setup['secret'])
    assert response.status_code==204,response.text
    cookies=response.headers.get_list('set-cookie')
    session_cookie=next(value for value in cookies if value.startswith('ktel_platform_session='))
    assert 'HttpOnly' in session_cookie and 'Path=/api/v1/platform' in session_cookie
    assert any(value.startswith('ktel_platform_csrf=') for value in cookies)
    assert not any(value.startswith('ktel_session=') for value in cookies)
    profile=client.get('/api/v1/platform/me')
    assert profile.status_code==200,profile.text
    assert profile.json()['email']==OPERATOR_EMAIL
    assert [row['action'] for row in audit_rows(platform_setup['owner'])]==['login']
    with platform_setup['owner'].connect() as connection:
        stored=connection.execute(text('SELECT token_hash FROM platform_sessions')).scalar_one()
    assert stored!=client.cookies.get('ktel_platform_session')


def test_wrong_code_is_refused_and_audited_with_the_operator(platform_setup):
    client=platform_setup['client']
    response=sign_in(client,platform_setup['secret'],code='000000' if current_code(platform_setup['secret'])!='000000' else '111111')
    assert response.status_code==401
    assert client.cookies.get('ktel_platform_session') is None
    rows=audit_rows(platform_setup['owner'])
    assert [(row['action'],row['operator_id'] is not None) for row in rows]==[('login_failed',True)]
    assert sign_in(client,platform_setup['secret'],password='wrong-password').status_code==401


def test_unknown_email_is_refused_and_audited_without_operator_or_plain_address(platform_setup):
    client=platform_setup['client']
    response=sign_in(client,platform_setup['secret'],email='nobody@example.org')
    assert response.status_code==401
    rows=audit_rows(platform_setup['owner'])
    assert len(rows)==1 and rows[0]['action']=='login_failed' and rows[0]['operator_id'] is None
    assert 'nobody@example.org' not in str(rows[0]['detail'])
    assert rows[0]['detail']['email_hash']


def test_the_same_code_cannot_be_used_twice(platform_setup):
    client=platform_setup['client']
    code=current_code(platform_setup['secret'])
    assert sign_in(client,platform_setup['secret'],code=code).status_code==204
    replay=TestClient(app)
    response=sign_in(replay,platform_setup['secret'],code=code)
    assert response.status_code==401
    assert replay.cookies.get('ktel_platform_session') is None
    assert [row['action'] for row in audit_rows(platform_setup['owner'])]==['login','login_failed']


def test_tenant_and_panel_credentials_never_cross(platform_setup):
    tenant=TestClient(app)
    accepted=tenant.post('/auth/accept-invitation',json={'token':platform_setup['first'].token,
        'password':'StrongTenantPassword123!','full_name':'KTEL administrator'})
    assert accepted.status_code==200,accepted.text
    assert tenant.get('/auth/me').status_code==200
    assert tenant.get('/api/v1/platform/me').status_code==401
    bearer={'Authorization':'Bearer '+accepted.json()['access_token']}
    assert TestClient(app).get('/api/v1/platform/me',headers=bearer).status_code==401
    panel=platform_setup['client']
    assert sign_in(panel,platform_setup['secret']).status_code==204
    token=panel.cookies.get('ktel_platform_session')
    assert token
    outsider=TestClient(app)
    assert outsider.get('/auth/me',headers={'Cookie':f'ktel_platform_session={token}'}).status_code==401
    assert outsider.get('/auth/me',headers={'Cookie':f'ktel_session={token}'}).status_code==401
    assert outsider.get('/api/v1/platform/me',headers={'Cookie':f'ktel_platform_session={token}'}).status_code==200


def test_panel_writes_require_csrf_and_logout_ends_the_session(platform_setup):
    client=platform_setup['client']
    assert sign_in(client,platform_setup['secret']).status_code==204
    assert client.post('/api/v1/platform/auth/logout').status_code==403
    assert client.post('/api/v1/platform/auth/logout',headers={'X-CSRF-Token':'forged'}).status_code==403
    assert client.get('/api/v1/platform/me').status_code==200
    csrf={'X-CSRF-Token':client.cookies.get('ktel_platform_csrf')}
    assert client.post('/api/v1/platform/auth/logout',headers=csrf).status_code==204
    assert client.get('/api/v1/platform/me').status_code==401
    assert [row['action'] for row in audit_rows(platform_setup['owner'])]==['login','logout']


def test_idle_panel_session_expires(platform_setup):
    client=platform_setup['client']
    assert sign_in(client,platform_setup['secret']).status_code==204
    with platform_setup['owner'].begin() as connection:
        connection.execute(text("UPDATE platform_sessions SET expires_at=now()-interval '1 second'"))
    assert client.get('/api/v1/platform/me').status_code==401


def test_inactive_operator_cannot_sign_in_or_keep_a_session(platform_setup):
    client=platform_setup['client']
    assert sign_in(client,platform_setup['secret']).status_code==204
    with platform_setup['owner'].begin() as connection:
        connection.execute(text('UPDATE platform_operators SET is_active=false'))
    assert client.get('/api/v1/platform/me').status_code==401


def test_sign_in_attempts_are_throttled_per_email_and_address_and_audited(platform_setup,monkeypatch):
    from config import settings
    monkeypatch.setattr(settings,'AUTH_LOGIN_LIMIT',2)
    client=platform_setup['client']
    for _ in range(2):
        assert sign_in(client,platform_setup['secret'],email='a@example.org').status_code==401
    throttled=sign_in(client,platform_setup['secret'],email='a@example.org')
    assert throttled.status_code==429
    assert client.cookies.get('ktel_platform_session') is None
    rows=audit_rows(platform_setup['owner'])
    assert [row['action'] for row in rows]==['login_failed','login_failed','login_throttled']
    assert rows[-1]['operator_id'] is None and 'a@example.org' not in str(rows[-1]['detail']) and rows[-1]['detail']['email_hash']
    assert sign_in(client,platform_setup['secret']).status_code==204


def test_code_guesses_are_capped_per_operator_across_addresses(platform_setup,monkeypatch):
    from app.api import platform as platform_api
    from app.domain.platform.service import TOTP_ATTEMPT_LIMIT
    addresses=iter(f'10.0.0.{index}' for index in range(1,100))
    monkeypatch.setattr(platform_api,'client_address',lambda request:next(addresses))
    client=platform_setup['client'];secret=platform_setup['secret']
    valid=current_code(secret)
    wrong=next(candidate for candidate in ('000000','111111','222222') if candidate!=valid)
    for _ in range(TOTP_ATTEMPT_LIMIT):
        assert sign_in(client,secret,code=wrong).status_code==401
    response=sign_in(client,secret,code=current_code(secret))
    assert response.status_code==401
    assert response.json()==sign_in(client,secret,code=wrong).json()
    assert client.cookies.get('ktel_platform_session') is None
    rows=audit_rows(platform_setup['owner'])
    assert len(rows)==TOTP_ATTEMPT_LIMIT+2
    assert all(row['action']=='login_failed' and row['operator_id'] is not None for row in rows)


def test_unknown_email_audit_hash_is_keyed(platform_setup):
    from app.domain.identity.service import digest
    from app.domain.platform.service import email_fingerprint
    assert sign_in(platform_setup['client'],platform_setup['secret'],email='nobody@example.org').status_code==401
    stored=audit_rows(platform_setup['owner'])[0]['detail']['email_hash']
    assert stored==email_fingerprint('nobody@example.org') and stored!=digest('nobody@example.org')


def test_panel_cookie_attributes(platform_setup):
    response=sign_in(platform_setup['client'],platform_setup['secret'])
    assert response.status_code==204
    cookies={value.split('=',1)[0]:[part.strip().lower() for part in value.split(';')] for value in response.headers.get_list('set-cookie')}
    session=cookies['ktel_platform_session'];csrf=cookies['ktel_platform_csrf']
    assert 'httponly' in session and 'path=/api/v1/platform' in session and 'samesite=strict' in session
    assert 'httponly' not in csrf and 'path=/platform' in csrf and 'samesite=strict' in csrf


def test_untrusted_origin_cannot_sign_in(platform_setup):
    response=platform_setup['client'].post('/api/v1/platform/auth/login',headers={'Origin':'https://evil.example'},
        json={'email':OPERATOR_EMAIL,'password':OPERATOR_PASSWORD,'code':current_code(platform_setup['secret'])})
    assert response.status_code==403


def test_tenant_reads_only_its_own_audit_rows_and_cannot_change_them(platform_setup):
    from app.domain.platform.service import record
    first,second=platform_setup['first'].tenant_id,platform_setup['second'].tenant_id
    with sessionmaker(bind=platform_setup['platform'])() as db:
        record(db,operator_id=None,tenant_id=first,action='customer_viewed',ip='10.0.0.1')
        record(db,operator_id=None,tenant_id=second,action='customer_viewed',ip='10.0.0.1')
        record(db,operator_id=None,tenant_id=None,action='login_failed',ip='10.0.0.1')
        db.commit()
    with platform_setup['api'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"),{'tenant':str(first)})
        assert connection.execute(text('SELECT tenant_id FROM platform_audit')).scalars().all()==[first]
        for statement in ("INSERT INTO platform_audit(tenant_id,action,ip) VALUES (:tenant,'forged','x')",
                          "UPDATE platform_audit SET action='forged' WHERE tenant_id=:tenant",
                          "DELETE FROM platform_audit WHERE tenant_id=:tenant"):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(statement),{'tenant':first})
    with platform_setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM platform_audit')).scalar_one()==3


def test_platform_role_is_limited_to_panel_tables(platform_setup):
    with platform_setup['platform'].begin() as connection:
        for statement in ('SELECT count(*) FROM users','SELECT count(*) FROM domain_drivers','SELECT count(*) FROM domain_auth_sessions',
                          'SELECT count(*) FROM platform_audit',"UPDATE platform_audit SET action='forged'",'DELETE FROM platform_audit'):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(statement))
        for function in ('ktel_login_identity(text)','ktel_session_by_token(text)'):
            assert connection.execute(text("SELECT has_function_privilege(current_user,:function,'EXECUTE')"),{'function':'public.'+function}).scalar_one() is False
    with platform_setup['api'].begin() as connection:
        for table in ('platform_operators','platform_sessions'):
            for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                assert connection.execute(text('SELECT has_table_privilege(current_user,:table,:privilege)'),{'table':table,'privilege':privilege}).scalar_one() is False
        for privilege in ('INSERT','UPDATE','DELETE'):
            assert connection.execute(text("SELECT has_table_privilege(current_user,'platform_audit',:privilege)"),{'privilege':privilege}).scalar_one() is False


def test_refresh_restores_platform_grants_only_for_an_existing_role(platform_setup):
    from db.provision_runtime import refresh_runtime_grants
    owner=platform_setup['owner'];role=platform_setup['platform_role']
    with owner.begin() as connection:
        connection.execute(text(f'GRANT SELECT ON users TO "{role}"'))
    refresh_runtime_grants(owner,*platform_setup['roles'],platform_role=role)
    missing='ktel_test_absent_'+uuid.uuid4().hex[:12]
    refresh_runtime_grants(owner,*platform_setup['roles'],platform_role=missing)
    with owner.connect() as connection:
        assert connection.execute(text("SELECT has_table_privilege(:role,'users','SELECT')"),{'role':role}).scalar_one() is False
        assert connection.execute(text("SELECT has_table_privilege(:role,'platform_sessions','INSERT')"),{'role':role}).scalar_one() is True
        assert connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':missing}).first() is None


def test_platform_role_provisioning_writes_private_url_once(postgres_engine,tmp_path):
    from db.migrations import upgrade_database
    from db.provision_runtime import provision_platform_role
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
    role='ktel_test_platform_'+uuid.uuid4().hex[:16]
    output=tmp_path/'.env.platform.local'
    engine=None
    try:
        provision_platform_role(postgres_engine,output,role)
        assert stat.S_IMODE(output.stat().st_mode)==0o600
        engine=create_engine(dotenv_values(output)['DATABASE_PLATFORM_URL'])
        with engine.begin() as connection:
            assert connection.execute(text('SELECT current_user')).scalar_one()==role
            assert connection.execute(text('SELECT count(*) FROM platform_operators')).scalar_one()==0
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text('SELECT count(*) FROM users'))
        with pytest.raises(RuntimeError):
            provision_platform_role(postgres_engine,tmp_path/'second.env',role)
        assert not (tmp_path/'second.env').exists()
    finally:
        if engine is not None:engine.dispose()
        drop_role(postgres_engine,role)


def test_operator_accounts_are_unique_and_store_only_hashes(platform_setup):
    from app.domain.platform.service import create_operator
    with platform_setup['owner'].connect() as connection:
        row=connection.execute(text('SELECT email,password_hash,is_active,last_totp_step FROM platform_operators')).one()
    assert row.email==OPERATOR_EMAIL and row.password_hash!=OPERATOR_PASSWORD and row.is_active and row.last_totp_step is None
    with sessionmaker(bind=platform_setup['platform'])() as db:
        with pytest.raises(ValueError):
            create_operator(db,email=OPERATOR_EMAIL,password=OPERATOR_PASSWORD)
        with pytest.raises(ValueError):
            create_operator(db,email='short@example.org',password='short')


def test_new_ktel_columns_default_to_active(platform_setup):
    with platform_setup['owner'].begin() as connection:
        assert set(connection.execute(text('SELECT status FROM ktels')).scalars())=={'active'}
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("UPDATE ktels SET status='paused'"))
        connection.execute(text("UPDATE ktels SET status='trial',trial_ends_on='2026-12-31',plan_note='pilot',support_access_until=now(),region='Crete' WHERE id=:id"),{'id':platform_setup['first'].tenant_id})


def test_platform_role_privileges_are_exactly_the_panel_tables_and_throttle(platform_setup):
    role=platform_setup['platform_role']
    with platform_setup['owner'].connect() as connection:
        tables=set(connection.execute(text('''SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','v','m','p')
            AND (has_table_privilege(:role,c.oid,'SELECT') OR has_table_privilege(:role,c.oid,'INSERT') OR has_table_privilege(:role,c.oid,'UPDATE')
              OR has_table_privilege(:role,c.oid,'DELETE') OR has_table_privilege(:role,c.oid,'TRUNCATE') OR has_table_privilege(:role,c.oid,'REFERENCES')
              OR has_table_privilege(:role,c.oid,'TRIGGER'))'''),{'role':role}).scalars())
        functions=set(connection.execute(text('''SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND p.prosecdef AND has_function_privilege(:role,p.oid,'EXECUTE')'''),{'role':role}).scalars())
    assert tables=={'platform_operators','platform_sessions','platform_audit'}
    assert functions=={'ktel_auth_budget','platform_create_customer','platform_set_status','platform_list_customers','platform_update_customer','platform_customer_health',
                       'platform_start_support_session','platform_end_support_sessions','platform_support_state'}


def test_tenancy_audit_checks_platform_audit_policies(platform_setup):
    from db.tenant_schema import audit_database_tenancy
    with platform_setup['owner'].begin() as connection:
        assert audit_database_tenancy(connection,platform_setup['roles'])==[]
        connection.execute(text('CREATE POLICY widened ON platform_audit FOR UPDATE USING (true)'))
        assert any('platform_audit' in issue for issue in audit_database_tenancy(connection,platform_setup['roles']))
        connection.execute(text('DROP POLICY widened ON platform_audit'))
        connection.execute(text('ALTER TABLE platform_audit NO FORCE ROW LEVEL SECURITY'))
        assert any('platform_audit' in issue for issue in audit_database_tenancy(connection,platform_setup['roles']))


def test_operator_cli_prints_enrolment_once_and_refuses_duplicates(postgres_engine,monkeypatch,capsys):
    import sys
    from app.cli import platform_operator
    from app.domain.platform import totp
    from db.migrations import upgrade_database
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
    monkeypatch.setenv('DATABASE_MIGRATION_URL',postgres_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(platform_operator.getpass,'getpass',lambda prompt='':OPERATOR_PASSWORD)
    monkeypatch.setattr(sys,'argv',['platform_operator','create','--email','New.Ops@Example.org'])
    platform_operator.main()
    printed=capsys.readouterr().out
    secret=next(line.split(': ',1)[1] for line in printed.splitlines() if line.startswith('TOTP secret: '))
    assert 'otpauth://totp/' in printed and f'secret={secret}' in printed
    with postgres_engine.connect() as connection:
        stored=connection.execute(text("SELECT totp_secret FROM platform_operators WHERE email='new.ops@example.org'")).scalar_one()
    assert stored==secret and totp.verify(secret,totp.code(secret,int(time.time())//30))
    with pytest.raises(SystemExit) as refused:
        platform_operator.main()
    assert refused.value.code!=0
    assert 'TOTP secret' not in capsys.readouterr().out


def test_api_startup_requires_current_support_grants(platform_setup,monkeypatch):
    import main
    monkeypatch.setattr(main,'engine',platform_setup['api'])
    with TestClient(main.app):pass
    with platform_setup['owner'].begin() as connection:
        connection.execute(text(f'REVOKE EXECUTE ON FUNCTION public.ktel_support_request(text,text,text,text) FROM "{platform_setup["roles"][0]}"'))
    with pytest.raises(RuntimeError,match='refresh-grants'):
        with TestClient(main.app):pass


def test_production_startup_checks_the_platform_role(platform_setup,monkeypatch):
    import main
    from app.api import platform as platform_module
    from config import settings
    monkeypatch.setattr(main,'engine',platform_setup['api'])
    monkeypatch.setattr(settings,'ENVIRONMENT','production')
    monkeypatch.setattr(settings,'DATABASE_PLATFORM_URL','postgresql://platform@localhost/other')
    monkeypatch.setattr(platform_module,'engine',platform_setup['platform'])
    with TestClient(main.app):pass
    monkeypatch.setattr(platform_module,'engine',platform_setup['owner'])
    with pytest.raises(RuntimeError,match='least-privilege'):
        with TestClient(main.app):pass
