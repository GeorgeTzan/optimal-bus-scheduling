"use client";
import {
  useCallback,
  useEffect,
  useState,
  useRef,
  type FormEvent,
} from "react";
import { Check, CalendarDays, Plus, ArrowRight } from "lucide-react";
import { TransferWorkspace } from "./TransferWorkspace";
import { serviceDay } from "../navigation/workspace-location";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { Resource } from "../resources/ResourceWorkspace";
import { RecordPicker } from "../resources/RecordPicker";
import { checked, Field, Modal, stationName } from "./shared";
interface Pairing {
  id: number;
  version: number;
  is_active: boolean;
  needs_review: boolean;
  driver_name: string;
  driver_code: string;
  vehicle_label: string;
  bus_type: string;
  home_station: Resource;
  driver_version: number;
  vehicle_version: number;
  home_station_version: number;
}
interface Issue {
  code: string;
  message: string;
  trip_code?: string;
  template_id?: number;
  field?: string;
  clock_time?: string;
  drivers?: { driver_id: number; driver_name: string }[];
}
interface Readiness {
  service_date: string;
  timezone: string;
  drivers: number;
  vehicles: number;
  timetables: number;
  operating_trips: number;
  confirmed_pairings: number;
  inputs_ready: boolean;
  day_prepared: boolean;
  template_versions: Record<string, number>;
  issues: Issue[];
  missing_transfers: { origin: Resource; destination: Resource }[];
  missing_transfer_count: number;
}
interface DatedTrip {
  id: number;
  trip_code: string;
  departure_local: string;
  arrival_local: string;
  arrival_day_offset: number;
  duration_minutes: number;
  origin: Resource;
  destination: Resource;
}
export function ServiceDayWorkspace({
  onTimetables,
  onOffice,
  onOpenStudio,
  serviceDate,
  onServiceDateChange,
}: {
  onTimetables: () => void;
  onOffice?: () => void;
  onOpenStudio?: (date: string) => Promise<void>;
  serviceDate?: string | null;
  onServiceDateChange?: (date: string, replace?: boolean) => boolean;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el",
    canPair = !!user?.permissions.includes("schedule.write"),
    canTimetable = !!user?.permissions.includes("timetable.write");
  const key = `ktel-service-date:${user?.ktelId}:${user?.id}`;
  const [date, setDate] = useState(() => {
      try {
        return (
          serviceDate ||
          serviceDay(
            new URL(window.location.href).searchParams.get("service_date"),
          ) ||
          serviceDay(localStorage.getItem(key)) ||
          ""
        );
      } catch {
        return serviceDate || "";
      }
    }),
    [ready, setReady] = useState<Readiness | null>(null),
    [pairs, setPairs] = useState<Pairing[]>([]),
    [trips, setTrips] = useState<DatedTrip[]>([]),
    [adding, setAdding] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [copyDate, setCopyDate] = useState(""),
    [hasTransferEdits, setHasTransferEdits] = useState(false),
    [showConfirmedCrews, setShowConfirmedCrews] = useState(false),
    [exception, setException] = useState<Issue | null>(null);
  const currentDate = useRef(date);
  currentDate.current = date;
  const dateChanged = useRef(onServiceDateChange);
  dateChanged.current = onServiceDateChange;
  useEffect(() => {
    if (serviceDate) setDate(serviceDate);
  }, [serviceDate]);
  useEffect(() => {
    if (serviceDay(date)) {
      const previous = new Date(date + "T12:00:00Z");
      previous.setUTCDate(previous.getUTCDate() - 1);
      setCopyDate(previous.toISOString().slice(0, 10));
    }
  }, [date]);
  const load = useCallback(
    async (signal?: AbortSignal, silent = false) => {
      if (date && !serviceDay(date)) return;
      if (!silent) setLoading(true);
      setError("");
      try {
        const a = await apiFetch(
          `/api/v1/setup/readiness${date ? `?service_date=${date}` : ""}`,
          { signal },
        ).then((r) => checked<Readiness>(r, el));
        if (signal?.aborted || currentDate.current !== date) return;
        if (!date) {
          dateChanged.current?.(a.service_date, true);
          setDate(a.service_date);
          return;
        }
        const [b, c] = await Promise.all([
          apiFetch(`/api/v1/pairings?service_date=${date}`, { signal }).then(
            (r) => checked<{ items: Pairing[] }>(r, el),
          ),
          apiFetch(`/api/v1/timetables/dated-trips?service_date=${date}`, {
            signal,
          }).then((r) => checked<{ items: DatedTrip[] }>(r, el)),
        ]);
        if (!signal?.aborted && currentDate.current === date) {
          setReady(a);
          setPairs(b.items.filter((p) => p.is_active));
          setTrips(c.items);
        }
      } catch (e) {
        if (!signal?.aborted && currentDate.current === date)
          setError(
            e instanceof Error
              ? e.message
              : el
                ? "Αποτυχία φόρτωσης."
                : "Could not load this date.",
          );
      } finally {
        if (!signal?.aborted && currentDate.current === date) setLoading(false);
      }
    },
    [apiFetch, date, el],
  );
  useEffect(() => {
    const c = new AbortController();
    setReady(null);
    setPairs([]);
    setShowConfirmedCrews(false);
    setTrips([]);
    setNotice("");
    void load(c.signal);
    try {
      if (date) localStorage.setItem(key, date);
    } catch {}
    return () => c.abort();
  }, [load, key, date]);
  const mutate = async (path: string, body: unknown, method = "POST") => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await checked(
        await apiFetch(path, { method, body: JSON.stringify(body) }),
        el,
      );
      if (currentDate.current !== date) return false;
      await load(undefined, true);
      return true;
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : el
            ? "Η αλλαγή δεν αποθηκεύτηκε."
            : "Your change was not saved.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  };
  const issueText = (issue: Issue) => {
    const messages: Record<string, [string, string]> = {
      no_services: [
        "Δεν εκτελούνται δρομολόγια σε αυτή την ημερομηνία. Επιλέξτε άλλη ημέρα ή ενημερώστε το πρόγραμμα.",
        "No services run on this date. Choose another day or update your timetable.",
      ],
      pairings_required: [
        "Επιλέξτε οδηγούς, οχήματα και αρχικές έδρες για αυτή την ημέρα.",
        "Choose drivers, vehicles and starting bases for this day.",
      ],
      pairing_needs_review: [
        "Ελέγξτε και επιβεβαιώστε τα ζεύγη που επισημαίνονται παρακάτω.",
        "Review and confirm the highlighted pairings below.",
      ],
      no_eligible_vehicle: [
        "Επιβεβαιώστε όχημα κατάλληλης κατηγορίας για αυτό το δρομολόγιο.",
        "Confirm a suitable vehicle category for this service.",
      ],
      working_windows_required: [
        "Δεν έχει καταχωριστεί ωράριο εργασίας για τους οδηγούς παρακάτω. Καταχωρίστε το στην ενότητα Γραφείο.",
        "Working time is not recorded for the drivers below. Record it in the Office section.",
      ],
      connection_time_conflict: [
        "Τα συνδεδεμένα δρομολόγια δεν αφήνουν χρόνο μετάβασης για το ίδιο όχημα. Ελέγξτε τις ώρες ή τη σύνδεση.",
        "Linked trips leave too little time for the same vehicle. Review their times or remove the connection.",
      ],
      connection_types_conflict: [
        "Τα συνδεδεμένα δρομολόγια χρειάζονται κοινή επιλέξιμη κατηγορία οχήματος.",
        "Linked trips need a common eligible vehicle category.",
      ],
      connection_vehicle_required: [
        "Επιβεβαιώστε ένα όχημα κατάλληλο για όλα τα συνδεδεμένα δρομολόγια.",
        "Confirm a vehicle that can operate all linked trips.",
      ],
      calendar_incomplete: [
        "Συμπληρώστε τις ημέρες και το διάστημα ισχύος στο δρομολόγιο.",
        "Complete the operating days and validity period in this timetable.",
      ],
      ambiguous_local_time: [
        "Η ώρα εμφανίζεται δύο φορές λόγω αλλαγής ώρας. Επιλέξτε ποια εννοείτε.",
        "The clock repeats on this date. Choose which occurrence to use.",
      ],
      nonexistent_local_time: [
        "Η ώρα δεν υπάρχει λόγω αλλαγής ώρας. Επιλέξτε άλλη ώρα για αυτή την ημέρα.",
        "This clock time is skipped on this date. Choose a different time for this day.",
      ],
    };
    return (
      messages[issue.code]?.[el ? 0 : 1] ??
      (el
        ? "Ελέγξτε τις ώρες αυτού του δρομολογίου."
        : "Review the times for this service.")
    );
  };
  return (
    <section className="resource-workspace">
      <div className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΜΙΑ ΗΜΕΡΑ ΤΗ ΦΟΡΑ" : "ONE DAY AT A TIME"}
          </span>
          <h1>{el ? "Προετοιμασία ημέρας" : "Prepare your service day"}</h1>
          <p>
            {el
              ? "Ελέγξτε ποιος οδηγεί, με ποιο όχημα και από πού ξεκινά."
              : "Check who is driving, which vehicle they use and where they start."}
          </p>
        </div>
        <Field label={el ? "Ημερομηνία υπηρεσίας" : "Service date"}>
          <input
            type="date"
            value={date}
            disabled={busy}
            onChange={(e) => {
              const selected = e.target.value;
              if (!serviceDay(selected)) return;
              if (onServiceDateChange && !onServiceDateChange(selected)) return;
              setDate(selected);
            }}
          />
        </Field>
      </div>
      {(!canPair || !canTimetable) && (
        <p className="resource-help">
          {!canPair &&
            (el
              ? "Ο υπεύθυνος προγραμματισμού μπορεί να επιβεβαιώσει τα ζεύγη οδηγών–οχημάτων. "
              : "Your scheduling manager can confirm driver–vehicle pairings. ")}
          {!canTimetable &&
            (el
              ? "Ο υπεύθυνος δρομολογίων μπορεί να συμπληρώσει τους χρόνους μετακίνησης και να προετοιμάσει τα δρομολόγια της ημέρας."
              : "Your timetable manager can add travel times and prepare this day’s trips.")}
        </p>
      )}
      {error && (
        <p className="auth-error" role="alert">
          {error}
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void load()}
          >
            {el ? "Ανανέωση" : "Refresh"}
          </button>
        </p>
      )}
      {notice && (
        <p className="planning-notice" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      {loading ? (
        <p className="resource-empty" role="status">
          {el ? "Έλεγχος ημέρας…" : "Checking this day…"}
        </p>
      ) : (
        ready && (
          <>
            <div className="planning-guide">
              <CalendarDays size={23} />
              <div>
                <strong>
                  {ready.operating_trips}{" "}
                  {el
                    ? ready.operating_trips === 1
                      ? "δρομολόγιο για αυτή την ημέρα"
                      : "δρομολόγια για αυτή την ημέρα"
                    : ready.operating_trips === 1
                      ? "service for this day"
                      : "services for this day"}
                </strong>
                <p>
                  {ready.timezone} ·{" "}
                  {el
                    ? "Οι αλλαγές σας αποθηκεύονται ανά βήμα."
                    : "Your changes are saved at each step."}
                </p>
              </div>
              <button className="button secondary" onClick={onTimetables}>
                {el ? "Δείτε τα δρομολόγια" : "Review timetables"}
                <ArrowRight size={15} />
              </button>
            </div>
            <div className="planning-section">
              <div className="planning-section-heading">
                <span className="planning-number">1</span>
                <div>
                  <h2>{el ? "Οδηγοί & οχήματα" : "Drivers & vehicles"}</h2>
                  <p>
                    {el
                      ? "Επιβεβαιώστε τα πραγματικά ζεύγη για τη συγκεκριμένη ημερομηνία."
                      : "Confirm the actual pairings for this date."}
                  </p>
                </div>
                <button
                  className="button secondary"
                  disabled={
                    !canPair || busy || !ready.drivers || !ready.vehicles
                  }
                  onClick={() => setAdding(true)}
                >
                  <Plus size={15} />
                  {el ? "Προσθήκη ζεύγους" : "Add pairing"}
                </button>
              </div>
              {!pairs.length ? (
                <div className="planning-empty">
                  <p>
                    {!ready.drivers || !ready.vehicles
                      ? el
                        ? "Προσθέστε πρώτα τους οδηγούς και τα οχήματά σας από το μενού."
                        : "Add your drivers and vehicles from the navigation first."
                      : el
                        ? "Δεν έχουν επιλεγεί ζεύγη για αυτή την ημέρα."
                        : "No pairings selected for this day yet."}
                  </p>
                  <div className="planning-copy-source">
                    <Field
                      label={
                        el
                          ? "Αντιγραφή ομάδας από ημερομηνία"
                          : "Copy crews from date"
                      }
                    >
                      <input
                        type="date"
                        value={copyDate}
                        disabled={busy || !canPair}
                        onChange={(event) => setCopyDate(event.target.value)}
                      />
                    </Field>
                    <button
                      className="button secondary"
                      disabled={
                        !canPair ||
                        busy ||
                        !serviceDay(copyDate) ||
                        copyDate === date
                      }
                      onClick={() =>
                        void mutate("/api/v1/pairings/copy", {
                          from_date: copyDate,
                          to_date: date,
                        })
                      }
                    >
                      {el ? "Αντιγραφή για έλεγχο" : "Copy crews for review"}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                <div className="planning-crew-summary"><p>{el ? `${ready.confirmed_pairings} επιβεβαιωμένα · ${pairs.length-ready.confirmed_pairings} χρειάζονται έλεγχο` : `${ready.confirmed_pairings} confirmed · ${pairs.length-ready.confirmed_pairings} need review`}</p>{ready.confirmed_pairings>0 && <button className="button secondary" aria-expanded={showConfirmedCrews} onClick={()=>setShowConfirmedCrews(value=>!value)}>{showConfirmedCrews ? (el?"Απόκρυψη επιβεβαιωμένων":"Hide confirmed crews") : (el?`Προβολή επιβεβαιωμένων (${ready.confirmed_pairings})`:`Show confirmed crews (${ready.confirmed_pairings})`)}</button>}</div>
                <div className="planning-pairings">
                  {pairs.filter(p=>showConfirmedCrews||p.needs_review).map((p) => (
                    <article
                      className={`planning-pairing ${p.needs_review ? "needs-review" : ""}`}
                      key={p.id}
                    >
                      <div>
                        <strong>{p.driver_name}</strong>
                        <small>{p.driver_code}</small>
                      </div>
                      <span className="planning-pair-arrow">→</span>
                      <div>
                        <strong>{p.vehicle_label}</strong>
                        <small>
                          {el ? "Κατηγορία" : "Type"} {p.bus_type} ·{" "}
                          {stationName(p.home_station, el)}
                        </small>
                      </div>
                      <span className="resource-status">
                        {p.needs_review
                          ? el
                            ? "Χρειάζεται επιβεβαίωση"
                            : "Needs confirmation"
                          : el
                            ? "Επιβεβαιωμένο"
                            : "Confirmed"}
                      </span>
                      {p.needs_review && (
                        <button
                          className="button secondary"
                          disabled={busy || !canPair}
                          onClick={() =>
                            void mutate(
                              `/api/v1/pairings/${p.id}`,
                              {
                                version: p.version,
                                driver_version: p.driver_version,
                                vehicle_version: p.vehicle_version,
                                home_station_version: p.home_station_version,
                                confirm: true,
                              },
                              "PATCH",
                            )
                          }
                        >
                          {el ? "Επιβεβαίωση" : "Confirm"}
                        </button>
                      )}
                      <button
                        className="button secondary"
                        disabled={busy || !canPair}
                        onClick={() =>
                          void mutate(
                            `/api/v1/pairings/${p.id}`,
                            { version: p.version, is_active: false },
                            "PATCH",
                          )
                        }
                      >
                        {el ? "Αφαίρεση" : "Remove"}
                      </button>
                    </article>
                  ))}
                </div>
                </>
              )}
            </div>
            <TransferWorkspace
              date={date}
              refreshToken={ready}
              onDirtyChange={setHasTransferEdits}
              onSaved={() => load(undefined, true)}
            />
            <div className="planning-section">
              <div className="planning-section-heading">
                <span className="planning-number">3</span>
                <div>
                  <h2>
                    {el
                      ? "Έλεγχος & αποθήκευση ημέρας"
                      : "Review & prepare the day"}
                  </h2>
                  <p>
                    {el
                      ? "Δημιουργήστε τα συγκεκριμένα δρομολόγια χωρίς να αλλάξετε το εβδομαδιαίο πρόγραμμα."
                      : "Save the dated trips while keeping your recurring timetable."}
                  </p>
                </div>
              </div>
              {ready.issues.length > 0 && (
                <ul className="planning-issues">
                  {ready.issues
                    .filter(
                      (issue) =>
                        issue.code !== "no_eligible_vehicle" ||
                        (ready.confirmed_pairings > 0 &&
                          ready.confirmed_pairings === pairs.length),
                    )
                    .map((issue, i) => (
                      <li key={i}>
                        <div>
                          {issue.trip_code && (
                            <strong>{issue.trip_code} · </strong>
                          )}
                          {issueText(issue)}
                        </div>
                        {issue.code === "working_windows_required" && (
                          <>
                            <small>{issue.drivers?.map((driver) => driver.driver_name).join(", ")}</small>
                            {onOffice && <button className="button primary" onClick={onOffice}>{el ? "Καταχώριση ωραρίου" : "Record working time"}</button>}
                          </>
                        )}
                        {issue.template_id &&
                          [
                            "ambiguous_local_time",
                            "nonexistent_local_time",
                          ].includes(issue.code) && (
                            <button
                              className="button secondary"
                              disabled={!canTimetable || busy}
                              onClick={() => setException(issue)}
                            >
                              {el ? "Έλεγχος ώρας" : "Review clock time"}
                            </button>
                          )}
                      </li>
                    ))}
                </ul>
              )}
              <div className="planning-section-footer">
                <p>
                  {ready.day_prepared
                    ? el
                      ? "Τα δρομολόγια αυτής της ημέρας είναι αποθηκευμένα."
                      : "This day’s trips are saved."
                    : el
                      ? "Συμπληρώστε τα παραπάνω για να προετοιμάσετε την ημέρα."
                      : "Complete the steps above to prepare this day."}
                </p>
                <button
                  className={
                    ready.day_prepared ? "button secondary" : "button primary"
                  }
                  disabled={
                    busy ||
                    !canTimetable ||
                    !ready.inputs_ready ||
                    hasTransferEdits
                  }
                  onClick={async () => {
                    if (
                      await mutate("/api/v1/timetables/materialize", {
                        service_date: date,
                        template_versions: ready.template_versions,
                      })
                    )
                      setNotice(
                        el
                          ? "Η ημέρα προετοιμάστηκε και αποθηκεύτηκε."
                          : "Service day prepared and saved.",
                      );
                  }}
                >
                  {busy
                    ? el
                      ? "Αποθήκευση…"
                      : "Saving…"
                    : el
                      ? "Προετοιμασία ημέρας"
                      : "Prepare service day"}
                </button>
              </div>
              {hasTransferEdits && (
                <p className="resource-help" role="status">
                  {el
                    ? "Αποθηκεύστε τις αλλαγές στους χρόνους μετακίνησης πριν προετοιμάσετε ή ανοίξετε το πρόγραμμα."
                    : "Save your travel-time edits before preparing or opening the schedule."}
                </p>
              )}
              {ready.day_prepared && ready.inputs_ready && onOpenStudio && (
                <div className="planning-section-footer">
                  <p>
                    {el
                      ? "Συνεχίστε με τις αναθέσεις στο πρόγραμμά σας."
                      : "Continue with assignments in your schedule."}
                  </p>
                  <button
                    className="button primary"
                    disabled={busy || !canPair || hasTransferEdits}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await onOpenStudio(date);
                      } catch (reason) {
                        setError(
                          reason instanceof Error
                            ? reason.message
                            : el
                              ? "Δεν ανοίχτηκε το προσχέδιο."
                              : "The draft could not be opened.",
                        );
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {el
                      ? "Άνοιγμα Scheduling Studio"
                      : "Open Scheduling Studio"}
                    <ArrowRight size={15} />
                  </button>
                </div>
              )}
              {trips.length > 0 && (
                <div
                  className="planning-table-scroll"
                  data-testid="prepared-trip-list"
                >
                  <table className="resource-table">
                    <thead>
                      <tr>
                        {[
                          el ? "Δρομολόγιο" : "Service",
                          el ? "Διαδρομή" : "Route",
                          el ? "Ώρες" : "Local times",
                          el ? "Διάρκεια" : "Duration",
                        ].map((x) => (
                          <th key={x}>{x}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {trips.map((t) => (
                        <tr key={t.id}>
                          <td>
                            <strong>{t.trip_code}</strong>
                          </td>
                          <td>
                            {stationName(t.origin, el)} →{" "}
                            {stationName(t.destination, el)}
                          </td>
                          <td>
                            {t.departure_local} — {t.arrival_local}
                            {t.arrival_day_offset > 0
                              ? ` (+${t.arrival_day_offset})`
                              : ""}
                          </td>
                          <td>
                            {t.duration_minutes} {el ? "λεπτά" : "min"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )
      )}
      {adding && (
        <PairingForm
          date={date}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            void load();
          }}
        />
      )}
      {exception && (
        <ClockReview
          issue={exception}
          date={date}
          onClose={() => setException(null)}
          onSaved={() => {
            setException(null);
            void load();
          }}
        />
      )}
    </section>
  );
}
function PairingForm({
  date,
  onClose,
  onSaved,
}: {
  date: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [driver, setDriver] = useState<Resource | null>(null),
    [vehicle, setVehicle] = useState<Resource | null>(null),
    [home, setHome] = useState<Resource | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!driver || !vehicle || !home) return;
    setBusy(true);
    try {
      await checked(
        await apiFetch("/api/v1/pairings", {
          method: "POST",
          body: JSON.stringify({
            service_date: date,
            driver_id: driver.id,
            vehicle_id: vehicle.id,
            home_station_id: home.id,
            driver_version: driver.version,
            vehicle_version: vehicle.version,
            home_station_version: home.version,
            confirm: true,
          }),
        }),
        el,
      );
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={el ? "Προσθήκη ζεύγους" : "Add pairing"}
      subtitle={date}
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Επιλέξτε τις αποθηκευμένες εγγραφές και επιβεβαιώστε την αρχική έδρα για αυτή την ημέρα."
              : "Choose saved records and confirm the starting base for this day."}
          </p>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <RecordPicker
            kind="drivers"
            label={el ? "Οδηγός" : "Driver"}
            value={driver}
            onChange={setDriver}
          />
          <RecordPicker
            kind="vehicles"
            label={el ? "Όχημα" : "Vehicle"}
            value={vehicle}
            onChange={setVehicle}
          />
          <RecordPicker
            kind="stations"
            label={el ? "Αρχική έδρα" : "Starting base"}
            value={home}
            onChange={setHome}
          />
        </div>
        <footer>
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button
            className="button primary"
            disabled={busy || !driver || !vehicle || !home}
          >
            {busy
              ? el
                ? "Αποθήκευση…"
                : "Saving…"
              : el
                ? "Επιβεβαίωση ζεύγους"
                : "Confirm pairing"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
interface SavedException {
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
function ClockReview({
  issue,
  date,
  onClose,
  onSaved,
}: {
  issue: Issue;
  date: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [saved, setSaved] = useState<SavedException | null>(null),
    [choice, setChoice] = useState(""),
    [clock, setClock] = useState(""),
    [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const ambiguous = issue.code === "ambiguous_local_time",
    start = issue.field === "departure_time";
  useEffect(() => {
    let alive = true;
    void apiFetch(`/api/v1/timetables/${issue.template_id}/exceptions`)
      .then((r) => checked<{ items: SavedException[] }>(r, el))
      .then((data) => {
        if (alive) {
          setSaved(data.items.find((x) => x.service_date === date) ?? null);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (alive)
          setError(
            el
              ? "Δεν φορτώθηκαν οι εξαιρέσεις. Ανοίξτε ξανά για νέα προσπάθεια."
              : "Exceptions could not load. Reopen to try again.",
          );
      });
    return () => {
      alive = false;
    };
  }, [apiFetch, date, issue.template_id, el]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = {
        ...(saved ? { version: saved.version } : { service_date: date }),
        action: saved?.action ?? "inherit",
        [ambiguous
          ? start
            ? "fold_start"
            : "fold_end"
          : start
            ? "departure_time"
            : "arrival_time"]: ambiguous ? Number(choice) : clock,
      };
      await checked(
        await apiFetch(
          `/api/v1/timetables/${issue.template_id}/exceptions${saved ? "/" + saved.id : ""}`,
          { method: saved ? "PATCH" : "POST", body: JSON.stringify(data) },
        ),
        el,
      );
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={el ? "Έλεγχος τοπικής ώρας" : "Review local clock time"}
      subtitle={`${issue.trip_code} · ${date}`}
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={submit}>
        <div className="resource-form-body">
          <p>
            {el
              ? "Η αλλαγή ισχύει μόνο για αυτή την ημερομηνία."
              : "This change applies only to this date."}{" "}
            {issue.clock_time}
          </p>
          {error && (
            <p role="alert" className="auth-error">
              {error}
            </p>
          )}
          {ambiguous ? (
            <Field label={el ? "Ποια εμφάνιση της ώρας;" : "Which occurrence?"}>
              <select
                required
                value={choice}
                onChange={(e) => setChoice(e.target.value)}
              >
                <option value="">{el ? "Επιλέξτε…" : "Choose…"}</option>
                <option value="0">
                  {el ? "Πρώτη (νωρίτερα)" : "First (earlier)"}
                </option>
                <option value="1">
                  {el ? "Δεύτερη (αργότερα)" : "Second (later)"}
                </option>
              </select>
            </Field>
          ) : (
            <Field label={el ? "Νέα ώρα" : "Replacement time"}>
              <input
                type="time"
                required
                value={clock}
                onChange={(e) => setClock(e.target.value)}
              />
            </Field>
          )}
        </div>
        <footer>
          <button className="button primary" disabled={!loaded || busy}>
            {el ? "Αποθήκευση εξαίρεσης" : "Save date exception"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
