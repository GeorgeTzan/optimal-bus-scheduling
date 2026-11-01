"use client";
import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { RecordPicker } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import { Field, Modal } from "../timetables/shared";
import { FoldPicker } from "./office-ui";
import { localTime, newRequestId, OfficeError, post } from "./office-api";

export function LeaveRequestForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [driver, setDriver] = useState<Resource | null>(null),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [category, setCategory] = useState("annual"),
    [note, setNote] = useState(""),
    [folds, setFolds] = useState<Record<string, 0 | 1>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<OfficeError | null>(null),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(!!driver || !!start || !!end || !!note || busy);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!driver) return;
    setBusy(true); setError(null);
    try {
      await post(apiFetch, "/leave-requests", { driver_id: driver.id, start_local: localTime(start), end_local: localTime(end),
        category, private_note: note.trim() || null, ...folds }, requestId, el);
      setRequestId(newRequestId());
      onSaved();
    } catch (failure) {
      setError(failure instanceof OfficeError ? failure : new OfficeError(el ? "Δεν αποθηκεύτηκε." : "Not saved.", 0, null, []));
    } finally { setBusy(false); }
  };
  return (
    <Modal title={el ? "Αίτημα άδειας" : "Leave request"} subtitle={el ? "Άδειες" : "Leave"} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Το αίτημα μένει σε εκκρεμότητα και δεν εμποδίζει τον προγραμματισμό μέχρι να εγκριθεί."
              : "The request stays pending and does not block scheduling until it is approved."}
          </p>
          {error && <p className="auth-error" role="alert">{error.message}</p>}
          <RecordPicker kind="drivers" label={el ? "Οδηγός" : "Driver"} value={driver} onChange={setDriver} />
          <div className="resource-grid">
            <Field label={el ? "Από (τοπική ώρα)" : "From (local time)"}><input required type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label={el ? "Έως (τοπική ώρα, μη συμπεριλαμβανομένου)" : "Until (local time, exclusive)"}><input required type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          </div>
          <Field label={el ? "Κατηγορία" : "Category"}>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="annual">{el ? "Κανονική" : "Annual"}</option>
              <option value="sick">{el ? "Ασθένεια" : "Sick"}</option>
              <option value="unpaid">{el ? "Άνευ αποδοχών" : "Unpaid"}</option>
              <option value="other">{el ? "Άλλο" : "Other"}</option>
            </select>
          </Field>
          <Field label={el ? "Σημείωση (προαιρετική, χωρίς ιατρικά στοιχεία)" : "Note (optional, no medical details)"}>
            <input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <FoldPicker error={error} folds={folds} onChange={(key, value) => setFolds({ ...folds, [key]: value })} />
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Άκυρο" : "Cancel"}</button>
          <button className="button primary" disabled={busy || !driver || !start || !end}>{el ? "Καταχώριση αιτήματος" : "Record request"}</button>
        </footer>
      </form>
    </Modal>
  );
}
