# Driver portal (first slice)

Design: `docs/superpowers/specs/2026-11-01-driver-portal-design.md`. Requirements: PORTAL-01…05 in `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md`. Incident reports are the second slice and are not built.

## How a driver gets access

1. The office adds the driver as a normal driver record (form or spreadsheet import).
2. An administrator (`members.manage`) opens the driver record → **Driver sign-in** → enters the driver's email → **Invite to sign in**. The invitation names that exact driver record.
3. The invitation is queued as email. **Real email is not enabled**: the status reads "Queued. No email has been sent because email delivery is not set up." The accept link exists only inside the email; no screen or API response shows it. Until delivery is authorized and configured, the link can only be read from the local mail outbox by an operator.
4. The driver opens the link, sets a password, and is linked to that driver record. The sign-in always lands on `/driver`.
5. Unlink (with confirmation) ends all of that login's sessions immediately. To link again, send a new invitation. If the email already belongs to an unlinked driver login of the same organization, accepting the new invitation links it again and sets the password the person chooses (the link proves the mailbox, as a password reset does) and ends its old sessions. A different email creates a new login.

Rules enforced by the database and server: one login per driver; one pending invitation per driver (revoke it to send another); an archived driver cannot be invited, and an invitation cannot be accepted after its driver was archived; an existing account email that is not an unlinked driver login of this organization cannot accept a driver invitation (409, nothing linked); the driver is never taken from request data.

## What a driver sees and does

| Area | Behaviour |
|---|---|
| My duties | Own trips from the **current published** schedule for yesterday through 14 days ahead, in the organization time zone. Drafts, other drivers and office notes never appear. A cancelled trip is shown as cancelled to the driver it was last published for; a trip already taken off a driver in a published version gives that driver no notice, and unpublished drafts never count. |
| Acknowledge | One button per trip, plus "Acknowledge all". It records the exact publication, version, trip, driver and time. Opening the page records nothing. A republished day shows the trips as not acknowledged again, and an old publication is refused (`publication_replaced`). Acknowledgment rows cannot be changed or deleted by the application role. |
| Leave | Request leave (annual, sick, unpaid, other) and see the real status after reload. It goes through the same approval routes as office-entered leave; a driver cannot decide any leave. A driver can cancel only their own request that is still waiting. |

Offline: actions fail with "No connection. Nothing was saved." Expired or revoked session: the driver is returned to the sign-in screen. There is no offline queue and no offline success.

## Not claimed

Delivered email, push messages or SMS; incident reports; a history or comparison of what changed between publications; legal rest or driving-time compliance; that the person who accepted an invitation is the intended driver beyond control of the invited mailbox; a full keyboard and screen-reader audit.

## Operating notes

- Migration `0017_driver_portal`; after upgrading run `uv run python -m db.provision_runtime --refresh-grants`. The application role has SELECT and INSERT only on `domain_driver_acknowledgments`.
- Browser journey `tests/driver-portal.spec.ts` needs the seeded service day (2026-10-31) to fall inside the duty window, so it skips itself after 2026-11-14.
