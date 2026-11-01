# Guided dispatcher workflow and practical daily Operations

Status: approved by the user (“sure looks good”); implementation authorized. One fresh read-only builder check reported “nothing important left.”

## Intent and evidence

Help a KTEL adopt the application because entering its records, preparing a day, reviewing a proposal and handling ordinary daily problems is easier to understand and faster to repeat. The user chose the recommended daily Operations board, has no GPS/telematics provider, requested a page-by-page practical audit, and approved a clickable review mockup. They specifically struggled with travel times and thought drivers/trips might require individual entry.

The existing FastAPI/PostgreSQL/Next.js architecture and verified foundation remain. Current evidence is recorded in `docs/audits/2026-11-01-workflow-usability-audit.md`. Bulk Excel/CSV import already works; it must be made discoverable rather than replaced. Actual loaded travel setup hides all saved durations once complete. Reloading Drivers returns to Studio. Operations is a placeholder. A local Generate click queued a real job and completed, but completion/results are not sufficiently discoverable; this does not establish that every reported failure has the same cause.

## Approaches considered and choice

1. **Practical daily board with optional staff reports — selected by the user.** Published trips and their frozen assignments are useful without GPS; staff record an exception when informed. Adds actual durable operational state and audit requirements, but completes a useful ordinary-day workflow.
2. **Planning only; hide Operations.** Smaller and makes incompleteness honest, but leaves the desired daily workflow absent. Not selected.
3. **Live GPS control centre.** Requires an unavailable provider and integration contract. Excluded from this project; no simulated positions, inferred departures or invented telemetry.

Builder proposal: deliver the selected direction together with focused navigation/bulk-entry/travel-time/result improvements. Keep the approved navy/blue/teal visual system. UI UX Pro Max informed feedback, accessibility, hierarchy and consistency; generic marketing/landing-page recommendations and architecture-changing framework advice do not override the project.

## Goals and boundaries

- A clear first-use versus daily-use distinction. Records and recurring timetable rules are entered once; daily crews and changes are reviewed for a date.
- Contextual bulk entry from Drivers, Fleet, Timetables and travel setup, using the existing validated import engine.
- Inspectable/editable reusable travel durations with a concrete explanation and both directions visible.
- Persistent navigation, predictable back/forward/reload and clear actions after save/solver completion.
- A real published-day Operations board with optional, tenant-scoped, attributed updates and problem resolution.
- A page-by-page acceptance matrix with actual rendered evidence, not an assertion that opening a page proves every action.

No new GPS provider, public registration, arbitrary spreadsheet auto-mapping, driver portal, legal/availability-rule invention, automatic rerouting, automatic assignment application/publication, destructive import replacement, automatic confirmation of copied crews or commercial deployment. Full recovery/frozen-prefix approvals remain their separate v2 phase. Existing tenant isolation, optimistic concurrency, independent verification and immutable publication are mandatory.

## Proposed user experience

### 1. Getting records in quickly

For an empty organization, the primary route is **Εισαγωγή πολλών από Excel/CSV**; a secondary route is **Προσθήκη μίας εγγραφής**. Explain that recurring trips are defined once with operating weekdays and dates. On populated resource pages, keep single addition convenient while making the bulk action visible alongside it. Never force an operator through one form per imported record.

Contextual import opens the real wizard with entity preselected, role-appropriate templates and a safe return destination. Preserve the reviewed batch URL, retry behavior, identity matching, configured1000-row/5MiB default and atomic commit. After save, show actual additions/updates and **Επιστροφή στους οδηγούς/στόλο/δρομολόγια** or the next setup action. Navigating away during a slow upload must not be undone by its eventual response.

Use existing templates for this delivery. Arbitrary existing-file mapping and a second paste/grid input engine are not prerequisites; do not silently promise they exist. The first improvement is exposing the existing fast route where people need it. If later observation shows template preparation is the remaining bottleneck, a paste/grid experience must share this same import validation and review pipeline rather than bypassing it.

### 2. Preparing a day

Use a consistent date across Overview, preparation, Studio and Operations, and explain when a page is showing a different historical date. Show which tasks reuse stored data and which need confirmation for this day. Daily readiness uses the real existing rules, not the mere presence of records.

Allow choosing a source date for the existing crew-copy capability when the destination has no crews. Copied pairings remain pending review. If crews already exist, explain that copying will not overwrite them; users keep/edit the existing assignments. Bulk pairing imports remain available through the real advanced workbook. Do not infer availability or suitability from the previous day's use.

