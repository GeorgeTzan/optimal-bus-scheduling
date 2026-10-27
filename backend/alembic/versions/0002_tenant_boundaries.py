"""Frozen tenant boundaries for the existing operational tables."""
from alembic import op
from sqlalchemy import text
import hashlib

revision = '0002_tenant_boundaries'
down_revision = '0001_existing_schema'
branch_labels = None
depends_on = None

SCOPES = {'ktels': 'id',
 'domain_drivers': 'tenant_id',
 'domain_incidents': 'tenant_id',
 'domain_jobs': 'tenant_id',
 'domain_outbox_events': 'tenant_id',
 'domain_scheduling_audit_logs': 'tenant_id',
 'domain_scheduling_periods': 'tenant_id',
 'domain_stations': 'tenant_id',
 'domain_vehicles': 'tenant_id',
 'users': 'ktel_id',
 'domain_driver_availabilities': 'tenant_id',
 'domain_driver_qualifications': 'tenant_id',
 'domain_recovery_proposals': 'tenant_id',
 'domain_routes': 'tenant_id',
 'domain_schedule_revisions': 'tenant_id',
 'domain_vehicle_availabilities': 'tenant_id',
 'schedules': 'ktel_id',
 'domain_approval_requests': 'tenant_id',
 'domain_publications': 'tenant_id',
 'domain_revision_assignments': 'tenant_id',
 'domain_revision_snapshots': 'tenant_id',
 'domain_service_templates': 'tenant_id',
 'drivers': 'ktel_id',
 'solutions': 'ktel_id',
 'trips': 'ktel_id',
 'domain_trip_instances': 'tenant_id'}

FOREIGN_KEYS = [('domain_driver_availabilities', ['driver_id'], 'domain_drivers', ['id']),
 ('domain_driver_qualifications', ['driver_id'], 'domain_drivers', ['id']),
 ('domain_recovery_proposals', ['incident_id'], 'domain_incidents', ['id']),
 ('domain_routes', ['destination_station_id'], 'domain_stations', ['id']),
 ('domain_routes', ['origin_station_id'], 'domain_stations', ['id']),
 ('domain_schedule_revisions', ['period_id'], 'domain_scheduling_periods', ['id']),
 ('domain_vehicle_availabilities', ['vehicle_id'], 'domain_vehicles', ['id']),
 ('schedules', ['created_by_id'], 'users', ['id']),
 ('domain_approval_requests', ['revision_id'], 'domain_schedule_revisions', ['revision_id']),
 ('domain_publications', ['revision_id'], 'domain_schedule_revisions', ['revision_id']),
 ('domain_revision_assignments', ['revision_id'], 'domain_schedule_revisions', ['revision_id']),
 ('domain_revision_snapshots', ['revision_id'], 'domain_schedule_revisions', ['revision_id']),
 ('domain_service_templates', ['route_id'], 'domain_routes', ['id']),
 ('drivers', ['schedule_id'], 'schedules', ['id']),
 ('solutions', ['schedule_id'], 'schedules', ['id']),
 ('trips', ['schedule_id'], 'schedules', ['id']),
 ('domain_trip_instances', ['template_id'], 'domain_service_templates', ['id']),
 ('domain_trip_instances', ['destination_station_id'], 'domain_stations', ['id']),
 ('domain_trip_instances', ['origin_station_id'], 'domain_stations', ['id']),
 ('domain_drivers', ['home_station_id'], 'domain_stations', ['id']),
 ('domain_vehicles', ['home_station_id'], 'domain_stations', ['id']),
 ('domain_schedule_revisions', ['parent_revision_id'], 'domain_schedule_revisions', ['revision_id']),
 ('domain_jobs', ['snapshot_id'], 'domain_revision_snapshots', ['revision_id']),
 ('domain_outbox_events', ['job_id'], 'domain_jobs', ['job_id']),
 ('domain_scheduling_audit_logs', ['revision_id'], 'domain_schedule_revisions', ['revision_id'])]

UNIQUE_KEYS = [('domain_drivers', ['tenant_id', 'id']),
 ('domain_incidents', ['tenant_id', 'id']),
 ('domain_jobs', ['tenant_id', 'id']),
 ('domain_outbox_events', ['tenant_id', 'id']),
 ('domain_scheduling_audit_logs', ['tenant_id', 'id']),
 ('domain_scheduling_periods', ['tenant_id', 'id']),
 ('domain_stations', ['tenant_id', 'id']),
 ('domain_vehicles', ['tenant_id', 'id']),
 ('users', ['ktel_id', 'id']),
 ('domain_driver_availabilities', ['tenant_id', 'id']),
 ('domain_driver_qualifications', ['tenant_id', 'id']),
 ('domain_recovery_proposals', ['tenant_id', 'id']),
 ('domain_routes', ['tenant_id', 'id']),
 ('domain_schedule_revisions', ['tenant_id', 'id']),
 ('domain_vehicle_availabilities', ['tenant_id', 'id']),
 ('schedules', ['ktel_id', 'id']),
 ('domain_approval_requests', ['tenant_id', 'id']),
 ('domain_publications', ['tenant_id', 'id']),
 ('domain_revision_assignments', ['tenant_id', 'id']),
 ('domain_revision_snapshots', ['tenant_id', 'revision_id']),
 ('domain_service_templates', ['tenant_id', 'id']),
 ('drivers', ['ktel_id', 'id']),
 ('solutions', ['ktel_id', 'id']),
 ('trips', ['ktel_id', 'id']),
 ('domain_trip_instances', ['tenant_id', 'id']),
 ('domain_schedule_revisions', ['tenant_id', 'revision_id']),
 ('domain_jobs', ['tenant_id', 'job_id']),
 ('domain_drivers', ['tenant_id', 'code']),
 ('domain_vehicles', ['tenant_id', 'registration_plate']),
 ('domain_stations', ['tenant_id', 'code']),
 ('domain_service_templates', ['tenant_id', 'trip_code']),
 ('domain_trip_instances', ['tenant_id', 'trip_code', 'service_date']),
 ('domain_revision_assignments', ['tenant_id', 'revision_id', 'trip_id']),
 ('domain_jobs', ['tenant_id', 'idempotency_key'])]

