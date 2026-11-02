# KTEL Operations Platform — Implementation Status

Updated: 2026-11-01. Branch: `feat/v2-ktel-platform`.

**The earlier claim that all phases were 100% completed and production verified was incorrect.** This document replaces that claim with observed evidence. No commits or pushes were made during this recovery. Pre-existing working-tree changes were preserved.

## Approved usability continuation — in progress

The user approved `docs/superpowers/specs/2026-11-01-guided-dispatch-workflow-design.md`. Persistent page/search/history navigation now passes4 focused browser tests, typecheck/build. Contextual Excel/CSV entry, bulk-first welcome and safe post-save return pass6 real production-browser journeys (including actual multi-row save), typecheck/build. Reusable transfer editing, clearer solver feedback and the real daily Operations board are implemented and covered by the full automated gates. Independent review remains in progress; the urgent-change prototype is not product functionality. Progress: `docs/superpowers/plans/2026-11-01-guided-dispatch-workflow-progress.md`.

## Current guided scheduling slice

The running local application now supports customer-owned Excel/CSV templates and manual entry → durable review/corrections → atomic save → dated crew/vehicle/travel preparation → persisted Studio draft → real queued CV/SSE → manual edits and independent verification → approval/publication → reload. Optional same-vehicle trip links are persisted, imported and enforced. Published labels, clocks and source inputs remain frozen; changed inputs mark future drafts for review. Normal customer flows exclude shared fixture endpoints; saved reference history is explicitly opened and read only.

The interface follows the supplied dense Studio references with consistent navigation, real KPI cards, a virtualized timeline, vehicle/driver grouping, contextual inspector, Greek/English, light/dark and responsive layouts. First use offers Excel or manual entry, required-first corrections, small travel-time groups, saved-import resumption and clear next actions. Advanced workbook sheets and connection rules stay collapsed. Unimplemented reports are absent from navigation.

Verification: production build and final strict TypeScript check pass; **15 browser tests passed in2.0m**. After the final backend cache optimization, the actual import and customer publication workflows passed again (**3 tests in38.2s**). The live PostgreSQL tenancy/runtime-role audit reports no issues. The final complete backend suite passed: **269 tests in454.78s**, exit0, including the bulk-import lookup budget and review regressions. Actual inspected captures: [screenshots](screenshots/2026-11-01/README.md). Independent review and fixes: [review](audits/2026-11-01-foundation-review.md).

Local database is at `0009_casefold_identity`; private backups preceded each migration and restricted runtime grants were refreshed. No deployment, external mail send, commit or push. Broader SaaS gates remain: full availability/leave/maintenance and legal horizon rules; incidents/driver portal/reports; queue capacity and deployment-specific load/restore/rollback; dependency remediation; external legal and solver/university commercial IP approval. This is a verified local vertical slice, not production certification.

## Office availability, leave and maintenance (2026-11-01)

Implemented, uncommitted: per-member office grants (off by default), leave approval routes, weekly working patterns and dated periods, leave lifecycle, vehicle maintenance and open out-of-service holds, usable windows frozen into new `ktel-operational-v2` drafts, solver and independent-verifier enforcement, a stale-availability gate, successor refresh with a server-derived exemption for operated trips, a lock release inside a reviewed change, derived impacts, and the Office screens. Latest gates: backend 400 passed and 1 timing-limit failure that passes alone; browser 56 of 58 on the development server (one fixed, one development-mode hydration race outside this work); typecheck clean. A clean production-build run is still owed. Acceptance, dispositions and open items: `docs/audits/2026-11-01-office-acceptance.md`. Operations: `docs/operations/OFFICE_AVAILABILITY.md`. Local database is at `0016_office_vehicle_periods`.

The sections below retain earlier recovery and task evidence; the current slice above supersedes their historical “next task” statements.

## Delivered recovery slice

