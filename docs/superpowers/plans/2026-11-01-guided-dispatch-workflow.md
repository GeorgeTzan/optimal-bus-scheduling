# Guided Dispatcher Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bulk setup, reusable travel times, proposal review and daily published-schedule operations understandable, fast and persistent.

**Architecture:** Retain Next.js/React and the authoritative FastAPI/PostgreSQL modular monolith. Reuse the existing import/verifier/CV pipeline; add focused navigation, transfer editing and published-trip reporting modules. Operational reports are separate from immutable published assignments, with authenticated REST and tenant event hints.

**Tech Stack:** Existing Python/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Next.js15/React19/strict TypeScript, Lucide, Playwright and pytest. No new runtime dependency is required.

**Spec:** `docs/superpowers/specs/2026-11-01-guided-dispatch-workflow-design.md` — user approved the written design and clickable prototype with “sure looks good.”

## Global Constraints

- Preserve the existing dedicated `feat/v2-ktel-platform` working tree. No commit, push, destructive data replacement, production deployment or external message.
- Native inline execution is preserved from the approved workflow. Design approval and the user's instruction to implement authorize execution; do not introduce another routine approval gate. One fresh whole-project code review at the end.
- Existing records, published history, RLS/composite tenant boundaries, non-owner runtime roles, CSRF, revocable sessions and independent verification remain mandatory.
- No GPS/telematics provider, simulated telemetry, invented confirmations, automatic proposal application/publication, arbitrary spreadsheet mapping or full recovery/driver portal/legal-rule expansion.
- Existing templates/import limits remain1000 rows and5MiB by default. Missing transfer durations never become zero; reverse directions are independent. Dates and actual clocks use tenant timezone/DST rules.
- Show one obvious next action; support Greek/English, themes, keyboard focus, reduced motion and responsive layouts. Use approved navy/blue/teal tokens and SVG icons.
- New migrations require disposable PostgreSQL evidence, private backup, explicit local upgrade and runtime grant refresh before restart. Run timed CV tests without concurrent browser/build load.

## Review Focus

1. Navigation changes while a slow import/create/solver request completes: old work must not redirect or populate a different tenant, view, date or revision (Tasks1,2,4).
2. Many required transfer pairs beyond the100-item readiness sample, stale station confirmations and conflicting updates of opposite directions: complete counts, pagination and atomic source/version validation without defaults (Task3).
3. A solver finishes before its first UI poll, fails with intermediate candidates or is restored on reload: authoritative results and useful recovery remain visible without auto-application (Task4).
4. A newer publication appears while a dispatcher records an update: the report remains bound to its original publication/trip, and history cannot leak to another tenant or publication (Tasks5,6).
5. Two dispatchers retry/report/resolve concurrently: one durable result per idempotency key, conflicts preserve input, and planned versus confirmed status stays distinct (Tasks5,6).

## File boundaries and interfaces

- `frontend/src/features/navigation/workspace-location.ts` and `use-workspace-navigation.ts`: validate/serialize view/date/import context, push/replace history and popstate. `use-list-location.ts` owns bounded list search/page URL state; no business fetches.
- Existing record/timetable/import/setup workspaces: visible contextual entry, actual templates and safe post-save return. No duplicated importer.
- `backend/app/domain/timetables/transfer_editor.py`, schemas and API: required/stored directed-pair pagination and atomic version/source-checked editing. `frontend/src/features/timetables/TransferWorkspace.tsx` owns the reusable editor.
- `frontend/src/features/scheduling/RunFeedback.tsx` and existing Studio/job hook: readable run states, actionable results and failure recovery. Existing REST remains authoritative.
- `backend/app/domain/incidents/operations_models.py`, `operations.py`, `operations_schemas.py`, `app/api/operations.py`: durable published-trip states/events, publication-bound reads and authorized report/resolution. Existing legacy incident/recovery models are preserved.
- `frontend/src/features/operations/{contracts.ts,OperationsWorkspace.tsx,ReportDialog.tsx}`: published-day board and real reports, independent of active draft loading.

## Task 1: Persistent navigation and list context

**Files:** new navigation modules above; modify `frontend/src/app/page.tsx`, `ResourceWorkspace.tsx`, `TimetableWorkspace.tsx`; test `frontend/tests/workflow-navigation.spec.ts`.
**Interfaces:** `readWorkspaceLocation(url: URL): WorkspaceLocation` returns validated `view: ShellTab`, `serviceDate: string|null`, `entity: Entity|'all'|null`, `returnTo: Destination|null`; `useWorkspaceNavigation()` returns location and `navigate(view, options?)`, with push for page changes and replace for local state normalization. `useListLocation()` returns bounded q/page setters and popstate synchronization.
- [ ] Write browser regressions using the real disposable canonical fixture: Drivers search→Fleet→back restores Drivers/filter; reload retains Drivers; forward returns Fleet; unknown view/page/date safely normalize; archive remains explicit/read-only.
- [ ] Run `cd frontend && npx playwright test tests/workflow-navigation.spec.ts --reporter=line`; expected RED: reload opens Studio or back does not restore.
- [ ] Implement validated navigation/list state, retain import batch URL and tenant/revision late-response fencing, and replace internal setActiveTab transitions with the same navigation path.
- [ ] Run the new navigation test, existing session-isolation/reference-archive browser tests and strict typecheck; expected all PASS. Record evidence without committing.

