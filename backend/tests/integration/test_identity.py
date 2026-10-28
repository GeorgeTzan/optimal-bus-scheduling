from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from db.database import get_db
from main import app


@pytest.fixture
def identity_setup(restricted_databases):
    from app.domain.identity.service import provision_organization
    from db.tenant_schema import grant_runtime_access
    owner_factory=sessionmaker(bind=restricted_databases['owner'])
    with owner_factory() as db:
        first=provision_organization(db,name='First KTEL',admin_email='first@example.org')
        second=provision_organization(db,name='Second KTEL',admin_email='second@example.org')
    with restricted_databases['owner'].begin() as connection:
        grant_runtime_access(connection,restricted_databases['roles'][0],authenticate=True)
    api_factory=sessionmaker(bind=restricted_databases['api'])
    def database():
        with api_factory() as db:
            yield db
    app.dependency_overrides[get_db]=database
    try:
        yield {'client':TestClient(app),'first':first,'second':second,'owner_factory':owner_factory}
    finally:
        app.dependency_overrides.clear()


def accept(client,invitation):
    response=client.post('/auth/accept-invitation',json={
        'token':invitation.token,'password':'StrongTenantPassword123!','full_name':'KTEL administrator'})
    assert response.status_code==200,response.text
    return response


def test_invitation_creates_private_cookie_session_and_csrf_guard(identity_setup):
    client=identity_setup['client'];invite=identity_setup['first']
    preview=client.post('/auth/invitations/preview',json={'token':invite.token})
    assert preview.status_code==200,preview.text
    assert preview.json()['organization_name']=='First KTEL'
    accepted=accept(client,invite)
    assert any('HttpOnly' in value and 'ktel_session=' in value for value in accepted.headers.get_list('set-cookie'))
    assert client.cookies.get('ktel_csrf')
    bearer={'Authorization':'Bearer '+accepted.json()['access_token']}
    profile=client.get('/auth/me')
    assert profile.status_code==200,profile.text
    assert profile.json()['ktel_id']==invite.tenant_id
    assert profile.json()['role']=='admin'
    assert profile.json()['ktel_name']=='First KTEL'
    assert 'members.manage' in profile.json()['permissions']
    assert client.post('/auth/logout').status_code==403
    assert client.get('/auth/me').status_code==200
    csrf={'X-CSRF-Token':client.cookies.get('ktel_csrf')}
    assert client.post('/auth/logout',headers=csrf).status_code==204
    assert client.get('/auth/me',headers=bearer).status_code==401
    assert client.get('/auth/me').status_code==401


def test_invitation_is_hashed_single_use_and_cannot_be_retargeted(identity_setup):
    client=identity_setup['client'];invite=identity_setup['first']
    with identity_setup['owner_factory']() as db:
        rows=db.execute(text('SELECT token_hash FROM domain_identity_tokens')).scalars().all()
        assert rows and invite.token not in rows
    forged=client.post('/auth/accept-invitation',json={'token':invite.token,
        'password':'StrongTenantPassword123!','full_name':'Admin','tenant_id':identity_setup['second'].tenant_id})
    assert forged.status_code==422
    accepted=accept(client,invite)
    assert client.post('/auth/accept-invitation',json={'token':invite.token,
        'password':'StrongTenantPassword123!','full_name':'Again'}).status_code==400
    with identity_setup['owner_factory']() as db:
        db.execute(text("UPDATE domain_identity_tokens SET expires_at=now()-interval '1 second' WHERE tenant_id=:tenant"),
                   {'tenant':identity_setup['second'].tenant_id})
        db.commit()
    assert client.post('/auth/invitations/preview',json={'token':identity_setup['second'].token}).status_code==400


