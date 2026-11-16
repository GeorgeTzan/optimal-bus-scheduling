import re
from datetime import datetime,timedelta,timezone
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from main import app
from tests.integration.test_platform_access import platform_setup,sign_in
from tests.integration.test_platform_customers import TENANT_PASSWORD,accept,operator_client

SUPPORT_COOKIE='ktel_support_session'
SAFE=('GET','HEAD','OPTIONS')


@pytest.fixture
def support_setup(platform_setup):
    owner=platform_setup['owner']
    first=platform_setup['first'].tenant_id
    second=platform_setup['second'].tenant_id
    with owner.begin() as connection:
        for tenant,code in ((first,'S001'),(second,'S002')):
            connection.execute(text("INSERT INTO domain_drivers (tenant_id,code,first_name,last_name) VALUES (:tenant,:code,'Support','Visible')"),{'tenant':tenant,'code':code})
        drivers={row.tenant_id:row.id for row in connection.execute(text('SELECT tenant_id,id FROM domain_drivers WHERE tenant_id IN (:a,:b)'),{'a':first,'b':second})}
    admin,admin_auth=accept(platform_setup['first'].token)
    other,other_auth=accept(platform_setup['second'].token)
    operator,csrf=operator_client(platform_setup)
    return {**platform_setup,'first_id':first,'second_id':second,'drivers':drivers,'admin':admin,'admin_auth':admin_auth,
            'other':other,'other_auth':other_auth,'operator':operator,'csrf':csrf}


def consent(setup,enabled=True,auth='admin_auth'):
    response=TestClient(app).put('/api/v1/identity/support-access',json={'enabled':enabled},headers=setup[auth])
    assert response.status_code==200,response.text
    return response.json()


def start(setup,tenant=None,body=None):
    tenant=tenant or setup['first_id']
    return setup['operator'].post(f'/api/v1/platform/customers/{tenant}/support-session',headers=setup['csrf'],
                                  json=body if body is not None else {'reason':'Customer cannot see Monday schedule','ticket':'T-42'})


def support_client(setup):
    started=start(setup)
    assert started.status_code==201,started.text
    client=TestClient(app)
    client.cookies.set(SUPPORT_COOKIE,setup['operator'].cookies.get(SUPPORT_COOKIE))
    return client,started


def audit(owner,tenant_id):
    with owner.connect() as connection:
        return connection.execute(text('SELECT action,reason,ticket,detail FROM platform_audit WHERE tenant_id=:id ORDER BY id'),{'id':tenant_id}).mappings().all()


def test_start_requires_open_consent_a_reason_and_an_open_organization(support_setup):
    setup=support_setup
    refused=start(setup)
    assert refused.status_code==403 and refused.json()['detail']['code']=='support_access_not_enabled'
    assert SUPPORT_COOKIE not in setup['operator'].cookies
    consent(setup)
    assert start(setup,body={'ticket':'T-1'}).status_code==422
    assert start(setup,body={'reason':'   '}).status_code==422
    assert start(setup,tenant=987654).status_code==404
    assert setup['operator'].post(f"/api/v1/platform/customers/{setup['first_id']}/support-session",json={'reason':'x'}).status_code==403
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='suspended' WHERE id=:id"),{'id':setup['first_id']})
    suspended=start(setup)
    assert suspended.status_code==403 and suspended.json()['detail']['code']=='organization_suspended'
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='active' WHERE id=:id"),{'id':setup['first_id']})
    started=start(setup)
    assert started.status_code==201,started.text
    body=started.json()
    assert body['redirect']=='/' and body['mail_status'] in ('queued','not_configured')
    ends=datetime.fromisoformat(body['ends_at'])
    assert timedelta(minutes=59)<ends-datetime.now(timezone.utc)<=timedelta(minutes=60)
    cookie=next(value for value in started.headers.get_list('set-cookie') if value.startswith(SUPPORT_COOKIE+'='))
    attributes={part.strip().split('=')[0].lower():part.strip() for part in cookie.split(';')}
    assert 'httponly' in attributes and attributes['samesite'].lower()=='samesite=strict' and attributes['path']=='Path=/'
    assert 3500<int(attributes['max-age'].split('=')[1])<=3600
    with setup['owner'].connect() as connection:
        row=connection.execute(text('SELECT token_hash,reason,ticket,expires_at FROM platform_support_sessions')).mappings().one()
    assert row['token_hash']!=setup['operator'].cookies.get(SUPPORT_COOKIE) and len(row['token_hash'])==64
    assert (row['reason'],row['ticket'])==('Customer cannot see Monday schedule','T-42')
    assert setup['operator'].get('/api/v1/platform/me').status_code==200
    state=setup['operator'].get(f"/api/v1/platform/customers/{setup['first_id']}/support-session").json()
    assert state['access_open'] is True and state['session']['ends_at']==body['ends_at']