- Persisted reference schedule import, immutable problem inputs, assignments and locks in PostgreSQL.
- `GET /api/v1/scheduling/revisions/active` and `POST /api/v1/scheduling/revisions/{id}/patches`.
- Atomic version check under a revision row lock, HTTP 409 on stale edits, immutable published revisions, batch validation before mutation, actor/version audit entries.
- Server-generated verification reports on load and edits: overlap, resource existence, bus type eligibility, mandatory chains and coverage reporting. Invalid drafts persist with findings; approval and publication are blocked.
- Real request-approval, approve and publish endpoints. Any assignment edit invalidates prior approval. Removed the service's absent-problem “Pre-verified” bypass.
- Server evaluates persisted tenant capabilities for every protected action. Six roles, invitation-only membership, revocable sessions and CSRF-protected browser writes are now implemented; see the continuation evidence below.
- Reference fixture is explicitly imported into a tenant-owned revision. Subsequent loads use stored inputs, not re-running legacy or greedy solvers. Source remains labeled as an imported reference archive, not a canonical live operational feed.
- Independent tenant-scoped CV consumer: `cd backend && uv run python -m app.domain.jobs.worker --tenant-id 1`. Separate spawned solver process, external deadline, heartbeat, lease-attempt fencing, verification and independently calculated metrics. Process stdout goes to the null device rather than an unbounded pipe buffer.
- Actual per-iteration best candidates are observed without changing CV search decisions. Each iteration remains available for comparison; final metadata replaces only the final iteration's provisional copy. Completed result records include seed, solver version, input hash and actual solve duration.
- State transitions and job progress events commit together. SSE includes job identity. Frontend uses cookie-authenticated fetch streaming (revocable bearer compatibility remains for API clients), cursor replay, job filtering, REST reconciliation and reconnection. REST polling reconciles silent proxy loss. Active run ID survives browser reload. Candidates never overwrite a draft automatically; explicit apply respects current locks and version.
- Workspace state is remounted for each authenticated session, preventing delayed responses from crossing login boundaries.

## Scheduling Studio visual recovery

Studied all four images under `docs/v2/KTEL_UI_Mockups/ktel_ui_mockups/` and the design tokens document. Implemented the dense studio layout, rather than copying decorative mockup data:

- Compact navy navigation, consistent icons, restrained typography, fine borders and smaller radii.
- Real assignment coverage, used resources, driving minutes and independent verification counts.
- Virtualized rows, sticky resource labels and time axis, visible grid, horizontally scrollable 24h windows, actual zoom, keyboard-operable trip blocks, route colors and distinct conflict/lock states.
- Bus and driver presentations of the documented fixed pairing model. Real service date navigation across the stored horizon.
- Contextual inspector, actual trip/station/time details, API-backed assignment/lock edits and server verification messages.
- Search, station and locked filters; trip/conflict/unassigned tables and persisted CV candidate comparison.
- Greek/English, light/dark theme persistence and layouts checked at desktop, tablet and mobile widths.
- Removed false notification badges, always-online claims, invented registrations and vehicle specifications, local publication and fabricated legal checkmarks. Mock operations component is no longer reachable from the main page; disconnected modules say so.

## Verification evidence

- Baseline before recovery: `cd backend && uv run pytest -q` — **77 passed**.
- Final recovery backend suite: same command — **88 passed in 40.60s**.
- One earlier run under simultaneous browser/build load failed the existing 5.5s performance threshold at 5.71s. No threshold was relaxed. The subsequent full run passed; this benchmark remains sensitive to shared machine load.
- Browser suite: `cd frontend && npx playwright test --reporter=line` — **5 passed in 39.3s** against development runtime; production-build rerun recorded below.
- Tests cover real lock and assignment edit/reload, verified overlap and disabled approval, authenticated SSE, actual CV candidate generation and browser reload, session response isolation, Greek/English, themes, grouping and narrow-screen overflow.
- Live PostgreSQL race probe against the running API: two writers using one version returned **[200, 409]**, exactly one version increment and unchanged assignment.
- Regression red→green observed for missing routes, eligibility checks, identity serialization, standalone worker FK bootstrap, retaining intermediate candidates and obsolete session responses. Positive publication lifecycle and edit-invalidates-approval tests pass.
- Independent review found session leakage and candidate replacement; both were fixed and covered by regressions.
- `git diff --check` passed. No git commit/push.

