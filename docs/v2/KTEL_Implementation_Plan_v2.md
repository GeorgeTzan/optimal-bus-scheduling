# KTEL Operations Platform — Revised Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an internally focused, secure KTEL SaaS using Christos Valouxis's maintainable, versioned CV solver as the only production scheduling algorithm, while preserving separate research benchmarking.

**Architecture:** FastAPI modular monolith, PostgreSQL with RLS, isolated CV worker processes claimed from a database queue, REST for state-changing operations and SSE for persisted state-change notifications. Next.js bilingual role-specific UI; immutable schedule revisions and independent prepublication verifier.

**Tech Stack:** Python 3.13 CV worker baseline, FastAPI, SQLAlchemy, psycopg3 after compatibility tests, Alembic, PostgreSQL 16, OR-Tools, pytest, Next.js/React/TypeScript/Tailwind, Playwright. Defer Redis/Celery/WebSockets until demonstrated need.

**Spec:** `docs/superpowers/specs/2026-10-30-ktel-operations-platform-design.md`

## Global Constraints

- Christos Valouxis CV Solver is the sole production scheduling engine; its greedy warm-start initializer is **part of CV**. Other standalone solvers may run only in research/benchmark contexts.
- Preserve original CV source/provenance as `cv-legacy-v0`; improvements live in versioned implementations and are promoted only after independent verifier and regression/benchmark gates.
- Hard constraints always outrank objective weights; never claim compliance without an externally verified, versioned legal ruleset.
- PostgreSQL is authoritative for schedules, jobs, audit, events; SSE clients resynchronize with REST after loss.
- Source authorization/tenancy enforced in API and workers; no public access to production data or unsafe debug endpoints.
- Separate driver/vehicle domain; CV v1 uses fixed synthetic driver-bus pairings, not true independent scheduling.
- Canonical datetimes use UTC instants + IANA timezone, with service-day conversion and DST tests.
- All significant code changes use TDD (failing test → minimal implementation → passing test → commit) and independent review.
- UI supports Greek + English from the start, accessible responsive views and light/dark themes.
- Keep code changes out of this planning phase. Clear solver author and university IP before commercial distribution.

## Review Focus — regression hazards

1. Empty trips/resources or impossible resource pairing must fail fast, not livelock a worker (Task 2).
2. Overlapping, duplicate or broken mandatory-chain assignments must fail independently of legacy checker (Task 1).
3. Spring/fall DST transitions and overnight services must map to correct elapsed minutes (Task 7).
4. Tenant-scope omission in an API, worker or SSE stream must be rejected (Tasks 5, 9).
5. Force-killed solver and reconnecting browser must converge on durable, non-published job state (Tasks 8, 9).

## Confirmed repository anchors and intended layout

**Existing source:** `backend/framework/cv_solver.py`, `framework/problem.py`, `framework/solution.py`, `framework/greedy_sa_solver.py`, `backend/services/legality_checker.py`, `backend/api/solver.py`, `backend/main.py`, `backend/db/models.py`, `frontend/src/app/page.tsx`, `frontend/src/app/api/solve/route.ts`, `docker-compose.yml`.

**Proposed new backend boundaries:**

- `backend/app/domain/optimization/contracts.py`: `SolverConfig`, `SolverProblem`, `SolverResult`, `ProgressSink`, `SchedulingSolver` typed contracts.
- `backend/app/domain/optimization/cv_legacy.py`: compatibility wrapper referencing preserved original algorithm.
- `backend/app/domain/optimization/cv_bounded.py`: reviewed, controlled improvements to CV.
- `backend/app/domain/optimization/registry.py`: named solver versions and promotion allowlist.
- `backend/app/domain/optimization/adapter.py`: date-normalized, pairing-based input construction.
- `backend/app/domain/verification/{rules.py,verifier.py}`: independent versioned hard-rule verification.
- `backend/app/domain/jobs/{models.py,repository.py,supervisor.py}`: durable state, lease claims, hard-kill process supervision.
- `backend/app/domain/{identity,workforce,fleet,timetables,scheduling,imports,incidents}/`: small cohesive modules, each with API, service and persistence when needed.
- `backend/app/api/events.py`: tenant-authorized resumable SSE.
- `backend/tests/{optimization,verification,security,domain,jobs,api}/`: feature-specific tests.
- `frontend/src/{app,features,components,i18n}/`: bilingual role-tailored screens, timeline spike and shared system.

