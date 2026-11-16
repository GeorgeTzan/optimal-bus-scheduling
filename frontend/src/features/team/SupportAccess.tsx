"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { teamCall } from "./team-api";

interface Entry { action: string; reason: string | null; ticket: string | null; method: string | null; path: string | null; ends_at: string | null; at: string; actor: string }
interface Access { enabled: boolean; until: string | null; session: { ends_at: string } | null; entries: Entry[] }

const actionText: Record<string, [string, string]> = {
  support_session_started: ["Έναρξη συνεδρίας υποστήριξης", "Support session started"],
  support_session_ended: ["Λήξη συνεδρίας υποστήριξης", "Support session ended"],
  support_request: ["Προβολή", "Viewed"],
  customer_created: ["Δημιουργία οργανισμού", "Organization created"],
  customer_updated: ["Αλλαγή συνδρομής", "Subscription changed"],
  customer_suspended: ["Αναστολή", "Suspended"],
  customer_cancelled: ["Ακύρωση", "Cancelled"],
  customer_reactivated: ["Επανενεργοποίηση", "Reactivated"],
  customer_status_changed: ["Αλλαγή κατάστασης", "Status changed"],
};

export function SupportAccess() {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    lang = el ? 0 : 1;
  const [access, setAccess] = useState<Access | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const when = (value: string) => new Date(value).toLocaleString(el ? "el-GR" : "en-GB", { dateStyle: "short", timeStyle: "short" });
  const load = useCallback(async (signal?: AbortSignal) => {
    try { setAccess(await teamCall<Access>(apiFetch, "/support-access", { signal }, el)); setError(""); }
    catch (failure) { if (!(failure instanceof DOMException && failure.name === "AbortError")) setError(failure instanceof Error ? failure.message : ""); }
  }, [apiFetch, el]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  async function change(enabled: boolean) {
    setBusy(true); setError("");
    try { setAccess(await teamCall<Access>(apiFetch, "/support-access", { method: "PUT", body: JSON.stringify({ enabled }) }, el)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : ""); }
    finally { setBusy(false); }
  }
  return (
    <section className="office-panel" aria-labelledby="support-access-heading">
      <h2 id="support-access-heading">{el ? "Πρόσβαση υποστήριξης" : "Support access"}</h2>
      <p>{el ? "Η υποστήριξη της πλατφόρμας μπορεί να δει τον οργανισμό μόνο για ανάγνωση, μόνο όσο το επιτρέπετε (έως 24 ώρες κάθε φορά)." : "Platform support can view your organization read-only, only while you allow it (up to 24 hours at a time)."}</p>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {access && (<>
        <p data-testid="support-access-state">{access.enabled && access.until
          ? (el ? `Επιτρέπεται πρόσβαση υποστήριξης έως ${when(access.until)}.` : `Support access is allowed until ${when(access.until)}.`)
          : (el ? "Η πρόσβαση υποστήριξης είναι κλειστή." : "Support access is off.")}
          {access.session ? ` ${el ? `Συνεδρία υποστήριξης ενεργή έως ${when(access.session.ends_at)}.` : `A support session is active until ${when(access.session.ends_at)}.`}` : ""}</p>
        <button className="button primary" disabled={busy} onClick={() => void change(true)}>{access.enabled ? (el ? "Παράταση 24 ωρών" : "Extend by 24 hours") : (el ? "Επιτρέπεται πρόσβαση υποστήριξης" : "Allow support access")}</button>{" "}
        {access.enabled && <button className="button secondary" disabled={busy} onClick={() => void change(false)}>{el ? "Ανάκληση πρόσβασης" : "Revoke access"}</button>}
        {access.entries.length > 0 && (
          <div className="resource-table-scroll"><table className="resource-table" aria-label={el ? "Ιστορικό πρόσβασης υποστήριξης" : "Support access history"}><thead><tr>
            <th>{el ? "Πότε" : "When"}</th><th>{el ? "Ποιος" : "Who"}</th><th>{el ? "Ενέργεια" : "Action"}</th><th>{el ? "Λεπτομέρειες" : "Details"}</th></tr></thead><tbody>
            {access.entries.map((entry, index) => (
              <tr key={`${entry.at}-${index}`}>
                <td>{when(entry.at)}</td><td>{el ? "Υποστήριξη πλατφόρμας" : "Platform support"}</td>
                <td>{(actionText[entry.action] ?? [entry.action, entry.action])[lang]}</td>
                <td>{[entry.reason, entry.ticket && `#${entry.ticket}`, entry.method && entry.path && `${entry.method} ${entry.path}`].filter(Boolean).join(" · ")}</td></tr>))}
          </tbody></table></div>)}
      </>)}
    </section>
  );
}
