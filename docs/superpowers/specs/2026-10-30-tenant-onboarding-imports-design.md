# KTEL SaaS completion: tenant onboarding and operational data design

Status: USER APPROVED — user explicitly said “i approve continue”. Implementation of this design is authorized. No commits or pushes.

## Intent and decisions already made

The user wants the remaining v2 implementation finished as a real internal KTEL operations SaaS, with mock/reference inputs removed from normal use and an easy way for each organization to add its own people, vehicles and trips. They explicitly chose supplied Excel templates plus manual entry, rather than requiring arbitrary spreadsheet mapping or postponing imports. They also explicitly require the whole UI and process to be friendly, guided and not overwhelming.

Preserve the FastAPI/PostgreSQL/Next.js architecture, existing working scheduling editor and independent CV solver. Existing v2 architecture and implementation plan remain scope anchors. This design details the next implementation project; it does not redefine the broader objective as an import wizard or claim the other phases are complete.

## Approaches considered

1. **Supplied templates + manual entry — user-selected.** Explain a supported workbook, validate predictable fields and let users make small changes in normal resource forms. Lowest uncertainty while actual KTEL source formats are unknown. Import updates have explicit stable identity rules.
2. Arbitrary spreadsheet mapping. Useful when real customer exports are available, but needs more mapping, ambiguity resolution and format-specific support. Deferred; keep parser boundaries extensible.
3. Manual-first, imports later. Easier initial implementation but tedious for hundreds of trips. Rejected as the primary onboarding path.

No assumptions about what a real KTEL currently uses are asserted. The proposed starting contract is ours, with later adapters based on actual source files.

## Scope, sequencing and remaining full objective

Deliver small independently tested slices in this order:

1. Migrations and database-enforced tenant boundaries; persisted organization identity, invitations, permissions and secure session lifecycle.
2. Canonical operational APIs and friendly manual management of drivers, vehicles, stations, timetables and daily driver–vehicle pairings.
3. Durable Excel/CSV staging, validation, review and atomic import, exposed through the guided Data Imports UI.
4. New organization setup flow and Studio creation from the tenant's own operational records; remove normal demo bootstrap, hardcoded stations and shared legacy input paths.
5. Acceptance for the complete path from empty organization to verified draft/publication, browser/API/worker restart durability, accessibility, themes and both locales.

The overarching goal then continues through remaining v2 scheduling features, availability/leave/maintenance, incident/recovery approval and driver portal, truthful reports, worker/queue hardening, dependency security, deployment/backup/restore/capacity checks and external legal/IP gates. Those remain open until implemented and verified, with additional focused designs when business policy is missing. Passenger ticketing/payments and invented subscription billing are outside the agreed scope.

## Friendly UX contract — applies across the app

- New tenants start with a calm welcome and one primary next action. Do not show an empty dashboard full of zeroes, fake statistics, or a dense timeline before setup.
- Explain the purpose and expected result of the current step. Use familiar operational words in Greek and English. Default to Greek, Europe/Athens and 24-hour times.
- Suggested journey: organization setup → add drivers → add vehicles → add timetable → choose a service day and confirm driver–vehicle pairings → generate the first draft. Stations can be added by name during timetable review; do not force users through a separate technical station-ID setup first.
- The setup checklist reflects actual persisted records/readiness. Steps save independently; users can leave, return, or use manual entry instead of upload. Optional fields and advanced settings are collapsed.
- Keep one obvious primary action per stage. Show Back and Save/Continue consistently. A user may skip a setup task and return later, but generating a schedule explains and links to unmet requirements.
- Keep the Studio available to experienced dispatchers; onboarding guidance becomes a dismissible checklist rather than a permanent wizard.
- Manual forms show required fields first, use searchable selectors for related records and validate inline without erasing input. Do not show SQL IDs, CV resource codes, CP-SAT/iteration settings or raw rule IDs as the normal user flow.
- User-facing optimization action is “Generate draft schedule” / “Δημιουργία προσχεδίου”. Advanced solver configuration remains available only where useful and under permission checks. Never imply automatic publication.
- Errors explain the problem, its location and the repair: “Timetable, row 12: arrival is earlier than departure. Mark next-day arrival if this is an overnight trip.” No generic “invalid payload” or raw traceback.
- Successful operations say what changed and offer a relevant next action. Do not use repeated confirmations for normal reversible edits. Import preview is the review step; archive/delete/publish confirmations are only where effects warrant them.
- Keyboard navigation, visible focus, labeled fields, accessible error summaries, status announcements, sufficient contrast and non-color status indicators are required. At narrow widths use cards/stacked controls and a responsive inspector; do not hide required actions.
- Preserve the premium Studio visual direction. Introduce no separate design style for onboarding, registers or imports.

