from alembic import op

revision = '0026_platform_health'
down_revision = '0025_platform_customers'
branch_labels = None
depends_on = None

SIGNATURE = 'public.platform_customer_health()'


def upgrade():
    op.execute('''CREATE FUNCTION public.platform_customer_health()
        RETURNS TABLE(tenant_id integer, last_sign_in timestamptz, drivers integer, vehicles integer, timetables integer,
                      published_days_30d integer, solver_failed_7d integer, mail_failed_7d integer, uncovered_share_latest numeric)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off AS $$
        SELECT k.id,
          (SELECT max(s.created_at) FROM domain_auth_sessions s WHERE s.tenant_id=k.id),
          (SELECT count(*)::integer FROM domain_drivers d WHERE d.tenant_id=k.id AND d.is_active IS NOT FALSE),
          (SELECT count(*)::integer FROM domain_vehicles v WHERE v.tenant_id=k.id AND v.is_active IS NOT FALSE),
          (SELECT count(*)::integer FROM domain_service_templates t WHERE t.tenant_id=k.id AND t.is_active IS NOT FALSE),
          (SELECT count(DISTINCT p.published_at::date)::integer FROM domain_publications p
             WHERE p.tenant_id=k.id AND p.published_at >= (now() AT TIME ZONE 'UTC') - interval '30 days'),
          (SELECT count(*)::integer FROM domain_jobs j WHERE j.tenant_id=k.id AND j.status='failed'
             AND coalesce(j.updated_at,j.created_at) >= (now() AT TIME ZONE 'UTC') - interval '7 days'),
          (SELECT count(*)::integer FROM domain_email_outbox o WHERE o.tenant_id=k.id AND o.delivery_status='failed'
             AND o.created_at >= now() - interval '7 days'),
          (SELECT round(count(*) FILTER (WHERE a.resource_id='UNASSIGNED')::numeric / nullif(count(*),0),4)
             FROM domain_revision_assignments a
             WHERE a.tenant_id=k.id AND NOT a.is_cancelled AND a.revision_id=(
               SELECT p.revision_id FROM domain_publications p WHERE p.tenant_id=k.id ORDER BY p.published_at DESC, p.id DESC LIMIT 1))
        FROM ktels k ORDER BY k.id $$''')
    op.execute(f'REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC')


def downgrade():
    op.execute(f'DROP FUNCTION {SIGNATURE}')
