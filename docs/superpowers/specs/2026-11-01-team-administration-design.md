# Team and access administration: design

Status: draft for approval. Follows `2026-11-01-driver-portal-design.md` (driver invitations, links) and `docs/operations/EMAIL_SETUP.md` (real email is configured by the user later).

## Intent

A customer's administrator manages who can sign in and in which role, without the API: invite staff, change roles, deactivate and reactivate people, and see, revoke and resend pending invitations. The server already enforces most safety rules; the missing parts are the screen, a few server additions and an honest delivery state.

## Goals

1. Team screen (administrators only, `members.manage`) in the sidebar.
2. Members table: name, email, role (plain words plus a one-line meaning), active or deactivated, linked driver. Actions: change role, deactivate, reactivate.
3. Invite a person: email + role. Role Driver is not offered here; the screen points to the driver record (driver logins must be tied to a real driver, see the driver portal design).
4. Pending invitations: email, role, driver if any, expiry, delivery status; Revoke and Resend (resend replaces the old link).
5. Every role change, status change, invitation, revoke and resend is recorded with the actor in the existing office audit table and is idempotent (`request_id`), like the office and driver actions.
6. Delivery is honest: statuses `not_configured`, `queued`, `delivering`, `sent`, `failed`, `discarded` are shown in words; `failed` says to check email settings.
7. The mail worker serves every organization, not one.

## Non-goals

Custom roles or permission editors (six fixed roles stay; office grants stay in Office → Access). Audit-log viewer. Login history or "last signed in". Forced password reset by an administrator. SSO. Bounce handling. Editing a person's name or email. Showing an invitation link on screen.

## Anti-goals

An administrator being able to lock the organization out (last administrator removed, or self-demotion by mistake). An invitation link visible to any administrator. A screen that says "sent" when only queued. Any role change that leaves the person's old sessions alive. A deactivated member still counting as a leave approver.

## Decided by the user

- Any administrator may make other people administrators (no single owner). The safeguard is traceability: audit record plus a confirmation that names the effect.
- Separate Team screen on the existing identity routes (approach A). Not folded into Office, no admin console.
- Real email delivery will be set up by the user with a provider chosen later; the screen must work with and without it.

## My calls (author's, open to change)

- You cannot change your own role or deactivate yourself from the screen (the row shows no actions for the signed-in administrator). The server keeps its last-administrator guard as the second line.
- Confirmations: role change to or from Administrator, deactivate, and revoke each ask for confirmation naming the effect ("their sessions end now").
- No second-person approval for promoting an administrator.
- Invitations to an email that already has an account in this organization are refused with a clear message pointing to role change or reactivation; an email that belongs to another organization is refused without saying so (no leaking of other organizations).

## Existing behaviour to reuse

`GET /api/v1/identity/members`; `PATCH /members/{id}` (role, active, version check, last-administrator guard, ends sessions, clears driver link when role is not driver); `POST /invitations` (role, optional driver, `request_id`, replaces earlier unused invitations for the same email, audited via `office_record`); `POST /invitations/{id}/revoke`; `domain_email_outbox` delivery states; leave approval routes already ignore inactive members.

## Server additions

- `GET /api/v1/identity/invitations`: unconsumed, unrevoked invitations of the organization (expired ones for 30 days after expiry) with id, email, role, driver_id, expires_at, created_at, delivery_status (from the outbox row), `expired` flag. Bounded (≤200, newest first).
- `POST /api/v1/identity/invitations/{id}/resend`: `request_id`; revokes the old invitation and issues a new one with the same email, role and driver; refused if the driver became linked or archived.
- `PATCH /members/{id}` gains optional `request_id` for replay and writes an audit record; refuses the signed-in member changing their own role or status (403 `own_membership`).
- Mail worker `--all-tenants` mode: loops over organizations that have deliverable mail. The worker database role cannot read user or organization data today, so the list of organizations comes from a narrowly privileged function that returns only organization ids having queued mail (same pattern as the other narrowed identity functions). Per-tenant `--tenant-id` stays working.
- Role Driver on `POST /invitations` without `driver_id` is refused (422) so a driver login is never created unlinked from the Team screen. (Existing tests that invite role driver without a driver must be adjusted.)

