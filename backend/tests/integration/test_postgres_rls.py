import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@pytest.mark.parametrize('role',['api','worker'])
def test_missing_tenant_context_returns_no_rows_and_denies_writes(restricted_databases, role):
    with restricted_databases[role].begin() as connection:
        assert connection.execute(text('SELECT count(*) FROM domain_drivers')).scalar_one() == 0
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("INSERT INTO domain_drivers (tenant_id,code,first_name,last_name) VALUES (1,'forged','Bad','Write')"))


@pytest.mark.parametrize('role',['api','worker'])
def test_real_roles_scope_raw_sql_and_deny_cross_tenant_updates(restricted_databases,role):
    with restricted_databases[role].begin() as connection:
        flags=connection.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        assert flags == (False,False)
        connection.execute(text("SELECT set_config('app.tenant_id','1',true)"))
        assert connection.execute(text('SELECT id FROM domain_drivers')).scalars().all() == [11]
        if role=='api':
            assert connection.execute(text("UPDATE domain_drivers SET first_name='forged' WHERE id=22")).rowcount == 0
            assert connection.execute(text('DELETE FROM domain_drivers WHERE id=22')).rowcount == 0
        else:
            for command in ("UPDATE domain_drivers SET first_name='forged' WHERE id=22",'DELETE FROM domain_drivers WHERE id=22'):
                with pytest.raises(DBAPIError):
                    with connection.begin_nested():
                        connection.execute(text(command))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("UPDATE domain_drivers SET tenant_id=2 WHERE id=11"))


def test_database_rejects_cross_tenant_foreign_key(restricted_databases):
    with restricted_databases['api'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id','1',true)"))
        with pytest.raises(DBAPIError) as failure:
            with connection.begin_nested():
                connection.execute(text("INSERT INTO domain_driver_qualifications (tenant_id,driver_id,qualification_code) VALUES (1,22,'D')"))
        assert failure.value.orig.pgcode == '23503'


def test_tenant_scope_survives_commit_and_never_leaks_on_pool_reuse(restricted_databases):
    from app.domain.identity.tenant_session import tenant_transaction
    engine=restricted_databases['api']
    with Session(engine) as db:
        with tenant_transaction(db,1):
            assert db.execute(text('SELECT id FROM domain_drivers')).scalars().all()==[11]
            db.commit()
            assert db.execute(text('SELECT id FROM domain_drivers')).scalars().all()==[11]
        assert db.execute(text('SELECT count(*) FROM domain_drivers')).scalar_one()==0
        db.rollback()
        with tenant_transaction(db,2):
            assert db.execute(text('SELECT id FROM domain_drivers')).scalars().all()==[22]
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM domain_drivers')).scalar_one()==0


def test_audit_inspects_actual_policies_composite_keys_and_roles(restricted_databases):
    from db.tenant_schema import audit_database_tenancy
    with restricted_databases['owner'].begin() as connection:
        assert audit_database_tenancy(connection,restricted_databases['roles']) == []
        connection.execute(text('ALTER TABLE domain_trip_instances DISABLE ROW LEVEL SECURITY'))
        assert any('domain_trip_instances' in issue for issue in audit_database_tenancy(connection,restricted_databases['roles']))


def test_cross_tenant_existing_data_blocks_upgrade_instead_of_rewriting_it(postgres_engine):
    from db.migrations import upgrade_database
    with postgres_engine.begin() as connection:
        upgrade_database(connection, '0001_existing_schema')
        connection.execute(text("INSERT INTO ktels (id,name) VALUES (1,'One'),(2,'Two')"))
        connection.execute(text("INSERT INTO domain_drivers (id,tenant_id,code,first_name,last_name) VALUES (22,2,'D','Other','Tenant')"))
        connection.execute(text("INSERT INTO domain_driver_qualifications (id,tenant_id,driver_id,qualification_code) VALUES (33,1,22,'D')"))
    with pytest.raises(RuntimeError,match='cross-tenant'):
        with postgres_engine.begin() as connection:
            upgrade_database(connection)
    with postgres_engine.connect() as connection:
        assert connection.execute(text('SELECT tenant_id FROM domain_driver_qualifications WHERE id=33')).scalar_one()==1
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0001_existing_schema'
