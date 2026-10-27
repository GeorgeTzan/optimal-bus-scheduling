"""Audit real PostgreSQL tenancy, including enforcement beyond ORM query filters."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from sqlalchemy import inspect, text


def boundary_manifest():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0002_tenant_boundaries.py'
    spec = spec_from_file_location('ktel_frozen_tenant_boundaries',path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_database_tenancy(connection, runtime_roles=()):
    manifest = boundary_manifest()
    inspector = inspect(connection)
    issues = []
    enforced = {row[0]: row[1:] for row in connection.execute(text('''SELECT relname,relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner)
        FROM pg_class JOIN pg_namespace ON pg_namespace.oid=relnamespace
        WHERE nspname='public' AND relkind='r' '''))}
    scopes = dict(manifest.SCOPES)
    # Include new tenant tables so the audit cannot accidentally cover just the original list.
    for table in inspector.get_table_names():
        if table not in scopes:
            scope = next((c['name'] for c in inspector.get_columns(table) if c['name'] in ('tenant_id','ktel_id')),None)
            if scope:
                scopes[table] = scope
    from db.metadata import load_domain_metadata
    metadata=load_domain_metadata()
    for model_table in metadata.tables.values():
        scope=next((column.name for column in model_table.columns if column.name in ('tenant_id','ktel_id')),None)
        if scope:scopes.setdefault(model_table.name,scope)
    for table in scopes:
        state = enforced.get(table)
        if not state or not state[0] or not state[1]:
            issues.append(f'{table}: RLS and FORCE RLS required')
            continue
        if state[2] in runtime_roles:
            issues.append(f'{table}: runtime role owns table')
        policies = connection.execute(text("SELECT policyname,qual,with_check,cmd,permissive,roles::text FROM pg_policies WHERE schemaname='public' AND tablename=:table"),{'table':table}).all()
        def normalized(value):return ''.join((value or '').replace('"','').replace('public.','').split())
        expected_policy=f'({scopes[table]}=ktel_current_tenant())'
        if (len(policies)!=1 or policies[0][0]!='tenant_isolation'
            or any(normalized(clause)!=expected_policy for clause in policies[0][1:3])
            or tuple(policies[0][3:])!=('ALL','PERMISSIVE','{public}')):
            issues.append(f'{table}: missing, permissive or additional tenant isolation policy')
    expected_relations=set()
    for table,columns,parent,referenced in manifest.FOREIGN_KEYS:
        expected_relations.add((table,tuple([scopes[table],*columns]),parent,tuple([scopes[parent],*referenced])))
    # Current model relationships extend the frozen baseline; dropping a new composite FK must be visible too.
    for table in metadata.tables.values():
        if table.name not in scopes:continue
        for constraint in table.foreign_key_constraints:
            parent=constraint.referred_table.name
            if parent not in scopes or parent=='ktels':continue
            pairs=[(element.parent.name,element.column.name) for element in constraint.elements]
            pairs=[pair for pair in pairs if pair!=(scopes[table.name],scopes[parent])]
            columns=(scopes[table.name],*(pair[0] for pair in pairs))
            referenced=(scopes[parent],*(pair[1] for pair in pairs))
            expected_relations.add((table.name,columns,parent,referenced))
    actual_by_table={}
    for table,columns,parent,referenced in sorted(expected_relations):
        if table not in enforced:continue
        if table not in actual_by_table:
            actual_by_table[table]={(tuple(fk['constrained_columns']),fk['referred_table'],tuple(fk['referred_columns'])) for fk in inspector.get_foreign_keys(table)}
        if (columns,parent,referenced) not in actual_by_table[table]:
            issues.append(f'{table}.{list(columns)}: missing composite tenant foreign key')
    for role in runtime_roles:
        flags=connection.execute(text('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:role'),{'role':role}).first()
        if not flags or any(flags):
            issues.append(f'{role}: unsafe runtime role privileges')
    return issues


def grant_runtime_access(connection,role, *, authenticate=False):
    quoted = connection.dialect.identifier_preparer.quote(role)
    connection.execute(text(f'GRANT USAGE ON SCHEMA public TO {quoted}'))
    # Refreshing grants must also remove broader grants from an older release.
    connection.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {quoted}'))
    connection.execute(text(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {quoted}'))
    connection.execute(text(f'GRANT SELECT ON alembic_version TO {quoted}'))
    inspector=inspect(connection)
    available=set(inspector.get_table_names())
    if authenticate:
        access={table:'SELECT, INSERT, UPDATE, DELETE' for table in available
            if any(c['name'] in ('tenant_id','ktel_id') for c in inspector.get_columns(table))}
        access['ktels']='SELECT, UPDATE'
        if 'domain_import_audit' in available:access['domain_import_audit']='SELECT, INSERT'
        if 'domain_operational_events' in available:access['domain_operational_events']='SELECT, INSERT'
        if 'domain_schedule_changes' in available:access['domain_schedule_changes']='SELECT, INSERT'
        if 'domain_office_audit' in available:access['domain_office_audit']='SELECT, INSERT'
        if 'domain_driver_acknowledgments' in available:access['domain_driver_acknowledgments']='SELECT, INSERT'
        if 'domain_revision_crews' in available:access['domain_revision_crews']='SELECT, INSERT'
    else:
        access={table:privileges for table,privileges in {
            'domain_jobs':'SELECT, UPDATE', 'domain_outbox_events':'SELECT, INSERT',
            'domain_revision_snapshots':'SELECT', 'domain_drivers':'SELECT', 'domain_vehicles':'SELECT',
            'domain_email_outbox':'SELECT, UPDATE', 'domain_identity_tokens':'SELECT',
        }.items() if table in available}
    for table,privileges in access.items():
        connection.execute(text(f'GRANT {privileges} ON "{table}" TO {quoted}'))
        if 'INSERT' in privileges and any(c['name']=='id' for c in inspector.get_columns(table)):
            sequence=connection.execute(text("SELECT pg_get_serial_sequence(:table,'id')"),{'table':table}).scalar_one()
            if sequence:
                connection.execute(text(f'GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {quoted}'))
    signatures=[f'public.{function}(text)' for function in
                ('ktel_login_identity','ktel_token_identity','ktel_session_by_token','ktel_session_by_id','ktel_identity_token')]
    signatures.append('public.ktel_auth_budget(text,integer,integer)')
    for signature in signatures:
        if connection.execute(text('SELECT to_regprocedure(:signature)'),{'signature':signature}).scalar_one() is not None:
            connection.execute(text(f'REVOKE ALL ON FUNCTION {signature} FROM {quoted}'))
            if authenticate:
                connection.execute(text(f'GRANT EXECUTE ON FUNCTION {signature} TO {quoted}'))
    # Only the mail worker may list the organizations that have mail waiting (ids only).
    if connection.execute(text("SELECT to_regprocedure('public.ktel_mail_tenants()')")).scalar_one() is not None:
        connection.execute(text(f'REVOKE ALL ON FUNCTION public.ktel_mail_tenants() FROM {quoted}'))
        if not authenticate:
            connection.execute(text(f'GRANT EXECUTE ON FUNCTION public.ktel_mail_tenants() TO {quoted}'))


def assert_runtime_role(connection):
    if connection.dialect.name != 'postgresql':
        raise RuntimeError('A least-privilege PostgreSQL runtime connection is required')
    flags=connection.execute(text('''SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole
        FROM pg_roles WHERE rolname=current_user''')).one()
    owns=connection.execute(text('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND pg_has_role(current_user,c.relowner,'MEMBER'))''')).scalar_one()
    can_create=connection.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
    if any(flags) or owns or can_create:
        raise RuntimeError('A least-privilege non-owner database role without schema creation or RLS bypass is required')
