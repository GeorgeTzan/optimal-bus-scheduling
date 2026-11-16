from alembic import op

revision = '0023_route_en_route_break'
down_revision = '0022_transfer_hash_without_depot'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE domain_routes ADD COLUMN en_route_break_minutes INTEGER NOT NULL DEFAULT 0 CHECK (en_route_break_minutes BETWEEN 0 AND 240)')


def downgrade():
    op.execute('ALTER TABLE domain_routes DROP COLUMN en_route_break_minutes')
