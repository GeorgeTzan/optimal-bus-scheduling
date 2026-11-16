"use client";
import { useEffect, useState, type FormEvent } from "react";
import { Field, Modal } from "../timetables/shared";

const REASONS: [string, string, string][] = [
  ["no_driver", "Δεν υπήρχε διαθέσιμος οδηγός", "No driver available"],
  ["driver_leave", "Άδεια ή ασθένεια οδηγού", "Driver leave or sickness"],
  ["no_vehicle", "Δεν υπήρχε διαθέσιμο όχημα", "No vehicle available"],
  ["work_rules", "Νόμιμο όριο ωρών εργασίας", "Legal working hours limit"],
  ["other", "Άλλο", "Other"],
];

export function PublishReason({
  count,
  el,
  onConfirm,
  onCancel,
}: {
  count: number;
  el: boolean;
  onConfirm: (reason: string, note: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [opener] = useState(() => document.activeElement),
    [reason, setReason] = useState(""),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(
    () => () => {
      if (opener instanceof HTMLElement) opener.focus();
    },
    [opener],
  );
  const text = note.trim();
  const valid = !!reason && (reason !== "other" || !!text);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError("");
    try {
      await onConfirm(reason, text);
    } catch (failure) {
      setError(
        failure instanceof Error && failure.message
          ? failure.message
          : el
            ? "Η δημοσίευση δεν ολοκληρώθηκε. Δοκιμάστε ξανά."
            : "Publishing did not complete. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={el ? "Γιατί μένουν δρομολόγια χωρίς οδηγό;" : "Why do trips stay without a driver?"}
      onClose={() => !busy && onCancel()}
      busy={busy}
    >
      <form onSubmit={(event) => void submit(event)}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? `Δρομολόγια χωρίς οδηγό: ${count}. Ο λόγος καταγράφεται στη μηνιαία αναφορά.`
              : `Trips without a driver: ${count}. The reason is recorded in the monthly report.`}
          </p>
          <fieldset className="import-match">
            <legend>{el ? "Λόγος" : "Reason"}</legend>
            {REASONS.map(([value, greek, english]) => (
              <label key={value}>
                <input
                  type="radio"
                  name="uncovered-reason"
                  value={value}
                  checked={reason === value}
                  disabled={busy}
                  onChange={() => setReason(value)}
                />
                {el ? greek : english}
              </label>
            ))}
          </fieldset>
          <Field
            label={
              reason === "other"
                ? el
                  ? "Σημείωση (απαιτείται)"
                  : "Note (required)"
                : el
                  ? "Σημείωση (προαιρετική)"
                  : "Note (optional)"
            }
          >
            <textarea
              rows={3}
              maxLength={500}
              required={reason === "other"}
              value={note}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
          {error && (
            <p className="import-alert" role="alert">
              {error}
            </p>
          )}
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" disabled={busy} onClick={onCancel}>
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button className="button primary" disabled={!valid || busy}>
            {el ? "Επιβεβαίωση" : "Confirm"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