def test_roles_are_server_authoritative_and_membership_changes_revoke_sessions(identity_setup):
    from app.domain.identity.service import issue_invitation
    client=identity_setup['client'];invite=identity_setup['first']
    admin=accept(client,invite)
    admin_headers={'Authorization':'Bearer '+admin.json()['access_token']}
    with identity_setup['owner_factory']() as db:
        dispatcher=issue_invitation(db,invite.tenant_id,'dispatcher@example.org','dispatcher')
        driver=issue_invitation(db,invite.tenant_id,'driver@example.org','driver')
        db.commit()
    dispatcher_login=accept(client,dispatcher)
    dispatcher_headers={'Authorization':'Bearer '+dispatcher_login.json()['access_token']}
    assert client.get('/api/v1/scheduling/revisions/active',headers=dispatcher_headers).status_code==404
    assert client.post('/api/v1/scheduling/revisions/missing/patches',headers=dispatcher_headers,json={
        'version':1,'patches':[{'trip_id':'missing','new_resource_id':'missing'}]}).status_code==404
    assert client.get('/api/v1/identity/members',headers=dispatcher_headers).status_code==403
    driver_login=accept(client,driver)
    driver_headers={'Authorization':'Bearer '+driver_login.json()['access_token']}
    assert client.get('/api/v1/scheduling/revisions/active',headers=driver_headers).status_code==403
    assert client.get('/events?once=true',headers=driver_headers).status_code==403
    members=client.get('/api/v1/identity/members',headers=admin_headers)
    assert members.status_code==200,members.text
    target=next(member for member in members.json()['members'] if member['email']=='dispatcher@example.org')
    changed=client.patch(f"/api/v1/identity/members/{target['id']}",headers=admin_headers,json={
        'version':target['version'],'role':'viewer','is_active':True})
    assert changed.status_code==200,changed.text
    assert client.get('/auth/me',headers=dispatcher_headers).status_code==401
    own=next(member for member in members.json()['members'] if member['email']==invite.email)
    assert client.patch(f"/api/v1/identity/members/{own['id']}",headers=admin_headers,json={
        'version':own['version'],'role':'viewer'}).status_code==403  # own role is refused before the last-administrator guard
    other=accept(client,identity_setup['second'])
    other_headers={'Authorization':'Bearer '+other.json()['access_token']}
    assert client.patch(f"/api/v1/identity/members/{target['id']}",headers=other_headers,json={
        'version':2,'role':'admin'}).status_code==404


def test_browser_auth_rejects_untrusted_origins_and_legacy_shared_invites(identity_setup,monkeypatch):
    client=identity_setup['client']
    assert client.post('/auth/login',headers={'Origin':'https://untrusted.example.org'},json={
        'email':'any@example.org','password':'anything'}).status_code==403
    assert client.post('/auth/register',json={'email':'any@example.org','password':'SomePassword123!',
        'full_name':'Someone','invitation_code':'KTEL-PILOT-2026'}).status_code==403
    # Normal customer routes hide reference tooling entirely; opted-in local tooling still requires authentication.
    assert TestClient(app).post('/solve/legacy').status_code==404
    from config import settings
    monkeypatch.setattr(settings,'REFERENCE_TOOLS_ENABLED',True)
    assert TestClient(app).post('/solve/legacy').status_code==401


def test_password_reset_is_private_single_use_and_revokes_existing_sessions(identity_setup):
    from app.domain.identity.mail import decrypt_payload
    from urllib.parse import urlsplit,parse_qs
    client=identity_setup['client'];invite=identity_setup['first']
    accepted=accept(client,invite)
    old_headers={'Authorization':'Bearer '+accepted.json()['access_token']}
    known=client.post('/auth/password-reset/request',json={'email':invite.email})
    unknown=client.post('/auth/password-reset/request',json={'email':'unknown@example.org'})
    assert known.status_code==unknown.status_code==202
    assert known.json()==unknown.json()
    with identity_setup['owner_factory']() as db:
        row=db.execute(text("SELECT encrypted_payload,delivery_status FROM domain_email_outbox WHERE kind='reset' ORDER BY created_at DESC LIMIT 1")).one()
        assert row.delivery_status=='not_configured'
        assert invite.email not in row.encrypted_payload
        payload=decrypt_payload(row.encrypted_payload)
        raw=parse_qs(urlsplit(payload['link']).fragment)['token'][0]
    changed=client.post('/auth/password-reset/confirm',json={'token':raw,'password':'A-new-strong-password123!'})
    assert changed.status_code==200,changed.text
    assert client.get('/auth/me',headers=old_headers).status_code==401
    assert client.post('/auth/password-reset/confirm',json={'token':raw,'password':'AnotherPassword123!'}).status_code==400
    assert client.post('/auth/login',json={'email':invite.email,'password':'StrongTenantPassword123!'}).status_code==401
    assert client.post('/auth/login',json={'email':invite.email,'password':'A-new-strong-password123!'}).status_code==200


def test_login_attempt_budget_is_durable_and_does_not_allow_bypass(identity_setup,monkeypatch):
    from config import settings
    monkeypatch.setattr(settings,'AUTH_LOGIN_LIMIT',2)
    client=identity_setup['client'];invite=identity_setup['first']
    accept(client,invite)
    for _ in range(2):
        assert client.post('/auth/login',json={'email':invite.email,'password':'incorrect'}).status_code==401
    limited=client.post('/auth/login',json={'email':invite.email,'password':'StrongTenantPassword123!'})
    assert limited.status_code==429
    assert int(limited.headers['retry-after'])>0
    with identity_setup['owner_factory']() as db:
        assert db.execute(text('SELECT max(attempts) FROM identity_rate_limits')).scalar_one()==3


