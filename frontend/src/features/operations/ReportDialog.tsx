"use client";
import { useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { Field, Modal } from "../timetables/shared";
import { newRequestId } from "../navigation/request-id";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import {
  updateLabel,
  type ReportTarget,
  type OperationalTrip,
  type OperationsDay,
} from "./contracts";
export function ReportDialog({
  target,
  onClose,
  onSaved,
}: {
  target: ReportTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [kind, setKind] = useState("delay"),
    [minutes, setMinutes] = useState(""),
    [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [conflict, setConflict] = useState(false),
    [review, setReview] = useState<OperationalTrip | null>(null),
    [version, setVersion] = useState(target.row.version);
  const attempt = useRef<{ signature: string; key: string } | null>(null),
    alert = useRef<HTMLParagraphElement>(null);
  useUnsavedChanges(!!description || !!minutes || busy);
  const close = () => {
    if (!busy && mayLeaveWorkspace()) onClose();
  };
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || conflict) return;
    setBusy(true);
    setError("");
    try {
      const body = target.event
        ? { expected_version: version, note: description }
        : {
            publication_id: target.publication.publication_id,
            trip_id: target.row.trip_id,
            expected_version: version,
            kind,
            description,
            delay_minutes: kind === "delay" ? Number(minutes) : null,
          };
      const signature = JSON.stringify(body);
      if (attempt.current?.signature !== signature)
        attempt.current = { signature, key: newRequestId() };
      const response = await apiFetch(
        target.event
          ? `/api/v1/operations/reports/${target.event.id}/resolve`
          : "/api/v1/operations/reports",
        {
          method: "POST",
          body: JSON.stringify({ ...body, request_id: attempt.current.key }),
        },
      );
      if (!response.ok) {
        if (response.status === 409) {
          setConflict(true);
          throw Error(
            el
              ? "Καταγράφηκε άλλη ενημέρωση. Ανανεώστε το δρομολόγιο και ελέγξτε τα στοιχεία σας."
              : "Another update was recorded. Refresh the trip and review your details.",
          );
        }
        throw Error(
          response.status === 403
            ? el
              ? "Η πρόσβασή σας άλλαξε. Ανανεώστε τη σελίδα."
              : "Your access changed. Reload the page."
            : el
              ? "Η ενημέρωση δεν αποθηκεύτηκε. Ελέγξτε τα πεδία και δοκιμάστε ξανά."
              : "The update could not be saved. Check the fields and try again.",
        );
      }
      onSaved();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : el
            ? "Δεν επιβεβαιώθηκε η αποθήκευση. Δοκιμάστε ξανά."
            : "Could not confirm the save. Try again.",
      );
      requestAnimationFrame(() => alert.current?.focus());
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const query = new URLSearchParams({
        service_date: target.serviceDate,
        publication_id: target.publication.publication_id,
        trip_id: target.row.trip_id,
      });
      const response = await apiFetch("/api/v1/operations/day?" + query.toString());
      if (!response.ok) throw Error();
      const day = (await response.json()) as OperationsDay,
        row = day.items.find((item) => item.trip_id === target.row.trip_id);
      if (!row) throw Error();
      setReview(row);
    } catch {
      setError(
        el
          ? "Δεν ανακτήθηκαν τα τελευταία στοιχεία. Δοκιμάστε ξανά."
          : "The latest trip could not be retrieved. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  const resolved =
    review &&
    target.event &&
    review.events.some((event) => event.resolved_event_id === target.event?.id);
  return (
    <Modal
      title={
        target.event
          ? el
            ? "Επίλυση αναφοράς"
            : "Resolve report"
          : el
            ? "Καταγραφή ενημέρωσης ομάδας"
            : "Record a staff update"
      }
      subtitle={`${target.row.trip.trip_code} · ${target.serviceDate}`}
      busy={busy}
      onClose={close}
    >
      <form onSubmit={(event) => void save(event)}>
        <p className="resource-help">
          {el
            ? "Η ενημέρωση αφορά αυτή τη δημοσίευση. Οι αναθέσεις του προγράμματος δεν αλλάζουν."
            : "This update belongs to this publication. Schedule assignments stay unchanged."}
        </p>
        {target.event && (
          <blockquote className="operations-original">
            {updateLabel(target.event.kind, el)}: {target.event.description}
          </blockquote>
        )}
        {!target.event && (
          <Field label={el ? "Τύπος ενημέρωσης" : "Update type"}>
            <select
              value={kind}
              disabled={busy}
              onChange={(event) => setKind(event.target.value)}
            >
              {(
                [
                  "delay",
                  "breakdown",
                  "note",
                  "departure",
                  "completion",
                ] as const
              ).map((value) => (
                <option key={value} value={value}>
                  {updateLabel(value, el)}
                </option>
              ))}
            </select>
          </Field>
        )}
        {!target.event && kind === "delay" && (
          <Field label={el ? "Καθυστέρηση (λεπτά)" : "Delay (minutes)"}>
            <input
              type="number"
              min={0}
              max={1440}
              step={1}
              required
              value={minutes}
              disabled={busy}
              onChange={(event) => setMinutes(event.target.value)}
            />
          </Field>
        )}
        <Field
          label={
            target.event
              ? el
                ? "Σημείωση επίλυσης"
                : "Resolution note"
              : el
                ? "Λεπτομέρειες"
                : "Details"
          }
        >
          <textarea
            rows={4}
            required
            maxLength={2000}
            value={description}
            disabled={busy}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <p className="resource-help">
          {el
            ? "Η ώρα και το όνομά σας καταγράφονται αυτόματα."
            : "Your name and the recording time are saved automatically."}
        </p>
        {error && (
          <p className="import-alert" role="alert" tabIndex={-1} ref={alert}>
            {error}
          </p>
        )}
        {conflict && (
          <div className="operations-conflict">
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => void refresh()}
            >
              {el ? "Ανανέωση για έλεγχο" : "Refresh trip for review"}
            </button>
            {review && (
              <div>
                <h3>{el ? "Τελευταίες ενημερώσεις" : "Latest updates"}</h3>
                {review.events.map((event) => (
                  <p key={event.id}>
                    {event.actor_name}: {event.description}
                  </p>
                ))}
                {resolved ? (
                  <p>
                    {el
                      ? "Η αναφορά έχει ήδη επιλυθεί. Κλείστε αυτό το παράθυρο για να δείτε το ιστορικό."
                      : "This report is already resolved. Close this window to view history."}
                  </p>
                ) : (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => {
                      setVersion(review.version);
                      setConflict(false);
                      setError("");
                      setReview(null);
                      attempt.current = null;
                    }}
                  >
                    {el
                      ? "Χρήση τελευταίας έκδοσης"
                      : "Use this latest version"}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        <footer className="resource-dialog-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={close}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button className="button primary" disabled={busy || conflict}>
            {busy
              ? el
                ? "Αποθήκευση…"
                : "Saving…"
              : target.event
                ? el
                  ? "Αποθήκευση επίλυσης"
                  : "Save resolution"
                : el
                  ? "Αποθήκευση ενημέρωσης"
                  : "Save update"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
