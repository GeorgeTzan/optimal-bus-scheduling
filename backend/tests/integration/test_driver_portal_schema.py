"""One login and one pending invitation per driver; acknowledgments are tenant-isolated and insert-only for the API role."""
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.integration.conftest import *  # noqa: F401,F403  (restricted_databases and its engine fixtures)


def add_user(connection, tenant, email):
    return connection.execute(text("INSERT INTO users (email,hashed_password,ktel_id,is_active) VALUES (:e,'x',:t,true) RETURNING id"), {'e': email, 't': tenant}).scalar_one()


def test_schema_enforces_one_login_and_one_pending_invitation_per_driver_and_acks_are_insert_only(restricted_databases):
    owner = restricted_databases['owner']
    with owner.begin() as connection:
        first, second = add_user(connection, 1, 'a@example.org'), add_user(connection, 1, 'b@example.org')
        for user in (first, second):
            connection.execute(text("INSERT INTO domain_memberships (tenant_id,user_id,role,is_active,version,created_at) VALUES (1,:u,'driver',true,1,now())"), {'u': user})
        connection.execute(text('UPDATE domain_memberships SET driver_id=11 WHERE user_id=:u'), {'u': first})
    with pytest.raises(IntegrityError):
        with owner.begin() as connection:
            connection.execute(text('UPDATE domain_memberships SET driver_id=11 WHERE user_id=:u'), {'u': second})

    def invite(connection, **extra):
        values = {'id': str(uuid.uuid4()), 'hash': uuid.uuid4().hex, **extra}
        connection.execute(text("INSERT INTO domain_identity_tokens (id,tenant_id,token_hash,kind,email,role,driver_id,expires_at,created_at,revoked_at) "
                                "VALUES (:id,1,:hash,'invitation',:email,:role,:driver,now()+interval '1 day',now(),:revoked)"),
                           {'email': 'x@example.org', 'role': 'driver', 'driver': 11, 'revoked': None, **values})
    with owner.begin() as connection:
        invite(connection, driver=None)
        invite(connection, driver=None)  # invitations without a driver stay unrestricted
        invite(connection)
        invite(connection, revoked='2026-01-01T00:00:00+00')  # a revoked one does not occupy the driver
    with pytest.raises(IntegrityError):
        with owner.begin() as connection:
            invite(connection)
    with pytest.raises(IntegrityError):
        with owner.begin() as connection:
            invite(connection, role='viewer', driver=22)  # a driver link needs the driver role
    with owner.connect() as connection:
        api = connection.execute(text("SELECT has_table_privilege(:r,'domain_driver_acknowledgments','INSERT'), has_table_privilege(:r,'domain_driver_acknowledgments','SELECT'), "
                                      "has_table_privilege(:r,'domain_driver_acknowledgments','UPDATE'), has_table_privilege(:r,'domain_driver_acknowledgments','DELETE')"), {'r': restricted_databases['roles'][0]}).one()
        worker = connection.execute(text("SELECT has_table_privilege(:r,'domain_driver_acknowledgments','SELECT')"), {'r': restricted_databases['roles'][1]}).scalar_one()
        flags = connection.execute(text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='domain_driver_acknowledgments'")).one()
    assert tuple(api) == (True, True, False, False) and worker is False and tuple(flags) == (True, True)