def test_session_is_capped_by_the_consent_window(support_setup):
    setup=support_setup
    consent(setup)
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET support_access_until=now()+interval '10 minutes' WHERE id=:id"),{'id':setup['first_id']})
    started=start(setup)
    assert started.status_code==201
    assert datetime.fromisoformat(started.json()['ends_at'])-datetime.now(timezone.utc)<=timedelta(minutes=10)
    cookie=next(value for value in started.headers.get_list('set-cookie') if value.startswith(SUPPORT_COOKIE+'='))
    assert int(re.search(r'Max-Age=(\d+)',cookie).group(1))<=600


def test_support_reads_its_tenant_only_and_is_reported_by_me(support_setup):
    setup=support_setup
    consent(setup)
    client,started=support_client(setup)
    me=client.get('/auth/me')
    assert me.status_code==200,me.text
    identity=me.json()
    assert identity['role']=='support' and identity['ktel_id']==setup['first_id']
    assert identity['support_session']['ends_at']==started.json()['ends_at']
    assert not {'members.manage','organization.manage','schedule.publish','schedule.approve','optimization.run','incidents.manage'}&set(identity['permissions'])
    assert not [permission for permission in identity['permissions'] if permission.endswith('.write')]
    assert {'resources.read','schedule.read'}<=set(identity['permissions'])
    drivers=client.get('/api/v1/drivers')
    assert drivers.status_code==200,drivers.text
    assert client.get(f"/api/v1/drivers/{setup['drivers'][setup['first_id']]}").status_code==200
    assert client.get(f"/api/v1/drivers/{setup['drivers'][setup['second_id']]}").status_code==404
    assert client.get('/api/v1/timetables').status_code==200
    codes={item['code'] for item in drivers.json()['items']}
    assert 'S001' in codes and 'S002' not in codes
    tenant_me=TestClient(app).get('/auth/me',headers=setup['admin_auth']).json()
    assert tenant_me['support_session']['ends_at']==started.json()['ends_at']
    assert TestClient(app).get('/auth/me',headers=setup['other_auth']).json()['support_session'] is None


def test_support_credential_cannot_write_or_reach_member_export_and_stream_routes(support_setup):
    setup=support_setup
    consent(setup)
    client,_=support_client(setup)
    for route in app.routes:
        if not isinstance(route,APIRoute) or route.path.startswith('/api/v1/platform'):
            continue
        path=re.sub(r'\{[^}]+\}','1',route.path)
        for method in route.methods-set(SAFE):
            response=client.request(method,path,json={})
            assert response.status_code==403,(method,path,response.text)
            assert response.json()['detail']['code']=='support_read_only',(method,path)
    for path in ('/api/v1/identity/members','/api/v1/identity/invitations','/api/v1/identity/support-access','/api/v1/office/grants'):
        assert client.get(path).status_code==403,path
    for path in ('/api/v1/reports/export?month=2026-10&format=xlsx','/events?once=true','/api/v1/imports/1/errors.csv','/api/v1/imports/1/populated.xlsx'):
        response=client.get(path)
        assert response.status_code==403,(path,response.text)
    with setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM domain_auth_sessions WHERE tenant_id=:id'),{'id':setup['first_id']}).scalar_one()==1
    rows=[row for row in audit(setup['owner'],setup['first_id']) if row['action']=='support_request']
    assert {'method':'POST','path':'/auth/login'} in [row['detail'] for row in rows]
    assert {'method':'GET','path':'/api/v1/identity/members'} in [row['detail'] for row in rows]


