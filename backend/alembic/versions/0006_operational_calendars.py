"""Recurring service rules, immutable dated materialization and confirmed daily pairings."""
from alembic import op
revision='0006_operational_calendars'
down_revision='0005_resource_versions'
branch_labels=None
depends_on=None

DDL=['\n'
 'CREATE TABLE domain_service_exceptions (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\ttemplate_id INTEGER NOT NULL, \n'
 '\tservice_date DATE NOT NULL, \n'
 '\taction VARCHAR NOT NULL, \n'
 '\tdeparture_time VARCHAR, \n'
 '\tarrival_time VARCHAR, \n'
 '\tarrival_day_offset INTEGER, \n'
 '\tfold_start INTEGER, \n'
 '\tfold_end INTEGER, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tUNIQUE (tenant_id, template_id, service_date), \n'
 '\tFOREIGN KEY(tenant_id, template_id) REFERENCES domain_service_templates (tenant_id, id), \n'
 "\tCHECK (action IN ('inherit','run','cancel')), \n"
 '\tCHECK (version>0), \n'
 '\tCHECK (arrival_day_offset IS NULL OR arrival_day_offset BETWEEN 0 AND 2), \n'
 '\tCHECK (fold_start IS NULL OR fold_start IN (0,1)), \n'
 '\tCHECK (fold_end IS NULL OR fold_end IN (0,1)), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_service_exceptions_service_date ON domain_service_exceptions (service_date)',
 'CREATE INDEX ix_domain_service_exceptions_template_id ON domain_service_exceptions (template_id)',
 'CREATE INDEX ix_domain_service_exceptions_tenant_id ON domain_service_exceptions (tenant_id)',
 '\n'
 'CREATE TABLE domain_daily_pairings (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tservice_date DATE NOT NULL, \n'
 '\tdriver_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\thome_station_id INTEGER NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tis_confirmed BOOLEAN NOT NULL, \n'
 '\tconfirmed_source_hash VARCHAR, \n'
 '\tconfirmed_sources JSON, \n'
 '\tconfirmed_by INTEGER, \n'
 '\tconfirmed_at TIMESTAMP WITH TIME ZONE, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, driver_id) REFERENCES domain_drivers (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, vehicle_id) REFERENCES domain_vehicles (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, home_station_id) REFERENCES domain_stations (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, confirmed_by) REFERENCES users (ktel_id, id), \n'
 '\tCHECK (version>0), \n'
 '\tCHECK (NOT is_confirmed OR (confirmed_source_hash IS NOT NULL AND confirmed_by IS NOT NULL AND '
 'confirmed_at IS NOT NULL)), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_daily_pairings_service_date ON domain_daily_pairings (service_date)',
 'CREATE INDEX ix_domain_daily_pairings_tenant_id ON domain_daily_pairings (tenant_id)',
 'CREATE UNIQUE INDEX uq_daily_pair_driver ON domain_daily_pairings (tenant_id, service_date, driver_id) '
 'WHERE is_active',
 'CREATE UNIQUE INDEX uq_daily_pair_vehicle ON domain_daily_pairings (tenant_id, service_date, vehicle_id) '
 'WHERE is_active',
 '\n'
 'CREATE TABLE domain_station_transfers (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\torigin_station_id INTEGER NOT NULL, \n'
 '\tdestination_station_id INTEGER NOT NULL, \n'
 '\tminutes INTEGER NOT NULL, \n'
 '\tconfirmed_source_hash VARCHAR NOT NULL, \n'
 '\tsource_note VARCHAR, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tconfirmed_by INTEGER NOT NULL, \n'
 '\tconfirmed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tUNIQUE (tenant_id, origin_station_id, destination_station_id), \n'
 '\tFOREIGN KEY(tenant_id, origin_station_id) REFERENCES domain_stations (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, destination_station_id) REFERENCES domain_stations (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, confirmed_by) REFERENCES users (ktel_id, id), \n'
 '\tCHECK (minutes BETWEEN 0 AND 1440), \n'
 '\tCHECK (version>0), \n'
 '\tCHECK (origin_station_id<>destination_station_id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_station_transfers_tenant_id ON domain_station_transfers (tenant_id)']


def upgrade():
    for table in ('domain_routes','domain_service_templates'):
        op.execute(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK(version>0)')
        op.execute(f'ALTER TABLE {table} ADD COLUMN external_source VARCHAR')
        op.execute(f'ALTER TABLE {table} ADD COLUMN external_key VARCHAR')
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT uq_{table}_external UNIQUE(tenant_id,external_source,external_key)')
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT ck_{table}_external CHECK((external_source IS NULL)=(external_key IS NULL))')
    op.execute('ALTER TABLE domain_service_templates ADD COLUMN valid_from DATE')
    op.execute('ALTER TABLE domain_service_templates ADD COLUMN valid_until DATE')
    op.execute('ALTER TABLE domain_service_templates ADD COLUMN operating_weekdays JSON')
    op.execute('ALTER TABLE domain_service_templates ADD COLUMN arrival_day_offset INTEGER CHECK(arrival_day_offset BETWEEN 0 AND 2)')
    op.execute('ALTER TABLE domain_service_templates ADD COLUMN allowed_bus_types JSON')
    op.execute('ALTER TABLE domain_service_templates ADD CONSTRAINT ck_timetable_validity CHECK(valid_until>=valid_from)')
    op.execute("ALTER TABLE domain_trip_instances ALTER COLUMN start_utc TYPE TIMESTAMPTZ USING start_utc AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE domain_trip_instances ALTER COLUMN end_utc TYPE TIMESTAMPTZ USING end_utc AT TIME ZONE 'UTC'")
    op.execute('ALTER TABLE domain_trip_instances ADD COLUMN source_hash VARCHAR')
    op.execute('ALTER TABLE domain_trip_instances ADD COLUMN template_version INTEGER')
    op.execute('ALTER TABLE domain_trip_instances ADD COLUMN calendar_exception_version INTEGER')
    op.execute('ALTER TABLE domain_trip_instances DROP CONSTRAINT uq_scope_34c694ed3c7e55deea')
    op.execute('CREATE UNIQUE INDEX uq_legacy_dated_trip ON domain_trip_instances(tenant_id,trip_code,service_date) WHERE source_hash IS NULL')
    op.execute('ALTER TABLE domain_trip_instances ADD CONSTRAINT uq_materialized_trip UNIQUE(tenant_id,template_id,service_date,source_hash)')
    for statement in DDL:op.execute(statement)
    for table in ('domain_service_exceptions','domain_daily_pairings','domain_station_transfers'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} FOR ALL USING (tenant_id=public.ktel_current_tenant()) WITH CHECK(tenant_id=public.ktel_current_tenant())')


def downgrade():
    raise RuntimeError('Operational history rollback requires a reviewed restore plan')