- `cd frontend && npm run typecheck` — passed, zero TypeScript errors.
- `cd frontend && npm run build` — passed; existing ESLint warnings remain. Root route first-load JS: 126 kB.
- `cd frontend && npx playwright test --reporter=line` against `next start` — **5 passed in 24.9s**. Final screenshots were captured from this production build, without the development overlay.
- Running locally: frontend production server at http://127.0.0.1:3000, backend at http://127.0.0.1:8000, independent tenant-1 CV worker and existing PostgreSQL container.

## Screenshots and comparison

Actual app captures are in `docs/screenshots/2026-10-30/`:

- `studio-desktop-light.png`, `studio-inspector-light.png`
- `studio-desktop-dark.png`, `studio-greek-dark.png`
- `studio-tablet-dark.png`, `studio-mobile-dark.png`
- `studio-real-cv-candidate.png`, `scheduling-inspector-light.png`

Visually inspected the real captures. The current implementation follows the reference hierarchy: left navigation, dense scheduling workspace, lower data table and contextual right panel. Pastel route blocks, grid lines, semantic status colors, compact proportions and a navy night theme replace the previous inconsistent surfaces. Fleet imagery, passenger figures, revenue, live telemetry and unimplemented controls were deliberately not copied from the references.

## Remaining production blockers and scope limits

1. **Database tenancy foundation is now implemented and locally verified (approved SaaS continuation).** Alembic baseline/adoption, real PostgreSQL RLS + FORCE RLS on all 26 existing tables, composite tenant references, protected runtime credentials, schema/role audit and migration-only administration are in place. Local API/worker use separate non-owner/non-BYPASSRLS roles. Full continuation suite: 109 passed; production browser regression: 5 passed. External deployment and later tables still require the same migration/policy gates.
2. Six persisted organization roles and capability checks, invitation/reset lifecycle, revocable HttpOnly sessions and CSRF protection are implemented and tested. Full driver portal, organization administration UI and broader business approval-policy acceptance remain open.
3. Versioned Alembic migrations now replace startup metadata creation. Fresh install, explicit adoption, safe legacy-column repair, preflight failure and backup restore/upgrade were verified on disposable PostgreSQL databases. See `docs/operations/DATABASE_MIGRATIONS.md`. Production restore/rollback drills remain an external deployment acceptance gate.
4. Reference archive contains real IDs/times but is not a live tenant operational integration. Its independent verifier reports defects; legacy solver output must not be treated as verified merely because it exists. Symbolic station transfer rules are not elapsed travel durations; they are not invented as a numeric travel matrix.
5. Daily/overnight views work. Complete weekly orchestration, revision branching/diffs, full business availability/qualifications/rest rules and 1000/2500-trip performance acceptance remain open. No claim of legal compliance.
6. Existing queue idempotency is application-level, not protected by a tenant/key uniqueness constraint; retries need limits, and broad cancellation APIs/worker observability need further hardening. Existing generic supervisor buffers output before truncation; the new CV worker avoids that capture path.
7. Existing synchronous research endpoints now require optimization.run permission; complete fixture/provenance isolation remains open. The Studio queues only bounded CV runs.
8. Frontend dependency installation reported **13 advisories (2 moderate, 10 high, 1 critical)**. No indiscriminate dependency upgrades were applied. Production dependency/security review remains required.
9. Imports/reports, live operations and driver portal are not completed product workflows. Backup/restore drills, production secret rotation, capacity limits, external legal review and solver/university commercial IP clearance are unverified.
10. Local API/worker now use provisioned runtime roles and reject privileged credentials at startup. Deployment must supply separate secrets, migrate first and provision appropriately scoped tenant workers; the Docker worker example still targets tenant 1.

Current approved work: persisted tenant roles, revocable cookie sessions/invitations, canonical operational management, guided imports and mock retirement, following `docs/superpowers/plans/2026-10-30-saas-foundation-imports.md`. Do not deploy as a production SaaS until the remaining gates are met.


## Approved SaaS continuation — identity and friendly resource entry