def test_request_transaction_is_read_only_and_stays_read_only_after_rollback(support_setup):
    from app.domain.identity.tenant_session import tenant_transaction
    factory=sessionmaker(bind=support_setup['api'])
    with factory() as db:
        db.info['read_only']=True
        with pytest.raises(DBAPIError) as raised:
            with tenant_transaction(db,support_setup['first_id']):
                db.execute(text("UPDATE domain_drivers SET first_name='Changed' WHERE tenant_id=:id"),{'id':support_setup['first_id']})
        assert raised.value.orig.pgcode=='25006'
        with pytest.raises(DBAPIError) as again:
            with tenant_transaction(db,support_setup['first_id']):
                db.execute(text("INSERT INTO domain_drivers (tenant_id,code,first_name,last_name) VALUES (:id,'X1','a','b')"),{'id':support_setup['first_id']})
        assert again.value.orig.pgcode=='25006'


def test_consent_revoke_ends_the_session_and_reenabling_does_not_revive_it(support_setup):
    setup=support_setup
    consent(setup)
    client,_=support_client(setup)
    assert client.get('/api/v1/drivers').status_code==200
    state=consent(setup,False)
    assert state['enabled'] is False
    with setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM platform_support_sessions WHERE ended_at IS NULL')).scalar_one()==0
    ended=client.get('/api/v1/drivers')
    assert ended.status_code==401
    assert any(value.startswith(SUPPORT_COOKIE+'=') and 'Max-Age=0' in value for value in ended.headers.get_list('set-cookie'))
    consent(setup)
    revived=TestClient(app)
    revived.cookies.set(SUPPORT_COOKIE,setup['operator'].cookies.get(SUPPORT_COOKIE))
    assert revived.get('/api/v1/drivers').status_code==401
    assert TestClient(app).get('/auth/me',headers=setup['admin_auth']).json()['support_session'] is None


def test_session_ends_at_expiry_suspension_operator_end_and_operator_logout(support_setup):
    setup=support_setup
    consent(setup)
    client,_=support_client(setup)
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE platform_support_sessions SET expires_at=now()-interval '1 second'"))
    assert client.get('/api/v1/drivers').status_code==401
    client,_=support_client(setup)
    assert setup['operator'].patch(f"/api/v1/platform/customers/{setup['first_id']}",headers=setup['csrf'],json={'status':'suspended'}).status_code==200
    assert client.get('/api/v1/drivers').status_code==401
    with setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM platform_support_sessions WHERE ended_at IS NULL')).scalar_one()==0
    assert setup['operator'].patch(f"/api/v1/platform/customers/{setup['first_id']}",headers=setup['csrf'],json={'status':'active'}).status_code==200
    client,_=support_client(setup)
    ended=setup['operator'].delete(f"/api/v1/platform/customers/{setup['first_id']}/support-session",headers=setup['csrf'])
    assert ended.status_code==204
    assert SUPPORT_COOKIE not in setup['operator'].cookies
    assert client.get('/api/v1/drivers').status_code==401
    client,_=support_client(setup)
    assert setup['operator'].post('/api/v1/platform/auth/logout',headers=setup['csrf']).status_code==204
    assert client.get('/api/v1/drivers').status_code==401
    ends=[row['detail']['by'] for row in audit(setup['owner'],setup['first_id']) if row['action']=='support_session_ended']
    assert ends==['suspension','operator','logout']


