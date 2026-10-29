"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { newRequestId } from "../office/office-api";

interface Link {
  state: "unlinked" | "invited" | "expired" | "linked";
  email: string | null;
  invitation_id: string | null;
  expires_at: string | null;
  delivery_status: string | null;
}
type Failure = { detail?: string | { message?: string } };

/** Invite a driver to sign in from their driver record, and see or end the link. The invitation link itself is only ever in the email. */
export function DriverAccess({ driverId, driverName }: { driverId: number; driverName: string }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [link, setLink] = useState<Link | null>(null),
    [email, setEmail] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [note, setNote] = useState(""),
    [confirmUnlink, setConfirmUnlink] = useState(false),
    attempt = useRef<{ key: string; id: string } | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch(`/api/v1/identity/driver-links?driver_ids=${driverId}`, { signal });
    if (!response.ok) throw Error();
    const body = (await response.json()) as { links: Record<string, Link> };
    setLink(body.links[String(driverId)] ?? null);
  }, [apiFetch, driverId]);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch(() => { if (!controller.signal.aborted) setError(el ? "Δεν φορτώθηκε η κατάσταση σύνδεσης." : "The sign-in status could not be loaded."); });
    return () => controller.abort();
  }, [load, el]);
  async function send(path: string, body: object, key: string, done: string) {
    if (busy) return;
    attempt.current = attempt.current?.key === key ? attempt.current : { key, id: newRequestId() };
    setBusy(true); setError(""); setNote("");
    try {
      const response = await apiFetch(path, { method: "POST", body: JSON.stringify({ ...body, request_id: attempt.current.id }) });
      const value = (await response.json()) as Failure & { delivery_status?: string };
      if (!response.ok) {
        const detail = value.detail;
        throw Error(typeof detail === "string" ? detail : (detail?.message ?? (el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed.")));
      }
      attempt.current = null;
      setNote(path.endsWith("/invitations") ? delivery(value.delivery_status, el) : done);
      setEmail(""); setConfirmUnlink(false);
      await load();
    } catch (failure) { setError(failure instanceof Error && failure.message ? failure.message : el ? "Δεν υπάρχει σύνδεση. Δοκιμάστε ξανά." : "No connection. Try again."); } finally { setBusy(false); }
  }
  return (
    <section className="office-access" aria-labelledby={`access-${driverId}`}>
      <h3 id={`access-${driverId}`}>{el ? "Πρόσβαση οδηγού" : "Driver sign-in"}</h3>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {note && <p className="office-summary" role="status">{note}</p>}
      {!link ? <p>{el ? "Φόρτωση…" : "Loading…"}</p> : link.state === "linked" ? (
        <>
          <p>{el ? "Συνδεδεμένος λογαριασμός:" : "Linked account:"} <strong>{link.email}</strong></p>
          {confirmUnlink ? (
            <p>
              <button type="button" className="button primary" disabled={busy} onClick={() => void send(`/api/v1/identity/drivers/${driverId}/unlink`, {}, `unlink:${driverId}`, el ? "Η σύνδεση αφαιρέθηκε και οι συνεδρίες έκλεισαν." : "Unlinked. Their sessions were ended.")}>{el ? "Επιβεβαίωση αφαίρεσης" : "Confirm unlink"}</button>{" "}
              <button type="button" className="button secondary" disabled={busy} onClick={() => setConfirmUnlink(false)}>{el ? "Ακύρωση" : "Cancel"}</button>
            </p>
          ) : <button type="button" className="button secondary" onClick={() => setConfirmUnlink(true)}>{el ? "Αφαίρεση σύνδεσης" : "Unlink sign-in"}</button>}
        </>
      ) : link.state === "invited" || link.state === "expired" ? (
        <>
          <p>{link.state === "invited" ? (el ? "Εκκρεμεί πρόσκληση προς" : "Invitation pending for") : (el ? "Έληξε η πρόσκληση προς" : "Invitation expired for")} <strong>{link.email}</strong>. {delivery(link.delivery_status, el)}</p>
          <button type="button" className="button secondary" disabled={busy} onClick={() => void send(`/api/v1/identity/invitations/${link.invitation_id}/revoke`, {}, `revoke:${link.invitation_id}`, el ? "Η πρόσκληση ανακλήθηκε." : "Invitation revoked.")}>{el ? "Ανάκληση πρόσκλησης" : "Revoke invitation"}</button>
        </>
      ) : (
        <>
          <p>{el ? `Ο/Η ${driverName} δεν έχει λογαριασμό σύνδεσης.` : `${driverName} cannot sign in yet.`}</p>
          <label className="resource-field">
            <span>{el ? "Email οδηγού" : "Driver email"}</span>
            <input type="email" value={email} maxLength={254} autoComplete="off" onChange={(e) => { setEmail(e.target.value); setError(""); }}
              onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} />
          </label>
          <button type="button" className="button primary" disabled={busy || !/^\S+@\S+\.\S+$/.test(email)}
            onClick={() => void send("/api/v1/identity/invitations", { email: email.trim(), role: "driver", driver_id: driverId }, `invite:${driverId}:${email.trim()}`, "")}>{el ? "Πρόσκληση για σύνδεση" : "Invite to sign in"}</button>
        </>
      )}
    </section>
  );
}

function delivery(status: string | null | undefined, el: boolean) {
  if (status === "not_configured") return el ? "Στήθηκε στην ουρά. Δεν έχει σταλεί email επειδή η αποστολή δεν έχει ρυθμιστεί." : "Queued. No email has been sent because email delivery is not set up.";
  if (status === "queued") return el ? "Το email είναι στην ουρά αποστολής." : "The email is queued for sending.";
  if (status === "sent") return el ? "Το email στάλθηκε." : "The email was sent.";
  return status ? (el ? `Κατάσταση αποστολής: ${status}.` : `Delivery status: ${status}.`) : "";
}
