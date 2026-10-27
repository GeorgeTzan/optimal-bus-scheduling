"""Explicit migrations/adoption; the API never creates or stamps customer schemas."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

BASELINE = '0001_existing_schema'


def assert_migration_owner(connection):
    from sqlalchemy import text
    flags=connection.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
    if not any(flags):
        raise RuntimeError('Database migration owner requires superuser or BYPASSRLS for protected authentication functions; never use this role for API/worker runtime')


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['connection'] = connection
    return config


def current_revision(connection):
    return MigrationContext.configure(connection).get_current_revision()


def upgrade_database(connection, revision='head'):
    assert_migration_owner(connection)
    if current_revision(connection) is None and set(inspect(connection).get_table_names()) - {'alembic_version'}:
        raise RuntimeError('Existing unversioned database: explicitly adopt the validated baseline before upgrade')
    command.upgrade(migration_config(connection), revision)


def adopt_existing_database(connection):
    assert_migration_owner(connection)
    if current_revision(connection) is not None:
        raise RuntimeError('Database already has a migration revision')
    # Compare against the frozen baseline, not models that will evolve in later migrations.
    from importlib.util import spec_from_file_location, module_from_spec
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0001_existing_schema.py'
    spec = spec_from_file_location('ktel_schema_baseline', path)
    baseline = module_from_spec(spec)
    spec.loader.exec_module(baseline)
    inspector = inspect(connection)
    issues = []
    for table, columns in baseline.EXPECTED_COLUMNS.items():
        if not inspector.has_table(table):
            issues.append(f'missing table {table}')
            continue
        actual = {column['name']: column for column in inspector.get_columns(table)}
        for name, expected in columns.items():
            if name not in actual:
                issues.append(f'missing column {table}.{name}')
                continue
            column = actual[name]
            actual_type = str(column['type'].compile(dialect=connection.dialect)).replace('DOUBLE PRECISION', 'FLOAT')
            if actual_type != expected['type'] or column['nullable'] != expected['nullable']:
                issues.append(f'incompatible column {table}.{name}')
    for table, keys in baseline.EXPECTED_KEYS.items():
        if not inspector.has_table(table):
            continue
        if inspector.get_pk_constraint(table)['constrained_columns'] != keys['primary_key']:
            issues.append(f'incompatible primary key {table}')
        actual_fks = {(tuple(fk['constrained_columns']), fk['referred_table'], tuple(fk['referred_columns']))
                      for fk in inspector.get_foreign_keys(table)}
        for fk in keys['foreign_keys']:
            signature = (tuple(fk['columns']), fk['target_table'], tuple(fk['target_columns']))
            if signature not in actual_fks:
                issues.append(f'missing foreign key {table}.{fk["columns"]}')
        actual_unique = {tuple(idx['column_names']) for idx in inspector.get_indexes(table) if idx['unique']}
        actual_unique.update(tuple(key['column_names']) for key in inspector.get_unique_constraints(table))
        for columns in keys['unique_indexes']:
            if tuple(columns) not in actual_unique:
                issues.append(f'missing uniqueness {table}.{columns}')
    if issues:
        raise RuntimeError('Cannot adopt existing schema: ' + '; '.join(issues))
    command.stamp(migration_config(connection), BASELINE)


def assert_schema_current(connection):
    head = ScriptDirectory.from_config(migration_config(connection)).get_current_head()
    if current_revision(connection) != head:
        raise RuntimeError('Database migrations required; run the explicit database upgrade command')


def repair_legacy_tenant_columns(connection):
    """Explicit repair of the three known pre-tenant tables, never default ownership."""
    assert_migration_owner(connection)
    inspector=inspect(connection)
    repairs=[]
    issues=[]
    from sqlalchemy import text
    for table in ('drivers','solutions','trips'):
        if not inspector.has_table(table):
            raise RuntimeError(f'Cannot repair missing legacy table {table}')
        columns={c['name'] for c in inspector.get_columns(table)}
        if 'ktel_id' in columns:
            continue
        if not {'id','schedule_id'} <= columns:
            raise RuntimeError(f'Cannot infer legacy ownership for incompatible table {table}')
        unresolved=connection.execute(text(f'''SELECT t.id FROM "{table}" t
            LEFT JOIN schedules s ON t.schedule_id=s.id
            WHERE s.ktel_id IS NULL LIMIT 5''')).scalars().all()
        if unresolved:
            issues.append(f'{table}: ownership unresolved for row IDs {unresolved}')
        repairs.append(table)
    if issues:
        raise RuntimeError('Legacy ownership repair refused: '+'; '.join(issues))
    for table in repairs:
        connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN ktel_id INTEGER REFERENCES ktels(id)'))
        connection.execute(text(f'''UPDATE "{table}" t SET ktel_id=s.ktel_id FROM schedules s
            WHERE t.schedule_id=s.id'''))
        connection.execute(text(f'CREATE INDEX "ix_{table}_ktel_id" ON "{table}" (ktel_id)'))


def main():
    import argparse
    import os
    from sqlalchemy import create_engine
    from config import settings
    parser = argparse.ArgumentParser(description='Explicit KTEL database migration administration')
    parser.add_argument('action', choices=['upgrade', 'check'])
    parser.add_argument('--adopt-existing', action='store_true',
                        help='Validate and stamp the pre-migration schema before upgrading')
    parser.add_argument('--repair-legacy-tenants', action='store_true',
                        help='Backfill only known missing legacy tenant columns using parent schedules')
    args = parser.parse_args()
    if args.action == 'check' and (args.adopt_existing or args.repair_legacy_tenants):
        parser.error('check does not accept schema-writing options')
    engine = create_engine(os.getenv('DATABASE_MIGRATION_URL', settings.DATABASE_URL),hide_parameters=True)
    try:
        with engine.begin() as connection:
            if args.action == 'check':
                assert_schema_current(connection)
            else:
                if args.repair_legacy_tenants:
                    repair_legacy_tenant_columns(connection)
                if args.adopt_existing:
                    adopt_existing_database(connection)
                upgrade_database(connection)
            print('Database schema revision:', current_revision(connection))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
