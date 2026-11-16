# Platform operator panel

The operator panel at `/platform` is how the platform provider onboards and looks after customers (KTEL organizations): customer list, subscription state, suspension, a per-customer health view and consented read-only support access. Operators are separate from customer users. They have their own accounts, their own database role, their own cookies and their own audit trail. Customers see what support did in their organization.

The customer API role can read only these `ktels` columns: `id`, `name`, `region`, `timezone`, `status`, `created_at`, `support_access_until` (and update `support_access_until`). It cannot read `plan_note` or `trial_ends_on`, and a refresh removes any hand-granted execute right on the panel functions.

Revisions: `0024` operator tables and audit, `0025` customers and suspension, `0026` health, `0027` support sessions, `0029` health ignores non-operational publications, `0028` hardening: a check that an outbox message without an identity token must be of kind `support_session`. Migration `0028` deletes any pre-existing tokenless outbox message of another kind before validating the check (none are created by the application), and the mail worker discards such rows. Panel code is under `backend/app/api/platform.py` and `backend/app/domain/platform/`, the screens under `frontend/src/features/platform/`.

## One-time set-up per environment

### 1. The `ktel_platform` database role

The panel never uses the customer API role and never reads customer tables directly. It connects as its own role, `ktel_platform`, which can only use the `platform_*` tables and a small set of `SECURITY DEFINER` functions (customer list and updates, health, support start/end). Create it once per environment, after migrations have been applied, with the privileged connection (`DATABASE_MIGRATION_URL`, or `DATABASE_URL` in development):

```sh
cd backend
uv run python -m db.provision_runtime --create-platform-role
```

This creates the role with a random password, writes `DATABASE_PLATFORM_URL=...` to the git-ignored file `backend/.env.platform.local` (mode 0600, created exclusively, never printed) and refuses to run if the role already exists. Another location can be chosen with `--platform-output PATH`, another role name with `--platform-role NAME`. The file is read by `config.py` next to `.env.runtime.local`.

In a deployment, set `DATABASE_PLATFORM_URL` as an environment secret of the backend, like `DATABASE_RUNTIME_URL`. In the production compose file the backend reads `secrets/app.env` and `secrets/runtime.env`; add the line there (mode 0600) and delete any temporary output file. The production containers have a read-only filesystem, so write the output file to a private mounted directory or run the command from a one-off checkout that has `DATABASE_MIGRATION_URL`, and rehearse this once before the real rollout (this procedure is documented but not rehearsed). Never paste the URL into chat, tickets or logs.

If `DATABASE_PLATFORM_URL` is not set it falls back to `DATABASE_URL`, the privileged owner connection. That is tolerated in development only. When `ENVIRONMENT=production`, API startup (the lifespan hook, `validate_platform_settings` in `config.py`) fails with `DATABASE_PLATFORM_URL must be set to the separate ktel_platform role in production.` if it is unset or equal to `DATABASE_URL`. Only the API refuses; migrations, `db.provision_runtime`, the solver worker and the mail worker are not affected.

First rollout of this feature to an existing production environment, the no-outage order: run `scripts/deploy.sh` once. It builds, migrates and refreshes grants, then its pre-flight stops before `up -d` because `DATABASE_PLATFORM_URL` is missing from `secrets/*.env` or the database has no `ktel_platform` role. The old containers keep running. Then create the role and put its URL into the secrets (the role needs the panel tables, so it can only be created after the migration), and run `scripts/deploy.sh` again. The outage path is to skip the pre-flight reasoning and start the new API without the variable: it refuses to start (see below) and customers are down until the role exists.

Guards that make a missed step loud:

- `scripts/deploy.sh` pre-flight, after migrate and `--refresh-grants` and before `up -d`: aborts when `DATABASE_PLATFORM_URL` is absent from the secrets env files or `pg_roles` has no `ktel_platform`.
- API startup (all environments): refuses to start with an explicit error when the runtime role lacks the support grants (`ktel_support_request` execute, column read on `platform_support_sessions`), which means `--refresh-grants` was skipped after migration `0027`.
- API startup (production): the panel connection must pass the same least-privilege check as the API role (not superuser, no BYPASSRLS, owns no tables, cannot create in `public`), in addition to `DATABASE_PLATFORM_URL` differing from `DATABASE_URL`.

