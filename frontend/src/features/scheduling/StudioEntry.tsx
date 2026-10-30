"use client";
import { useEffect, useState } from "react";
import { CalendarDays, ArrowRight, Route } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { SetupWelcome } from "../resources/SetupWelcome";
import { Field, checked } from "../timetables/shared";

type SetupTab = "drivers" | "fleet" | "timetables" | "planning" | "imports";
interface DayReadiness {
  drivers: number;
  vehicles: number;
  timetables: number;
  service_date: string;
  operating_trips: number;
  inputs_ready: boolean;
  day_prepared: boolean;
  timezone: string;
  issues: { code: string }[];
}
export function StudioEntry({
  serviceDate,
  busy,
  onDate,
  onCreate,
  onOpen,
}: {
  serviceDate: string | null;
  busy: boolean;
  onDate: (date: string) => void;
  onCreate: (date: string) => Promise<void>;
  onOpen: (tab: SetupTab, date?: string) => void;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [createError, setCreateError] = useState<string | null>(null);
  const [data, setData] = useState<DayReadiness | null>(null),
    [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(false);
    void apiFetch(
      `/api/v1/setup/readiness${serviceDate ? `?service_date=${serviceDate}` : ""}`,
      { signal: controller.signal },
    )
      .then((response) => checked<DayReadiness>(response, el))
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [apiFetch, serviceDate, el]);
  if (error)
    return (
      <section className="resource-empty">
        <p role="alert">
          {el
            ? "Δεν μπορέσαμε να ελέγξουμε αυτή την ημέρα."
            : "We could not check this service day."}
        </p>
        <button
          className="button secondary"
          onClick={() => window.location.reload()}
        >
          {el ? "Νέα προσπάθεια" : "Try again"}
        </button>
      </section>
    );
  if (!data)
    return (
      <p className="resource-empty" role="status">
        {el ? "Προετοιμασία του χώρου σας…" : "Opening your workspace…"}
      </p>
    );
  if (!data.drivers || !data.vehicles || !data.timetables)
    return <SetupWelcome onOpen={(tab) => onOpen(tab)} />;
  const noServices = data.issues.some((issue) => issue.code === "no_services"),
    ready = data.inputs_ready && data.day_prepared;
  return (
    <section className="resource-workspace studio-entry">
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΣΧΕΔΙΑΣΜΟΣ & ΚΑΤΑΝΟΜΗ" : "PLANNING & DISPATCH"}
          </span>
          <h1>Scheduling Studio</h1>
          <p>
            {el
              ? "Το δικό σας πρόγραμμα, μία ημέρα τη φορά."
              : "Your own schedule, one day at a time."}
          </p>
        </div>
        <Field label={el ? "Ημερομηνία υπηρεσίας" : "Service date"}>
          <input
            type="date"
            value={data.service_date}
            disabled={busy}
            onChange={(event) => {
              if (event.target.value) onDate(event.target.value);
            }}
          />
        </Field>
      </header>
      {createError && (
        <p className="auth-error" role="alert">
          {createError}
        </p>
      )}
      <div className="studio-entry-card">
        <span className="studio-entry-icon">
          <CalendarDays size={28} />
        </span>
        <span className="resource-eyebrow">{data.timezone}</span>
        <h2>
          {noServices
            ? el
              ? "Δεν υπάρχουν δρομολόγια για αυτή την ημέρα."
              : "No services run on this date."
            : ready
              ? el
                ? "Η ημέρα σας είναι έτοιμη."
                : "Your service day is ready."
              : el
                ? "Ας προετοιμάσουμε αυτή την ημέρα."
                : "Let’s prepare this service day."}
        </h2>
        <p>
          {noServices
            ? el
              ? "Επιλέξτε άλλη ημερομηνία ή ελέγξτε τις ημέρες λειτουργίας στο πρόγραμμα."
              : "Choose another date or review the operating days in your timetable."
            : ready
              ? el
                ? "Ανοίξτε ένα προσχέδιο με τα αποθηκευμένα δρομολόγια, οχήματα και επιβεβαιωμένους οδηγούς σας."
                : "Open a draft with your saved services, vehicles and confirmed drivers."
              : el
                ? "Επιβεβαιώστε τους οδηγούς και τα οχήματα, ελέγξτε τους χρόνους μετακίνησης και αποθηκεύστε τα δρομολόγια της ημέρας."
                : "Confirm drivers and vehicles, review travel times and save the day’s trips."}
        </p>
        {ready && user?.permissions.includes("schedule.write") ? (
          <button
            className="button primary"
            disabled={busy}
            onClick={() =>
              void onCreate(data.service_date).catch((reason) =>
                setCreateError(
                  reason instanceof Error
                    ? reason.message
                    : el
                      ? "Δεν ανοίχτηκε το προσχέδιο."
                      : "The draft could not be opened.",
                ),
              )
            }
          >
            {busy
              ? el
                ? "Άνοιγμα…"
                : "Opening…"
              : el
                ? "Άνοιγμα Scheduling Studio"
                : "Open Scheduling Studio"}
            <ArrowRight size={15} />
          </button>
        ) : (
          <button
            className="button primary"
            disabled={busy}
            onClick={() =>
              onOpen(noServices ? "timetables" : "planning", data.service_date)
            }
          >
            {noServices
              ? el
                ? "Έλεγχος δρομολογίων"
                : "Review timetables"
              : el
                ? "Προετοιμασία ημέρας"
                : "Prepare service day"}
            {noServices ? <Route size={15} /> : <ArrowRight size={15} />}
          </button>
        )}
        {ready && !user?.permissions.includes("schedule.write") && (
          <p>
            {el
              ? "Ο υπεύθυνος προγραμματισμού μπορεί να δημιουργήσει το προσχέδιο."
              : "Your scheduling manager can create the draft."}
          </p>
        )}
      </div>
    </section>
  );
}