def constraint_name(prefix, value):
    return prefix + hashlib.sha256(repr(value).encode()).hexdigest()[:18]


def preflight(connection):
    issues = []
    for table, scope in SCOPES.items():
        if table == 'ktels':
            continue
        if connection.execute(text(f'SELECT 1 FROM "{table}" WHERE "{scope}" IS NULL LIMIT 1')).first():
            issues.append(f'{table}: missing organization identity')
    for table, columns, parent, referenced in FOREIGN_KEYS:
        child_scope, parent_scope = SCOPES[table], SCOPES[parent]
        join = ' AND '.join(f'c."{col}" = p."{ref}"' for col,ref in zip(columns,referenced))
        non_null = ' AND '.join(f'c."{col}" IS NOT NULL' for col in columns)
        query = f'''SELECT 1 FROM "{table}" c LEFT JOIN "{parent}" p ON {join}
                    WHERE {non_null} AND (p."{parent_scope}" IS NULL OR c."{child_scope}" <> p."{parent_scope}") LIMIT 1'''
        if connection.execute(text(query)).first():
            issues.append(f'{table}.{columns}: cross-tenant or missing reference to {parent}')
    for table, columns in UNIQUE_KEYS:
        group = ','.join(f'"{column}"' for column in columns)
        non_null = ' AND '.join(f'"{column}" IS NOT NULL' for column in columns)
        if connection.execute(text(f'SELECT 1 FROM "{table}" WHERE {non_null} GROUP BY {group} HAVING count(*)>1 LIMIT 1')).first():
            issues.append(f'{table}.{columns}: duplicate values prevent uniqueness')
    if issues:
        raise RuntimeError('Tenant migration preflight failed; repair explicitly: ' + '; '.join(issues))


def upgrade():
    preflight(op.get_bind())
    op.execute('''CREATE FUNCTION public.ktel_current_tenant() RETURNS bigint LANGUAGE sql STABLE
        SET search_path = pg_catalog
        AS $$ SELECT CASE WHEN current_setting('app.tenant_id', true) ~ '^[1-9][0-9]{0,17}$'
                          THEN current_setting('app.tenant_id', true)::bigint ELSE NULL END $$''')
    for table, columns in UNIQUE_KEYS:
        op.create_unique_constraint(constraint_name('uq_scope_', (table,columns)),table,columns)
    for table, columns, parent, referenced in FOREIGN_KEYS:
        op.create_foreign_key(constraint_name('fk_scope_', (table,columns,parent,referenced)),table,parent,
                              [SCOPES[table],*columns],[SCOPES[parent],*referenced])
    for table, scope in SCOPES.items():
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY tenant_isolation ON "{table}" FOR ALL
            USING ("{scope}" = public.ktel_current_tenant())
            WITH CHECK ("{scope}" = public.ktel_current_tenant())''')
    # Authentication has to discover a tenant before tenant-scoped queries are possible.
    # These narrowly scoped definer functions expose no arbitrary SQL/system-bypass flag.
    op.execute('''CREATE FUNCTION public.ktel_login_identity(identity text) RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public SET row_security = off
        AS $$ SELECT * FROM public.users WHERE email = identity $$''')
    op.execute('''CREATE FUNCTION public.ktel_token_identity(identity text) RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public SET row_security = off
        AS $$ SELECT * FROM public.users WHERE id::text = identity OR email = identity $$''')
    op.execute('REVOKE ALL ON FUNCTION public.ktel_login_identity(text) FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION public.ktel_token_identity(text) FROM PUBLIC')


def downgrade():
    op.execute('DROP FUNCTION public.ktel_login_identity(text)')
    op.execute('DROP FUNCTION public.ktel_token_identity(text)')
    for table in SCOPES:
        op.execute(f'DROP POLICY tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    for table, columns, parent, referenced in reversed(FOREIGN_KEYS):
        op.drop_constraint(constraint_name('fk_scope_', (table,columns,parent,referenced)),table,type_='foreignkey')
    for table,columns in reversed(UNIQUE_KEYS):
        op.drop_constraint(constraint_name('uq_scope_', (table,columns)),table,type_='unique')
    op.execute('DROP FUNCTION public.ktel_current_tenant()')