The production-container procedure for `--create-platform-role` (read-only filesystem, one-off container) is documented here but has NOT been rehearsed. Rehearse it on a copy before relying on it.

### 2. Deploy order and grants

Every deployment that includes a migration must do these steps in this order. `scripts/deploy.sh` already does it (migrate, `--refresh-grants`, then `up -d`), so it needs no change for the panel:

```sh
uv run python -m db.migrations upgrade
uv run python -m db.provision_runtime --refresh-grants
```

then restart the API, workers and mail worker.

`--refresh-grants` also refreshes the `ktel_platform` grants, but only if the role already exists. It never creates it.

Warning: after migration `0027` the tenant API role needs a column grant on `platform_support_sessions` and execute rights on `ktel_support_request` and `ktel_end_support_sessions`, and `/auth/me` reads them. If the migration is applied but `--refresh-grants` is skipped, `/auth/me` fails for every tenant user, so nobody can use the application. Never restart the API on a new revision without refreshing grants.

### 3. The first operator and TOTP enrolment

Operators sign in with email, password and a 6-digit TOTP code (RFC 6238, SHA-1, 6 digits, 30 seconds, one step of drift accepted). There is no self-registration. Create the first operator on the server with the privileged connection:

```sh
cd backend
uv run python -m app.cli.platform_operator create --email operator@example.org
```

It asks twice for a password (at least 12 characters, not echoed), then prints the TOTP secret and the `otpauth://` URI once. Enter the secret in an authenticator app straight away (scan the URI as a QR code on a trusted machine, or type the secret). The secret is stored in the database and cannot be shown again; Never paste the password, the secret or the URI into chat, tickets, email or shell history. A duplicate email is refused without printing a secret. To reset an operator's authenticator device, create a new operator with a different email (a duplicate email is refused) and deactivate the old one.

In production run it in an interactive one-off container, for example `docker compose -f docker-compose.prod.yml -p ktel run --rm --no-deps backend python -m app.cli.platform_operator create --email operator@example.org` (the command needs a terminal for the password prompt and the privileged `DATABASE_MIGRATION_URL`).

## Signing in

Open `/platform`. Sign in with email, password and the current 6-digit code.

- A code can be used once. Reusing a code, even from another browser, is refused.
- Sign-in attempts are limited per email and address (`AUTH_LOGIN_LIMIT`, 5 per 15 minutes in production). Code guesses are also capped at 10 per operator per 15 minutes across all addresses. A refused attempt looks the same as a wrong password. Throttled attempts are audited.
- The session lasts 60 minutes of inactivity; each request slides the limit. There is no separate absolute cap. Sign out ends it.
- Cookies: `ktel_platform_session` (HttpOnly, SameSite=Strict, Secure in production, `Path=/api/v1/platform`, a browser-session cookie) and `ktel_platform_csrf` (readable by the page, `Path=/platform`); writes require the matching `X-CSRF-Token` header. Panel routes ignore the customer cookie and bearer tokens, and customer routes ignore the panel cookies.
- The browser origin must be trusted (`ALLOWED_ORIGINS`), as for customer sign-in.

## Customers, status and suspension

**New customer** takes a name, region, time zone, first administrator email, status (trial or active) and, for a trial, its end date. It creates the organization, an invitation for the first administrator (48 hours) and a queued invitation email in one database step. The invitation link is shown once in the panel; only its hash is stored. If email is not configured the message is marked `not_configured` and the operator must give the link to the customer by another channel (see `EMAIL_SETUP.md`). A duplicate name gives 409, an unknown time zone 422, a blank name 422.

Statuses: `trial`, `active`, `suspended`, `cancelled`. Trial and plan notes are informational: a trial that has ended only shows a warning chip, nothing is blocked automatically. Edit status, trial end, region and plan note under **Manage**. Organizations cannot be deleted from the panel.