- Database now at `0005_resource_versions` locally. Private backups precede both identity and resource upgrades. Runtime roles preserve non-owner/non-BYPASSRLS restrictions; live tenant audit returns no issues.
- Six server-side roles, single-use hashed invitation/reset tokens, eight-hour revocable HttpOnly cookie sessions, CSRF validation, durable authentication budgets and capability enforcement. Logout/password/membership changes revoke access; open SSE checks access each poll. Browser localStorage no longer stores tokens/user authority. Organization name comes from the authenticated profile.
- Encrypted durable mail outbox, tenant-scoped delivery worker, explicit delivery status and privileged organization provisioning command. Only local SMTP sink delivery was tested; no external email was sent. See `docs/operations/IDENTITY_AND_ACCESS.md`.
- Consistent navy/teal sign-in, password recovery and invitation screens; blank credentials, labeled inputs, password visibility control, actionable errors, Greek/English and responsive layout. Actual inspected captures: `docs/screenshots/2026-10-31/`.
- Real versioned canonical driver, vehicle and station APIs with restricted PostgreSQL tests. Explicit roles, validation, active station references, source identity constraints, case-insensitive registrations and stale-write conflicts. Unknown vehicle capacity stays unknown. Archived records remain stored; relevant active references block archive.
- Guided first-use checklist and focused Drivers/Fleet forms replace reference rosters and hardcoded fleet counts. Mobile record cards keep Edit visible without horizontal scrolling. Search, pagination, optional details and actual save/reload behavior are connected to PostgreSQL. Normal missing-schedule/error states no longer offer reference import. The existing Studio snapshot still uses its labeled reference input until Task 9.
- Main planning action uses “Generate draft schedule”; search passes are in “Planning options”. Solver candidates still need explicit application and approval/publication gates.
- Identity checkpoint: full backend 129 passed, build/typecheck passed; three identity browser scenarios and real cookie/SSE CV workflow passed. Resource slice final verification: backend **135 passed in 164.81s**, production browser **9 passed in 43.5s**, strict typecheck/build/diff checks pass. One earlier concurrent-build performance run missed 5.5s at 5.62s; isolated module and final quiet full suite passed without changing the threshold.

Next approved implementation: durable import previews and atomic commit (Task 7), followed by the guided import UI and canonical Studio snapshots. Full SaaS scope and deployment/legal acceptance gates remain open.

## Guided calendars and service-day preparation (Task 5 complete)

Real recurring timetable APIs now store explicit local clocks, next-day arrival offsets, weekdays, validity dates and actual eligible fleet categories. Dated preparation is atomic and idempotent, preserves UTC instants across migration, and retains immutable versioned inputs. DST gaps/repeated clocks require explicit dated correction; all affected clock fields are reported together. Date-specific cancellation, extra service and restoration of normal rules are available from the timetable list.

Daily pairings use real active drivers, vehicles and starting bases. Confirmation records source versions; relevant source changes require review. Copied pairings are unconfirmed, and active driver/vehicle uniqueness is enforced per date. Archiving resources referenced by current/upcoming pairings is blocked until the pairing is removed. Directed transfer minutes are explicitly entered and batch-saved atomically; unknown travel inputs block readiness.

The new Timetables screen splits route/times and operating rules into two focused steps with inline station creation. Service day separates pairings, travel review and dated preparation into saved steps. Reload restores the selected date and persisted trips. The layout uses the established navy/teal shell and light/dark tokens. Actual inspected captures: `docs/screenshots/2026-10-31/service-day-*.png`.

Local development database upgraded to 0006 after private 0600 backup `/tmp/ktel-before-calendars-2026-10-31.sql` (2118099 bytes); API/CV worker restarted with existing restricted credentials. Live tenant-policy, composite-FK and runtime-role audit passes. Production build/typecheck and 11 browser scenarios pass, including explicit DST occurrence selection producing a 90-minute trip and dated cancellation. Quiet final backend run: **177 passed in 218.21s**, including unchanged solver timing checks. Final full production browser suite: **11 passed** (1.1m); after toolbar/count styling, the focused complete timetable/day/DST/cancellation journey passed in 19.6s. Final strict typecheck, production build and diff checks pass. Mobile timetable cards keep Edit and date-exception actions visible without horizontal scrolling. Additional inspected captures: `timetable-route-step.png`, `timetable-calendar-step.png`, `timetable-roster.png`, `timetable-mobile.png` in the same screenshots directory.

Canonical Studio generation, Excel templates/import review and wider availability/rest/publication acceptance remain open. This slice does not assert complete legal compliance or production readiness.

## Supported spreadsheet templates and parsers (Task 6 complete)

