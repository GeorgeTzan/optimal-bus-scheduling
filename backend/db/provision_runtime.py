"""Create least-privilege local/deployment roles without printing credentials."""
import argparse
import os
from pathlib import Path
import re
import secrets
from sqlalchemy import text,create_engine
from db.migrations import assert_schema_current
from db.tenant_schema import grant_runtime_access,grant_platform_access


def provision_runtime_roles(owner_engine,output_path,api_role='ktel_api',worker_role='ktel_worker'):
    output_path=Path(output_path)
    for role in (api_role,worker_role):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',role) or role.startswith('pg_'):
            raise ValueError('Runtime role names must be lowercase identifiers, excluding reserved names')
    if api_role==worker_role:
        raise ValueError('API and worker roles must be separate')
    # O_EXCL and mode 0600 protect pre-existing secrets and newly generated passwords.
    descriptor=os.open(output_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'w') as output:
            urls={}
            with owner_engine.begin() as connection:
                assert_schema_current(connection)
                for role,field,authenticate in (
                    (api_role,'DATABASE_RUNTIME_URL',True),(worker_role,'DATABASE_WORKER_URL',False)):
                    if connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
                        raise RuntimeError('Runtime role already exists; refusing to rotate existing credentials implicitly')
                    password=secrets.token_urlsafe(32)
                    quoted=connection.dialect.identifier_preparer.quote(role)
                    connection.execute(text(f'CREATE ROLE {quoted} LOGIN PASSWORD :password NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'),{'password':password})
                    grant_runtime_access(connection,role,authenticate=authenticate)
                    urls[field]=owner_engine.url.set(username=role,password=password).render_as_string(hide_password=False)
                output.write('# Generated runtime roles; keep this file private and out of version control.\n')
                for field,url in urls.items():
                    output.write(f'{field}={url}\n')
                output.flush()
                os.fsync(output.fileno())
    except BaseException:
        output_path.unlink(missing_ok=True) # Only the new file opened above belongs to this operation.
        raise


def provision_platform_role(owner_engine,output_path,role='ktel_platform'):
    output_path=Path(output_path)
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',role) or role.startswith('pg_'):
        raise ValueError('Platform role name must be a lowercase identifier, excluding reserved names')
    descriptor=os.open(output_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'w') as output:
            with owner_engine.begin() as connection:
                assert_schema_current(connection)
                if connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
                    raise RuntimeError('Platform role already exists; refusing to rotate existing credentials implicitly')
                password=secrets.token_urlsafe(32)
                quoted=connection.dialect.identifier_preparer.quote(role)
                connection.execute(text(f'CREATE ROLE {quoted} LOGIN PASSWORD :password NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'),{'password':password})
                grant_platform_access(connection,role)
                url=owner_engine.url.set(username=role,password=password).render_as_string(hide_password=False)
                output.write(f'DATABASE_PLATFORM_URL={url}\n')
                output.flush()
                os.fsync(output.fileno())
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise


def least_privilege_role(connection,role):
    flags=connection.execute(text('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:role'),{'role':role}).first()
    owns=connection.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace AND pg_get_userbyid(relowner)=:role)"),{'role':role}).scalar_one()
    return flags is not None and not any(flags) and not owns


def refresh_runtime_grants(owner_engine,api_role,worker_role,platform_role='ktel_platform'):
    if len({api_role,worker_role,platform_role})!=3:
        raise ValueError('API, worker and platform roles must be separate')
    with owner_engine.begin() as connection:
        assert_schema_current(connection)
        for role,authenticate in ((api_role,True),(worker_role,False)):
            if not least_privilege_role(connection,role):
                raise ValueError('Only existing least-privilege non-owner runtime roles can be refreshed')
            grant_runtime_access(connection,role,authenticate=authenticate)
        if connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':platform_role}).first():
            if not least_privilege_role(connection,platform_role):
                raise ValueError('Only an existing least-privilege non-owner platform role can be refreshed')
            grant_platform_access(connection,platform_role)


def main():
    from config import settings
    parser=argparse.ArgumentParser(description='Provision separate API/worker database roles')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'.env.runtime.local')
    parser.add_argument('--api-role',default='ktel_api')
    parser.add_argument('--worker-role',default='ktel_worker')
    parser.add_argument('--platform-role',default='ktel_platform')
    parser.add_argument('--platform-output',type=Path,default=Path(__file__).resolve().parents[1]/'.env.platform.local')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--refresh-grants',action='store_true',help='Refresh existing role grants without changing credentials')
    action.add_argument('--create-platform-role',action='store_true',help='Create the operator panel role once and write its private URL')
    args=parser.parse_args()
    engine=create_engine(os.getenv('DATABASE_MIGRATION_URL',settings.DATABASE_URL),hide_parameters=True)
    try:
        if args.refresh_grants:
            refresh_runtime_grants(engine,args.api_role,args.worker_role,args.platform_role)
            print('Runtime grants refreshed; credentials preserved')
        elif args.create_platform_role:
            provision_platform_role(engine,args.platform_output,args.platform_role)
            print('Created least-privilege platform role; private configuration written to',args.platform_output)
        else:
            provision_runtime_roles(engine,args.output,args.api_role,args.worker_role)
            print('Created least-privilege API/worker roles; private configuration written to',args.output)
    finally:
        engine.dispose()


if __name__=='__main__':
    main()
