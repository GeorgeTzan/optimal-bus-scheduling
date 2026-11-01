"use client";
import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { RecordPicker } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import { Field, Modal } from "../timetables/shared";
import type { VehiclePeriod } from "./contracts";
import { FoldPicker } from "./office-ui";
import { localTime, newRequestId, OfficeError, post } from "./office-api";

export function MaintenanceForm({ onClose, onSaved }: { onClose: () => void; onSaved: (impactCount?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [vehicle, setVehicle] = useState<Resource | null>(null),
    [kind, setKind] = useState<"planned_maintenance" | "out_of_service">("out_of_service"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [estimate, setEstimate] = useState(""),
    [who, setWho] = useState(""),
    [folds, setFolds] = useState<Record<string, 0 | 1>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<OfficeError | null>(null),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(!!vehicle || !!start || !!end || !!who || busy);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const planned = kind === "planned_maintenance";
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!vehicle) return;
    setBusy(true); setError(null);
    try {
      const result = await post<{ impact_count?: number }>(apiFetch, "/vehicle-periods", { vehicle_id: vehicle.id, kind, start_local: localTime(start),
        end_local: planned ? localTime(end) : null, estimated_end_local: !planned && estimate ? localTime(estimate) : null,
        responsible_label: who.trim() || null, ...folds }, requestId, el);
      setRequestId(newRequestId());
      onSaved(result.impact_count);
    } catch (failure) {
      setError(failure instanceof OfficeError ? failure : new OfficeError(el ? "Δεν αποθηκεύτηκε." : "Not saved.", 0, null, []));
    } finally { setBusy(false); }
  };
  return (
    <Modal title={el ? "Συντήρηση ή ακινησία οχήματος" : "Vehicle maintenance or out of service"} subtitle={el ? "Στόλος" : "Fleet"} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          {error && <p className="auth-error" role="alert">{error.message}</p>}
          <RecordPicker kind="vehicles" label={el ? "Όχημα" : "Vehicle"} value={vehicle} onChange={setVehicle} />
          <fieldset className="office-days"><legend>{el ? "Τι συμβαίνει" : "What is happening"}</legend>
            <label><input type="radio" name="kind" checked={!planned} onChange={() => setKind("out_of_service")} />{el ? "Εκτός λειτουργίας τώρα" : "Out of service"}</label>
            <label><input type="radio" name="kind" checked={planned} onChange={() => setKind("planned_maintenance")} />{el ? "Προγραμματισμένη συντήρηση" : "Planned maintenance"}</label>
          </fieldset>
          <p className="resource-form-intro">
            {planned
              ? el ? "Δεσμεύει το όχημα για γνωστό χρονικό διάστημα." : "Reserves the vehicle for a known period."
              : el ? "Μένει ανοιχτή μέχρι να αποδεσμευτεί ρητά. Η εκτιμώμενη επιστροφή δεν την κλείνει ποτέ μόνη της." : "Stays open until someone releases it. An estimated return never closes it by itself."}
          </p>
          <div className="resource-grid">
            <Field label={el ? "Από (τοπική ώρα)" : "From (local time)"}><input required type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            {planned ? <Field label={el ? "Έως (τοπική ώρα)" : "Until (local time)"}><input required type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
              : <Field label={el ? "Εκτιμώμενη επιστροφή (προαιρετικά)" : "Estimated return (optional)"}><input type="datetime-local" value={estimate} onChange={(e) => setEstimate(e.target.value)} /></Field>}
          </div>
          <Field label={el ? "Υπεύθυνος / συνεργείο (προαιρετικά)" : "Responsible person or workshop (optional)"}>
            <input maxLength={200} value={who} onChange={(e) => setWho(e.target.value)} /></Field>
          <FoldPicker error={error} folds={folds} onChange={(key, value) => setFolds({ ...folds, [key]: value })} />
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Άκυρο" : "Cancel"}</button>
          <button className="button primary" disabled={busy || !vehicle || !start || (planned && !end)}>{el ? "Αποθήκευση" : "Save"}</button>
        </footer>
      </form>
    </Modal>
  );
}

/** Releasing records an operational decision. It is not a mechanical certification. */
export function ReleaseDialog({ row, vehicleName, mode, onClose, onSaved }: {
  row: VehiclePeriod; vehicleName: string; mode: "release" | "cancel"; onClose: () => void; onSaved: (impactCount?: number) => void;
}) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [at, setAt] = useState(""),
    [text, setText] = useState(""),
    [folds, setFolds] = useState<Record<string, 0 | 1>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<OfficeError | null>(null),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(!!at || !!text || busy);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const result = mode === "release" ? await post<{ impact_count?: number }>(apiFetch, `/vehicle-periods/${row.id}/release`, { expected_version: row.version, released_at_local: localTime(at), note: text.trim(), ...folds }, requestId, el)
        : await post<{ impact_count?: number }>(apiFetch, `/vehicle-periods/${row.id}/cancel`, { expected_version: row.version, reason: text.trim() }, requestId, el);
      setRequestId(newRequestId());
      onSaved(result.impact_count);
    } catch (failure) {
      setError(failure instanceof OfficeError ? failure : new OfficeError(el ? "Δεν αποθηκεύτηκε." : "Not saved.", 0, null, []));
    } finally { setBusy(false); }
  };
  return (
    <Modal title={mode === "release" ? (el ? "Αποδέσμευση οχήματος" : "Release vehicle") : (el ? "Ακύρωση καταχώρισης" : "Cancel entry")} subtitle={vehicleName} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          {error && <p className="auth-error" role="alert">{error.message}</p>}
          <p className="resource-form-intro">
            {mode === "release"
              ? el ? "Καταγράφετε ότι το όχημα επιστρέφει σε λειτουργία. Δεν πιστοποιεί τη μηχανική του κατάσταση." : "You are recording that the vehicle is back in service. This does not certify its mechanical condition."
              : el ? "Για καταχώριση που έγινε κατά λάθος. Δεν είναι αποδέσμευση." : "For an entry made in error. This is not a release."}
          </p>
          {mode === "release" && <Field label={el ? "Πότε επέστρεψε (τοπική ώρα, όχι μελλοντική)" : "When it returned (local time, not in the future)"}>
            <input required type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></Field>}
          <Field label={mode === "release" ? (el ? "Σημείωση" : "Note") : (el ? "Αιτιολογία" : "Reason")}>
            <input required maxLength={mode === "release" ? 500 : 1000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <FoldPicker error={error} folds={folds} onChange={(key, value) => setFolds({ ...folds, [key]: value })} />
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Κλείσιμο" : "Close"}</button>
          <button className="button primary" disabled={busy || !text.trim() || (mode === "release" && !at)}>{mode === "release" ? (el ? "Αποδέσμευση" : "Release") : el ? "Ακύρωση καταχώρισης" : "Cancel entry"}</button>
        </footer>
      </form>
    </Modal>
  );
}