Suspension (and cancellation, which behaves the same) does exactly this:

- Every live session of the organization is revoked at once.
- Sign-in is refused with a clear message, after the password has been checked (a wrong password still gets the ordinary error, so status is not disclosed).
- Any session that is still presented is refused (403 `organization_suspended`), including bearer tokens and the driver portal.
- The solver worker does not claim new jobs; a job already running finishes.
- Support sessions of the organization end.
- Invitation acceptance is refused, and password-reset requests and confirmations behave as for an unknown address (no mail, no change).
- No data is deleted. Reactivating (back to trial or active) allows sign-in again; users have to sign in again.

## Health view

Per customer, from one function that reads only counts and dates (never names, email addresses or schedule content):

- Last sign-in: latest session creation. Never signed in is highlighted.
- Drivers, vehicles, timetables: rows not marked inactive.
- Published days (30 days): distinct dates on which a schedule was published in the last 30 days.
- Solver failures (7 days): jobs with status `failed` whose update time (or creation time if never updated) is in the last 7 days.
- Mail failures (7 days): outbox messages with delivery status `failed` created in the last 7 days. The outbox has no failure timestamp, so this uses the time the message was queued, not the time it failed.
- Uncovered share: for the schedule of the latest operational publication (reference or fixture publications are ignored; revision `0029`), assignments not cancelled whose resource is `UNASSIGNED`, divided by all non-cancelled assignments, rounded to four places. Empty when nothing has been published or there are no such assignments. This is the same notion as the coverage report.

Chips: red for solver or mail failures or an uncovered share above 25 %, amber for never signed in or no sign-in for 14 days, otherwise Healthy; a customer whose health could not be loaded shows a dash, not Healthy. Reading health is not audited.

## Support access

Support is possible only with the customer's consent, read-only, time limited and visible to the customer.

1. A customer administrator opens **Team**, **Support access** and chooses to allow it. That opens a window of 24 hours (allowing again extends it). Revoking closes the window at once and ends any running support session.
2. The operator opens the customer in the panel, enters a reason (required) and optionally a ticket reference, and starts a session. Without an open window the panel refuses (403 `support_access_not_enabled`).
3. A support session lasts at most 60 minutes and never beyond the consent window. A new session by the same operator ends the previous one. Panel sign-out, operator deactivation, suspension and consent revocation each end it at the next request.
4. The operator uses **Open customer app**, which opens `/` with the cookie `ktel_support_session` (HttpOnly, SameSite=Strict, `Path=/`, Secure in production, `Max-Age` up to the end). Use a browser profile that is not signed in as a customer: a customer cookie takes precedence over the support cookie. The panel session is untouched.
5. Every page shows the banner "Platform support is viewing this organization, read-only, until ...". It hides itself after the end time and the app re-reads `/auth/me` every 60 seconds while it is shown.
6. Customer administrators receive an email (reason and end time, bilingual). Sending it is best effort: if it cannot be queued the session still starts and the panel shows the mail status (`queued`, `not_configured`, `no_recipients`, `failed`).

What support can do: read resources, imports (without raw downloads), schedules, optimization results and reports on screen of that organization. What it cannot do: change anything (every non-read request is refused with 403 `support_read_only` before any handler runs, and the database transaction is set to read only), export reports, download raw import files or open the event stream (403 `support_not_available`), manage members, invitations or support access, or sign in as a user. It is not a member of the organization, never appears in member lists and holds no office grants, so some office screens show no access. Tenant isolation is the same row-level security as for any customer user.

What is audited, always in an append-only table that the panel can only insert into: operator sign-in, failed sign-in (with a keyed hash of an unknown address, never the address), throttled sign-in, sign-out, customer created, updated, suspended, cancelled, reactivated or status changed, support session started (reason, ticket, end time, address), support session ended (by operator, customer, suspension, logout or replacement) and every request made with a support cookie (method and path, up to 16 and 500 characters, including refused writes). Customers see this list in Team: action, reason, ticket, method, path and time, newest first (the latest 200 start/end/change rows plus the latest 200 request rows). It never shows operator names, addresses or plan notes.