## Screen behaviour

Members and invitations load together; stale responses are ignored; a failed action keeps the table and shows the server's message; actions show a busy state and use one `request_id` per attempt. Greek and English, light and dark, usable at 390px (table scrolls with the action column pinned, like Office). Empty states: only you in the team; no pending invitations.

## Acceptance checks

Backend: role change ends sessions and is audited and idempotent; self role change and self deactivate refused; last administrator guard still holds; promoting to administrator and demoting work; deactivated member cannot sign in and drops out of approval routes; invite list shows delivery status and never a token; resend replaces the old link (old link fails); resend refused for linked or archived driver; invite for existing email in the same organization refused; other-organization email gives no information; invitation of role Driver without driver refused; all-tenants worker sends mail for two organizations and never reads another organization's user data; non-administrators get 403 on every route.
Browser: administrator invites a dispatcher (queued state), sees it pending, resends, revokes, accepts one from the local outbox, changes role with confirmation, deactivates and reactivates; own row has no actions; Greek, dark and phone captures reviewed.

## Builder-check answers (calls marked "my call" are the author's)

1. **Sessions.** Every request, including ones with an already-issued access token, is checked against the stored session (`session_lookup`, the token carries the session id). Revoking the stored sessions of the member therefore ends access on their next request; no denylist or per-member version is needed. "Their sessions end now" is literally true.
2. **Mail worker tenancy.** The database uses shared tables with row-level security and a `tenant_id` column, not a schema per organization (`db/tenant_schema.py` is about grants and policies). `domain_email_outbox` is one table. The new function is a security-definer SQL function returning `SELECT DISTINCT tenant_id` from `domain_email_outbox` where the status is `queued`, or `delivering` with an expired lease (a crashed worker's rows), and attempts are below the retry limit. It returns only ids. It needs a migration only, no trigger or marker column. My call.
3. **`not_configured`.** Set by the API at enqueue time (`enqueue_identity_email`) when SMTP is absent, so the screen shows it without a worker. Rows marked `not_configured` are never delivered later; after real email is enabled the office uses Resend, which creates a new queued message. `discarded` is already produced by the worker for expired or consumed invitations, and now also by Resend and Revoke for the superseded row.
4. **Resend.** Creates a new invitation and outbox row and marks the old invitation revoked and its outbox row `discarded` when it is `queued` or `not_configured` (a row already `delivering` or `sent` is left as it is). The old link can never be delivered after a resend. Expired invitations can be resent.
5. **PATCH replay and audit.** `request_id` is optional on the server (existing callers keep working; without it a fresh id is generated) and always sent by the Team screen. Replay is keyed by organization and request id with the actor in the payload hash (same helper as the other routes). A call that changes nothing writes no audit record and returns the member unchanged. Every real change writes one. My call.
6. **Role Driver on PATCH.** The Team screen's role menu does not offer Driver. The server refuses changing a member to Driver (422 `driver_needs_record`): a driver login is created only by an invitation that names a driver record. Changing a driver to another role is allowed and clears the link (existing behaviour). Existing tests that PATCH to Driver or invite Driver without a record are adjusted. My call.
7. **Existing email.** Matching uses the same case-insensitive lookup as sign-in. An email that is already a member of this organization, active or deactivated, is refused at invitation time with 409 `member_exists` and a hint (reactivate or change role). An email that belongs to another organization gets the same 202 as a new email; the refusal happens when the link is accepted ("an account already exists"), as today, so nothing about other organizations leaks. My call.
8. **Expired invitations.** Shown with an `expired` flag until revoked or resent, for 30 days after expiry, then hidden from the list (still in the database). They count toward the 200 cap only within that window. Empty state is shown when the list is empty. My call.