def test_tenant_audit_list_shows_start_requests_and_end_without_operator_identity(support_setup):
    setup=support_setup
    consent(setup)
    assert setup['operator'].patch(f"/api/v1/platform/customers/{setup['first_id']}",headers=setup['csrf'],json={'plan_note':'Secret internal pricing'}).status_code==200
    client,_=support_client(setup)
    client.get('/api/v1/drivers')
    client.post('/api/v1/drivers',json={})
    setup['operator'].delete(f"/api/v1/platform/customers/{setup['first_id']}/support-session",headers=setup['csrf'])
    view=TestClient(app).get('/api/v1/identity/support-access',headers=setup['admin_auth'])
    assert view.status_code==200,view.text
    data=view.json()
    assert data['enabled'] is True and data['until']
    entries=data['entries']
    actions=[entry['action'] for entry in entries]
    assert actions[0]=='support_session_ended' and 'support_session_started' in actions
    requests=[(entry['method'],entry['path']) for entry in entries if entry['action']=='support_request']
    assert ('GET','/api/v1/drivers') in requests and ('POST','/api/v1/drivers') in requests
    started=next(entry for entry in entries if entry['action']=='support_session_started')
    assert (started['reason'],started['ticket'],started['actor'])==('Customer cannot see Monday schedule','T-42','platform_support')
    allowed={'action','reason','ticket','method','path','ends_at','at','actor'}
    assert all(set(entry)==allowed for entry in entries)
    assert 'Secret internal pricing' not in view.text and 'ops@example.org' not in view.text and 'testclient' not in view.text
    other=TestClient(app).get('/api/v1/identity/support-access',headers=setup['other_auth']).json()
    assert other['entries']==[] and other['enabled'] is False


def test_support_principal_is_not_a_member(support_setup):
    setup=support_setup
    consent(setup)
    support_client(setup)
    members=TestClient(app).get('/api/v1/identity/members',headers=setup['admin_auth']).json()['members']
    assert [member['role'] for member in members]==['admin']
    assert all(member['email']=='first@example.org' for member in members)


def test_panel_and_support_cookies_never_cross(support_setup):
    setup=support_setup
    consent(setup)
    support_token=(support_client(setup)[0]).cookies.get(SUPPORT_COOKIE)
    panel_token=setup['operator'].cookies.get('ktel_platform_session')
    assert TestClient(app).get('/api/v1/platform/me',headers={'Cookie':f'{SUPPORT_COOKIE}={support_token}'}).status_code==401
    assert TestClient(app).get('/api/v1/platform/customers',headers={'Cookie':f'{SUPPORT_COOKIE}={support_token}'}).status_code==401
    assert TestClient(app).get('/auth/me',headers={'Cookie':f'ktel_platform_session={panel_token}'}).status_code==401
    assert TestClient(app).get('/api/v1/drivers',headers={'Cookie':f'ktel_platform_session={panel_token}'}).status_code==401
    assert TestClient(app).get('/auth/me',headers={'Cookie':f'{SUPPORT_COOKIE}={support_token}; ktel_session=forged'}).status_code==401
    assert TestClient(app).get('/auth/me',headers={'Cookie':f'{SUPPORT_COOKIE}={support_token}','Authorization':'Bearer forged'}).status_code==401


