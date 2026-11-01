# Driver Portal (first slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Office invites a driver from an existing driver record; the driver signs in on a phone and sees own published duties, requests leave and acknowledges exact duty versions.

**Architecture:** Same FastAPI app and Next app. Identity link = `Membership.driver_id`, set when an invitation that carries `driver_id` is accepted. New `/api/v1/driver/*` routes take the driver only from the session (`current_driver`). Acknowledgments are an insert-only table. Office actions reuse `office_replay`/`office_record` and `domain_office_audit`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic raw SQL, PostgreSQL RLS, pytest; Next.js 15 app router, TypeScript, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-01-driver-portal-design.md` (approved, includes builder-check answers and the invitation-delivery decision).

## Global Constraints

- API/worker DB roles non-owner, non-BYPASSRLS; new tables: RLS + FORCE RLS + composite tenant keys; migration `0017_driver_portal`; run `uv run python -m db.provision_runtime --refresh-grants` after upgrade.
- No runtime schema creation. Local DB upgrade only after a private backup (0600 file under `~/.local/share/ktel-db-backups/`). Never touch an external or production DB.
- No real email. Invitation mail stays in `domain_email_outbox` with status `not_configured`; tests read it with `decrypt_payload`. The accept link is never returned by an API or shown in the UI.
- Nothing committed or pushed until the user directs it (the executing-plans commit steps are skipped; ledger records "No commits").
- Driver id is never accepted from a caller under `/api/v1/driver`; request bodies use `extra='forbid'`.
- Other thread's uncommitted work stays untouched; small precise edits after re-reading shared files.
- Ponytail: reuse `Membership.driver_id`, `IdentityToken`, `EmailOutbox`, office leave and audit helpers, `Operations.day` data shape. Tag shortcuts `# [ponytail: ...]`.
- Greek and English copy for every new string; light and dark; phone width 390px works without horizontal scroll in `/driver`.

## Review Focus

1. A linked driver whose publication is replaced mid-day: My duties must show only the current publication; an acknowledgment of the old one must not count (Task 4 test).
2. Same driver on two crews (replace-driver change): duties from every crew of that driver appear once each (Task 3 test).
3. Unlink while the driver is signed in: next request is 401/403 and sessions are revoked (Task 2 test).
4. Invitation to an email that already has an account: clear 409 at accept, the driver stays unlinked and the office row says why (Task 2 test).
5. Cancelled trip in a current publication: shown as cancelled, acknowledgeable, never listed as active work (Task 3/4 tests).

---

### Task 0: Remove the misleading stub and record the plan ledger

**Files:** Delete `frontend/src/features/driver/DriverPortal.tsx` (tracked, unreferenced; it marks duties acknowledged in local state only, which violates PORTAL-04). Create `docs/superpowers/plans/2026-11-01-driver-portal-progress.md` (first line `# SDD ledger — plan: docs/superpowers/plans/2026-11-01-driver-portal.md`).

- [ ] **Step 1:** Confirm nothing imports it: `grep -rn DriverPortal frontend/src frontend/tests` shows only the file itself. Expected: no other matches.
- [ ] **Step 2:** Delete the file; create the ledger with the line "Task 0: complete — stub removed; no commits."

### Task 1: Migration 0017, models, grants

**Files:** Create `backend/alembic/versions/0017_driver_portal.py`, `backend/app/domain/identity/driver_models.py`; Modify `backend/app/domain/identity/models.py` (IdentityToken gains `driver_id`, `revoked_at`), `backend/db/metadata.py` (import new model), `backend/db/tenant_schema.py` (grant `domain_driver_acknowledgments` as `'SELECT, INSERT'` in the API branch only), `backend/tests/integration/test_migrations.py` (head revision + table list).
Test: `backend/tests/integration/test_driver_portal_schema.py`.

