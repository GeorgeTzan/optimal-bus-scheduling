# Team and Access Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Administrators manage members, roles and invitations from a Team screen; mail delivery serves every organization and is shown honestly.

**Architecture:** Same FastAPI + Next app. New list/resend routes and a safer member PATCH in `backend/app/api/identity.py`, reusing the `once()` idempotency/audit wrapper (`office_replay`/`office_record`). One new migration adds a narrow security-definer function for the all-tenants mail worker. One new sidebar screen, `features/team`, mirroring how Office is wired.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic raw SQL, PostgreSQL RLS, pytest; Next.js 15, TypeScript, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-01-team-administration-design.md` (approved; includes builder-check answers).

## Global Constraints

- API/worker roles stay non-owner, non-BYPASSRLS; migration `0018_team_admin` (down_revision `0017_driver_portal`); after upgrade run `uv run python -m db.provision_runtime --refresh-grants`. Local DB upgrade only after a private backup (0600, `~/.local/share/ktel-db-backups/`).
- No real email is sent by any test or by this work. Real delivery stays off until the user sets `backend/.env.mail.local` (see `docs/operations/EMAIL_SETUP.md`). Tests use the outbox rows and `decrypt_payload`.
- No invitation link or token in any API response or screen.
- Nothing committed or pushed (ledger records "No commits"). Other threads' uncommitted work untouched; re-read shared files before editing.
- Service-level `issue_invitation(..., 'driver')` without a driver stays valid (tests and seed scripts use it); the Driver-needs-a-record rule is enforced on the HTTP route only.
- Ponytail: reuse `once()`, `office_replay/record`, `list_driver_links` patterns, existing `Modal`/`Field`/office CSS classes. Tag shortcuts.
- Greek and English for every string; light/dark; usable at 390px.

## Review Focus

1. Administrator demotes or deactivates the *other* administrator concurrently with the last two admins doing it to each other (Task 1 test: second request is refused, one admin remains).
2. Role change while the member is signed in: their next request fails (Task 1 test).
3. Resend for an invitation whose driver was linked or archived meanwhile (Task 2 test).
4. Invite an email that is a deactivated member of this organization (Task 2 test: 409 `member_exists`) and one that belongs to another organization (same 202 as a fresh email).
5. Mail worker sends for two organizations in one run and never reads another organization's user rows (Task 3 test).

---

### Task 1: Safer member changes

**Files:** Modify `backend/app/api/identity.py` (`MemberPatch`, `update_member`), `backend/app/domain/identity/permissions.py` only if needed. Test: `backend/tests/integration/test_team_members.py`.

**Interfaces:**
- `MemberPatch` gains `request_id: UUID | None = None` (extra still forbidden).
- `PATCH /api/v1/identity/members/{id}` rules, in this order after the existing version and last-administrator checks: signed-in member changing their own role or status → 403 `{'code':'own_membership'}`; new role `driver` and current role not `driver` → 422 `{'code':'driver_needs_record'}`; a patch that changes nothing → 200 unchanged member view, no audit, no version bump; a real change runs inside `once(db,user,request_id or uuid4(),'member','change',payload,work)` so it is replayable and audited (entity `member`, response = `member_view`). Existing behaviour kept: ends the member's sessions, clears `driver_id` when role is not driver, last-administrator 409.
- Replay payload includes `member_id` and the requested fields; reuse with different fields → 409 `request_changed`.

- [ ] **Step 1: Failing tests** in `test_team_members.py` (use `identity_setup`, `person()` from `test_office_permissions`): (a) admin changes dispatcher → viewer: 200, version bumped, one `domain_office_audit` row with entity `member`, the member's old bearer gets 401; (b) same request id and payload replays the identical response and no second audit row; changed payload → 409 `request_changed`; (c) PATCH with the same role → 200, no audit row, version unchanged; (d) own role/own deactivate → 403 `own_membership`; (e) to role `driver` → 422 `driver_needs_record`, from a linked driver to `viewer` clears the link; (f) two admins demote each other with two requests → at most one succeeds, the other 409, one active admin remains (sequential is enough: second request sees the guard); (g) deactivated member cannot sign in (401/403) and an approval route naming them is ignored by `resolve_approver_routes`; (h) non-admin 403.
- [ ] **Step 2:** `cd backend && uv run pytest -q tests/integration/test_team_members.py` → FAIL.
- [ ] **Step 3:** Implement in `update_member` (read the current function first; keep the organization row lock at the top).
- [ ] **Step 4:** Run the new file plus `tests/integration/test_identity.py tests/integration/test_office_permissions.py` → PASS. **Step 5:** Ledger line.

### Task 2: Invitation list, resend, revoke, invite rules

**Files:** Modify `backend/app/api/identity.py`, `backend/app/domain/identity/driver_links.py` (or a new `invitations.py` beside it for `list_invitations`, `resend_invitation`; revoke exists), `backend/app/domain/identity/service.py` (`issue_invitation` unchanged signature). Test: `backend/tests/integration/test_team_invitations.py`.

**Interfaces:**
- `list_invitations(db, tenant_id: int, now: datetime) -> list[dict]`: unconsumed, unrevoked invitations; expired ones only up to 30 days after `expires_at`; newest first, max 200; each `{'id','email','role','driver_id','expires_at','created_at','expired': bool,'delivery_status': str|None}` (status from the invitation's outbox row). Never a token or link.
- `GET /api/v1/identity/invitations` → `{'invitations': [...]}`; `members.manage`.
- `POST /api/v1/identity/invitations/{id}/resend` body `{request_id}`; via `once(..., 'invitation','resend', ...)`: loads the invitation (404 if not found/consumed/revoked), revokes it and sets its outbox row to `discarded` when that row is `queued` or `not_configured`, then `issue_invitation(db, tenant, email, role, driver_id)`; a driver invitation whose driver is now linked → 409 `driver_already_linked`, archived → 409 `driver_archived`; returns the same shape as the invite response.
- Revoke also sets the invitation's outbox row to `discarded` under the same condition.
- `POST /invitations`: role `driver` without `driver_id` → 422; email already a member of this organization (case-insensitive, active or deactivated) → 409 `{'code':'member_exists','message': ...reactivate or change role}`; an email belonging to another organization still returns 202.

- [ ] **Step 1: Failing tests:** list shows pending with delivery status `not_configured`, never a token (`'token' not in str(body)`); an invitation expired 31 days ago is hidden, 5 days ago shown with `expired: true`; resend → old link fails with 400, new link works, old outbox row `discarded`, list has one entry; resend refused when the driver became linked/archived; revoke discards the queued mail; role driver without record → 422; invite to an active and to a deactivated member's email (different case) → 409 `member_exists`; invite to another organization's email → 202; replay/changed payload; non-admin 403 on list and resend.
- [ ] **Step 2–4:** red → implement → run `test_team_invitations.py test_driver_links.py test_identity.py` green. **Step 5:** Ledger.

### Task 3: Mail worker for every organization

**Files:** Create `backend/alembic/versions/0018_team_admin.py`; Modify `backend/app/domain/identity/mail_worker.py`, `backend/app/domain/identity/mail.py` (a `pending_mail_tenants(db) -> list[int]` helper), `backend/db/tenant_schema.py` (worker may `EXECUTE` the new function only). Test: `backend/tests/integration/test_mail_all_tenants.py`.

**Interfaces:**
- SQL `public.ktel_mail_tenants() RETURNS SETOF integer`: `LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=off`, `SELECT DISTINCT tenant_id FROM domain_email_outbox WHERE attempts<5 AND (delivery_status='queued' OR (delivery_status='delivering' AND lease_expires_at<clock_timestamp()))`; `REVOKE ALL ... FROM PUBLIC`; execute granted to the worker role only in `grant_runtime_access` (API role not). Follow the pattern of `ktel_session_by_id` in `0003_identity.py`. Downgrade raises.
- `mail_worker`: new flag `--all-tenants` (mutually exclusive with `--tenant-id`); each pass calls `ktel_mail_tenants()` then `deliver_once(factory, tenant_id, worker_id)` per returned tenant; sleeps 1 s when nothing was delivered; `--once` still stops after one pass. Existing `--tenant-id` unchanged. `SMTP_HOST`/`SMTP_FROM` requirement unchanged.

- [ ] **Step 1: Failing test:** with `restricted_databases` and `identity_setup`, queue invitations in two organizations, monkeypatch `send_email` to record recipients and mark SMTP configured; run one `--all-tenants --once` pass (call the same function the CLI calls, with the worker role engine); both messages become `sent`, nothing for an organization without mail is touched; the worker role cannot `SELECT` from `users` or call the function with an argument; API role cannot execute the function (`ProgrammingError`); a `delivering` row with an expired lease is returned and one with a live lease is not.
- [ ] **Step 2–4:** red → write migration (preflight none) and code → green. Upgrade check: `uv run python -m db.migrations check` after the local upgrade in Task 6. **Step 5:** Ledger.

### Task 4: Team screen

**Files:** Create `frontend/src/features/team/{TeamWorkspace,MemberTable,InviteForm,InvitationList,team-api}.tsx|ts`; Modify `frontend/src/components/layout/Shell.tsx` (`ShellTab` + nav entry `{ id: "team", icon: Users, el: "Ομάδα", en: "Team" }` shown only with `members.manage`), `frontend/src/components/layout/Navbar.tsx` (names map), `frontend/src/features/navigation/workspace-location.ts` (add `"team"` to the list), `frontend/src/app/page.tsx` (render like `office`), `frontend/src/styles/globals.css` (`team-*` classes reusing `office-*` look). Test: `frontend/tests/team-admin.spec.ts`.

**Interfaces:**
- `team-api.ts`: `listMembers()`, `listInvitations()`, `changeMember(id, version, {role?|is_active?})`, `invite(email, role)`, `resend(id)`, `revoke(id)`; every mutation one stable `request_id` per attempt; error codes `own_membership`, `driver_needs_record`, `member_exists`, `last_admin`, `request_changed`, `version_conflict`, `driver_already_linked`, `driver_archived` mapped to Greek/English text.
- Role menu offers admin, dispatcher, fleet_manager, management, viewer (never driver); a driver row's role is shown read-only with "linked driver" and no role menu. Role words with one-line meanings from `PERMISSIONS` in `identity/permissions.py` (copy the meanings into the UI text; do not derive at runtime). The signed-in administrator's row shows no actions. Confirmation dialogs (use existing `Modal`) for: change to or from Administrator ("can manage everyone's access"), deactivate ("their sessions end now"), revoke. Delivery words: `not_configured` → "Queued. No email has been sent because email delivery is not set up."; `queued`/`delivering` → "Email is being sent"; `sent` → "Email sent (accepted by the mail server, not a delivery receipt)"; `failed` → "Sending failed. Check the email settings."; `discarded` → "Replaced".

- [ ] **Step 1: Failing journey** (`team-admin.spec.ts`, `customer` fixture, admin signs in): Team item visible; invite a dispatcher → appears under Pending with the "Queued…" text and no link; resend; revoke with confirmation; invite again, accept the invitation via the local outbox (`identity-seed.py mail <tenant> <email>`), reload → member listed active; change role to viewer with confirmation; deactivate then reactivate; own row has no actions; non-admin (dispatcher) never sees the Team item or `/?view=team`; Greek, dark and 390px captures reviewed by reading the images.
- [ ] **Step 2–4:** red → build → green; `npm run typecheck`, `npm run lint` (0 errors). **Step 5:** Ledger. Restart the dev server if styles look stale.

### Task 5: Docs and tests alignment

**Files:** Modify `docs/operations/IDENTITY_AND_ACCESS.md` (members and invitations via screen; worker `--all-tenants`; statuses), `docs/operations/EMAIL_SETUP.md` (worker section now true; Resend after enabling), `docs/IMPLEMENTATION_STATUS.md`; Create `docs/audits/2026-11-01-team-admin-acceptance.md`; Modify `frontend/tests/import-permission-default.spec.ts` or others only if a changed rule breaks them.

- [ ] Run the identity, driver and office backend tests together plus the three new files; fix expectation changes (Driver-role API rule) with a ledger Ruling each. Write the acceptance table (each Goal 1–7 with evidence, PARTIAL/NOT VERIFIED rows honest: real delivery not verified, bounce handling absent).

### Task 6: Gates and final review

- [ ] Back up the local DB privately, `uv run python -m db.migrations upgrade`, `uv run python -m db.provision_runtime --refresh-grants`, `uv run python -m db.migrations check`, tenancy audit as before.
- [ ] Full `cd backend && uv run pytest -q`; stop the dev server, `npm run build`, serve it, full `npx playwright test`; restart the dev server for the user.
- [ ] One fresh read-only reviewer on the whole delivery (opus); re-grade; one fix pass test-first; minors to the ledger; final report lists every `Ruling:` and deferred minor.
