"""Encrypted identity email delivery and durable anonymous attempt budgets."""
from alembic import op

revision='0004_identity_delivery'
down_revision='0003_identity'
branch_labels=None
depends_on=None

DDL=['\n'
 'CREATE TABLE identity_rate_limits (\n'
 '\tkey_hash VARCHAR NOT NULL, \n'
 '\twindow_start TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tattempts INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (key_hash)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE domain_email_outbox (\n'
 '\tid VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tidentity_token_id VARCHAR NOT NULL, \n'
 '\tkind VARCHAR NOT NULL, \n'
 '\tencrypted_payload VARCHAR NOT NULL, \n'
 '\tdelivery_status VARCHAR NOT NULL, \n'
 '\tattempts INTEGER NOT NULL, \n'
 '\tattempt_token INTEGER NOT NULL, \n'
 '\tworker_id VARCHAR, \n'
 '\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tsent_at TIMESTAMP WITH TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, identity_token_id) REFERENCES domain_identity_tokens (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_email_outbox_delivery_status ON domain_email_outbox (delivery_status)',
 'CREATE INDEX ix_domain_email_outbox_tenant_id ON domain_email_outbox (tenant_id)']

def upgrade():
    for statement in DDL:
        op.execute(statement)
    for table in ('domain_email_outbox','identity_rate_limits'):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY tenant_isolation ON domain_email_outbox FOR ALL
        USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())''')
    op.execute('''CREATE FUNCTION public.ktel_auth_budget(key text,seconds integer,attempt_limit integer) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off AS $$
        DECLARE used integer;
        BEGIN
            IF length(key)<>64 OR seconds<1 OR seconds>86400 OR attempt_limit<1 OR attempt_limit>1000 THEN
                RAISE EXCEPTION 'Invalid authentication budget' USING ERRCODE='22023';
            END IF;
            INSERT INTO public.identity_rate_limits(key_hash,window_start,attempts) VALUES(key,clock_timestamp(),1)
            ON CONFLICT(key_hash) DO UPDATE SET
                attempts=CASE WHEN identity_rate_limits.window_start<clock_timestamp()-make_interval(secs=>seconds)
                              THEN 1 ELSE identity_rate_limits.attempts+1 END,
                window_start=CASE WHEN identity_rate_limits.window_start<clock_timestamp()-make_interval(secs=>seconds)
                                  THEN clock_timestamp() ELSE identity_rate_limits.window_start END
            RETURNING attempts INTO used;
            RETURN used<=attempt_limit;
        END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.ktel_auth_budget(text,integer,integer) FROM PUBLIC')


def downgrade():
    op.execute('DROP FUNCTION public.ktel_auth_budget(text,integer,integer)')
    op.drop_table('identity_rate_limits')
    op.drop_table('domain_email_outbox')