### 3. Travel times that make sense

Prefer **Μετακίνηση κενού οχήματος** with the explanation: “Πόσα λεπτά χρειάζεται το λεωφορείο για να φτάσει από έναν σταθμό στην επόμενη αφετηρία;” Show an optional concrete example: a bus finishes at Kiato09:10, next departs Corinth10:00, and a25-minute empty transfer arrives09:35. This is transfer feasibility, not a guarantee of complete legal compliance.

Display saved values and missing values in the same editor, with a default filter for stations needed on the selected day and an option to review the stored network. Pair opposite directions visually, retaining two independent minute values. State that they may differ. An explicit “same time on return” choice may fill the other input but never silently copy or save it. Missing values remain missing; zero is accepted only when explicitly entered according to the current domain contract. Never derive empty running from passenger-trip duration, geographic guesses or an unknown-to-zero fallback.

Show stored/missing/review-required counts and, in plain language, why the selected day needs these stations (services and crew starting bases). Keep the existing complete-known-transfer solver requirement; improving usability is not permission to weaken it. Paginate required/stored pairs and avoid generating an unbounded all-pairs DOM. The current readiness sample caps missing examples at100; a complete paginated editor must not misrepresent that sample as the whole required network.

Use the real GET/create/PATCH transfer services and versions. Saved rows remain visible and editable after completion. Station changes that invalidate confirmation show **Χρειάζεται επανέλεγχο**, with explicit review/reconfirmation instead of hiding the row. Save only entered/changed directions; partial progress persists. Editing both directions together is atomic, version-checked and source-checked. Bulk import opens the existing Transfers template directly; no hidden advanced-menu hunting. Values persist across dates and reloads; drafts made from earlier inputs become stale through existing source protection, while published schedules retain their snapshots.

### 4. Draft generation, review and publication

Investigate reported failures across the actual click→API→queue→worker→REST/SSE→candidate flow before claiming a specific fix. The result area must make all states distinguishable: ready, submitting, queued, searching, restoring an existing run, completed with proposals, completed without a proposal, failed, cancelled and connection interrupted. Use confirmed server progress only; never show a fictional initial percentage.

For a run initiated on the current Studio, bring newly available results into view unless the operator deliberately moved elsewhere; otherwise show a persistent **Η πρόταση είναι έτοιμη — Δείτε την** action. Do not navigate someone back after they leave. Results are available via reload from the correct tenant/revision run key and authoritative REST retrieval. Explain the current state and one next action close to the generate control.

Proposal readiness is not application or publication. Label review, apply-to-draft, request approval, approve and publish as distinct actions according to real permissions. Show actual changed assignments and verifier findings. Explain disabled actions with useful recovery links: published history is immutable, inputs changed, missing capability, active search or blocking findings. Failed runs provide a safe retry; any still-valid intermediate result is labeled accurately. No approved/published badge from client state alone. Overview should route into the same workflow rather than a competing optimization experience.

### 5. Daily Operations without GPS

Operations loads independently of whether an active draft exists. Its primary source is the latest authorized publication for the chosen service date, with an explicit selected publication/version. For multiple publications, show which one is being viewed and allow opening historical versions. A date without publication has an actionable empty state; authorized staff may open its Studio, readers receive appropriate guidance.

Show published trip reference, planned departure/arrival, frozen station names and assigned driver/vehicle; show unassigned coverage honestly. A scheduled clock time never changes a trip into “departed/completed.” The board does not display a live vehicle location.

An ordinary dispatcher need not mark every trip. A trip action permits **Καθυστέρηση**, **Βλάβη οχήματος** or **Άλλη ενημέρωση**, with brief required details and delay minutes where applicable. Optional explicit departure/completion reports may be available in the trip details, with their source visible. Reported status is clearly different from planned status. Display who recorded it and the recorded time in the tenant's timezone. Default recording time is server UTC; no confusing timestamp-entry requirement for an ordinary report.

Open problems can be marked resolved with a note. Preserve the original report and resolution history. A report of a delay/breakdown does not automatically change an assignment, certify a vehicle unavailable for all future work, cancel a scheduled trip, apply a recovery solution or rewrite a publication. Show **Χρειάζεται ενέργεια** where appropriate, avoiding claims that the problem was solved by filing a report.