## SaaS identity and tenancy

Retain invitation-only customer onboarding from the existing architecture. A platform provisioning command creates an empty organization and issues the first administrator invitation; there is no public endpoint where a caller chooses tenant IDs or grants themselves an admin role. Platform provisioning privileges are separate from tenant administration.

Persist organization profile/timezone, memberships/roles, invitations, password reset and revocable session state. Tenant roles: administrator, dispatcher, fleet manager, driver and management/view-only. The concrete permission matrix is versioned and tested. Administrator manages members/imports/configuration; dispatcher manages timetable planning and draft scheduling; fleet manager manages fleet/maintenance; driver sees their own published duties and acknowledgments; management reads approved operational information. Driver-to-member links are explicit. Existing `is_admin` tenant users migrate conservatively to tenant administrator; other users retain read-only access until explicitly assigned. No existing flag silently grants cross-tenant/platform access.

Invitation/reset tokens are random, stored hashed, expire, are single-use and never appear in logs. An SMTP adapter and transactional delivery outbox support deployment-provided mail settings; development can expose a clearly identified local invitation link to the platform operator. Production without configured mail must show an actionable delivery failure, never report “email sent”. Actual production provider/credentials are deployment configuration, not an assumption or an external send performed during development.

API and worker run with non-owner, non-BYPASSRLS roles. Set transaction-local tenant context for every tenant transaction; missing scope returns no tenant data and denies mutation. Apply RLS, including FORCE where appropriate, to every tenant-owned table, and composite tenant foreign keys to related tenant records. Global identity lookup uses a narrowly defined authentication path, not a blanket system bypass. Refresh/logout/expiry and membership changes revoke server sessions. First-party browser authentication uses a server-revocable session in an HttpOnly cookie (Secure in production, SameSite=Lax), with CSRF protection on state-changing cookie-authenticated requests, including logout. Serve the app and API through the same origin. Retain a documented bearer-authentication compatibility boundary for existing API clients/tests, tied to the same revocation and permission checks; do not retain browser tokens or authoritative identity claims in localStorage. The implementation plan must define the compatibility migration before removing old login responses.

Use versioned Alembic migrations with a tested fresh install and upgrade from the current database. Do not run metadata `create_all` at runtime. Audit and report pre-existing duplicate/cross-tenant data before enabling constraints; do not silently merge or delete it. Preserve existing snapshots and published revisions.

## Operational source of truth

Organization-owned PostgreSQL records are authoritative. Add versioning, tenant-scoped uniqueness and external source identifiers to the existing canonical models rather than building a second set of registers.

- Drivers: staff reference, name, active state, home/depot, optional contact/license/qualification fields. No mandatory personal detail unrelated to planning.
- Vehicles: human reference and registration, vehicle type, optional verified capacity and depot, active state. Do not fabricate model or seat count. Vehicle type mappings must match solver eligibility semantics; no hardcoded “01” for all imports.
- Stations/depots: human names with stable tenant-owned codes; optional alternate/localized names. Names shown in the UI come from tenant records, including snapshots of historical display labels.
- Timetables: stable trip reference, origin/destination, local departure/arrival, explicit arrival day offset, operating weekdays and validity range; optional known distance, eligible vehicle types and mandatory connections. Recurring service is materialized into dated trip instances with service exceptions/cancellations.
- Pairings: one approved driver–vehicle pair per service day/resource window for CV v1, selected through familiar driver/bus selectors. Users may copy the previous day's pairings and review changes. Neither imports nor UI claim independent joint scheduling or mid-duty swaps.