Do not copy/reorganize the entire existing app in one commit; migrate module-by-module with compatibility tests.

## Task template for each task below

Perform **five individually checkable steps**: (1) write the specific failing test(s) named under *Tests*, (2) run the named test path and confirm failure for intended reason, (3) implement the exact *Interfaces* in the stated files, (4) rerun focused and relevant suite until green, (5) commit only this scope. Never infer that tests passed from a plan; record actual command/output in the PR. Where a compatibility binary is unavailable, mark tests BLOCKED rather than faking a pass.

## Phase 0 — CV safety and feasibility foundations

### Task 1: Independent verifier MVP

**Files:** Create `backend/app/domain/verification/rules.py`, `verifier.py`, `backend/tests/verification/test_verifier.py`.

**Interfaces:** `verify_schedule(problem: SolverProblem, assignments: list[Assignment], rules: RuleSet) -> VerificationReport`; `VerificationReport` has `valid: bool`, `violations: list[Violation]`, rule version. Start with explicit trip uniqueness, overlaps, station continuity, mandatory chains and required coverage policy; add rules only when specified and tested.

**Tests:** `test_rejects_duplicate_trip`, `test_rejects_overlapping_trips`, `test_rejects_broken_chain`, `test_reports_unassigned_without_falsely_claiming_valid_full_coverage`.

- [ ] Failing tests `cd backend && uv run pytest tests/verification/test_verifier.py -q`.
- [ ] Implement rules without importing `services/legality_checker.py`.
- [ ] Run focused suite, demonstrate deliberate invalid fixtures fail validation; commit.

### Task 2: Characterize legacy CV and safeguard degenerate inputs

**Files:** Existing `backend/framework/cv_solver.py`, `framework/greedy_sa_solver.py`; create `backend/tests/optimization/test_cv_characterization.py`, `test_cv_safety.py`, `backend/app/domain/optimization/cv_legacy.py`.

**Interfaces:** `CVLegacyV0.solve_legacy(problem, iterations, previous_solution)` as compatibility boundary; `validate_cv_input(problem: SolverProblem) -> None` raises typed `InvalidSolverInput` for empty resources/incompatible pairing. Preserve original tagged source before changing algorithm.

**Tests:** `test_empty_resources_rejected_preflight`, `test_zero_or_duplicate_trip_ids_rejected`, `test_cv_warm_start_calls_constructive_heuristic`, `test_result_partitions_assigned_unassigned`, `test_legacy_cv_properties_on_fixture`. Existing CV cannot be characterized completely without actual OR-Tools: create a compatibility environment and mark blocked tests explicitly.

- [ ] Write failing property tests and run `cd backend && uv run pytest tests/optimization -q`.
- [ ] Implement input preflight and a compatibility wrapper, not a speculative solver rewrite.
- [ ] Test with real OR-Tools; collect fixture metrics, ranges and failure modes; commit.

### Task 3: Agreed CV safety patch and versioned solver contracts

**Files:** Create `backend/app/domain/optimization/{contracts.py,cv_bounded.py,registry.py}` and `backend/tests/optimization/test_cv_bounded.py`; modify legacy `cv_solver.py` only via reviewed/recorded patch or snapshot copy.

**Interfaces:** `SolverConfig(seed:int,time_limit_seconds:int,cp_sat_workers:int=1,iterations:int=5)`; `SchedulingSolver.solve(problem,config,progress)->SolverResult`; `registry.get_production_solver(version:str)->SchedulingSolver` rejects research solvers. `cv-bounded-v1` is promoted only after comparison.

