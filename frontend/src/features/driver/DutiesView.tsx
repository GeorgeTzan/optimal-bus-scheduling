"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { Duty, DutiesResponse, DutyDay } from "./contracts";
import { DriverError, driverCall, requestId } from "./driver-api";

/** Own published duties for the next days. An acknowledgment is only ever recorded by a button, for the exact publication shown. */
export function DutiesView() {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    lang = el ? "el-GR" : "en-GB";
  const [data, setData] = useState<DutiesResponse | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(""),
    attempt = useRef<{ key: string; id: string } | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setData(await driverCall<DutiesResponse>(apiFetch, "/api/v1/driver/duties", { signal }, el));
      setError("");
    } catch (failure) {
      if (failure instanceof DOMException && failure.name === "AbortError") return;
      setError(failure instanceof Error ? failure.message : "");
    }
  }, [apiFetch, el]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  async function acknowledge(day: DutyDay, trips: Duty[]) {
    const ids = trips.map((duty) => duty.trip_id), key = `${day.publication_id}:${ids.join(",")}`;
    if (busy) return;
    attempt.current = attempt.current?.key === key ? attempt.current : { key, id: requestId() };
    setBusy(key); setError(""); setNotice("");
    try {
      await driverCall(apiFetch, "/api/v1/driver/acknowledgments", { method: "POST", body: JSON.stringify({ request_id: attempt.current.id, publication_id: day.publication_id, trip_ids: ids }) }, el);
      attempt.current = null;
      setNotice(el ? "Καταγράφηκε η επιβεβαίωση." : "Acknowledgment recorded.");
      await load();
    } catch (failure) {
      attempt.current = null;
      setError(failure instanceof Error ? failure.message : "");
      if (failure instanceof DriverError && failure.code === "publication_replaced") await load();
    } finally { setBusy(""); }
  }
  if (!data && !error) return <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p>;
  const zone = data?.timezone;
  const time = (iso: string) => new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: zone }).format(new Date(iso));
  const station = (s: Duty["origin"]) => (s ? (el ? s.name_el : s.name_en) : "—");
  return (
    <section aria-labelledby="duties-heading" className="driver-section">
      <h1 id="duties-heading">{el ? "Οι υπηρεσίες μου" : "My duties"}</h1>
      {error && (
        <div className="auth-error" role="alert">
          <p>{error}</p>
          <button className="button secondary" onClick={() => void load()}>{el ? "Δοκιμάστε ξανά" : "Try again"}</button>
        </div>)}
      {notice && <p className="office-summary" role="status">{notice}</p>}
      {data?.days.length === 0 && !error && <p className="office-empty">{el ? "Δεν υπάρχουν δημοσιευμένες υπηρεσίες για εσάς τις επόμενες 14 ημέρες." : "You have no published duties in the next 14 days."}</p>}
      {data?.days.map((day) => {
        const open = day.duties.filter((duty) => !duty.acknowledged);
        return (
          <article key={day.service_date} className="driver-day" aria-label={day.service_date}>
            <header>
              <h2>{new Intl.DateTimeFormat(lang, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(`${day.service_date}T12:00:00Z`))}</h2>
              {open.length > 1 && <button className="button secondary" disabled={!!busy} onClick={() => void acknowledge(day, open)}>{el ? "Επιβεβαίωση όλων" : "Acknowledge all"}</button>}
            </header>
            <ul>
              {day.duties.map((duty) => (
                <li key={duty.trip_id} className={duty.cancelled ? "driver-duty cancelled" : "driver-duty"}>
                  <div>
                    <strong>{duty.trip_code ?? duty.trip_id}</strong>{" "}
                    <span>{time(duty.start_utc)}–{time(duty.end_utc)}</span>
                    {duty.cancelled && <span className="driver-badge">✕ {el ? "Ακυρώθηκε" : "Cancelled"}</span>}
                  </div>
                  <div>{station(duty.origin)} → {station(duty.destination)}</div>
                  {duty.vehicle_label && <div className="driver-muted">{el ? "Όχημα" : "Vehicle"}: {duty.vehicle_label}</div>}
                  {duty.acknowledged
                    ? <span className="driver-ok">✓ {el ? "Επιβεβαιώθηκε" : "Acknowledged"}</span>
                    : <button className="button primary" disabled={!!busy} onClick={() => void acknowledge(day, [duty])}>{duty.cancelled ? (el ? "Επιβεβαίωση ακύρωσης" : "Acknowledge cancellation") : (el ? "Επιβεβαίωση" : "Acknowledge")}</button>}
                </li>))}
            </ul>
          </article>);
      })}
      {data && <p className="driver-muted">{el ? `Ώρες στη ζώνη ${data.timezone}.` : `Times are in ${data.timezone}.`}</p>}
    </section>
  );
}
