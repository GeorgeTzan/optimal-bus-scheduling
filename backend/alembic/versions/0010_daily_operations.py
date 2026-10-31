"""Staff reports tied to an immutable published trip, separate from planning."""
from alembic import op
revision='0010_daily_operations'
down_revision='0009_casefold_identity'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('ALTER TABLE domain_publications ADD CONSTRAINT uq_publication_revision_identity UNIQUE (tenant_id,publication_id,revision_id)')
    op.execute('ALTER TABLE domain_outbox_events ALTER COLUMN job_id DROP NOT NULL')
    op.execute('''CREATE TABLE domain_operational_trip_states (
        id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id),
        publication_id TEXT NOT NULL, revision_id TEXT NOT NULL, trip_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version>0),
        UNIQUE(tenant_id,id), UNIQUE(tenant_id,publication_id,trip_id),
        FOREIGN KEY(tenant_id,publication_id,revision_id) REFERENCES domain_publications(tenant_id,publication_id,revision_id),
        FOREIGN KEY(tenant_id,revision_id,trip_id) REFERENCES domain_revision_assignments(tenant_id,revision_id,trip_id))''')
    op.execute('''CREATE TABLE domain_operational_events (
        id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES ktels(id), state_id INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('delay','breakdown','note','departure','completion','resolution')),
        description VARCHAR(2000) NOT NULL, delay_minutes INTEGER,
        actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL, recorded_at TIMESTAMPTZ NOT NULL,
        resolved_event_id INTEGER, request_id VARCHAR(36) NOT NULL, payload_hash VARCHAR(64) NOT NULL,
        state_version INTEGER NOT NULL CHECK(state_version>0),
        UNIQUE(tenant_id,id), UNIQUE(tenant_id,state_id,id), UNIQUE(tenant_id,request_id),
        FOREIGN KEY(tenant_id,state_id) REFERENCES domain_operational_trip_states(tenant_id,id),
        FOREIGN KEY(tenant_id,state_id,resolved_event_id) REFERENCES domain_operational_events(tenant_id,state_id,id),
        FOREIGN KEY(tenant_id,actor_id) REFERENCES users(ktel_id,id),
        CHECK((kind='delay' AND delay_minutes IS NOT NULL AND delay_minutes BETWEEN 0 AND 1440) OR (kind<>'delay' AND delay_minutes IS NULL)),
        CHECK((kind='resolution')=(resolved_event_id IS NOT NULL)))''')
    for table in ('domain_operational_trip_states','domain_operational_events'):
        op.execute(f'CREATE INDEX ix_{table}_tenant_id ON {table}(tenant_id)')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_id=public.ktel_current_tenant()) WITH CHECK (tenant_id=public.ktel_current_tenant())')
    op.execute('CREATE INDEX ix_domain_operational_events_state_id ON domain_operational_events(state_id)')


def downgrade():
    raise RuntimeError('Operational history rollback requires a reviewed restore')
