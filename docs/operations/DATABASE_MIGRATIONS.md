# Database migrations

The API never creates/stamps tables. Run migrations explicitly as a database migration owner before starting API or worker processes; runtime credentials must not own tables or bypass RLS.

From `backend/`:

- Fresh database: `uv run python -m db.migrations upgrade`
- Existing pre-migration installation: take a backup first, then `uv run python -m db.migrations upgrade --adopt-existing`. Adoption validates the frozen baseline's tables, column types/nullability, primary/foreign keys and uniqueness. It refuses incompatible schemas instead of rewriting them.
- Check installed version: `uv run python -m db.migrations check`

Set `DATABASE_MIGRATION_URL` for the privileged migration connection. This migration/function owner must have superuser or BYPASSRLS because the narrow authentication lookup functions run under that owner while user tables enforce FORCE RLS. The prerequisite is checked before any schema mutation; a normal non-BYPASSRLS owner is rejected with an actionable error. Do not grant this prerequisite to runtime roles. Never publish credentials or use migration-owner credentials for customer requests. The fallback `DATABASE_URL` supports the current development setup until runtime-role provisioning is configured.

Migrations are atomic under PostgreSQL. A failed preflight or migration must leave the database at its previous revision; correct the reported data/schema issue and retry. Never automatically delete duplicates or fix cross-tenant references. For an existing deployment retain a tested backup/restore path; a baseline downgrade drops its tables and is for disposable test databases only, not a customer rollback procedure.

Integration tests create randomly named `ktel_test_<uuid>` databases using `KTEL_TEST_ADMIN_URL` (or the local configured database owner), run migrations and clean up only those test databases. Do not point integration administration at an external production cluster. The suite intentionally fails if real PostgreSQL is unavailable instead of claiming SQLite proves PostgreSQL behavior.

If the validated original legacy schema lacks `ktel_id` on `drivers`, `solutions` or `trips`, use the explicit `--repair-legacy-tenants` option together with `upgrade --adopt-existing`. It first verifies every affected row has an owning schedule, then derives the tenant only from that schedule. Empty tables can be repaired safely. Unowned rows stop the operation with row IDs for manual stewardship; there is no fallback to tenant 1.

After upgrading, run `uv run python -m db.provision_runtime`. It creates distinct `ktel_api` / `ktel_worker` roles, grants only table DML, sequence usage, read-only migration version, and narrowly scoped identity-function access for the API only. Neither role owns tables, bypasses RLS, creates roles/databases, or creates schema objects. Credentials are stored with mode 0600 in git-ignored `backend/.env.runtime.local`, never printed. Existing roles/files are not overwritten. Use the separate migration-owner connection for subsequent upgrades.

`DATABASE_RUNTIME_URL` and `DATABASE_WORKER_URL` are read from environment or that private local configuration file. The original `DATABASE_URL` remains the development migration-owner fallback. API and standalone worker startup validate migrations and reject owner/superuser/BYPASSRLS credentials. Provide distinct environment secrets instead of the local file in a deployment.

After subsequent migrations, run `uv run python -m db.provision_runtime --refresh-grants` before restarting services. This reconciles existing grants (including revoking obsolete worker access), without replacing passwords or private files. Identity delivery configuration and operator provisioning are documented in [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md).

Revision `0008_service_connections` adds tenant-owned optional linear same-vehicle links with composite foreign keys, active-successor/predecessor uniqueness, versioning, FORCE RLS and no CV worker table access. It expands the durable import entity check without modifying canonical records. The existing runtime grant refresh is required. Published snapshots retain their original frozen connections; changing a link marks unpublished operational drafts for source review.

Revision `0009_casefold_identity` preserves stored legacy email spelling while making login/reset discovery case-insensitive and adding a matching unique index. Before any change it refuses competing legacy addresses differing only by case/outer whitespace, reporting user IDs for explicit account stewardship. It never merges accounts. Existing narrowed identity-function privileges are preserved; use the normal migration-owner and runtime grant refresh process.
