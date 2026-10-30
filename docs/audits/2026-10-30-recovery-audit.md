# Recovery audit — 2026-10-30

Read both v2 specification and implementation plan. Inspected current API, revision service, verifier, job repository/supervisor, outbox, UI loading/editor and authentication.

Verified source findings before recovery:
- No scheduling REST router registered. Inspector changes, approvals and publication are local state. Publication fallback falsely reports success.
- Revision service checks versions without an atomic write lock. Publication accepts absent problem as pre-verified; does not enforce approved state. Edit does not invalidate approval.
- Independent verifier checks duplicates/overlap/chains/coverage but does not check resource existence or bus-type eligibility. UI always claims eligibility and driving-law compliance.
- UI loads shared DAT fixture through `/trips` and `/drivers`, not canonical tenant-owned PostgreSQL operational records; generates registration plates and vehicle specifications.
- UI load effect depends on unstable apiFetch; each render recreates it. Solver invocation is synchronous legacy CustomSolver, despite CV-Bounded label.
- Optimization endpoints enqueue jobs, but no consumer bridges queue to solver. Supervisor caps output only after communicate has buffered it (not a bounded-memory guarantee).
- SSE hook uses native EventSource without bearer auth, wrong proxy paths, no job filter and no durable reconnect loop. Outbox is not connected to job transitions.
- User model has is_admin, no persisted roles. Registration passes nonexistent role field. Invitation uses static config codes, not tenant-bound invitation entities.
- Tenant module applies optional ORM filters to five old tables; schema audit only checks tenant column presence. No migrations/RLS policies or composite tenant foreign keys found. Tests named RLS do not prove PostgreSQL RLS.
- Status document's all-phase completion claim is unsupported. Imports/reports/date controls/driver views need acceptance tests; operations contains fixtures.
- No frontend tests or browser configuration. Claimed running localhost UI was unreachable on first probe; requires runtime verification.

Preserve existing solver source. Commercial IP and external legal clearance remain unverified. Security/runtime findings outside this slice remain open; this work is not a production certification.

Recovery evidence: original suite 77 passed; post-recovery suite 88 passed. Live PostgreSQL concurrent writes returned 200/409 with one version increment. Five browser workflows passed, including reload persistence, verified overlap, real asynchronous CV and authenticated SSE, session isolation and responsive themes. See IMPLEMENTATION_STATUS.md for final build results and remaining gates. Earlier source findings above describe the pre-recovery state; fixed items are enumerated in that status document.
