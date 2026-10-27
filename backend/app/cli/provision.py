"""Explicit platform-owner provisioning. Tenant administrators cannot create organizations."""
import argparse
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import TypeAdapter,EmailStr
from config import settings
from db.migrations import assert_schema_current
from app.domain.identity.service import provision_organization


def provision_to_file(db,*,name,admin_email,timezone,output):
    if not name.strip():
        raise ValueError('Organization name is required')
    email=str(TypeAdapter(EmailStr).validate_python(admin_email)).lower()
    path=Path(output)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'w') as file:
            invitation=provision_organization(db,name=name,admin_email=email,timezone=timezone)
            file.write(f'{settings.PUBLIC_APP_URL}/accept-invitation#token={invitation.token}\n')
            file.flush();os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return invitation.tenant_id


def main():
    parser=argparse.ArgumentParser(description='Provision an organization and private first-admin invitation')
    parser.add_argument('--name',required=True)
    parser.add_argument('--admin-email',required=True)
    parser.add_argument('--timezone',default='Europe/Athens')
    parser.add_argument('--invitation-file',type=Path,required=True)
    args=parser.parse_args()
    engine=create_engine(os.getenv('DATABASE_MIGRATION_URL',settings.DATABASE_URL),hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert_schema_current(connection)
            # The runtime API has neither table ownership nor permission to provision tenants.
            from sqlalchemy import text
            if not connection.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")).scalar_one():
                raise RuntimeError('Platform provisioning requires the separate privileged administration connection')
        with sessionmaker(bind=engine)() as db:
            tenant_id=provision_to_file(db,name=args.name,admin_email=args.admin_email,timezone=args.timezone,output=args.invitation_file)
        print(f'Organization {tenant_id} created. Private invitation written to {args.invitation_file}. Delivery depends on SMTP configuration.')
    finally:
        engine.dispose()


if __name__=='__main__':
    main()
