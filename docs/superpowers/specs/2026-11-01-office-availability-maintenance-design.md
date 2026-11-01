# Office availability, leave and maintenance — design

Status: user approved on 2026-11-01 the unlock step, weekly patterns and per-member grants defaulting to off; whole document awaits final approval. Written after review of the plan `docs/superpowers/plans/2026-11-01-office-availability-maintenance.md` against the working tree. The user delegated the open technical and product calls ("you're the expert"). Each is marked **[Claude's call]** so it can be rejected. Requirements come from `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md`. The office-first direction was approved in a side conversation that left no written spec; this document replaces that gap.

## Why

KTEL office staff need one place to record who can work, approve leave and take buses out of service. Those facts must actually constrain the solver, verifier and publication, and they must lead to reviewed repair of affected schedules. Today `domain_driver_availabilities` and `domain_vehicle_availabilities` exist but nothing calls `add_availability`, and neither solver nor verifier reads them.

## Goals

- Record driver working time, absences, leave decisions, planned maintenance and out-of-service holds, with actor, time and history (OFFICE-01..07, FLEET-01..05).
- Confirmed absences and holds constrain CV and fail independent verification.
- A fact that changes after preparation blocks stale apply, approve and publish, without blocking the recovery that repairs it.
- Show affected pairings, drafts and published trips, and link to the existing schedule-change workflow.

## Non-goals

Driver portal, general reports, notifications, legal or rest-rule certification, roadworthiness claims, an owner login, automatic reassignment, automatic publication, a new approval layer for schedules, a workflow engine, new dependencies.

## Anti-goals

The delivery has failed, even if tests pass, when:

- Confirming working time is so repetitive that staff approve it unread.
- A recovery for an absence is refused because of that same absence.
- A missing record is read as "available".
- An external owner's decision looks like an authenticated in-app approval.
- Published history changes.

## Constraints

- Prerequisite: urgent-change Task 5 is in progress and Task 6 has not started. Implementation waits for acceptance of that plan, then reads the final contracts.
- All work stays uncommitted and unpushed until the user directs otherwise.
- API and worker roles stay non-owner and non-BYPASSRLS. No runtime schema creation.
- Services flush; the outer transactional API owns commit and rollback.
- Greek/English, light/dark, keyboard/touch and narrow-screen actions are required.

## Approaches: how the office states who can work

The biggest gap in the original plan. It offered only dated windows and a batch limit of 100, so a confirmation was needed for every driver and every day.

| Approach | Trade-off |
|---|---|
| A. Dated windows only (original plan) | Simplest model. Roughly drivers × days of entry; invites unread bulk approval. |
| **B. Weekly working pattern plus dated overrides (selected)** | One small extra table. Entry drops to a few patterns per season, and daily pairing confirmation remains the human check on the day. |
| C. Enter hours on each daily pairing | No new table, but daily burden, nothing known ahead of time, and copied pairings would carry hours forward unchecked. |

**[Claude's call] B.** It changes the plan's decision 4, which allowed only dated windows; the safety rule stays intact because a missing basis still means unknown. Unverified assumption: rosters mostly repeat weekly. Rotating rosters fall back to dated windows in batches. Confirm with a real operator before pilot.

## Data model

All tables: `tenant_id`, composite tenant FKs, RLS and FORCE RLS, `version`.

**`domain_driver_working_patterns` (new).** `driver_id`, `weekday_mask`, `local_start`, `local_end`, `ends_next_day`, `valid_from`, `valid_until` (required, at most 366 days after `valid_from`), `status` (`active`, `retired`), `recorded_by`, `recorded_at`.

**`domain_driver_availabilities` (altered).** `kind` (`available`, `unavailable`), `start_utc`, nullable `end_utc`, `status` (`active`, `retired`), `source_leave_id`, `recorded_by`, `recorded_at`. Open end is allowed only for `unavailable`. Remove `service_date` and naive timestamps.

**`domain_vehicle_availabilities` (altered).** `kind` (`planned_maintenance`, `out_of_service`), `start_utc`, nullable `end_utc`, `estimated_end_utc`, `responsible_label`, `status` (`active`, `released`, `cancelled`), `released_at`, `released_by`, `release_note`, `recorded_by`, `recorded_at`.

- `planned_maintenance` needs a finite end.
- `out_of_service` blocks until explicit release. `estimated_end_utc` never affects availability.
- Remove the `cascade="all, delete-orphan"` relationships on both availability tables so history is not deletable through the ORM.

**`domain_leave_requests` (new).** `driver_id`, `start_utc`, `end_utc`, `category` (`annual`, `sick`, `unpaid`, `other`), `state`, `private_note`, `requested_by`, `recorded_at`, and decision columns: `decided_by_membership_id` (always the actual actor), `decision_basis` (`member`, `external`), `external_route_id`, `stated_decision_maker`, `decided_at`. There is no diagnosis field. General views show only "absent"; category and note need note access.

**`domain_leave_approval_routes` (new).** Nullable `driver_id` (null is the organization default), and exactly one of `membership_id` or `external_contact_name` (CHECK), `is_active`. Multiple active routes per scope are allowed, which provides the designated alternative approver.

**`domain_office_audit` (new, SELECT and INSERT only).** Entity, action, actor, time, unique `request_id`, `payload_hash`, stored response. Also the idempotency record, following `ScheduleChange`: exact retry returns the original, changed payload returns 409. Stored responses and audit details never contain private notes. Add it to the append-only overrides in `backend/db/tenant_schema.py`.

**Existing rows [Claude's call].** The migration preflight aborts with row counts if either availability table holds rows. No code path writes them, so conversion, provenance and legacy-review machinery are dropped from the plan. If real rows appear at Task 0, return to the user rather than guess (SEC-09).

## Authority

**[Claude's call]** Two mechanisms replace the plan's five-capability grant table:

- **Record-keeping uses per-member grants, off by default (user approved).** New table `domain_office_grants`: `membership_id`, `capability`, `is_active`, `granted_by`, `granted_at`, `version`; unique on membership and capability, composite tenant FKs, RLS, append-only audit. Allowlist: `availability.manage`, `maintenance.manage`, `maintenance.release`, `office.notes.read`. The migration seeds nothing, so no existing account changes. Only `members.manage` can grant or revoke, and the next request sees it. Admin has no implicit grant and must grant themselves. `require_office_permission` reads this table, not the role matrix, which stays unchanged.

- **Leave authority comes only from an approval route.** No role implies it, and an admin must add themselves to a route to decide. Route administration requires `members.manage`. Management and viewer gain nothing.

Recording a hold and releasing it are separate grants, so an organization can give night staff `maintenance.manage` without `maintenance.release`.

**Deciding leave.** `decide(leave_id, expected_version, decision, action_id, note, external_route_id=None)`, with identity from the session:

- Without `external_route_id`: the actor needs an active route covering this driver with their own membership.
- With `external_route_id`: the actor needs `availability.manage`, the route must be external and cover this driver. The contact name is copied into `stated_decision_maker`. The UI labels this "recorded by X, stated decision by Y".
- Either way, the actor's `Membership.driver_id` must not equal the subject (also blocks recording your own external approval).
- Route lookup: driver-specific routes, else organization default. No route gives a visible `approver_missing` finding; the request stays pending.
- A route member also gets note access for drivers in that route's scope.

Known limit: own-leave protection relies on the explicit driver link. A staff member who drives but has no link is undetectable, and matching by name is forbidden (DATA-02). The route admin screen shows when a route member has no driver link.

**Undoing a blocker [Claude's call, after builder check].** Nothing that blocks work can be lifted by a weaker authority than the one that created the block:

- Cancelling approved leave needs the same authority as deciding it: a route covering that driver, and the actor's driver link is not the subject.
- Periods with `source_leave_id` are immutable except through leave cancel.
- Retiring an unlinked `unavailable` period needs `availability.manage` and the same own-subject check.
- Cancelling a `planned_maintenance` reservation needs `maintenance.manage`. Cancelling an `out_of_service` hold, which means "entered by mistake", needs `maintenance.release`; releasing a real hold also needs `maintenance.release`. Cancel requires a reason and is not release.

**Reading [Claude's call, after builder check].**

- Leave requests and driver periods: `availability.manage`, or an active route covering that driver. Route members see only their drivers' requests, whatever their role.
- Private note and category: `office.notes.read`, or a route covering that driver.
- Vehicle periods: `maintenance.manage`.
- Impacts: `schedule.read`. Rows show the driver or vehicle label and "unavailable", never category or note.
- Management and viewer roles gain nothing unless placed on a route.

## Availability calculation

One function, `availability_for_resources(db, tenant_id, identities, horizon)`, used by readiness, snapshot freezing, recovery and impacts.

- All intervals are half-open UTC. Adjacent endpoints do not overlap; touching windows merge.
- **Driver base:** dated `available` rows starting on a local date replace patterns for that date; otherwise active patterns expand through the existing wall-clock resolver in `time_service.py`. A pattern time in a DST gap or fold yields finding `working_window_needs_resolution`, fixed by a dated window with explicit fold.
- **Driver usable** = base − active `unavailable` rows, including approved leave. Pending leave is warning only.
- **Unknown:** no base and no blocker covering the horizon. **Known empty:** blockers cover the horizon. A pending request does not count as a blocker.
- **Vehicle usable** = whole horizon − active maintenance and holds. **[Claude's call]** Vehicles have no working windows; an active vehicle in a confirmed pairing is the explicit basis.
- **Crew usable** = driver ∩ vehicle.
- **Horizon** = service-day start to latest trip end plus largest transfer. Includes overnight patterns from the previous date. Open holds are clipped, never given a guessed end.

## Snapshots and verification

- `ResourceSnapshot.available_windows: tuple[tuple[int, int], ...] | None = None`, in elapsed minutes from the frozen `service_day_start_utc`.
- `SolverProblem.availability_enforced: bool = False` and `availability_exempt_trip_ids: tuple[str, ...] = ()`. These replace the plan's `availability_required_trip_ids`. **[Claude's call]** New snapshots enforce for all trips by default.
- `decode_problem` must tolerate missing keys and convert lists to tuples. Old snapshots decode as not enforced and remain byte-for-byte unchanged.
- `source_data['availability']` holds a fingerprint of the source rows and versions used, plus per-resource provenance. It is **not** placed in `source_versions` (see Recovery).
- New snapshots use `source_schema_version = 'ktel-operational-v2'`.
- `build_operational_snapshot` rejects unknown drivers with `working_windows_required`, naming each driver, with one next action. Pending leave and known-empty crews are warnings.

**Verifier** (new rules, bump `RuleSet.version`), calculated from frozen windows only:

- Trip `[start, end)` must fit inside one usable window.
- Consecutive trips needing travel: the transfer must fit inside one window at either end of the gap. An absence does not count as travel time. Windows 08:00–12:00 and 14:00–18:00, first trip ends 11:45, next starts 14:15, transfer 30: rejected.
- When `availability_enforced`, `None` windows are an error. Exempt trips skip these rules.
- Verifier never trusts a solver flag.

## Solver

- **[Claude's call]** Do not modify `framework/` or `services/`. `BoundedCustomSolver` overrides `is_valid`, adding the two availability helpers. Every shift entering the CP-SAT model already passes through `is_valid`, so one override covers neighbourhood search.
- **Seed:** the greedy seed comes from shared reference code. After `GreedySASolver` returns, a new sanitizer moves violating trips to unassigned, re-validates what remains in the shift, and if that shift is invalid (continuity, mandatory connection) unassigns the whole shift. Search can then reassign them.
- `cv-legacy-v0` gets a guard only: refuse a problem with `availability_enforced`. The API already allows only `cv-bounded-v1` for jobs, so legacy is not enforcement-capable and stays a reference.
- `cv_bounded` keys by `bus_id`. Daily unique indexes guarantee one active pairing per vehicle and per driver per date, so prepared problems map one to one. Successor crews can share a bus but do not go through the solver; `validate_cv_input` rejects duplicate `bus_id` under enforcement.
- Worker: reads the frozen snapshot only, so no new grants.

## Stale checks and recovery

The original plan could deadlock: `ScheduleChanges.validate` calls `source_review_required`, and successors copy the base's `source_versions`. Adding availability there would make a new absence block its own repair and make a successor unpublishable.

- `source_review_required` keeps its meaning, excludes availability and accepts v1 and v2, so v1 published bases stay changeable.
- New `availability_review_required(db, revision, snapshot)` compares current fingerprint with frozen, for unpublished operational revisions. v1 drafts return true. Called under the organization lock at apply, patch, approve and publish, and **not** on the published base in `changes.validate`.
- **Successor preview and create refresh availability.** Both compute current windows for all resources, including new `CREW_*` crews by underlying driver and vehicle, and set enforcement on. The published source remains untouched. `create` writes a new `source_data['availability']`.
- `availability_exempt_trip_ids` comes from `operated`, already computed server-side in `validate` from recorded departure and completion through lineage. Never from caller input or a clock.
- **Locked trips (user approved A).** A reviewed change may include `unlock` for a trip only when the refreshed check finds an availability conflict on it. It needs a reason, the existing `schedule.write` change permission and an audit entry. It never applies to a trip with a recorded departure or completion, and has no effect outside that change. The successor copies the lock state, then the unlock clears it. This is the one required edit to the urgent-change contracts: add the operation to `change_schemas.py` and `changes.validate`, with tests. Do it after urgent-change acceptance.
- If the refreshed verification still has violations, existing behaviour stands: `create` returns 422 with findings. All affected non-operated trips must be moved, unassigned or cancelled in that successor.
- v1 base with unknown drivers: `working_windows_required`, not a silent pass.
- Lock order: office writes take the organization row then their own row and never a revision, so they cannot deadlock with `changes.create` (revision then organization). The organization lock makes publish and office writes serial.

## Impacts

**[Claude's call]** Derived only, with no stored impact state; the plan's "retire" step is removed.

`list_office_impacts(db, tenant_id, *, date_from, date_to, page, page_size)`, with date range of at most 31 days: active blockers intersected with active pairings, open drafts and the latest publication per date. Each row gives entity, resource, trip, interval, publication or revision, and whether the trip has a recorded departure or completion.

An impact disappears only when a successor is actually published without the conflict, or the blocker ends. Cancelling leave or releasing a bus recomputes and restores nothing (OFFICE-07). GET writes nothing. Mutation responses return the same count for that interval ("saved, N trips need review"). Outbox hints contain IDs only, never notes or category.

## Interfaces

Routes live under `/api/v1/office`:

- `GET/POST/PATCH working-patterns`, `POST working-patterns/batch` (selected drivers, at most 100, atomic)
- `GET/POST/PATCH driver-periods`, `POST driver-periods/batch` (at most 100, atomic; for rotating rosters)
- `GET/POST leave-requests`, `POST leave-requests/{id}/decision`, `POST leave-requests/{id}/cancel`
- `GET/POST/PATCH vehicle-periods`, `POST vehicle-periods/{id}/release`, `POST vehicle-periods/{id}/cancel`
- `GET/POST/PATCH approval-routes`
- `GET impacts`

Every write takes a `request_id` and, for existing records, `expected_version`. Dates on approved leave do not change; cancel and create a new request. Release rejects future `released_at` and a time before the hold's start. Closing one hold does not affect others.

Backend code lives in `backend/app/domain/office/` and `backend/app/api/office.py`. Frontend lives in `frontend/src/features/office/`, reusing `RecordPicker`, workspace navigation, unsaved-change helpers and `apiFetch`.

## Interface behaviour

- Service day shows "these drivers have no working time for this date", with one action.
- Bulk form: choose drivers, weekdays, hours, date range; shows exact proposed result before saving. Timetable-derived suggestions are labelled and never saved on open.
- Pending, approved absence, planned maintenance, estimated return and actual hold have distinct text and icon, not colour alone.
- Impact list links to the existing change workflow with no parallel write path.
- No delivery, replacement or certification claims.

## Delivery order and review

**[Claude's call]** Three independent review gates instead of one final review:

1. **Records:** routes, intervals and patterns, leave, maintenance. Review gate A.
2. **Office screens,** before enforcement, so staff and tests can enter working time before anything requires it.
3. **Enforcement and recovery:** snapshot, verifier, solver, stale checks, successor refresh, impacts and impact UI. Update backend and browser fixtures with one shared working-time helper; budget this explicitly, since every operational fixture needs it. Review gate B.
4. **Acceptance:** full suites, screenshots, requirement dispositions. Final whole-tree review.

## Acceptance

From the scope document, scenarios 2, 3, 4, 5, 6, 7, 9, 10, 11, against real PostgreSQL with restricted roles and rendered frontend. In addition:

- Approve leave on a published day, then complete a successor for the same day and publish it.
- A trip with a recorded departure on an absent driver stays exempt; a forged exemption has no input path.
- A weekly pattern across DST gap and fold gives a finding, then a dated fix resolves it.
- External route decision shows both recorder and stated decision-maker.
- Owner-employed driver: wrong route member refused.
- CV never assigns into absence on a real one-pair/two-trip problem; forged candidate fails verification.

## Left to the builder

Column types and index choices, module split inside `office/`, migration numbering at Task 0 following the `NNNN_name` convention (currently head `0012_schedule_cancellation`), form layout within the design system, and how to expose the wall-clock resolver without duplicating it.
