"use client";
import React, { useState } from "react";
import {
  X,
  Route,
  Clock3,
  MapPin,
  BusFront,
  UserRound,
  LockKeyhole,
  LockKeyholeOpen,
  ShieldCheck,
  AlertTriangle,
  ArrowRight,
  MousePointer2,
} from "lucide-react";
import { useI18n } from "../../../i18n/context";
import type { StudioTrip, StudioResource } from "../types";
import { scheduleDisplay, type ScheduleDisplayContext } from "../display";
interface Props {
  displayContext?: ScheduleDisplayContext;
  trip: StudioTrip | null;
  resources: StudioResource[];
  isLockedRevision?: boolean;
  onClose: () => void;
  onToggleLock: (id: string) => void;
  onReassignResource: (id: string, resource: string) => void;
  onReviewChange?: (
    id: string,
    mode: "move" | "cancel" | "replace_driver",
  ) => void;
  published?: boolean;
}
export function AssignmentInspector({
  displayContext,
  trip,
  resources,
  isLockedRevision,
  onClose,
  onToggleLock,
  onReassignResource,
  onReviewChange,
  published = false,
}: Props) {
  const { locale } = useI18n();
  const el = locale === "el";
  const { stationName, timeLabel } = scheduleDisplay(displayContext);
  const [tab, setTab] = useState<"details" | "resource" | "validation">(
    "details",
  );
  const resource = resources.find((r) => r.id === trip?.resourceId);
  return (
    <aside
      className="assignment-inspector"
      aria-label={el ? "Επιθεωρητής δρομολογίου" : "Trip Details"}
    >
      <div className="inspector-heading">
        <h2>{el ? "Στοιχεία ανάθεσης" : "Assignment details"}</h2>
        {trip && (
          <button
            className="icon-button"
            onClick={onClose}
            aria-label={el ? "Κλείσιμο" : "Close"}
          >
            <X size={17} />
          </button>
        )}
      </div>
      {!trip ? (
        <div className="inspector-empty">
          <span>
            <MousePointer2 size={26} strokeWidth={1.3} />
          </span>
          <h3>
            {el
              ? "Κάθε διαδρομή, σε λεπτομέρεια"
              : "A closer look at every trip"}
          </h3>
          <p>
            {el
              ? "Επιλέξτε ένα δρομολόγιο στο χρονολόγιο για να δείτε στοιχεία, αναθέσεις και ευρήματα."
              : "Select a trip on the timeline to inspect its details, manage the assignment and review validation findings."}
          </p>
          <div>
            <span className="keyboard-key">Tab</span>
            <small>{el ? "για πλοήγηση" : "to navigate"}</small>
            <span className="keyboard-key">↵</span>
            <small>{el ? "για επιλογή" : "to select"}</small>
          </div>
        </div>
      ) : (
        <>
          <div className="inspector-trip-title">
            <div className="trip-meta">
              <span
                className={`status-pill ${trip.hasViolation ? "warning" : trip.resourceId === "UNASSIGNED" ? "neutral" : "good"}`}
              >
                {trip.hasViolation ? (
                  <AlertTriangle size={11} />
                ) : (
                  <ShieldCheck size={11} />
                )}{" "}
                {trip.hasViolation
                  ? el
                    ? "Απαιτεί έλεγχο"
                    : "Needs review"
                  : trip.resourceId === "UNASSIGNED"
                    ? el
                      ? "Χωρίς ανάθεση"
                      : "Unassigned"
                    : el
                      ? "Ανατεθειμένο"
                      : "Assigned"}
              </span>
              <span className="trip-reference">#{trip.tripCode}</span>
            </div>
            <h3>
              {stationName(trip.startStation, el)} <ArrowRight size={16} />{" "}
              {stationName(trip.endStation, el)}
            </h3>
            <p>{el ? "Στοιχεία δρομολογίου" : "Service details"}</p>
          </div>
          {onReviewChange && (!trip.isLocked || published) && (
            <div className="inspector-change-actions">
              <button
                className="button secondary"
                onClick={() => onReviewChange(trip.id, "move")}
              >
                {el ? "Μετακίνηση δρομολογίου" : "Move trip"}
              </button>
              {published && (
                <>
                  <button
                    className="button secondary"
                    onClick={() => onReviewChange(trip.id, "replace_driver")}
                  >
                    {el ? "Αντικατάσταση οδηγού" : "Replace driver"}
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => onReviewChange(trip.id, "cancel")}
                  >
                    {el ? "Ακύρωση δρομολογίου" : "Cancel trip"}
                  </button>
                </>
              )}
            </div>
          )}
          <div className="inspector-tabs">
            {(["details", "resource", "validation"] as const).map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t === "details"
                  ? el
                    ? "Λεπτομέρειες"
                    : "Details"
                  : t === "resource"
                    ? el
                      ? "Πόρος"
                      : "Resource"
                    : el
                      ? "Έλεγχος κανόνων"
                      : "Legality"}
                {t === "validation" && trip.hasViolation && (
                  <i className="tiny-dot amber" />
                )}
              </button>
            ))}
          </div>
          <div className="inspector-content">
            {tab === "details" ? (
              <>
                <div className="journey">
                  <div className="journey-stop">
                    <i />
                    <div>
                      <small>{el ? "ΑΝΑΧΩΡΗΣΗ" : "DEPARTURE"}</small>
                      <strong>{stationName(trip.startStation, el)}</strong>
                      <span>
                        {el ? "Σταθμός" : "Station"} {trip.startStation}
                      </span>
                    </div>
                    <b>{timeLabel(trip.startMinutes)}</b>
                  </div>
                  <div className="journey-duration">
                    <Clock3 size={12} />
                    {trip.endMinutes - trip.startMinutes}{" "}
                    {el ? "λεπτά" : "minutes"}
                  </div>
                  <div className="journey-stop arrival">
                    <i />
                    <div>
                      <small>{el ? "ΑΦΙΞΗ" : "ARRIVAL"}</small>
                      <strong>{stationName(trip.endStation, el)}</strong>
                      <span>
                        {el ? "Σταθμός" : "Station"} {trip.endStation}
                      </span>
                    </div>
                    <b>{timeLabel(trip.endMinutes)}</b>
                  </div>
                </div>
                <div className="trip-facts">
                  <div>
                    <MapPin size={16} />
                    <span>
                      {el ? "Απόσταση" : "Distance"}
                      <strong>
                        {trip.distanceKm === undefined
                          ? "—"
                          : `${trip.distanceKm} km`}
                      </strong>
                    </span>
                  </div>
                  <div>
                    <Clock3 size={16} />
                    <span>
                      {el ? "Διάρκεια" : "Duration"}
                      <strong>
                        {Math.floor((trip.endMinutes - trip.startMinutes) / 60)}
                        h {(trip.endMinutes - trip.startMinutes) % 60}m
                      </strong>
                    </span>
                  </div>
                  <div>
                    <BusFront size={16} />
                    <span>
                      {el ? "Τύποι οχήματος" : "Bus types"}
                      <strong>{trip.allowedBusTypes?.join(", ") ?? "—"}</strong>
                    </span>
                  </div>
                  <div>
                    <Route size={16} />
                    <span>
                      {el ? "Τύπος δρόμου" : "Road type"}
                      <strong>{trip.roadType ?? "—"}</strong>
                    </span>
                  </div>
                </div>
                <div className="inspector-section">
                  <h4>{el ? "Ανατεθειμένος πόρος" : "Assigned resource"}</h4>
                  <div className="assigned-person">
                    <span className="resource-symbol">
                      <UserRound size={18} />
                    </span>
                    <div>
                      <strong>
                        {resource
                          ? `${el ? "Οδηγός" : "Driver"} ${resource.driverName}`
                          : "—"}
                      </strong>
                      <small>
                        {el
                          ? "Σταθερό ζεύγος οδηγού–οχήματος"
                          : "Fixed driver–vehicle pairing"}
                      </small>
                    </div>
                  </div>
                  <div className="assigned-person">
                    <span className="resource-symbol">
                      <BusFront size={18} />
                    </span>
                    <div>
                      <strong>
                        {resource
                          ? `${el ? "Όχημα" : "Bus"} ${resource.code}`
                          : "—"}
                      </strong>
                      <small>
                        {resource
                          ? stationName(resource.homeStation, el)
                          : el
                            ? "Χωρίς ανάθεση"
                            : "Unassigned"}
                      </small>
                    </div>
                  </div>
                </div>
              </>
            ) : tab === "resource" ? (
              <div className="inspector-section">
                <h4>
                  {el ? "Ανάθεση σε όχημα / οδηγό" : "Assign to bus / driver"}
                </h4>
                <p className="section-description">
                  {el
                    ? "Η αλλαγή αποθηκεύεται ως νέα έκδοση και ελέγχεται ανεξάρτητα."
                    : "Changes create a new revision version and run independent verification."}
                </p>
                <label className="field-label" htmlFor="resource-assignment">
                  {el ? "Όχημα · Οδηγός" : "Bus · Driver"}
                </label>
                <select
                  id="resource-assignment"
                  className="assignment-select"
                  disabled={isLockedRevision || trip.isLocked}
                  value={trip.resourceId}
                  onChange={(e) => onReassignResource(trip.id, e.target.value)}
                >
                  <option value="UNASSIGNED">
                    {el ? "Χωρίς ανάθεση" : "Unassigned"}
                  </option>
                  {resources.map((r) => (
                    <option key={r.id} value={r.id}>
                      {el ? "Όχημα" : "Bus"} {r.code} · {r.driverName} ·{" "}
                      {stationName(r.homeStation, el)}
                    </option>
                  ))}
                </select>
                <div className="inline-hint">
                  <ShieldCheck size={15} />
                  {el
                    ? "Ο έλεγχος γίνεται στον διακομιστή μετά την αποθήκευση."
                    : "The server validates the schedule after saving."}
                </div>
              </div>
            ) : (
              <div className="inspector-section">
                <h4>
                  {el
                    ? "Ανεξάρτητος έλεγχος διακομιστή"
                    : "Independent server verification"}
                </h4>
                {trip.hasViolation ? (
                  <div role="alert" className="validation-result error">
                    <AlertTriangle size={18} />
                    <div>
                      <strong>
                        {el
                          ? "Εντοπίστηκαν παραβιάσεις"
                          : "Rule violations found"}
                      </strong>
                      <p>{trip.violationMessage}</p>
                    </div>
                  </div>
                ) : (
                  <div className="validation-result success">
                    <ShieldCheck size={18} />
                    <div>
                      <strong>
                        {el
                          ? "Δεν υπάρχουν ευρήματα για το δρομολόγιο"
                          : "No findings for this trip"}
                      </strong>
                      <p>
                        {el
                          ? "Με βάση τους υλοποιημένους κανόνες επικάλυψης, συμβατότητας και αλυσίδων."
                          : "Based on the implemented overlap, eligibility and chain rules."}
                      </p>
                    </div>
                  </div>
                )}
                <p className="section-description">
                  {el
                    ? "Ο έλεγχος αυτός δεν πιστοποιεί συμμόρφωση με την εργατική νομοθεσία."
                    : "This check does not certify transport or labour law compliance."}
                </p>
              </div>
            )}
          </div>
          <div className="inspector-actions">
            <button
              className={`button ${trip.isLocked ? "locked" : "secondary"}`}
              disabled={isLockedRevision}
              onClick={() => onToggleLock(trip.id)}
            >
              {trip.isLocked ? (
                <LockKeyhole size={15} />
              ) : (
                <LockKeyholeOpen size={15} />
              )}{" "}
              {trip.isLocked
                ? el
                  ? "Κλειδωμένο"
                  : "Locked"
                : el
                  ? "Ξεκλείδωτο"
                  : "Unlocked"}
            </button>
            <button
              className="button secondary"
              onClick={() => setTab("resource")}
              disabled={isLockedRevision}
            >
              <BusFront size={15} />
              {el ? "Αλλαγή πόρου" : "Reassign"}
            </button>
          </div>
        </>
      )}
    </aside>
  );
}
