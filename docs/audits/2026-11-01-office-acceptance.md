# Office availability, leave and maintenance — acceptance

Reviewed tree: `feat/v2-ktel-platform` at `a81aced` plus the uncommitted working tree (nothing committed or pushed). Environment: local PostgreSQL 16 container, disposable `ktel_test_*` databases for backend tests; browser tests use disposable "Browser identity test" organizations in the local database upgraded to `0016_office_vehicle_periods` (private backup first), own backend on :8001 and production frontend on :3000. Plan and decisions: `docs/superpowers/plans/2026-11-01-office-availability-maintenance.md` and its `-progress.md` ledger.

## Evidence

| Gate | Command | Result |
|---|---|---|
| Backend, whole suite | `cd backend && uv run pytest -q` | **400 passed, 1 failed** in 23m. The failure is `tests/performance/test_synthetic_ladder.py::test_synthetic_ladder_100_trips` (6.0s against a 5.5s limit) and happened while the browser suite loaded the machine; it passed alone afterwards (2 of 2 runs). Not a functional failure, but not a clean full-suite run either |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend lint | `npm run lint` | 0 errors (existing style warnings remain) |
| Production build | `BACKEND_URL=http://127.0.0.1:8001 npm run build` | succeeds |
| Browser, whole suite | `npx playwright test` | Last full run against the development server: **56 passed, 2 failed** in 13.3m. (1) the two-driver repair journey failed because of a bug in my "ignore stale check" change (a mounted-flag broke under React's development double-mount); fixed, and the journey passes alone. (2) `identity.spec.ts:53` (password recovery) fails in development mode with an empty form after submit, which looks like submitting before the page hydrates; it is in code this work did not touch and passed in the earlier production-build run (57 passed in 6.7m). Not re-run on a production build since |
| Independent review | three fresh read-only reviews (records; enforcement and UI; whole delivery) plus two cross-checks from a second reviewer | findings fixed test-first; see ledger `Final(A)`, `Final(B)`, `Final(C)` |

Not done: a clean full backend run and a full browser run on a production build after the last fix pass (the targeted tests for each fix pass); load, capacity and restore drills on a representative environment; a licence or legal review.

Captures reviewed by eye: `frontend/test-results/office-*.png`, `visual-*.png`, `service-day-working-time.png` (English and Greek, light and dark, desktop and 390px).

## Requirement dispositions

PASS needs implementation plus a completed verification. Test names are in `backend/tests/{domain,integration,verification,optimization}/test_office_*.py` and `frontend/tests/office-*.spec.ts`.

| ID | Status | Basis and limits |
|---|---|---|
| OFFICE-01 | PASS | Records carry subject, recorder, category, exact interval; leave and period history in append-only office audit. |
| OFFICE-02 | PASS | Four leave states; pending is warning only (`test_pending_leave_is_a_warning…`); approved leave and absences constrain solver and verifier. |
| OFFICE-03 | PASS | Approval routes, own-leave via driver link, external decisions record recorder and stated decision-maker, versioned and concurrent decisions (`test_retry_with_changed_payload…`, `test_only_a_member_on_the_drivers_route…`). |
| OFFICE-04 | PARTIAL | Category and notes need `office.notes.read` or a route; audit and impacts carry no notes. No office events or outbox hints are emitted, although the design called for them. Application logs were not inspected. |
| OFFICE-05 | PASS | Adjacent, partial, overnight, multi-day, leap-day and DST gap/fold cases (`test_office_intervals.py`, `test_pattern_in_dst_gap_or_fold…`); missing time is unknown; the horizon is the service day plus travel and is documented. |
| OFFICE-06 | PARTIAL | Approval is never refused for existing trips and affected trips are listed; repair uses the existing reviewed change. A day with two absent drivers is repaired in one reviewed change from the UI (journey passes). |
| OFFICE-07 | PASS | `test_cancelling_leave_rechecks_without_restoring_assignments`. |
| FLEET-01 | PASS | Planned reservations and open holds are separate records; no minor-issue concept exists, so none can be mistaken for a hold (claim removed; not tested). |
| FLEET-02 | PASS | `test_estimate_passing_never_releases_a_hold`; journey keeps a hold "Open" past its estimate. |
| FLEET-03 | PASS | Release records actor, time and note; the dialog states it is not a mechanical certification; release needs its own grant. |
| FLEET-04 | PASS | Vehicle blockers in solver and verifier, per underlying driver and vehicle. |
| FLEET-05 | PARTIAL | Overlapping holds, late extension, early release, stale versions and archived vehicles are tested; concurrent maintenance edits are covered by version checks, not a thread race. |
| STUDIO-02 | PASS | `RULE_AVAILABILITY_{TRIP,TRANSITION,UNKNOWN}` recomputed from frozen windows. |
| STUDIO-04 | PASS | `availability_changed` at patch, request-approval, approve, publish and solver enqueue; the published base is exempt. |
| SEC-01, SEC-02 | PASS | New tables have RLS, FORCE RLS and composite tenant keys; audit is insert-only for the API role; the worker has no office-table access (`test_office_permissions.py`, tenancy audit clean on the upgraded database). |
| SEC-03 | PASS | Per-member grants, off by default; revocation applies on the next request. |
| SEC-06 | PASS | Organization lock then own rows; idempotent retries; one concurrency test shows an office write and a publication step do not deadlock; it accepts either outcome and does not prove an ordering. |
| SEC-08 | PARTIAL | The worker reads only the frozen snapshot; not load tested. |
| SEC-09 | PARTIAL | Migrations `0013`–`0016` abort on existing availability rows; upgraded locally after a private backup. A restore drill was not run. |
| UX-02…UX-06 | PARTIAL | Required-first forms, unsaved-change guard, failed saves keep entries, stale responses ignored on the Repair check (other screens not audited), text-plus-symbol states, phone actions reachable. A full keyboard and screen-reader audit was not done. |

Scenarios from the scope document: 4 (leave) PASS; 5 (maintenance and open holds) PASS; 6 (change arriving at each stage) PASS for apply, approve, publish and solver run, preview covered by successor refresh; 7 (recovery) PARTIAL; 9 (DST) PASS for availability and solver inputs, not exercised through imports or reports; 12 (load and restore) NOT VERIFIED.

## Limits and open items

1. **Resolved:** a day with several absent drivers is repaired in one reviewed change (Office → Affected trips → "Repair <date> in one change"). Chained trips are moved or cancelled together with their partners; this part is verified by a server test and typecheck, not by a browser journey.
2. Office tables scroll sideways on phones with the action column pinned; no card layout.
3. A locked trip whose only conflict is travel through an absence cannot be released.
4. A stale reviewed-change successor shows the Service-day advice rather than "start a new change from the publication".
5. Not claimed: legal driving-hour or rest compliance, medical fitness, roadworthiness, notification delivery, authenticated external approval, production capacity.
6. Impact counts after an edit cover the next 31 days; a change that affects trips further out says nothing until that day enters the window.
7. The solver does not model a bus handed between two crews; the verifier rejects an infeasible handover, so the cost is fewer valid solver results.
8. Deferred minors are listed in the ledger under `Final(C)`.
