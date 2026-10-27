"""Real PostgreSQL fixtures. Never create/drop the configured application database."""
import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from config import settings


@pytest.fixture
def postgres_engine():
    admin_url = os.getenv('KTEL_TEST_ADMIN_URL', settings.DATABASE_URL)
    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT')
    name = 'ktel_test_' + uuid.uuid4().hex
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(admin.url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def restricted_databases(postgres_engine):
    import secrets
    from db.migrations import upgrade_database
    from db.metadata import load_domain_metadata
    roles = []
    engines = []
    with postgres_engine.begin() as connection:
        upgrade_database(connection)
        connection.execute(text("INSERT INTO ktels (id,name) VALUES (1,'First'),(2,'Second')"))
        connection.execute(text("INSERT INTO domain_drivers (id,tenant_id,code,first_name,last_name) VALUES (11,1,'D001','First','Driver'),(22,2,'D001','Second','Driver')"))
        connection.execute(text("SELECT setval(pg_get_serial_sequence('ktels','id'),2,true)"))
        connection.execute(text("SELECT setval(pg_get_serial_sequence('domain_drivers','id'),22,true)"))
        for suffix in ('api', 'worker'):
            role = 'ktel_test_' + suffix + '_' + uuid.uuid4().hex[:16]
            password = secrets.token_urlsafe(24)
            connection.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD :password NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'), {'password':password})
            from db.tenant_schema import grant_runtime_access
            grant_runtime_access(connection,role,authenticate=suffix=='api')
            roles.append(role)
            engines.append(create_engine(postgres_engine.url.set(username=role,password=password)))
    try:
        yield {'owner':postgres_engine,'api':engines[0],'worker':engines[1],'roles':roles}
    finally:
        for engine in engines:
            engine.dispose()
        with postgres_engine.begin() as connection:
            for role in roles:
                connection.execute(text(f'DROP OWNED BY "{role}"'))
                connection.execute(text(f'DROP ROLE "{role}"'))
