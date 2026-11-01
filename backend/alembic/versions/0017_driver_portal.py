"""Driver sign-in links (invitation carries a driver) and insert-only duty acknowledgments."""
import sqlalchemy as sa
from alembic import op
revision = '0017_driver_portal'
down_revision = '0016_office_vehicle_periods'
branch_labels = None
depends_on = None


def upgrade():
    shared = op.get_bind().execute(sa.text('SELECT count(*) FROM (SELECT 1 FROM domain_memberships WHERE driver_id IS NOT NULL GROUP BY tenant_id, driver_id HAVING count(*)>1) x')).scalar_one()
    if shared:
        raise RuntimeError(f'{shared} drivers are linked to more than one login; resolve them before upgrading')
    op.execute('ALTER TABLE domain_identity_tokens ADD COLUMN driver_id INTEGER, ADD COLUMN revoked_at TIMESTAMPTZ')
    op.execute('ALTER TABLE domain_identity_tokens ADD FOREIGN KEY (tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id)')
    op.execute("ALTER TABLE domain_identity_tokens ADD CHECK (driver_id IS NULL OR (kind='invitation' AND role='driver'))")
    op.execute("CREATE UNIQUE INDEX uq_invitation_driver_active ON domain_identity_tokens(tenant_id,driver_id) WHERE kind='invitation' AND consumed_at IS NULL AND revoked_at IS NULL AND driver_id IS NOT NULL")
    op.execute('CREATE UNIQUE INDEX uq_membership_driver ON domain_memberships(tenant_id,driver_id) WHERE driver_id IS NOT NULL')
    op.execute('''CREATE TABLE domain_driver_acknowledgments (
      id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), publication_id VARCHAR NOT NULL, revision_id VARCHAR NOT NULL,
      revision_version INTEGER NOT NULL CHECK (revision_version>0), trip_id VARCHAR NOT NULL, driver_id INTEGER NOT NULL, acknowledged_by INTEGER NOT NULL,
      acknowledged_at TIMESTAMPTZ NOT NULL, request_id VARCHAR(36) NOT NULL,
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,publication_id,trip_id,driver_id), UNIQUE(tenant_id,request_id,trip_id),
      FOREIGN KEY(tenant_id,driver_id) REFERENCES domain_drivers(tenant_id,id),
      FOREIGN KEY(tenant_id,acknowledged_by) REFERENCES users(ktel_id,id),
      FOREIGN KEY(tenant_id,publication_id,revision_id) REFERENCES domain_publications(tenant_id,publication_id,revision_id))''')
    op.execute('CREATE INDEX ix_domain_driver_acknowledgments_tenant_id ON domain_driver_acknowledgments(tenant_id)')
    op.execute('ALTER TABLE domain_driver_acknowledgments ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_driver_acknowledgments FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_driver_acknowledgments USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')


def downgrade():
    raise RuntimeError('Acknowledgment history rollback requires a reviewed restore')
