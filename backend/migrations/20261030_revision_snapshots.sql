-- Apply before deploying the new revision API; development startup creates this via metadata.
BEGIN;
CREATE TABLE IF NOT EXISTS domain_revision_snapshots (
    revision_id varchar PRIMARY KEY REFERENCES domain_schedule_revisions(revision_id),
    tenant_id integer NOT NULL REFERENCES ktels(id),
    problem_data json NOT NULL,
    source_data json NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_domain_revision_snapshots_tenant_id ON domain_revision_snapshots(tenant_id);
COMMIT;
