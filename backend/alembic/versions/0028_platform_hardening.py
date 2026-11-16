from alembic import op

revision = '0028_platform_hardening'
down_revision = '0027_platform_support'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE domain_email_outbox ADD CONSTRAINT ck_email_outbox_token_or_support CHECK (identity_token_id IS NOT NULL OR kind = 'support_session') NOT VALID")
    op.execute("DELETE FROM domain_email_outbox WHERE identity_token_id IS NULL AND kind<>'support_session'")
    op.execute('ALTER TABLE domain_email_outbox VALIDATE CONSTRAINT ck_email_outbox_token_or_support')


def downgrade():
    op.execute('ALTER TABLE domain_email_outbox DROP CONSTRAINT ck_email_outbox_token_or_support')
