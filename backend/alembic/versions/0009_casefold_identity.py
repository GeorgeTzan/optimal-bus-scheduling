"""Compatible case-insensitive login discovery without rewriting legacy identities."""
from alembic import op
from sqlalchemy import text
revision='0009_casefold_identity'
down_revision='0008_service_connections'
branch_labels=None
depends_on=None


def upgrade():
    connection=op.get_bind()
    collisions=connection.execute(text('''SELECT array_agg(id ORDER BY id) FROM users
        WHERE email IS NOT NULL GROUP BY lower(btrim(email)) HAVING count(*)>1 LIMIT 5''')).scalars().all()
    if collisions:
        raise RuntimeError('Identity migration preflight: case-insensitive email collision for user IDs '+str(collisions)+'. Review ownership and correct distinct addresses explicitly before retrying; accounts were not merged.')
    op.execute('CREATE UNIQUE INDEX uq_users_email_casefold ON users (lower(btrim(email)))')
    op.execute('''CREATE OR REPLACE FUNCTION public.ktel_login_identity(identity text) RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public SET row_security = off
        AS $$ SELECT * FROM public.users WHERE lower(btrim(email)) = lower(btrim(identity)) $$''')


def downgrade():
    raise RuntimeError('Identity lookup rollback requires reviewed account compatibility')
