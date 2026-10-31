# KTEL Operations Platform — Revised Design Specification (v2)

**Status:** Proposed revision following independent pre-implementation review, 2026-10-30. User-approved architecture and product scope retained; this revised document requires review before implementation.

## Intent, scope and exclusions

Build an excellent software-engineering portfolio project that can become a commercial SaaS for **internal** KTEL operations: administrators, dispatchers, drivers, fleet managers and management. Support daily and weekly planning, recurring timetables, leave, maintenance, disruptions, versioned publication, multi-tenant isolation, imports and advanced optimization. No passenger bookings, ticket sales, payments or public portal.

Goals: correct, explainable, safe, operable scheduling; maintainability and future improvements of Christos Valouxis's CV solver; elegant Greek/English UI; measured scalability. Non-goals for pilot: microservices, experimental solver auto-publication, fully independent driver/vehicle joint optimization, perfect automatic weekly scheduling, passenger systems.

## Chosen architecture and alternatives

**Chosen:** FastAPI modular monolith + PostgreSQL + isolated per-job Python solver processes + Next.js/React/TypeScript. Domain modules: identity/tenancy, timetables, workforce, fleet, scheduling, optimization, incidents, imports, notifications/audit. REST is authoritative for mutations and retrieval; authenticated SSE provides one-way progress and operational notifications, with reconnection/replay. WebSockets remain a future opt-in for bidirectional co-editing/presence after measurable need. Alternative A (in-process synchronous solve) risks blocking and lack of bounded cancellation. Alternative B (Redis/Celery from day one) increases operations cost; defer until PostgreSQL job claiming demonstrably falls short. Alternative C (microservices) adds distributed consistency problems without current benefits.

**Job design:** a PostgreSQL-backed job queue with transactional claim (e.g. `FOR UPDATE SKIP LOCKED`), leases and heartbeat, retry policy, owner/tenant IDs, idempotent submission, persisted timestamps, terminal state, cancellation request and result references. A supervisor spawns one isolated subprocess per solve and enforces an external hard wall-clock deadline; force-kill non-cooperative runs, record failure, and never alter a published schedule. Spawn processes do not inherit connection pools. Durable outbox rows are written transactionally with state changes and can be streamed as SSE updates; clients always refresh authoritative REST state on reconnect. No implicit exactly-once delivery assumption.

## Tenancy, roles and database integrity

Use organization-level tenancy with `tenant_id` scoped access and PostgreSQL row-level security on every tenant-owned table, enforced in API and worker transactions using `SET LOCAL app.tenant_id`, a non-owner least-privilege role, `FORCE ROW LEVEL SECURITY` where appropriate, and explicit administrative service pathways. Composite foreign keys involving tenant IDs prohibit cross-tenant references; CI schema audit detects missing RLS policies. Never take tenant identity from a caller-supplied query/body value. Invitation-based onboarding, role/permission checks and short sessions; audit material operational changes. Confirm all claims with integration tests using separate application/worker roles.

## Domain and temporal model

- Tenant, User, RoleAssignment, Invitation, AuditEvent.
- Station, Depot, Route, ServiceTemplate, ServiceCalendar, ServiceException, TripInstance.
- Vehicle, VehicleType, VehicleAvailability, MaintenanceEvent; Driver, Qualification, DriverAvailability, Leave, DriverDuty, DutyRest.
- SchedulingPeriod, ScheduleRevision, Assignment, FrozenAssignment, SolverRun, SolverCandidate, VerificationReport, Publication, ApprovalRequest.
- Disruption, RecoveryProposal, Notification, ImportBatch, ImportIssue, ExternalIdentifier, OutboxEvent.
- Store operational instants in UTC with associated IANA timezone and original service-local date. Preserve absolute elapsed time across midnight and DST; *never* equate `local minute since midnight` with elapsed UTC minutes on 23/25-hour dates. Create service-day normalized CV inputs from validated instants with explicit day offsets. Test Europe/Athens spring and fall transitions.
- Separate physical vehicles and drivers in the canonical model. **CV v1 maps each pre-approved driver–vehicle pairing to a synthetic resource for a service day**. No claim of true independent driver/vehicle optimization, mid-duty vehicle swaps or relief-point planning in v1. Those require solver model evolution.
- Publish immutable revisions. Planned vs actual schedules are distinct. Reject stale revision writes with `409 Conflict`; approval policies and publication validation are versioned and auditable.

## CV Solver as primary production engine — versionable, not frozen

Source: `backend/framework/cv_solver.py`, `framework/problem.py`, `framework/solution.py`, `services/legality_checker.py`, `framework/greedy_sa_solver.py`. Preserve Valouxis's original source as a tagged immutable reference and record provenance/permission. CV is a matheuristic using a greedy constructive warm start, `k_opt` neighborhood search and OR-Tools CP-SAT subproblems. **The CV-specific greedy initializer is part of the production CV algorithm; standalone Greedy, Simulated Annealing and LAHC stay in a separate research/benchmark workspace.** Do not silently swap CV for a different algorithm.

Establish `CVLegacyV0` characterization baseline before refactoring. Expose a stable typed contract, such as:

```python
@dataclass(frozen=True)
class SolverConfig:
    seed: int
    time_limit_seconds: int
    cp_sat_workers: int = 1
    iterations: int = 5

class SchedulingSolver(Protocol):
    @property
    def algorithm_id(self) -> str: ...
    @property
    def version(self) -> str: ...
    def solve(self, problem: SolverProblem, config: SolverConfig, progress: ProgressSink) -> SolverResult: ...
```

