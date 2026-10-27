import pytest
from sqlalchemy import inspect, text


def test_fresh_database_upgrade_creates_complete_versioned_schema(postgres_engine):
    from db.migrations import upgrade_database, current_revision
    from db.metadata import load_domain_metadata
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
        expected = set(load_domain_metadata().tables)
        assert expected <= set(inspect(connection).get_table_names())
        assert current_revision(connection) is not None
    with postgres_engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM ktels')).scalar_one() == 0


def test_existing_schema_is_adopted_explicitly_without_data_loss(postgres_engine):
    from db.metadata import load_domain_metadata
    from db.migrations import adopt_existing_database, upgrade_database, current_revision
    with postgres_engine.begin() as baseline_connection:
        from db.migrations import upgrade_database
        upgrade_database(baseline_connection, "0001_existing_schema")
        baseline_connection.execute(text("DROP TABLE alembic_version"))
    with postgres_engine.begin() as connection:
        connection.execute(text("INSERT INTO ktels (id,name) VALUES (901,'Preserve me')"))
        adopt_existing_database(connection)
        upgrade_database(connection)
        assert current_revision(connection)
        assert connection.execute(text('SELECT name FROM ktels WHERE id=901')).scalar_one() == 'Preserve me'


def test_adoption_rejects_incompatible_schema_before_stamping(postgres_engine):
    from db.metadata import load_domain_metadata
    from db.migrations import adopt_existing_database
    with postgres_engine.begin() as baseline_connection:
        from db.migrations import upgrade_database
        upgrade_database(baseline_connection, "0001_existing_schema")
        baseline_connection.execute(text("DROP TABLE alembic_version"))
    with postgres_engine.begin() as connection:
        connection.execute(text('ALTER TABLE domain_stations DROP COLUMN name_en'))
        with pytest.raises(RuntimeError, match='domain_stations.name_en'):
            adopt_existing_database(connection)
        assert not inspect(connection).has_table('alembic_version')


def test_upgrade_refuses_to_adopt_existing_tables_implicitly(postgres_engine):
    from db.metadata import load_domain_metadata
    from db.migrations import upgrade_database
    with postgres_engine.begin() as baseline_connection:
        from db.migrations import upgrade_database
        upgrade_database(baseline_connection, "0001_existing_schema")
        baseline_connection.execute(text("DROP TABLE alembic_version"))
    with postgres_engine.begin() as connection:
        with pytest.raises(RuntimeError, match='adopt'):
            upgrade_database(connection)


def test_api_startup_does_not_create_tables(restricted_databases, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(main, 'engine', restricted_databases['api'])
    monkeypatch.setattr(main.Base.metadata, 'create_all', lambda **kwargs: pytest.fail('API must not create schema'))
    with TestClient(main.app) as client:
        assert client.get('/').status_code == 200


def test_adoption_rejects_missing_foreign_keys(postgres_engine):
    from db.metadata import load_domain_metadata
    from db.migrations import adopt_existing_database
    with postgres_engine.begin() as baseline_connection:
        from db.migrations import upgrade_database
        upgrade_database(baseline_connection, "0001_existing_schema")
        baseline_connection.execute(text("DROP TABLE alembic_version"))
    with postgres_engine.begin() as connection:
        key = next(key for key in inspect(connection).get_foreign_keys('domain_routes')
                   if key['constrained_columns'] == ['origin_station_id'])
        connection.execute(text(f'ALTER TABLE domain_routes DROP CONSTRAINT "{key["name"]}"'))
        with pytest.raises(RuntimeError, match='foreign key'):
            adopt_existing_database(connection)


def test_api_refuses_runtime_database_owner(postgres_engine,monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from db.migrations import upgrade_database
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
    monkeypatch.setattr(main,'engine',postgres_engine)
    with pytest.raises(RuntimeError,match='least-privilege'):
        with TestClient(main.app):
            pass


def test_explicit_legacy_tenant_backfill_uses_parent_schedule_identity(postgres_engine):
    from db.migrations import upgrade_database,adopt_existing_database,repair_legacy_tenant_columns
    with postgres_engine.begin() as connection:
        upgrade_database(connection,'0001_existing_schema')
        connection.execute(text('DROP TABLE alembic_version'))
        connection.execute(text("INSERT INTO ktels(id,name) VALUES (7,'Seventh')"))
        connection.execute(text("INSERT INTO schedules(id,name,ktel_id) VALUES (71,'Owned schedule',7)"))
        connection.execute(text("INSERT INTO trips(id,trip_code,schedule_id,ktel_id) VALUES (72,'Original',71,7)"))
        for table in ('drivers','solutions','trips'):
            connection.execute(text(f'ALTER TABLE {table} DROP COLUMN ktel_id CASCADE'))
        repair_legacy_tenant_columns(connection)
        assert connection.execute(text('SELECT ktel_id FROM trips WHERE id=72')).scalar_one()==7
        adopt_existing_database(connection)
        upgrade_database(connection)
        assert connection.execute(text('SELECT trip_code FROM trips WHERE id=72')).scalar_one()=='Original'


def test_legacy_backfill_refuses_unowned_rows_without_guessing(postgres_engine):
    from db.migrations import upgrade_database,repair_legacy_tenant_columns
    with postgres_engine.begin() as connection:
        upgrade_database(connection,'0001_existing_schema')
        connection.execute(text('ALTER TABLE trips DROP COLUMN ktel_id CASCADE'))
        connection.execute(text("INSERT INTO trips(id,trip_code) VALUES (88,'No owner')"))
        with pytest.raises(RuntimeError,match='ownership'):
            repair_legacy_tenant_columns(connection)
        assert 'ktel_id' not in {c['name'] for c in inspect(connection).get_columns('trips')}


def test_unprivileged_migration_owner_fails_clearly_before_schema_mutations(postgres_engine):
    import uuid
    from sqlalchemy import create_engine
    from db.migrations import upgrade_database
    role='ktel_test_migrator_'+uuid.uuid4().hex[:16]
    with postgres_engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{role}" NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text(f'GRANT USAGE,CREATE ON SCHEMA public TO "{role}"'))
    try:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            with pytest.raises(RuntimeError,match='migration.*BYPASSRLS'):
                upgrade_database(connection)
            # A failed prerequisite must not create the baseline or version table.
            assert inspect(connection).get_table_names()==[]
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))


