"use client";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  UsersRound,
  BusFront,
  CalendarDays,
  Check,
  Route,
} from "lucide-react";
import { BulkImportButton } from "../imports/BulkImportButton";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
export function SetupWelcome({
  onOpen,
}: {
  onOpen: (
    tab: "drivers" | "fleet" | "timetables" | "planning" | "imports",
  ) => void;
}) {
  const { apiFetch, user } = useAuth();
  const { locale } = useI18n();
  const el = locale === "el";
  const [data, setData] = useState<{
      drivers: number;
      vehicles: number;
      timetables: number;
    } | null>(null),
    [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void apiFetch("/api/v1/setup/readiness", { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error();
        setData(
          (await r.json()) as {
            drivers: number;
            vehicles: number;
            timetables: number;
          },
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [apiFetch]);
  return (
    <section className="setup-welcome">
      <div className="setup-welcome-copy">
        <span className="resource-eyebrow">
          {el ? "Ο ΧΩΡΟΣ ΕΡΓΑΣΙΑΣ ΣΑΣ" : "YOUR WORKSPACE"}
        </span>
        <h1>
          {el
            ? "Ας οργανώσουμε\nτην πρώτη σας ημέρα."
            : "Let’s get ready\nfor your first day."}
        </h1>
        <p>
          {el
            ? "Ξεκινήστε με τους οδηγούς και τα οχήματά σας. Κάθε βήμα αποθηκεύεται, ώστε να μπορείτε να συνεχίσετε όποτε θέλετε."
            : "Start with your drivers and vehicles. Each step is saved, so you can leave and continue whenever you’re ready."}
        </p>
        <BulkImportButton
          entity={
            !data?.drivers
              ? "drivers"
              : !data.vehicles
                ? "vehicles"
                : "timetable"
          }
          returnTo={
            !data?.drivers ? "drivers" : !data.vehicles ? "fleet" : "timetables"
          }
          primary
          label={
            el
              ? "Εισαγωγή πολλών από Excel/CSV"
              : "Import many records from Excel/CSV"
          }
        />
        <p className="resource-help">
          {el
            ? "Δεν χρειάζεται καταχώριση ένα προς ένα. Χρησιμοποιήστε τις σύντομες φόρμες για λίγες προσθήκες ή διορθώσεις."
            : "No need to enter every record individually. Use the short forms for small additions or corrections."}
        </p>
        {error ? (
          <p className="auth-error" role="alert">
            {el
              ? "Δεν μπορέσαμε να ελέγξουμε τα στοιχεία σας. Ανανεώστε τη σελίδα για νέα προσπάθεια."
              : "We could not check your setup. Refresh the page to try again."}
          </p>
        ) : !data ? (
          <p role="status">
            {el ? "Έλεγχος στοιχείων…" : "Checking your setup…"}
          </p>
        ) : (
          <button
            className="button secondary"
            onClick={() =>
              onOpen(
                data.drivers === 0
                  ? "drivers"
                  : data.vehicles === 0
                    ? "fleet"
                    : data.timetables === 0
                      ? "timetables"
                      : "planning",
              )
            }
            disabled={
              !user?.permissions.includes(
                data.drivers === 0
                  ? "drivers.write"
                  : data.vehicles === 0
                    ? "fleet.write"
                    : data.timetables === 0
                      ? "timetable.write"
                      : "schedule.write",
              )
            }
          >
            {data.drivers === 0
              ? el
                ? "Προσθέστε τον πρώτο οδηγό"
                : "Add your first driver"
              : data.vehicles === 0
                ? el
                  ? "Προσθέστε το πρώτο όχημα"
                  : "Add your first vehicle"
                : data.timetables === 0
                  ? el
                    ? "Προσθέστε το πρώτο δρομολόγιο"
                    : "Add your first timetable"
                  : el
                    ? "Προετοιμάστε την ημέρα σας"
                    : "Prepare your service day"}
            <ArrowRight size={16} />
          </button>
        )}
        {data &&
          !user?.permissions.includes(
            data.drivers === 0
              ? "drivers.write"
              : data.vehicles === 0
                ? "fleet.write"
                : data.timetables === 0
                  ? "timetable.write"
                  : "schedule.write",
          ) && (
            <p className="resource-help">
              {el
                ? "Ζητήστε από τον διαχειριστή ή τον υπεύθυνο μητρώου να ολοκληρώσει αυτό το βήμα. Μπορείτε να επιστρέψετε όποτε θέλετε."
                : "Ask your administrator or register manager to complete this step. You can return whenever you’re ready."}
            </p>
          )}
      </div>
      <div className="setup-steps">
        {[
          {
            icon: UsersRound,
            name: el ? "Οι οδηγοί σας" : "Your drivers",
            detail: el
              ? "Ονόματα και προαιρετικά στοιχεία επικοινωνίας."
              : "Names and optional contact details.",
            count: data?.drivers,
            tab: "drivers" as const,
          },
          {
            icon: BusFront,
            name: el ? "Τα οχήματά σας" : "Your vehicles",
            detail: el
              ? "Πινακίδες και κατηγορίες οχημάτων."
              : "Registrations and vehicle categories.",
            count: data?.vehicles,
            tab: "fleet" as const,
          },
          {
            icon: CalendarDays,
            name: el ? "Τα δρομολόγιά σας" : "Your timetable",
            detail: el
              ? "Διαδρομές, ώρες και ημέρες λειτουργίας."
              : "Routes, times and operating days.",
            count: data?.timetables,
            tab: "timetables" as const,
          },
        ].map((step, index) => (
          <div key={index} className="setup-step">
            <span className={`setup-step-icon ${step.count ? "complete" : ""}`}>
              {step.count ? <Check size={21} /> : <step.icon size={21} />}
            </span>
            <div>
              <span className="resource-eyebrow">
                {el ? "ΒΗΜΑ" : "STEP"} {index + 1}
              </span>
              <h2>{step.name}</h2>
              <p>{step.detail}</p>
              {step.count !== undefined && step.count > 0 && (
                <small>
                  {step.count} {el ? "αποθηκευμένες εγγραφές" : "saved records"}
                </small>
              )}
            </div>
            {step.tab && (
              <button
                className="icon-button"
                onClick={() => {
                  if (step.tab) onOpen(step.tab);
                }}
                aria-label={step.name}
              >
                <ArrowRight size={17} />
              </button>
            )}
          </div>
        ))}
      </div>
      <p className="setup-reassurance">
        <Route size={16} />
        {el
          ? "Δεν χρειάζεται να τα συμπληρώσετε όλα μαζί."
          : "You don’t need to complete everything at once."}
      </p>
    </section>
  );
}
