# Email delivery setup (invitations and password resets)

Status: **not yet enabled.** Until the steps below are done, messages stay queued and the screens say "No email has been sent because email delivery is not set up." Nothing in the code sends mail to anyone until `SMTP_HOST` and `SMTP_FROM` are set.

## Recommended provider for a pilot: Brevo (SMTP relay)

Reasons: an EU company (data stays under EU rules, which matters for Greek customers' staff emails), plain SMTP so no new code, a free tier large enough for invitations and resets, no AWS account needed. Amazon SES is cheaper at large volume but needs account approval out of sandbox and more setup; Postmark has very good deliverability but is US-hosted. Changing provider later is only a change to the five values below. Check Brevo's current pricing, limits and screen names before you start; they change.

## One-time steps (you, not the code)

1. **Sending domain.** Use a domain you control, for example `ktel-platform.gr`. Sender address: `no-reply@ktel-platform.gr`.
2. **Brevo account** → *Senders, domains*: add the domain. Brevo shows DNS records to add at your DNS provider:
   - a DKIM record (TXT or CNAME, as Brevo shows),
   - an SPF record: add Brevo to the domain's single SPF TXT record (for example `v=spf1 include:spf.brevo.com ~all`; never create two SPF records),
   - a DMARC record, to start: `v=DMARC1; p=none; rua=mailto:you@yourdomain` and tighten it later.
   Wait until Brevo shows the domain as authenticated. Without these records invitations are likely to land in spam.
3. **SMTP key.** In Brevo → *SMTP & API* create an SMTP key. The relay is `smtp-relay.brevo.com`, port `587`, STARTTLS; the username is your Brevo login email and the password is that SMTP key (not your account password).
4. **Application settings, in a git-ignored file.** Create `backend/.env.mail.local` (it matches `.env*.local` in `.gitignore`, and `config.py` loads it). Make it readable by you only:

   ```
   umask 077
   cat > backend/.env.mail.local <<'EOT'
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USERNAME=<your Brevo login email>
   SMTP_PASSWORD=<the SMTP key>
   SMTP_FROM=no-reply@ktel-platform.gr
   SMTP_USE_TLS=true
   PUBLIC_APP_URL=https://<the address people open>
   EOT
   ```

   Never put these values in `backend/.env`, `.env.example`, the compose file, a ticket or a chat. `PUBLIC_APP_URL` is the address inside every link, so it must be the real HTTPS address; with the local default `http://127.0.0.1:3000` the links only work on your own computer.
5. **Restart** the API and start the mail worker (see "Worker" below).
6. **Test once, to yourself.** Invite a second mailbox of yours (not the address you sign in with: an address that is already a member is refused) as a staff member from Team and confirm the message arrives, is not in spam, and the link opens the accept page. Send nothing to anyone else until this works.

## Worker

Delivery is done by a separate process, which must connect with the **worker** database role (`DATABASE_WORKER_URL`, written to `backend/.env.runtime.local` by `uv run python -m db.provision_runtime`). If that setting is missing the process falls back to the API role, which may not run `--all-tenants`. After upgrading to migration `0018`, run `uv run python -m db.provision_runtime --refresh-grants` so the worker role may run the mailing function. `uv run python -m app.domain.identity.mail_worker --all-tenants` (serves every organization; `--tenant-id N` serves one). Keep it running next to the API. Messages queued while email was not configured are marked `not_configured` and are never sent later: after enabling email use **Resend** on Team → Pending invitations. The Team screen shows *failed, check the email settings* when the relay refuses a message.

## What is known to be risky

- **`backend/.env` is tracked by git** and already contains `DATABASE_URL`, `SECRET_KEY` and `SENTRY_DSN` (it was added in commit `15c3abe`). Anyone with the repository has them. Recommended, when you decide to touch git: stop tracking it (`git rm --cached backend/.env`, keep the file locally), rotate the database password and `SECRET_KEY`, and treat the Sentry DSN as exposed. Rotating `SECRET_KEY` also changes the key that encrypts queued mail unless `EMAIL_OUTBOX_KEY` is set; set `EMAIL_OUTBOX_KEY` first. I have not changed git or rotated anything.
- The mail text is Greek only, and contains the invitation link, so it must be sent to the intended mailbox only.
- Delivery status says "sent" when the relay accepted the message, not that the person received it. Bounces are not tracked.
