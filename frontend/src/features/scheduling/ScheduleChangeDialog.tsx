"use client";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { confirmDiscardOwn } from "../navigation/unsaved-changes";
import { newRequestId } from "../navigation/request-id";
import { Field, Modal } from "../timetables/shared";
import { scheduleDisplay } from "./display";
import type { PersistedRevision, Verification } from "./revision-api";
import type { StudioResource, StudioTrip } from "./types";

type Mode = "move" | "cancel" | "replace_driver";
interface Preview {
  verification: Verification;
  changes: Array<{
    trip_id: string;
    original_resource_id: string;
    new_resource_id: string;
    start_minutes: number;
    end_minutes: number;
  }>;
}
interface Props {
  revision: PersistedRevision;
  trip: StudioTrip;
  trips: StudioTrip[];
  resources: StudioResource[];
  initialMode: Mode;
  initialTarget?: string;
  onClose: () => void;
  onSaved: (revision: PersistedRevision) => void;
}
export function ScheduleChangeDialog({
  revision,
  trip,
  trips,
  resources,
  initialMode,
  initialTarget,
  onClose,
  onSaved,
}: Props) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const published = revision.status === "published";
  const [mode, setMode] = useState<Mode>(initialMode),
    [destination, setDestination] = useState(initialTarget ?? ""),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [selected, setSelected] = useState<string[]>([trip.id]),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [publication, setPublication] = useState(""),
    [loadingPublication, setLoadingPublication] = useState(published);
  const active = useRef(true),
    attempt = useRef<{ signature: string; key: string } | null>(null),
    alert = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  const dirty =
    !!reason ||
    confirmed ||
    destination !== (initialTarget ?? "") ||
    selected.length !== 1 ||
    selected[0] !== trip.id ||
    mode !== initialMode;
  useUnsavedChanges(dirty || busy);
  const close = () => {
    if (!busy && confirmDiscardOwn(dirty, el)) onClose();
  };
  useEffect(() => {
    if (!published) return;
    const controller = new AbortController();
    setLoadingPublication(true);
    void apiFetch(
      `/api/v1/operations/day?service_date=${encodeURIComponent(revision.problem.service_date)}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw Error();
        const data = (await response.json()) as {
          publication: { publication_id: string; revision_id: string } | null;
        };
        if (!controller.signal.aborted) {
          if (data.publication?.revision_id === revision.revision_id)
            setPublication(data.publication.publication_id);
          else
            setError(
              el
                ? "Υπάρχει άλλη ενεργή δημοσίευση. Ανοίξτε την τελευταία πριν κάνετε αλλαγές."
                : "A different publication is current. Open the latest schedule before making changes.",
            );
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            el
              ? "Δεν ελέγχθηκε η δημοσίευση. Κλείστε και δοκιμάστε ξανά."
              : "The publication could not be checked. Close and try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingPublication(false);
      });
    return () => controller.abort();
  }, [
    apiFetch,
    published,
    revision.problem.service_date,
    revision.revision_id,
    el,
  ]);
  const related = useMemo(
    () =>
      trips.filter(
        (item) => item.resourceId === trip.resourceId && (published || !item.isLocked),
      ),
    [trips, trip.resourceId, published],
  );
  const source = revision.source_resources.find(
    (item) => item.resource_id === trip.resourceId,
  );
  const replacement = revision.source_resources.find(
    (item) => item.resource_id === destination,
  );
  const clock = scheduleDisplay({
    timezone: revision.timezone,
    serviceDayStartUtc: revision.service_day_start_utc,
    dayBoundariesMinutes: revision.day_boundaries_minutes,
  });
  const changed = () => {
    setPreview(null);
    setError("");
    attempt.current = null;
  };
  function body() {
    const ids = mode === "replace_driver" ? selected : [trip.id];
    const locked = (tripId: string) => trips.find((item) => item.id === tripId)?.isLocked === true;
    const patches = ids.map((tripId) => ({ ...(locked(tripId) ? { unlock: true } : {}), ...(
      mode === "cancel"
        ? { trip_id: tripId, operation: "cancel", reason: reason.trim() }
        : mode === "replace_driver"
          ? {
              trip_id: tripId,
              operation: "replace_driver",
              replacement_resource_id: destination,
              driver_version: replacement?.driver_version,
              vehicle_version: source?.vehicle_version,
              confirm_replacement: true,
            }
          : { trip_id: tripId, new_resource_id: destination }) }),
    );
    return published
      ? {
          publication_id: publication,
          version: revision.version,
          reason: reason.trim(),
          reviewed_not_started: ids,
          patches,
        }
      : { version: revision.version, patches };
  }
  async function check(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch(
        published
          ? "/api/v1/scheduling/changes/preview"
          : `/api/v1/scheduling/revisions/${revision.revision_id}/patches/preview`,
        { method: "POST", body: JSON.stringify(body()) },
      );
      const value = (await response.json()) as Preview & {
        detail?: string | { message?: string };
      };
      if (!response.ok)
        throw Error(
          typeof value.detail === "string"
            ? value.detail
            : (value.detail?.message ??
                (el
                  ? "Δεν ολοκληρώθηκε ο έλεγχος."
                  : "The change could not be checked.")),
        );
      if (active.current) setPreview(value);
    } catch (e) {
      if (active.current) {
        setError(
          e instanceof Error
            ? e.message
            : el
              ? "Δεν ολοκληρώθηκε ο έλεγχος."
              : "The change could not be checked.",
        );
        requestAnimationFrame(() => alert.current?.focus());
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function save() {
    if (!preview?.verification.valid || busy) return;
    setBusy(true);
    setError("");
    try {
      const payload = body(),
        signature = JSON.stringify(payload);
      if (published && attempt.current?.signature !== signature)
        attempt.current = { signature, key: newRequestId() };
      const response = await apiFetch(
        published
          ? "/api/v1/scheduling/changes"
          : `/api/v1/scheduling/revisions/${revision.revision_id}/patches`,
        {
          method: "POST",
          body: JSON.stringify(
            published
              ? { ...payload, request_id: attempt.current?.key }
              : payload,
          ),
        },
      );
      const value = (await response.json()) as PersistedRevision & {
        detail?: string | { message?: string };
      };
      if (!response.ok)
        throw Error(
          typeof value.detail === "string"
            ? value.detail
            : (value.detail?.message ??
                (el
                  ? "Η αλλαγή δεν αποθηκεύτηκε. Ελέγξτε ξανά."
                  : "The change was not saved. Review it again.")),
        );
      if (active.current) onSaved(value);
    } catch (e) {
      if (active.current) {
        setError(
          e instanceof Error
            ? e.message
            : el
              ? "Δεν επιβεβαιώθηκε η αποθήκευση. Δοκιμάστε ξανά."
              : "Could not confirm the save. Try again.",
        );
        requestAnimationFrame(() => alert.current?.focus());
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  const allowed =
    mode === "cancel" ||
    (!!destination &&
      (mode !== "replace_driver" ||
        (!!replacement?.driver_version && !!source?.vehicle_version)));
  return (
    <Modal
      title={el ? "Έλεγχος αλλαγής προγράμματος" : "Review schedule change"}
      subtitle={trip.tripCode}
      onClose={close}
      busy={busy}
    >
      <form onSubmit={(event) => void check(event)}>
        <div className="resource-form-body change-form">
          <p className="resource-form-intro">
            {el
              ? "Η ώρα του δρομολογίου παραμένει ίδια. Ελέγξτε την αλλαγή πριν αποθηκευτεί."
              : "The trip time stays the same. Check the change before saving."}
          </p>
          <div className="change-original">
            <strong>
              {trip.tripCode} · {clock.timeLabel(trip.startMinutes)} –{" "}
              {clock.timeLabel(trip.endMinutes)}
            </strong>
            <span>
              {clock.stationName(trip.startStation, el)} →{" "}
              {clock.stationName(trip.endStation, el)}
            </span>
          </div>
          <Field label={el ? "Τι θέλετε να αλλάξετε;" : "Change type"}>
            <select
              value={mode}
              disabled={busy}
              onChange={(event) => {
                setMode(event.target.value as Mode);
                setDestination("");
                setSelected([trip.id]);
                changed();
              }}
            >
              <option value="move">
                {el ? "Μετακίνηση δρομολογίου" : "Move trip"}
              </option>
              {published && (
                <option value="replace_driver">
                  {el
                    ? "Αντικατάσταση οδηγού, ίδιο όχημα"
                    : "Replace driver, keep bus"}
                </option>
              )}
              {published && (
                <option value="cancel">
                  {el ? "Ακύρωση δρομολογίου" : "Cancel trip"}
                </option>
              )}
            </select>
          </Field>
          {mode !== "cancel" && (
            <Field
              label={
                mode === "replace_driver"
                  ? el
                    ? "Οδηγός αντικατάστασης"
                    : "Replacement driver"
                  : el
                    ? "Νέα ανάθεση"
                    : "Destination assignment"
              }
            >
              <select
                required
                value={destination}
                disabled={busy}
                onChange={(event) => {
                  setDestination(event.target.value);
                  changed();
                }}
              >
                <option value="">{el ? "Επιλέξτε…" : "Choose…"}</option>
                {mode === "move" && (
                  <option value="UNASSIGNED">
                    {el ? "Χωρίς ανάθεση" : "Unassigned"}
                  </option>
                )}
                {resources
                  .filter((item) => item.id !== trip.resourceId)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.driverName} · {item.busPlate}
                    </option>
                  ))}
              </select>
            </Field>
          )}
          {mode === "replace_driver" && (
            <fieldset className="change-trip-selection">
              <legend>
                {el ? "Δρομολόγια προς αλλαγή" : "Trips to change"}
              </legend>
              {related.map((item) => (
                <label key={item.id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(item.id)}
                    disabled={busy}
                    onChange={(event) => {
                      setSelected((old) =>
                        event.target.checked
                          ? [...old, item.id]
                          : old.filter((id) => id !== item.id),
                      );
                      changed();
                    }}
                  />
                  {item.tripCode} · {clock.timeLabel(item.startMinutes)} –{" "}
                  {clock.timeLabel(item.endMinutes)}
                </label>
              ))}
            </fieldset>
          )}
          {published && (
            <>
              <Field label={el ? "Αιτία αλλαγής" : "Reason for change"}>
                <textarea
                  required
                  rows={3}
                  maxLength={1000}
                  value={reason}
                  disabled={busy}
                  onChange={(event) => {
                    setReason(event.target.value);
                    changed();
                  }}
                />
              </Field>
              <label className="change-confirm">
                <input
                  type="checkbox"
                  required
                  checked={confirmed}
                  disabled={busy}
                  onChange={(event) => {
                    setConfirmed(event.target.checked);
                    changed();
                  }}
                />
                {el
                  ? "Έχω επιβεβαιώσει ότι τα επιλεγμένα δρομολόγια δεν έχουν ξεκινήσει"
                  : "I confirmed the selected trips have not started"}
              </label>
              <p className="resource-help">
                {el
                  ? "Η αλλαγή δημιουργεί προσχέδιο. Η ισχύουσα δημοσίευση παραμένει μέχρι τη νέα έγκριση και δημοσίευση."
                  : "This creates a draft. The current publication stays in force until the updated schedule is approved and published."}
              </p>
            </>
          )}
          {error && (
            <p className="import-alert" role="alert" tabIndex={-1} ref={alert}>
              {error}
            </p>
          )}
          {preview && (
            <section
              className="change-check"
              aria-label={el ? "Αποτέλεσμα ελέγχου" : "Check result"}
            >
              <strong>
                {preview.verification.valid
                  ? el
                    ? "Ο έλεγχος ολοκληρώθηκε"
                    : "Check completed"
                  : el
                    ? "Η αλλαγή χρειάζεται έλεγχο"
                    : "This change needs attention"}
              </strong>
              <p>
                {el
                  ? "Οι έλεγχοι αφορούν τα διαθέσιμα αποθηκευμένα στοιχεία. Δεν αποτελούν πλήρη έλεγχο διαθεσιμότητας ή νομοθεσίας."
                  : "Checks use the available saved records; they do not establish full availability or legal compliance."}
              </p>
              {preview.verification.violations.map((violation, index) => (
                <p key={`${violation.rule_id}-${index}`}>{violation.message}</p>
              ))}
              {preview.verification.unassigned_trips.length > 0 && (
                <p>
                  {el
                    ? `${preview.verification.unassigned_trips.length} δρομολόγια παραμένουν χωρίς ανάθεση.`
                    : `${preview.verification.unassigned_trips.length} trips remain unassigned.`}
                </p>
              )}
            </section>
          )}
        </div>
        <footer className="resource-dialog-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={close}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          {preview?.verification.valid ? (
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => void save()}
            >
              {busy
                ? el
                  ? "Αποθήκευση…"
                  : "Saving…"
                : published
                  ? el
                    ? "Δημιουργία ελεγμένου προσχεδίου"
                    : "Create reviewed draft"
                  : el
                    ? "Αποθήκευση αλλαγής"
                    : "Save change"}
            </button>
          ) : (
            <button
              className="button primary"
              disabled={
                busy ||
                loadingPublication ||
                (published && !publication) ||
                !allowed ||
                !selected.length
              }
            >
              {busy
                ? el
                  ? "Έλεγχος…"
                  : "Checking…"
                : el
                  ? "Έλεγχος αλλαγής"
                  : "Check change"}
            </button>
          )}
        </footer>
      </form>
    </Modal>
  );
}
