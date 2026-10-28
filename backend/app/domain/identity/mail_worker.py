"""Tenant-scoped durable identity mail delivery; never logs link or message payloads."""
import argparse
import time
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from db.migrations import assert_schema_current
from db.tenant_schema import assert_runtime_role
from app.domain.identity.mail import deliver_once,deliver_all_once


def main():
    parser=argparse.ArgumentParser(description='Deliver queued invitation/reset messages for one tenant')
    scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--tenant-id',type=int)
    scope.add_argument('--all-tenants',action='store_true',help='Serve every organization that has mail waiting')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.tenant_id is not None and args.tenant_id<=0:parser.error('tenant-id must be positive')
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        parser.error('Configure SMTP_HOST and SMTP_FROM before starting mail delivery')
    engine=create_engine(settings.DATABASE_WORKER_URL,hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert_schema_current(connection);assert_runtime_role(connection)
        factory=sessionmaker(bind=engine);worker_id=str(uuid4())
        while True:
            worked=deliver_all_once(factory,worker_id) if args.all_tenants else deliver_once(factory,args.tenant_id,worker_id)
            if args.once:return
            if not worked:time.sleep(1)
    finally:engine.dispose()


if __name__=='__main__':main()