All related IDs are tenant-validated, with database constraints as a second boundary. Use UTC timestamptz plus service-local date/timezone. Use calendar deltas across month/year boundaries. Handle nonexistent and ambiguous DST instants explicitly; show a guided correction for the affected dated trip, rather than silently picking a fold. A recurring wall-clock template may be saved, but date materialization must stop on an unresolved DST ambiguity/gap. Retain template version/provenance. Changes to a timetable affect future materialization/new drafts, never mutate historical solver inputs or published revisions.

Unknown inter-station transfer requirements are not silently zero. Provide an explicit readiness/verification issue for required unconfigured travel links; an operator can enter verified durations. Do not invent journey lengths, eligibility, legal limits or cross-day rest compliance.

## Supported import contract

Versioned `.xlsx` workbook with Instructions, Drivers, Vehicles, Stations (optional), Timetable and optional Pairings/Connections sheets. Matching UTF-8 CSV templates per entity are also available. Download only the relevant template by default; offer the complete workbook as an alternative. Templates contain instructions, examples in the instructions sheet and readable column labels, not mock operational rows that could accidentally become live records. Empty sheets are ignored; users can start with just drivers and return later.

Required initial bulk fields are minimal and explained. For drivers: name and an optional existing staff reference. Vehicles require registration or an explicit stable vehicle reference; timetable rows require route names, times, service rule and a stable human trip reference. Manual entry generates readable codes where absent.

Identity matching is conservative. Supplied staff/trip references and vehicle registration map to tenant-scoped external identifiers, preserving leading zeroes. For first-time driver rows without references, assign stable references during preview and provide a populated workbook after commit. A later changed file lacking those references must not merge different people merely by name; show probable duplicates and require explicit matching or a new-record decision. Exact-file retries are idempotent. Do not require users to understand internal UUIDs.

Create/update mode is additive by default. Preview explicitly separates additions, updates, unchanged rows and unresolved matches. Missing rows never mean delete or archive. Intentional deactivation is an explicit supported action with impact checks; never silently remove assignments. Warn about updates that make future drafts stale; published history remains immutable.

Known legacy DAT/JSON reference loaders remain isolated adapters/test tooling, not a customer-wide shared live feed. Preserve backward compatibility of fixture/solver tests without keeping insecure or public fixture endpoints available in the normal SaaS runtime.

## Durable guided import flow

1. **Choose:** select “Drivers”, “Vehicles” or “Timetable”, download the matching template or use manual entry. Explain minimum data with a small real example rendered as help, not saved data.
2. **Upload:** authenticated multipart upload; derive tenant and actor from the server session. Persist batch metadata, schema version, checksum, original filename, bounded staged rows, row positions and validation state in PostgreSQL. Raw bytes are processed within configured bounds; no local process-global registry.
3. **Review:** show a short summary and actionable errors with sheet/row/column. Show suggested normalized values but never rewrite ambiguous data silently. Resolve new station names, staff matches, vehicle types and references here. Saving corrections revalidates the entire dependent batch and increments its version.
4. **Save:** commit the reviewed batch under a batch lock/version and source-record versions; stale preview returns 409 and guides refresh. Commit selected/nonempty entity sets atomically in dependency order, including source mappings and audit. On failure roll back all live writes. Store an immutable result summary so repeated requests return the same result, not duplicate inserts.
5. **Continue:** show actual imported counts, optional corrected/populated download and one next action. Batch and setup state survive browser/API/worker restarts. Error rows can be exported for correction. Manual record edits share the same domain validation.

No partial hidden success. With a workbook containing multiple nonempty sheets, the review clearly lists the whole proposed transaction. If it has blocking errors, nothing in that transaction is committed; users may submit entity templates separately as independent setup steps.

File handling: allowlisted XLSX/CSV, verified content/container checks, bounded upload bytes, sheet/row/cell counts and decompression size, no macros or external links, no formula evaluation, reject nonliteral operational cell values and explain how to paste values. Preserve text IDs/leading zeroes. Accept common Greek/English locale formats only through explicit normalization rules; ambiguous dates require correction. Protect CSV exports from spreadsheet formula injection. Limits are configured and explained before upload; batching guidance appears for larger files. Derive chosen defaults from measured worker/API capacity, not untested “unlimited” claims.