def test_database_roles_keep_support_sessions_narrow(support_setup):
    setup=support_setup
    consent(setup)
    support_client(setup)
    consent(setup,auth='other_auth')
    start(setup,tenant=setup['second_id'])
    from app.domain.identity.tenant_session import tenant_transaction
    factory=sessionmaker(bind=setup['api'])
    with factory() as db,tenant_transaction(db,setup['first_id']):
        rows=db.execute(text('SELECT tenant_id,reason FROM platform_support_sessions')).all()
        assert [row.tenant_id for row in rows]==[setup['first_id']]
    for statement in ('SELECT token_hash FROM platform_support_sessions','SELECT operator_id FROM platform_support_sessions',
                      "UPDATE platform_support_sessions SET ended_at=now()","DELETE FROM platform_support_sessions",
                      "INSERT INTO platform_support_sessions(operator_id,tenant_id,reason,token_hash,expires_at) VALUES (1,1,'r','x',now())",
                      "SELECT public.platform_start_support_session(1,1,'r',NULL,'x','ip')"):
        with factory() as db,pytest.raises(DBAPIError),tenant_transaction(db,setup['first_id']):
            db.execute(text(statement))
    for engine in (setup['worker'],setup['platform']):
        with engine.connect() as connection:
            for statement in ('SELECT id FROM platform_support_sessions',"SELECT * FROM public.ktel_support_request('x','GET','/','ip')"):
                with pytest.raises(DBAPIError):
                    connection.execute(text(statement))
                connection.rollback()
    with setup['platform'].connect() as connection:
        for statement in ('SELECT public.ktel_end_support_sessions()','SELECT id FROM users'):
            with pytest.raises(DBAPIError):
                connection.execute(text(statement))
            connection.rollback()
    from db.tenant_schema import audit_database_tenancy
    with setup['owner'].begin() as connection:
        assert not [issue for issue in audit_database_tenancy(connection) if 'platform_support_sessions' in issue]
        connection.execute(text('CREATE POLICY widened ON platform_support_sessions FOR SELECT USING (true)'))
        assert any('platform_support_sessions' in issue for issue in audit_database_tenancy(connection))
        connection.rollback()


def test_administrators_are_mailed_on_start_and_mail_failure_never_blocks(support_setup,monkeypatch):
    setup=support_setup
    consent(setup)
    started=start(setup)
    assert started.status_code==201
    from app.domain.identity.mail import decrypt_payload
    with setup['owner'].connect() as connection:
        rows=connection.execute(text("SELECT identity_token_id,encrypted_payload,delivery_status FROM domain_email_outbox WHERE tenant_id=:id AND kind='support_session'"),{'id':setup['first_id']}).mappings().all()
    assert len(rows)==1 and rows[0]['identity_token_id'] is None
    payload=decrypt_payload(rows[0]['encrypted_payload'])
    assert payload['to']=='first@example.org' and 'Customer cannot see Monday schedule' in payload['text']
    assert started.json()['mail_status']==rows[0]['delivery_status']
    from app.domain.platform import support
    def broken(*args,**kwargs):
        raise RuntimeError('mail is down')
    monkeypatch.setattr(support,'support_email',broken)
    again=start(setup)
    assert again.status_code==201 and again.json()['mail_status']=='failed'


def test_tokenless_support_mail_is_delivered(support_setup,monkeypatch):
    setup=support_setup
    from config import settings
    from app.domain.identity import mail
    monkeypatch.setattr(settings,'SMTP_HOST','127.0.0.1')
    monkeypatch.setattr(settings,'SMTP_FROM','sender@example.org')
    consent(setup)
    start(setup)
    sent=[]
    monkeypatch.setattr(mail,'send_email',lambda payload,identifier:sent.append(payload['to']))
    factory=sessionmaker(bind=setup['worker'])
    assert mail.deliver_once(factory,setup['first_id'],'worker-1')
    assert sent==['first@example.org']
    with setup['owner'].connect() as connection:
        assert connection.execute(text("SELECT delivery_status FROM domain_email_outbox WHERE kind='support_session'")).scalar_one()=='sent'


def test_tokenless_mail_of_another_kind_is_discarded(support_setup,monkeypatch):
    setup=support_setup
    from config import settings
    from app.domain.identity import mail
    monkeypatch.setattr(settings,'SMTP_HOST','127.0.0.1')
    monkeypatch.setattr(settings,'SMTP_FROM','sender@example.org')
    with setup['owner'].begin() as connection:
        connection.execute(text('ALTER TABLE domain_email_outbox DROP CONSTRAINT ck_email_outbox_token_or_support'))
        connection.execute(text("INSERT INTO domain_email_outbox(id,tenant_id,identity_token_id,kind,encrypted_payload,delivery_status,attempts,attempt_token,created_at) VALUES ('orphan',:id,NULL,'invitation','x','queued',0,0,now())"),{'id':setup['first_id']})
    sent=[]
    monkeypatch.setattr(mail,'send_email',lambda payload,identifier:sent.append(identifier))
    factory=sessionmaker(bind=setup['worker'])
    assert mail.deliver_once(factory,setup['first_id'],'worker-1')
    assert sent==[]
    with setup['owner'].connect() as connection:
        assert connection.execute(text("SELECT delivery_status FROM domain_email_outbox WHERE id='orphan'")).scalar_one()=='discarded'


