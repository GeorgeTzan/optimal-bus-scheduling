"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { RecordPicker } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import { Field, Modal, weekdays } from "../timetables/shared";
import type { Pattern, Period } from "./contracts";
import { FoldPicker, useNames } from "./office-ui";
import { formatInstant, localTime, newRequestId, officeCall, OfficeError, post } from "./office-api";
import { WorkingPatternForm } from "./WorkingPatternForm";

function DriverPeriodForm({ onClose, onSaved }: { onClose: () => void; onSaved: (impactCount?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [driver, setDriver] = useState<Resource | null>(null),
    [kind, setKind] = useState<"available" | "unavailable">("unavailable"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [category, setCategory] = useState("other"),
    [folds, setFolds] = useState<Record<string, 0 | 1>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<OfficeError | null>(null),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(!!driver || !!start || !!end || busy);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!driver) return;
    setBusy(true); setError(null);
    try {
      const result = await post<{ impact_count?: number }>(apiFetch, "/driver-periods", { items: [{
        driver_id: driver.id, kind, start_local: localTime(start), end_local: localTime(end),
        category: kind === "unavailable" ? category : null, ...folds }] }, requestId, el);
      setRequestId(newRequestId());
      onSaved(result.impact_count);
    } catch (failure) {
      setError(failure instanceof OfficeError ? failure : new OfficeError(el ? "Δεν αποθηκεύτηκε." : "Not saved.", 0, null, []));
    } finally { setBusy(false); }
  };
  return (
    <Modal title={el ? "Συγκεκριμένη περίοδος" : "A specific period"} subtitle={el ? "Ωράριο εργασίας" : "Working time"} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Χρησιμοποιήστε το για μία συγκεκριμένη ημερομηνία ή για απουσία. Ένα ωράριο για μια ημέρα αντικαθιστά το εβδομαδιαίο αυτής της ημέρας."
              : "Use this for one date or an absence. A working period on a date replaces the weekly pattern for that date."}
          </p>
          {error && <p className="auth-error" role="alert">{error.message}</p>}
          <RecordPicker kind="drivers" label={el ? "Οδηγός" : "Driver"} value={driver} onChange={setDriver} />
          <Field label={el ? "Τύπος" : "Type"}>
            <select value={kind} onChange={(e) => setKind(e.target.value as "available" | "unavailable")}>
              <option value="unavailable">{el ? "Μη διαθέσιμος" : "Unavailable"}</option>
              <option value="available">{el ? "Εργάζεται" : "Working"}</option>
            </select>
          </Field>
          <div className="resource-grid">
            <Field label={el ? "Από (τοπική ώρα)" : "From (local time)"}><input required type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label={kind === "available" ? (el ? "Έως (τοπική ώρα)" : "Until (local time)") : (el ? "Έως (κενό = μέχρι νεοτέρας)" : "Until (empty = until further notice)")}>
              <input required={kind === "available"} type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          {kind === "unavailable" && (
            <Field label={el ? "Κατηγορία" : "Category"}>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="sick">{el ? "Ασθένεια" : "Sick"}</option>
                <option value="training">{el ? "Εκπαίδευση" : "Training"}</option>
                <option value="other">{el ? "Άλλο" : "Other"}</option>
              </select>
            </Field>
          )}
          <FoldPicker error={error} folds={folds} onChange={(key, value) => setFolds({ ...folds, [key]: value })} />
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Άκυρο" : "Cancel"}</button>
          <button className="button primary" disabled={busy || !driver || !start}>{el ? "Αποθήκευση" : "Save"}</button>
        </footer>
      </form>
    </Modal>
  );
}

