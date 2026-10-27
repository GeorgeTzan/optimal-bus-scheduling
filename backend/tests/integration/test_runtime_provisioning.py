import stat
import uuid
import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError


def test_runtime_provisioning_creates_private_credentials_and_minimum_grants(postgres_engine,tmp_path):
    from db.provision_runtime import provision_runtime_roles
    from db.migrations import upgrade_database,assert_schema_current
    from db.tenant_schema import assert_runtime_role
    suffix=uuid.uuid4().hex[:16]
    roles=['ktel_test_app_'+suffix,'ktel_test_worker_'+suffix]
    output=tmp_path/'.env.runtime.local'
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
    engines=[]
    try:
        provision_runtime_roles(postgres_engine,output,roles[0],roles[1])
        assert stat.S_IMODE(output.stat().st_mode)==0o600
        config=dotenv_values(output)
        for field in ('DATABASE_RUNTIME_URL','DATABASE_WORKER_URL'):
            engine=create_engine(config[field]);engines.append(engine)
            with engine.begin() as connection:
                assert_schema_current(connection)
                assert_runtime_role(connection)
                if field=='DATABASE_RUNTIME_URL':
                    assert connection.execute(text('SELECT count(*) FROM users')).scalar_one()==0
                else:
                    with pytest.raises(DBAPIError):
                        with connection.begin_nested():
                            connection.execute(text('SELECT count(*) FROM users'))
                with pytest.raises(DBAPIError):
                    with connection.begin_nested():
                        connection.execute(text("UPDATE alembic_version SET version_num='forged'"))
                can_auth=connection.execute(text("SELECT has_function_privilege(current_user,'public.ktel_login_identity(text)','EXECUTE')")).scalar_one()
                assert can_auth == (field=='DATABASE_RUNTIME_URL')
    finally:
        for engine in engines:
            engine.dispose()
        with postgres_engine.begin() as connection:
            for role in roles:
                if connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
                    connection.execute(text(f'DROP OWNED BY "{role}"'))
                    connection.execute(text(f'DROP ROLE "{role}"'))


def test_provisioning_never_overwrites_existing_secret_file(postgres_engine,tmp_path):
    from db.provision_runtime import provision_runtime_roles
    output=tmp_path/'.env.runtime.local';output.write_text('keep this secret')
    with pytest.raises(FileExistsError):
        provision_runtime_roles(postgres_engine,output,'unused_app','unused_worker')
    assert output.read_text()=='keep this secret'


def test_worker_cannot_read_passwords_or_manage_members_even_in_valid_scope(restricted_databases):
    from db.tenant_schema import grant_runtime_access
    with restricted_databases['worker'].begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id','1',true)"))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text('SELECT hashed_password FROM users'))
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("INSERT INTO domain_memberships(tenant_id,user_id,role,is_active,version,created_at) VALUES (1,1,'admin',true,1,now())"))


def test_refresh_grants_preserves_existing_credentials_and_removes_stale_worker_access(restricted_databases):
    from db.provision_runtime import refresh_runtime_grants
    role=restricted_databases['roles'][1]
    with restricted_databases['owner'].begin() as connection:
        before=connection.execute(text('SELECT rolpassword FROM pg_authid WHERE rolname=:role'),{'role':role}).scalar_one()
        connection.execute(text(f'GRANT SELECT ON users TO "{role}"'))
    refresh_runtime_grants(restricted_databases['owner'],*restricted_databases['roles'])
    with restricted_databases['owner'].begin() as connection:
        assert connection.execute(text('SELECT rolpassword FROM pg_authid WHERE rolname=:role'),{'role':role}).scalar_one()==before
    with restricted_databases['worker'].begin() as connection:
        assert connection.execute(text("SELECT has_table_privilege(current_user,'users','SELECT')")).scalar_one() is False