def test_outbox_rejects_tokenless_rows_of_other_kinds(support_setup):
    setup=support_setup
    with setup['owner'].begin() as connection:
        connection.execute(text("INSERT INTO domain_email_outbox(id,tenant_id,identity_token_id,kind,encrypted_payload,delivery_status,attempts,attempt_token,created_at) VALUES ('ok',:id,NULL,'support_session','x','queued',0,0,now())"),{'id':setup['first_id']})
    with pytest.raises(Exception,match='ck_email_outbox_token_or_support'):
        with setup['owner'].begin() as connection:
            connection.execute(text("INSERT INTO domain_email_outbox(id,tenant_id,identity_token_id,kind,encrypted_payload,delivery_status,attempts,attempt_token,created_at) VALUES ('bad',:id,NULL,'invitation','x','queued',0,0,now())"),{'id':setup['first_id']})


def test_suspended_organization_cannot_accept_invitations_or_reset_passwords(support_setup,monkeypatch):
    setup=support_setup
    from app.domain.identity.service import issue_invitation,issue_reset
    from app.domain.identity.tenant_session import tenant_transaction
    from db.models import User
    with setup['owner_factory']() as db,tenant_transaction(db,setup['first_id']):
        invitation=issue_invitation(db,setup['first_id'],'new@example.org','viewer')
        user=db.query(User).filter_by(email='first@example.org').one()
        _,reset_secret,_=issue_reset(db,user,setup['first_id'])
        db.commit()
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='suspended' WHERE id=:id"),{'id':setup['first_id']})
        before=connection.execute(text('SELECT count(*) FROM domain_email_outbox WHERE tenant_id=:id'),{'id':setup['first_id']}).scalar_one()
        password=connection.execute(text("SELECT hashed_password FROM users WHERE email='first@example.org'")).scalar_one()
    accepted=TestClient(app).post('/auth/accept-invitation',json={'token':invitation.token,'password':TENANT_PASSWORD,'full_name':'New person'})
    assert accepted.status_code==403 and accepted.json()['detail']['code']=='organization_suspended'
    requested=TestClient(app).post('/auth/password-reset/request',json={'email':'first@example.org'})
    unknown=TestClient(app).post('/auth/password-reset/request',json={'email':'nobody@example.org'})
    assert requested.status_code==unknown.status_code==202 and requested.json()==unknown.json()
    confirmed=TestClient(app).post('/auth/password-reset/confirm',json={'token':reset_secret,'password':'AnotherStrongPassword1!'})
    invalid=TestClient(app).post('/auth/password-reset/confirm',json={'token':'x'*43,'password':'AnotherStrongPassword1!'})
    assert confirmed.status_code==invalid.status_code==400 and confirmed.json()==invalid.json()
    with setup['owner'].connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM domain_email_outbox WHERE tenant_id=:id'),{'id':setup['first_id']}).scalar_one()==before
        assert connection.execute(text("SELECT hashed_password FROM users WHERE email='first@example.org'")).scalar_one()==password
        assert connection.execute(text("SELECT count(*) FROM users WHERE email='new@example.org'")).scalar_one()==0


