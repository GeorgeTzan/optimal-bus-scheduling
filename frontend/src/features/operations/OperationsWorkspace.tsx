"use client";
import { useEffect, useRef, useState } from "react";
import {
  RefreshCw,
  CalendarDays,
  MessageSquarePlus,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertCircle,
  ClipboardList,
  Search,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { scheduleDisplay } from "../scheduling/display";
import { useListLocation } from "../navigation/use-list-location";
import {
  locationEvent,
  writeWorkspaceUrl,
} from "../navigation/workspace-location";
import { ReportDialog } from "./ReportDialog";
import {
  updateLabel,
  type OperationsDay,
  type OperationalTrip,
  type OperationalEvent,
  type LinkedOperationalEvent,
  type ReportTarget,
} from "./contracts";

export function OperationsWorkspace({
  serviceDate,
  onDate,
  onStudio,
}: {
  serviceDate: string | null;
  onDate: (date: string) => void;
  onStudio: (date: string) => void;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const { query, page, setQuery, setPage } = useListLocation();
  const [selection, setSelection] = useState({
      publication: "",
      openOnly: false,
    }),
    [data, setData] = useState<OperationsDay | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true),
    [refresh, setRefresh] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null),
    [target, setTarget] = useState<ReportTarget | null>(null);
  const latest = useRef(0);
  const canRead = !!user?.permissions.includes("schedule.read"),
    canReport = !!user?.permissions.includes("incidents.manage");
  useEffect(() => {
    const sync = () => {
      const url = new URL(window.location.href);
      setSelection({
        publication: (url.searchParams.get("publication") ?? "").slice(0, 100),
        openOnly: url.searchParams.get("open_only") === "true",
      });
    };
    sync();
    window.addEventListener(locationEvent, sync);
    return () => {
      window.removeEventListener(locationEvent, sync);
    };
  }, []);
  useEffect(() => {
    setTarget(null);
    setExpanded(null);
  }, [serviceDate, selection.publication]);
  useEffect(() => {
    if (!canRead) return;
    const controller = new AbortController(),
      epoch = ++latest.current;
    setBusy(true);
    setError("");
    const parameters = new URLSearchParams({
      page: String(page),
      page_size: "25",
      q: query,
      open_only: String(selection.openOnly),
    });
    if (serviceDate) parameters.set("service_date", serviceDate);
    if (selection.publication)
      parameters.set("publication_id", selection.publication);
    void apiFetch("/api/v1/operations/day?" + parameters.toString(), {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw Error(
            response.status === 404
              ? el
                ? "Αυτή η δημοσίευση δεν υπάρχει για την επιλεγμένη ημέρα."
                : "This publication is not available for the selected day."
              : el
                ? "Δεν φορτώθηκε η ημέρα. Δοκιμάστε ξανά."
                : "This day could not be loaded. Try again.",
          );
        const value = (await response.json()) as OperationsDay;
        if (controller.signal.aborted || epoch !== latest.current) return;
        setData(value);
        // Pin the first actual publication so later polls cannot silently rebind reports.
        if (!selection.publication && value.publication) {
          const url = new URL(window.location.href);
          url.searchParams.set("publication", value.publication.publication_id);
          writeWorkspaceUrl(url, true);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted && epoch === latest.current)
          setError(
            e instanceof Error
              ? e.message
              : el
                ? "Δεν φορτώθηκε η ημέρα."
                : "Could not load this day.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && epoch === latest.current)
          setBusy(false);
      });
    return () => controller.abort();
  }, [
    apiFetch,
    canRead,
    serviceDate,
    selection.publication,
    selection.openOnly,
    query,
    page,
    refresh,
    el,
  ]);
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") setRefresh((v) => v + 1);
    }, 15000);
    return () => clearInterval(interval);
  }, []);
  const changeSelection = (
    publication: string,
    openOnly = selection.openOnly,
  ) => {
    const url = new URL(window.location.href);
    if (publication) url.searchParams.set("publication", publication);
    else url.searchParams.delete("publication");
    url.searchParams.set("open_only", String(openOnly));
    url.searchParams.delete("page");
    writeWorkspaceUrl(url);
  };
  const chooseDate = (date: string) => {
    if (!date) return;
    onDate(date);
  };
  const ready =
    data === null ? false : data.service_date === (serviceDate ?? data.service_date) &&
    (!selection.publication ||
      selection.publication === data.publication?.publication_id);
  const clock = scheduleDisplay({
    timezone: data?.timezone,
    serviceDayStartUtc: data?.service_day_start_utc,
    dayBoundariesMinutes: data?.day_boundaries_minutes,
  });
  const timestamp = (value: string) =>
    new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
      timeZone: data?.timezone ?? "Europe/Athens",
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  const report = (row: OperationalTrip, event?: OperationalEvent, linked?: LinkedOperationalEvent) => {
    if (data?.publication)
      setTarget({
        row: linked ? {...row, version:linked.source_state_version} : row,
        publication: linked?.source_publication ?? data.publication,
        serviceDate: data.service_date,
        timezone: data.timezone,
        event,
      });
  };
  if (!canRead)
    return (
      <section className="resource-empty">
        <h1>{el ? "Καθημερινή λειτουργία" : "Daily Operations"}</h1>
        <p>
          {el
            ? "Ο ρόλος σας δεν επιτρέπει πρόσβαση στο πρόγραμμα της ομάδας. Επικοινωνήστε με τον υπεύθυνο."
            : "Your role does not grant access to the team schedule. Contact your dispatcher."}
        </p>
      </section>
    );
  return (
    <section className="resource-workspace operations-workspace">
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el
              ? "ΤΟ ΔΗΜΟΣΙΕΥΜΕΝΟ ΠΡΟΓΡΑΜΜΑ ΣΤΗΝ ΠΡΑΞΗ"
              : "YOUR PUBLISHED DAY IN PRACTICE"}
          </span>
          <h1>{el ? "Καθημερινή λειτουργία" : "Daily Operations"}</h1>
          <p>
            {el
              ? "Το πρόγραμμα της ημέρας και οι ενημερώσεις που λαμβάνετε από την ομάδα."
              : "The day’s schedule and updates you receive from your team."}
          </p>
        </div>
        <div className="resource-heading-actions">
          <label className="overview-date">
            {el ? "Ημερομηνία υπηρεσίας" : "Service date"}
            <input
              type="date"
              value={serviceDate ?? data?.service_date ?? ""}
              onChange={(event) => chooseDate(event.target.value)}
            />
          </label>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => setRefresh((v) => v + 1)}
          >
            <RefreshCw size={16} />
            {el ? "Ανανέωση" : "Refresh"}
          </button>
        </div>
      </header>
      {error && (
        <div className="import-alert" role="alert">
          <p>{error}</p>
          <button
            className="button secondary"
            onClick={() => {
              setData(null);
              changeSelection("");
              setRefresh((v) => v + 1);
            }}
          >
            {el ? "Επαναφόρτωση ημέρας" : "Reload this day"}
          </button>
        </div>
      )}
      {!ready && busy && (
        <p role="status">
          {el
            ? "Φόρτωση δημοσιευμένου προγράμματος…"
            : "Loading published schedule…"}
        </p>
      )}
      {ready && data && (
        <>
          {!data.publication ? (
            <section className="operations-empty">
              <CalendarDays size={32} />
              <h2>
                {el
                  ? "Δεν υπάρχει δημοσιευμένο πρόγραμμα για αυτή την ημέρα"
                  : "No published schedule for this day"}
              </h2>
              <p>
                {el
                  ? "Η καθημερινή λειτουργία ξεκινά μετά τον έλεγχο, την έγκριση και τη δημοσίευση του προγράμματος."
                  : "Daily Operations begins after the schedule is reviewed, approved and published."}
              </p>
              {user?.permissions.includes("schedule.write") ? (
                <button
                  className="button primary"
                  onClick={() => onStudio(data.service_date)}
                >
                  {el ? "Άνοιγμα Scheduling Studio" : "Open Scheduling Studio"}
                </button>
              ) : (
                <p>
                  {el
                    ? "Ζητήστε από τον υπεύθυνο προγραμματισμού να δημοσιεύσει την ημέρα."
                    : "Ask your dispatcher to publish this day."}
                </p>
              )}
            </section>
          ) : (
            <>
              <div className="operations-publication">
                <div>
                  <span className="status-pill">
                    <CheckCircle2 size={14} />
                    {el ? "Δημοσιευμένο πρόγραμμα" : "Published schedule"}
                  </span>
                  <p>
                    {el ? "Δημοσίευση" : "Published"}{" "}
                    {timestamp(data.publication.published_at)} · {data.timezone}
                  </p>
                </div>
                <label>
                  {el ? "Έκδοση δημοσίευσης" : "Publication version"}
                  <select
                    value={data.publication.publication_id}
                    onChange={(event) => changeSelection(event.target.value)}
                  >
                    {data.publications.map((publication, index) => (
                      <option
                        key={publication.publication_id}
                        value={publication.publication_id}
                      >
                        {index === 0
                          ? el
                            ? "Τελευταία"
                            : "Latest"
                          : el
                            ? "Ιστορική"
                            : "Historical"}{" "}
                        · {timestamp(publication.published_at)} ·{" "}
                        {publication.publication_id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {data.newer_publication && (
                <div className="import-alert" role="status">
                  <p>
                    {el
                      ? "Υπάρχει νεότερη δημοσίευση. Οι ενημερώσεις που βλέπετε παραμένουν σε αυτή την έκδοση."
                      : "A newer publication is available. These updates remain with this version."}
                  </p>
                  <button
                    className="button secondary"
                    onClick={() =>
                      changeSelection(
                        data.publications[0]?.publication_id ?? "",
                      )
                    }
                  >
                    {el
                      ? "Άνοιγμα νεότερης δημοσίευσης"
                      : "Open newer publication"}
                  </button>
                </div>
              )}
              <div className="operations-guidance">
                <ClipboardList size={20} />
                <p>
                  {el
                    ? "Δεν χρειάζεται να σημειώνετε κάθε διαδρομή. Καταγράψτε μια ενημέρωση όταν σας ενημερώσει η ομάδα. Οι ώρες προγράμματος δεν αποτελούν επιβεβαίωση αναχώρησης."
                    : "You do not need to mark every trip. Record an update when your team informs you. Scheduled times do not confirm an actual departure."}
                </p>
              </div>
              <div className="operations-toolbar">
                <label className="operations-search">
                  <Search size={17} />
                  <span className="sr-only">
                    {el
                      ? "Αναζήτηση δρομολογίου, οδηγού ή οχήματος"
                      : "Search trips, drivers or vehicles"}
                  </span>
                  <input
                    value={query}
                    placeholder={
                      el
                        ? "Δρομολόγιο, οδηγός ή όχημα…"
                        : "Trip, driver or vehicle…"
                    }
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <button
                  className="button secondary"
                  aria-pressed={selection.openOnly}
                  onClick={() =>
                    changeSelection(selection.publication, !selection.openOnly)
                  }
                >
                  <AlertCircle size={16} />
                  {el ? "Ανοιχτές αναφορές" : "Open reports"}{" "}
                  <strong>{data.open_count}</strong>
                </button>
              </div>
              <p className="operations-results" role="status">
                {data.total}{" "}
                {el ? "δρομολόγια στην προβολή" : "trips in this view"}
                {busy ? (el ? " · Ανανέωση…" : " · Refreshing…") : ""}
              </p>
              <div className="operations-trips">
                {data.items.map((row) => {
                  const isExpanded = expanded === row.trip_id,
                    resolved = new Set(
                      row.events.map((event) => event.resolved_event_id),
                    );
                  const earlierStatus = [...row.linked_events].reverse().find(event => event.kind === "departure" || event.kind === "completion");
                  const station = (value: OperationalTrip["trip"]["origin"]) =>
                    (el ? value.name_el : value.name_en || value.name_el) ||
                    value.code;
                  return (
                    <article className="operations-trip" key={row.trip_id}>
                      <div className="operations-trip-main">
                        <div className="operations-trip-time">
                          <strong>{clock.timeLabel(row.start_minutes)}</strong>
                          <span>{clock.timeLabel(row.end_minutes)}</span>
                        </div>
                        <div className="operations-trip-route">
                          <div>
                            <span className="operations-trip-code">
                              {row.trip.trip_code}
                            </span>
                            <strong>
                              {station(row.trip.origin)} →{" "}
                              {station(row.trip.destination)}
                            </strong>
                          </div>
                          <p>
                            {row.is_cancelled ? (el ? "Ακυρωμένο" : "Cancelled") : row.resource
                              ? `${row.resource.driver_name} · ${row.resource.vehicle_label}`
                              : el
                                ? "Χωρίς ανάθεση"
                                : "Unassigned"}
                          </p>
                          <span className="operations-reported-status">
                            {row.is_cancelled ? (el ? `Ακυρώθηκε · ${row.cancellation_reason ?? ""}` : `Cancelled · ${row.cancellation_reason ?? ""}`) : row.reported_status === "planned" && earlierStatus ? (earlierStatus.kind === "departure" ? (el ? "Αναχώρηση · αναφέρθηκε σε προηγούμενη δημοσίευση" : "Departure · reported on an earlier publication") : (el ? "Ολοκλήρωση · αναφέρθηκε σε προηγούμενη δημοσίευση" : "Completion · reported on an earlier publication")) : row.reported_status === "planned"
                              ? el
                                ? "Προγραμματισμένο · χωρίς επιβεβαίωση ομάδας"
                                : "Planned · no staff confirmation"
                              : row.reported_status === "departure"
                                ? el
                                  ? "Αναχώρηση · ενημέρωση ομάδας"
                                  : "Departure · staff report"
                                : el
                                  ? "Ολοκλήρωση · ενημέρωση ομάδας"
                                  : "Completion · staff report"}
                          </span>
                        </div>
                        <div className="operations-trip-actions">
                          {row.open_count + row.linked_open_count > 0 && (
                            <span className="operations-open">
                              <AlertCircle size={14} />
                              {row.open_count + row.linked_open_count}{" "}
                              {el ? "ανοιχτές αναφορές" : "open reports"}
                            </span>
                          )}
                          {canReport && (
                            <button
                              className="button secondary"
                              aria-label={`${el ? "Καταγραφή ενημέρωσης για" : "Record update for"} ${row.trip.trip_code}`}
                              onClick={() => report(row)}
                            >
                              <MessageSquarePlus size={16} />
                              {el ? "Ενημέρωση" : "Record update"}
                            </button>
                          )}
                          <button
                            className="operations-details-button"
                            aria-label={`${el ? "Λεπτομέρειες για" : "Trip details for"} ${row.trip.trip_code}`}
                            aria-expanded={isExpanded}
                            onClick={() =>
                              setExpanded(isExpanded ? null : row.trip_id)
                            }
                          >
                            {el ? "Ιστορικό" : "Details"}{" "}
                            {row.events.length + row.linked_events.length > 0 && `(${row.events.length + row.linked_events.length})`}
                            {isExpanded ? (
                              <ChevronUp size={15} />
                            ) : (
                              <ChevronDown size={15} />
                            )}
                          </button>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="operations-history">
                          {row.events.length === 0 ? (
                            <p>
                              {row.linked_events.length > 0
                                ? (el ? "Δεν υπάρχουν ενημερώσεις σε αυτή τη δημοσίευση." : "No updates on this publication.")
                                : (el ? "Δεν υπάρχουν ενημερώσεις ομάδας για αυτό το δρομολόγιο." : "No staff updates for this trip.")}
                            </p>
                          ) : (
                            row.events.map((event) => (
                              <div className="operations-event" key={event.id}>
                                <div className="operations-event-heading">
                                  <strong>
                                    {updateLabel(event.kind, el)}
                                    {event.delay_minutes !== null &&
                                      ` · ${event.delay_minutes} ${el ? "λεπτά" : "min"}`}
                                  </strong>
                                  {["delay", "breakdown", "note"].includes(
                                    event.kind,
                                  ) && (
                                    <span className="status-pill">
                                      {resolved.has(event.id)
                                        ? el
                                          ? "Επιλύθηκε"
                                          : "Resolved"
                                        : el
                                          ? "Ανοιχτή"
                                          : "Open"}
                                    </span>
                                  )}
                                </div>
                                <p>{event.description}</p>
                                <small>
                                  {event.actor_name} ·{" "}
                                  {timestamp(event.recorded_at)}
                                </small>
                                {canReport &&
                                  ["delay", "breakdown", "note"].includes(
                                    event.kind,
                                  ) &&
                                  !resolved.has(event.id) && (
                                    <button
                                      className="button secondary"
                                      onClick={() => report(row, event)}
                                    >
                                      {el
                                        ? "Σήμανση ως επιλυμένο"
                                        : "Mark resolved"}
                                    </button>
                                  )}
                              </div>
                            ))
                          )}
                          {row.linked_events.length > 0 && (
                            <section aria-label={el ? "Ενημερώσεις προηγούμενης δημοσίευσης" : "Earlier publication updates"} className="operations-linked-history">
                              <h3>{el ? "Ενημερώσεις προηγούμενης δημοσίευσης" : "Earlier publication updates"}</h3>
                              <p className="resource-help">{el ? "Οι αναφορές παραμένουν στην αρχική δημοσίευση." : "These reports remain attached to their original publication."}</p>
                              {row.linked_events.map(event => <div className="operations-event" key={event.id}>
                                <div className="operations-event-heading"><strong>{updateLabel(event.kind,el)}{event.delay_minutes !== null && ` · ${event.delay_minutes} ${el ? "λεπτά" : "min"}`}</strong>{["delay","breakdown","note"].includes(event.kind) && <span className="status-pill">{event.is_open ? (el ? "Ανοιχτή" : "Open") : (el ? "Επιλύθηκε" : "Resolved")}</span>}</div>
                                <p>{event.description}</p><small>{event.actor_name} · {timestamp(event.recorded_at)} · {el ? "Προηγούμενη δημοσίευση" : "Earlier publication"} {timestamp(event.source_publication.published_at)} · {event.source_publication.publication_id.slice(0,8)}</small>
                                {canReport && event.is_open && <button className="button secondary" onClick={()=>report(row,event,event)}>{el ? "Σήμανση ως επιλυμένο" : "Mark resolved"}</button>}
                              </div>)}
                            </section>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
              {data.total === 0 && (
                <div className="operations-empty">
                  <h2>
                    {el ? "Δεν βρέθηκαν δρομολόγια" : "No matching trips"}
                  </h2>
                  <p>
                    {el
                      ? "Αλλάξτε την αναζήτηση ή το φίλτρο ανοιχτών αναφορών."
                      : "Change your search or the open-reports filter."}
                  </p>
                </div>
              )}
              <div className="import-pagination">
                <span>
                  {el ? "Σελίδα" : "Page"} {page} /{" "}
                  {Math.max(1, Math.ceil(data.total / 25))}
                </span>
                <button
                  className="button secondary"
                  disabled={busy || page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  {el ? "Προηγούμενη" : "Previous"}
                </button>
                <button
                  className="button secondary"
                  disabled={busy || page * 25 >= data.total}
                  onClick={() => setPage(page + 1)}
                >
                  {el ? "Επόμενη" : "Next"}
                </button>
              </div>
            </>
          )}
        </>
      )}
      {target && (
        <ReportDialog
          target={target}
          onClose={() => {
            setTarget(null);
            setRefresh((v) => v + 1);
          }}
          onSaved={() => {
            setTarget(null);
            setRefresh((v) => v + 1);
            setExpanded(target.row.trip_id);
          }}
        />
      )}
    </section>
  );
}
