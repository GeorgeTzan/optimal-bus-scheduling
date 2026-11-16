"""Reason for uncovered trips at publication and the monthly report export log."""
from alembic import op

revision = '0021_management_reports'
down_revision = '0020_import_route_rules'
branch_labels = None
depends_on = None
REASONS = "'no_driver','driver_leave','no_vehicle','work_rules','other'"


def upgrade():
    op.execute(f'ALTER TABLE domain_publications ADD COLUMN uncovered_reason VARCHAR(20) NULL CHECK (uncovered_reason IN ({REASONS})), ADD COLUMN uncovered_note VARCHAR(500) NULL')
    op.execute('''CREATE TABLE domain_report_exports (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), month DATE NOT NULL,
      format VARCHAR(8) NOT NULL CHECK (format IN ('xlsx','pdf')), generated_by INTEGER NOT NULL,
      generated_at TIMESTAMPTZ NOT NULL DEFAULT now(), fingerprint VARCHAR NOT NULL,
      FOREIGN KEY(tenant_id,generated_by) REFERENCES users(ktel_id,id))''')
    op.execute('CREATE INDEX ix_domain_report_exports_tenant_id ON domain_report_exports(tenant_id)')
    op.execute('CREATE INDEX ix_domain_report_exports_month ON domain_report_exports(tenant_id, month, generated_at DESC)')
    op.execute('ALTER TABLE domain_report_exports ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_report_exports FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_report_exports USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')


def downgrade():
    op.execute('DROP TABLE domain_report_exports')
    op.execute('ALTER TABLE domain_publications DROP COLUMN uncovered_reason, DROP COLUMN uncovered_note')
