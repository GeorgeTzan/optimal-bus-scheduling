# Driver portal (first slice): acceptance report

Scope: `docs/superpowers/specs/2026-11-01-driver-portal-design.md`; requirements PORTAL-01…05. Revision: uncommitted working tree on `feat/v2-ktel-platform` (HEAD `a81aced`) with other threads' changes. Local database at `0017_driver_portal`. Nothing was committed, pushed, deployed or emailed.

## Evidence

| Gate | Result |
|---|---|
| Backend, whole suite (`cd backend && uv run pytest -q`) | **423 passed** in 22m (an earlier run had one solver timing test fail under machine load; it passes alone and in this run) |
| Browser, whole suite on a production build | **61 passed** in 8.3m |
| Typecheck, lint | clean, 0 errors |
| Independent review | one fresh read-only reviewer on the whole delivery, 9 findings, fixed test-first in one pass except one noted limit (see ledger `Final`) |

## Requirements

| ID | Status | Evidence and limits |
|---|---|---|
| PORTAL-01 | PASS | Linking happens only through an invitation that names an existing driver record; one login and one pending invitation per driver are database constraints; the driver always comes from the session. Tests: `test_driver_links.py`, `test_driver_portal_schema.py`, `test_driver_duties.py` (a supplied `driver_id` is ignored), journey `driver-invite.spec.ts`. Re-linking an unlinked login to the same email works and sets a new password. |
| PORTAL-02 | PARTIAL | Own current published duties for yesterday through 14 days ahead, no drafts, no other drivers (`test_driver_duties.py`). Cancelled trips are shown to the driver they were last published for. Not built: a view of what changed between publications. |
| PORTAL-03 | PARTIAL | Leave requests, status after reload, cancel own waiting request, decided through the existing approval routes (`test_driver_leave.py`, `driver-portal.spec.ts`). Incident reports are not built (second slice). |
| PORTAL-04 | PASS | Acknowledgment names the exact publication, version, trip, driver and time; a republished day needs a new one and an old publication is refused; opening a page writes nothing; the application role cannot update or delete rows (`test_driver_acks.py`). Per trip only; there is no whole-change acknowledgment. |
| PORTAL-05 | PARTIAL | 390px layout, offline refusal that saves nothing, session end after unlink, sign-out and sign-in as another driver, Greek/English and light/dark captures were inspected. Not done: a full keyboard and screen-reader audit; some leave validation errors appear in English in the Greek interface. |

## Limits and honest notes

1. **Real email is not enabled.** Invitations are queued; the accept link exists only in the (local) outbox. Delivery has never been verified against a real mail server.
2. The browser journey depends on the seeded day 2026-10-31 being inside the duty window and skips itself after 2026-11-14.
3. One review fix (sign-out and sign-in as another driver) has a passing journey, but I could not show it failing against the old code.
4. Re-linking by accepting a new invitation lets whoever can read that mailbox set the login's password, as a password reset already does.
5. Not claimed: delivered notifications, legal rest or driving-hour compliance, offline operation, that the accepter is the intended person beyond the invited mailbox.
