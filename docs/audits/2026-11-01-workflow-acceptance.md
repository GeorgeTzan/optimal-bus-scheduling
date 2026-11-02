# Guided dispatcher workflow acceptance

Status: full automated gates passed; independent review in progress. This records exercised cases, not a claim that every possible action or deployment is verified. Approved spec and detailed RED/GREEN evidence are in `docs/superpowers/`.

| Page/workflow | Current evidence | Remaining acceptance |
|---|---|---|
| Invitation/login/logout | Existing registered cookie sessions, CSRF, revocation tests; Task5 identity regression | Full browser gate passed; driver-only guidance and reader Operations exercised |
| Overview | Task4 dated next-step and verifier-derived metrics browsers | Studio locale/theme/mobile exercised; Overview-specific visual inspection remains limited |
| Drivers/Fleet/stations | Existing canonical resource browsers; contextual real two-driver CSV import | Resource form warning and role-aware navigation exercised; station nested form checked |
| Timetables/date exceptions/connections | Existing canonical full CV/publication + timetable browsers | Timetable and date-exception unsaved warnings exercised; complete manual inspection of every control remains open |
| Imports | Actual reviewed atomic CSV/XLSX, correction/resumption and tenant boundaries retained | Dispatcher role defaults to authorized timetable; browser import and server isolation tests pass |
| Service day | Actual chosen-date copy remains unconfirmed, server timezone date and confirmed-crew summary | Crew copy and actual preparation exercised; exhaustive role/empty/mobile combinations remain open |
| Empty-bus travel | Six PostgreSQL contracts, actual partial/edit/reverse-copy/reload browsers | Complete-pair/source conflicts covered by PostgreSQL and browser tests |
| Scheduling Studio | Actual CV/SSE, restore, apply/manual verifier/approval/publication; four reproduced Generate failures fixed | Full browser run passed; Studio visual test covers locales, themes and narrow screens |
| Daily Operations | Seven PostgreSQL cases including publication history/concurrency;39 migration/identity/RLS/event regressions | Real published board, reader, retry/conflict, history, no-publication and desktop/mobile screenshots exercised |
| Reference archive | Explicit readonly route preserved and browser-tested in Task1 | Full browser gate passed |

No GPS provider or simulated vehicle positions. Availability/leave/maintenance, complete regulatory rule coverage, full disruption recovery, driver portal and commercial deployment remain separate phases.

Full automated gates: 282 PostgreSQL/backend tests passed in585.50s; strict TypeScript and production build passed; 42 production browser tests passed in5.3m. Screenshots include `docs/screenshots/2026-11-01/operations-desktop.png` and `operations-mobile.png`. Independent whole-working-tree review remains pending; tests do not establish full legal, availability, maintenance, driver-portal, deployment or all-controls acceptance.
