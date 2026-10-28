"""Tenant memberships, invitations and server-revocable sessions."""
from alembic import op

revision='0003_identity'
down_revision='0002_tenant_boundaries'
branch_labels=None
depends_on=None

TABLES=['domain_identity_tokens', 'domain_memberships', 'domain_auth_sessions']

DDL=['\n'
 'CREATE TABLE domain_identity_tokens (\n'
 '\tid VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\ttoken_hash VARCHAR NOT NULL, \n'
 '\tkind VARCHAR NOT NULL, \n'
 '\temail VARCHAR NOT NULL, \n'
 '\trole VARCHAR, \n'
 '\tuser_id INTEGER, \n'
 '\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tconsumed_at TIMESTAMP WITH TIME ZONE, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, user_id) REFERENCES users (ktel_id, id), \n'
 "\tCHECK (kind IN ('invitation','reset')), \n"
 "\tCHECK (role IS NULL OR role IN ('admin','dispatcher','fleet_manager','driver','management','viewer')), \n"
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_identity_tokens_expires_at ON domain_identity_tokens (expires_at)',
 'CREATE INDEX ix_domain_identity_tokens_kind ON domain_identity_tokens (kind)',
 'CREATE INDEX ix_domain_identity_tokens_tenant_id ON domain_identity_tokens (tenant_id)',
 'CREATE UNIQUE INDEX ix_domain_identity_tokens_token_hash ON domain_identity_tokens (token_hash)',
 '\n'
 'CREATE TABLE domain_memberships (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\trole VARCHAR NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tdriver_id INTEGER, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tUNIQUE (tenant_id, user_id), \n'
 '\tFOREIGN KEY(tenant_id, user_id) REFERENCES users (ktel_id, id), \n'
 '\tFOREIGN KEY(tenant_id, driver_id) REFERENCES domain_drivers (tenant_id, id), \n'
 "\tCHECK (role IN ('admin','dispatcher','fleet_manager','driver','management','viewer')), \n"
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_memberships_tenant_id ON domain_memberships (tenant_id)',
 'CREATE INDEX ix_domain_memberships_user_id ON domain_memberships (user_id)',
 '\n'
 'CREATE TABLE domain_auth_sessions (\n'
 '\tid VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tmembership_id INTEGER NOT NULL, \n'
 '\ttoken_hash VARCHAR NOT NULL, \n'
 '\tcsrf_hash VARCHAR NOT NULL, \n'
 '\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\trevoked_at TIMESTAMP WITH TIME ZONE, \n'
 '\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id, user_id) REFERENCES users (ktel_id, id), \n'
 '\tFOREIGN KEY(tenant_id, membership_id) REFERENCES domain_memberships (tenant_id, id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_auth_sessions_expires_at ON domain_auth_sessions (expires_at)',
 'CREATE INDEX ix_domain_auth_sessions_membership_id ON domain_auth_sessions (membership_id)',
 'CREATE INDEX ix_domain_auth_sessions_tenant_id ON domain_auth_sessions (tenant_id)',
 'CREATE UNIQUE INDEX ix_domain_auth_sessions_token_hash ON domain_auth_sessions (token_hash)',
 'CREATE INDEX ix_domain_auth_sessions_user_id ON domain_auth_sessions (user_id)']

def upgrade():
    op.execute("ALTER TABLE ktels ADD COLUMN timezone VARCHAR NOT NULL DEFAULT 'Europe/Athens'")
    for statement in DDL:
        op.execute(statement)
    op.execute('''INSERT INTO domain_memberships(tenant_id,user_id,role,is_active,version,created_at)
        SELECT ktel_id,id,CASE WHEN is_admin THEN 'admin' ELSE 'viewer' END,COALESCE(is_active,false),1,now()
        FROM users''')
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY tenant_isolation ON "{table}" FOR ALL
            USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())''')
    for function,field in (('ktel_session_by_token','token_hash'),('ktel_session_by_id','id')):
        op.execute(f'''CREATE FUNCTION public.{function}(identifier text) RETURNS SETOF public.domain_auth_sessions
            LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off
            AS $$ SELECT * FROM public.domain_auth_sessions
                WHERE "{field}"=identifier AND revoked_at IS NULL AND expires_at>clock_timestamp() $$''')
        op.execute(f'REVOKE ALL ON FUNCTION public.{function}(text) FROM PUBLIC')
    op.execute('''CREATE FUNCTION public.ktel_identity_token(identifier text) RETURNS SETOF public.domain_identity_tokens
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off
        AS $$ SELECT * FROM public.domain_identity_tokens WHERE token_hash=identifier
            AND consumed_at IS NULL AND expires_at>clock_timestamp() $$''')
    op.execute('REVOKE ALL ON FUNCTION public.ktel_identity_token(text) FROM PUBLIC')


def downgrade():
    for function in ('ktel_identity_token','ktel_session_by_token','ktel_session_by_id'):
        op.execute(f'DROP FUNCTION public.{function}(text)')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_column('ktels','timezone')
