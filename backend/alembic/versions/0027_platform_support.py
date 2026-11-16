from alembic import op

revision = '0027_platform_support'
down_revision = '0026_platform_health'
branch_labels = None
depends_on = None

DEFINER = 'SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off'
SIGNATURES = (
    'public.platform_end_support_sessions(integer,integer,text,text)',
    'public.platform_start_support_session(integer,integer,text,text,text,text)',
    'public.platform_support_state(integer,integer)',
    'public.ktel_support_request(text,text,text,text)',
    'public.ktel_end_support_sessions()',
)


def set_status(ending):
    return f'''CREATE OR REPLACE FUNCTION public.platform_set_status(p_tenant_id integer, p_status text) RETURNS void
        LANGUAGE plpgsql {DEFINER} AS $$
        BEGIN
          UPDATE ktels SET status=p_status WHERE id=p_tenant_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Unknown organization'; END IF;
          IF p_status IN ('suspended','cancelled') THEN
            UPDATE domain_auth_sessions SET revoked_at=now() WHERE tenant_id=p_tenant_id AND revoked_at IS NULL;{ending}
          END IF;
        END $$'''


def upgrade():
    op.execute('''CREATE TABLE platform_support_sessions (
      id SERIAL PRIMARY KEY, operator_id INTEGER NOT NULL REFERENCES platform_operators(id), tenant_id INTEGER NOT NULL REFERENCES ktels(id),
      reason TEXT NOT NULL CHECK (btrim(reason) <> ''), ticket TEXT, token_hash VARCHAR(64) NOT NULL UNIQUE,
      expires_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX ix_platform_support_sessions_tenant_id ON platform_support_sessions(tenant_id)')
    op.execute('CREATE INDEX ix_platform_support_sessions_operator_id ON platform_support_sessions(operator_id)')
    op.execute('ALTER TABLE platform_support_sessions ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE platform_support_sessions FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_read ON platform_support_sessions FOR SELECT USING (tenant_id = public.ktel_current_tenant())')
    op.execute('ALTER TABLE domain_email_outbox ALTER COLUMN identity_token_id DROP NOT NULL')
    op.execute(f'''CREATE FUNCTION public.platform_end_support_sessions(p_operator_id integer, p_tenant_id integer, p_ip text, p_by text)
        RETURNS integer LANGUAGE plpgsql {DEFINER} AS $$
        DECLARE ended integer;
        BEGIN
          IF p_by NOT IN ('operator','logout','replaced') THEN RAISE EXCEPTION 'Unknown support session ending'; END IF;
          WITH closed AS (
            UPDATE platform_support_sessions SET ended_at=now()
            WHERE operator_id=p_operator_id AND (p_tenant_id IS NULL OR tenant_id=p_tenant_id) AND ended_at IS NULL AND expires_at>now()
            RETURNING id, tenant_id)
          INSERT INTO platform_audit(operator_id,tenant_id,action,detail,ip)
            SELECT p_operator_id, closed.tenant_id, 'support_session_ended', jsonb_build_object('by',p_by,'session',closed.id), left(p_ip,100) FROM closed;
          GET DIAGNOSTICS ended = ROW_COUNT;
          RETURN ended;
        END $$''')
    op.execute(f'''CREATE FUNCTION public.platform_start_support_session(p_tenant_id integer, p_operator_id integer, p_reason text,
        p_ticket text, p_token_hash text, p_ip text) RETURNS timestamptz LANGUAGE plpgsql {DEFINER} AS $$
        DECLARE customer record; ends timestamptz;
        BEGIN
          IF btrim(coalesce(p_reason,'')) = '' THEN RAISE EXCEPTION 'A reason is required' USING ERRCODE='22023'; END IF;
          SELECT k.status, k.support_access_until INTO customer FROM ktels k WHERE k.id=p_tenant_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'Unknown organization' USING ERRCODE='KT404'; END IF;
          IF customer.status IN ('suspended','cancelled') THEN RAISE EXCEPTION 'Organization suspended' USING ERRCODE='KT403'; END IF;
          IF customer.support_access_until IS NULL OR customer.support_access_until <= now() THEN
            RAISE EXCEPTION 'Support access is not enabled' USING ERRCODE='KT401';
          END IF;
          PERFORM public.platform_end_support_sessions(p_operator_id, NULL, p_ip, 'replaced');
          ends := least(now() + interval '60 minutes', customer.support_access_until);
          INSERT INTO platform_support_sessions(operator_id,tenant_id,reason,ticket,token_hash,expires_at)
            VALUES (p_operator_id, p_tenant_id, btrim(p_reason), nullif(btrim(p_ticket),''), p_token_hash, ends);
          INSERT INTO platform_audit(operator_id,tenant_id,action,reason,ticket,detail,ip)
            VALUES (p_operator_id, p_tenant_id, 'support_session_started', btrim(p_reason), nullif(btrim(p_ticket),''),
                    jsonb_build_object('ends_at',ends), left(p_ip,100));
          RETURN ends;
        END $$''')
    op.execute(f'''CREATE FUNCTION public.platform_support_state(p_tenant_id integer, p_operator_id integer)
        RETURNS TABLE(access_until timestamptz, session_ends_at timestamptz) LANGUAGE sql STABLE {DEFINER} AS $$
        SELECT k.support_access_until,
          (SELECT max(least(s.expires_at, k.support_access_until)) FROM platform_support_sessions s
            WHERE s.tenant_id=k.id AND s.operator_id=p_operator_id AND s.ended_at IS NULL AND s.expires_at>now()
              AND k.support_access_until>now() AND k.status NOT IN ('suspended','cancelled'))
        FROM ktels k WHERE k.id=p_tenant_id $$''')
    op.execute(f'''CREATE FUNCTION public.ktel_support_request(p_token_hash text, p_method text, p_path text, p_ip text)
        RETURNS TABLE(support_session_id integer, support_tenant_id integer, support_ends_at timestamptz) LANGUAGE plpgsql {DEFINER} AS $$
        DECLARE hit record;
        BEGIN
          SELECT s.id, s.tenant_id, s.operator_id, least(s.expires_at, k.support_access_until) AS ends INTO hit
            FROM platform_support_sessions s JOIN ktels k ON k.id=s.tenant_id JOIN platform_operators o ON o.id=s.operator_id AND o.is_active
            WHERE s.token_hash=p_token_hash AND s.ended_at IS NULL AND s.expires_at>clock_timestamp()
              AND k.support_access_until>clock_timestamp() AND k.status NOT IN ('suspended','cancelled');
          IF NOT FOUND THEN RETURN; END IF;
          INSERT INTO platform_audit(operator_id,tenant_id,action,detail,ip)
            VALUES (hit.operator_id, hit.tenant_id, 'support_request',
                    jsonb_build_object('method',left(p_method,16),'path',left(p_path,500)), left(p_ip,100));
          RETURN QUERY SELECT hit.id, hit.tenant_id, hit.ends;
        END $$''')
    op.execute(f'''CREATE FUNCTION public.ktel_end_support_sessions() RETURNS integer LANGUAGE plpgsql {DEFINER} AS $$
        DECLARE scope bigint := public.ktel_current_tenant(); ended integer;
        BEGIN
          IF scope IS NULL THEN RAISE EXCEPTION 'An organization scope is required'; END IF;
          WITH closed AS (
            UPDATE platform_support_sessions SET ended_at=now() WHERE tenant_id=scope AND ended_at IS NULL AND expires_at>now()
            RETURNING id, operator_id)
          INSERT INTO platform_audit(operator_id,tenant_id,action,detail)
            SELECT closed.operator_id, scope, 'support_session_ended', jsonb_build_object('by','customer','session',closed.id) FROM closed;
          GET DIAGNOSTICS ended = ROW_COUNT;
          RETURN ended;
        END $$''')
    op.execute(set_status('''
            WITH closed AS (
              UPDATE platform_support_sessions SET ended_at=now() WHERE tenant_id=p_tenant_id AND ended_at IS NULL AND expires_at>now()
              RETURNING id, operator_id)
            INSERT INTO platform_audit(operator_id,tenant_id,action,detail)
              SELECT closed.operator_id, p_tenant_id, 'support_session_ended', jsonb_build_object('by','suspension','session',closed.id) FROM closed;
            UPDATE platform_support_sessions SET ended_at=now() WHERE tenant_id=p_tenant_id AND ended_at IS NULL;'''))
    for signature in SIGNATURES:
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC')


def downgrade():
    op.execute(set_status(''))
    for signature in SIGNATURES:
        op.execute(f'DROP FUNCTION {signature}')
    op.execute('DELETE FROM domain_email_outbox WHERE identity_token_id IS NULL')
    op.execute('ALTER TABLE domain_email_outbox ALTER COLUMN identity_token_id SET NOT NULL')
    op.execute('DROP TABLE platform_support_sessions')
