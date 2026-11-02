# KTEL Operations Platform — Product Scope and Independent Safety Review

Created: 2026-11-01. Intended reviewer: Claude or another independent engineer.

**Purpose:** Define what the product is intended to support and what an independent reviewer must verify before we describe it as complete or suitable for commercial deployment. This document is a requirements and review contract, not a statement that every feature below is implemented, secure, legally compliant or production-ready.

## 1. Scope, approval and interpretation

The user approved completing a real multi-tenant KTEL operations SaaS, with customer-owned data, guided workflows and a professional Greek/English interface. The user subsequently approved the office-first availability/leave/maintenance design discussed in the side conversation, followed by recovery, driver self-service and reports. This file records that agreement for the main implementation thread and eventual independent review.

Preserve FastAPI, PostgreSQL, Next.js, the existing independent verifier and modular Christos Valouxis CV integration. Reuse working code and the approved urgent-change design; do not build competing scheduling or approval systems.

The user explicitly requires all work to remain uncommitted/unpushed until they direct git finalization. Review tracked **and untracked** files. A clean commit history is not evidence that the working tree has been reviewed.

Use the detailed approved specifications for implementation details. If this document and an earlier approved specification conflict, report the exact conflict and obtain a product decision; do not silently choose a different approval policy, algorithm or data model.

### Status categories

| Area | Status at document creation | What a final reviewer must establish |
|---|---|---|
| Tenant identity, canonical registers, imports and customer scheduling | Implemented according to existing project evidence | Independently verify the actual final code, migrations, UI and runtime |
| Guided navigation, preparation and publication-bound Operations | Implemented according to the latest workflow ledger | Verify actual behavior and documented acceptance limitations |
| Urgent schedule changes and recovery foundations | Separately approved design/plan | Determine actual implementation status; a prototype or plan is not delivery |
| Full driver availability, leave and maintenance workflows | Office-first design approved; implementation not established by this document | Verify the complete business workflow and scheduling enforcement |
| Driver portal and operational reports | Agreed follow-on scope | Verify full workflows; settle any still-undocumented policy explicitly |
| Commercial deployment, capacity, security and external clearance | Required release gates | Verify deployment-specific evidence and identify external blockers |

Status is deliberately separate from acceptance. Do not convert a requirement into “passed” because an endpoint, table, screenshot, mockup or test name exists.

## 2. Product boundaries

### Intended product

- An organization enters or imports its own drivers, vehicles, stations, timetables and operational constraints.
- Office staff prepare service days, confirm appropriate driver–vehicle pairings and generate draft schedules through the real background CV solver.
- Authorized users inspect, change, verify, approve and publish schedules with durable history.
- Availability, leave, maintenance and incidents identify conflicts and feed reviewed recovery workflows.
- Drivers access their own published duties, requests, acknowledgments and reports.
- Operational reports use authoritative stored facts and explain their provenance.

### Not automatically included or claimed

- Passenger ticket sales, payments, payroll, subscription billing or a full accounting/HR system.
- GPS tracking or automatic departure/completion inference without an actual supported data source.
- Automatic publication, autonomous incident resolution or passenger messaging.
- SMS/push/email delivery merely because a button was clicked or a database row was queued.
- Full labour-law, driving-hours, medical-fitness or vehicle-roadworthiness certification.
- Arbitrary third-party spreadsheet formats beyond the documented import contract.
- Independent joint driver/bus optimization or unrestricted mid-duty swaps beyond the supported CV pairing/change model.

Any later expansion needs an explicit requirement and acceptance evidence.

## 3. Roles and responsibilities

Business job titles and software authorization are separate. The app must not assume that a president, manager, dispatcher or vehicle owner automatically has unrestricted access.

| Responsibility | Intended support |
|---|---|
| Organization administrator | Manage accounts, organization settings and explicitly assigned permissions |
| Operations lead / Προϊστάμενος Κίνησης | Assigned responsibility for planning oversight and designated operational approvals |
| Dispatch / Γραφείο Κίνησης / Σταθμάρχης | Prepare schedules, record operational changes, review affected trips and propose recovery |
| Fleet/maintenance staff | Record maintenance and out-of-service periods and authorized vehicle release |
| Driver | Own-duty access, own requests, explicit acknowledgments and appropriately scoped problem reporting |
| Employer/bus owner, where applicable | An explicit relationship/contact and approval responsibility; ownership is not global software access |
| Management/read-only users | Authorized summaries/reports; no write permission inferred from a display title |