def test_login_rechecks_password_after_concurrent_credential_change(identity_setup,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from core.security import hash_password
    import api.auth as auth_module
    client=identity_setup['client'];invite=identity_setup['first']
    accept(client,invite)
    looked_up=Event();proceed=Event()
    original=auth_module.lookup_identity
    def observe(db,identity,**kwargs):
        user=original(db,identity,**kwargs)
        looked_up.set()
        assert proceed.wait(10)
        return user
    monkeypatch.setattr(auth_module,'lookup_identity',observe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(lambda:TestClient(app).post('/auth/login',json={
            'email':invite.email,'password':'StrongTenantPassword123!'}))
        assert looked_up.wait(10)
        try:
            with identity_setup['owner_factory']() as db:
                db.execute(text('UPDATE users SET hashed_password=:password WHERE email=:email'),
                           {'password':hash_password('Updated-credential-password123!'),'email':invite.email})
                db.commit()
        finally:
            proceed.set()
        assert future.result(timeout=15).status_code==401


def test_admin_invites_are_bound_to_tenant_and_never_report_unconfigured_mail_as_sent(identity_setup):
    client=identity_setup['client'];invite=identity_setup['first']
    logged=accept(client,invite)
    headers={'Authorization':'Bearer '+logged.json()['access_token']}
    response=client.post('/api/v1/identity/invitations',headers=headers,json={
        'email':'new-dispatcher@example.org','role':'dispatcher'})
    assert response.status_code==202,response.text
    assert response.json()['delivery_status']=='not_configured'
    assert 'token' not in response.json()
    assert 'link' not in response.json()
    assert client.post('/api/v1/identity/invitations',headers=headers,json={
        'email':'forged@example.org','role':'platform_admin'}).status_code==422
    assert client.post('/api/v1/identity/invitations',headers=headers,json={
        'email':'forged@example.org','role':'admin','tenant_id':identity_setup['second'].tenant_id}).status_code==422


def test_open_event_stream_rechecks_revocation_between_polls(identity_setup,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.api.events import sse_events
    from app.domain.events.outbox import OutboxService
    from app.domain.identity.models import AuthSession
    from app.domain.identity.tenant_session import set_tenant_scope
    client=identity_setup['client'];accept(client,identity_setup['first'])
    profile=client.get('/auth/me').json()
    monkeypatch.setattr(OutboxService,'get_events_after',lambda *args,**kwargs:[SimpleNamespace(id=1,payload={},job_id='private',event_type='job.progress')])
    async def exercise():
        with identity_setup['owner_factory']() as db:
            set_tenant_scope(db,profile['ktel_id'])
            user=SimpleNamespace(id=profile['id'],ktel_id=profile['ktel_id'],session_id=profile['session_id'])
            response=await sse_events(request=SimpleNamespace(),cursor=0,once=True,current_user=user,db=db)
            stream=response.body_iterator
            assert 'heartbeat' in await anext(stream)
            with identity_setup['owner_factory']() as other:
                other.query(AuthSession).filter_by(id=profile['session_id']).update({'revoked_at':datetime.now(timezone.utc)})
                other.commit()
            remaining=[frame async for frame in stream]
            assert not any('private' in frame for frame in remaining)
    asyncio.run(exercise())


def test_reissued_invitation_invalidates_previous_link(identity_setup):
    from app.domain.identity.service import issue_invitation
    client=identity_setup['client'];invite=identity_setup['first'];accept(client,invite)
    with identity_setup['owner_factory']() as db:
        first=issue_invitation(db,invite.tenant_id,'new@example.org','viewer');db.commit()
        replacement=issue_invitation(db,invite.tenant_id,'new@example.org','dispatcher');db.commit()
    assert client.post('/auth/invitations/preview',json={'token':first.token}).status_code==400
    preview=client.post('/auth/invitations/preview',json={'token':replacement.token})
    assert preview.status_code==200 and preview.json()['role']=='dispatcher'


def test_platform_provisioning_writes_only_private_invitation_file(identity_setup,tmp_path,capsys):
    import stat
    from app.cli.provision import provision_to_file
    path=tmp_path/'first-admin.txt'
    with identity_setup['owner_factory']() as db:
        provision_to_file(db,name='New operator',admin_email='operator@example.org',timezone='Europe/Athens',output=path)
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    assert '#token=' in path.read_text()
    assert '#token=' not in capsys.readouterr().out
    with identity_setup['owner_factory']() as db:
        before=db.execute(text('SELECT count(*) FROM ktels')).scalar_one()
        with pytest.raises(FileExistsError):
            provision_to_file(db,name='Duplicate operator',admin_email='duplicate@example.org',timezone='Europe/Athens',output=path)
        assert db.execute(text('SELECT count(*) FROM ktels')).scalar_one()==before
