"""Planned maintenance reservations and open out-of-service holds for vehicles."""
import sqlalchemy as sa
from alembic import op
revision = '0016_office_vehicle_periods'
down_revision = '0015_office_leave'
branch_labels = None
depends_on = None


def upgrade():
    count = op.get_bind().execute(sa.text('SELECT count(*) FROM domain_vehicle_availabilities')).scalar_one()
    if count:
        raise RuntimeError(f'domain_vehicle_availabilities holds {count} rows with unconfirmed time semantics; review them before upgrading')
    op.execute('ALTER TABLE domain_vehicle_availabilities DROP COLUMN service_date, DROP COLUMN status')
    op.execute('ALTER TABLE domain_vehicle_availabilities RENAME COLUMN start_time_utc TO start_utc')
    op.execute('ALTER TABLE domain_vehicle_availabilities RENAME COLUMN end_time_utc TO end_utc')
    op.execute("""ALTER TABLE domain_vehicle_availabilities
      ALTER COLUMN start_utc TYPE TIMESTAMPTZ USING start_utc AT TIME ZONE 'UTC', ALTER COLUMN end_utc DROP NOT NULL,
      ALTER COLUMN end_utc TYPE TIMESTAMPTZ USING end_utc AT TIME ZONE 'UTC',
      ADD COLUMN kind VARCHAR NOT NULL CHECK (kind IN ('planned_maintenance','out_of_service')),
      ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active' CHECK (status IN ('active','released','cancelled')),
      ADD COLUMN estimated_end_utc TIMESTAMPTZ, ADD COLUMN responsible_label VARCHAR(200), ADD COLUMN released_at TIMESTAMPTZ,
      ADD COLUMN released_by INTEGER, ADD COLUMN release_note VARCHAR(500), ADD COLUMN cancelled_by INTEGER, ADD COLUMN cancel_reason VARCHAR(1000),
      ADD COLUMN recorded_by INTEGER NOT NULL, ADD COLUMN recorded_at TIMESTAMPTZ NOT NULL,
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      ADD CHECK (kind<>'planned_maintenance' OR end_utc IS NOT NULL), ADD CHECK (end_utc IS NULL OR end_utc > start_utc),
      ADD CHECK (status<>'released' OR (kind='out_of_service' AND released_at IS NOT NULL AND released_by IS NOT NULL)),
      ADD FOREIGN KEY(tenant_id,recorded_by) REFERENCES users(ktel_id,id), ADD FOREIGN KEY(tenant_id,released_by) REFERENCES users(ktel_id,id),
      ADD FOREIGN KEY(tenant_id,cancelled_by) REFERENCES users(ktel_id,id)""")


def downgrade():
    raise RuntimeError('Maintenance history rollback requires a reviewed restore')