**Tests:** `test_iteration_limit_even_on_continue`, `test_repeated_seed_and_env_is_reproducible_or_variance_recorded`, `test_cp_sat_parameters_applied`, `test_production_registry_rejects_research`, `test_metrics_not_faked_as_zero`. Request agreement from CV author for alteration and confirm licensing.

- [ ] Write failing configuration, timeout-bound and registry tests and run `cd backend && uv run pytest tests/optimization/test_cv_bounded.py -q`.
- [ ] Implement local PRNG, bounded iteration accounting, configured CP-SAT options, structured progress and stable contracts; avoid broad algorithm changes.
- [ ] Verify against fixture, golden *properties* and verifier; commit.

**Phase gate:** CV can run safely on supported interpreter and real OR-Tools; baseline/modified results characterized; verifier detects known-bad solutions. Record solver and university ownership status separately.

## Phase 1 — Secure runtime, tenancy, bilingual shell

### Task 4: Secure runtime and auth migrations

**Files:** Modify `backend/main.py`, `backend/config.py`, `backend/api/auth.py`, `docker-compose.yml`; create `backend/alembic/versions/...`, `backend/tests/security/test_auth_runtime.py`.

**Interfaces:** invitation-based registration; protected operational routes; production settings validation; migration runner. Remove publicly reachable `/sentry-debug`, full tracebacks, wildcard CORS+credentials and default secrets; no `create_all` on API startup; no public DB port in production.

**Tests:** `test_unauthenticated_solve_trips_drivers_data_rejected`, `test_registration_requires_invitation`, `test_no_debug_route_in_production`, `test_missing_secret_fails_startup`, `test_no_raw_traceback`.

- [ ] Write tests and verify fail `cd backend && uv run pytest tests/security/test_auth_runtime.py -q`.
- [ ] Implement secure settings, invitation policy, migrations and maintained auth library after compatibility assessment; inspect and rotate exposed `.env` secrets/history.
- [ ] Verify tests and migration upgrade/downgrade on disposable DB; commit.

### Task 5: Tenant isolation through RLS and composite keys

**Files:** Extend `backend/db/models.py` via Alembic; create `backend/app/domain/identity/tenant_session.py`, `backend/tests/security/test_tenant_rls.py`, `test_worker_scope.py`.

**Interfaces:** `tenant_transaction(session, tenant_id)` sets transaction-local tenant; app and worker non-owner roles; composite `(tenant_id,id)` FK. Apply RLS on tenant-owned tables, CI schema inspection for missing RLS policies.

**Tests:** `test_cross_tenant_query_empty`, `test_cross_tenant_update_denied`, `test_invalid_cross_tenant_fk_fails`, `test_worker_cannot_escape_tenant`, `test_schema_has_rls_for_each_tenant_table`.

- [ ] Write failing integration tests, run against ephemeral PostgreSQL with non-owner roles.
- [ ] Add migrations, session/worker tenant context and policies; ensure fail-closed connection handling.
- [ ] Run integration and schema audit tests; commit.

### Task 6: Shared bilingual UI shell

**Files:** Create `frontend/src/i18n/{el,en}.json`, `frontend/src/components/layout/*`, `frontend/src/features/auth/*`; reduce reliance on `frontend/src/app/page.tsx` monolith.

**Interfaces:** locale-aware shell (Greek default selectable / English), role navigation, accessible light/dark themes, empty/error/loading states, authenticated fetch client.

**Tests:** `frontend/tests/i18n.spec.ts`, `frontend/tests/layout.spec.ts` with Greek labels, locale date format, keyboard navigation and theme persistence.

- [ ] Write failing UI tests, run `cd frontend && npx playwright test tests/i18n.spec.ts tests/layout.spec.ts` (install/configure Playwright as part of task).
- [ ] Implement shell and message catalogs; do not build scheduling UI yet.
- [ ] Run targeted UI checks, typecheck and build; commit.

**Phase gate:** secure invitation-only, isolated tenants, safe API baseline and bilingual accessible navigation.

## Phase 2 — Canonical operational data and imports

### Task 7: Core resource and time model

