# Office Availability, Leave and Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans in the main implementation thread, task by task, with failure-first tests. The execution method is already chosen; do not re-select it. Steps use checkbox (`- [ ]`) syntax. **No commits or pushes** until the user directs git finalization, so tasks have no commit step.

**Goal:** Office staff record driver working time, leave and vehicle maintenance; those facts constrain CV optimization and independent verification; affected schedules are repaired through the existing reviewed-change workflow.

**Architecture:** Extend the existing availability tables and identity records with tenant-bound, versioned, audited office records. Freeze usable windows into new `ktel-operational-v2` snapshots; the verifier recomputes from frozen windows, and `BoundedCustomSolver` overrides `is_valid` without touching `framework/` or `services/`. A separate `availability_review_required` gate guards unpublished revisions; the published base is exempt so recovery is never blocked by the absence it repairs.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, OR-Tools CP-SAT (existing), Next.js, React, TypeScript, pytest, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-01-office-availability-maintenance-design.md` (approved), `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md` (OFFICE, FLEET, SEC, UX). Recovery follows `docs/superpowers/specs/2026-11-01-urgent-schedule-changes-design.md`.

## Global Constraints

- Prerequisite: urgent-change plan (`2026-11-01-urgent-schedule-changes.md`) accepted. Do not touch its in-progress work before that.
- Preserve `feat/v2-ktel-platform` and the whole dirty tree. Never commit, push, reset or clean.
- Intervals are half-open UTC `[start, end)`; adjacent endpoints do not overlap. A missing record means unknown, never available.
- Open end only on `unavailable` driver rows and `out_of_service` vehicle rows. An estimated end never releases a hold.
- Working-pattern validity: `valid_until` required, at most 366 days after `valid_from`. Batches: at most 100 items, atomic. Impact queries: date range at most 31 days. State these bounds in the UI; they are input limits, not capacity claims.
- Every write: server-derived tenant and actor, `request_id` (exact retry returns original; changed payload returns 409), `expected_version` on existing records, append-only audit in the same transaction.
- API and worker roles stay non-owner, non-BYPASSRLS. Composite tenant FKs, RLS and FORCE RLS on every new table. No runtime schema creation.
- Services flush; the transactional API owns commit and rollback. Lock order: organization row, then own rows. Office writes never lock a revision.
- Private notes and leave category never appear in impacts, events, logs, audit details or outbox hints.
- No diagnosis field. No roadworthiness, delivery or legal-compliance claims. Existing schedule approval and publication rules unchanged.
- Greek/English, light/dark, keyboard/touch, 390px actions, existing unsaved-change guard. Run CPU-heavy build/browser work apart from timed backend runs. Interrupted or failed runs are not green.

## Review Focus

1. Weekly pattern across an Athens DST gap or fold: finding `working_window_needs_resolution`, never a silently chosen occurrence (Task 2).
2. Overnight pattern from the previous date covers an after-midnight trip; absence ending exactly at a trip start allows it (Tasks 2, 6).
3. Releasing one hold leaves an overlapping second hold blocking (Task 4).
4. Retry of a decision with changed payload returns 409; simultaneous approve and reject leave one outcome and one linked blocker (Task 3).
5. Approved leave on an already published day: successor for that same day is creatable and publishable; forged exemption has no input path (Task 7).

## File Map

- Create `backend/app/domain/office/`: `models.py`, `schemas.py`, `permissions.py`, `intervals.py`, `patterns.py`, `availability.py`, `leave.py`, `maintenance.py`, `impacts.py`, `audit.py`.
- Create `backend/app/api/office.py`; register in `backend/main.py`; models in `backend/db/metadata.py`.
- Modify `backend/app/domain/{workforce,fleet}/models.py` and their `service.py` (remove delete-orphan cascade; replace `add_availability`).
- Create `backend/app/domain/optimization/availability.py`; modify `contracts.py`, `adapter.py`, `cv_legacy.py`, `cv_bounded.py`.
- Modify `backend/app/domain/verification/{rules,verifier}.py`, `scheduling/{snapshots,source_review,changes,change_schemas,service}.py`, `timetables/operations.py`, `api/scheduling.py`.
- Create `backend/app/domain/scheduling/availability_review.py`.
- Migrations: `backend/alembic/versions/NNNN_office_records.py`, `NNNN_office_periods.py`. `NNNN` is the number after the actual head at Task 0 (currently `0012_schedule_cancellation`); revision ID equals the file stem.
- Modify `backend/db/tenant_schema.py`: `domain_office_audit` SELECT/INSERT only.
- Frontend: `frontend/src/features/office/{OfficeWorkspace,WorkingPatternForm,LeaveRequestForm,LeaveDecisionDialog,MaintenanceForm,ImpactReview}.tsx`, `contracts.ts`, `office-api.ts`; entry links in Drivers, Fleet, Service day, Operations. Tests in `frontend/tests/office-*.spec.ts`.

## Task 0: Freeze baseline

**Files:** this plan, `docs/IMPLEMENTATION_STATUS.md`.

- [ ] Confirm urgent-change acceptance is recorded in its progress ledger. If not, stop and queue this plan.
- [ ] Record branch, dirty-tree scope, migration head, latest completed backend and browser exit statuses.
- [ ] On the local database, count rows in `domain_driver_availabilities` and `domain_vehicle_availabilities` (read-only). If either is nonzero, stop and report to the user (spec: preflight aborts on rows).
- [ ] Read the final urgent-change `change_schemas.py`, `changes.py`, `/api/v1/schedule-changes` contracts and note any drift from this plan.

**Done:** baseline and migration number recorded in the ledger.

## Task 1: Per-member grants, approval routes, audit

**Files:** `office/{models,schemas,permissions,audit}.py`; migration `NNNN_office_records`; `api/office.py` (settings routes); `db/{metadata,tenant_schema}.py`; test `backend/tests/integration/test_office_permissions.py`.

**Interfaces:**
- Produces: `require_office_permission(db, user, capability: str, driver_id: int | None = None) -> None` (403 `office_permission_required`); `resolve_approver_routes(db, tenant_id: int, driver_id: int) -> list[ApprovalRoute]` (driver-specific active routes, else organization default, else `[]`); `record_office_action(db, tenant_id, actor_id, request_id: str, entity: str, action: str, payload: dict, response: dict | None) -> OfficeAudit | previous`; `GET/PUT /api/v1/office/grants`, `GET/POST/PATCH /api/v1/office/approval-routes`.
- Tables: `domain_office_grants(membership_id, capability, is_active, granted_by, granted_at, version)` unique on membership and capability; `domain_leave_approval_routes(driver_id null, membership_id | external_contact_name exactly one, is_active, version)`; `domain_office_audit(entity, action, actor_id, request_id unique, payload_hash, response_data, created_at)`.

- [ ] Write failing tests: `test_grants_default_off_for_existing_accounts` (after migration no membership has any grant), `test_only_members_manage_can_grant`, `test_grant_revocation_applies_next_request`, `test_admin_has_no_implicit_grant`, `test_capability_outside_allowlist_rejected`, `test_foreign_tenant_membership_or_driver_rejected` (physical FK, raw SQL), `test_route_requires_exactly_one_approver_kind`, `test_missing_route_returns_empty_list`, `test_driver_route_overrides_default`, `test_audit_is_append_only_for_api_role`, `test_audit_retry_same_payload_returns_original_changed_payload_409`.
- [ ] Run `cd backend && uv run pytest tests/integration/test_office_permissions.py -q`; expect missing-module failures.
- [ ] Implement models, migration (seeds nothing; chain to the head from Task 0), permissions, audit; add `domain_office_audit` to the append-only overrides in `tenant_schema.py`; refresh runtime grants.
- [ ] Re-run the file plus identity, RLS and runtime-provisioning tests; expect pass. Assert worker role cannot read grants or routes.

**Done:** explicit, revocable authority; no silent promotion.

## Task 2: Intervals, working patterns, driver periods, availability source

**Files:** `office/{intervals,patterns,availability}.py`; migration `NNNN_office_periods` (driver half); `workforce/{models,service}.py`; routes in `api/office.py`; tests `backend/tests/domain/test_office_intervals.py`, `backend/tests/integration/test_office_availability.py`.

**Interfaces:**
- Produces: `normalize_office_interval(start_local: datetime, end_local: datetime | None, timezone: str, fold_start: int | None, fold_end: int | None) -> tuple[datetime, datetime | None]` (reuses `_resolve_wall_clock`/`normalize_service_trip` in `timetables/time_service.py`; no caller timezone override); `PatternService(db, tenant_id, actor_id).save / .save_batch / .retire`; `OfficeAvailabilityService(db, tenant_id, actor_id).save_period / .save_period_batch / .retire_period`; `availability_for_resources(db, tenant_id: int, identities: Sequence[tuple[int | None, int | None]], start_utc: datetime, end_utc: datetime) -> dict[tuple, ResourceAvailability]` where `ResourceAvailability` has `windows: tuple[tuple[datetime, datetime], ...] | None` (None = unknown), `blockers`, `warnings` (pending leave), `findings`, `fingerprint: str`. Routes: `working-patterns`, `driver-periods` (GET/POST/PATCH, `/batch`).
- Tables: `domain_driver_working_patterns` and altered `domain_driver_availabilities` per spec Data model; drop `service_date`, naive timestamps and delete-orphan cascade. Migration preflight aborts with counts if rows exist.

- [ ] Write failing tests: `test_adjacent_intervals_do_not_overlap`, `test_overlap_contained_partial`, `test_overnight_and_leap_day_and_year_rollover`, `test_open_end_only_for_unavailable`, `test_dst_gap_pattern_yields_finding` (Review Focus 1), `test_dst_fold_pattern_yields_finding`, `test_dated_window_replaces_pattern_for_that_date`, `test_overnight_pattern_from_previous_date_covers_after_midnight_trip` (Focus 2), `test_missing_basis_is_unknown_not_available`, `test_known_empty_when_blockers_cover_horizon`, `test_pending_leave_is_warning_only`, `test_pattern_validity_over_366_days_rejected`, `test_batch_over_100_rejected`, `test_batch_failure_rolls_back_all`, `test_stale_version_409_leaves_audit_unchanged`, `test_foreign_tenant_driver_rejected`, `test_availability_write_requires_grant`.
- [ ] Run both files; expect failures.
- [ ] Implement per signatures. `availability_for_resources` implements spec rules: base = dated windows else expanded patterns, usable = base − active unavailable rows, vehicle usable = horizon − active vehicle blockers (Task 4 supplies those), crew = driver ∩ vehicle.
- [ ] Re-run both files plus migration, RLS and composite-FK tests; expect pass.

**Done:** one interval source with explicit unknowns.

## Task 3: Leave lifecycle

**Files:** `office/leave.py`; leave routes in `api/office.py`; migration `NNNN_office_records` additions (`domain_leave_requests`); test `backend/tests/integration/test_office_leave.py`.

**Interfaces:**
- Produces: `LeaveService(db, tenant_id, actor_id)` with `.request(request) -> dict`; `.decide(leave_id: int, expected_version: int, decision: Literal['approved','rejected'], action_id: str, note: str | None, external_route_id: int | None = None) -> dict`; `.cancel(leave_id: int, expected_version: int, action_id: str, reason: str) -> dict`. Routes: `GET/POST /leave-requests`, `POST /{id}/decision`, `POST /{id}/cancel`. Responses carry `id, version, state, impact_count`; notes/category only with note access.
- Approval creates exactly one linked `unavailable` row (`source_leave_id`); cancel retires only that row.

- [ ] Write failing tests: `test_staff_enters_request_for_driver`, `test_no_route_keeps_pending_with_approver_missing`, `test_wrong_driver_route_member_refused`, `test_own_leave_refused_via_driver_link`, `test_admin_without_route_cannot_decide`, `test_external_decision_records_recorder_and_stated_maker`, `test_external_requires_availability_manage_and_external_route`, `test_recording_own_external_approval_refused`, `test_approve_creates_one_linked_blocker`, `test_approve_with_assigned_trips_succeeds_with_impacts`, `test_cancel_retires_only_linked_blocker_keeps_history`, `test_cancel_requires_decision_authority`, `test_linked_period_immutable_except_via_cancel`, `test_retry_changed_payload_409` and `test_concurrent_approve_reject_one_outcome` (Focus 4), `test_forced_failure_leaves_no_orphan_blocker`, `test_private_note_needs_notes_grant_or_route`, `test_reads_scoped_to_route_drivers`.
- [ ] Run file; expect failures.
- [ ] Implement transitions under organization-first lock; check route and grant while locked; version and idempotency via `record_office_action`.
- [ ] Re-run with simultaneous decision/cancel threads against PostgreSQL; expect pass.

**Done:** truthful approval workflow with consequences, no history rewrite.

## Task 4: Maintenance and holds

**Files:** `office/maintenance.py`; vehicle routes in `api/office.py`; `NNNN_office_periods` (vehicle half); `fleet/{models,service}.py`; test `backend/tests/integration/test_office_maintenance.py`.

**Interfaces:**
- Produces: `MaintenanceService(db, tenant_id, actor_id).save(request, record_id: int | None = None) -> dict`; `.release(record_id: int, expected_version: int, action_id: str, released_at_utc: datetime, note: str) -> dict`; `.cancel(record_id: int, expected_version: int, action_id: str, reason: str) -> dict`. Routes: `vehicle-periods` GET/POST/PATCH, `/{id}/release`, `/{id}/cancel`. Cancel authority per spec "Undoing a blocker".

- [ ] Write failing tests: `test_planned_requires_finite_end`, `test_out_of_service_without_estimate_stays_open`, `test_estimate_passing_does_not_release`, `test_release_requires_release_grant`, `test_release_before_start_or_in_future_rejected`, `test_release_one_hold_keeps_overlapping_hold_blocking` (Focus 3), `test_cancel_planned_needs_manage_cancel_hold_needs_release`, `test_cancel_is_not_release_and_keeps_reason`, `test_minor_report_not_a_hold`, `test_stale_version_409`, `test_foreign_and_archived_vehicle`, `test_archive_check_lists_active_office_periods`.
- [ ] Run file; expect failures.
- [ ] Implement; extend vehicle archive impact check so active periods are listed, not orphaned. Ensure `availability_for_resources` consumes vehicle blockers.
- [ ] Re-run with fleet/resource archive tests; expect pass.

**Done:** truthful fleet availability.

**Review gate A (after Task 4):** one fresh read-only reviewer on Tasks 1–4 code, migrations and tests (tenant isolation, authority, idempotency, intervals). Fix Critical/Important findings test-first; rerun affected gates.

## Task 5: Office screens (before enforcement)

**Files:** frontend files in File Map; entry links in Drivers, Fleet, Service day; tests `frontend/tests/office-availability.spec.ts`, `office-leave.spec.ts`, `office-maintenance.spec.ts`.

**Interfaces:**
- Produces typed `office-api.ts` functions through existing `apiFetch`: `saveWorkingPattern`, `saveWorkingPatternBatch`, `saveDriverPeriod`, `saveLeaveRequest`, `decideLeaveRequest`, `cancelLeaveRequest`, `saveVehiclePeriod`, `releaseVehiclePeriod`, `cancelVehiclePeriod`, `getGrants`, `saveRoutes`.

- [ ] Write failing browser journeys against a temporary organization: grant → save pattern → request leave → decide → record hold → release; reload after each. Assert pending, approved, planned, estimate and actual hold are distinct by text and icon, not colour.
- [ ] Implement required-first forms with named pickers, explicit local time and clock-change resolution; bulk pattern form shows exact proposed result and the 100-item bound before atomic save; timetable-derived suggestions are labelled and never saved on open; hide actions the user lacks, with a reason for blocked ones.
- [ ] Add regressions: unsaved close/history/date navigation, failed save keeps entries, stale 409 keeps selections, delayed reply after date/session change ignored, private note hidden, 390px approve/release actions reachable, route member with no driver link flagged.
- [ ] Run the three files, `npm run typecheck`, `npm run build`; inspect real Greek/English, light/dark, desktop and 390px captures.

**Done:** staff can enter all records before anything requires them.

## Task 6: Freeze, verify and solve with availability

**Files:** `optimization/{availability,contracts,adapter,cv_legacy,cv_bounded}.py`, `verification/{rules,verifier}.py`, `scheduling/snapshots.py`, `timetables/operations.py`; shared test helper `backend/tests/helpers/working_time.py`; tests `backend/tests/verification/test_office_availability.py`, `backend/tests/optimization/test_availability_solver.py`, `backend/tests/integration/test_office_schedule_snapshots.py`.

**Interfaces:**
- `ResourceSnapshot.available_windows: tuple[tuple[int, int], ...] | None = None` (elapsed minutes from frozen `service_day_start_utc`; `None` unknown, `()` none).
- `SolverProblem.availability_enforced: bool = False`, `availability_exempt_trip_ids: tuple[str, ...] = ()`. `decode_problem` tolerates missing keys and converts lists to tuples; old snapshots stay byte-identical.
- `availability_allows_trip(resource, trip) -> bool`; `availability_allows_transition(resource, previous_trip, next_trip, transfer_minutes: int) -> bool`; `sanitize_seed(problem, solution) -> Solution` in `optimization/availability.py`.
- `RuleSet.version = "v2.4-availability"`; rule ids `RULE_AVAILABILITY_TRIP`, `RULE_AVAILABILITY_TRANSITION`, `RULE_AVAILABILITY_UNKNOWN`.
- New snapshots: `source_schema_version = 'ktel-operational-v2'`, `source_data['availability']` = fingerprint and per-resource provenance (not in `source_versions`). `build_operational_snapshot` raises `working_windows_required` naming each unknown driver.

- [ ] Add `working_time.py` helper that grants and creates patterns for fixture drivers; update existing backend and browser fixtures that build operational snapshots to use it.
- [ ] Write failing tests: one pair, two trips, one trip inside approved leave → `test_cv_never_assigns_into_absence`; forged assignment → `test_verifier_rejects_forged_assignment`; `test_exact_boundary_end_equals_start_allowed`, `test_two_windows_each_usable`, `test_open_hold_clipped_not_guessed`, `test_transfer_must_fit_inside_window` (windows 08:00–12:00 and 14:00–18:00, trip ends 11:45, next starts 14:15, transfer 30 → rejected; within-window counterpart passes), `test_unknown_windows_error_when_enforced`, `test_exempt_trip_skips_rules`, `test_v1_snapshot_decodes_unchanged_bytes`, `test_missing_windows_in_v2_snapshot_fails_not_legacy`, `test_cv_legacy_refuses_enforced_problem`, `test_duplicate_bus_id_rejected_when_enforced`, `test_seed_violations_become_unassigned_and_shift_revalidated`, `test_known_empty_crew_is_warning_not_error`.
- [ ] Run the three files; expect failures.
- [ ] Implement. Verifier computes findings from frozen windows only. `BoundedCustomSolver` overrides `is_valid` to add the two helpers (windows passed via `problem_snapshot_to_legacy_dict` into the resource dict); apply `sanitize_seed` after `GreedySASolver.solve`. Do not edit `framework/` or `services/`.
- [ ] Re-run deterministic CV/reference, canonical, clock, verifier regressions and restricted-worker job test; expect pass.

**Done:** availability changes actual optimization and verification.

## Task 7: Stale checks, successor refresh, unlock, impacts

**Files:** `scheduling/availability_review.py`, `scheduling/{source_review,changes,change_schemas,service}.py`, `api/scheduling.py`, `office/impacts.py`; tests `backend/tests/integration/test_office_impacts.py`, `test_office_recovery.py`.

**Interfaces:**
- `availability_review_required(db, revision, snapshot) -> bool`: true for unpublished operational revisions whose frozen availability fingerprint differs from current, and for v1 drafts; false for published revisions.
- `source_review_required` accepts schema v1 and v2 and ignores availability.
- Call `availability_review_required` under the organization lock at apply, patch, approve and publish. Not called on the published base in `ScheduleChanges.validate`.
- `ScheduleChanges.validate/create`: refresh availability for all resources including new `CREW_*` crews by underlying driver and vehicle, enforce on, set `availability_exempt_trip_ids` from the server-computed `operated` set, write new `source_data['availability']`.
- Patch operation `unlock` in `change_schemas.py`: allowed only for a trip with an availability conflict in the refreshed check, requires reason, needs existing `schedule.write`, never on operated trips, audited.
- `list_office_impacts(db, tenant_id: int, *, date_from: date, date_to: date, page: int, page_size: int) -> dict` (range at most 31 days; derived only; GET writes nothing). `GET /api/v1/office/impacts` requires `schedule.read`.

- [ ] Write failing tests: `test_absence_after_confirmation_enqueue_candidate_preview_approval_each_409s_stale`, `test_publish_blocked_when_availability_changed`, `test_leave_on_published_day_successor_creatable_and_publishable` and `test_no_input_path_for_exemption` (Focus 5), `test_operated_trip_exempt_from_server_set_only`, `test_locked_trip_unlock_only_with_conflict`, `test_unlock_needs_reason_audit_and_not_for_operated`, `test_replace_driver_crew_uses_underlying_availability`, `test_no_replacement_reports_unresolved`, `test_v1_base_with_unknown_drivers_reports_working_windows_required`, `test_cancel_leave_rechecks_without_restoring_assignment`, `test_release_bus_rechecks_without_restoring`, `test_impacts_range_over_31_days_rejected`, `test_impacts_hide_notes_and_category`, `test_get_impacts_creates_no_rows`, `test_office_write_vs_publish_no_deadlock`.
- [ ] Run both files; expect failures.
- [ ] Implement per interfaces. Retire no stored impact state: derive from blockers ∩ active pairings, open drafts and latest publication per date. Hints in office mutations carry IDs only.
- [ ] Re-run office, successor/cancellation/lineage, underlying-overlap, Operations and tenant security tests; expect pass.

**Review gate B (after Task 7):** one fresh read-only reviewer on Tasks 5–7, including untracked files, the five Review Focus cases and spec section "Stale checks and recovery". Fix test-first; rerun affected gates.

**Done:** truthful consequences, recovery never blocked by its own cause.

## Task 8: Impact and recovery interface

**Files:** `ImpactReview.tsx`, Service day, Operations entry points; tests `frontend/tests/office-impacts.spec.ts`.

- [ ] Write failing browser journey: approve leave → "saved, N trips need review" from the API → impact list → existing change workflow → successor with unlock where needed → publish → reload; original publication remains visible until the successor is published.
- [ ] Implement read-only impact list with the recovery link to existing preview/create APIs (no parallel write path); Service day shows missing working time with one next action.
- [ ] Regressions: delayed replies, stale 409 keeps selections, mobile actions, no claim of replacement, delivery or certification.
- [ ] Run this file plus related Operations, urgent-change and planning cases, typecheck, build; inspect Greek/English, light/dark, desktop and 390px captures.

**Done:** full office journey without raw endpoints.

## Task 9: Acceptance and handoff

**Files:** `docs/IMPLEMENTATION_STATUS.md`, this plan's ledger `2026-11-01-office-availability-maintenance-progress.md`, `docs/operations/OFFICE_AVAILABILITY.md`, scope review matrix, screenshots.

- [ ] Complete tenant journey: grants → patterns → scheduled work → pending leave warning → approval → conflicts → reviewed replacement → successor → publish → reload. Separately: hold, release, no-replacement. Two tenants, reader/driver/dispatcher/fleet/approver accounts, own-approval, concurrent decisions, DST, overnight.
- [ ] Before any local schema upgrade: private 0600 backup, restore and upgrade on a disposable database, preflight, migrate, refresh grants, recheck RLS and composite FKs.
- [ ] Run full backend suite in a quiet process to completion, then typecheck, build and full browser suite. Record commands, exits and screenshots; keep failed attempts in history, not counted green.
- [ ] One final fresh read-only whole-tree review (tracked and untracked). Fix Critical/Important findings test-first, rerun gates.
- [ ] Update OFFICE, FLEET and related requirement dispositions. Do not mark portal, reports, legal compliance or deployment complete.

**Done:** reviewable office delivery with evidence; portal and reports remain follow-on plans.

## Self-review

- Spec coverage: grants/routes/audit → T1; patterns/periods/availability → T2; leave → T3; maintenance → T4; snapshots/verifier/solver/v2 → T6; stale gate, refresh, exemption, unlock, impacts → T7; UI → T5, T8; review gates and order → after T4, T7, T9; acceptance list → T9 and Review Focus.
- Known conflict with prior wording: scope doc OFFICE-05 says planning horizon explicit; covered by horizon rule in `availability_for_resources` (service-day start to latest trip end plus largest transfer).
- Types checked: `available_windows`, `availability_enforced`, `availability_exempt_trip_ids`, `availability_review_required`, `availability_for_resources` used identically in T2, T6, T7.
