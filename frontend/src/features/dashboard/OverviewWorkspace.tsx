"use client";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  UsersRound,
  BusFront,
  CalendarDays,
  Link2,
  LayoutDashboard,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { BulkImportButton } from "../imports/BulkImportButton";
import { checked } from "../timetables/shared";
import type { PersistedRevision } from "../scheduling/revision-api";
import type { ShellTab } from "../../components/layout/Shell";

interface Readiness {
  service_date: string;
  timezone: string;
  drivers: number;
  vehicles: number;
  timetables: number;
  operating_trips: number;
  confirmed_pairings: number;
  pairings: number;
  inputs_ready: boolean;
  day_prepared: boolean;
}
export function OverviewWorkspace({
  serviceDate,
  revision,
  onDate,
  onOpen,
  onOpenStudio,
}: {
  serviceDate: string | null;
  revision: PersistedRevision | null;
  onDate: (date: string) => void;
  onOpen: (view: ShellTab, date?: string) => void;
  onOpenStudio: (date: string) => Promise<void>;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [data, setData] = useState<Readiness | null>(null),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0),
    [opening, setOpening] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    void apiFetch(
      `/api/v1/setup/readiness${serviceDate ? `?service_date=${serviceDate}` : ""}`,
      { signal: controller.signal },
    )
      .then((r) => checked<Readiness>(r, el))
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            el
              ? "Δεν ήταν δυνατός ο έλεγχος της ημέρας. Δοκιμάστε ξανά."
              : "This day could not be checked. Try again.",
          );
      });
    return () => controller.abort();
  }, [apiFetch, serviceDate, el, refresh]);
  if (!data)
    return (
      <section className="resource-workspace">
        <h1>{el ? "Η ημέρα εργασίας σας" : "Your working day"}</h1>
        {error ? (
          <div className="import-alert" role="alert">
            <p>{error}</p>
            <button
              className="button secondary"
              onClick={() => setRefresh((v) => v + 1)}
            >
              <RefreshCw size={16} />
              {el ? "Νέα προσπάθεια" : "Try again"}
            </button>
          </div>
        ) : (
          <p role="status">
            {el
              ? "Έλεγχος πραγματικών στοιχείων…"
              : "Checking your actual records…"}
          </p>
        )}
      </section>
    );
  const current =
    revision?.source_kind === "operational" &&
    revision.problem.service_date === data.service_date
      ? revision
      : null;
  const selectedDay = data.service_date;
  const canCreate = !!user?.permissions.includes("schedule.write");
  let destination: ShellTab = "planning",
    title = "",
    detail = "",
    action = "";
  if (!data.drivers) {
    destination = "drivers";
    title = el ? "Ξεκινήστε με τους οδηγούς σας." : "Start with your drivers.";
    detail = el
      ? "Περάστε πολλούς οδηγούς μαζί από Excel/CSV ή χρησιμοποιήστε τη σύντομη φόρμα για λίγες εγγραφές."
      : "Import many drivers together from Excel/CSV, or use a short form for a few records.";
    action = el ? "Προβολή οδηγών" : "Open drivers";
  } else if (!data.vehicles) {
    destination = "fleet";
    title = el ? "Προσθέστε τα οχήματά σας." : "Add your vehicles.";
    detail = el
      ? "Οι οδηγοί είναι αποθηκευμένοι. Συνεχίστε με τον πραγματικό στόλο."
      : "Your drivers are saved. Continue with your actual fleet.";
    action = el ? "Προβολή στόλου" : "Open fleet";
  } else if (!data.timetables || !data.operating_trips) {
    destination = "timetables";
    title = el
      ? "Ελέγξτε τα δρομολόγια αυτής της ημέρας."
      : "Review the services for this day.";
    detail = el
      ? "Τα τακτικά δρομολόγια καταχωρίζονται μία φορά με τις ημέρες λειτουργίας τους. Δεν χρειάζεται να τα ξαναγράφετε καθημερινά."
      : "Set recurring services once with their operating days. You do not need to re-enter them every day.";
    action = el ? "Προβολή δρομολογίων" : "Open timetables";
  } else if (
    !data.inputs_ready ||
    !data.day_prepared ||
    current?.source_review_required
  ) {
    title = el
      ? "Προετοιμάστε την ομάδα και τα στοιχεία της ημέρας."
      : "Prepare the crew and inputs for this day.";
    detail = el
      ? "Επιβεβαιώστε ποιοι εργάζονται και ελέγξτε τους χρόνους μετακίνησης κενού οχήματος. Τα αποθηκευμένα στοιχεία επαναχρησιμοποιούνται."
      : "Confirm who is working and review empty-bus travel times. Saved values are reused.";
    action = el ? "Προετοιμασία ημέρας" : "Prepare service day";
  } else if (current?.status === "published") {
    destination = "operations";
    title = el
      ? "Το πρόγραμμα έχει δημοσιευτεί."
      : "Your schedule is published.";
    detail = el
      ? "Χρησιμοποιήστε το δημοσιευμένο πρόγραμμα και καταγράψτε προαιρετικά όσα σας αναφέρει η ομάδα."
      : "Use the published schedule and optionally record updates reported by the team.";
    action = el ? "Καθημερινή λειτουργία" : "Open Operations";
  } else {
    destination = "scheduling";
    title = el
      ? "Η ημέρα είναι έτοιμη για προγραμματισμό."
      : "This day is ready for scheduling.";
    detail = current
      ? el
        ? "Ανοίξτε το αποθηκευμένο προσχέδιο, ελέγξτε τις προτάσεις και συνεχίστε με την έγκριση."
        : "Open the saved draft, review proposals and continue with approval."
      : el
        ? "Δημιουργήστε προσχέδιο από τα πραγματικά δρομολόγια, οχήματα και επιβεβαιωμένους οδηγούς."
        : "Create a draft from your actual services, vehicles and confirmed drivers.";
    action = el ? "Άνοιγμα Scheduling Studio" : "Open Scheduling Studio";
  }
  async function next() {
    if (destination === "scheduling" && !current && canCreate) {
      setOpening(true);
      setError("");
      try {
        await onOpenStudio(selectedDay);
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : el
              ? "Δεν άνοιξε το προσχέδιο."
              : "The draft could not be opened.",
        );
      } finally {
        setOpening(false);
      }
    } else onOpen(destination, selectedDay);
  }
  const metrics = [
    {
      icon: UsersRound,
      label: el ? "Αποθηκευμένοι οδηγοί" : "Registered drivers",
      value: data.drivers,
    },
    {
      icon: BusFront,
      label: el ? "Αποθηκευμένα οχήματα" : "Registered vehicles",
      value: data.vehicles,
    },
    {
      icon: CalendarDays,
      label: el ? "Δρομολόγια αυτής της ημέρας" : "Services for this day",
      value: data.operating_trips,
    },
    {
      icon: Link2,
      label: el ? "Επιβεβαιωμένα ζεύγη" : "Confirmed crews",
      value: `${data.confirmed_pairings} / ${data.pairings}`,
    },
  ];
  const dayLabel = new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
    dateStyle: "full",
    timeZone: "UTC",
  }).format(new Date(data.service_date + "T12:00:00Z"));
  return (
    <section className="resource-workspace overview-workspace">
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "Ο ΧΩΡΟΣ ΕΡΓΑΣΙΑΣ ΣΑΣ" : "YOUR WORKSPACE"}
          </span>
          <h1>{el ? "Η ημέρα εργασίας σας" : "Your working day"}</h1>
          <p>
            {dayLabel} · {data.timezone}
          </p>
        </div>
        <label className="overview-date">
          {el ? "Ημερομηνία υπηρεσίας" : "Service date"}
          <input
            type="date"
            value={data.service_date}
            disabled={opening}
            onChange={(event) => {
              if (event.target.value) onDate(event.target.value);
            }}
          />
        </label>
      </header>
      <div className="overview-metrics">
        {metrics.map(({ icon: Icon, label, value }) => (
          <article className="overview-metric" key={label}>
            <span className="overview-metric-icon">
              <Icon size={21} />
            </span>
            <div>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          </article>
        ))}
      </div>
      {error && (
        <p className="import-alert" role="alert">
          {error}
        </p>
      )}
      <section
        className="overview-next-action"
        aria-label={el ? "Το επόμενο βήμα σας" : "Your next step"}
      >
        <div className="overview-next-icon">
          <LayoutDashboard size={25} />
        </div>
        <div>
          <span className="resource-eyebrow">
            {el ? "ΤΟ ΕΠΟΜΕΝΟ ΒΗΜΑ ΣΑΣ" : "YOUR NEXT STEP"}
          </span>
          <h2>{title}</h2>
          <p>{detail}</p>
          <div className="resource-heading-actions">
            <button
              className="button primary"
              disabled={opening}
              onClick={() => void next()}
            >
              {opening ? (el ? "Άνοιγμα…" : "Opening…") : action}
              <ArrowRight size={16} />
            </button>
            {!data.drivers && (
              <BulkImportButton entity="drivers" returnTo="drivers" />
            )}
          </div>
          {!canCreate && destination === "scheduling" && !current && (
            <p className="resource-help">
              {el
                ? "Ο υπεύθυνος προγραμματισμού μπορεί να δημιουργήσει το προσχέδιο. Μπορείτε να ελέγξετε τα στοιχεία."
                : "A dispatcher can create the draft. You can review the inputs."}
            </p>
          )}
        </div>
      </section>
      {current && (
        <section className="resource-panel overview-schedule">
          <h2>
            {el
              ? "Αποθηκευμένο πρόγραμμα αυτής της ημέρας"
              : "Saved schedule for this day"}
          </h2>
          <div className="overview-schedule-facts">
            <div>
              <span>{el ? "Ανατεθειμένα δρομολόγια" : "Assigned trips"}</span>
              <strong>
                {
                  current.assignments.filter(
                    (item) => item.resource_id !== "UNASSIGNED",
                  ).length
                }{" "}
                / {current.problem.trips.length}
              </strong>
            </div>
            <div>
              <span>{el ? "Χωρίς ανάθεση" : "Unassigned Trips"}</span>
              <strong>{current.verification.unassigned_trips.length}</strong>
            </div>
            <div>
              <span>{el ? "Ευρήματα ελέγχου" : "Check findings"}</span>
              <strong>{current.verification.violations.length}</strong>
            </div>
          </div>
          <p className="resource-help">
            {el
              ? "Η κάλυψη και τα ευρήματα προέρχονται από το αποθηκευμένο πρόγραμμα και τον ανεξάρτητο έλεγχο."
              : "Coverage and findings come from the saved schedule and independent verification."}
          </p>
        </section>
      )}
      <div className="overview-links">
        <button className="button secondary" onClick={() => onOpen("drivers")}>
          {el ? "Οδηγοί" : "Drivers"}
        </button>
        <button className="button secondary" onClick={() => onOpen("fleet")}>
          {el ? "Στόλος" : "Fleet"}
        </button>
        <button
          className="button secondary"
          onClick={() => onOpen("timetables")}
        >
          {el ? "Τακτικά δρομολόγια" : "Recurring services"}
        </button>
        {user?.permissions.includes("imports.read") && (
          <button
            className="button secondary"
            onClick={() => onOpen("imports")}
          >
            {el ? "Εισαγωγές στοιχείων" : "Data imports"}
          </button>
        )}
      </div>
    </section>
  );
}
