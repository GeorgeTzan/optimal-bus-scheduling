# SaaS Foundation and Guided Imports Implementation Plan

> For agentic workers: use superpowers:executing-plans inline, with TDD and a fresh final reviewer. User approved the design and said continue; do not request redundant implementation approval.

**Goal:** Let an isolated KTEL organization onboard users, manage/import its own operational records and generate persisted schedules without reference data.
**Architecture:** Existing modular FastAPI/PostgreSQL/Next.js application. Canonical records feed immutable revision snapshots and the bounded CV worker. Database-enforced tenant boundaries underpin every customer workflow.
**Tech stack:** Python 3.13, SQLAlchemy/Alembic/PostgreSQL 16, pytest, Next.js/React/TypeScript, Playwright; XLSX parser selected/tested in Task 6.
**Spec:** docs/superpowers/specs/2026-10-30-tenant-onboarding-imports-design.md (user approved).

## Global Constraints

- No commits or pushes. Preserve the existing working directory/feature branch and pre-existing uncommitted changes.
- Guided Greek/English UI, resumable setup, actionable errors and hidden advanced settings throughout.
- Tenant and permission identity comes from authenticated server state; non-owner API/worker database roles, RLS and composite tenant references.
- Imported data is additive/update-by-stable-reference, never implicit destructive replacement; previews and historical snapshots are durable.
- No formula evaluation, invented customer data, legal certification, alternative production algorithm or automatic publication.
- Existing CV behavior remains the reference; any solver changes need separate regression evidence and provenance review.
- Tests before implementation; complete suite/typecheck/build/browser checks at relevant task boundaries; record evidence, not assumptions.
- Full SaaS goal continues after this project: operations/availability/driver workflows/reporting/production readiness are not silently dropped.

## Review Focus

1. Existing data prevents new uniqueness/tenant constraints: fail with an actionable preflight rather than deleting/merging customer records (Tasks 1–2).
2. Tenant context disappears on commit/reused pooled connections: scope must be reinstalled per transaction and cleared safely (Task 2).
3. Authentication before tenant discovery must not grant arbitrary cross-tenant reads; revoked sessions and permission changes fail immediately (Task 3).
4. Re-uploaded/edited spreadsheets with missing references must not merge distinct people or create silent duplicates (Tasks 6–8).
5. Corrected source records or DST materialization cannot rewrite published schedules, snapshots or previously reviewed imports (Tasks 5,7,9).

## Task 1: Versioned schema baseline and migration runtime

