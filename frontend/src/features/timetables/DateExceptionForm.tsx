"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { checked, Field, Modal, type Timetable } from "./shared";
interface Exception {
  id: number;
  version: number;
  service_date: string;
  action: string;
  departure_time: string | null;
  arrival_time: string | null;
  arrival_day_offset: number | null;
  fold_start: number | null;
  fold_end: number | null;
}
export function DateExceptionForm({
  template,
  onClose,
  onSaved,
}: {
  template: Timetable;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [date, setDate] = useState(""),
    [action, setAction] = useState(""),
    [records, setRecords] = useState<Exception[]>([]),
    [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useUnsavedChanges(!!date || !!action || busy);
  const closeGuarded = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  useEffect(() => {
    const c = new AbortController();
    void apiFetch(`/api/v1/timetables/${template.id}/exceptions`, {
      signal: c.signal,
    })
      .then((r) => checked<{ items: Exception[] }>(r, el))
      .then((data) => {
        if (!c.signal.aborted) {
          setRecords(data.items);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!c.signal.aborted)
          setError(
            el
              ? "Δεν φορτώθηκαν οι εξαιρέσεις. Ανοίξτε ξανά για νέα προσπάθεια."
              : "Date exceptions could not load. Reopen to try again.",
          );
      });
    return () => c.abort();
  }, [apiFetch, template.id, el]);
  const saved = records.find((r) => r.service_date === date);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!loaded) return;
    setBusy(true);
    setError("");
    try {
      const overrides =
        action === "run" && saved
          ? {
              departure_time: saved.departure_time,
              arrival_time: saved.arrival_time,
              arrival_day_offset: saved.arrival_day_offset,
              fold_start: saved.fold_start,
              fold_end: saved.fold_end,
            }
          : {
              departure_time: null,
              arrival_time: null,
              arrival_day_offset: null,
              fold_start: null,
              fold_end: null,
            };
      await checked(
        await apiFetch(
          `/api/v1/timetables/${template.id}/exceptions${saved ? "/" + saved.id : ""}`,
          {
            method: saved ? "PATCH" : "POST",
            body: JSON.stringify({
              ...(saved ? { version: saved.version } : { service_date: date }),
              action,
              ...overrides,
            }),
          },
        ),
        el,
      );
      onSaved();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : el
            ? "Δεν αποθηκεύτηκε η αλλαγή."
            : "Your change was not saved.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={el ? "Αλλαγή μίας ημερομηνίας" : "Change one date"}
      subtitle={template.trip_code}
      onClose={closeGuarded}
      busy={busy}
    >
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Η αλλαγή ισχύει μόνο για αυτή την ημερομηνία. Το εβδομαδιαίο πρόγραμμα παραμένει αποθηκευμένο."
              : "This change applies only to this date. Your recurring timetable stays saved."}
          </p>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <Field label={el ? "Ημερομηνία εξαίρεσης" : "Exception date"}>
            <input
              required
              type="date"
              min={template.valid_from ?? undefined}
              max={template.valid_until ?? undefined}
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                setAction("");
              }}
            />
          </Field>
          {saved && (
            <p className="resource-form-intro">
              {el
                ? "Υπάρχει ήδη αποθηκευμένη εξαίρεση για αυτή την ημέρα. Η νέα επιλογή θα την ενημερώσει."
                : "A date exception is already saved for this day. Your selection will update it."}
            </p>
          )}
          <Field label={el ? "Τι αλλάζει;" : "What changes?"}>
            <select
              required
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              <option value="">{el ? "Επιλέξτε…" : "Choose…"}</option>
              <option value="cancel">
                {el ? "Ακύρωση για αυτή την ημέρα" : "Cancel on this date"}
              </option>
              <option value="run">
                {el
                  ? "Εκτέλεση και εκτός τακτικών ημερών"
                  : "Run even if normally off"}
              </option>
              <option value="inherit">
                {el
                  ? "Επαναφορά στο κανονικό πρόγραμμα"
                  : "Use normal timetable"}
              </option>
            </select>
          </Field>
          <p className="resource-form-intro">
            {el
              ? "Οι ώρες ελέγχονται στην προετοιμασία ημέρας. Η επαναφορά αφαιρεί τυχόν ειδικές ώρες ή επιλογές αλλαγής ώρας."
              : "Clocks are checked when preparing the service day. Using the normal timetable clears any special times or clock-change choices."}
          </p>
        </div>
        <footer>
          <button
            type="button"
            className="button secondary"
            onClick={closeGuarded}
            disabled={busy}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button className="button primary" disabled={!loaded || busy}>
            {busy
              ? el
                ? "Αποθήκευση…"
                : "Saving…"
              : el
                ? "Αποθήκευση εξαίρεσης"
                : "Save date exception"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
