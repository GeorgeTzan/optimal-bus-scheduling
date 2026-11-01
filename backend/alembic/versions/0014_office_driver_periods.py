"""Driver working patterns and explicit, timezone-aware driver availability periods."""
import sqlalchemy as sa
from alembic import op
revision = '0014_office_driver_periods'
down_revision = '0013_office_records'
branch_labels = None
depends_on = None


def upgrade():
    count = op.get_bind().execute(sa.text('SELECT count(*) FROM domain_driver_availabilities')).scalar_one()
    if count:
        raise RuntimeError(f'domain_driver_availabilities holds {count} rows with unconfirmed time semantics; review them before upgrading')
    op.execute('ALTER TABLE domain_driver_availabilities DROP COLUMN service_date, DROP COLUMN status')
    op.execute('ALTER TABLE domain_driver_availabilities RENAME COLUMN start_time_utc TO start_utc')
    op.execute('ALTER TABLE domain_driver_availabilities RENAME COLUMN end_time_utc TO end_utc')
    op.execute("""ALTER TABLE domain_driver_availabilities
      ALTER COLUMN start_utc TYPE TIMESTAMPTZ USING start_utc AT TIME ZONE 'UTC', ALTER COLUMN end_utc DROP NOT NULL,
      ALTER COLUMN end_utc TYPE TIMESTAMPTZ USING end_utc AT TIME ZONE 'UTC',
      ADD COLUMN kind VARCHAR NOT NULL CHECK (kind IN ('available','unavailable')),
      ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
      ADD COLUMN category VARCHAR CHECK (category IS NULL OR category IN ('sick','training','other','leave')),
      ADD COLUMN recorded_by INTEGER NOT NULL, ADD COLUMN recorded_at TIMESTAMPTZ NOT NULL,
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      ADD CHECK (kind='unavailable' OR (end_utc IS NOT NULL AND category IS NULL)), ADD CHECK (end_utc IS NULL OR end_utc > start_utc),
      ADD FOREIGN KEY(tenant_id,recorded_by) REFERENCES users(ktel_id,id)""")
    op.execute("""CREATE TABLE domain_driver_working_patterns (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER NOT NULL,
      weekday_mask INTEGER NOT NULL CHECK (weekday_mask BETWEEN 1 AND 127), local_start TIME NOT NULL, local_end TIME NOT NULL,
      ends_next_day BOOLEAN NOT NULL DEFAULT FALSE, valid_from DATE NOT NULL, valid_until DATE NOT NULL,
      status VARCHAR NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')), recorded_by INTEGER NOT NULL,
      recorded_at TIMESTAMPTZ NOT NULL, version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      CHECK (valid_until >= valid_from AND valid_until - valid_from <= 366), CHECK (ends_next_day OR local_end > local_start),
      UNIQUE(tenant_id,id), FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,recorded_by) REFERENCES users(ktel_id,id))""")
    op.execute('CREATE INDEX ix_domain_driver_working_patterns_tenant_id ON domain_driver_working_patterns(tenant_id)')
    op.execute('ALTER TABLE domain_driver_working_patterns ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_driver_working_patterns FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_driver_working_patterns USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')


def downgrade():
    raise RuntimeError('Availability history rollback requires a reviewed restore')