The board supports date, trip/resource search, open-problem filter, clear empty states and manual refresh. After a report/resolution, refresh via authoritative REST. Existing authenticated tenant events may notify other open boards; REST periodic reconciliation remains the fallback. If the selected publication changes, clearly signal that a newer publication exists. Never move reports silently to a different revision.

## Data, permissions and integrity

Use the existing incidents domain and publication/snapshot boundary. Add a durable operational reporting model as needed with tenant+publication+trip identity, optimistic version/state and append-only attributed event history. The exact internal split between incident records and per-trip operational state is a builder decision; it must preserve reporting history and avoid conflating “delay reported” with actual departure/completion.

Publication/trip ownership and existence must be validated against frozen published assignments/snapshot. Use composite tenant foreign keys for new relationships wherever representable and FORCE RLS. No unscoped string ID is sufficient authorization. Existing incident/recovery rows are not deleted or reinterpreted silently. Migration adoption/preflight and explicit non-owner role grants remain required.

Read access uses `schedule.read`; report/resolve uses existing `incidents.manage` (admin/dispatcher). Management/viewer can read their authorized board. Driver self-reporting/portal remains deferred; `incidents.self.report` alone must not permit reading or reporting other drivers' duties. The UI reflects these server-enforced capabilities.

Mutations require session/CSRF, expected state version and idempotent request identity. Concurrent changes return a recoverable conflict without losing input or duplicating a report. Reports are recorded in one transaction with their audit/event hint; nothing is announced before commit. Published snapshot/assignment rows never change as a side effect. Tenant events contain only minimal identifiers/versions; no personal descriptions in transport/telemetry. Runtime workers do not gain unrelated operational table access.

## Shared usability and navigation

Preserve page, date, search/filter and pagination in bounded validated URLs; support reload, back and forward. Preserve the existing tenant/revision guards for late requests and import resumption. Unsaved form data must not disappear without an appropriate warning; do not prompt for empty untouched forms. One clear primary action at each stage, consistent button hierarchy, visible minute units and ordinary Greek/English labels. Show enough guidance to start; keep advanced rules collapsed.

Reuse existing design tokens and Lucide SVGs, replace emoji-based Overview metrics, check readable contrast and mobile text/targets, keyboard order, focus after dialog open/errors, non-colour status labels and reduced motion. Tables may scroll within their container; the entire page must not overflow. Do not redesign functioning screens gratuitously or substitute untested dependencies.

## Visual proposal and its limits

The accepted brainstorming companion contains `workflow-proposal.html` under the current `.superpowers/brainstorm/` session: bulk versus single entry; day/transfer explanation and opposite directions; generated proposal and explicit application/approval/publication; published-day optional reporting. All data and interactions are prominently labeled examples. It is a review prototype, not a customer-facing mock feature or an API implementation. The real application remains unchanged during this design step. A portable copy is retained at `docs/prototypes/ktel-workflow-proposal.html`; temporary keyed companion state is excluded locally from git.

## Acceptance and delivery

Before implementation, turn this approved design into a task-by-task implementation plan. Use regressions for real reported bugs, including lost page on reload and invisible completed results. Work in the existing dedicated dirty feature branch; preserve changes and never commit/push without the user's later instruction.

After implementation, audit each visible page and action with a disposable populated tenant, a new empty tenant and a reader role: invitation/login/logout; Overview; Drivers; Fleet/stations; Timetables/exceptions/connections; Imports/review/corrections/save/retry; day crews/copy/materialization; travel review/edit/bulk/partial save/reload; Studio search/grouping/manual verifier/CV/candidate/approval/publication; Operations/no-publication/report/resolution/conflict/isolation/reload; explicit read-only Reference archive. Check every user-visible control is functional, capability-restricted or clearly unavailable with a reason. Do not claim absent broader SaaS modules are delivered.

Exercise delayed/failed requests, empty states, stale sources, browser back/forward and two concurrent dispatchers. Published schedules must remain unchanged after reports or canonical input edits. Run the complete backend suite, strict TypeScript, production build and production-browser acceptance; capture actual desktop/tablet/mobile, Greek/English and light/dark screens. Record observed results and remaining defects in the implementation status and a page-by-page acceptance matrix. Keep CPU-heavy build/browser work separate from timed CV safety tests.

No production deployment, external messages, live GPS integration, external legal/IP decisions or git history finalization are authorized by approval of this design.
