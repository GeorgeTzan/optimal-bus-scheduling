"""Tenant scope is transaction-local and restored on every new transaction."""
from contextlib import contextmanager
from sqlalchemy import event, text
from sqlalchemy.orm import Session


class CrossTenantAccessError(PermissionError):
    pass


def _configure(connection, tenant_id):
    if connection.dialect.name == 'postgresql':
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                           {'tenant': str(tenant_id) if tenant_id is not None else ''})


@event.listens_for(Session,'after_begin')
def _apply_scope(session,transaction,connection):
    _configure(connection,session.info.get('tenant_id'))


def set_tenant_scope(session,tenant_id):
    if isinstance(tenant_id,bool):
        raise CrossTenantAccessError('A positive organization identity is required')
    try:
        tenant_id=int(tenant_id)
    except (ValueError,TypeError):
        raise CrossTenantAccessError('A positive organization identity is required') from None
    if tenant_id<=0:
        raise CrossTenantAccessError('A positive organization identity is required')
    existing=session.info.get('tenant_id')
    if existing is not None and int(existing)!=tenant_id:
        raise CrossTenantAccessError('Cannot change organizations inside a scoped request')
    session.info['tenant_id']=str(tenant_id)
    if session.in_transaction():
        _configure(session.connection(),tenant_id)


@event.listens_for(Session,'do_orm_execute')
def _enforce_tenant_scoping(state):
    tenant_id=state.session.info.get('tenant_id')
    if tenant_id is None or not hasattr(state.statement,'where'):
        return
    if state.is_select or state.is_update or state.is_delete:
        for mapper in state.all_mappers:
            entity=mapper.class_
            scope=next((name for name in ('tenant_id','ktel_id') if hasattr(entity,name)),None)
            if mapper.persist_selectable.name=='ktels':
                scope='id'
            if scope:
                state.statement=state.statement.where(getattr(entity,scope)==int(tenant_id))


@contextmanager
def tenant_transaction(session,tenant_id):
    previous=session.info.get('tenant_id')
    set_tenant_scope(session,tenant_id)
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        if previous is None:
            session.info.pop('tenant_id',None)
        else:
            session.info['tenant_id']=previous
        if session.in_transaction():
            _configure(session.connection(),previous)
        if not session.new and not session.dirty and not session.deleted:
            session.expire_all()


@contextmanager
def system_worker_transaction(session):
    if session.info.get('tenant_id') is None:
        raise CrossTenantAccessError('Workers require an explicit tenant scope; system flags do not bypass isolation')
    yield session


def audit_tenant_schema(metadata):
    missing=[]
    for table in metadata.tables.values():
        if table.name in ('ktels','alembic_version','identity_rate_limits'):
            continue
        if not any(c.name in ('tenant_id','ktel_id') for c in table.columns):
            missing.append(f'{table.name}: missing tenant identity')
    return missing
