"""Leave requests and their linked scheduling blockers."""
from alembic import op
revision = '0015_office_leave'
down_revision = '0014_office_driver_periods'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE domain_leave_requests (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER NOT NULL,
      start_utc TIMESTAMPTZ NOT NULL, end_utc TIMESTAMPTZ NOT NULL CHECK (end_utc > start_utc),
      category VARCHAR NOT NULL CHECK (category IN ('annual','sick','unpaid','other')), private_note VARCHAR(500),
      state VARCHAR NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','rejected','cancelled')),
      requested_by INTEGER NOT NULL, requested_at TIMESTAMPTZ NOT NULL, decided_by INTEGER,
      decision_basis VARCHAR CHECK (decision_basis IS NULL OR decision_basis IN ('member','external')), external_route_id INTEGER,
      stated_decision_maker VARCHAR(200), decided_at TIMESTAMPTZ, decision_note VARCHAR(500),
      cancelled_by INTEGER, cancelled_at TIMESTAMPTZ, cancel_reason VARCHAR(1000), version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      UNIQUE(tenant_id,id), FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,requested_by) REFERENCES users(ktel_id,id), FOREIGN KEY(tenant_id,decided_by) REFERENCES users(ktel_id,id),
      FOREIGN KEY(tenant_id,cancelled_by) REFERENCES users(ktel_id,id),
      FOREIGN KEY(tenant_id,external_route_id) REFERENCES domain_leave_approval_routes(tenant_id,id))''')
    op.execute('CREATE INDEX ix_domain_leave_requests_tenant_id ON domain_leave_requests(tenant_id)')
    op.execute('ALTER TABLE domain_leave_requests ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_leave_requests FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_leave_requests USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')
    op.execute('ALTER TABLE domain_driver_availabilities ADD COLUMN source_leave_id INTEGER, ADD FOREIGN KEY(tenant_id,source_leave_id) REFERENCES domain_leave_requests(tenant_id,id)')


def downgrade():
    raise RuntimeError('Leave history rollback requires a reviewed restore')