## Task 2: Contextual bulk entry and first-use clarity

**Files:** existing SetupWelcome, ResourceWorkspace, TimetableWorkspace, ImportWorkspace/contracts and root; test `frontend/tests/bulk-entry.spec.ts`, existing imports/resources/timetables specs.
**Interfaces:** `openImport(entity: Entity|'all', returnTo: Destination)` encodes safe context. ImportWorkspace accepts initial entity/context and offers a real post-save return; reviewed batch entity overrides stale initial entity. Write capabilities govern both CTA and backend.
- [ ] Add RED browser cases: Drivers and Timetables expose bulk entry, preselect the right actual template, preserve context through reload and return after a real save; empty tenant sees bulk-first and manual alternative; slow upload cannot undo navigation.
- [ ] Run `npx playwright test tests/bulk-entry.spec.ts --reporter=line`; expected missing contextual action.
- [ ] Wire actual import engine and template downloads from each page; improve first-use/daily-use copy without renaming existing tested manual actions gratuitously. Preserve current batch/identity matching and permission behavior.
- [ ] Run bulk-entry, imports, resources and timetables browser tests and typecheck; expected PASS and real saved records. No commits.

## Task 3: Understandable reusable transfer editor and chosen-date crew copy

**Files:** new transfer_editor module, operational schemas/API, TransferWorkspace; modify ServiceDayWorkspace; tests `backend/tests/integration/test_transfer_editor.py`, `frontend/tests/travel-times.spec.ts` and existing timetables tests.
**Interfaces:** GET `/api/v1/transfers/editor?service_date=YYYY-MM-DD&filter=required|missing|all&page=1&page_size=25` returns paired directions, actual saved ids/versions/minutes/review state, station versions, aggregate counts and total. POST `/api/v1/transfers/editor` accepts up to100 changed directions with current station versions and expected record version (`null` means new), and saves the whole request atomically. Existing endpoints/imports remain compatible.
- [ ] Write RED real PostgreSQL cases for visible saved values, more than100 missing directions with complete pagination/counts, partial save, reverse independence, stale source/version conflict with no prefix writes, foreign tenant and viewer refusal.
- [ ] Run `uv run pytest tests/integration/test_transfer_editor.py`; expected404/missing interface.
- [ ] Implement tenant/date-scoped required-pair querying independent of the readiness sample, current source/version checks under the organization lock and flush-only domain saves; no unbounded all-pairs frontend or unknown→zero fallback. Reuse transfer DTO/domain validation and immutable snapshot staleness.
- [ ] Add RED browser coverage for readable explanation/example, stored values remaining editable after completion, single-direction save/reload, explicit reverse-copy choice, contextual transfer import, and choosing a crew-copy source date without overwriting existing target crews.
- [ ] Implement the reusable paginated editor, counts/help/review states and date picker for the existing empty-target crew-copy API. Run transfer integration, travel/timetables/import browser tests and typecheck; expected PASS.

## Task 4: Obvious draft results and unified practical Overview

**Files:** RunFeedback, SchedulingStudio, use-job-events, root, existing Overview/KPI components; tests `frontend/tests/draft-feedback.spec.ts`, optimization/overview/canonical specs.
**Interfaces:** RunFeedback consumes authoritative job status/progress/error and candidate count, with a real “Review proposal” action. Studio tracks initiation for the current revision and user-selected tab so results are revealed without redirecting deliberate navigation. Overview opens the same Studio workflow.
- [ ] Add RED actual-CV browser tests: fast completion reveals proposals; reload restores results with no fake queued bar; failure/connection recovery exposes useful next action; leaving the page during a run is respected; no assignments/publication change until explicit apply.
- [ ] Run `npx playwright test tests/draft-feedback.spec.ts --reporter=line`; expected absent completed-result action/hidden results.
- [ ] Implement submitting/queued/searching/restoring/completed/empty/failed/cancelled states, localized errors and disabled explanations; retain REST reconciliation, candidates, snapshot scoping and approval verifier. Consolidate Overview visual hierarchy/primary action with real KPIs and SVGs, including actionable no-revision readiness.
- [ ] Run draft-feedback, optimization, overview, scheduling, canonical and session-isolation browser tests/typecheck; expected PASS. Preserve source-aware publication gates.

## Task 5: Durable publication-bound Operations API