Allow an organization to assign the appropriate responsibilities without requiring a separate employee for every title. Preserve existing conservative account permissions when migrating; adding an approver responsibility must not silently promote all existing management/viewer accounts.

Leave approvers are configured per organization and, where appropriate, driver/employer relationship. Unknown responsibility must be visible and resolved; do not silently approve or invent an employer. Proposed default: a person cannot approve their own leave, with an explicitly designated alternative approver.

External decisions entered by office staff must retain who recorded them and the stated decision-maker. Never represent that as the external person having authenticated and approved in the app.

### Research basis, not a universal legal organization chart

- [KTEL Kefalonia internal rules](https://ktelkefalonias.gr/images/isologismoi/esoterikos-kanonismos-leitourgias-so.pdf), particularly operations/station duties on printed pages 10–11, describe scheduling, leave/rest planning and responses to disruption.
- [KTEL Pella published regulation](https://www.ktelpellas.gr/kanonismos-proswpikou-ktel/) distinguishes company staff from drivers employed by owners of affiliated buses; the linked regulation describes owner coordination with the movement office.
- [KTEL Xanthi workshop](https://www.ktelxanthis.gr/sinergio-ktel/) describes technicians working with drivers on vehicle maintenance.

These sources informed the configurable product design. They do not establish the current approval delegation, employment arrangements or applicable legal obligations of every customer KTEL. Verify those with the actual operator before deployment.

## 4. Functional acceptance requirements

Every ID below must receive an independent final disposition and supporting evidence.

### DATA — Canonical records and truthful provenance

- **DATA-01:** Drivers, vehicles, stations, timetables, pairings, connections and travel inputs are tenant-owned PostgreSQL records. Reload/process restart retains saved changes.
- **DATA-02:** Preserve supplied references and leading zeroes. Generated references are stable and human-readable. Do not silently merge people by name or redirect reserved historical import aliases.
- **DATA-03:** Unknown capacity, distances, travel times, vehicle categories, availability and operational outcomes remain unknown. Required unknown inputs produce actionable readiness/verification findings.
- **DATA-04:** Customer station/driver/vehicle labels come from authoritative customer records and frozen history. Unverified numeric-code-to-city mappings must not be presented as facts. Preserve original codes where no verified mapping exists.
- **DATA-05:** Published history retains its original inputs, labels, clocks, source versions and attribution after source records change or are archived.
- **DATA-06:** Related records must belong to the same tenant. Archiving/deactivation explains and checks affected future work; it does not delete history or silently cancel services.

### IMPORT — Supported Excel/CSV onboarding

- **IMPORT-01:** Provide documented, versioned Excel/CSV templates for supported entity sets, including required/optional fields, readable instructions and both interface languages. Example instructions must not become live operational rows.
- **IMPORT-02:** Upload → validate → review/correct/match → save → result is a real persisted workflow. It can resume after reload without browser storage becoming the source of truth.
- **IMPORT-03:** Errors identify the relevant sheet/row/field and explain a repair. Corrections and relationship matches are explicit; edited files without stable references cannot silently match a different person or vehicle.
- **IMPORT-04:** Commit-time validation rechecks permissions, source versions and dependencies. The selected transaction saves atomically. A stale preview returns a recoverable conflict; exact retries do not duplicate records. Missing rows never imply deletion.
- **IMPORT-05:** Bound upload, decompression, worksheet/row/cell/style/text and error-output costs. Test malformed containers, path traversal, macros, external relationships, XML entities and invalid/ambiguous cell values. Never evaluate spreadsheet formulas; protect exported spreadsheet/CSV content from formula injection.
- **IMPORT-06:** Parse validity alone is not tenant-reference validity. Resolve and revalidate actual driver, vehicle, station, template and connection references against the organization and staged transaction.

### PLAN — Calendars, preparation and optimization

- **PLAN-01:** Support actual operating weekdays, validity ranges, dated exceptions/cancellations and explicit next-day arrival. Month/year/leap-day boundaries work.
- **PLAN-02:** Use authoritative UTC instants with service-local dates/timezones. Ambiguous/nonexistent local times need explicit resolution. Do not silently select a DST occurrence or assume every service day has 1,440 minutes.
- **PLAN-03:** Daily pairings are explicit and checked against their actual drivers, vehicles, home stations and current constraints. Copying a prior day does not silently confirm it.
- **PLAN-04:** Actual vehicle eligibility, verified transfer requirements and supported mandatory connections reach the immutable solver snapshot and independent verifier. Reject unsupported branching/cycles instead of dropping links.
- **PLAN-05:** “Generate draft schedule” queues a real bounded CV job using the selected customer's prepared inputs. Progress, candidates, errors and terminal status are real, survive reconnect/reload and stay scoped to tenant/date/revision.
- **PLAN-06:** Candidates do not automatically replace, approve or publish a schedule. Applying one checks current versions, locks and source state and retains truthful coverage/unassigned counts.
- **PLAN-07:** Preserve the original solver as a reference; test algorithm changes for reproducibility, bounded termination, leases, attempt fencing and regressions. An interface responsiveness claim requires an actual background worker.

### STUDIO — Editing, verification and publication

- **STUDIO-01:** The timeline and inspector expose actual trip details, driver/vehicle grouping, search/filter/zoom and real manual assignment/lock edits through persisted APIs.
- **STUDIO-02:** The server independently checks supported hard constraints, including trip overlaps by underlying driver and vehicle across different pair IDs, eligibility, transfers/connections and applicable availability periods.
- **STUDIO-03:** Invalid drafts may remain visible for repair, with real findings. They cannot bypass required approval/publication checks. Missing/unavailable verification must not produce a green “verified” result.
- **STUDIO-04:** Recheck revision, base publication, relevant source/availability versions and authorization at apply/approve/publish time under an appropriate concurrency boundary. Two users cannot silently overwrite each other.
- **STUDIO-05:** Published assignments/snapshots remain immutable. New published versions use explicit successor/lineage semantics and preserve which publication remains current until a successor is actually published.
- **STUDIO-06:** Unassignment and cancellation are distinct. Cancellation requires a reason, stays auditable/visible and is consistently reflected in optimization, coverage, Operations and reports.
- **STUDIO-07:** Preserve the operator's current approved coverage/publication policy. This document does not invent a new emergency bypass, additional approval layer or permission to publish uncovered work.

### OFFICE — Driver availability and leave

- **OFFICE-01:** Office staff can record working/unavailable periods, leave requests and confirmed absences for the appropriate driver. The record identifies the subject, recorder, category, exact interval and decision history.
- **OFFICE-02:** Leave has explicit Pending, Approved, Rejected and Cancelled states. Pending requests warn planners without silently becoming approved absences. Approved leave and confirmed unavailability constrain scheduling.
- **OFFICE-03:** Enforce the configured approver and responsibility scope server-side, including own-leave protection. Repeated/concurrent decisions are versioned and cannot create conflicting silent outcomes.
- **OFFICE-04:** Supporting information is operationally minimal; a medical diagnosis is not a required scheduling field. Restrict personal notes to authorized users and keep sensitive details out of general dashboards/events/logs.
- **OFFICE-05:** Test partial-day, adjacent, overlapping, overnight, multi-day and DST periods. Do not infer unrestricted 24-hour availability because a record is missing; the supported availability basis and planning horizon must be explicit.
- **OFFICE-06:** Approving a genuine absence may create work that needs repair. Show the affected pairings, drafts and published trips; do not silently deny the absence because trips exist, reassign people, cancel trips or modify published history.
- **OFFICE-07:** Changed or cancelled absence decisions trigger an accurate recheck of affected work. They do not automatically restore old assignments or erase prior decisions.

### FLEET — Maintenance and out-of-service periods

- **FLEET-01:** Record planned maintenance, an unplanned out-of-service period, responsibility and an expected end where actually known. A generic minor issue is not automatically a breakdown.
- **FLEET-02:** Unknown return dates remain open/uncertain until explicitly resolved. Such periods cannot be treated as available merely because an estimated date passed.
- **FLEET-03:** Authorized staff record vehicle release with actor/time/reason. The app records an operational decision and does not claim mechanical certification.
- **FLEET-04:** Exclude conflicting vehicle assignments in optimization and expose/block the corresponding verification/publication conflicts. Check driver and bus identities independently of pair IDs.
- **FLEET-05:** Saving maintenance shows the affected work without mutating historical assignments. Test overlapping bookings, late extensions, early release, concurrent edits and archived vehicles.

### OPS — Daily facts, incidents and recovery

- **OPS-01:** Operations reads a clearly identified publication/service date. Scheduled time alone never establishes an actual departure, completion, delay or vehicle location.
- **OPS-02:** Authorized office staff can report an incident; later driver self-service is restricted to authorized own-duty/resource scope. Distinguish “reported”, “being handled” and “resolved” from an actual published recovery.
- **OPS-03:** Recovery follows the approved urgent-change specification: review changes against the current publication, preserve trip times when moving rows, verify actual eligibility, and create an auditable successor draft.
- **OPS-04:** Replacing only the driver while retaining a vehicle is distinct from moving a trip to an existing crew. No invented pairing, availability or legal eligibility. If no suitable replacement exists, report that explicitly.
- **OPS-05:** Protect recorded started/completed work and use the approved conservative handling of uncertain operational state. Never infer what has actually operated from a wall clock alone.
- **OPS-06:** Retain relevant prior-publication reports and recorded facts through verified lineage, with original publication/actor/time. Do not duplicate, rebind, lose or expose another tenant's reports.
- **OPS-07:** Preview/apply/publish recheck relevant versions and current facts. Exact retries are idempotent; stale/conflicting requests retain selections and provide a repair path.
- **OPS-08:** Driver/station staff can report problems as agreed. Publication and release remain authorized office actions; reporting an incident is not proof that a replacement was approved or a notification delivered.

### PORTAL — Driver self-service, after the office workflow

- **PORTAL-01:** Link an authenticated driver account to the correct canonical driver explicitly. Identity must come from the session, never a caller-supplied driver ID or bus-owner assertion.
- **PORTAL-02:** Show only authorized own published duties and relevant changes, with actual date/timezone, route, vehicle and publication/version. Drafts and other drivers' personal data must not leak.
- **PORTAL-03:** Drivers submit their own leave requests and appropriately scoped incident reports through the same office approval/handling process, with truthful status after reload.
- **PORTAL-04:** An acknowledgment identifies the exact published duty/change/version and the authenticated driver/time. Opening a page is not acknowledgment; an old acknowledgment cannot cover a later changed publication.
- **PORTAL-05:** Mobile operation, clear empty/error/offline/expired-session states, revocation and changed-driver-account links are tested. No offline-success or delivered-message claim without a real supported mechanism.

### REPORT — Operational reporting

- **REPORT-01:** Support useful date-scoped exports/summaries of assignment coverage, unassigned/cancelled work, scheduled driver time, vehicle use and schedule/operational changes from authoritative records.
- **REPORT-02:** Identify whether results describe a draft, a particular publication or explicitly recorded operational facts. Define calculations, units, timezone, filters, cancellations and overnight/DST treatment.
- **REPORT-03:** Planned time is not actual worked time. Missing actual events, occupancy, revenue or GPS remain unknown; never fill charts with invented numbers or classify unknown work as completed.
- **REPORT-04:** Enforce tenant and role scope for queries, downloads and any cached/queued result. Protect spreadsheet exports and bound costly report queries/jobs.

### UX — Guided interface and honest controls

- **UX-01:** Consistent enterprise design informed by the supplied mockups, Greek/English, light/dark and responsive layouts. Do not copy fictional mockup statistics into operational screens.
- **UX-02:** A new organization receives a calm, persisted next-step journey. Required fields/actions come first; optional/advanced controls stay secondary. Show only actions a user is authorized to use or explain a relevant blocked action.
- **UX-03:** Keyboard/touch alternatives, labels, focus restoration, error summaries, contrast and non-colour status cues are required. Mobile cards/panels keep necessary actions reachable.
- **UX-04:** Failed saves and stale conflicts preserve entered data/selections. Confirm meaningful loss of unsaved changes across close, date/tab/history navigation and reload; nested forms must not create false warnings.
- **UX-05:** Every visible business control either performs its documented action or explicitly explains an unavailable prerequisite. No decorative approvals, fake metrics, simulated optimization or false delivery/online/GPS indicators.
- **UX-06:** Loading/unknown status is distinct from a measured zero, queued job or successful result. Delayed responses cannot overwrite another date, revision, organization, session or newer navigation choice.

## 5. Mandatory security and data-integrity gates

| ID | Required independent checks |
|---|---|
| SEC-01 | Tenant scope on every read/write/download/event/job; PostgreSQL RLS and FORCE RLS on tenant tables; composite tenant foreign keys; no blanket worker/system bypass |
| SEC-02 | Separate privileged migration administration and restricted API/worker roles; no runtime table ownership, RLS bypass or schema creation; correct least-privilege grants for new tables/functions |
| SEC-03 | Server-side permission checks for every mutation and sensitive read; least privilege, scoped delegation, own-duty protection and immediate membership/session revocation |
| SEC-04 | HttpOnly browser sessions, appropriate production cookie flags, CSRF protection for cookie writes, safe origin/proxy configuration, no browser-stored authoritative credentials |
| SEC-05 | Hashed expiring/single-use identity secrets, durable abuse controls, safe password handling, no raw secrets in URLs/logs/errors/events/artifacts; honest mail configuration/delivery states |
| SEC-06 | Optimistic versions plus correct locking/transactions at check-and-write boundaries; no partial imports, stale approvals, double publication, duplicate retry or cross-session cache leak |
| SEC-07 | Immutable scheduling inputs/history, separate current operational facts, durable actor/reason/time attribution and transactional event hints/outbox where needed |
| SEC-08 | Worker deadlines, cancellation/failure handling, bounded memory/output, leases/attempt fencing and tenant/snapshot-scoped progress/candidates; no browser-blocking production solver path |
| SEC-09 | Versioned explicit migrations, safe data preflight, backups and tested restore/upgrade; no startup schema creation or destructive “repair” of ambiguous customer data |
| SEC-10 | Input/upload/export/query limits, dependency review, sanitized errors, safe secret management and deployment-specific HTTPS/proxy/CORS configuration |

Inspect actual access paths, raw SQL, caches, SECURITY DEFINER functions, file/download paths, reconnects and background jobs. ORM filters and happy-path UI tests alone are insufficient.

## 6. Required acceptance scenarios

At minimum, demonstrate these against real PostgreSQL with restricted runtime roles and actual rendered frontend behavior:

1. Empty organization → manual/Excel entry → correction/matching → atomic save → service-day preparation → real CV → review/apply → independent verification → approval/publication → browser/API/worker restart durability.
2. Second organization and driver/read-only/fleet/dispatch accounts cannot access or change unauthorized records, duties, requests, reports, downloads, jobs or events by forging identifiers.
3. Two users change the same record, approve the same request or publish against an obsolete base: conflicts are explicit, with no silent overwrite or partial success.
4. Leave is requested, approved/rejected/cancelled by the correct actor; own-approval and wrong employer/tenant attempts fail. Resulting future conflicts are accurately shown.
5. Maintenance/breakdown spans partial days, overnight work and an uncertain end. Conflicting assignments cannot be published; release is explicit and attributable.
6. A confirmed absence or maintenance change arrives after preparation, after optimization, during preview, after approval and before publication. Every unsafe stale result is caught.
7. Recover an affected future trip from a published schedule without changing original history, times, operated work, unrelated trips or reports. Exercise driver-only replacement, crew move, no replacement, cancellation and unassignment separately.
8. Driver acknowledgment belongs to the exact relevant published version; another driver, revoked account or obsolete publication cannot falsely acknowledge current work.
9. DST gap/fold, 23/25-hour days, leap day, month/year rollover, adjacent intervals and multi-day horizons are handled consistently across imports, availability, solver inputs, UI and reports.
10. Disconnect/reload during upload, worker execution, event streaming, correction, conflict recovery and date/session navigation. No fabricated success, duplicate data or late-response state contamination.
11. Verify the actual Greek/English desktop/mobile/light/dark screens, keyboard/touch operation and unsaved-form protections; compare actual captures with the reference hierarchy.
12. Load, queue fairness/capacity, deadlines, restore/upgrade/rollback and deployment failures are tested on a declared representative environment. Do not invent a supported fleet/trip capacity from small fixture tests.

## 7. Evidence and release claims

For each requirement/scenario, report one of: **PASS, FAIL, PARTIAL, NOT IMPLEMENTED, BLOCKED EXTERNALLY, NOT VERIFIED**.

PASS requires relevant implementation evidence and an actually completed verification. Include:

- Exact file paths/line references and the reviewed working-tree state.
- Actual test command, environment, fixture/input, completion/exit status and output.
- Actor, tenant, service date/timezone and revision/publication/source versions where relevant.
- Expected versus observed behavior, including failure/recovery paths.
- Actual screenshots for UI claims; a design image or prototype is not evidence of running functionality.
- Severity, reproduction steps and practical impact for each finding.

Historical checkpoints are context only. The latest guided workflow ledger reports 283 backend tests and 44 production browser tests passed; earlier sections report smaller suites and older schema versions. **These were not rerun to create this document and do not prove later features are implemented.** Verify the final tree and do not add separate historical test counts together or count interrupted/failed runs as passing.

Passing tests do not prove absence of vulnerabilities, exhaustive accessibility, legal compliance, commercial licensing clearance or production capacity.

## 8. Deployment and external acceptance

Before a commercial release, independently verify:

- A documented clean installation and upgrade path, supported Docker/local/deployment commands and correct runtime host/secret configuration.
- TLS, cookie/proxy/origin settings, secret rotation, removal/protection of development identities and restricted administration.
- Monitoring, failure visibility, worker recovery, log/data retention, backups and actual restore/rollback drills.
- Dependency vulnerabilities and their remediation or explicit assessed exceptions; no indiscriminate upgrades without regression evidence.
- Measured representative capacity and resource/cost limits, including imports, reports and simultaneous solver jobs.
- Customer-approved employment/leave/delegation and operating policies. Full legal horizon rules need authoritative requirements and appropriate external review.
- Commercial rights for the original CV solver, inherited code/data, university contributions and all relevant dependencies/assets. A package licence check does not establish rights to the entire product.
- Explicit authorization/configuration before external email/SMS/push, public deployment, production migrations or customer-data changes.

Unknown external requirements remain blockers or documented limitations. They are not solved by adding a green UI badge.

## 9. Suggested prompt for Claude

> Independently audit the KTEL Operations Platform against every requirement ID in `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md` and the linked approved specifications. Do not trust completion claims, comments, screenshots or existing tests without inspecting the actual implementation. Review the full working tree, including untracked files, and identify its revision/environment. Preserve all uncommitted changes; do not commit, push, deploy, send external messages or modify customer data.
>
> This is a read-only code review unless I explicitly authorize fixes. Run verification only in a confirmed safe disposable/local test environment; tests may create their own disposable data/artifacts. Do not migrate a real application/production database, silently alter credentials/roles, clear user data, or start conflicting services. If you cannot run a check safely, mark it NOT VERIFIED and explain why.
>
> Trace each visible business action through UI, API, permission/tenant enforcement, database transaction, verifier/worker where relevant, and reload/restart behavior. Inspect abuse, authorization, race, stale-source, file/parser, cancellation/history and failure-recovery cases. Distinguish actual operational facts from scheduled/inferred data. Check tenant isolation and underlying driver/vehicle conflicts with real PostgreSQL, not only SQLite or mocks.
>
> Produce a requirement-by-requirement status matrix with evidence; prioritized Critical/High/Medium/Low findings with file/line references and reproductions; missing functionality and misleading controls/claims; test and screenshot evidence; migration/deployment/restore/dependency/licensing gaps; and explicit remaining uncertainty. Record which areas you actually inspected and which you did not. Do not claim exhaustive safety, legal compliance or production readiness from an incomplete review. Give separate recommendations for a local demonstration, a limited customer pilot and a commercial production release.

## 10. Project references

- [Implementation status](IMPLEMENTATION_STATUS.md) — includes historical sections; establish which statements apply to the reviewed tree.
- [Foundation/imports design](superpowers/specs/2026-10-30-tenant-onboarding-imports-design.md).
- [Guided dispatcher design](superpowers/specs/2026-11-01-guided-dispatch-workflow-design.md).
- [Guided workflow ledger](superpowers/plans/2026-11-01-guided-dispatch-workflow-progress.md).
- [Urgent schedule-change design](superpowers/specs/2026-11-01-urgent-schedule-changes-design.md).
- [Urgent schedule-change implementation plan](superpowers/plans/2026-11-01-urgent-schedule-changes.md).
- [Office availability, leave and maintenance implementation plan](superpowers/plans/2026-11-01-office-availability-maintenance.md) — prepared after design approval; execution belongs in the main implementation thread.
- [Office availability acceptance and dispositions](audits/2026-11-01-office-acceptance.md) and [operations note](operations/OFFICE_AVAILABILITY.md).
- [Workflow acceptance](audits/2026-11-01-workflow-acceptance.md) and [foundation review](audits/2026-11-01-foundation-review.md).
- [Database migrations](operations/DATABASE_MIGRATIONS.md), [identity/access](operations/IDENTITY_AND_ACCESS.md), [canonical resources](operations/OPERATIONAL_RESOURCES.md).
- [Actual screenshots](screenshots/2026-11-01/README.md) and [UI design tokens](UI_DESIGN_SYSTEM.md).

Keep this contract traceable. Update status/evidence as implementation advances; change expected behavior only when the user approves the change. Completion of the earlier foundation/import project does not establish completion of the broader commercial product described here.