Versioned English/Greek XLSX and UTF-8 CSV generation covers drivers, vehicles, stations, recurring timetables, daily pairings and directed travel times. Empty review copies are in `docs/templates`; examples occur only in Instructions. Download/preview/commit product endpoints and their wizard remain Tasks 7–8, so there is no claim of a completed customer import flow yet.

The parser preserves text references/leading zeroes and original cell types, reports actual sheet/row/column/cell positions, reuses resource/calendar rules and accepts an explicit reference catalog. Template language remains independent of UI language. Unknown nonempty cells are retained and block saving. Formulas are not evaluated, active content/external relationships/XML entities are blocked, and bytes, expansion, rows, cells, styles, text and error details are bounded. Malformed coordinate order/value namespaces cannot silently erase fields; invalid numbers are safe for persisted preview serialization.

English/Greek generated workbooks pass independent Calamine-reader checks. Local 5000-service/long-Greek-name probe: XLSX generation 2.212s, parse 4.606s, peak whole-process RSS 96.6 MiB; CSV generation 0.141s, parse 1.152s, peak 92.8 MiB. Database commit and concurrent-upload capacity remain unverified until their workflows exist. The final quiet full backend suite passed **215 tests in 246.28s**, including 37 spreadsheet cases, independent-reader checks, malformed-input regressions and both solver/export timing checks. Diff checks pass. No frontend code changed after Task 5 verification. See `docs/operations/SPREADSHEET_IMPORTS.md`.

## Durable spreadsheet imports — verified continuation

- Local schema is now `0007_durable_imports`, upgraded after a private mode0600 backup. API and CV worker retain their separate restricted runtime roles; staging rows are inaccessible to the worker.
- Real XLSX/CSV upload, persisted review/correction, batch/source optimistic checks, conservative explicit identity matching, entity permissions, atomic save, idempotent retries, audit, safe error reports and commit-time populated workbooks are implemented. Legacy fixture staging remains isolated from customer routes. Missing rows never delete records.
- Source copies expire and can be purged independently of committed results and canonical records. Explicit tenant-scoped retention CLI and telemetry data minimization are documented in `docs/operations/SPREADSHEET_IMPORTS.md`.
- Full backend: **240 passed in336.05s**. Real API process restart preserved a staged preview; cookie/CSRF save, idempotent retry and workbook download passed afterward. Temporary verification tenant removed.
- Measured1000-row default: preview2.630s, save10.018s, export0.424s. Operator/parser ceiling5000 was measured separately; it is not the normal recommended interactive limit.
- Guided frontend is in progress: required-first correction, final summary, recent imports and URL resumption are connected. Browser acceptance/screenshots remain pending; do not infer UI completion from the backend evidence. Canonical Studio creation and broader SaaS/deployment acceptance remain open.

## Guided setup/import UI — verified

The Data imports placeholder is replaced by a real choose → upload → review → summary → save flow, recent imports, completed/error downloads and DB-backed reload resumption. Three primary entry choices keep first use manageable; additional sheets stay collapsed. Required fields come first in correction dialogs, keyboard focus moves to the affected field, and matching is explicit. Manual entry remains available alongside Excel/CSV templates. Slow upload replies cannot overwrite subsequent navigation. Service-day travel inputs are grouped by six and permit explicit partial saves, with real remaining counts and role guidance.

Strict TypeScript and production build pass. **13 production-browser tests passed in1.3m**, including canonical import persistence/retry and all prior CV+SSE/manual-edit/identity journeys. Actual inspected screenshots: `docs/screenshots/2026-10-31/import-{choose,choose-mobile,review,review-mobile,review-greek-dark,saved}.png`. The local schema/roles were audited clean. Next: canonical customer-data Studio draft creation and reference archive isolation (Task9); broader production acceptance remains open.

Guided workflow continuation: navigation, contextual imports, travel editor, draft feedback and publication-bound Operations are implemented; live local schema is0010. Full backend282 and browser42 gates, typecheck and production build passed. Independent review and remaining acceptance limitations are tracked in `docs/audits/2026-11-01-workflow-acceptance.md`. Evidence: `docs/superpowers/plans/2026-11-01-guided-dispatch-workflow-progress.md`.
