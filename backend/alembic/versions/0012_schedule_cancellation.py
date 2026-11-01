"""Keep cancelled services in revision history while excluding them from active work."""
from alembic import op
revision='0012_schedule_cancellation'
down_revision='0011_schedule_changes'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('ALTER TABLE domain_revision_assignments ADD COLUMN is_cancelled BOOLEAN NOT NULL DEFAULT FALSE')
    op.execute('ALTER TABLE domain_revision_assignments ADD COLUMN cancellation_reason VARCHAR(1000)')
    op.execute("ALTER TABLE domain_revision_assignments ADD CONSTRAINT ck_revision_cancellation CHECK ((NOT is_cancelled AND cancellation_reason IS NULL) OR (is_cancelled AND cancellation_reason IS NOT NULL AND btrim(cancellation_reason)<>'' AND resource_id='UNASSIGNED'))")
    op.execute("""CREATE TABLE domain_revision_crews (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), revision_id TEXT NOT NULL,
      resource_id TEXT NOT NULL, driver_id INTEGER NOT NULL, vehicle_id INTEGER NOT NULL,
      driver_version INTEGER NOT NULL CHECK(driver_version>0), vehicle_version INTEGER NOT NULL CHECK(vehicle_version>0),
      confirmed_by INTEGER NOT NULL, confirmed_at TIMESTAMPTZ NOT NULL,
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,revision_id,resource_id),
      FOREIGN KEY(tenant_id,revision_id) REFERENCES domain_schedule_revisions(tenant_id,revision_id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,vehicle_id) REFERENCES domain_vehicles(tenant_id,id),
      FOREIGN KEY(tenant_id,confirmed_by) REFERENCES users(ktel_id,id))""")
    op.execute('CREATE INDEX ix_domain_revision_crews_tenant_id ON domain_revision_crews(tenant_id)')
    op.execute('ALTER TABLE domain_revision_crews ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_revision_crews FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_revision_crews USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')

def downgrade():raise RuntimeError('Cancellation history rollback requires a reviewed restore')