Known audit limits:

- The support console polls job status every 4 seconds (the event stream is refused), and each poll is one audited request. An open job page writes about 900 audit rows per hour of support session (4 s polling). In addition the banner re-reads `/auth/me` every 60 seconds while it is shown, about 60 more rows per hour in a support tab. Expect this when reading the list.
- Public GET requests that do not authenticate (for example static or health requests) under a support cookie are not audited, because no tenant route resolves the session.
- Expiry does not write a "ended" row. The start row records `ends_at`, and the customer list shows it.

## Trusted proxy and client address

Rate limits and audit addresses use the connection address (`request.client.host`). Behind the Next.js proxy and any front proxy that address is the proxy's, so all audit rows show the same address and the per-address limit is shared by all callers. Before exposing the panel, configure a deliberate forwarded-header policy: run uvicorn with `--proxy-headers` and `--forwarded-allow-ips` set to the addresses of your trusted proxy only (never `*` on a network that reaches the container directly), and make the front proxy overwrite, not append, the client address header. Until then treat audit addresses and address-based limits as unreliable. The email-keyed and operator-keyed limits still work.

## Known follow-ups

- Operator management (list, deactivate, reset a device, password change) has no screen; it is database or CLI work.
- The production-container role set-up is documented but not rehearsed, and manual; `scripts/deploy.sh` does not create the role.
- Trial end and plan notes are informational; there is no billing, reminder or automatic suspension.
- Mid-session `organization_suspended`, `support_read_only` and `support_not_available` are mapped to Greek and English text in the shared timetable and resource helper, the office calls and the panel. The import and report dialogs still show their generic 403 text.
- Operator TOTP secrets are stored in plain text in `platform_operators`; encrypt them at rest.
- The panel role has table-wide grants on `platform_operators` and `platform_sessions`; narrow them to the columns and statements actually used.
- Support banner colours are not tuned for dark mode.
- The audit email hash is keyed with `SECRET_KEY`; rotating it breaks correlation with older rows.
- Health uses queued time for mail failures; a failure timestamp would be more accurate.
- The health list scans all customers on each load, fine for tens of customers.
- The dev panel runs as the owner connection unless `backend/.env.platform.local` exists, so the least-privilege path is exercised for real only in tests and in deployments with the role.
- `frontend/tests/session-isolation.spec.ts` test 1 fails since commit `2af30ec` (the schedule load now treats only 204 as no revision, the test mocks 404). Unrelated to the panel, not fixed here.

## GDPR note

Operating the panel means the platform provider processes customers' personal data (drivers, users, schedules) on their behalf, and support access is a controlled form of that. The processor wording (Articles 28, 29 and 32: contract terms, processing only on instruction, security measures) in customer agreements and the privacy documents must be confirmed by counsel before the first paying customer. The sources used while designing the consent, audit and retention behaviour were vendor blogs and general guidance, not legal advice or regulator texts. Retention of the audit table is not yet defined.

## Verification

As of 2026-11-16 on branch `feat/platform-operator-panel`:

- Backend: `cd backend && PYTHONPATH=. uv run pytest -q` gave 746 passed in 36 minutes (migrations through `0029_platform_health_operational`).
- Playwright: `work-rules.spec.ts` (17), `platform.spec.ts` (2) and `support-codes.spec.ts` (1) gave 20 passed before the last fix wave; after it `platform.spec.ts`, `platform-health-flags.spec.ts` and `support-codes.spec.ts` gave 4 passed. `work-rules.spec.ts` "baseline times follow the tenant timezone" timed out once in a combined run right after a fresh server start and passed when rerun alone and in the full spec; treat it as flaky.
- `session-isolation.spec.ts` test 1 fails as described under known follow-ups (404 vs 204 since commit `2af30ec`); test 2 passes. It is unrelated to the panel.
- The production-container `--create-platform-role` procedure is not rehearsed. `scripts/deploy.sh` was checked with `bash -n` and by reading only; it was not run.
- `tsc --noEmit` is clean and eslint reports no errors on the changed frontend files.
