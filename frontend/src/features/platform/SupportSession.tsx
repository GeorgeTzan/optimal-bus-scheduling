"use client";
import React, { useCallback, useEffect, useState } from "react";
import {
  PlatformError,
  platformCall,
  type SupportStarted,
  type SupportState,
} from "./platform-api";

const mailText: Record<string, [string, string]> = {
  queued: [
    "Ειδοποίηση στους διαχειριστές: στην ουρά.",
    "Administrator notice: queued.",
  ],
  not_configured: [
    "Ειδοποίηση στους διαχειριστές: δεν στάλθηκε, η αποστολή email δεν έχει ρυθμιστεί.",
    "Administrator notice: not sent, email delivery is not set up.",
  ],
  no_recipients: [
    "Ειδοποίηση στους διαχειριστές: δεν υπάρχει ενεργός διαχειριστής.",
    "Administrator notice: no active administrator.",
  ],
  failed: [
    "Ειδοποίηση στους διαχειριστές: απέτυχε.",
    "Administrator notice: failed.",
  ],
};

export function SupportSession({
  customerId,
  el,
}: {
  customerId: number;
  el: boolean;
}) {
  const [state, setState] = useState<SupportState | null>(null),
    [reason, setReason] = useState(""),
    [ticket, setTicket] = useState(""),
    [mail, setMail] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const lang = el ? 0 : 1;
  const when = (value: string) =>
    new Date(value).toLocaleString(el ? "el-GR" : "en-GB", {
      dateStyle: "short",
      timeStyle: "short",
    });
  const load = useCallback(
    () =>
      platformCall<SupportState>(`/customers/${customerId}/support-session`, el)
        .then(setState)
        .catch((failure: unknown) =>
          setError(failure instanceof PlatformError ? failure.message : ""),
        ),
    [customerId, el],
  );
  useEffect(() => {
    void load();
  }, [load]);
  async function begin(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const started = await platformCall<SupportStarted>(
        `/customers/${customerId}/support-session`,
        el,
        {
          method: "POST",
          body: JSON.stringify({ reason, ticket: ticket || null }),
        },
      );
      setMail((mailText[started.mail_status] ?? ["", ""])[lang]);
      setReason("");
      setTicket("");
      await load();
    } catch (failure) {
      setError(failure instanceof PlatformError ? failure.message : "");
    } finally {
      setBusy(false);
    }
  }
  async function end() {
    setBusy(true);
    setError("");
    try {
      await platformCall<void>(`/customers/${customerId}/support-session`, el, {
        method: "DELETE",
      });
      setMail("");
      await load();
    } catch (failure) {
      setError(failure instanceof PlatformError ? failure.message : "");
    } finally {
      setBusy(false);
    }
  }
  if (!state) return error ? <p role="alert">{error}</p> : null;
  return (
    <section
      className="platform-support"
      aria-label={el ? "Συνεδρία υποστήριξης" : "Support session"}
    >
      <h3>{el ? "Συνεδρία υποστήριξης" : "Support session"}</h3>
      <p data-testid="support-consent">
        {state.access_open && state.access_until
          ? el
            ? `Ο πελάτης επιτρέπει πρόσβαση έως ${when(state.access_until)}.`
            : `The customer allows access until ${when(state.access_until)}.`
          : el
            ? "Ο πελάτης δεν έχει επιτρέψει πρόσβαση υποστήριξης."
            : "The customer has not allowed support access."}
      </p>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {state.session ? (
        <>
          <p data-testid="support-active">
            {el
              ? `Ενεργή συνεδρία μόνο για ανάγνωση έως ${when(state.session.ends_at)}.`
              : `Read-only session active until ${when(state.session.ends_at)}.`}
          </p>
          {mail && <p data-testid="support-mail">{mail}</p>}
          <a className="button primary" href="/" target="_blank" rel="noopener">
            {el ? "Άνοιγμα εφαρμογής πελάτη" : "Open customer app"}
          </a>{" "}
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void end()}
          >
            {el ? "Τερματισμός συνεδρίας" : "End session"}
          </button>
        </>
      ) : (
        state.access_open && (
          <form
            className="platform-form"
            onSubmit={(event) => void begin(event)}
          >
            <label>
              {el ? "Αιτία" : "Reason"}
              <input
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <label>
              {el ? "Αίτημα (προαιρετικό)" : "Ticket (optional)"}
              <input
                maxLength={100}
                value={ticket}
                onChange={(event) => setTicket(event.target.value)}
              />
            </label>
            <button
              className="button primary"
              type="submit"
              disabled={busy || !reason.trim()}
            >
              {el ? "Έναρξη συνεδρίας" : "Start session"}
            </button>
          </form>
        )
      )}
    </section>
  );
}