**Files:** Create `backend/app/domain/{workforce,fleet,timetables}/` with `models.py`, `schemas.py`, `service.py`; migrations; `backend/tests/domain/test_service_time.py`, `test_resources.py`.

**Interfaces:** create/list/update tenant-scoped drivers, vehicles, availability, stations, templates, dated trip instances; `normalize_service_trip(local_start,local_end,iana_timezone)->TripInstant` and `make_cv_day_offsets(trips,service_date)->...` using elapsed UTC instants.

**Tests:** `test_spring_forward_athens`, `test_fall_back_ambiguous_time_requires_disambiguation`, `test_overnight_service`, `test_driver_vehicle_records_independent`, `test_cross_day_rest_input`.

- [ ] Write failing domain and time tests, run `cd backend && uv run pytest tests/domain -q`.
- [ ] Implement focused entities and services with migrations and explicit date normalization.
- [ ] Verify DB round-trip, time-boundary tests and tenancy; commit.

### Task 8: Staged imports and CV input adapter

**Files:** Create `backend/app/domain/imports/{staging.py,validation.py,service.py}`, `backend/app/domain/optimization/adapter.py`, `backend/tests/domain/test_imports.py`, `backend/tests/optimization/test_cv_adapter.py`.

**Interfaces:** `stage_import(tenant_id,file,format)->ImportBatch`; `preview_import(batch_id)->ImportPreview`; `commit_import(batch_id,expected_version)->ImportResult`; `to_cv_problem(snapshot:OperationalSnapshot,service_day:date)->SolverProblem`. Supports Excel/CSV and legacy `.DAT` with explicit parser validation; immutable snapshots and controlled synthetic driver-bus pairs.

**Tests:** `test_rejects_duplicate_source_ids`, `test_import_preview_does_not_write_live_data`, `test_import_rolls_back_on_invalid_rows`, `test_fixed_pairings_no_mid_duty_swap`, `test_round_trip_fixture`, `test_cross_tenant_import_denied`.

- [ ] Write failing import/adapter tests and run relevant pytest files.
- [ ] Implement staging/mapping and adapter on Task 7 canonical data model.
- [ ] Verify full round-trip fixture, review invalid-row report and commit.

**Phase gate:** KTEL-shaped imported or manually entered data can round-trip, validate and produce a deterministic CV input snapshot.

## Phase 3 — Durable jobs, CV integration and streaming

### Task 9: Job repository and external process supervisor

**Files:** Create `backend/app/domain/jobs/{models.py,repository.py,supervisor.py}`, migration, `backend/tests/jobs/test_claiming.py`, `test_supervisor.py`.

**Interfaces:** `enqueue_cv_job(tenant_id,snapshot_id,solver_version,config,idempotency_key)->JobId`, `claim_next_job(worker_id)->Job|None`, `cancel_job(job_id,actor)->Job`, `run_job_subprocess(job_id,deadline_seconds)->JobOutcome`. Postgres lease claim, heartbeat, retries, consistent terminal states, capped stdout and hard-kill worker process.

**Tests:** `test_duplicate_key_one_job`, `test_concurrent_claim_once`, `test_crash_recovers_lease`, `test_deadline_kills_child`, `test_cancel_does_not_publish`, `test_tenant_scoped_worker_claim`.

- [ ] Write failing job tests and run `cd backend && uv run pytest tests/jobs -q`.
- [ ] Implement durable claims and independent subprocess lifecycle; no Celery required.
- [ ] Verify crash/kill/retry state and commit.

### Task 10: CV result verification and candidate APIs

**Files:** Create `backend/app/domain/optimization/service.py`, `backend/app/domain/optimization/metrics.py`, `backend/app/api/optimization.py`, `backend/tests/api/test_cv_runs.py`.

**Interfaces:** `POST /optimization/runs` (202 + ID), `GET /optimization/runs/{id}`, `GET /optimization/runs/{id}/candidates`; `calculate_metrics(problem,result)->CandidateMetrics`; `verify_candidate(candidate,rules)->VerificationReport` prior to any publication. Store seed, snapshot hash, solver version and actual runtime.

