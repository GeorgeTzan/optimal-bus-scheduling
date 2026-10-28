"""Atomic identity actions. All tokens are random, hashed, expiring and single-use."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import hashlib
import secrets
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from db.models import KTEL,User
from core.security import hash_password,create_access_token
from app.domain.identity.models import Membership,AuthSession,IdentityToken,ROLES
from app.domain.identity.tenant_session import tenant_transaction

SESSION_SECONDS=8*60*60


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class IssuedInvitation:
    tenant_id:int
    token:str
    email:str
    role:str


@dataclass(frozen=True)
class SessionCredentials:
    cookie_token:str
    csrf_token:str
    bearer_token:str
    session_id:str


def _refuse(status,code,message):
    raise HTTPException(status,{'code':code,'message':message})


def issue_invitation(db,tenant_id,email,role='viewer',driver_id=None):
    if role not in ROLES:
        raise ValueError('Unsupported organization role')
    if driver_id is not None and role!='driver':
        raise ValueError('Only the driver role can be linked to a driver record')
    db.query(KTEL).filter_by(id=tenant_id).with_for_update().one()
    email=email.strip().lower()
    now=datetime.now(timezone.utc)
    if driver_id is not None:
        from app.domain.workforce.models import WorkforceDriver
        driver=db.query(WorkforceDriver).filter_by(tenant_id=tenant_id,id=driver_id).first()
        if driver is None:
            raise HTTPException(404,'Driver not found in your organization')
        if not driver.is_active:
            _refuse(409,'driver_archived','This driver is archived and cannot be invited.')
        if db.query(Membership.id).filter_by(tenant_id=tenant_id,driver_id=driver_id).first() is not None:
            _refuse(409,'driver_already_linked','This driver already has a linked sign-in. Unlink it first.')
        mine=db.query(IdentityToken).filter_by(tenant_id=tenant_id,driver_id=driver_id,kind='invitation').filter(
            IdentityToken.consumed_at.is_(None),IdentityToken.revoked_at.is_(None))
        if mine.filter(IdentityToken.expires_at>now).first() is not None:
            _refuse(409,'driver_invite_pending','An invitation for this driver is still pending. Revoke it to send another.')
        mine.update({'revoked_at':now},synchronize_session=False)  # expired invitations stop occupying the driver
    db.query(IdentityToken).filter_by(tenant_id=tenant_id,email=email,kind='invitation').filter(
        IdentityToken.consumed_at.is_(None)).update({'expires_at':now,'revoked_at':now},synchronize_session=False)
    secret=secrets.token_urlsafe(32)
    token=IdentityToken(id=str(uuid4()),tenant_id=tenant_id,token_hash=digest(secret),kind='invitation',
        email=email.strip().lower(),role=role,driver_id=driver_id,expires_at=datetime.now(timezone.utc)+timedelta(days=2))
    db.add(token);db.flush()
    from app.domain.identity.mail import enqueue_identity_email
    tenant=db.query(KTEL).filter_by(id=tenant_id).one()
    enqueue_identity_email(db,token,secret,tenant.name)
    return IssuedInvitation(tenant_id,secret,email.strip().lower(),role)


def provision_organization(db,*,name,admin_email,timezone='Europe/Athens'):
    ZoneInfo(timezone)
    tenant=KTEL(name=name.strip(),timezone=timezone)
    db.add(tenant);db.flush()
    with tenant_transaction(db,tenant.id):
        invitation=issue_invitation(db,tenant.id,admin_email,'admin')
        db.commit()
    return invitation


def create_session(db,user,membership):
    if not user.is_active or not membership.is_active:
        raise HTTPException(403,'Your organization membership is inactive')
    secret=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    session=AuthSession(id=str(uuid4()),tenant_id=membership.tenant_id,user_id=user.id,
        membership_id=membership.id,token_hash=digest(secret),csrf_hash=digest(csrf),
        expires_at=datetime.now(timezone.utc)+timedelta(seconds=SESSION_SECONDS))
    db.add(session);db.flush()
    bearer=create_access_token({'sub':str(user.id),'sid':session.id,'exp':session.expires_at})
    return SessionCredentials(secret,csrf,bearer,session.id)


def token_lookup(db,secret):
    token_hash=digest(secret)
    if db.get_bind().dialect.name=='postgresql':
        return db.query(IdentityToken).from_statement(text('SELECT * FROM public.ktel_identity_token(:hash)')).params(hash=token_hash).first()
    return db.query(IdentityToken).filter(IdentityToken.token_hash==token_hash,
        IdentityToken.consumed_at.is_(None),IdentityToken.expires_at>datetime.now(timezone.utc)).first()


def valid_invitation(db,secret):
    token=token_lookup(db,secret)
    if token is None or token.kind!='invitation':
        raise HTTPException(400,'This invitation is invalid, expired or has already been used. Ask your administrator for a new link.')
    return token


def _relink_existing_driver_login(db,token,password):
    """An unlinked driver login of this organization may take a new driver invitation to its own mailbox: the link proves the mailbox, as a password reset does.
    Anything else (another organization, another role, a login that is still linked) stays refused."""
    if token.driver_id is None:
        return None
    user=db.query(User).filter(User.email==token.email,User.ktel_id==token.tenant_id).first()
    member=db.query(Membership).filter_by(tenant_id=token.tenant_id,user_id=user.id).with_for_update().first() if user else None
    if member is None or member.role!='driver' or member.driver_id is not None or not member.is_active or not user.is_active:
        return None
    member.driver_id=token.driver_id;member.version+=1
    user.hashed_password=hash_password(password)
    db.query(AuthSession).filter_by(tenant_id=token.tenant_id,user_id=user.id).filter(AuthSession.revoked_at.is_(None)).update(
        {'revoked_at':datetime.now(timezone.utc)},synchronize_session=False)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        _refuse(409,'driver_already_linked','This driver already has a linked sign-in. Ask your administrator for a new invitation.')
    credentials=create_session(db,user,member)
    token.consumed_at=datetime.now(timezone.utc)
    db.commit()
    return credentials


def accept_invitation(db,secret,password,full_name):
    token=valid_invitation(db,secret)
    with tenant_transaction(db,token.tenant_id):
        db.query(KTEL).filter_by(id=token.tenant_id).with_for_update().one()
        token=db.query(IdentityToken).filter_by(id=token.id).populate_existing().with_for_update().one()
        if token.consumed_at is not None or utc(token.expires_at)<=datetime.now(timezone.utc):
            raise HTTPException(400,'This invitation has expired or already been used')
        # Global email identity is checked through the narrow authentication lookup.
        from app.domain.identity.lookup import lookup_identity
        if token.driver_id is not None:
            from app.domain.workforce.models import WorkforceDriver
            driver=db.query(WorkforceDriver).filter_by(tenant_id=token.tenant_id,id=token.driver_id).first()
            if driver is None or not driver.is_active:
                _refuse(409,'driver_archived','This driver record is archived. Ask your administrator.')
        if lookup_identity(db,token.email,login=True) is not None:
            relinked=_relink_existing_driver_login(db,token,password)
            if relinked is None:
                raise HTTPException(409,'An account already exists for this email. Sign in or ask an administrator for help.')
            return relinked
        user=User(email=token.email,full_name=full_name.strip(),hashed_password=hash_password(password),
                  ktel_id=token.tenant_id,is_active=True,is_admin=token.role=='admin')
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'An account already exists for this email. Sign in or ask an administrator for help.') from None
        member=Membership(tenant_id=token.tenant_id,user_id=user.id,role=token.role,is_active=True,driver_id=token.driver_id)
        db.add(member)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if token.driver_id is not None:
                _refuse(409,'driver_already_linked','This driver already has a linked sign-in. Ask your administrator for a new invitation.')
            raise
        credentials=create_session(db,user,member)
        token.consumed_at=datetime.now(timezone.utc)
        db.commit()
        return credentials


def session_lookup(db,identifier,*,by_id=False):
    if db.get_bind().dialect.name=='postgresql':
        function='ktel_session_by_id' if by_id else 'ktel_session_by_token'
        return db.query(AuthSession).from_statement(text(f'SELECT * FROM public.{function}(:identifier)')).params(identifier=identifier).first()
    field=AuthSession.id if by_id else AuthSession.token_hash
    return db.query(AuthSession).filter(field==identifier,AuthSession.revoked_at.is_(None),
        AuthSession.expires_at>datetime.now(timezone.utc)).first()


def request_password_reset(db,email):
    from app.domain.identity.lookup import lookup_identity
    from app.domain.identity.mail import enqueue_identity_email
    user=lookup_identity(db,email.strip().lower(),login=True)
    if user is None or not user.is_active or user.ktel_id is None:
        return
    with tenant_transaction(db,user.ktel_id):
        member=db.query(Membership).filter_by(user_id=user.id,is_active=True).first()
        if member is None:
            return
        now=datetime.now(timezone.utc)
        db.query(IdentityToken).filter_by(user_id=user.id,kind='reset').filter(
            IdentityToken.consumed_at.is_(None)).update({'expires_at':now},synchronize_session=False)
        secret=secrets.token_urlsafe(32)
        token=IdentityToken(id=str(uuid4()),tenant_id=user.ktel_id,user_id=user.id,email=user.email,
            token_hash=digest(secret),kind='reset',expires_at=now+timedelta(minutes=30))
        db.add(token);db.flush()
        tenant=db.query(KTEL).filter_by(id=user.ktel_id).one()
        enqueue_identity_email(db,token,secret,tenant.name)
        db.commit()


def confirm_password_reset(db,secret,password):
    token=token_lookup(db,secret)
    if token is None or token.kind!='reset':
        raise HTTPException(400,'This reset link is invalid, expired or already used. Request a new one.')
    with tenant_transaction(db,token.tenant_id):
        user=db.query(User).filter_by(id=token.user_id).populate_existing().with_for_update().first()
        token=db.query(IdentityToken).filter_by(id=token.id).populate_existing().with_for_update().one()
        if user is None or not user.is_active or token.consumed_at is not None or utc(token.expires_at)<=datetime.now(timezone.utc):
            raise HTTPException(400,'This reset link is invalid, expired or already used. Request a new one.')
        now=datetime.now(timezone.utc)
        user.hashed_password=hash_password(password)
        token.consumed_at=now
        db.query(AuthSession).filter_by(user_id=user.id).filter(AuthSession.revoked_at.is_(None)).update(
            {'revoked_at':now},synchronize_session=False)
        db.commit()
