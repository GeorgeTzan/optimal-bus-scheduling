"""Audited, idempotent successors to an immutable publication."""
from alembic import op
revision='0011_schedule_changes'
down_revision='0010_daily_operations'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE domain_schedule_changes (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), publication_id TEXT NOT NULL,
      base_revision_id TEXT NOT NULL, successor_revision_id TEXT NOT NULL, request_id VARCHAR(36) NOT NULL,
      payload_hash VARCHAR(64) NOT NULL, actor_id INTEGER NOT NULL, reason VARCHAR(1000) NOT NULL,
      changes JSON NOT NULL, response_data JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL,
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,request_id), UNIQUE(tenant_id,successor_revision_id),
      FOREIGN KEY(tenant_id,publication_id,base_revision_id) REFERENCES domain_publications(tenant_id,publication_id,revision_id),
      FOREIGN KEY(tenant_id,successor_revision_id) REFERENCES domain_schedule_revisions(tenant_id,revision_id),
      FOREIGN KEY(tenant_id,actor_id) REFERENCES users(ktel_id,id))''')
    op.execute('CREATE INDEX ix_domain_schedule_changes_tenant_id ON domain_schedule_changes(tenant_id)')
    op.execute('ALTER TABLE domain_schedule_changes ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_schedule_changes FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_schedule_changes USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')

def downgrade():
    raise RuntimeError('Schedule change history rollback requires a reviewed restore')
