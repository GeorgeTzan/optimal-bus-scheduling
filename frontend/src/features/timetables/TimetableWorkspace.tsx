"use client";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, CalendarDays, Plus, Search } from "lucide-react";
import { ConnectionPanel } from "./ConnectionPanel";
import { DateExceptionForm } from "./DateExceptionForm";
import { BulkImportButton } from "../imports/BulkImportButton";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { useListLocation } from "../navigation/use-list-location";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { ResourceForm, type Resource } from "../resources/ResourceWorkspace";
import { RecordPicker } from "../resources/RecordPicker";
import {
  checked,
  Field,
  Modal,
  stationName,
  weekdays,
  type Timetable,
} from "./shared";
export function TimetableWorkspace({ onPrepare }: { onPrepare: () => void }) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el",
    canWrite = !!user?.permissions.includes("timetable.write");
  const { query: q, setQuery: setQ, page, setPage } = useListLocation();
  const [items, setItems] = useState<Timetable[]>([]),
    [total, setTotal] = useState(0),
    [editing, setEditing] = useState<Timetable | "new" | null>(null),
    [exceptionTemplate, setExceptionTemplate] = useState<Timetable | null>(
      null,
    ),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      void apiFetch(
        `/api/v1/timetables?q=${encodeURIComponent(q)}&page=${page}`,
      )
        .then((r) => checked<{ items: Timetable[]; total: number }>(r, el))
        .then((data) => {
          if (!c.signal.aborted) {
            setItems(data.items);
            setTotal(data.total);
            setError("");
          }
        })
        .catch(() => {
          if (!c.signal.aborted)
            setError(
              el
                ? "Δεν φορτώθηκαν τα δρομολόγια."
                : "Timetables could not load.",
            );
        })
        .finally(() => {
          if (!c.signal.aborted) setLoading(false);
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [apiFetch, q, page, el, refresh]);
  return (
    <section className="resource-workspace">
      <div className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΒΑΣΗ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟΥ" : "PLANNING FOUNDATIONS"}
          </span>
          <h1>{el ? "Τα δρομολόγιά σας" : "Your timetables"}</h1>
          <p>
            {el
              ? "Εισαγάγετε πολλά δρομολόγια από Excel ή προσθέστε μία διαδρομή με τις ημέρες λειτουργίας της. Τα τακτικά δρομολόγια καταχωρίζονται μία φορά."
              : "Add many services from Excel, or set one route and choose the days it runs. You only enter a recurring service once."}
          </p>
        </div>
        <div className="resource-heading-actions">
          <BulkImportButton
            entity="timetable"
            returnTo="timetables"
            primary={total === 0 && !q}
          />
          <button
            className={`button ${total === 0 && !q && user?.permissions.includes("imports.write") ? "secondary" : "primary"}`}
            disabled={!canWrite}
            onClick={() => setEditing("new")}
          >
            <Plus size={16} />
            {el ? "Προσθήκη δρομολογίου" : "Add timetable"}
          </button>
        </div>
      </div>
      <div className="planning-guide">
        <CalendarDays size={22} />
        <div>
          <strong>
            {el
              ? "Από το εβδομαδιαίο πρόγραμμα στη συγκεκριμένη ημέρα"
              : "From your weekly timetable to a working day"}
          </strong>
          <p>
            {el
              ? "Αποθηκεύστε τα τακτικά δρομολόγια και μετά επιλέξτε οδηγούς και οχήματα για μια ημερομηνία."
              : "Save your recurring services, then choose drivers and vehicles for a date."}
          </p>
        </div>
        <button className="button secondary" onClick={onPrepare}>
          {el ? "Προετοιμασία ημέρας" : "Prepare a service day"}
          <ArrowRight size={15} />
        </button>
      </div>
      <div className="resource-panel">
        <div className="resource-tools">
          <label className="resource-search">
            <Search size={16} />
            <input
              aria-label={
                el ? "Αναζήτηση δρομολογίου" : "Search trip reference"
              }
              placeholder={el ? "Αναζήτηση κωδικού…" : "Search trip reference…"}
              value={q}
              maxLength={160}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </label>
          <span className="resource-result-count">
            {total}{" "}
            {el
              ? total === 1
                ? "δρομολόγιο"
                : "δρομολόγια"
              : total === 1
                ? "timetable"
                : "timetables"}
          </span>
        </div>
        {error ? (
          <div className="resource-empty">
            <p role="alert">{error}</p>
            <button
              className="button secondary"
              onClick={() => setRefresh((x) => x + 1)}
            >
              {el ? "Νέα προσπάθεια" : "Try again"}
            </button>
          </div>
        ) : loading ? (
          <p className="resource-empty" role="status">
            {el ? "Φόρτωση…" : "Loading…"}
          </p>
        ) : !items.length ? (
          <div className="resource-empty">
            <CalendarDays size={32} />
            <h2>
              {q
                ? el
                  ? "Δεν βρέθηκαν δρομολόγια"
                  : "No matching timetables"
                : el
                  ? "Ξεκινήστε με μία διαδρομή"
                  : "Start with one route"}
            </h2>
            <p>
              {el
                ? "Σταθμοί, ώρες και ημέρες λειτουργίας — θα σας καθοδηγήσουμε βήμα βήμα."
                : "Stations, times and operating days — we’ll guide you through each step."}
            </p>
          </div>
        ) : (
          <div className="planning-table-scroll timetable-desktop-list">
            <table className="resource-table">
              <thead>
                <tr>
                  {[
                    el ? "Δρομολόγιο" : "Service",
                    el ? "Διαδρομή" : "Route",
                    el ? "Ώρες" : "Times",
                    el ? "Ημέρες" : "Days",
                    el ? "Κατάσταση" : "Status",
                    el ? "Ενέργεια" : "Action",
                  ].map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.trip_code}</strong>
                      <small>
                        {row.valid_from} — {row.valid_until}
                      </small>
                    </td>
                    <td>
                      {stationName(row.origin, el)}
                      <small>→ {stationName(row.destination, el)}</small>
                    </td>
                    <td>
                      {row.departure_time?.slice(0, 5)} —{" "}
                      {row.arrival_time?.slice(0, 5)}
                      {row.arrival_day_offset > 0 && (
                        <small>
                          +{row.arrival_day_offset} {el ? "ημέρα" : "day"}
                        </small>
                      )}
                    </td>
                    <td>
                      {row.operating_weekdays
                        ?.map((d) =>
                          (weekdays[d]?.[el ? 0 : 1] ?? "").slice(0, 3),
                        )
                        .join(" · ") || "—"}
                    </td>
                    <td>
                      <span
                        className={`resource-status ${row.is_active && row.calendar_ready ? "active" : ""}`}
                      >
                        {!row.is_active
                          ? el
                            ? "Αρχειοθετημένο"
                            : "Archived"
                          : row.calendar_ready
                            ? el
                              ? "Ενεργό"
                              : "Active"
                            : el
                              ? "Χρειάζεται συμπλήρωση"
                              : "Needs details"}
                      </span>
                    </td>
                    <td>
                      <button
                        className="button secondary"
                        disabled={!canWrite}
                        onClick={() => setEditing(row)}
                      >
                        {el ? "Επεξεργασία" : "Edit"}
                      </button>
                      <button
                        className="button secondary"
                        disabled={!canWrite}
                        onClick={() => setExceptionTemplate(row)}
                      >
                        {el ? "Αλλαγή μίας ημερομηνίας" : "Change one date"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && items.length > 0 && (
          <ul
            className="resource-mobile-list"
            aria-label={el ? "Δρομολόγια" : "Timetables"}
          >
            {items.map((row) => (
              <li key={row.id} className="resource-mobile-card">
                <div className="resource-card-heading">
                  <div>
                    <strong>{row.trip_code}</strong>
                    <small>
                      {row.departure_time?.slice(0, 5)} —{" "}
                      {row.arrival_time?.slice(0, 5)}
                      {row.arrival_day_offset > 0
                        ? ` (+${row.arrival_day_offset})`
                        : ""}
                    </small>
                  </div>
                  <button
                    className="button secondary"
                    disabled={!canWrite}
                    onClick={() => setEditing(row)}
                  >
                    {el ? "Επεξεργασία" : "Edit"}
                  </button>
                </div>
                <dl>
                  <div>
                    <dt>{el ? "Διαδρομή" : "Route"}</dt>
                    <dd>
                      {stationName(row.origin, el)} →{" "}
                      {stationName(row.destination, el)}
                    </dd>
                  </div>
                  <div>
                    <dt>{el ? "Ημέρες" : "Days"}</dt>
                    <dd>
                      {row.operating_weekdays
                        ?.map((d) =>
                          (weekdays[d]?.[el ? 0 : 1] ?? "").slice(0, 3),
                        )
                        .join(" · ") || "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>{el ? "Ισχύς" : "Validity"}</dt>
                    <dd>
                      {row.valid_from} — {row.valid_until}
                    </dd>
                  </div>
                  <div>
                    <dt>{el ? "Κατάσταση" : "Status"}</dt>
                    <dd>
                      {!row.is_active
                        ? el
                          ? "Αρχειοθετημένο"
                          : "Archived"
                        : row.calendar_ready
                          ? el
                            ? "Ενεργό"
                            : "Active"
                          : el
                            ? "Χρειάζεται συμπλήρωση"
                            : "Needs details"}
                    </dd>
                  </div>
                </dl>
                <div className="timetable-mobile-actions">
                  <button
                    className="button secondary"
                    disabled={!canWrite}
                    onClick={() => setExceptionTemplate(row)}
                  >
                    {el ? "Αλλαγή μίας ημερομηνίας" : "Change one date"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {total > 25 && (
          <div className="planning-pagination">
            <button
              className="button secondary"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              {el ? "Προηγούμενη" : "Previous"}
            </button>
            <span>
              {page} / {Math.ceil(total / 25)}
            </span>
            <button
              className="button secondary"
              disabled={page * 25 >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              {el ? "Επόμενη" : "Next"}
            </button>
          </div>
        )}
      </div>
      <ConnectionPanel />
      {exceptionTemplate && (
        <DateExceptionForm
          template={exceptionTemplate}
          onClose={() => setExceptionTemplate(null)}
          onSaved={() => setExceptionTemplate(null)}
        />
      )}
      {editing && (
        <TimetableForm
          record={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setRefresh((x) => x + 1);
          }}
        />
      )}
    </section>
  );
}
function TimetableForm({
  record,
  onClose,
  onSaved,
}: {
  record: Timetable | "new";
  onClose: () => void;
  onSaved: () => void;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el",
    row = record === "new" ? null : record;
  const [step, setStep] = useState(0),
    [code, setCode] = useState(row?.trip_code ?? ""),
    [origin, setOrigin] = useState<Resource | null>(row?.origin ?? null),
    [destination, setDestination] = useState<Resource | null>(
      row?.destination ?? null,
    ),
    [departure, setDeparture] = useState(
      row?.departure_time?.slice(0, 5) ?? "",
    ),
    [arrival, setArrival] = useState(row?.arrival_time?.slice(0, 5) ?? ""),
    [offset, setOffset] = useState(row?.arrival_day_offset ?? 0),
    [distance, setDistance] = useState(row?.distance_km?.toString() ?? ""),
    [days, setDays] = useState<number[]>(row?.operating_weekdays ?? []),
    [from, setFrom] = useState(row?.valid_from ?? ""),
    [until, setUntil] = useState(row?.valid_until ?? ""),
    [types, setTypes] = useState<string[]>(row?.allowed_bus_types ?? []),
    [availableTypes, setAvailableTypes] = useState<string[]>(
      row?.allowed_bus_types ?? [],
    ),
    [active, setActive] = useState(row?.is_active ?? true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [creating, setCreating] = useState<{
      field: "origin" | "destination";
      name: string;
    } | null>(null);
  const formValue = JSON.stringify({code,origin:origin?.id,destination:destination?.id,departure,arrival,offset,distance,days,from,until,types,active});
  const baseline = useRef(formValue);
  useUnsavedChanges(formValue !== baseline.current || busy);
  const closeGuarded = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const loadTypes = useCallback(async () => {
    try {
      const found = new Set(row?.allowed_bus_types ?? []);
      let page = 1,
        total = 0;
      do {
        const data = await checked<{ items: Resource[]; total: number }>(
          await apiFetch(
            `/api/v1/vehicles?active_only=true&page_size=100&page=${page}`,
          ),
          el,
        );
        data.items.forEach((v) => {
          if (v.bus_type) found.add(v.bus_type);
        });
        total = data.total;
        page++;
      } while ((page - 1) * 100 < total);
      setAvailableTypes([...found].sort());
    } catch {
      setError(
        el
          ? "Δεν φορτώθηκαν οι κατηγορίες στόλου. Ανοίξτε ξανά τη φόρμα."
          : "Fleet categories could not load. Reopen the form to try again.",
      );
    }
  }, [apiFetch, el, row]);
  useEffect(() => {
    void loadTypes();
  }, [loadTypes]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!origin || !destination || origin.id === destination.id) {
      setError(
        el
          ? "Επιλέξτε δύο διαφορετικούς σταθμούς."
          : "Choose two different stations.",
      );
      return;
    }
    if (step === 0) {
      setError("");
      setStep(1);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await checked(
        await apiFetch(`/api/v1/timetables${row ? "/" + row.id : ""}`, {
          method: row ? "PATCH" : "POST",
          body: JSON.stringify({
            ...(row ? { version: row.version } : {}),
            trip_code: code,
            origin_station_id: origin.id,
            destination_station_id: destination.id,
            departure_time: departure,
            arrival_time: arrival,
            arrival_day_offset: offset,
            operating_weekdays: days,
            valid_from: from,
            valid_until: until,
            allowed_bus_types: types,
            distance_km: distance ? Number(distance) : null,
            is_active: active,
          }),
        }),
        el,
      );
      onSaved();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : el
            ? "Η αποθήκευση απέτυχε."
            : "Save failed.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Modal
        title={
          row
            ? el
              ? "Επεξεργασία δρομολογίου"
              : "Edit timetable"
            : el
              ? "Προσθήκη δρομολογίου"
              : "Add timetable"
        }
        subtitle={el ? `ΒΗΜΑ ${step + 1} ΑΠΟ 2` : `STEP ${step + 1} OF 2`}
        onClose={closeGuarded}
        busy={busy}
      >
        <form onSubmit={submit}>
          <div className="resource-form-body">
            <div className="planning-step-track">
              <span className={step === 0 ? "current" : ""}>
                1 · {el ? "Διαδρομή & ώρες" : "Route & times"}
              </span>
              <span className={step === 1 ? "current" : ""}>
                2 · {el ? "Ημέρες λειτουργίας" : "Operating days"}
              </span>
            </div>
            {error && (
              <p className="auth-error" role="alert">
                {error}
              </p>
            )}
            {step === 0 ? (
              <>
                <p className="resource-form-intro">
                  {el
                    ? "Χρησιμοποιήστε ονομασίες που αναγνωρίζει η ομάδα σας. Μπορείτε να προσθέσετε σταθμό εδώ."
                    : "Use names your team recognizes. You can add a station here without leaving this form."}
                </p>
                <Field label={el ? "Κωδικός δρομολογίου" : "Trip reference"}>
                  <input
                    required
                    maxLength={64}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </Field>
                <RecordPicker
                  kind="stations"
                  label={el ? "Σταθμός αναχώρησης" : "Origin station"}
                  value={origin}
                  onChange={setOrigin}
                  onCreate={
                    user?.permissions.includes("timetable.write")
                      ? (name) => setCreating({ field: "origin", name })
                      : undefined
                  }
                  createLabel={
                    el ? "Προσθήκη σταθμού αναχώρησης" : "Add origin station"
                  }
                />
                <RecordPicker
                  kind="stations"
                  label={el ? "Σταθμός άφιξης" : "Destination station"}
                  value={destination}
                  onChange={setDestination}
                  onCreate={
                    user?.permissions.includes("timetable.write")
                      ? (name) => setCreating({ field: "destination", name })
                      : undefined
                  }
                  createLabel={
                    el ? "Προσθήκη σταθμού άφιξης" : "Add destination station"
                  }
                />
                <div className="resource-form-grid">
                  <Field label={el ? "Ώρα αναχώρησης" : "Departure time"}>
                    <input
                      type="time"
                      required
                      value={departure}
                      onChange={(e) => setDeparture(e.target.value)}
                    />
                  </Field>
                  <Field label={el ? "Ώρα άφιξης" : "Arrival time"}>
                    <input
                      type="time"
                      required
                      value={arrival}
                      onChange={(e) => setArrival(e.target.value)}
                    />
                  </Field>
                </div>
                <Field label={el ? "Ημέρα άφιξης" : "Arrival day"}>
                  <select
                    value={offset}
                    onChange={(e) => setOffset(Number(e.target.value))}
                  >
                    <option value={0}>
                      {el ? "Την ίδια ημέρα" : "Same day"}
                    </option>
                    <option value={1}>
                      {el ? "Την επόμενη ημέρα" : "Next day"}
                    </option>
                    <option value={2}>
                      {el ? "Μετά από δύο ημέρες" : "Two days later"}
                    </option>
                  </select>
                </Field>
                <details>
                  <summary>
                    {el ? "Προαιρετική απόσταση" : "Optional distance"}
                  </summary>
                  <Field label={el ? "Απόσταση (χλμ.)" : "Distance (km)"}>
                    <input
                      type="number"
                      min={0}
                      max={10000}
                      step="any"
                      value={distance}
                      onChange={(e) => setDistance(e.target.value)}
                    />
                  </Field>
                </details>
              </>
            ) : (
              <>
                <p className="resource-form-intro">
                  {el
                    ? "Επιλέξτε τις πραγματικές ημέρες λειτουργίας και το διάστημα ισχύος. Οι εξαιρέσεις ελέγχονται ανά ημερομηνία."
                    : "Choose the actual operating days and validity period. Date-specific exceptions are reviewed separately."}
                </p>
                <fieldset className="planning-choices">
                  <legend>
                    {el ? "Ημέρες εβδομάδας" : "Days of the week"}
                  </legend>
                  {weekdays.map((names, i) => (
                    <label key={i}>
                      <input
                        type="checkbox"
                        checked={days.includes(i)}
                        onChange={(e) =>
                          setDays(
                            e.target.checked
                              ? [...days, i]
                              : days.filter((d) => d !== i),
                          )
                        }
                      />
                      {names[el ? 0 : 1]}
                    </label>
                  ))}
                </fieldset>
                <div className="resource-form-grid">
                  <Field label={el ? "Ισχύει από" : "Valid from"}>
                    <input
                      type="date"
                      required
                      value={from}
                      onChange={(e) => setFrom(e.target.value)}
                    />
                  </Field>
                  <Field label={el ? "Ισχύει έως" : "Valid until"}>
                    <input
                      type="date"
                      required
                      min={from}
                      value={until}
                      onChange={(e) => setUntil(e.target.value)}
                    />
                  </Field>
                </div>
                <fieldset className="planning-choices">
                  <legend>
                    {el
                      ? "Επιλέξιμες κατηγορίες οχημάτων"
                      : "Eligible vehicle categories"}
                  </legend>
                  {availableTypes.map((type) => (
                    <label key={type}>
                      <input
                        type="checkbox"
                        checked={types.includes(type)}
                        onChange={(e) =>
                          setTypes(
                            e.target.checked
                              ? [...types, type]
                              : types.filter((t) => t !== type),
                          )
                        }
                      />
                      {el ? "Κατηγορία" : "Type"} {type}
                    </label>
                  ))}
                  {!availableTypes.length && (
                    <p>
                      {el
                        ? "Προσθέστε πρώτα ένα όχημα με την κατηγορία του στον στόλο."
                        : "First add a vehicle with its category in Fleet."}
                    </p>
                  )}
                </fieldset>
                {row && (
                  <label className="planning-check">
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={(e) => setActive(e.target.checked)}
                    />
                    {el ? "Ενεργό δρομολόγιο" : "Active timetable"}
                  </label>
                )}
              </>
            )}
          </div>
          <footer>
            {step === 1 && (
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={() => setStep(0)}
              >
                {el ? "Πίσω" : "Back"}
              </button>
            )}
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={closeGuarded}
            >
              {el ? "Ακύρωση" : "Cancel"}
            </button>
            <button
              className="button primary"
              disabled={busy || (step === 1 && (!days.length || !types.length))}
            >
              {busy
                ? el
                  ? "Αποθήκευση…"
                  : "Saving…"
                : step === 0
                  ? el
                    ? "Συνέχεια"
                    : "Continue"
                  : el
                    ? "Αποθήκευση δρομολογίου"
                    : "Save timetable"}
            </button>
          </footer>
        </form>
      </Modal>
      {creating && (
        <ResourceForm
          kind="stations"
          record="new"
          initialValues={{ name_el: creating.name }}
          onClose={() => setCreating(null)}
          onSaved={(station) => {
            if (creating.field === "origin") setOrigin(station);
            else setDestination(station);
            setCreating(null);
          }}
        />
      )}
    </>
  );
}
