import hashlib
import hmac
import json
import secrets
from functools import cache
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from config import settings
from core.security import hash_password,verify_password
from app.domain.identity.service import digest
from app.domain.identity.throttle import consume_budget
from app.domain.platform import totp

SESSION_IDLE_SECONDS=60*60
MIN_PASSWORD_LENGTH=12
TOTP_ATTEMPT_LIMIT=10
TOTP_ATTEMPT_SECONDS=900


def record(db,*,operator_id,tenant_id,action,reason=None,ticket=None,detail=None,ip):
    db.execute(text('''INSERT INTO platform_audit(operator_id,tenant_id,action,reason,ticket,detail,ip)
        VALUES (:operator_id,:tenant_id,:action,:reason,:ticket,CAST(:detail AS jsonb),:ip)'''),
        {'operator_id':operator_id,'tenant_id':tenant_id,'action':action,'reason':reason,'ticket':ticket,'detail':json.dumps(detail or {}),'ip':ip})


def create_operator(db,*,email,password):
    email=email.strip().lower()
    if '@' not in email:
        raise ValueError('A valid operator email is required')
    if len(password)<MIN_PASSWORD_LENGTH:
        raise ValueError(f'The password must have at least {MIN_PASSWORD_LENGTH} characters')
    secret=totp.new_secret()
    try:
        db.execute(text('INSERT INTO platform_operators(email,password_hash,totp_secret) VALUES (:email,:password_hash,:secret)'),
                   {'email':email,'password_hash':hash_password(password),'secret':secret})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('An operator with this email already exists') from None
    return secret


@cache
def _decoy_hash():
    return hash_password(secrets.token_urlsafe(32))


def email_fingerprint(email):
    return hmac.new(settings.SECRET_KEY.encode(),email.strip().lower().encode(),hashlib.sha256).hexdigest()


def record_throttled(db,*,email,ip):
    record(db,operator_id=None,tenant_id=None,action='login_throttled',detail={'email_hash':email_fingerprint(email)},ip=ip)
    db.commit()


def sign_in(db,*,email,password,code,ip):
    email=email.strip().lower()
    operator=db.execute(text('SELECT id,password_hash,totp_secret,is_active FROM platform_operators WHERE email=:email'),{'email':email}).mappings().first()
    password_matches=verify_password(password,operator['password_hash'] if operator else _decoy_hash())
    step=None
    if operator and operator['is_active'] and password_matches and consume_budget(db,'platform_totp',str(operator['id']),'',TOTP_ATTEMPT_LIMIT,TOTP_ATTEMPT_SECONDS):
        step=totp.matching_step(operator['totp_secret'],code)
    if step is not None and not db.execute(text('''UPDATE platform_operators SET last_totp_step=:step
            WHERE id=:id AND (last_totp_step IS NULL OR last_totp_step<:step)'''),{'id':operator['id'],'step':step}).rowcount:
        step=None
    if step is None:
        record(db,operator_id=operator['id'] if operator else None,tenant_id=None,action='login_failed',
               detail=None if operator else {'email_hash':email_fingerprint(email)},ip=ip)
        db.commit()
        return None
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    db.execute(text('''INSERT INTO platform_sessions(operator_id,token_hash,csrf_hash,expires_at)
        VALUES (:operator_id,:token_hash,:csrf_hash,now()+make_interval(secs=>:seconds))'''),
        {'operator_id':operator['id'],'token_hash':digest(token),'csrf_hash':digest(csrf),'seconds':SESSION_IDLE_SECONDS})
    record(db,operator_id=operator['id'],tenant_id=None,action='login',ip=ip)
    db.commit()
    return token,csrf


def session_operator(db,token_hash):
    return db.execute(text('''UPDATE platform_sessions AS s SET expires_at=now()+make_interval(secs=>:seconds)
        FROM platform_operators AS o
        WHERE s.token_hash=:token_hash AND s.revoked_at IS NULL AND s.expires_at>now() AND o.id=s.operator_id AND o.is_active
        RETURNING o.id,o.email,s.id AS session_id,s.csrf_hash'''),{'token_hash':token_hash,'seconds':SESSION_IDLE_SECONDS}).mappings().first()


def sign_out(db,operator,*,ip):
    db.execute(text('UPDATE platform_sessions SET revoked_at=now() WHERE id=:id'),{'id':operator['session_id']})
    record(db,operator_id=operator['id'],tenant_id=None,action='logout',ip=ip)
    db.commit()
