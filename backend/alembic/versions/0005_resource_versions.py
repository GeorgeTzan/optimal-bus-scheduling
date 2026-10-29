"""Versioned canonical resources and stable external source references."""
from alembic import op
from sqlalchemy import text
revision='0005_resource_versions'
down_revision='0004_identity_delivery'
branch_labels=None
depends_on=None
TABLES=('domain_drivers','domain_vehicles','domain_stations')

def upgrade():
    duplicate=op.get_bind().execute(text('''SELECT 1 FROM domain_vehicles WHERE registration_plate IS NOT NULL
        GROUP BY tenant_id,lower(registration_plate) HAVING count(*)>1 LIMIT 1''')).first()
    if duplicate:
        raise RuntimeError('Duplicate vehicle registrations ignoring letter case; review source records before migration')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version>0)')
        op.execute(f'ALTER TABLE {table} ADD COLUMN external_source VARCHAR')
        op.execute(f'ALTER TABLE {table} ADD COLUMN external_key VARCHAR')
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT uq_{table}_external UNIQUE (tenant_id,external_source,external_key)')
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT ck_{table}_external CHECK ((external_source IS NULL)=(external_key IS NULL))')
    op.execute('ALTER TABLE domain_vehicles ADD COLUMN code VARCHAR')
    op.execute("UPDATE domain_vehicles SET code='V-' || id::text")
    op.execute('ALTER TABLE domain_vehicles ALTER COLUMN code SET NOT NULL')
    op.execute('ALTER TABLE domain_vehicles ADD CONSTRAINT uq_domain_vehicles_code UNIQUE(tenant_id,code)')
    op.execute('ALTER TABLE domain_vehicles ALTER COLUMN registration_plate DROP NOT NULL')
    op.execute('ALTER TABLE domain_stations ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true')
    op.execute('CREATE UNIQUE INDEX uq_domain_vehicle_registration_folded ON domain_vehicles(tenant_id,lower(registration_plate))')


def downgrade():
    raise RuntimeError('Resource version rollback requires a reviewed restore plan; never discard source/version history implicitly')
