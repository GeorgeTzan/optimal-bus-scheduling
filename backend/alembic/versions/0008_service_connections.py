"""Optional tenant-owned linear same-vehicle service connections."""
from alembic import op
revision='0008_service_connections'
down_revision='0007_durable_imports'
branch_labels=None
depends_on=None

DDL=['\nCREATE TABLE domain_service_connections (\n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tincoming_template_id INTEGER NOT NULL, \n\toutgoing_template_id INTEGER NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER, \n\tupdated_by INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, incoming_template_id, outgoing_template_id), \n\tFOREIGN KEY(tenant_id, incoming_template_id) REFERENCES domain_service_templates (tenant_id, id), \n\tFOREIGN KEY(tenant_id, outgoing_template_id) REFERENCES domain_service_templates (tenant_id, id), \n\tFOREIGN KEY(tenant_id, created_by) REFERENCES users (ktel_id, id), \n\tFOREIGN KEY(tenant_id, updated_by) REFERENCES users (ktel_id, id), \n\tCHECK (incoming_template_id<>outgoing_template_id), \n\tCHECK (version>0), \n\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n)\n\n', 'CREATE INDEX ix_domain_service_connections_tenant_id ON domain_service_connections (tenant_id)', 'CREATE UNIQUE INDEX uq_service_connection_next ON domain_service_connections (tenant_id, incoming_template_id) WHERE is_active', 'CREATE UNIQUE INDEX uq_service_connection_previous ON domain_service_connections (tenant_id, outgoing_template_id) WHERE is_active']

def upgrade():
    for statement in DDL:op.execute(statement)
    op.execute("""DO $$ DECLARE name text; BEGIN
      SELECT conname INTO STRICT name FROM pg_constraint
      WHERE conrelid='domain_import_rows'::regclass AND contype='c'
        AND pg_get_constraintdef(oid) LIKE '%entity%';
      EXECUTE format('ALTER TABLE domain_import_rows DROP CONSTRAINT %I',name);
    END $$""")
    op.execute("ALTER TABLE domain_import_rows ADD CONSTRAINT ck_import_row_entity CHECK (entity IN ('drivers','vehicles','stations','timetable','pairings','transfers','connections'))")
    op.execute('ALTER TABLE domain_service_connections ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE domain_service_connections FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON domain_service_connections USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')

def downgrade():
    raise RuntimeError('Connection history rollback requires a reviewed restore')
