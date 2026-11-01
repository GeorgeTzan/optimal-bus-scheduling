# Driver portal, first slice: design

Status: draft for approval. Scope source: PORTAL-01..05 in `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md`. Follows `2026-11-01-office-availability-maintenance-design.md`.

## Intent

Office stops adding logins by hand. Driver signs in on a phone, sees own published duties, requests leave, acknowledges an exact duty version. Identity always comes from the session.

## Goals

1. Office invites a driver from an existing driver record. Accepting the invitation links the login to that driver.
2. Office sees invitation state (pending, accepted, expired) per driver and can revoke an invitation, unlink a login, or re-link (new phone or email).
3. Driver area `/driver`: My duties (read only), Leave (request, list, cancel pending), Acknowledge (per duty and version).
4. Phone-first, Greek/English, light/dark, clear empty, error, offline and expired-session states.

## Non-goals

Incident reports (second slice). Pushing or emailing duties. Offline queues or offline success. Driver editing own working time. Bus-owner portal. Any real email send (stays off until the user authorizes it).

## Anti-goals

A driver ever seeing a draft, another driver's data, or office screens. An acknowledgment that outlives a changed publication. A caller-supplied driver id accepted anywhere under `/api/v1/driver`. Auto-creating a driver record from a sign-in.

## Constraints

- API and worker DB roles stay non-owner, non-BYPASSRLS. New tables: RLS, FORCE RLS, composite tenant keys, explicit grants, migration `0017`, `provision_runtime --refresh-grants`.
- No external email. Invitation uses the existing outbox and shows its delivery status.
- Nothing committed or pushed until the user directs it.
- Ponytail: reuse `Membership.driver_id`, `IdentityToken`, office leave service, `domain_office_audit` replay pattern. No new framework.

## Approaches

- **A. Separate driver area in the same Next app, `/api/v1/driver/*` endpoints (chosen by user).** Small layout, session-derived driver, small testable permission set. Cost: a second layout.
- B. Reuse the office shell, hide tabs by role. Rejected: one missed check leaks data; awkward on phones.
- C. Separate mobile app. Rejected: second deployment; offline claims forbidden without a real mechanism.

## Decisions

- **Invite.** `POST /api/v1/identity/invitations` gains optional `driver_id`, allowed only with role `driver`, requires `members.manage`. The token row stores `driver_id` (composite FK to drivers). Accepting sets `Membership.driver_id`. One active login per driver and one driver per login: a second link is refused with a clear 409 naming the state, never a silent replace.
- **Unlink and re-link.** Admin action sets `driver_id` to null (existing role-change code already clears it), revokes the member's sessions, and audits who did it. Re-link is a new invitation. Old acknowledgments stay attached to the driver, not the login.
- **Driver identity.** Every `/api/v1/driver/*` route requires a new dependency `current_driver`: role `driver`, active membership, `driver_id` not null, driver not archived. Else 403 with a message that says to ask the office to link the account. Permissions: `driver.self.read`, `driver.self.acknowledge`, plus new `driver.self.leave`. No driver permission appears on any office route.
- **My duties.** Derived read-only from the currently published revision per date, for today minus 1 through today plus 14, in the organization timezone: assignments of crews whose `driver_id` is the session driver. Fields: date, local start and end with zone, route and station names, vehicle label, publication id, revision version, cancelled flag, `acknowledged` for that exact (publication, trip, version). Never drafts, never other drivers, never office notes.
- **Acknowledge.** `POST /api/v1/driver/acknowledgments` with `{publication_id, trip_id, request_id}`. Server checks the publication is the current one for that date and the trip is the session driver's, then inserts one row (publication, revision version, trip, driver, time, request id). Insert-only for the API role (like the office audit table), unique on (tenant, publication, trip, driver). A newer publication produces new rows; old rows never count for it. Opening a page never writes. Replay with the same request id returns the same result; a different payload with the same id is 409.
- **Leave.** Driver endpoints wrap the existing office leave service with `driver_id` forced from the session; categories limited to what the office form allows; private notes visible to the owning driver for own requests only. Status shown is the real record. Driver can cancel own pending request only. Own approval stays blocked by the existing own-leave rule.
- **Office UI.** On each driver record: Invite to sign in (email, shows status), pending list with revoke, linked account with Unlink. Needs `members.manage`. Invite result shows delivery status honestly; copy says no email has been sent while delivery is off.
- **Driver UI.** Route `/driver` (and Greek/English toggle, theme). Signed-in `driver` role lands there; other roles never see it. Three views with large touch targets. Session expiry shows a sign-in prompt, not stale data. Offline shows "No connection" and never claims success.

## Left to the builder

Table and column names beyond those above, exact response shapes, cards vs list layout, copy text (Greek and English), test fixtures, and how to schedule the revocation cleanup.

## Acceptance checks

Backend: driver sees only own published duties and no draft; caller-supplied driver ids ignored or rejected; acknowledgment of an old publication does not count for a new one; unlink revokes sessions and blocks `/driver/*`; second link refused; replay and changed-payload 409; RLS and grants audit clean; unlinked or archived driver gets the clear 403.
Browser: invite from a driver record, accept, sign in on a phone viewport, see duties, acknowledge, request leave, office approves, status updates after reload; Greek and dark captures reviewed; expired session state.

## Builder-check answers (calls marked "my call" are the author's, open to change)

- **Duty = one trip assignment.** Acknowledgment rows are per (publication, trip, driver). The day view offers "Acknowledge all" which writes one row per trip in one request. A cancelled trip can be acknowledged (the driver confirms they saw the cancellation). My call.
- **Publication vs revision.** Each publish creates a new `Publication` (unique id, bound to exactly one revision). A change is a new revision and a new publication, so an acknowledgment keyed to the publication id is also keyed to one revision version. Store both.
- **Accepting an invitation** always creates a new account for the invited email (existing behaviour; an existing email is a 409). The token is bound to the invited email. My call: no change.
- **One login per driver.** Partial unique index on memberships (tenant, driver_id) where driver_id is not null. A pending invitation also occupies the driver: partial unique index on invitation tokens (tenant, driver_id) where unconsumed and not revoked. A second invite or link is a 409 that names the state. My call.
- **Leave.** The office service has cancel and uses the leave categories already defined; a driver may cancel only their own pending request, which needs a small ownership-checked path because today pending-cancel requires `availability.manage`. Categories: the same list as the office form. My call.
- **Archived driver.** `current_driver` returns 403 on every request; sessions are not revoked; office list shows "linked to an archived driver". My call.
- **Sign-in and sessions.** Password sign-in and per-member session revocation already exist; the driver lands on `/driver` after sign-in by role.
- **Timezone.** `KTEL.timezone` is per organization; the window (yesterday to +14 days) is fixed in the first slice.

## Decided by the user

Invitation delivery: **email through the existing mail worker** (user chose, 2026-11-01). The accept link is never shown in the office UI. While real email is not authorized, invitations stay queued with an honest "not sent" status; browser and backend tests read the local mail capture (outbox row) instead. Turning on real delivery needs the user's explicit authorization and is not part of this slice.