Files: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_existing_schema.py`, `backend/db/metadata.py`, `backend/db/migrations.py`, `backend/tests/integration/conftest.py`, `backend/tests/integration/test_migrations.py`, `backend/main.py`.
Interfaces: `load_domain_metadata() -> MetaData`; `upgrade_database(connection: Connection, revision: str='head') -> None`; `adopt_existing_database(connection: Connection) -> None` validates known schema before stamping baseline. No silent adoption or startup writes.
- [ ] Write PostgreSQL tests for fresh upgrade/table inventory, adoption preserving seeded data, incompatible schema rejection and non-creating API startup. Disposable database only; tests must identify and clean only their own randomly named databases/roles.
- [ ] Run `uv run pytest tests/integration/test_migrations.py -q` and confirm missing migration interface failure.
- [ ] Implement immutable baseline DDL, Alembic connection injection, explicit adoption with validation and production runtime migration check. Remove all startup metadata creation. SQLite-only unit fixtures may still use metadata.
- [ ] Rerun migration tests and backend suite. Record commands/results in progress ledger; keep changes uncommitted.

## Task 2: Enforced tenant database boundaries

Files: migration `0002_tenant_boundaries.py`, `backend/db/tenant_schema.py`, `backend/app/domain/identity/tenant_session.py`, `backend/api/deps.py`, scheduling/optimization/events APIs, jobs worker, `backend/tests/integration/test_postgres_rls.py`.
Interfaces: `set_tenant_scope(session: Session, tenant_id: int) -> None` re-applies transaction-local scope on transaction begin; `tenant_transaction(session, tenant_id)` nests only within the same scope. `audit_tenant_schema(metadata)` covers all tenant tables; `audit_database_tenancy(connection) -> list[str]` inspects actual RLS/policies/FKs/roles.
- [ ] Tests use distinct non-owner API/worker roles and raw SQL: missing context empty/denied, two tenants cannot select/update/delete/insert each other's rows, forged cross-tenant FK fails, FORCE RLS applies, pool reuse/commit cannot leak context, every tenant table audited. Test schema preflight with inconsistent existing references and duplicate natural keys.
- [ ] Run `uv run pytest tests/integration/test_postgres_rls.py -q` → intended failures.
- [ ] Add constraints and policies with safe preflight; scope existing API/worker units of work. No auth/system-worker flag bypass. Migration owner remains separate from runtime roles. Provision grants through an explicit command/runbook; do not overwrite existing deployment secrets.
- [ ] Run focused tests, full backend suite and existing live scheduling/browser flows using runtime roles before declaring Task 2 complete.

## Task 3: Real organization identity, roles, invitations and sessions

Files: `app/domain/identity/{models,permissions,sessions,invitations,mail}.py`, `app/api/identity.py`, existing auth/deps/security/schemas, migrations, CLI `app/cli/provision.py`, frontend auth forms/context, tests `tests/integration/test_identity.py`, `frontend/tests/identity.spec.ts`.
Interfaces: `provision_organization(name, timezone, admin_email) -> Invitation`; `accept_invitation(token, password, full_name) -> Session`; `require_permission(permission)`; secure cookie session + CSRF, revocable bearer compatibility. Platform provisioning separate from tenant admin. SMTP delivery state never faked.
- [ ] RED tests: expired/reused/wrong token, hashed token storage, no caller role/tenant escalation, password reset/expiry/logout invalidation, same-origin CSRF, inactive membership and role enforcement, conservative migration of current users.
- [ ] Implement invitation-only organization/member lifecycle, non-global tenant roles and cookie login. Preserve tested API compatibility with the same revocation checks.
- [ ] Verify role matrix in PostgreSQL API tests and browser login/invite/logout flows; actual mail only through configured test SMTP, no external sends. Full regression suite.

## Task 4: Friendly canonical resource management

Files: existing workforce/fleet/timetables models/schemas/services; `app/api/{workforce,fleet,timetables}.py`; frontend `features/{drivers,fleet,stations}/*`; migration and tests.
Interfaces: tenant-scoped versioned CRUD under `/api/v1/{drivers,vehicles,stations}` with pagination, readable references and `version` on updates. `GET /api/v1/setup/readiness` reports actual persisted setup state, not counters in localStorage.
- [ ] RED tests: cross-tenant reference rejection, inactive resources, duplicate natural/external keys, invalid partial updates, optional unknown capacity, stale updates; keyboard and bilingual inline validation.
- [ ] Implement guided forms, searchable related-record selectors, actual records and clear empty/success states; no SQL IDs in forms.
- [ ] Verify APIs on restricted roles and browser resource creation/update/reload, then suites/typecheck/build.

## Task 5: Recurring service calendars, dated trips and daily pairings

Files: timetable models/service/time_service/adapter; new calendar/pairing modules and API; tests `tests/domain/test_calendars.py`, `tests/integration/test_operational_snapshots.py`; frontend timetable/pairing forms.
Interfaces: `materialize_service_date(tenant_id, service_date, template_versions) -> list[TripInstance]`; explicit weekdays/validity/arrival-day offsets/exceptions/folds; `create_daily_pairing(driver_id, vehicle_id, service_date, version)`; typed snapshots preserve actual vehicle eligibility and display names.
- [ ] RED tests: month/year rollover, Athens DST gap/fold, leap day, recurring/cancelled exceptions, duplicate materialization idempotency, driver/vehicle pairing uniqueness and cross-tenant FKs, source edit leaves historical snapshots unchanged.
- [ ] Implement calendar deltas and immutable materialization provenance; unresolved DST/travel inputs block readiness with plain-language guidance. No invented travel times/vehicle types.
- [ ] Verify date/pairing flow in browser and actual CV-compatible serialization, regression suites.

## Task 6: Safe versioned XLSX/CSV templates and parsers

Files: `app/domain/imports/{templates,parsers,validation,contracts}.py`, dependency lock, parser tests.
Interfaces: `generate_template(entity, locale, populated_records=None) -> bytes`; `parse_upload(content, filename, entity, locale) -> ParsedWorkbook` bounded file/container/sheet/row/cell handling; readable headers map to stable internal schema version.
- [ ] RED fixtures: Greek names, leading-zero IDs, empty sheets, unsupported format, invalid UTF-8, formulas/macros/external links, oversized/decompression-bomb containers, ambiguous date/locale/time and unknown vehicle references. Export formulas escaped.
- [ ] Implement minimal templates/CSV and vetted XLSX reader. Examples live only in Instructions. Errors carry sheet/row/column/message/code; show friendly messages by default.
- [ ] Verify generated templates round-trip through an independent XLSX reader and all parsing/security tests.

## Task 7: Durable import previews, correction and atomic commit

Files: imports staging models/service, new imports API, external IDs/audit, migration, integration tests.
Interfaces: `POST /api/v1/imports`, `GET /imports/{id}`, `PATCH /imports/{id}/rows` with version, `POST /imports/{id}/commit`, discard, error/populated export. Content checksum and idempotent commit summary. No global batch registry.
- [ ] RED tests: independent connection/restart sees staged batch, preview changes no live rows, multi-sheet invalid row rolls back all writes, stale source/batch version returns 409, exact re-upload retries and commit retries do not duplicate, missing driver refs require explicit ambiguous-match resolution, omitted rows never delete, tenant/file isolation and safe purge.
- [ ] Implement persisted stage/resolve/revalidate/review/commit, locking and transactional audit. Driver/vehicle/timetable services share validation; no hidden partial import.
- [ ] Verify whole workbook on PostgreSQL restricted API/worker roles with process/browser restart and full suite.

## Task 8: Guided import wizard and resumable setup

Files: frontend `features/imports/*`, `features/onboarding/*`, catalogs, shell navigation and browser tests.
Interfaces: choose → upload → review → save → next action. Steps persist in backend; manual entry is an equal alternate path. Required fields first, optional details collapsed, one primary action, errors link to actual cells/rows.
- [ ] RED browser tests: new empty tenant sees guidance, template download and actual XLSX upload, correction/error navigation, summary before commit, duplicate/update summary, progress restored after reload, keyboard/focus, Greek/English/light/dark and mobile.
- [ ] Implement using existing design tokens and working APIs. Do not expose solver/DB terms or fake import success.
- [ ] Inspect real screenshots and run suites/typecheck/build.

## Task 9: Studio from customer records; retire normal reference flows

Files: scheduling API/snapshots, adapter/worker readiness, frontend page/revision-api/Studio/display; reference router gating; migration/provenance; tests.
Interfaces: service-date/period lookup and `POST /api/v1/scheduling/revisions` freezes tenant-owned canonical inputs into an initially unassigned revision. Snapshot labels/resources are authoritative; legacy history remains labeled and archived only explicitly.
- [ ] RED tests: new tenant never sees bundled input, imported/manual records create a draft, no date trips gives action links, pairings/eligibility/travel readiness errors guide repair, actual CV candidate/edit/approve/publish/reload; source updates do not alter history; unsupported small-instance solver input explains restrictions without substituting algorithms.
- [ ] Implement canonical workflow and friendly “Generate draft schedule”; move advanced options behind appropriate permissions. Remove customer-accessible shared fixture endpoints/hardcoded station names/mock components, preserve explicit test/demo adapters.
- [ ] Run complete two-tenant customer journey against production frontend build and non-owner backend/worker; retain real screenshots and database checks.

## Task 10: Project acceptance, review and operations handoff

Files: `docs/IMPLEMENTATION_STATUS.md`, deployment/migration/import/identity runbooks, CI checks and final review artifacts.
- [ ] Verify every approved design acceptance requirement against actual evidence (not unit mocks). Run full pytest, PostgreSQL tenant/identity/import/snapshot integration, frontend typecheck/build and browser acceptance.
- [ ] Fresh independent review of working-tree changes and listed Review Focus. Fix important findings with failure-first regressions; repeat checks only for new changes/failures.
- [ ] Record operational limitations and explicit remaining full-SaaS phases. Leave changes uncommitted/unpushed and goal active if broader requirements remain.

## Scope continuity after this project

Subsequent projects remain required by the full goal: availability/leave/maintenance and full-horizon verification; incidents and frozen-prefix recovery approvals; driver-owned duties/acknowledgments; honest reports; queue uniqueness/retry/cancellation/observability; dependency remediation; deployment, backup/restore/rollback and capacity ladder; external legal and solver/university IP signoff. Design and implement each against v2 acceptance gates, without pretending this project's acceptance completes those requirements.

## Execution rulings and ledger

User's “i approve continue” authorizes implementation of the approved design. Native execution selected to keep costs and coordination low; final fresh review retained. The current dedicated feature branch contains the working application in uncommitted files, so retain this workspace rather than a clean worktree that would omit those changes. This overrides generic skill worktree/commit steps. Progress/evidence are recorded in `docs/superpowers/plans/2026-10-30-saas-foundation-imports-progress.md`.
