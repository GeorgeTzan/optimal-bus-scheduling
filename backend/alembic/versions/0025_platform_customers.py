from alembic import op

revision = '0025_platform_customers'
down_revision = '0024_platform_operator'
branch_labels = None
depends_on = None

DEFINER = 'SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off'
SIGNATURES = (
    'public.platform_create_customer(text,text,text,text,date,text,text,text,timestamptz,text,text,text)',
    'public.platform_set_status(integer,text)',
    'public.platform_list_customers()',
    'public.platform_update_customer(integer,text,date,text)',
)


def upgrade():
    op.execute(f'''CREATE FUNCTION public.platform_create_customer(p_name text, p_region text, p_timezone text, p_status text,
        p_trial_ends_on date, p_admin_email text, p_token_id text, p_token_hash text, p_expires_at timestamptz,
        p_outbox_id text, p_encrypted_payload text, p_delivery_status text) RETURNS integer
        LANGUAGE plpgsql {DEFINER} AS $$
        DECLARE new_id integer;
        BEGIN
          IF p_status NOT IN ('trial','active') THEN RAISE EXCEPTION 'A new customer starts as trial or active'; END IF;
          INSERT INTO ktels(name,region,timezone,status,trial_ends_on,created_at)
            VALUES (p_name,p_region,p_timezone,p_status,p_trial_ends_on,now() AT TIME ZONE 'UTC') RETURNING id INTO new_id;
          INSERT INTO domain_identity_tokens(id,tenant_id,token_hash,kind,email,role,expires_at,created_at)
            VALUES (p_token_id,new_id,p_token_hash,'invitation',p_admin_email,'admin',p_expires_at,now());
          INSERT INTO domain_email_outbox(id,tenant_id,identity_token_id,kind,encrypted_payload,delivery_status,attempts,attempt_token,created_at)
            VALUES (p_outbox_id,new_id,p_token_id,'invitation',p_encrypted_payload,p_delivery_status,0,0,now());
          RETURN new_id;
        END $$''')
    op.execute(f'''CREATE FUNCTION public.platform_set_status(p_tenant_id integer, p_status text) RETURNS void
        LANGUAGE plpgsql {DEFINER} AS $$
        BEGIN
          UPDATE ktels SET status=p_status WHERE id=p_tenant_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Unknown organization'; END IF;
          IF p_status IN ('suspended','cancelled') THEN
            UPDATE domain_auth_sessions SET revoked_at=now() WHERE tenant_id=p_tenant_id AND revoked_at IS NULL;
          END IF;
        END $$''')
    op.execute(f'''CREATE FUNCTION public.platform_list_customers()
        RETURNS TABLE(id integer, name text, region text, status text, trial_ends_on date, plan_note text, created_at timestamp)
        LANGUAGE sql STABLE {DEFINER} AS $$
        SELECT k.id,k.name::text,k.region::text,k.status,k.trial_ends_on,k.plan_note,k.created_at FROM ktels k ORDER BY k.name $$''')
    op.execute(f'''CREATE FUNCTION public.platform_update_customer(p_tenant_id integer, p_plan_note text, p_trial_ends_on date, p_region text)
        RETURNS void LANGUAGE sql {DEFINER} AS $$
        UPDATE ktels SET plan_note=p_plan_note, trial_ends_on=p_trial_ends_on, region=p_region WHERE id=p_tenant_id $$''')
    for signature in SIGNATURES:
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC')


def downgrade():
    for signature in SIGNATURES:
        op.execute(f'DROP FUNCTION {signature}')
