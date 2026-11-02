# Team and access administration: acceptance report

Spec: `docs/superpowers/specs/2026-11-01-team-administration-design.md`. Uncommitted working tree; local database at `0018_team_admin`. Nothing committed, pushed, deployed or emailed.

## Evidence

| Gate | Result |
|---|---|
| Backend, whole suite | **440 passed** (25m) after the review fix pass |
| Team journey `team-admin.spec.ts` | passes on the **development** server (EN light, EL dark and phone captures read) |
| Browser, whole suite on a production build | **61 passed, 1 skipped, 0 failed** (8.6m). The skipped test is the driver-duties journey, which skips itself when the seeded service day 2026-10-31 is outside the duty window (it was, on 2026-11-02); it passed on 2026-11-01 (61 passed). Typecheck clean, lint 0 errors |
| Independent review | one fresh read-only reviewer, 14 findings (none Critical); fixed test-first except the deferred minors in the ledger |

## Goals

| # | Status | Note |
|---|---|---|
| 1 Team screen, administrators only | PASS | sidebar item and screen gated by `members.manage`; a dispatcher never sees it |
| 2 Members, role change, deactivate, reactivate | PASS | audited, idempotent, ends sessions, own row has no actions |
| 3 Invite (Driver only from a driver record) | PASS | server refuses Driver without a record and existing members |
| 4 Pending invitations, resend, revoke | PASS | list never shows a link; resend and revoke discard queued mail |
| 5 Audit and idempotency | PASS | office audit table, entity `member` / `invitation` / `driver_link` (revoke is labelled `driver_link` for all, a known minor) |
| 6 Honest delivery wording | PASS for `not_configured`; **real delivery NOT VERIFIED** | no real mail server was used |
| 7 Worker serves every organization | PASS (tests with a stubbed sender) | needs the worker database role and `--refresh-grants` |

## Limits

Real email delivery, bounces and spam placement are unverified. Phone tables scroll sideways with a pinned action column. Deferred minors are in the ledger under `Final`.
