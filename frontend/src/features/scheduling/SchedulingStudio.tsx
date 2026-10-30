"use client";
import React, { useState, useMemo, useEffect, useRef } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  BusFront,
  UsersRound,
  Play,
  Send,
  Search,
  Filter,
  LockKeyhole,
  ShieldCheck,
  AlertTriangle,
  Clock3,
  Check,
  X,
  Minus,
  Plus,
  Settings2,
} from "lucide-react";
import { useI18n } from "../../i18n/context";
import type { StudioTrip, StudioResource, StudioRevision } from "./types";
import type { Verification } from "./revision-api";
import { SchedulingTimeline } from "./timeline/SchedulingTimeline";
import { ScheduleChangeDialog } from "./ScheduleChangeDialog";
import type { PersistedRevision } from "./revision-api";
import { RunFeedback } from "./RunFeedback";
import { AssignmentInspector } from "./inspector/AssignmentInspector";
import { scheduleDisplay, type ScheduleDisplayContext } from "./display";
import type { CandidatePlan } from "./CandidateComparisonTray";
interface Props {
  initialRevision: StudioRevision;
  persistedRevision: PersistedRevision;
  onSaveChange: (value: PersistedRevision, baseRevisionId: string) => void;
  displayContext?: ScheduleDisplayContext;
  sourceKind?: "operational" | "reference_archive";
  sourceReviewRequired?: boolean;
  onReviewSource?: () => void;
  serviceDate: string;
  onServiceDateChange?: (date: string) => void;
  verification: Verification;
  resources: StudioResource[];
  trips: StudioTrip[];
  plans: CandidatePlan[];
  selectedPlanId: string;
  permissions: string[];
  isOptimizing?: boolean;
  isRestoringRun?: boolean;
  progressPct?: number;
  jobStatus?: string;
  runId?: string | null;
  jobError?: string | null;
  onSelectPlan: (id: string) => void;
  onApplyPlan: (plan: CandidatePlan) => void | Promise<void>;
  onRunCVSolver: (iterations: number) => Promise<void>;
  onPatchAssignment: (
    tripId: string,
    resourceId: string,
    locked?: boolean,
  ) => Promise<void>;
  onRevisionAction: (action: string) => Promise<void>;
}
export function SchedulingStudio({
  initialRevision: revision,
  persistedRevision,
  onSaveChange,
  displayContext,
  sourceKind = "operational",
  sourceReviewRequired = false,
  onReviewSource,
  serviceDate,
  onServiceDateChange,
  verification,
  resources,
  trips,
  plans,
  selectedPlanId,
  permissions,
  isOptimizing,
  isRestoringRun = false,
  progressPct = 0,
  jobStatus,
  runId = null,
  jobError,
  onSelectPlan,
  onApplyPlan,
  onRunCVSolver,
  onPatchAssignment,
  onRevisionAction,
}: Props) {
  const { locale } = useI18n();
  const el = locale === "el";
  const { stationName, timeLabel, dayIndex } = useMemo(
    () => scheduleDisplay(displayContext),
    [displayContext],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [change, setChange] = useState<{
    tripId: string;
    mode: "move" | "cancel" | "replace_driver";
    target?: string;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [station, setStation] = useState("");
  const [group, setGroup] = useState<"buses" | "drivers">("buses");
  const [day, setDay] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [tab, setTab] = useState<
    "trips" | "conflicts" | "unassigned" | "candidates"
  >("trips");
  const [onlyLocked, setOnlyLocked] = useState(false);
  const [iterations, setIterations] = useState(3);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [startingRun, setStartingRun] = useState(false);
  const [attemptFailed, setAttemptFailed] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const requestedAfter = useRef<string | null | undefined>(undefined);
  const reviewResults = () => {
    setTab("candidates");
    requestAnimationFrame(() => {
      resultsRef.current?.scrollIntoView({ block: "start", behavior: "auto" });
      resultsRef.current?.focus({ preventScroll: true });
    });
  };
  useEffect(() => {
    if (
      requestedAfter.current !== undefined &&
      !startingRun &&
      runId &&
      runId !== requestedAfter.current &&
      plans.length > 0 &&
      tab === "candidates"
    ) {
      requestedAfter.current = undefined;
      resultsRef.current?.scrollIntoView({ block: "start", behavior: "auto" });
    }
  }, [runId, plans.length, tab, startingRun]);
  const startRun = async () => {
    setStartingRun(true);
    setBusy(true);
    setNotice(null);
    setAttemptFailed(false);
    requestedAfter.current = runId;
    setTab("candidates");
    try {
      await onRunCVSolver(iterations);
    } catch (error) {
      setAttemptFailed(true);
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setStartingRun(false);
      setBusy(false);
    }
  };

  const readonly =
    !permissions.includes("schedule.write") ||
    revision.status === "published" ||
    sourceKind === "reference_archive" ||
    sourceReviewRequired;
  const canApprove = permissions.includes(
    revision.status === "draft"
      ? "schedule.write"
      : revision.status === "approval_requested"
        ? "schedule.approve"
        : "schedule.publish",
  );
  const execute = async (work: () => Promise<void>) => {
    setBusy(true);
    setNotice(null);
    try {
      await work();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const selectedTrip = trips.find((t) => t.id === selected) ?? null;
  const changeTrip = change
    ? trips.find((item) => item.id === change.tripId)
    : undefined;
  const canReviewChange =
    permissions.includes("schedule.write") &&
    sourceKind === "operational" &&
    !sourceReviewRequired &&
    !busy &&
    !isOptimizing &&
    !isRestoringRun;
  const requestChange = (
    tripId: string,
    mode: "move" | "cancel" | "replace_driver",
    target?: string,
  ) => {
    const item = trips.find((t) => t.id === tripId);
    // A locked trip of a published day can be reviewed too: the server releases the lock only for an availability conflict.
    if (canReviewChange && item && (!item.isLocked || revision.status === "published"))
      setChange({ tripId, mode, target });
  };
  const maxDay = Math.max(0, ...trips.map((t) => dayIndex(t.endMinutes - 1)));
  const resourceById = useMemo(
    () => new Map(resources.map((resource) => [resource.id, resource])),
    [resources],
  );
  const stations = Array.from(
    new Set(trips.flatMap((t) => [t.startStation, t.endStation])),
  ).sort();
  const visible = useMemo(
    () =>
      trips.filter((t) => {
        if (onlyLocked && !t.isLocked) return false;
        if (station && t.startStation !== station && t.endStation !== station)
          return false;
        if (tab === "conflicts" && !t.hasViolation) return false;
        if (tab === "unassigned" && t.resourceId !== "UNASSIGNED") return false;
        return (
          !query ||
          `${t.tripCode} ${resourceById.get(t.resourceId)?.busPlate ?? ""} ${resourceById.get(t.resourceId)?.driverName ?? ""} ${stationName(t.startStation, el)} ${stationName(t.endStation, el)}`
            .toLowerCase()
            .includes(query.toLowerCase())
        );
      }),
    [trips, onlyLocked, station, tab, query, el, stationName, resourceById],
  );
  const assigned = trips.filter((t) => t.resourceId !== "UNASSIGNED");
  const used = new Set(assigned.map((t) => t.resourceId)).size;
  const driving = assigned.reduce(
    (sum, t) => sum + t.endMinutes - t.startMinutes,
    0,
  );
  const conflicts = trips.filter((t) => t.hasViolation).length;
  const date = new Date(`${serviceDate}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + day);
  const dateText = new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Europe/Athens",
  }).format(date);
  const [coverage, utilization] = [
    Math.round((assigned.length / Math.max(trips.length, 1)) * 100),
    Math.round((used / Math.max(resources.length, 1)) * 100),
  ];
  return (
    <section className="studio">
      <div className="studio-heading">
        <div>
          <div className="eyebrow">
            {el ? "ΣΧΕΔΙΑΣΜΟΣ & ΚΑΤΑΝΟΜΗ" : "PLANNING & DISPATCH"}
          </div>
          <h1>Scheduling Studio</h1>
          <p>
            {el
              ? "Σχεδιάστε. Αναθέστε. Ελέγξτε κάθε διαδρομή."
              : "Plan with clarity. Keep every journey connected."}
          </p>
        </div>
        <div className="heading-actions">
          <span
            className={`status-pill ${revision.status === "published" ? "good" : "neutral"}`}
          >
            <span className="status-dot" />
            {
              {
                draft: el ? "Προσχέδιο" : "Draft",
                approval_requested: el ? "Σε έγκριση" : "Pending approval",
                approved: el ? "Εγκεκριμένο" : "Approved",
                published: el ? "Δημοσιευμένο" : "Published",
              }[revision.status]
            }
          </span>
          <span className="revision-version" data-testid="revision-version">
            v{revision.version}
          </span>
        </div>
      </div>
      <div className="summary-grid">
        <div className="summary-card">
          <span className="metric-icon teal">
            <CalendarDays size={20} />
          </span>
          <div>
            <span className="metric-label">
              {el ? "Ανατεθειμένα δρομολόγια" : "Scheduled trips"}
            </span>
            <div className="metric-value">
              {assigned.length}
              <small> / {trips.length}</small>
            </div>
            <span className="metric-caption">
              {el ? "κάλυψη προγράμματος" : "schedule coverage"}
            </span>
          </div>
          <div
            className="metric-ring"
            style={{ "--percent": `${coverage}%` } as React.CSSProperties}
          >
            <span>{coverage}%</span>
          </div>
        </div>
        <div className="summary-card">
          <span className="metric-icon blue">
            <BusFront size={20} />
          </span>
          <div>
            <span className="metric-label">
              {el ? "Οχήματα σε υπηρεσία" : "Buses in service"}
            </span>
            <div className="metric-value">
              {used}
              <small> / {resources.length}</small>
            </div>
            <span className="metric-caption">
              {el
                ? "σταθερά ζεύγη οδηγού–οχήματος"
                : "fixed driver–vehicle pairs"}
            </span>
          </div>
          <span className="metric-percent">{utilization}%</span>
        </div>
        <div className="summary-card">
          <span className="metric-icon violet">
            <Clock3 size={20} />
          </span>
          <div>
            <span className="metric-label">
              {el ? "Χρόνος οδήγησης" : "Scheduled driving"}
            </span>
            <div className="metric-value">
              {Math.floor(driving / 60)}
              <small>h {driving % 60}m</small>
            </div>
            <span className="metric-caption">
              {el
                ? "από αποθηκευμένες αναθέσεις"
                : "from persisted assignments"}
            </span>
          </div>
        </div>
        <div className="summary-card">
          <span
            className={`metric-icon ${verification.valid ? "teal" : "amber"}`}
          >
            <ShieldCheck size={20} />
          </span>
          <div>
            <span className="metric-label">
              {el ? "Έλεγχος προγράμματος" : "Schedule validation"}
            </span>
            <div className="metric-value">
              {verification.violations.length}
              <small>{el ? " ευρήματα" : " findings"}</small>
            </div>
            <span className="metric-caption">
              {el
                ? "ανεξάρτητος έλεγχος κανόνων"
                : "independent rule verification"}
            </span>
          </div>
        </div>
      </div>
      <div className="studio-toolbar">
        <div className="date-control">
          <CalendarDays size={16} />
          <strong>{dateText}</strong>
          {onServiceDateChange && (
            <input
              type="date"
              aria-label={el ? "Ημερομηνία υπηρεσίας" : "Service date"}
              value={serviceDate}
              onChange={(event) => {
                if (event.target.value) onServiceDateChange(event.target.value);
              }}
            />
          )}
          <button
            className="icon-button"
            disabled={day === 0}
            onClick={() => setDay(day - 1)}
            aria-label="Previous day"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className="icon-button"
            disabled={day === maxDay}
            onClick={() => setDay(day + 1)}
            aria-label="Next day"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="segmented">
          <button
            className={group === "buses" ? "active" : ""}
            onClick={() => setGroup("buses")}
          >
            <BusFront size={14} />
            {el ? "Οχήματα" : "Buses"}
          </button>
          <button
            className={group === "drivers" ? "active" : ""}
            onClick={() => setGroup("drivers")}
          >
            <UsersRound size={14} />
            {el ? "Οδηγοί" : "Drivers"}
          </button>
        </div>
        <div className="toolbar-spacer" />
        <details className="planning-options">
          <summary>
            <Settings2 size={14} />
            {el ? "Επιλογές σχεδιασμού" : "Planning options"}
          </summary>
          <div>
            {" "}
            <label className="iteration-control">
              {el ? "Επαναλήψεις" : "Iterations"}
              <select
                aria-label="CV iterations"
                value={iterations}
                onChange={(e) => setIterations(Number(e.target.value))}
              >
                {[1, 3, 5, 10].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <p>
              {el
                ? "Περισσότερες επαναλήψεις μπορεί να χρειαστούν περισσότερο χρόνο."
                : "More search passes may take longer."}
            </p>
          </div>
        </details>
        <button
          className="button secondary"
          disabled={
            busy ||
            startingRun ||
            isOptimizing ||
            isRestoringRun ||
            readonly ||
            !permissions.includes("optimization.run")
          }
          onClick={() => void startRun()}
        >
          <Play size={14} />
          {startingRun
            ? el
              ? "Έναρξη αναζήτησης…"
              : "Starting search…"
            : isOptimizing
              ? el
                ? "Δημιουργία προσχεδίου…"
                : "Preparing draft…"
              : el
                ? "Δημιουργία προσχεδίου"
                : "Generate draft schedule"}
        </button>
        <button
          className="button primary"
          disabled={
            busy ||
            readonly ||
            isOptimizing ||
            isRestoringRun ||
            !verification.valid ||
            !canApprove
          }
          onClick={() =>
            execute(() =>
              onRevisionAction(
                revision.status === "draft"
                  ? "request-approval"
                  : revision.status === "approval_requested"
                    ? "approve"
                    : "publish",
              ),
            )
          }
        >
          <Send size={14} />
          {revision.status === "draft"
            ? el
              ? "Αίτηση έγκρισης"
              : "Request approval"
            : revision.status === "approval_requested"
              ? el
                ? "Έγκριση"
                : "Approve schedule"
              : el
                ? "Δημοσίευση"
                : "Publish schedule"}
        </button>
      </div>
      {sourceKind === "operational" && (
        <RunFeedback
          status={jobStatus}
          hasRun={!!runId}
          restoring={isRestoringRun}
          submitting={startingRun}
          progress={progressPct}
          candidateCount={plans.length}
          error={jobError}
          attemptFailed={attemptFailed}
          onReview={reviewResults}
          onRetry={() => void startRun()}
          retryDisabled={
            busy ||
            startingRun ||
            !!isOptimizing ||
            isRestoringRun ||
            readonly ||
            !permissions.includes("optimization.run")
          }
          onReviewSource={onReviewSource}
        />
      )}
      {revision.status === "published" && (
        <p className="studio-readonly-help">
          {el
            ? "Αυτό το πρόγραμμα έχει δημοσιευτεί και παραμένει αμετάβλητο. Οι αλλαγές χρειάζονται νέο προσχέδιο."
            : "This schedule is published and stays unchanged. Changes require a new draft."}
        </p>
      )}
      {sourceKind === "reference_archive" && (
        <p className="studio-readonly-help">
          {el
            ? "Το αρχείο αναφοράς προορίζεται για ανάγνωση. Χρησιμοποιήστε τα δικά σας στοιχεία από την ημέρα υπηρεσίας."
            : "The reference archive is read only. Use your own records from Service day."}
        </p>
      )}
      {!permissions.includes("schedule.write") && (
        <p className="studio-readonly-help">
          {el
            ? "Ο ρόλος σας επιτρέπει προβολή. Ο υπεύθυνος προγραμματισμού μπορεί να αλλάξει ή να δημιουργήσει προσχέδιο."
            : "Your role can review this schedule. A dispatcher can edit or generate a draft."}
        </p>
      )}
      {busy && !startingRun && (
        <p className="resource-help" role="status">
          {el ? "Αποθήκευση αλλαγής…" : "Saving your change…"}
        </p>
      )}
      {sourceReviewRequired && (
        <div className="notice error" role="alert">
          <AlertTriangle size={18} />
          <span>
            {el
              ? "Τα στοιχεία της ημέρας άλλαξαν μετά τη δημιουργία αυτού του προσχεδίου. Ελέγξτε την ημέρα και ανοίξτε ενημερωμένο προσχέδιο πριν από την έγκριση."
              : "The day's inputs changed after this draft was created. Review Service day and open an updated draft before approval."}
          </span>
          {onReviewSource && (
            <button className="button secondary" onClick={onReviewSource}>
              {el ? "Έλεγχος ημέρας" : "Review service day"}
            </button>
          )}
        </div>
      )}
      {notice && (
        <div role="alert" className="notice error">
          <AlertTriangle size={16} />
          <span>{notice}</span>
          <button
            className="icon-button"
            onClick={() => setNotice(null)}
            aria-label="Dismiss error"
          >
            <X size={14} />
          </button>
        </div>
      )}
      <div className="studio-workspace">
        <div className="studio-center">
          <div className="schedule-panel">
            <div className="panel-heading">
              <h2>
                {el ? "Χρονολόγιο προγράμματος" : "Schedule timeline"}
                <span>
                  {resources.length} {el ? "πόροι" : "resources"}
                </span>
              </h2>
              <div className="timeline-legend">
                <span>
                  <i className="legend-dot blue" />
                  {el ? "Ανάθεση" : "Assigned"}
                </span>
                <span>
                  <i className="legend-dot amber" />
                  {el ? "Κλείδωμα" : "Locked"}
                </span>
                <span>
                  <i className="legend-dot rose" />
                  {el ? "Εύρημα" : "Conflict"}
                </span>
              </div>
              <div className="zoom-control">
                <button
                  className="icon-button"
                  disabled={zoom <= 0.75}
                  onClick={() => setZoom(zoom - 0.25)}
                  aria-label="Zoom out"
                >
                  <Minus size={14} />
                </button>
                <span>{Math.round(zoom * 100)}%</span>
                <button
                  className="icon-button"
                  disabled={zoom >= 2}
                  onClick={() => setZoom(zoom + 0.25)}
                  aria-label="Zoom in"
                >
                  <Plus size={14} />
                </button>
              </div>
            </div>
            <div className="schedule-filters">
              <div className="search-field">
                <Search size={15} />
                <input
                  aria-label="Search schedule"
                  placeholder={
                    el
                      ? "Αναζήτηση δρομολογίου, σταθμού…"
                      : "Search trips, stations, buses…"
                  }
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {query && (
                  <button
                    className="icon-button"
                    onClick={() => setQuery("")}
                    aria-label="Clear search"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
              <label className="station-select">
                <Filter size={13} />
                <select
                  aria-label="Station filter"
                  value={station}
                  onChange={(e) => setStation(e.target.value)}
                >
                  <option value="">
                    {el ? "Όλοι οι σταθμοί" : "All stations"}
                  </option>
                  {stations.map((s) => (
                    <option key={s} value={s}>
                      {stationName(s, el)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={`filter-lock ${onlyLocked ? "active" : ""}`}
                aria-pressed={onlyLocked}
                onClick={() => setOnlyLocked(!onlyLocked)}
              >
                <LockKeyhole size={13} />
                {el ? "Κλειδωμένα" : "Locked"}
              </button>
            </div>
            <SchedulingTimeline
              displayContext={displayContext}
              resources={resources}
              trips={visible}
              selectedTripId={selected}
              onSelectTrip={setSelected}
              onRequestMove={
                canReviewChange
                  ? (id, target) => requestChange(id, "move", target)
                  : undefined
              }
              grouping={group}
              day={day}
              zoom={zoom}
            />
            <div className="timeline-footer">
              <span>
                {visible.length}{" "}
                {el ? "δρομολόγια στο φίλτρο" : "trips matching filters"}
              </span>
              <span>
                <span className="tiny-dot" />
                {sourceKind === "reference_archive"
                  ? el
                    ? "Αρχείο αναφοράς · Μόνο ανάγνωση"
                    : "Reference archive · Read only"
                  : el
                    ? "Αποθηκευμένα επιχειρησιακά στοιχεία"
                    : "Saved operational inputs"}{" "}
                · {displayContext?.timezone ?? ""}
              </span>
            </div>
          </div>
          <div
            className="detail-table-panel"
            ref={resultsRef}
            tabIndex={-1}
            aria-label={el ? "Προτάσεις και δρομολόγια" : "Proposals and trips"}
          >
            <div className="data-tabs">
              {(
                ["trips", "conflicts", "unassigned", "candidates"] as const
              ).map((t) => (
                <button
                  key={t}
                  className={tab === t ? "active" : ""}
                  onClick={() => {
                    requestedAfter.current = undefined;
                    setTab(t);
                  }}
                >
                  {
                    {
                      trips: el ? "Δρομολόγια" : "Trips",
                      conflicts: el ? "Ευρήματα" : "Conflicts",
                      unassigned: el ? "Χωρίς ανάθεση" : "Unassigned",
                      candidates: el ? "Επιλογές προσχεδίου" : "Draft options",
                    }[t]
                  }
                  <span>
                    {t === "trips"
                      ? trips.length
                      : t === "conflicts"
                        ? conflicts
                        : t === "unassigned"
                          ? trips.length - assigned.length
                          : plans.length}
                  </span>
                </button>
              ))}
            </div>
            {tab === "candidates" ? (
              <div className="candidate-list">
                {plans.length === 0 ? (
                  <div className="table-empty">
                    <Play size={20} />
                    <strong>
                      {el
                        ? isOptimizing || startingRun
                          ? "Η πρόταση προετοιμάζεται…"
                          : "Δημιουργήστε προσχέδιο για να δείτε τις επιλογές σας"
                        : isOptimizing || startingRun
                          ? "Your proposal is being prepared…"
                          : "Generate a draft to see your options"}
                    </strong>
                    <span>
                      {el
                        ? "Εκτελέστε τον επιλυτή για να συγκρίνετε πραγματικά αποτελέσματα."
                        : "Run the solver to compare actual scheduling results."}
                    </span>
                  </div>
                ) : (
                  plans.map((p) => (
                    <div
                      className={`candidate-row ${p.id === selectedPlanId ? "selected" : ""}`}
                      key={p.id}
                    >
                      <input
                        type="radio"
                        aria-label={p.name}
                        checked={p.id === selectedPlanId}
                        onChange={() => onSelectPlan(p.id)}
                      />
                      <div>
                        <strong>{p.name}</strong>
                        <small>
                          {p.generatedAt} · {p.algorithm}
                        </small>
                      </div>
                      <span>
                        {p.assignedTrips}/{p.totalTrips}{" "}
                        {el ? "δρομ." : "trips"}
                      </span>
                      <span>
                        {p.busesUsed} {el ? "οχήματα" : "buses"}
                      </span>
                      <button
                        className="button secondary"
                        disabled={
                          readonly || busy || isOptimizing || isRestoringRun
                        }
                        onClick={() =>
                          execute(async () => {
                            await onApplyPlan(p);
                          })
                        }
                      >
                        {el ? "Εφαρμογή" : "Apply candidate"}
                      </button>
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div className="trip-table-scroll">
                <table className="trip-table">
                  <thead>
                    <tr>
                      <th>{el ? "Δρομολόγιο" : "Trip"}</th>
                      <th>{el ? "Διαδρομή" : "Route"}</th>
                      <th>{el ? "Αναχώρηση" : "Departure"}</th>
                      <th>{el ? "Άφιξη" : "Arrival"}</th>
                      <th>{el ? "Όχημα" : "Bus"}</th>
                      <th>{el ? "Κατάσταση" : "Status"}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {visible.slice(0, 80).map((t) => (
                      <tr
                        key={t.id}
                        onClick={() => setSelected(t.id)}
                        className={selected === t.id ? "selected" : ""}
                      >
                        <td className="trip-code">{t.tripCode}</td>
                        <td>
                          {stationName(t.startStation, el)}{" "}
                          <span className="route-arrow">→</span>{" "}
                          {stationName(t.endStation, el)}
                        </td>
                        <td className="tabular">{timeLabel(t.startMinutes)}</td>
                        <td className="tabular">{timeLabel(t.endMinutes)}</td>
                        <td className="tabular">
                          {t.resourceId === "UNASSIGNED"
                            ? "—"
                            : (resourceById.get(t.resourceId)?.busPlate ??
                              t.resourceId)}
                        </td>
                        <td>
                          <span
                            className={`status-pill ${t.hasViolation ? "warning" : t.resourceId === "UNASSIGNED" ? "neutral" : "good"}`}
                          >
                            {t.hasViolation ? (
                              <AlertTriangle size={11} />
                            ) : t.isLocked ? (
                              <LockKeyhole size={11} />
                            ) : (
                              <Check size={11} />
                            )}
                            {t.hasViolation
                              ? el
                                ? "Έλεγχος"
                                : "Review"
                              : t.resourceId === "UNASSIGNED"
                                ? el
                                  ? "Χωρίς ανάθεση"
                                  : "Unassigned"
                                : el
                                  ? "Ανατεθειμένο"
                                  : "Assigned"}
                          </span>
                        </td>
                        <td>
                          <button
                            className="icon-button"
                            aria-label={`Inspect ${t.tripCode}`}
                            onClick={() => setSelected(t.id)}
                          >
                            <ChevronRight size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {visible.length === 0 && (
                  <div className="table-empty">
                    {el
                      ? "Δεν βρέθηκαν δρομολόγια."
                      : "No trips match these filters."}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <AssignmentInspector
          displayContext={displayContext}
          trip={selectedTrip}
          resources={resources}
          isLockedRevision={
            readonly || busy || !!isOptimizing || isRestoringRun
          }
          onClose={() => setSelected(null)}
          onReviewChange={canReviewChange ? requestChange : undefined}
          published={revision.status === "published"}
          onToggleLock={(id) => {
            const t = trips.find((t) => t.id === id)!;
            void execute(() =>
              onPatchAssignment(id, t.resourceId, !t.isLocked),
            );
          }}
          onReassignResource={(id, res) => {
            void execute(() => onPatchAssignment(id, res));
          }}
        />
      </div>
      {persistedRevision.source_trips.some((item) => item.is_cancelled) && (
        <section
          className="cancelled-trips"
          aria-label={el ? "Ακυρωμένα δρομολόγια" : "Cancelled trips"}
        >
          <h2>{el ? "Ακυρωμένα δρομολόγια" : "Cancelled trips"}</h2>
          {persistedRevision.source_trips
            .filter((item) => item.is_cancelled)
            .map((item) => (
              <p key={item.id}>
                <strong>{item.trip_code ?? item.id}</strong> ·{" "}
                {item.cancellation_reason}
              </p>
            ))}
        </section>
      )}
      {change && changeTrip && (
        <ScheduleChangeDialog
          key={`${revision.revisionId}:${change.tripId}`}
          revision={persistedRevision}
          trip={changeTrip}
          trips={trips}
          resources={resources}
          initialMode={change.mode}
          initialTarget={change.target}
          onClose={() => setChange(null)}
          onSaved={(value) => {
            setChange(null);
            onSaveChange(value, revision.revisionId);
          }}
        />
      )}
      <div className="studio-statusbar">
        <span>
          <span className="tiny-dot teal" />
          {el ? "Αποθηκευμένη έκδοση" : "Saved version"} ·{" "}
          <span className="tabular">v{revision.version}</span>
        </span>
        <span>
          {sourceKind === "reference_archive"
            ? el
              ? "Αρχείο αναφοράς · Μόνο ανάγνωση"
              : "Reference archive · Read only"
            : el
              ? "Τα δικά σας στοιχεία · Σταθερά ζεύγη οδηγού–οχήματος"
              : "Your operational records · Fixed driver–vehicle pairs"}
        </span>
        <span>
          {el ? "Ενημέρωση" : "Updated"}{" "}
          {new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "Europe/Athens",
          }).format(
            new Date(
              revision.updatedAt.endsWith("Z") ||
              revision.updatedAt.includes("+")
                ? revision.updatedAt
                : revision.updatedAt + "Z",
            ),
          )}
        </span>
      </div>
    </section>
  );
}