export function WorkingTimePanel({ zone, from, to, onImpacts }: { zone: string; from: string; to: string; onImpacts: (count?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    names = useNames("drivers");
  const [patterns, setPatterns] = useState<Pattern[] | null>(null),
    [periods, setPeriods] = useState<Period[] | null>(null),
    [error, setError] = useState(""),
    [dialog, setDialog] = useState<"pattern" | "period" | null>(null),
    [refresh, setRefresh] = useState(0),
    [busyRow, setBusyRow] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setPatterns(null); setPeriods(null); setError("");
    const get = <T,>(path: string) => officeCall<{ items: T[] }>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), path, undefined, el);
    void Promise.all([get<Pattern>("/working-patterns"), get<Period>(`/driver-periods?date_from=${from}&date_to=${to}`)])
      .then(([a, b]) => { if (!controller.signal.aborted) { setPatterns(a.items); setPeriods(b.items); } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, from, to, refresh]);
  const retire = useCallback(async (path: string, row: { id: number; version: number }, what: string) => {
    if (!window.confirm(el ? `Αποσύρετε ${what}; Χωρίς άλλο ωράριο, η διαθεσιμότητα του οδηγού θα γίνει άγνωστη και τυχόν πρόχειρα θα χρειαστούν έλεγχο.` : `Retire ${what}? Without other working time, the driver's availability becomes unknown and open drafts will need review.`)) return;
    setBusyRow(row.id);
    try { const result = await post<{ impact_count?: number }>(apiFetch, `${path}/${row.id}/retire`, { expected_version: row.version }, newRequestId(), el); setRefresh((n) => n + 1); onImpacts(result.impact_count); }
    catch (failure) { setError(failure instanceof Error ? failure.message : ""); }
    finally { setBusyRow(null); }
  }, [apiFetch, el, onImpacts]);
  const days = (mask: number) => weekdays.filter((_, index) => mask & (1 << index)).map((names) => (names[el ? 0 : 1] ?? "").slice(0, 3)).join(" ");
  const done = (count?: number) => { setDialog(null); setRefresh((n) => n + 1); onImpacts(count); };
  return (
    <section aria-labelledby="working-heading" className="office-panel">
      <header className="office-panel-head">
        <div><h2 id="working-heading">{el ? "Ωράριο οδηγών" : "Driver working time"}</h2>
          <p>{el ? "Χωρίς καταχωρημένο ωράριο, η διαθεσιμότητα είναι άγνωστη και δεν επιτρέπεται η δημιουργία προγράμματος." : "Without recorded working time, availability is unknown."}</p></div>
        <div className="office-actions">
          <button className="button primary" onClick={() => setDialog("pattern")}>{el ? "Εβδομαδιαίο ωράριο" : "Weekly working time"}</button>
          <button className="button secondary" onClick={() => setDialog("period")}>{el ? "Περίοδος ή απουσία" : "Period or absence"}</button>
        </div>
      </header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {patterns === null && !error ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : (
        <>
          <h3>{el ? "Εβδομαδιαία ωράρια" : "Weekly patterns"}</h3>
          {patterns?.length === 0 ? <p className="office-empty">{el ? "Δεν υπάρχει ωράριο ακόμα." : "No working time recorded yet."}</p> : (
            <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
              <th>{el ? "Οδηγός" : "Driver"}</th><th>{el ? "Ημέρες" : "Days"}</th><th>{el ? "Ώρες" : "Hours"}</th><th>{el ? "Ισχύει" : "Valid"}</th><th /></tr></thead><tbody>
              {patterns?.map((row) => (
                <tr key={row.id}><td>{names.get(row.driver_id) ?? `#${row.driver_id}`}</td><td>{days(row.weekday_mask)}</td>
                  <td>{row.local_start}–{row.local_end}{row.ends_next_day ? " +1" : ""}</td><td>{row.valid_from} → {row.valid_until}</td>
                  <td className="office-action-cell"><button className="button secondary" disabled={busyRow === row.id} aria-label={`${el ? "Απόσυρση ωραρίου" : "Retire working time"}: ${names.get(row.driver_id) ?? row.driver_id}`} onClick={() => void retire("/working-patterns", row, el ? "αυτό το ωράριο" : "this working time")}>{el ? "Αποσύρω" : "Retire"}</button></td></tr>))}
            </tbody></table></div>)}
          <h3>{el ? "Περίοδοι και απουσίες στον μήνα" : "Periods and absences this month"}</h3>
          {periods?.length === 0 ? <p className="office-empty">{el ? "Καμία περίοδος αυτό τον μήνα." : "No periods this month."}</p> : (
            <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
              <th>{el ? "Οδηγός" : "Driver"}</th><th>{el ? "Τύπος" : "Type"}</th><th>{el ? "Από" : "From"}</th><th>{el ? "Έως" : "Until"}</th><th /></tr></thead><tbody>
              {periods?.map((row) => (
                <tr key={row.id}><td>{names.get(row.driver_id) ?? `#${row.driver_id}`}</td>
                  <td>{row.kind === "available" ? (el ? "Εργάζεται" : "Working") : (el ? "Μη διαθέσιμος" : "Unavailable")}{row.category ? ` · ${row.category}` : ""}</td>
                  <td>{formatInstant(row.start_utc, zone, el)}</td><td>{formatInstant(row.end_utc, zone, el)}</td>
                  <td className="office-action-cell"><button className="button secondary" disabled={busyRow === row.id} aria-label={`${el ? "Απόσυρση περιόδου" : "Retire period"}: ${names.get(row.driver_id) ?? row.driver_id}`} onClick={() => void retire("/driver-periods", row, el ? "αυτή την περίοδο" : "this period")}>{el ? "Αποσύρω" : "Retire"}</button></td></tr>))}
            </tbody></table></div>)}
        </>)}
      {dialog === "pattern" && <WorkingPatternForm onClose={() => setDialog(null)} onSaved={done} />}
      {dialog === "period" && <DriverPeriodForm onClose={() => setDialog(null)} onSaved={done} />}
    </section>
  );
}
