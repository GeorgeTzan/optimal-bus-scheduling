"use client";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { LeaveItem } from "./contracts";
import { driverCall, requestId } from "./driver-api";

const categories: Record<string, [string, string]> = { annual: ["Ετήσια", "Annual"], sick: ["Ασθένεια", "Sick"], unpaid: ["Άνευ αποδοχών", "Unpaid"], other: ["Άλλο", "Other"] };
const states: Record<LeaveItem["state"], [string, string, string]> = { pending: ["Σε αναμονή", "Waiting", "…"], approved: ["Εγκρίθηκε", "Approved", "✓"], rejected: ["Απορρίφθηκε", "Declined", "✕"], cancelled: ["Ακυρώθηκε", "Cancelled", "–"] };

const addDays = (day: string, count: number) => new Date(Date.parse(`${day}T12:00:00Z`) + count * 86_400_000).toISOString().slice(0, 10);

/** Request leave and see the real status of each request. Only a request that is still waiting can be cancelled here. */
export function LeaveView({ timezone }: { timezone: string }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    lang = el ? "el-GR" : "en-GB";
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: timezone }).format(new Date());
  const [items, setItems] = useState<LeaveItem[] | null>(null),
    [from, setFrom] = useState(""), [until, setUntil] = useState(""), [category, setCategory] = useState("annual"), [note, setNote] = useState(""),
    [error, setError] = useState(""), [loadFailed, setLoadFailed] = useState(false), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false),
    attempt = useRef<{ key: string; id: string } | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const value = await driverCall<{ items: LeaveItem[] }>(apiFetch, `/api/v1/driver/leave-requests?date_from=${addDays(today, -30)}&date_to=${addDays(today, 31)}`, { signal }, el);
      setItems(value.items);
      setLoadFailed(false);
    } catch (failure) {
      if (failure instanceof DOMException && failure.name === "AbortError") return;
      setError(failure instanceof Error ? failure.message : "");
      setLoadFailed(true);
      setItems([]);
    }
  }, [apiFetch, el, today]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !from || !until) return;
    const body = { start_local: `${from}T00:00:00`, end_local: `${addDays(until, 1)}T00:00:00`, category, private_note: note.trim() || null };
    const key = JSON.stringify(body);
    attempt.current = attempt.current?.key === key ? attempt.current : { key, id: requestId() };
    setBusy(true); setError(""); setNotice("");
    try {
      await driverCall(apiFetch, "/api/v1/driver/leave-requests", { method: "POST", body: JSON.stringify({ ...body, request_id: attempt.current.id }) }, el);
      attempt.current = null;
      setFrom(""); setUntil(""); setNote("");
      setNotice(el ? "Το αίτημα στάλθηκε. Περιμένετε την απόφαση του γραφείου." : "Request sent. Wait for the office's decision.");
      await load();
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); } finally { setBusy(false); }
  }
  async function cancel(item: LeaveItem) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await driverCall(apiFetch, `/api/v1/driver/leave-requests/${item.id}/cancel`, { method: "POST", body: JSON.stringify({ request_id: requestId(), expected_version: item.version }) }, el);
      await load();
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); await load(); } finally { setBusy(false); }
  }
  const day = (iso: string, last = false) => new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", year: "numeric", timeZone: timezone }).format(new Date(last ? Date.parse(iso) - 1 : Date.parse(iso)));
  return (
    <section aria-labelledby="leave-heading" className="driver-section">
      <h1 id="leave-heading">{el ? "Άδειες" : "Leave"}</h1>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {notice && <p className="office-summary" role="status">{notice}</p>}
      <form onSubmit={submit} className="driver-form">
        <label>{el ? "Από" : "From"}<input type="date" required value={from} min={today} onChange={(e) => { setFrom(e.target.value); if (until && e.target.value > until) setUntil(e.target.value); }} /></label>
        <label>{el ? "Έως (τελευταία ημέρα απουσίας)" : "Until (last day away)"}<input type="date" required value={until} min={from || today} onChange={(e) => setUntil(e.target.value)} /></label>
        <label>{el ? "Είδος" : "Type"}
          <select value={category} onChange={(e) => setCategory(e.target.value)}>{Object.entries(categories).map(([value, names]) => <option key={value} value={value}>{names[el ? 0 : 1]}</option>)}</select></label>
        <label>{el ? "Σημείωση (προαιρετική, ιδιωτική)" : "Note (optional, private)"}<textarea maxLength={500} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <button className="button primary" disabled={busy || !from || !until}>{el ? "Αίτημα άδειας" : "Request leave"}</button>
      </form>
      <h2>{el ? "Τα αιτήματά μου" : "My requests"}</h2>
      {!items ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : items.length === 0 ? (loadFailed ? null : <p className="office-empty">{el ? "Δεν υπάρχουν αιτήματα." : "You have no requests in this period."}</p>) : (
        <ul className="driver-leave-list">
          {items.map((item) => (
            <li key={item.id}>
              <div><strong>{day(item.start_utc)} – {day(item.end_utc, true)}</strong> · {categories[item.category ?? ""]?.[el ? 0 : 1] ?? item.category}</div>
              <div><span className="driver-badge">{states[item.state][2]} {states[item.state][el ? 0 : 1]}</span></div>
              {item.decision_note && <div className="driver-muted">{el ? "Σημείωση γραφείου" : "Office note"}: {item.decision_note}</div>}
              {item.state === "pending" && <button className="button secondary" disabled={busy} onClick={() => void cancel(item)}>{el ? "Ακύρωση αιτήματος" : "Cancel request"}</button>}
            </li>))}
        </ul>)}
    </section>
  );
}
