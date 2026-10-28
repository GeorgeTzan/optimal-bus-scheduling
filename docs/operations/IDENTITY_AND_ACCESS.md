# Organization access and identity delivery

Run database migrations and refresh runtime grants before upgrading API/worker processes:

```sh
cd backend
uv run python -m db.migrations upgrade
uv run python -m db.provision_runtime --refresh-grants
```

Refresh preserves role passwords and the private runtime configuration file. The API role can authenticate and manage permitted tenant records. The solver/mail worker cannot read user password hashes or manage organization members. Never run application traffic with migration-owner credentials.

Platform operators create organizations through a separate privileged administration connection:

```sh
uv run python -m app.cli.provision --name 'Organization name' --admin-email 'admin@example.org' --timezone Europe/Athens --invitation-file /private/path/first-admin.txt
```

The command refuses to overwrite a file and writes the invitation with mode 0600. Protect it as a credential. It never prints the token. Tenant administrators can invite members through `POST /api/v1/identity/invitations` with email and one of admin, dispatcher, fleet_manager, driver, management or viewer. Tenant identity comes from the authenticated session. Reissuing an invitation invalidates the previous unused link. Existing accounts use sign-in/reset; invitations do not silently transfer an account between organizations.

Identity links expire (invitations 48 hours; password resets 30 minutes), are hashed in the database and consumed once. The link secret uses a URL fragment, is read by the account form and removed from browser history. The API receives it in a request body. Outbox email contents are encrypted with EMAIL_OUTBOX_KEY (Fernet), or a domain-separated key derived from SECRET_KEY. Keep this key stable for pending deliveries; rotate deliberately. API/worker SQL engines hide parameter values.

Configure PUBLIC_APP_URL, SMTP_HOST, SMTP_PORT, SMTP_FROM, optional SMTP_USERNAME/SMTP_PASSWORD and SMTP_USE_TLS. Production requires an HTTPS public URL and TLS for configured SMTP. No configured sender means `not_configured`, never `sent`. Start the dedicated tenant worker only when mail delivery is intended:

```sh
uv run python -m app.domain.identity.mail_worker --tenant-id ORGANIZATION_ID
```

The outbox uses leases and attempt fencing; `sent` means SMTP accepted the message, not inbox delivery. Ambiguous worker crashes may redeliver with a stable Message-ID. Failed messages stay `failed`; reissue an invitation or request a fresh reset after fixing SMTP. New requests invalidate previous links. There is no untested external-email success claim: integration tests use a local SMTP sink, including rejected delivery.

Sessions last eight hours, use HttpOnly cookies (Secure in production, SameSite=Lax), and require a session-bound CSRF header for cookie-authenticated writes. Browser state reloads from `/auth/me`; JWTs and user authority are not persisted in localStorage. Logout, password changes and membership changes revoke server sessions. Revocable bearer credentials remain available for API compatibility. Open progress streams recheck access each poll. Login/reset budgets are atomic PostgreSQL counters keyed by an HMAC of action/address/email; limits persist across process restarts. Deploy behind a trusted proxy with a deliberate client-address policy before exposing the service publicly.

Driver accounts currently have only their own-duty capabilities; the driver portal remains a later implementation task. Organization invitations and roles do not imply that the remaining operational/import workflows are finished.

## Team screen (administrators)

Administrators (`members.manage`) manage people from **Team** in the sidebar instead of the API:

- **Invite** a person with email and one of admin, dispatcher, fleet manager, management or viewer. Drivers are invited from their driver record (Drivers → Edit → Driver sign-in) so a driver login is always tied to a real driver. An email already in the organization (active or deactivated) is refused with a hint; an email of another organization is answered like any new email, and is refused when the link is accepted.
- **Pending invitations** show email, role, expiry and the delivery status in words: *Queued, no email sent because delivery is not set up* (`not_configured`), *being sent* (`queued`, `delivering`), *sent* (accepted by the mail server, not a receipt), *failed, check settings*, *replaced* (`discarded`). Expired invitations stay visible for 30 days. **Resend** creates a new link and discards the old queued mail; **Revoke** kills the link and discards the queued mail.
- **Members**: change role, deactivate, reactivate. Each real change ends that person's sessions, is idempotent and is recorded in the office audit table (entity `member`). Becoming or ceasing to be an administrator, deactivating and revoking ask for confirmation. You cannot change your own role or status (ask another administrator); the last-administrator guard stays as a second line. A role change to Driver is refused; a driver changed to another role loses the driver link. Deactivated members stop being leave approvers.
- Any administrator may make others administrators; the safeguards are the confirmation and the audit record.

## Mail worker

`uv run python -m app.domain.identity.mail_worker --all-tenants` serves every organization that has mail waiting (a narrow database function, `ktel_mail_tenants()`, returns only organization ids and is executable by the worker role alone). `--tenant-id N` still serves one organization. It needs `SMTP_HOST` and `SMTP_FROM` (see `EMAIL_SETUP.md`), the worker database role (`DATABASE_WORKER_URL`), and `uv run python -m db.provision_runtime --refresh-grants` after migration `0018`. A message that cannot be decrypted (for example the encryption key changed while it waited) is marked `failed` and does not stop other messages; one organization's database error does not stop the others. Mail queued while delivery was not configured is marked `not_configured` and is not sent later: after enabling email, use **Resend**.
