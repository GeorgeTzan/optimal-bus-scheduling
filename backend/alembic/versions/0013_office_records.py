"""Office grants, leave approval routes and append-only office history."""
from alembic import op
revision = '0013_office_records'
down_revision = '0012_schedule_cancellation'
branch_labels = None
depends_on = None
TABLES = ('domain_office_grants', 'domain_leave_approval_routes', 'domain_office_audit')


def upgrade():
    op.execute('''CREATE TABLE domain_office_grants (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), membership_id INTEGER NOT NULL,
      capability VARCHAR NOT NULL CHECK (capability IN ('availability.manage','maintenance.manage','maintenance.release','office.notes.read')),
      is_active BOOLEAN NOT NULL DEFAULT TRUE, granted_by INTEGER NOT NULL, granted_at TIMESTAMPTZ NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,membership_id,capability),
      FOREIGN KEY(tenant_id,membership_id) REFERENCES domain_memberships(tenant_id,id),
      FOREIGN KEY(tenant_id,granted_by) REFERENCES users(ktel_id,id))''')
    op.execute('''CREATE TABLE domain_leave_approval_routes (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), driver_id INTEGER, membership_id INTEGER,
      external_contact_name VARCHAR(200), is_active BOOLEAN NOT NULL DEFAULT TRUE, created_by INTEGER NOT NULL,
      created_at TIMESTAMPTZ NOT NULL, version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
      CHECK ((membership_id IS NULL) <> (external_contact_name IS NULL)), UNIQUE(tenant_id,id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,membership_id) REFERENCES domain_memberships(tenant_id,id),
      FOREIGN KEY(tenant_id,created_by) REFERENCES users(ktel_id,id))''')
    op.execute('''CREATE TABLE domain_office_audit (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), entity VARCHAR NOT NULL, action VARCHAR NOT NULL,
      actor_id INTEGER NOT NULL, request_id VARCHAR(36) NOT NULL, payload_hash VARCHAR(64) NOT NULL,
      response_data JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL,
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,request_id), FOREIGN KEY(tenant_id,actor_id) REFERENCES users(ktel_id,id))''')
    for table in TABLES:
        op.execute(f'CREATE INDEX ix_{table}_tenant_id ON {table}(tenant_id)')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')


def downgrade():
    raise RuntimeError('Office history rollback requires a reviewed restore')
