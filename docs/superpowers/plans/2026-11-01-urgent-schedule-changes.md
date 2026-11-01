# Guided Last-Minute Schedule Changes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task with regressions and one final fresh review.

**Goal:** Let dispatchers safely review and publish urgent driver, trip and cancellation changes with clear timeline feedback.

**Architecture:** Preserve immutable published revisions, tenant-scoped PostgreSQL and independent verification. Introduce explicit successor/change records and cancellation semantics before exposing workflow actions; show linked prior-publication operational facts without moving their ownership. Reuse existing Next.js timeline and permissions.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Next.js, React, TypeScript, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-01-urgent-schedule-changes-design.md` (user approved).

## Global Constraints

- Finish the in-progress guided dispatcher/Operations acceptance and final review first; preserve the current dedicated dirty branch. Never commit or push.
- Published snapshots/history stay immutable; server enforces RLS, tenant boundaries, CSRF, permissions, concurrency, independent verification, and idempotency. No real notification/GPS/legal-coverage claims.
- Trips retain departure/arrival during drag. Cancellation is distinct from unassignment. Driver-only substitution and moving to an existing crew are distinct.
- Preserve original publication/attribution for linked operational reports. Do not infer departure from a clock; protect started/completed work conservatively.
- Existing approval and publication rules stay authoritative. Changes that require unsupported legal/availability facts must be visibly uncertain and blocked where needed.

## Review Focus

1. Same person or vehicle present through two distinct pair IDs: conflicting assignments must be detected (Task 1).
2. New publication or changed source while a preview is open: no stale change may silently apply (Task 2).
3. A cancelled trip must not vanish from the audit, historical publication or Operations while being excluded from active future work (Task 3).
4. Prior-publication open reports and actual departure/completion facts must remain attributed and visible, without contaminating another tenant or trip (Task 4).
5. Keyboard/touch operation and dragging across rows at arbitrary horizontal coordinates must retain the timetable and expose the same checks (Task 5).

## Task 0: Finish existing authorized workflow

**Files:** existing guided workflow plan, ledger, acceptance audit, tests and screenshots.
- [ ] Complete the Operations browser gate and inspect actual screenshots; fix failures with targeted regressions.
- [ ] Complete page-by-page acceptance (including unsaved forms and role-appropriate navigation), backend full suite, typecheck/build, full browser suite and fresh whole-working-tree review as required by `docs/superpowers/plans/2026-11-01-guided-dispatch-workflow.md`.
- [ ] Record evidence and outstanding limitations; no commits or pushes.

## Task 1: Verify underlying driver and vehicle conflicts

**Files:** `backend/app/domain/verification/verifier.py`, verifier contracts/snapshot adapters as required; `backend/tests/verification/test_assignment_eligibility.py`, new `backend/tests/verification/test_underlying_resource_overlap.py`.
**Interface:** `HardRuleVerifier.verify(problem, assignments)` remains authoritative and emits separate driver/vehicle overlap findings with trip references when two distinct resource IDs represent the same underlying person or bus.
- [ ] Add tests: overlapping assignments on pair A and B sharing a driver fail; sharing a vehicle fail; different driver and vehicle pass; adjacent endpoints pass; non-overlapping shared identities pass; unavailable identity is reported rather than guessed for a driver-only change.
- [ ] Run `uv --directory backend run pytest tests/verification/test_underlying_resource_overlap.py -q`; expect failure for cross-pair overlap.
- [ ] Extend independent verification and frozen snapshot identity mappings; preserve current constraints and existing verifier contracts.
- [ ] Run new and existing verifier/canonical tests; expect all pass.

## Task 2: Immutable publication successor and previews

**Files:** new `backend/app/domain/scheduling/changes.py`, `change_schemas.py`, `backend/app/api/schedule_changes.py`, migration after current head and registry/grants; tests `backend/tests/integration/test_schedule_changes.py`.
**Interface:** `POST /api/v1/scheduling/changes/preview` accepts base `publication_id`, base revision version, proposed trip→pair assignments and reason, returns original/proposed facts, source versions and independent findings with no writes. `POST /api/v1/scheduling/changes` accepts those identifiers, expected versions, stable request ID and the reviewed changes, creates one draft successor atomically, and returns revision/version; an exact retry returns the same result, a changed retry or stale base returns409. Normal approval/publish endpoints remain the only publication path.
- [ ] Test actual published fixture: preview has no writes; one-trip move retains frozen times; batch validates atomically; immutable source stays byte-for-byte unchanged; repeat request deduplicates; concurrent/stale publication, version and source reject with409; tenant and read-only roles cannot write.
- [ ] Run test file and observe missing endpoint failure; implement composite tenant foreign keys, FORCE RLS, restricted grants, durable attribution/reason/idempotency and preview/recheck under a lock.
- [ ] Test explicit reported departure/completion and uncertain operational state block unsafe historical changes; clocks alone never establish departure. Test locked trips and cross-pair findings from Task1.
- [ ] Run migration, identity/RLS, scheduling, verifier and change integration tests; back up local DB privately before any local migration, upgrade and refresh restricted grants only after tests pass.

## Task 3: Cancellation and driver replacement

**Files:** scheduling change domain/API, snapshot/verification/coverage/solver contracts, migrations as needed; `backend/tests/integration/test_schedule_change_actions.py`.
**Interface:** Preview/apply request extends Task2 with typed operations `move`, `unassign`, `cancel` (required reason), and `replace_driver` (selected trip IDs, old driver, replacement driver, retained bus). Explicit crew identity and source versions accompany replacement; it may not invent a pairing or availability.
- [ ] Test cancellation remains visible with reason in successor and old publication, is excluded from active work and coverage, and differs from unassignment; test atomic mixed batch and rejection of missing reason.
- [ ] Test selected versus all remaining trips, independent driver/vehicle overlap, locked/in-progress work, no suitable replacement, changed source, partial failure and concurrent edits; no duplicate or silently auto-applied proposal.
- [ ] Run tests to observe failures, implement cancellation through all authoritative snapshot/solver/verifier/read paths and preserve tenant/audit guarantees, then run focused canonical/optimization/verification integration gates.

## Task 4: Linked operational history across publications

**Files:** `backend/app/domain/incidents/operations.py`, operations contracts/API and `frontend/src/features/operations/`; tests `backend/tests/integration/test_operations_publication_history.py`, `frontend/tests/daily-operations.spec.ts`.
**Interface:** `GET /api/v1/operations/day` includes explicitly labelled linked prior-publication reports and departure/completion facts with original publication ID, author, timestamp, resolution status and trip identity; original events are never copied or rebound. Only verified lineage and matching trip identity may link.
- [ ] Test an open breakdown and explicit departure remain visible after successor publication, are absent from unrelated/foreign schedules, retain original owner/attribution, and resolution operates on the original state with expected version/idempotency. Verify cancellations and ambiguous changed trips do not link incorrectly.
- [ ] Observe initial failure; implement bounded lineage queries and role-scoped UI with source labels; test old publication remains unchanged and user can understand which version each report belongs to.
- [ ] Run operations/history/RLS and production-browser tests.

## Task 5: Accessible timeline interaction and guided review

**Files:** `frontend/src/features/scheduling/timeline/`, new focused change-review components and API client; `frontend/tests/schedule-changes.spec.ts`.
**Interface:** A target row identifies the exact driver/vehicle pair; drag shows original outline, target highlight, fixed-time preview and checking/ready/conflict text; drop and keyboard/touch **Move to…** call the same Task2 preview. Multi-trip driver replacement and cancellation use Task3 actions. Confirming applies only a draft and publication remains a separate authorized action.
- [ ] Browser tests with real fixture: drag at different horizontal coordinates retains 08:00/09:30, target identifies both people/vehicle, invalid/conflicting target is explained, cancellation versus unassignment remain visible, keyboard alternative works, stale response cannot update another date/tenant and failed request preserves selections.
- [ ] Observe RED; implement pointer/keyboard/touch workflow, focus restoration, accessible non-colour feedback, reduced motion, responsive layouts, clear progress and review/publish state. Never fabricate check results.
- [ ] Run change, canonical, Operations and navigation browser tests, typecheck/build; inspect desktop/mobile screenshots in Greek/English and both themes.

## Task 6: Acceptance and final review

- [ ] Complete end-to-end published→successor workflow with two dispatchers, two tenants, reader, conflicting and already-operated examples; verify previous publication and linked history survive reload.
- [ ] Run full backend suite, strict typecheck, production build and full browser suite; keep CPU-heavy build/browser work separate from timed CV tests. Record output, screenshots, migration and limitations.
- [ ] Dispatch one fresh read-only whole-working-tree review including untracked files, spec, ledger and the exact Review Focus. Fix Important/Critical findings in one RED→GREEN pass; rerun affected/full gates. Preserve working tree without committing.

## Self-review

Tasks1–5 map each approved interaction and underlying safety requirement to a real server contract and tests. Task0 preserves the previously authorized completion order. Cancellation and driver replacement are intentionally backend work rather than decorative drag behavior. Retain execution method and authorization already given in this session; no redundant plan approval or git history action.
