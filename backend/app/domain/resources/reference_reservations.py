"""Historical references remain reserved; cache only within the locked transaction."""
from fastapi import HTTPException


def remember_reservations(db, tenant_id, aliases):
    values={}
    for alias in aliases:
        values.setdefault((alias.entity,alias.external_key),set()).add(alias.target_id)
    db.info['reference_reservations']=(tenant_id,db.get_transaction(),values)


def is_reserved(db, tenant_id, kind, value, target_id=None, *, registration=False):
    from app.domain.imports.models import ImportIdentity
    cached=db.info.get('reference_reservations')
    if cached is None or cached[:2]!=(tenant_id,db.get_transaction()):
        aliases=db.query(ImportIdentity).filter_by(tenant_id=tenant_id).all()
        remember_reservations(db,tenant_id,aliases)
        cached=db.info['reference_reservations']
    keys=['registration:'+value.upper()] if registration else ['code:'+value]
    # Vehicle relationships accept both readable references and registrations.
    if kind=='vehicles':keys=list(set(keys+['code:'+value,'registration:'+value.upper()]))
    return any(identifier!=target_id for key in keys for identifier in cached[2].get((kind,key),()))


def check_reference(db, tenant_id, kind, value, target_id=None, *, registration=False):
    if value and is_reserved(db,tenant_id,kind,value,target_id,registration=registration):
        raise HTTPException(409,{'code':'reference_reserved','message':'This reference belongs to a previously imported record. Open that record or choose a different reference.'})