Restrict access to raw/staged personal data by role and tenant. Record who imported and confirmed changes. Retention is configurable and documented; avoid storing personal details in job/SSE payloads. Implement discard/purge for uncommitted batches without erasing committed audit summaries. This is data hygiene, not a claim of legal/GDPR certification.

## Studio and mock retirement

New tenants see setup, not the reference-import button. A service-day/period selector loads the tenant's own dated trips and usable resources. “Create draft” freezes a canonical operational snapshot and creates initially unassigned rows. The existing queue, verifier and explicit candidate application consume that snapshot. REST is authoritative; events remain hints requiring reconciliation.

Store snapshot provenance, schema/rule/solver version, actual resource types, tenant station labels and input hash. Display driver names and registrations from tenant records, not generated labels. The original reference dataset remains an explicit development/test fixture or isolated demo tenant, never an automatic fallback. Existing reference-derived tenant revisions are labeled legacy/reference and preserved for history until an administrator explicitly archives them. Do not destructively clear existing user schedules during migration.

Selecting a date with no trips gives an actionable empty state (“Add timetable” / “Choose another day”). Selecting a date without enough approved pairings explains solver readiness. Preserve the current solver's characterized resource-count restriction until a separately tested/approved solver change; a small tenant can still maintain data and edit a draft manually. Ineligible/unavailable resources and unresolved travel/rule inputs cannot be presented as publication-ready.

## Acceptance evidence required

- Fresh database migration, current-database upgrade, restart and documented rollback/recovery strategy tested on PostgreSQL.
- Two organizations with the same human codes import independently; separate least-privilege API/worker roles cannot query, mutate, reference or subscribe across tenants, including raw SQL and direct forged foreign keys. Missing tenant context fails closed.
- Invitation acceptance, duplicate/expired/reused tokens, reset, revocation and every role action have server tests. Normal onboarding requires no manual SQL or edits to `.env` per customer.
- Import actual XLSX/CSV drivers, vehicles and recurring timetable through the UI. Preview writes no live entities; staged data survives independent sessions/process restart. One invalid cross-sheet row rolls back all selected writes; a repeated commit/file retry creates no duplicate data; concurrent/stale updates are detected.
- Names with Greek characters, leading-zero codes, duplicates, empty sheets/files, month/year rollover, overnight journeys, 23/25-hour Athens days, formula cells and invalid/bounded containers are covered.
- Create service-day trips/pairings from imported data, freeze a snapshot, generate a real CV candidate, inspect and edit, verify, approve/publish according to permissions and reload successfully. Underlying source changes cannot mutate old snapshots/publications.
- New-tenant browser flow completes without reference data or developer instructions. Tests assert progressive guidance, saved setup, usable empty/error/success states, keyboard/label/focus behavior, both locales and responsive light/dark layouts. Capture actual screenshots and compare to the established design direction.
- No customer flow silently uses bundled fixture trips, hardcoded station names, fabricated vehicle properties, mock incidents or invented KPIs. Unimplemented modules remain clearly unavailable until their phase is delivered.
- Full backend tests, frontend typecheck/build and focused browser suites run after each independently deliverable task. Record actual output and remaining gates in IMPLEMENTATION_STATUS.md; no completion claims from mock-only checks.

## Builder discretion and approval boundary

The builder may choose internal module/file boundaries, parser library after compatibility/security review, workbook styling, concrete permission enum names, API pagination, transaction helpers and tested capacity limits. They may not add payments/public onboarding, auto-publish solver outputs, relax tenant isolation, infer destructive import replacement, evaluate spreadsheet formulas, invent regulatory rules or silently change CV semantics.

Before implementation, turn this design into a task-by-task plan with exact interfaces/migrations and failure-first tests. User approval of this document authorizes that plan and the described implementation scope, not production deployment, external email sends, commercial licensing decisions or git commits/pushes.

## Design review record

A fresh SaaS builder reviewed this document under the brainstorming skill and reported “nothing important left”. User-selected import approach and the user-friendly UI requirement are recorded above. Remaining routine implementation choices stay with the builder. User explicitly approved this design and instructed implementation to continue.
