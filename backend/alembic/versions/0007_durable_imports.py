"""Durable reviewed imports, stable source identities and transactional audit."""
from alembic import op
revision='0007_durable_imports'
down_revision='0006_operational_calendars'
branch_labels=None
depends_on=None

DDL=['\n'
 'CREATE TABLE domain_import_batches (\n'
 '\tbatch_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tcreated_by INTEGER NOT NULL, \n'
 '\tupdated_by INTEGER NOT NULL, \n'
 '\toriginal_filename VARCHAR NOT NULL, \n'
 '\tfile_format VARCHAR NOT NULL, \n'
 '\tfile_bytes INTEGER NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tsource_kind VARCHAR NOT NULL, \n'
 '\trequested_entity VARCHAR NOT NULL, \n'
 '\tschema_version VARCHAR NOT NULL, \n'
 '\tvalidation_version VARCHAR NOT NULL, \n'
 '\tlocale VARCHAR NOT NULL, \n'
 '\tsource_locale VARCHAR NOT NULL, \n'
 '\tentities JSONB NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\trow_count INTEGER NOT NULL, \n'
 '\tsummary JSONB NOT NULL, \n'
 '\tfile_issues JSONB NOT NULL, \n'
 '\tsource_snapshot JSONB NOT NULL, \n'
 '\tstation_resolutions JSONB NOT NULL, \n'
 '\tstation_plan JSONB NOT NULL, \n'
 '\tresult_summary JSONB, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tcommitted_at TIMESTAMP WITH TIME ZONE, \n'
 '\traw_purged_at TIMESTAMP WITH TIME ZONE, \n'
 '\tPRIMARY KEY (batch_id), \n'
 '\tUNIQUE (tenant_id, batch_id), \n'
 '\tFOREIGN KEY(tenant_id, created_by) REFERENCES users (ktel_id, id), \n'
 '\tFOREIGN KEY(tenant_id, updated_by) REFERENCES users (ktel_id, id), \n'
 "\tCHECK (status IN ('review','ready','committed','discarded','purged')), \n"
 "\tCHECK (file_format IN ('xlsx','csv')), \n"
 "\tCHECK (locale IN ('en','el') AND source_locale IN ('en','el')), \n"
 '\tCHECK (version>0 AND row_count>=0 AND file_bytes>0), \n'
 '\tCHECK (length(checksum)=64), \n'
 "\tCHECK (status<>'committed' OR (result_summary IS NOT NULL AND committed_at IS NOT NULL)), \n"
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_import_batches_tenant_id ON domain_import_batches (tenant_id)',
 'CREATE INDEX ix_import_retention ON domain_import_batches (tenant_id, expires_at, raw_purged_at)',
 'CREATE UNIQUE INDEX uq_import_active_source ON domain_import_batches (tenant_id, checksum, source_kind, '
 "schema_version) WHERE status NOT IN ('discarded','purged')",
 '\n'
 'CREATE TABLE domain_import_rows (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tbatch_id VARCHAR NOT NULL, \n'
 '\tposition INTEGER NOT NULL, \n'
 '\tentity VARCHAR NOT NULL, \n'
 '\tsheet VARCHAR NOT NULL, \n'
 '\trow_number INTEGER NOT NULL, \n'
 '\traw JSONB NOT NULL, \n'
 '\tcell_types JSONB NOT NULL, \n'
 '\tsource_columns JSONB NOT NULL, \n'
 '\tsource_cells JSONB NOT NULL, \n'
 '\tvalues JSONB NOT NULL, \n'
 '\tissues JSONB NOT NULL, \n'
 '\tresolution JSONB NOT NULL, \n'
 '\tplanned_reference VARCHAR, \n'
 '\tplan JSONB NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tUNIQUE (tenant_id, batch_id, position), \n'
 '\tFOREIGN KEY(tenant_id, batch_id) REFERENCES domain_import_batches (tenant_id, batch_id), \n'
 '\tCHECK (position>=0 AND row_number>=2), \n'
 "\tCHECK (entity IN ('drivers','vehicles','stations','timetable','pairings','transfers')), \n"
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_import_rows_batch_id ON domain_import_rows (batch_id)',
 'CREATE INDEX ix_domain_import_rows_tenant_id ON domain_import_rows (tenant_id)',
 '\n'
 'CREATE TABLE domain_import_identities (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tentity VARCHAR NOT NULL, \n'
 '\tsource VARCHAR NOT NULL, \n'
 '\texternal_key VARCHAR NOT NULL, \n'
 '\tdriver_id INTEGER, \n'
 '\tvehicle_id INTEGER, \n'
 '\tstation_id INTEGER, \n'
 '\ttemplate_id INTEGER, \n'
 '\tbatch_id VARCHAR NOT NULL, \n'
 '\tcreated_by INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tUNIQUE (tenant_id, entity, source, external_key), \n'
 '\tFOREIGN KEY(tenant_id, driver_id) REFERENCES domain_drivers (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, vehicle_id) REFERENCES domain_vehicles (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, station_id) REFERENCES domain_stations (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, template_id) REFERENCES domain_service_templates (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, batch_id) REFERENCES domain_import_batches (tenant_id, batch_id), \n'
 '\tFOREIGN KEY(tenant_id, created_by) REFERENCES users (ktel_id, id), \n'
 "\tCHECK ((entity='drivers' AND driver_id IS NOT NULL AND vehicle_id IS NULL AND station_id IS NULL AND "
 'template_id IS NULL)\n'
 "          OR (entity='vehicles' AND vehicle_id IS NOT NULL AND driver_id IS NULL AND station_id IS NULL "
 'AND template_id IS NULL)\n'
 "          OR (entity='stations' AND station_id IS NOT NULL AND driver_id IS NULL AND vehicle_id IS NULL "
 'AND template_id IS NULL)\n'
 "          OR (entity='timetable' AND template_id IS NOT NULL AND driver_id IS NULL AND vehicle_id IS NULL "
 'AND station_id IS NULL)), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_import_identities_tenant_id ON domain_import_identities (tenant_id)',
 '\n'
 'CREATE TABLE domain_import_audit (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tbatch_id VARCHAR NOT NULL, \n'
 '\tactor_id INTEGER, \n'
 '\tactor_type VARCHAR NOT NULL, \n'
 '\tevent VARCHAR NOT NULL, \n'
 '\tbatch_version INTEGER NOT NULL, \n'
 '\tdetails JSONB NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, batch_id) REFERENCES domain_import_batches (tenant_id, batch_id), \n'
 '\tFOREIGN KEY(tenant_id, actor_id) REFERENCES users (ktel_id, id), \n'
 "\tCHECK (actor_type IN ('user','retention')), \n"
 '\tCHECK (batch_version>0), \n'
 "\tCHECK (actor_type<>'user' OR actor_id IS NOT NULL), \n"
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_import_audit_batch_id ON domain_import_audit (batch_id)',
 'CREATE INDEX ix_domain_import_audit_tenant_id ON domain_import_audit (tenant_id)']

def upgrade():
    for statement in DDL:op.execute(statement)
    for table in ('domain_import_batches','domain_import_rows','domain_import_identities','domain_import_audit'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')

def downgrade():
    raise RuntimeError('Import history rollback requires a reviewed restore; do not discard customer audit implicitly')