def test_calendar_upgrade_preserves_existing_utc_instants_and_does_not_guess_rules(postgres_engine):
    from sqlalchemy import text,inspect
    from db.migrations import upgrade_database
    with postgres_engine.begin() as connection:
        upgrade_database(connection,revision='0005_resource_versions')
        connection.execute(text("INSERT INTO ktels(id,name,timezone) VALUES(1,'Existing','Europe/Athens')"))
        connection.execute(text("INSERT INTO domain_stations(id,tenant_id,code,name_el,name_en) VALUES(11,1,'A','A','A'),(12,1,'B','B','B')"))
        connection.execute(text("INSERT INTO domain_routes(id,tenant_id,origin_station_id,destination_station_id) VALUES(1,1,11,12)"))
        connection.execute(text("INSERT INTO domain_service_templates(id,tenant_id,route_id,trip_code,departure_time,arrival_time,is_active) VALUES(1,1,1,'T','23:30','01:15',true)"))
        connection.execute(text("""INSERT INTO domain_trip_instances(id,tenant_id,trip_code,service_date,origin_station_id,destination_station_id,start_utc,end_utc,template_id,properties)
            VALUES(1,1,'T','2026-12-31',11,12,'2026-12-31 21:30','2026-12-31 23:15',1,'{}')"""))
        upgrade_database(connection)
        row=connection.execute(text('SELECT start_utc,end_utc,source_hash FROM domain_trip_instances')).one()
        assert row.start_utc.hour==21 and row.end_utc.hour==23 and row.end_utc.minute==15
        assert row.start_utc.utcoffset().total_seconds()==0 and row.source_hash is None
        calendar=connection.execute(text('SELECT valid_from,valid_until,operating_weekdays,arrival_day_offset FROM domain_service_templates')).one()
        assert all(value is None for value in calendar)


def test_case_insensitive_identity_upgrade_refuses_competing_legacy_accounts(postgres_engine):
    from db.migrations import upgrade_database,current_revision
    with postgres_engine.begin() as connection:
        upgrade_database(connection,'0008_service_connections')
        connection.execute(text("INSERT INTO users (email) VALUES ('Nikos@example.org'),('nikos@example.org')"))
    with pytest.raises(RuntimeError,match='case-insensitive email collision'):
        with postgres_engine.begin() as connection:upgrade_database(connection)
    with postgres_engine.connect() as connection:
        assert current_revision(connection)=='0008_service_connections'
        assert connection.execute(text('SELECT count(*) FROM users')).scalar_one()==2


def test_case_insensitive_identity_upgrade_preserves_mixed_case_legacy_address(postgres_engine):
    from db.migrations import upgrade_database
    with postgres_engine.begin() as connection:
        upgrade_database(connection,'0008_service_connections')
        identifier=connection.execute(text("INSERT INTO users (email) VALUES ('Nikos@example.org') RETURNING id")).scalar_one()
        upgrade_database(connection)
        assert connection.execute(text("SELECT id FROM public.ktel_login_identity('nikos@example.org')")).scalar_one()==identifier
        assert connection.execute(text('SELECT email FROM users WHERE id=:id'),{'id':identifier}).scalar_one()=='Nikos@example.org'