**Files:** new operations domain/API modules; `backend/alembic/versions/0010_daily_operations.py`, registry/main/runtime grants/outbox; tests `backend/tests/integration/test_daily_operations.py`.
**Interfaces:** GET `/api/v1/operations/day?service_date=...&publication_id=...&q=...&open_only=false&page=1&page_size=25` returns publication list/selection, actual trip/resource frozen facts, planned/explicit status, open-report counts/history and projection version (`0` before any report). POST `/api/v1/operations/reports` accepts publication/trip, expected version, request_id, kind=`delay|breakdown|note|departure|completion`, description and applicable delay_minutes. POST `/api/v1/operations/reports/{id}/resolve` accepts expected version/request_id/note. GET/mutation are read-only/report capabilities respectively.
- [ ] RED tests create/publish real canonical inputs; assert draft-only days have no operational publication, clocks never imply departure, reports/resolution persist, history and original publication remain unchanged, exact retries deduplicate and different retry payload conflicts. Cover two tenants/readers/drivers, physical composite FKs/RLS and API UPDATE/DELETE denial for event history.
- [ ] Run `uv run pytest tests/integration/test_daily_operations.py`; expected404.
- [ ] Add two tables: `domain_operational_trip_states` (tenant/publication/revision/trip, unique per publication/trip, version) and append-only runtime `domain_operational_events` (state, kind, description/minutes, actor, recorded_at UTC, optional resolved_event_id, request_id/payload hash). Composite FKs bind state to the same publication/revision and revision assignment; add the necessary publication composite unique key. Resolve only an open report belonging to this state. Reads never create state rows.
- [ ] Implement flush-only services with organization/state lock, source validation and expected version; role `schedule.read` reads and `incidents.manage` writes, driver-only self capability grants neither. Serialize statuses from explicit events, preserve all history and reject publication/trip reassignment. No automated recovery or publication writes.
- [ ] Extend generic outbox job_id to nullable for genuine non-job events, preserving existing job behavior; emit minimal publication/trip/version hints after the same transaction. Runtime API grants events SELECT/INSERT only; worker receives no new operational table privileges.
- [ ] Run daily-operations, migration, identity/permissions and tenant/event tests; expected PASS. Back up local DB, upgrade0010, refresh grants, restart restricted API/worker and verify schema/runtime audit. No external deployment or commits.

## Task 6: Real daily board and optional reports

**Files:** new frontend operations modules; root independent Operations route and shared date/navigation; tests `frontend/tests/daily-operations.spec.ts`.
**Interfaces:** OperationsWorkspace uses the Task5 APIs and safe view/date/publication URL context. ReportDialog preserves values on recoverable conflict and sends stable request_id retries. REST updates immediately and polls every15seconds while visible, with manual refresh; minimal authenticated event hints may accelerate refresh.
- [ ] RED browser cases: published actual customer schedule opens, new/unpublished day has an actionable empty state without requiring an active draft, record/resolve delay persists through reload, viewer cannot write, another tenant cannot access publication/history, newer publication is signaled without rebinding an old report, planned versus confirmed labels remain distinct.
- [ ] Run `npx playwright test tests/daily-operations.spec.ts --reporter=line`; expected placeholder/missing action.
- [ ] Implement actual dated board, filters, publication selector/history, frozen labels and real report counts; optional report and resolution dialogs with attribution, precise units, field-level recovery, no GPS or mandatory trip-by-trip updating. Handle abort/unmount/newer publication/409 and authorization consistently.
- [ ] Run Operations and canonical/navigation browsers, strict typecheck/build, inspect actual desktop/mobile/Greek/English/themes; expected PASS and no document overflow.

## Task 7: Page-by-page acceptance and one final review

**Files:** `docs/IMPLEMENTATION_STATUS.md`, `docs/audits/2026-11-01-workflow-acceptance.md`, screenshots/runbooks, this plan's progress ledger.
- [ ] Exercise every page/action from the spec on a new tenant, a populated tenant and reader, including resource/station forms, imports/error corrections/retries, date rules/exceptions/connections, crew copy, transfer editing/bulk/partial/review, actual CV/SSE/explicit apply/manual verifier/approval/publication, Operations/report/resolution and immutable archive.
- [ ] Run full `uv run pytest` quietly, then `npm run typecheck`, `npm run build` and the full production `npx playwright test --reporter=line`; inspect real screenshots and record actual outputs. Fix observed failures; never weaken data/tenant/solver gates to claim a green run.
- [ ] One fresh read-only whole-working-tree review including untracked source, spec/ledger and exact Review Focus; reproduce/fix Important/Critical findings in one pass and rerun affected/full gates when changes justify it.
- [ ] Record page-by-page results, migration/permissions, screenshots, limitations and later full-SaaS phases. Keep all changes uncommitted/unpushed and avoid claiming external production/GPS/legal readiness.

## Self-review and execution rulings

All design sections map to Tasks1–7. Interfaces shared by navigation/imports/travel/result/Operations are defined above; normal import limits/identity and published source data remain unchanged. Ops tables are separate from legacy incident/recovery rows and have a concrete publication/assignment integrity boundary. Transfer editor pagination replaces neither the known-matrix solver requirement nor older API contracts. The existing native method and explicit implementation authorization persist, so execution proceeds without another plan-permission round. Each task records RED/GREEN evidence and rulings in `docs/superpowers/plans/2026-11-01-guided-dispatch-workflow-progress.md`.
