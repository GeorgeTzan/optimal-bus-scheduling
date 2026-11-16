import argparse
import getpass
import os
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from config import settings
from db.migrations import assert_schema_current
from app.domain.platform import totp
from app.domain.platform.service import create_operator


def main():
    parser=argparse.ArgumentParser(description='Manage platform operator accounts')
    commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('create',help='Create an operator and print the TOTP enrolment secret once')
    create.add_argument('--email',required=True)
    args=parser.parse_args()
    password=getpass.getpass('Operator password: ')
    if password!=getpass.getpass('Repeat password: '):
        raise SystemExit('The passwords do not match')
    engine=create_engine(os.getenv('DATABASE_MIGRATION_URL',settings.DATABASE_URL),hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert_schema_current(connection)
            if not connection.execute(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user')).scalar_one():
                raise RuntimeError('Operator creation requires the separate privileged administration connection')
        with sessionmaker(bind=engine)() as db:
            try:
                secret=create_operator(db,email=args.email,password=password)
            except ValueError as error:
                raise SystemExit(str(error)) from None
        print(f'Operator {args.email.strip().lower()} created. Add this to an authenticator app now; it is not shown again.')
        print(f'TOTP secret: {secret}')
        print(f'otpauth URI: {totp.otpauth_uri(secret,args.email.strip().lower())}')
    finally:
        engine.dispose()


if __name__=='__main__':
    main()