`SolverProblem` is a *versioned immutable snapshot*, not a mutable DB model. `SolverResult` carries assignments, explicit unassigned trips, diagnostics, validated metrics and solver/build metadata. The contract remains stable even as internal candidate builders, neighborhood selection, cost function, feasibility probes and CP-SAT repair steps evolve. Use named registries for explicitly approved CV versions (e.g. `cv-legacy-v0`, `cv-bounded-v1`, experimental `cv-...`); only an administrator-controlled version is eligible for production runs. Version the schema, constraints/rules, solver code hash, instance, weights, seed, worker count and environment. Promotion requires verified improvement on a fixed benchmark ladder without publication regressions.

**Minimal safety patch of CV**, reviewed with Valouxis when required by licensing/collaboration terms: bounded loop accounting including `continue` branches; reject empty/degenerate inputs; seeded *local* RNG rather than module-global random; configure CP-SAT seed, time limit and workers; progress/log hooks and clean error returns. External process timeout remains mandatory. Do not promise bit-identical results across platform/library versions or different CP-SAT worker counts. For seed+build+environment consistency, test repeatability; when not reproducible, record variability.

**Independent verifier:** separate from `services/legality_checker.py`, derived from explicit versioned business/legal requirements. Check unique coverage, no duplicates, time/spatial continuity, mandatory connections/chains, vehicle/driver availability, qualification, rest across days, frozen assignments, tenant scope and publication requirements; return structured violations. The legacy checker is not authoritative because field-name and chain enforcement gaps were identified. Hard rules cannot be paid off via optimization weights. **Do not label existing 900/600/720/270/30 defaults legally compliant.** Confirm Greek/EU transport and labour rules and actual operator agreements with qualified specialists before any deployment represented as compliant.

**Weekly scheduling:** rolling-horizon orchestration over daily CV instances, passing day-boundary state and verifying full-horizon rest and resource availability. This is not identical to globally optimized weekly planning; state its limitations and keep infeasible drafts unpublishable. **Incremental recovery:** spike first; use validated frozen-prefix transforms to preserve operated and locked trips. A `previous_solution` alone is not a lock. Never publish automated operational changes by default; policy-eligible low-risk informational actions can run automatically, material assignment changes require human approval.

**Metrics:** compute all displayed quality metrics independently from returned assignments. Legacy zero-filled `fairness`, `totalOver8h`, `totalTransferTime` values must not be displayed as proven measurements. A legitimate run may have unassigned trips; mark coverage accurately, and block publication only when tenant-defined required coverage or operational exceptions are unmet.

## Interfaces and UI

Desktop-first dispatcher Scheduling Studio with virtualized timeline/Gantt and keyboard-operable manual edits, validations, schedule versions/diffs, candidates and approval. Validate library suitability with a standalone timeline spike before committing to `gantt-task-react` for large data. Additional role-tailored modules for fleet, workforce, administrators, management and mobile-first driver portal. **Greek and English localization from first shell task**, including message catalogs, pluralization, time/date/number formatting and Europe/Athens. Light/dark themes and accessibility foundation now; density presets after operational workflows are usable. Stream progress via SSE; maintain client event cursors, refresh via REST after disconnects and discard stale events.

## Security, operations and IP gates

Eliminate unauthenticated operational routes, open registration and `/sentry-debug` in deployed environments; remove raw traceback disclosure; restrict CORS; replace default secrets, hardcoded DB credentials, public database ports and development reload. Review `.env` provenance and history; rotate exposed secrets. Replace dated authentication libraries based on maintained compatibility review, upgrade to psycopg3 when tested; use Alembic rather than `create_all` during app startup. Add structured logs, audit, rollback, backups and tested restoration, capacity monitoring and incident procedures. Record permission from solver author and university/thesis ownership/co-authorship rights before commercial distribution. Document GDPR data handling, retention and processor responsibilities.

## Python support policy

**Pin current CV worker baseline at Python 3.13** until its characterization suite passes with actual OR-Tools binaries. Test Python 3.14 and 3.15 independently in CI as supported, and promote only after real-wheel compatibility, correctness and performance are validated. API and worker images may evolve separately. Use process-level parallelism; free-threading or JIT is not a precondition.

## Acceptance criteria and explicit risks

- Two tenants cannot read/write/subscribe to each other's records, including via worker identities; malicious cross-tenant foreign keys fail.
- CV completes within external deadline; pathological/no-resource input fails fast; force-kill leaves terminal consistent job state and zero published changes.
- Versioned verifier catches intentionally broken overlaps, chains, double assignment, DST errors and cross-day rest violations. Publication blocked on violations.
- Multiple CV configurations produce results with honest independently calculated metrics, and candidate metadata is reproducible/traceable.
- Published schedules are immutable; concurrent stale edit returns HTTP 409; approval and audit data persist.
- Imports are staged and previewed before commit; Greek and English UIs allow core workflows.
- Licensing/legal gates have recorded clearance for commercial pilot; performance measured on 100/400/1000/2500-trip synthetic ladders, not assumed.

## Delivery phases

0. CV characterization, external verifier rule requirements, author/university IP, Python+OR-Tools probe.
1. Security/tenancy/invitations/migrations and bilingual UI shell.
2. Canonical operational models, staging/imports, DST correctness and separate driver/vehicle domain.
3. PostgreSQL jobs, bounded CV adapter and subprocess, SSE progress, verified candidate comparison.
4. Schedule revisions, timeline spike then scheduling workspace, approvals and publish.
5. Controlled disruption recovery, driver-facing workflows and notifications.
6. Pilot hardening, ops monitoring, disaster recovery, load tests and externally verified legal rule sets.

No production feature is implemented by this specification; each phase has independent acceptance gates and can be delivered separately.
