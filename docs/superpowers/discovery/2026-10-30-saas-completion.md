# SaaS completion — discovery record

Status: discovery for user-requested Superpowers brainstorming. This is not an approved design or implementation plan. Existing no-commit/no-push rule remains in effect.

## User objective

Finish the remaining implementation as a real multi-tenant KTEL operations SaaS. Retire mock/reference data from normal operation. Make it easy for each KTEL to add its own drivers, vehicles and trips through a supported import system, then plan and operate its own schedules. Preserve the existing v2 architecture, CV primary solver and UI quality direction.

## Current-state evidence inspected this turn

- `backend/app/domain/imports/service.py`: import batches reside in module-global `_BATCH_STORE`; stages are lost on process restart and not shared across workers. Only trip imports are implemented. `expected_version` is accepted but unused. Commit performs flush, not an explicit durable transaction commit. Re-import appends records without stable external-ID/upsert semantics.
- `backend/app/domain/imports/validation.py`: CSV, JSON and legacy DAT parsers, fixed field aliases, duplicate detection within a batch. No XLSX reader, column mapping, file size limits, persisted preview or driver/vehicle import. UTF-8 decode replaces invalid bytes. Empty import and cross-reference validation need explicit acceptance criteria.
- `backend/app/domain/imports/service.py` and `optimization/adapter.py`: overnight date construction increments the numerical day of month instead of using a calendar delta; month/year-end handling is unsafe.
- `backend/app/domain/{workforce,fleet,timetables}/models.py`: separate canonical drivers, vehicles, stations, routes, templates and dated trip instances exist. Services are partially implemented, but these entities are not the Studio's authoritative live source.
- `backend/main.py`: no imports/workforce/fleet/timetable routers registered. Current `/trips` and `/drivers` are shared reference-file routes.
- `backend/app/api/scheduling.py`: only schedule bootstrap is `import-reference`; active lookup chooses latest imported revision. Need tenant-owned period/date selection and schedule creation from operational inputs.
- `frontend/src/app/page.tsx`: empty tenant is prompted to import reference archive. Import/report modules remain disconnected. Driver/fleet pages derive from revision snapshot, not canonical resource registers.
- `backend/db/models.py`: user belongs to a KTEL and has `is_admin`; organization onboarding, memberships, invitations and permission roles are incomplete.
- `backend/app/domain/identity/tenant_session.py`: optional filters target only five legacy models. The schema audit checks tenant-column presence, not PostgreSQL RLS. No verified database policies or composite tenant foreign keys.
- `backend/migrations/`: only a snapshot-table SQL migration. No complete versioned migration/bootstrap/upgrade workflow.
- `docs/IMPLEMENTATION_STATUS.md`: existing recovery evidence and unresolved gates re-read. Current working tree remains on `feat/v2-ktel-platform` with extensive existing uncommitted work.

## Full objective remains broader than imports

The existing v2 specification remains the scope anchor. Completion must include verified organization onboarding and identity; tenant isolation and permissions; tenant-owned operational registers and staged imports; schedule creation, revisions, verification and publication; durable CV execution; real availability/incident/driver workflows; honest operational reporting; deployment/migrations/backups/restore/security and supported capacity. A successful import wizard alone does not finish this objective. Passenger commerce is excluded by the existing architecture; do not infer subscriptions/billing requirements merely from the word SaaS.

## Outcomes to use in the design discussion

A new organization starts empty, adds its own data, corrects row-level errors before any live write, previews additions/updates, imports atomically, can safely import revisions without duplicates or silent deletion, and plans a dated schedule from those records. Another tenant cannot see files, previews, records, jobs or schedules. User data survives API/worker/browser restarts. Demo assets must not become live data implicitly.

Recurring timetables, service dates and driver–vehicle daily pairings must be explicit. Current CV models fixed pairings, so an import must not imply unrestricted independent driver/vehicle optimization. Human-readable station names must come from tenant records, not hardcoded station codes. Data corrections must not mutate immutable published schedules or historical solver inputs.

## Open discovery question

Asked the user what source records a KTEL is expected to have: spreadsheets, exports from existing software, paper/manual records, or unknown. Their answer determines whether guided spreadsheet import, custom export mapping or manual entry should be the primary onboarding workflow. No approach has been selected or approved yet.

## Process and next action

First discuss the source data and operational workflow. Present concrete approaches grounded in that answer, recommend one and let the user choose. Write the scoped design, run the skill's builder review, then obtain design approval before implementation. Follow with a full implementation plan and task-by-task TDD/verification. Keep the overarching SaaS objective active throughout.

## Fresh checks and user response

- `cd backend && uv run pytest tests/domain/test_imports.py -q`: 5 passed in 0.60s. These use an in-memory SQLite database and the same SQLAlchemy session; they do not verify process restart, PostgreSQL durability or independent-session visibility.
- Read-only PostgreSQL tenant-transaction probe (`tenant_transaction` + `SELECT 1`): passed on the current environment. No syntax failure should be assumed from the source expression alone. This does not establish RLS enforcement.
- User does not know which source format a KTEL would have. Presented template-first Excel + manual entry (recommended), arbitrary-sheet column mapping, and manual-first as alternatives. Asked the user to select the onboarding approach. No selection or design approval yet.

User selected supplied templates + manual entry and added that the entire UI/process must guide users without overwhelming them. Wrote `../specs/2026-10-30-tenant-onboarding-imports-design.md` with progressive onboarding, plain-language validation, optional advanced details, durable imports, tenant security and canonical scheduling. Fresh builder check returned “nothing important left”. Next step is user approval of that concrete design, then writing-plans and implementation; the full SaaS goal remains active.
