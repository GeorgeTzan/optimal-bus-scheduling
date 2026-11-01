"use client";
import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { RecordPicker, resourceLabel } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import { Field, Modal, weekdays } from "../timetables/shared";
import { FoldPicker } from "./office-ui";
import { newRequestId, OfficeError, post } from "./office-api";

const MAX_ITEMS = 100;
/** Bulk-first: choose drivers, weekdays and hours once; the exact result is shown before it is saved atomically. */
export function WorkingPatternForm({ onClose, onSaved }: { onClose: () => void; onSaved: (impacts?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [drivers, setDrivers] = useState<Resource[]>([]),
    [picked, setPicked] = useState<Resource | null>(null),
    [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]),
    [start, setStart] = useState("08:00"),
    [end, setEnd] = useState("16:00"),
    [overnight, setOvernight] = useState(false),
    [from, setFrom] = useState(""),
    [until, setUntil] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<OfficeError | null>(null),
    [message, setMessage] = useState(""),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(drivers.length > 0 || !!from || !!until || busy);
  const mask = days.reduce((total, day) => total + (1 << day), 0),
    close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const add = (row: Resource | null) => {
    setPicked(row);
    if (row && !drivers.some((d) => d.id === row.id) && drivers.length < MAX_ITEMS) {
      setDrivers([...drivers, row]);
      setTimeout(() => setPicked(null), 0);
    }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(null); setMessage("");
    try {
      const result = await post<{ impact_count?: number }>(apiFetch, "/working-patterns", {
        items: drivers.map((driver) => ({
          driver_id: driver.id, weekday_mask: mask, local_start: start, local_end: end,
          ends_next_day: overnight, valid_from: from, valid_until: until,
        })),
      }, requestId, el);
      setRequestId(newRequestId());
      onSaved(result.impact_count);
    } catch (failure) {
      if (failure instanceof OfficeError) setError(failure);
      else setMessage(el ? "Δεν αποθηκεύτηκε. Δοκιμάστε ξανά." : "Not saved. Please try again.");
    } finally { setBusy(false); }
  };
  const ready = drivers.length > 0 && days.length > 0 && !!from && !!until && !busy;
  return (
    <Modal title={el ? "Εβδομαδιαίο ωράριο" : "Weekly working time"} subtitle={el ? "Ωράριο εργασίας" : "Working time"} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Ορίστε πότε εργάζονται οι οδηγοί. Ό,τι δεν έχει οριστεί παραμένει άγνωστο και δεν θεωρείται διαθέσιμο."
              : "Say when drivers work. Anything not set stays unknown and is never treated as available."}
          </p>
          {(error || message) && <p className="auth-error" role="alert">{error?.message ?? message}</p>}
          <RecordPicker kind="drivers" label={el ? "Προσθήκη οδηγού" : "Add a driver"} value={picked} onChange={add} />
          <ul className="office-chips" aria-label={el ? "Επιλεγμένοι οδηγοί" : "Selected drivers"}>
            {drivers.map((driver) => (
              <li key={driver.id}>
                {resourceLabel(driver, "drivers", el)}
                <button type="button" aria-label={(el ? "Αφαίρεση " : "Remove ") + resourceLabel(driver, "drivers", el)}
                  onClick={() => setDrivers(drivers.filter((d) => d.id !== driver.id))}>×</button>
              </li>
            ))}
          </ul>
          <small>{el ? `Έως ${MAX_ITEMS} οδηγοί ανά αποθήκευση.` : `Up to ${MAX_ITEMS} drivers per save.`}</small>
          <fieldset className="office-days">
            <legend>{el ? "Ημέρες" : "Days"}</legend>
            {weekdays.map(([greek, english], index) => (
              <label key={english}>
                <input type="checkbox" checked={days.includes(index)}
                  onChange={() => setDays(days.includes(index) ? days.filter((d) => d !== index) : [...days, index])} />
                {el ? greek : english}
              </label>
            ))}
          </fieldset>
          <div className="resource-grid">
            <Field label={el ? "Έναρξη" : "Start"}><input required type="time" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label={el ? "Λήξη" : "End"}><input required type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          </div>
          <label className="office-check">
            <input type="checkbox" checked={overnight} onChange={(e) => setOvernight(e.target.checked)} />
            {el ? "Λήγει την επόμενη ημέρα" : "Ends the next day"}
          </label>
          <div className="resource-grid">
            <Field label={el ? "Ισχύει από" : "Valid from"}><input required type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
            <Field label={el ? "Ισχύει έως (έως 366 ημέρες)" : "Valid until (at most 366 days)"}><input required type="date" min={from || undefined} value={until} onChange={(e) => setUntil(e.target.value)} /></Field>
          </div>
          <FoldPicker error={error} folds={{}} onChange={() => undefined} />
          {drivers.length > 0 && days.length > 0 && (
            <p className="office-summary" aria-live="polite">
              {el
                ? `Θα αποθηκευτούν ${drivers.length} ωράρια: ${start}–${end}${overnight ? " (+1 ημέρα)" : ""}, ${days.length} ημέρες την εβδομάδα.`
                : `${drivers.length} patterns will be saved: ${start}–${end}${overnight ? " (+1 day)" : ""}, ${days.length} days a week.`}
            </p>
          )}
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Άκυρο" : "Cancel"}</button>
          <button className="button primary" disabled={!ready}>{busy ? (el ? "Αποθήκευση…" : "Saving…") : el ? "Αποθήκευση ωραρίου" : "Save working time"}</button>
        </footer>
      </form>
    </Modal>
  );
}
