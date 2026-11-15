"""Company work rules, driver profiles and baselines, route rules, finding overrides and route service type."""
from alembic import op
revision = '0019_driver_work_rules'
down_revision = '0018_team_admin'
branch_labels = None
depends_on = None
TABLES = ('domain_company_work_rules', 'domain_driver_work_profiles', 'domain_driver_route_rules',
          'domain_vehicle_route_rules', 'domain_driver_work_baselines', 'domain_work_rule_overrides')


def upgrade():
    op.execute('''CREATE TABLE domain_company_work_rules (
      tenant_id INTEGER PRIMARY KEY REFERENCES ktels(id), overrides JSON NOT NULL DEFAULT '{}'::json, warning_rules JSON NOT NULL DEFAULT '[]'::json,
      version INTEGER NOT NULL DEFAULT 1 CHECK (version>0), updated_by INTEGER, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,updated_by) REFERENCES users(ktel_id,id))''')
    op.execute('''CREATE TABLE domain_driver_work_profiles (
      tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER NOT NULL,
      overnight_allowed BOOLEAN NOT NULL DEFAULT TRUE, split_shift_allowed BOOLEAN NOT NULL DEFAULT TRUE, must_return_to_base BOOLEAN NOT NULL DEFAULT FALSE,
      version INTEGER NOT NULL DEFAULT 1 CHECK (version>0), PRIMARY KEY(tenant_id,driver_id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id))''')
    op.execute('''CREATE TABLE domain_driver_route_rules (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER NOT NULL, route_id INTEGER NOT NULL,
      kind VARCHAR NOT NULL CHECK (kind IN ('prefer','forbid')), UNIQUE(tenant_id,driver_id,route_id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,route_id) REFERENCES domain_routes(tenant_id,id))''')
    op.execute('''CREATE TABLE domain_vehicle_route_rules (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), vehicle_id INTEGER NOT NULL, route_id INTEGER NOT NULL,
      UNIQUE(tenant_id,vehicle_id,route_id),
      FOREIGN KEY(tenant_id,vehicle_id) REFERENCES domain_vehicles(tenant_id,id),
      FOREIGN KEY(tenant_id,route_id) REFERENCES domain_routes(tenant_id,id))''')
    op.execute('''CREATE TABLE domain_driver_work_baselines (
      tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER NOT NULL, as_of DATE NOT NULL,
      overtime_minutes INTEGER NOT NULL DEFAULT 0 CHECK (overtime_minutes>=0), last_duty_end TIMESTAMPTZ, last_weekly_rest_end TIMESTAMPTZ,
      last_weekly_rest_at_base BOOLEAN NOT NULL DEFAULT FALSE, owed_rest_minutes INTEGER NOT NULL DEFAULT 0 CHECK (owed_rest_minutes>=0),
      version INTEGER NOT NULL DEFAULT 1 CHECK (version>0), updated_by INTEGER, PRIMARY KEY(tenant_id,driver_id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,updated_by) REFERENCES users(ktel_id,id))''')
    op.execute('''CREATE TABLE domain_work_rule_overrides (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), revision_id VARCHAR NOT NULL, finding_key VARCHAR NOT NULL,
      reason VARCHAR(1000) NOT NULL, actor_id INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(tenant_id,revision_id,finding_key),
      FOREIGN KEY(tenant_id,revision_id) REFERENCES domain_schedule_revisions(tenant_id,revision_id),
      FOREIGN KEY(tenant_id,actor_id) REFERENCES users(ktel_id,id))''')
    for table in TABLES:
        op.execute(f'CREATE INDEX ix_{table}_tenant_id ON {table}(tenant_id)')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')
    op.execute("ALTER TABLE domain_routes ADD COLUMN service_type VARCHAR NOT NULL DEFAULT 'intercity' CHECK (service_type IN ('intercity','urban'))")
    op.execute('ALTER TABLE domain_schedule_changes ADD COLUMN emergency BOOLEAN NOT NULL DEFAULT FALSE')
    op.execute('ALTER TABLE domain_drivers DROP COLUMN max_daily_driving_minutes, DROP COLUMN max_continuous_driving_minutes, DROP COLUMN min_daily_rest_minutes')


def downgrade():
    op.execute('ALTER TABLE domain_drivers ADD COLUMN max_daily_driving_minutes INTEGER, ADD COLUMN max_continuous_driving_minutes INTEGER, ADD COLUMN min_daily_rest_minutes INTEGER')
    op.execute('UPDATE domain_drivers SET max_daily_driving_minutes=540, max_continuous_driving_minutes=270, min_daily_rest_minutes=660')
    op.execute('ALTER TABLE domain_schedule_changes DROP COLUMN emergency')
    op.execute('ALTER TABLE domain_routes DROP COLUMN service_type')
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE {table}')
