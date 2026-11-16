from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from sqlalchemy import text
from app.domain.identity.mail import identity_link
from app.domain.identity.service import CLOSED_STATUSES,invitation_rows
from app.domain.platform.service import record

STATUS_ACTIONS={'suspended':'customer_suspended','cancelled':'customer_cancelled'}


class CustomerError(ValueError):
    pass


def list_customers(db,tenant_id=None):
    rows=db.execute(text('SELECT * FROM public.platform_list_customers()')).mappings().all()
    return [dict(row) for row in rows if tenant_id is None or row['id']==tenant_id]


def customer_health(db):
    rows=db.execute(text('SELECT * FROM public.platform_customer_health()')).mappings().all()
    return {row['tenant_id']:{**row,'uncovered_share_latest':None if row['uncovered_share_latest'] is None else float(row['uncovered_share_latest'])} for row in rows}


def create_customer(db,operator,*,name,region,timezone,status,trial_ends_on,admin_email,ip):
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError,ValueError):
        raise CustomerError('Unknown time zone') from None
    if status not in ('trial','active'):
        raise CustomerError('A new customer starts as trial or active')
    name=name.strip()
    if not name:
        raise CustomerError('An organization name is required')
    rows=invitation_rows(None,admin_email,'admin',name)
    tenant_id=db.execute(text('''SELECT public.platform_create_customer(:name,:region,:timezone,:status,:trial_ends_on,:admin_email,
        :token_id,:token_hash,:expires_at,:outbox_id,:encrypted_payload,:delivery_status)'''),
        {'name':name,'region':region,'timezone':timezone,'status':status,'trial_ends_on':trial_ends_on,'admin_email':rows.token.email,
         'token_id':rows.token.id,'token_hash':rows.token.token_hash,'expires_at':rows.token.expires_at,'outbox_id':rows.email.id,
         'encrypted_payload':rows.email.encrypted_payload,'delivery_status':rows.email.delivery_status}).scalar_one()
    record(db,operator_id=operator['id'],tenant_id=tenant_id,action='customer_created',detail={'status':status},ip=ip)
    db.commit()
    return tenant_id,identity_link(rows.secret)


def update_customer(db,operator,tenant_id,changes,*,ip):
    current=next(iter(list_customers(db,tenant_id)),None)
    if current is None:
        return None
    details={key:value for key,value in changes.items() if key!='status' and value!=current[key]}
    if details:
        merged={**current,**details}
        db.execute(text('SELECT public.platform_update_customer(:id,:plan_note,:trial_ends_on,:region)'),
                   {'id':tenant_id,'plan_note':merged['plan_note'],'trial_ends_on':merged['trial_ends_on'],'region':merged['region']})
        record(db,operator_id=operator['id'],tenant_id=tenant_id,action='customer_updated',detail={key:str(value) if value is not None else None for key,value in details.items()},ip=ip)
    status=changes.get('status',current['status'])
    if status!=current['status']:
        db.execute(text('SELECT public.platform_set_status(:id,:status)'),{'id':tenant_id,'status':status})
        action=STATUS_ACTIONS.get(status,'customer_reactivated' if current['status'] in CLOSED_STATUSES else 'customer_status_changed')
        record(db,operator_id=operator['id'],tenant_id=tenant_id,action=action,detail={'from':current['status'],'to':status},ip=ip)
    db.commit()
    return list_customers(db,tenant_id)[0]