**Tests:** `test_cv_default_production`, `test_other_solver_not_callable_from_production_route`, `test_unknown_metrics_not_reported_as_zero`, `test_invalid_candidate_not_publishable`, `test_unassigned_trip_visible`, `test_tenant_cannot_read_other_candidate`.

- [ ] Write failing API and metrics tests, run `cd backend && uv run pytest tests/api/test_cv_runs.py -q`.
- [ ] Implement CV-only orchestration APIs and independent metrics/verifier integration.
- [ ] Run API + worker integration tests; commit.

### Task 11: Durable outbox and SSE notifications

**Files:** Create `backend/app/api/events.py`, `backend/app/domain/events/outbox.py`, `backend/tests/api/test_events.py`, `frontend/src/features/optimization/use-job-events.ts`.

**Interfaces:** `GET /events?cursor=...` authenticated tenant-scoped SSE; monotonic event ID, controlled backfill, heartbeat, bounded payloads; `useJobEvents(jobId)` re-fetches REST on reconnect/event gap.

**Tests:** `test_event_no_tenant_leak`, `test_replay_after_disconnect`, `test_event_gap_refetch`, `test_job_remains_running_without_browser`, `test_event_payload_no_sensitive_internal_log`.

- [ ] Write failing event/stream tests, run `cd backend && uv run pytest tests/api/test_events.py -q`.
- [ ] Implement transactional outbox and SSE gateway with browser reconnect logic.
- [ ] Verify multi-client reconnect and duplicate tolerance; commit.

**Phase gate:** real CV runs are bounded, isolated, persisted and comparable; browser observes progress without holding the HTTP request open.

## Phase 4 — Revisioned planning and Gantt

### Task 12: Schedule revisions, concurrency and publication

**Files:** Create `backend/app/domain/scheduling/{models.py,service.py,publication.py}`, migration, `backend/tests/domain/test_schedule_revision.py`.

**Interfaces:** `create_revision(period_id,parent_revision_id)->Revision`; `apply_assignment_patch(revision_id,patch,expected_version)->Revision`; `request_publication(revision_id)->ApprovalRequest`; `publish_verified_revision(revision_id,actor)->Publication` requires independent verifier and approvals.

**Tests:** `test_stale_version_is_409`, `test_published_revision_immutable`, `test_failed_verification_blocks_publish`, `test_approval_audited`, `test_locked_assignment_not_modified`.

- [ ] Write failing revision tests and run focused pytest.
- [ ] Implement concurrency/version model and publication workflow.
- [ ] Verify immutable/revision and audit invariants; commit.

### Task 13: Virtualized timeline viability spike

**Files:** Create `frontend/src/features/scheduling/timeline-spike/*`, `frontend/tests/timeline-performance.spec.ts`.

**Interfaces:** exploratory UI with 400/1000/2500 trip fixtures, keyboard selection and drag intention; instrument frame rate, navigation performance and visible row rendering. Spike is disposable; document decision custom virtualized DOM/canvas vs existing library.

**Tests:** scroll responsiveness, assignment hit-testing, basic screen-reader alternatives and reduced-motion support. **Spike cannot be called production implementation**.

- [ ] Create measurement tests and acceptance thresholds before experimentation.
- [ ] Build disposable alternatives and record measurements on declared hardware.
- [ ] Choose rendering strategy and commit documented decision; remove unusable spike code.

### Task 14: Production Scheduling Studio

**Files:** Create `frontend/src/features/scheduling/{timeline,inspector,filters,revision-actions}/*`, `frontend/tests/scheduling.spec.ts`.

**Interfaces:** daily/weekly windows, selection, role-aware edit, validation panel, candidate compare, revision diff, approval status; REST mutation with `If-Match`/revision token and SSE refresh hints.

**Tests:** `test_reject_conflicting_edit`, `test_explain_violation`, `test_switch_el_en`, `test_keyboard_assignment_edit`, `test_approvals_only_for_authorized_role`.

