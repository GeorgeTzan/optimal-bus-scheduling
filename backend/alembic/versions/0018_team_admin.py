"""A narrow function so one mail worker can find the organizations that have mail waiting, without reading any organization data."""
from alembic import op
revision = '0018_team_admin'
down_revision = '0017_driver_portal'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE FUNCTION public.ktel_mail_tenants() RETURNS SETOF integer
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off
        AS $$ SELECT DISTINCT tenant_id FROM public.domain_email_outbox
              WHERE attempts<5 AND (delivery_status='queued' OR (delivery_status='delivering' AND lease_expires_at<clock_timestamp())) $$''')
    op.execute('REVOKE ALL ON FUNCTION public.ktel_mail_tenants() FROM PUBLIC')


def downgrade():
    raise RuntimeError('Team administration rollback requires a reviewed restore')