**Interfaces:**
- Produces: columns `domain_identity_tokens.driver_id INTEGER NULL` (composite FK `(tenant_id,driver_id)` → `domain_drivers`), `revoked_at TIMESTAMPTZ NULL`; CHECK `driver_id IS NULL OR (kind='invitation' AND role='driver')`; partial unique index `uq_invitation_driver_active ON (tenant_id,driver_id) WHERE kind='invitation' AND consumed_at IS NULL AND revoked_at IS NULL AND driver_id IS NOT NULL`; partial unique index `uq_membership_driver ON domain_memberships(tenant_id,driver_id) WHERE driver_id IS NOT NULL`; table `domain_driver_acknowledgments(id SERIAL PK, tenant_id, publication_id VARCHAR NOT NULL, revision_id VARCHAR NOT NULL, revision_version INTEGER NOT NULL, trip_id VARCHAR NOT NULL, driver_id INTEGER NOT NULL, acknowledged_by INTEGER NOT NULL, acknowledged_at TIMESTAMPTZ NOT NULL, request_id VARCHAR(36) NOT NULL, UNIQUE(tenant_id,publication_id,trip_id,driver_id), UNIQUE(tenant_id,request_id,trip_id), FKs (tenant_id,driver_id)→drivers, (tenant_id,acknowledged_by)→users(ktel_id,id), (tenant_id,publication_id,revision_id)→domain_publications(tenant_id,publication_id,revision_id))` with RLS + FORCE RLS + tenant policy; SQLAlchemy model `DriverAcknowledgment` in `driver_models.py`.
- Preflight in upgrade: abort with a row count if two memberships already share `(tenant_id,driver_id)`.

- [ ] **Step 1: Write failing test** `test_schema_enforces_one_login_and_one_pending_invitation_per_driver_and_acks_are_insert_only`: with `restricted_databases`, as owner insert two memberships with the same driver → IntegrityError; two unrevoked unconsumed invitation tokens for one driver → IntegrityError; as the API role, `INSERT` into acknowledgments succeeds and `UPDATE`/`DELETE` raise permission errors; a cross-tenant acknowledgment row is invisible under the other tenant's RLS context.
- [ ] **Step 2:** `cd backend && uv run pytest -q tests/integration/test_driver_portal_schema.py` → FAIL (no table).
- [ ] **Step 3:** Write the migration (raw SQL, same style as `0013`; `down_revision='0016_office_vehicle_periods'`; downgrade raises). Add model + metadata import + grant line.
- [ ] **Step 4:** Make the migration test list/head expectations pass (`tests/integration/test_migrations.py`). Run both test files → PASS.
- [ ] **Step 5:** Ledger line with exact command and result.

### Task 2: Invite, link, unlink, revoke (server)

**Files:** Modify `backend/app/domain/identity/service.py` (`issue_invitation`, `accept_invitation`), `backend/app/api/identity.py`, `backend/api/auth.py` only if the accept route passes the token through (read it first). Create `backend/app/domain/identity/driver_links.py`.
Test: `backend/tests/integration/test_driver_links.py`.