- [ ] Write failing end-to-end workflows and run Playwright.
- [ ] Implement selected virtualized timeline and focused inspector/editor.
- [ ] Validate accessibility and responsive behavior; commit.

**Phase gate:** dispatcher can generate CV candidates, edit draft, see violations, approve and publish immutable revision.

## Phase 5 — Recovery and staff experience

### Task 15: Frozen-prefix recovery feasibility spike

**Files:** Create `backend/app/domain/incidents/recovery_spike.py`, `backend/tests/optimization/test_frozen_prefix.py`.

**Interfaces:** `split_operated_future(schedule,as_of)->(frozen,remainder)`; `build_recovery_input(...)` must prove pre-existing operated trips remain unchanged and locked tasks are hard-preserved. Avoid claiming CV supports independent driver/vehicle repair until measured.

**Tests:** mid-duty breakdown preserves past, locked assignment cannot move, unavailable replacement returns infeasible proposal, weekly rest verification across day boundary.

- [ ] Write failing spike tests and deliberately impossible scenarios.
- [ ] Test CV adaptation and identify unsupported cases; no auto-publish.
- [ ] Record findings and gate feasibility; commit design decision only if model extension required.

### Task 16: Incidents, approval-controlled recovery and driver portal

**Files:** Create `backend/app/domain/incidents/{models.py,service.py}`; `frontend/src/features/incidents/*`, `frontend/src/features/driver/*`; `frontend/tests/incident-flow.spec.ts`.

**Interfaces:** `report_incident`, `propose_recovery`, `approve_recovery`, `notify_affected_users`; driver sees assigned schedule and acknowledgment; low-risk notification automation only, assignment changes require dispatcher approval.

**Tests:** auditability, no notification before authorized publish, unavailable vehicle, driver role cannot publish, own-duty-only visibility.

- [ ] Write failing workflow tests.
- [ ] Implement incident handling, controlled recovery and minimal driver portal.
- [ ] Run API and UI acceptance scenarios; commit.

## Phase 6 — Pilot readiness

### Task 17: Performance, security, compliance and operations

**Files:** `backend/tests/performance/*`, `backend/tests/security/*`, `docs/operations/*`, CI workflows, production Compose and monitoring configs.

**Interfaces:** benchmark ladder of synthetic 100/400/1000/2500-trip input; solver time/cost/coverage and CPU/memory; retention/redaction audit, reproducibility report, backup/restore drill, force-kill and rollback runbook. Real-world regulatory rule validation and IP clearance documented as external signoffs.

**Tests:** restore from backup into isolated environment; load-test tenant isolation and SSE connections; verify process memory/time ceilings; RLS schema audit; deployment rollback; no unsafe debug endpoints.

- [ ] Define objective pilot SLOs and write automated deployment/ops checks that fail against unsafe baseline.
- [ ] Implement observability/security/restore/load necessities; only introduce Redis, WebSockets or extra infrastructure on evidence.
- [ ] Run reproducible pilot gate, record evidence and operator/legal/IP signoff; commit.

## Final self-review / coverage map

- Solver safety, greedy dependency, reproducibility and extensibility: Tasks 1–3, 9–10, 15.
- Security, invitation, tenancy/RLS, protected events: Tasks 4–5, 9, 11, 17.
- Canonical data, DST, separate drivers/vehicles and imports: Tasks 7–8.
- Greek/English UX, responsive theme, virtualized timeline: Tasks 6, 13–14.
- Publication, approval, recovery and driver operations: Tasks 12, 15–16.
- Deployment, licensing, legal review, backups and scaled benchmarks: Phases 0 and 6.
- No dependency inversion: CV adapter follows canonical resource model; jobs follow adapter, revision UI follows persisted schedules.
- Missing until requirements validated: exact legal formulas for every operator and any solver-owner-approved algorithmic redesign; explicitly block legal certification/production auto-publication, not foundation development.

## Handoff

Review this revision and resolve rights/legal requirements with appropriate parties. Once approved, implement task-by-task with Superpowers TDD and reviews. No changes to production source have been made by creating these planning artifacts.
