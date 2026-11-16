from alembic import op

revision = '0024_platform_operator'
down_revision = '0023_route_en_route_break'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''ALTER TABLE ktels ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('trial','active','suspended','cancelled')),
      ADD COLUMN trial_ends_on DATE, ADD COLUMN plan_note TEXT, ADD COLUMN support_access_until TIMESTAMPTZ''')
    op.execute('''CREATE TABLE platform_operators (
      id SERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE CHECK (email = lower(email)), password_hash TEXT NOT NULL,
      totp_secret TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT true, last_totp_step BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.execute('''CREATE TABLE platform_sessions (
      id SERIAL PRIMARY KEY, operator_id INTEGER NOT NULL REFERENCES platform_operators(id),
      token_hash VARCHAR(64) NOT NULL UNIQUE, csrf_hash VARCHAR(64) NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX ix_platform_sessions_operator_id ON platform_sessions(operator_id)')
    op.execute('''CREATE TABLE platform_audit (
      id BIGSERIAL PRIMARY KEY, operator_id INTEGER REFERENCES platform_operators(id), tenant_id INTEGER REFERENCES ktels(id),
      action TEXT NOT NULL, reason TEXT, ticket TEXT, detail JSONB NOT NULL DEFAULT '{}'::jsonb, ip TEXT,
      at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX ix_platform_audit_tenant_at ON platform_audit(tenant_id, at DESC)')
    op.execute('ALTER TABLE platform_audit ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE platform_audit FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_read ON platform_audit FOR SELECT USING (tenant_id = public.ktel_current_tenant())')
    op.execute('CREATE POLICY platform_append ON platform_audit FOR INSERT WITH CHECK (true)')


def downgrade():
    op.execute('DROP TABLE platform_audit')
    op.execute('DROP TABLE platform_sessions')
    op.execute('DROP TABLE platform_operators')
    op.execute('ALTER TABLE ktels DROP COLUMN status, DROP COLUMN trial_ends_on, DROP COLUMN plan_note, DROP COLUMN support_access_until')