**Interfaces:**
- `issue_invitation(db, tenant_id, email, role='viewer', driver_id: int | None = None)`: `driver_id` only with `role == 'driver'`, driver must exist, be active and not already linked, else `HTTPException(409, {'code': 'driver_already_linked' | 'driver_invite_pending' | 'driver_archived', 'message': ...})`. Before inserting, set `revoked_at=now` on this driver's unconsumed tokens that are past `expires_at`; a still-valid pending invitation for the same driver → `driver_invite_pending` (use revoke first to replace).
- `accept_invitation` sets `Membership.driver_id = token.driver_id` in the same transaction (IntegrityError on the unique index → 409 `driver_already_linked`; existing-email 409 unchanged and the token stays unconsumed).
- `driver_links.py`: `list_driver_links(db, tenant_id, driver_ids: list[int]) -> dict[int, dict]` returning `{driver_id: {'state': 'unlinked'|'invited'|'linked'|'expired', 'email': str|None, 'membership_id': int|None, 'invitation_id': str|None, 'expires_at': iso|None, 'delivery_status': str|None}}`; `revoke_invitation(db, user, invitation_id) -> None`; `unlink_driver(db, user, driver_id) -> None` (sets `driver_id=None`, bumps `Membership.version`, revokes all of that member's `AuthSession`s, in one transaction; membership role stays `driver`).
- Routes (all `members.manage`, all via `run_once`-style idempotency using `office_replay`/`office_record`, entity `driver_link`): `POST /api/v1/identity/invitations` gains optional `driver_id` and `request_id`(UUID, optional for legacy callers); `GET /api/v1/identity/driver-links?driver_ids=1,2,...` (≤100); `POST /api/v1/identity/invitations/{id}/revoke`; `POST /api/v1/identity/drivers/{driver_id}/unlink`. Response of invite never contains the token or link.

- [ ] **Step 1: Failing tests** in `test_driver_links.py`: (a) invite with `driver_id` → outbox row `not_configured`, response has no `token`/`link`; accept via `decrypt_payload` link → `/auth/me` as that user returns role `driver` and membership `driver_id` set; (b) second invite for same driver while pending → 409 `driver_invite_pending`; after revoke the old link no longer accepts (400) and a new invite works; (c) linking an already-linked driver → 409 `driver_already_linked`; (d) archived driver → 409; `driver_id` with role `viewer` → 422; (e) unlink: member's existing session gets 401 on the next request, list shows `unlinked`, invitation can be re-sent; (f) invitee email already has an account → accept 409, driver stays `invited`, token unconsumed; (g) same `request_id` replays identical response, changed payload → 409 `request_changed`; (h) non-admin → 403; cross-tenant driver id → 404/409 not leaking existence.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run `tests/integration/test_driver_links.py tests/integration/test_identity.py` → PASS. **Step 5:** Ledger.

### Task 3: `current_driver` and My duties

**Files:** Modify `backend/app/domain/identity/permissions.py` (`driver` role gains `driver.self.leave`); Create `backend/app/api/driver.py`, `backend/app/domain/identity/current_driver.py`, `backend/app/domain/scheduling/driver_duties.py`; Modify `backend/main.py` (include router at `/api/v1/driver`).
Test: `backend/tests/integration/test_driver_duties.py`.

**Interfaces:**
- `current_driver(user=Depends(get_current_user), db=Depends(get_db)) -> DriverContext` (`dataclass(user, driver_id: int)`): requires role `driver`, active membership, `driver_id` not null and the driver active; else 403 `{'code': 'driver_not_linked' | 'driver_archived', 'message': <office guidance>}`.
- `driver_duties(db, tenant_id: int, driver_id: int, today: date, timezone: str) -> dict`: window `today-1 … today+14` in the organization timezone; for each date takes the newest `Publication` of an operational revision (same selection as `Operations.day`); returns `{'timezone': str, 'days': [{'service_date': str, 'publication_id': str, 'revision_id': str, 'revision_version': int, 'duties': [{'trip_id', 'trip_code', 'start_local', 'end_local', 'start_utc', 'end_utc', 'origin': {'code','name_el','name_en'}, 'destination': {...}, 'vehicle_label', 'cancelled': bool, 'acknowledged': bool}]}]}` where duties are `RevisionAssignment` rows whose resource's `driver_id` equals the session driver (from `snapshot.source_data['resources']`/`problem_data`). No draft, no other driver's name, no office notes. Only days with ≥1 duty are returned.
- `GET /api/v1/driver/duties` → that dict. `GET /api/v1/driver/me` → `{'driver_name', 'driver_code', 'timezone'}`.

- [ ] **Step 1: Failing tests:** (a) published day: linked driver sees exactly own trips, none of the other crew's; a draft successor never appears; (b) driver on two crews (replace-driver change) sees each trip once; (c) cancelled trip appears with `cancelled: true`; (d) unlinked `driver` role → 403 `driver_not_linked`; non-driver role (admin) on `/api/v1/driver/duties` → 403; (e) a query string `?driver_id=` is ignored and cannot select another driver; (f) window bounds; (g) another tenant's driver id impossible (RLS).
- [ ] **Step 2:** FAIL. **Step 3:** Implement (reuse `Operations`-style publication query; do not edit `incidents/operations.py`). **Step 4:** PASS. **Step 5:** Ledger.

### Task 4: Acknowledgments

**Files:** Modify `backend/app/api/driver.py`; Create `backend/app/domain/scheduling/driver_acks.py`.
Test: `backend/tests/integration/test_driver_acks.py`.

**Interfaces:**
- `POST /api/v1/driver/acknowledgments` body `{request_id: UUID, publication_id: str, trip_ids: list[str] (1..200, unique)}` (`extra='forbid'`) → `{'acknowledged': [{'trip_id','acknowledged_at'}]}`. Server checks per trip: publication is the newest for its date, trip is an assignment of the session driver in that publication; else 409 `{'code': 'publication_replaced' | 'not_your_duty'}` and nothing is written (all-or-nothing). Idempotent: `office_replay`/`office_record` pattern with entity `driver_ack`; already-acknowledged trips return the stored time and write nothing.
- Duties payload `acknowledged` becomes true only for a row matching (publication_id, trip_id, driver).

- [ ] **Step 1: Failing tests:** (a) acknowledge one trip → duties show it acknowledged after reload, row stores revision id/version and actor; (b) a republish (new publication) shows the same trip unacknowledged and the old publication id is refused with `publication_replaced`; (c) another driver's trip → 409 `not_your_duty`, nothing written; (d) replay returns identical result; changed payload same `request_id` → 409; (e) acknowledging a cancelled trip works and is flagged cancelled; (f) GET duties never writes (row count unchanged); (g) API role cannot UPDATE/DELETE the table.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Ledger.

### Task 5: Driver leave

**Files:** Modify `backend/app/domain/office/leave.py` (extract `_create_leave(db, user, driver_id, req)`; `request_leave` keeps its `availability.manage` check and calls it; add `request_own_leave(db, user, driver_id, req)` and `cancel_own_pending_leave(db, user, driver_id, leave_id, req)`), `backend/app/api/driver.py`.
Test: `backend/tests/integration/test_driver_leave.py`.

**Interfaces:**
- `POST /api/v1/driver/leave-requests` body = `LeaveCreate` without `driver_id` (new schema `DriverLeaveCreate(request_id, start_local, end_local, fold_start, fold_end, category, private_note)`, `extra='forbid'`); `GET /api/v1/driver/leave-requests?date_from&date_to` (≤62 days, own requests only, includes own `category`, `private_note`, `decision_note`, state, decider display only as `decision_basis`); `POST /api/v1/driver/leave-requests/{id}/cancel` body `{request_id, expected_version}` — own `pending` only, else 409 `not_cancellable`. All require `driver.self.leave` and `current_driver`; idempotent via `run_once` helpers (move `run_once` out of `api/office.py` only if needed; otherwise import it).
- Approval, the own-leave block and impacts stay exactly as in the office service.

- [ ] **Step 1: Failing tests:** (a) driver creates pending request; the office approver (route member) sees it and approves; driver's list shows `approved` after reload and an `unavailable` period exists; (b) driver cannot decide or cancel an approved request; cancels own pending; (c) another driver's id cannot be supplied (schema rejects `driver_id`); another driver's request id → 404; (d) overlapping/over-long ranges rejected like the office form; (e) replay/changed payload; (f) a driver login cannot call any `/api/v1/office/*` route (403).
- [ ] **Step 2–4:** FAIL → implement → PASS plus `tests/integration/test_office_leave.py` still PASS. **Step 5:** Ledger.

### Task 6: Office UI — invite and link status

**Files:** Modify the Drivers screen component under `frontend/src/features/resources/` (find the driver record row/detail component first; add a small `DriverAccess.tsx` beside it); Create `frontend/src/features/resources/DriverAccess.tsx`; Modify `frontend/src/globals.css` equivalent (`frontend/src/styles/globals.css`) only for needed classes (reuse `office-*`).
Test: `frontend/tests/driver-invite.spec.ts`.

**Interfaces:**
- `DriverAccess({ driver, canManage }: { driver: { id: number; name: string }; canManage: boolean })` shows state from `GET /identity/driver-links`: Unlinked → "Invite to sign in" (email input, `request_id` per attempt, message "Queued. No email has been sent." when status is `not_configured`, else "Email queued"); Invited → email, expiry, delivery status, "Revoke invitation"; Linked → email, "Unlink sign-in" with confirmation. Visible only with `members.manage`.

- [ ] **Step 1: Failing journey** `a dispatcher invites a driver from the driver record and unlinks the sign-in`: create driver, open record, invite, see "Queued", revoke, invite again, accept via the outbox link (read with the node helper used by `identity.spec.ts`), record shows Linked; unlink shows Unlinked; non-admin sees no controls.
- [ ] **Step 2–4:** FAIL → build → PASS. Inspect real captures (EN/EL, light/dark, 390px). **Step 5:** Ledger.

### Task 7: Driver area `/driver`

**Files:** Create `frontend/src/app/driver/page.tsx`, `frontend/src/features/driver/{DriverShell,DutiesView,LeaveView,driver-api,contracts}.tsx|ts`; Modify `frontend/src/app/page.tsx` (role `driver` → `router.replace('/driver')`; non-driver roles opening `/driver` → `/`), `frontend/src/styles/globals.css` (driver-* classes, mobile-first).
Test: `frontend/tests/driver-portal.spec.ts`, `frontend/tests/driver-visual.spec.ts`.

**Interfaces:**
- `driver-api.ts`: `getDuties()`, `acknowledge(publicationId, tripIds)`, `listLeave(from,to)`, `requestLeave(body)`, `cancelLeave(id, version)`; every mutation uses one stable `request_id` per attempt; errors map `driver_not_linked`, `publication_replaced`, `not_your_duty`, 401 (session expired), `TypeError` (offline) to Greek/English text; never claims success without a 2xx.
- Views: My duties (days, duties with local time and zone label, vehicle, cancelled badge, per-duty "Acknowledge" and "Acknowledge all" per day; acknowledged shows time); Leave (form + list with real status, cancel on pending); header with language, theme, sign out. No office navigation.

- [ ] **Step 1: Failing journeys:** driver (linked via API fixture) signs in at 390px → sees only own duties → acknowledges → reload keeps it; republish by office → duty returns unacknowledged; requests leave → office approves → status updates after reload; unlinked driver sees the "ask the office" state; admin visiting `/driver` is redirected to `/`; offline (`context.setOffline`) shows "No connection" and does not mark acknowledged; expired session shows sign-in prompt.
- [ ] **Step 2–4:** FAIL → build → PASS; real captures reviewed (EN/EL, light/dark, 390px, empty/error states).
- [ ] **Step 5:** `npm run typecheck`, `npm run lint` (0 errors), production build.

### Task 8: Gates, docs, final review

- [ ] Full backend `cd backend && uv run pytest -q`, full `npx playwright test`; read outputs.
- [ ] Back up the local DB privately, `alembic upgrade head`, `db.provision_runtime --refresh-grants`, tenancy audit clean (same commands as the office slice; record paths).
- [ ] Update `docs/IMPLEMENTATION_STATUS.md`, `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md` (link), add `docs/operations/DRIVER_PORTAL.md` (roles, invite flow, mail-off behaviour, what is not claimed), acceptance table `docs/audits/2026-11-01-driver-portal-acceptance.md` marking PORTAL-01..05 with evidence and honest PARTIAL/NOT VERIFIED rows (incident reports and real email delivery out of slice).
- [ ] Dispatch one fresh read-only reviewer on the whole delivery; re-grade; one fix pass test-first; minors to ledger.