def test_suspended_organization_cannot_relink_a_driver_login(support_setup):
    setup=support_setup
    from app.domain.identity.service import accept_invitation
    from app.domain.identity.models import IdentityToken
    from app.domain.identity.service import digest
    from fastapi import HTTPException
    tenant=setup['first_id']
    driver=setup['drivers'][tenant]
    with setup['owner'].begin() as connection:
        connection.execute(text("UPDATE ktels SET status='cancelled' WHERE id=:id"),{'id':tenant})
    factory=sessionmaker(bind=setup['owner'])
    with factory() as db:
        db.add(IdentityToken(id='relink-token',tenant_id=tenant,token_hash=digest('relink-secret-value-0123456789'),kind='invitation',
                             email='first@example.org',role='driver',driver_id=driver,expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        db.commit()
    api=sessionmaker(bind=setup['api'])
    with api() as db,pytest.raises(HTTPException) as refused:
        accept_invitation(db,'relink-secret-value-0123456789',TENANT_PASSWORD,'Driver')
    assert refused.value.status_code==403 and refused.value.detail['code']=='organization_suspended'


def test_customer_name_blank_after_stripping_is_refused(support_setup):
    setup=support_setup
    response=setup['operator'].post('/api/v1/platform/customers',headers=setup['csrf'],
                                    json={'name':'   ','timezone':'Europe/Athens','status':'active','admin_email':'blank@example.org'})
    assert response.status_code==422


def test_real_support_request_runs_in_a_read_only_transaction_and_tenant_requests_do_not(support_setup,monkeypatch):
    setup=support_setup
    consent(setup)
    client,_=support_client(setup)
    from app.domain.platform import support
    seen=[]
    original=support.principal
    def spy(db,found):
        seen.append(db.execute(text('SHOW transaction_read_only')).scalar_one())
        return original(db,found)
    monkeypatch.setattr(support,'principal',spy)
    assert client.get('/auth/me').status_code==200
    assert seen==['on']
    tenant_seen=[]
    original_active=support.active_session
    def tenant_spy(db,tenant_id):
        tenant_seen.append(db.execute(text('SHOW transaction_read_only')).scalar_one())
        return original_active(db,tenant_id)
    monkeypatch.setattr(support,'active_session',tenant_spy)
    assert TestClient(app).get('/auth/me',headers=setup['admin_auth']).status_code==200
    assert tenant_seen==['off']


def test_audit_list_keeps_session_rows_when_requests_exceed_the_limit(support_setup,monkeypatch):
    setup=support_setup
    from app.domain.platform import support
    monkeypatch.setattr(support,'ENTRY_LIMIT',5)
    consent(setup)
    client,_=support_client(setup)
    for _ in range(8):
        client.get('/api/v1/drivers')
    entries=TestClient(app).get('/api/v1/identity/support-access',headers=setup['admin_auth']).json()['entries']
    actions=[entry['action'] for entry in entries]
    assert actions.count('support_request')==5 and 'support_session_started' in actions


def test_deactivated_operator_loses_support_access(support_setup):
    setup=support_setup
    consent(setup)
    client,_=support_client(setup)
    assert client.get('/api/v1/drivers').status_code==200
    with setup['owner'].begin() as connection:
        connection.execute(text('UPDATE platform_operators SET is_active=false'))
    assert client.get('/api/v1/drivers').status_code==401


def test_every_panel_route_refuses_tenant_bearer_tenant_cookie_and_support_cookie(support_setup):
    setup=support_setup
    consent(setup)
    support=support_client(setup)[0]
    credentials=[('tenant cookie',setup['admin'],{}),('tenant bearer',TestClient(app),setup['admin_auth']),('support cookie',support,{})]
    swept=0
    for route in app.routes:
        if not isinstance(route,APIRoute) or not route.path.startswith('/api/v1/platform') or route.path.endswith('/auth/login'):continue
        path=re.sub(r'\{[^}]+\}','1',route.path)
        for method in route.methods-{'HEAD','OPTIONS'}:
            for label,client,headers in credentials:
                response=client.request(method,path,headers={**headers,'Origin':'http://localhost:3000'},json={} if method not in SAFE else None)
                assert response.status_code==401,(method,path,label,response.status_code)
            swept+=1
    assert swept>=8
