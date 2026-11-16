import secrets
from dataclasses import dataclass,field
from datetime import datetime,timezone
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from db.models import KTEL,User
from app.domain.identity.mail import support_email
from app.domain.identity.models import Membership
from app.domain.identity.permissions import PERMISSIONS
from app.domain.identity.service import digest
from app.domain.identity.tenant_session import tenant_transaction

COOKIE='ktel_support_session'
ENTRY_LIMIT=200
REFUSALS={'KT401':(403,'support_access_not_enabled','Support access is not enabled by this customer.'),
          'KT403':(403,'organization_suspended','This customer is suspended.'),
          'KT404':(404,None,'Customer not found')}


class SupportError(Exception):
    def __init__(self,status,code,message):
        super().__init__(message)
        self.status,self.code,self.message=status,code,message


@dataclass
class SupportPrincipal:
    ktel_id:int
    ktel:KTEL
    session_id:str
    support_session:dict
    id:int=0
    membership_id:int=0
    email:str|None=None
    full_name:str='Platform support'
    is_active:bool=True
    is_admin:bool=False
    role:str='support'
    ktel_name:str|None=None
    permissions:list=field(default_factory=lambda:sorted(PERMISSIONS['support']))


def start(db,operator,tenant_id,*,reason,ticket,ip):
    token=secrets.token_urlsafe(32)
    try:
        ends_at=db.execute(text('SELECT public.platform_start_support_session(:tenant,:operator,:reason,:ticket,:token_hash,:ip)'),
            {'tenant':tenant_id,'operator':operator['id'],'reason':reason,'ticket':ticket,'token_hash':digest(token),'ip':ip}).scalar_one()
    except DBAPIError as error:
        db.rollback()
        refusal=REFUSALS.get(getattr(error.orig,'pgcode',None))
        if refusal is None:
            raise
        raise SupportError(*refusal) from None
    db.commit()
    return token,ends_at


def end(db,operator,*,tenant_id,ip,by):
    ended=db.execute(text('SELECT public.platform_end_support_sessions(:operator,:tenant,:ip,:by)'),
                     {'operator':operator['id'],'tenant':tenant_id,'ip':ip,'by':by}).scalar_one()
    db.commit()
    return ended


def state(db,operator,tenant_id):
    row=db.execute(text('SELECT * FROM public.platform_support_state(:tenant,:operator)'),{'tenant':tenant_id,'operator':operator['id']}).mappings().first()
    if row is None:
        return None
    until=row['access_until']
    return {'access_until':until,'access_open':until is not None and until>datetime.now(timezone.utc),
            'session':{'ends_at':row['session_ends_at'].isoformat()} if row['session_ends_at'] else None}


def notify_administrators(db,tenant_id,reason,ends_at):
    try:
        with tenant_transaction(db,tenant_id):
            tenant=db.query(KTEL).filter_by(id=tenant_id).one()
            recipients=[email for (email,) in db.query(User.email).join(Membership,Membership.user_id==User.id).filter(
                Membership.role=='admin',Membership.is_active.is_(True),User.is_active.is_(True)).order_by(User.id)]
            if not recipients:
                return 'no_recipients'
            rows=[support_email(tenant_id,email,tenant.name,reason,ends_at) for email in recipients]
            db.add_all(rows)
            db.commit()
            return rows[0].delivery_status
    except Exception:
        db.rollback()
        return 'failed'


def resolve(db,token,*,method,path,ip):
    row=db.execute(text('SELECT * FROM public.ktel_support_request(:token_hash,:method,:path,:ip)'),
                   {'token_hash':digest(token),'method':method,'path':path,'ip':ip}).mappings().first()
    db.commit()
    return dict(row) if row else None


def principal(db,found):
    tenant=db.query(KTEL).filter_by(id=found['support_tenant_id']).one()
    return SupportPrincipal(ktel_id=tenant.id,ktel=tenant,session_id=f"support-{found['support_session_id']}",
                            support_session={'ends_at':found['support_ends_at'].isoformat()})


def active_session(db,tenant_id):
    if db.get_bind().dialect.name!='postgresql':
        return None
    ends_at=db.execute(text('''SELECT max(least(s.expires_at,k.support_access_until)) FROM platform_support_sessions s JOIN ktels k ON k.id=s.tenant_id
        WHERE s.tenant_id=:tenant AND s.ended_at IS NULL AND s.expires_at>now() AND k.support_access_until>now()'''),{'tenant':tenant_id}).scalar()
    return {'ends_at':ends_at.isoformat()} if ends_at else None


def set_access(db,tenant_id,enabled):
    if enabled:
        db.execute(text("UPDATE ktels SET support_access_until=now()+interval '24 hours' WHERE id=:tenant"),{'tenant':tenant_id})
    else:
        db.execute(text('UPDATE ktels SET support_access_until=now() WHERE id=:tenant'),{'tenant':tenant_id})
        db.execute(text('SELECT public.ktel_end_support_sessions()'))


def access_view(db,tenant_id):
    until,open_=db.execute(text('SELECT support_access_until,coalesce(support_access_until>now(),false) FROM ktels WHERE id=:tenant'),{'tenant':tenant_id}).one()
    entries=db.execute(text('''SELECT action,reason,ticket,method,path,ends_at,at FROM (
        (SELECT id,action,reason,ticket,detail->>'method' AS method,detail->>'path' AS path,detail->>'ends_at' AS ends_at,at
          FROM platform_audit WHERE tenant_id=:tenant AND action<>'support_request' ORDER BY at DESC,id DESC LIMIT :limit)
        UNION ALL
        (SELECT id,action,reason,ticket,detail->>'method',detail->>'path',detail->>'ends_at',at
          FROM platform_audit WHERE tenant_id=:tenant AND action='support_request' ORDER BY at DESC,id DESC LIMIT :limit)) AS entries
        ORDER BY at DESC,id DESC'''),{'tenant':tenant_id,'limit':ENTRY_LIMIT}).mappings().all()
    return {'enabled':open_,'until':until,'session':active_session(db,tenant_id),
            'entries':[{**entry,'actor':'platform_support'} for entry in entries]}
