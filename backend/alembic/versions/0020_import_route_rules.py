"""Allow the route rules sheet in staged import rows."""
from alembic import op

revision = '0020_import_route_rules'
down_revision = '0019_driver_work_rules'
branch_labels = None
depends_on = None
ENTITIES = "'drivers','vehicles','stations','timetable','pairings','transfers','connections'"


def replace_constraint(entities):
    op.execute('ALTER TABLE domain_import_rows DROP CONSTRAINT ck_import_row_entity')
    op.execute(f'ALTER TABLE domain_import_rows ADD CONSTRAINT ck_import_row_entity CHECK (entity IN ({entities}))')


def upgrade():
    replace_constraint(ENTITIES + ",'route_rules'")


def downgrade():
    op.execute("DELETE FROM domain_import_rows WHERE entity='route_rules'")
    replace_constraint(ENTITIES)
