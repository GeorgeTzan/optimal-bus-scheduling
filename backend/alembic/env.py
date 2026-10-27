from alembic import context
from sqlalchemy import create_engine
from config import settings
from db.metadata import load_domain_metadata
import os

config = context.config
target_metadata = load_domain_metadata()


def run_migrations(connection):
    from db.migrations import assert_migration_owner
    assert_migration_owner(connection)
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=os.getenv('DATABASE_MIGRATION_URL', settings.DATABASE_URL),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = config.attributes.get('connection')
    if connection is not None:
        run_migrations(connection)
    else:
        engine = create_engine(os.getenv('DATABASE_MIGRATION_URL', settings.DATABASE_URL))
        with engine.connect() as connection:
            run_migrations(connection)
        engine.dispose()
