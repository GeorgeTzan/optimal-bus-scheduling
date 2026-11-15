"use client";
import { citation } from "../workrules/WorkRulesWorkspace";
import { scheduleDisplay } from "./display";
import { studioResources, type PersistedRevision, type Violation } from "./revision-api";
import type { StudioTrip } from "./types";

export interface FindingLabels {
  driver: (id: string | undefined) => string | null;
  trip: (id: string | null) => string | null;
}

export function findingLabels(revision: PersistedRevision, trips: StudioTrip[]): FindingLabels {
  const { timeLabel } = scheduleDisplay({
    timezone: revision.timezone,
    serviceDayStartUtc: revision.service_day_start_utc,
    dayBoundariesMinutes: revision.day_boundaries_minutes,
  });
  const resources = new Map(studioResources(revision).map((item) => [item.id, item.driverName]));
  const names = new Map<string, string>();
  for (const resource of revision.problem.resources) {
    const name = resources.get(resource.resource_id);
    if (name) names.set(String(resource.driver_id), name);
  }
  return {
    driver: (id) => (id ? (names.get(id) ?? null) : null),
    trip: (id) => {
      const trip = trips.find((item) => item.id === id);
      return trip ? `${trip.tripCode} ${timeLabel(trip.startMinutes)}` : null;
    },
  };
}

type Text = [string, string];

export const isWorkRule = (violation: Violation) => violation.rule_id.startsWith("WR_");
export const blocksApproval = (violation: Violation) =>
  isWorkRule(violation) && violation.severity?.toLowerCase() === "error";

const clock = (value: number | null | undefined) =>
  typeof value === "number" ? `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}` : "—";

function instant(value: string | undefined, tz: string, el: boolean) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: tz || "Europe/Athens",
  }).format(date);
}

const partial: Text = [" Το ιστορικό είναι ελλιπές· το σύνολο μπορεί να είναι υψηλότερο.", " History is incomplete; the total may be higher."];

function words(v: Violation, tz: string, el: boolean): Text {
  const [m, l] = [clock(v.measured), clock(v.limit)];
  const hint = v.hint ?? {};
  const more = hint.partial === "true" ? partial : ["", ""];
  switch (v.rule_id) {
    case "WR_DAILY_WORK":
      return [`Εργάζεται ${m} σε μία ημέρα (όριο ${l}).`, `Works ${m} in one day (limit ${l}).`];
    case "WR_CONTINUOUS_DRIVING":
      return [`Οδηγεί ${m} συνεχόμενα χωρίς διάλειμμα (όριο ${l}).`, `Drives ${m} without a break (limit ${l}).`];
    case "WR_URBAN_BREAK":
      return [`Στις αστικές γραμμές λείπει διάλειμμα ${l}.`, `A break of ${l} is missing on urban routes.`];
    case "WR_DAILY_DRIVING":
      return [`Οδηγεί ${m} σε μία ημέρα (όριο ${l}).`, `Drives ${m} in one day (limit ${l}).`];
    case "WR_DAILY_REST": {
      const until = instant(hint.rest_until, tz, el);
      return [
        `Μόνο ${m} ανάπαυση από την προηγούμενη υπηρεσία (όριο ${l}). Νωρίτερη έναρξη: ${until}.`,
        `Only ${m} rest after the previous duty (limit ${l}). Earliest start: ${until}.`,
      ];
    }
    case "WR_REDUCED_REST_COMPENSATION":
      return [
        `Η μειωμένη ημερήσια ανάπαυση δεν αναπληρώνεται εντός της εβδομάδας (ανάπαυση ${m}, απαιτούνται ${l}).`,
        `Reduced daily rest is not made up within the week (rest ${m}, ${l} needed).`,
      ];
    case "WR_WEEKLY_WORK":
      return [`Εργάζεται ${m} την εβδομάδα (όριο ${l}).${more[0]}`, `Works ${m} this week (limit ${l}).${more[1]}`];
    case "WR_WEEKLY_DRIVING":
      return [`Οδηγεί ${m} την εβδομάδα (όριο ${l}).${more[0]}`, `Drives ${m} this week (limit ${l}).${more[1]}`];
    case "WR_FORTNIGHT_DRIVING":
      return [`Οδηγεί ${m} σε δεκαπενθήμερο (όριο ${l}).${more[0]}`, `Drives ${m} in a fortnight (limit ${l}).${more[1]}`];
    case "WR_INTERRUPTIONS":
      return hint.measure === "minutes"
        ? [`Διακοπές ${m} την εβδομάδα (όριο ${l}).${more[0]}`, `Interruptions total ${m} this week (limit ${l}).${more[1]}`]
        : [`${v.measured ?? "—"} διακοπές την εβδομάδα (όριο ${v.limit ?? "—"}).${more[0]}`, `${v.measured ?? "—"} interruptions this week (limit ${v.limit ?? "—"}).${more[1]}`];
    case "WR_WEEKLY_REST":
      return [
        `${v.measured ?? "—"} εργάσιμες ημέρες στη σειρά χωρίς εβδομαδιαία ανάπαυση (όριο ${v.limit ?? "—"}).${more[0]}`,
        `${v.measured ?? "—"} working days in a row without weekly rest (limit ${v.limit ?? "—"}).${more[1]}`,
      ];
    case "WR_WEEKLY_REST_BASE":
      return [
        `Η εβδομαδιαία ανάπαυση (${m}) ξεκινά μακριά από τη βάση.`,
        `Weekly rest (${m}) starts away from base.`,
      ];
    case "WR_SUNDAY_REST":
      return [
        `Καμία ελεύθερη Κυριακή σε ${v.limit ?? "—"} εβδομάδες.`,
        `No free Sunday within ${v.limit ?? "—"} weeks.`,
      ];
    case "WR_OVERTIME_YEAR":
      return [`Υπερωρίες ${m} στο έτος (όριο ${l}).${more[0]}`, `Overtime ${m} this year (limit ${l}).${more[1]}`];
    case "WR_OVERTIME_YEAR_ABSOLUTE":
      return [`Υπερωρίες ${m} στο έτος, πάνω από το απόλυτο όριο ${l}.${more[0]}`, `Overtime ${m} this year, above the absolute cap of ${l}.${more[1]}`];
    case "WR_SPLIT_SHIFT":
      return [`Διακεκομμένο ωράριο με ${v.measured ?? "—"} διακοπή(ές).`, `Split shift with ${v.measured ?? "—"} interruption(s).`];
    case "WR_MUST_RETURN_BASE":
      return ["Ο οδηγός πρέπει να επιστρέφει στη βάση, αλλά τελειώνει αλλού.", "The driver must return to base but finishes elsewhere."];
    case "WR_FORBIDDEN_DRIVER_ROUTE":
      return ["Ο οδηγός έχει απαγόρευση σε γραμμή αυτής της υπηρεσίας.", "The driver is barred from a route on this duty."];
    case "WR_FORBIDDEN_VEHICLE_ROUTE":
      return ["Το όχημα έχει απαγόρευση σε γραμμή αυτής της υπηρεσίας.", "The vehicle is barred from a route on this duty."];
    case "WR_OVERNIGHT_NOT_ALLOWED":
      return ["Ο οδηγός δεν επιτρέπεται να διανυκτερεύει.", "The driver may not stay overnight."];
    case "WR_OVERNIGHT_REST_DAY":
      return ["Δουλειά την ημέρα μετά από διανυκτέρευση· απαιτείται ρεπό.", "Working the day after an overnight; a rest day is required."];
    case "WR_OVERNIGHT_CONSECUTIVE":
      return ["Δεύτερη διανυκτέρευση στη σειρά.", "A second overnight in a row."];
    case "WR_SHIFT_ROTATION":
      return ["Η εναλλαγή βαρδιών δεν τηρείται.", "Shift rotation is not respected."];
    case "WR_HISTORY_UNKNOWN":
      return [
        `Το ιστορικό του οδηγού πριν από ${v.hint?.known_from ?? "—"} είναι άγνωστο· οι εβδομαδιαίοι έλεγχοι είναι μερικοί.`,
        `Driver history before ${v.hint?.known_from ?? "—"} is unknown; weekly checks are partial.`,
      ];
    default:
      return [`Εύρημα ${v.rule_id}: μετρήθηκε ${m}, όριο ${l}.`, `Finding ${v.rule_id}: measured ${m}, limit ${l}.`];
  }
}

const origins: Record<string, Text> = {
  "Company rule": ["Κανόνας εταιρείας", "Company rule"],
  "Driver restriction": ["Περιορισμός οδηγού", "Driver restriction"],
  "Driver history": ["Ιστορικό οδηγού", "Driver history"],
};

function pill(v: Violation): { cls: string; text: Text } {
  if (v.kind === "info") return { cls: "neutral", text: ["Σημείωση", "Note"] };
  if (v.kind === "legal" && v.preexisting) return { cls: "neutral", text: ["Υπάρχον", "Existing"] };
  if (v.kind === "legal") return { cls: "bad", text: ["Νόμος", "Law"] };
  return { cls: "warning", text: ["Εταιρεία", "Company"] };
}

export const canOverride = (v: Violation) => v.kind === "warning" && !!v.finding_key;
export const firstTrip = (v: Violation) => v.entity_ids[1] ?? null;

export function FindingsList({
  violations,
  el,
  timezone,
  labels,
  onShow,
  onOverride,
}: {
  violations: Violation[];
  el: boolean;
  timezone: string;
  labels: FindingLabels;
  onShow?: (tripId: string) => void;
  onOverride?: (violation: Violation) => void;
}) {
  const lang = el ? 0 : 1;
  return (
    <ul className="work-findings" aria-label={el ? "Ευρήματα κανόνων εργασίας" : "Work-rule findings"}>
      {violations.map((v, index) => {
        const tag = pill(v);
        const trip = firstTrip(v);
        const driver = labels.driver(v.entity_ids[0]);
        const where = labels.trip(trip);
        const origin = v.source ? (origins[v.source]?.[lang] ?? citation(v.source, el)) : null;
        const detail = [origin, where].filter(Boolean).join(" · ");
        return (
          <li key={`${v.finding_key ?? v.rule_id}-${index}`}>
            <span className={`status-pill ${tag.cls}`}>{tag.text[lang]}</span>
            <span className="finding-text">
              <span>
                {driver && <strong>{driver}: </strong>}
                {words(v, timezone, el)[lang]}
              </span>
              {detail && <small>{detail}</small>}
            </span>
            {onShow && trip && (
              <button type="button" className="button secondary" onClick={() => onShow(trip)}>
                {el ? "Δείξε" : "Show"}
              </button>
            )}
            {onOverride && canOverride(v) && (
              <button type="button" className="button secondary" onClick={() => onOverride(v)}>
                {el ? "Παράκαμψη…" : "Override…"}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function WorkRulesTab({
  violations,
  el,
  timezone,
  labels,
  onShow,
  onOverride,
}: {
  violations: Violation[];
  el: boolean;
  timezone: string;
  labels: FindingLabels;
  onShow: (tripId: string) => void;
  onOverride?: (violation: Violation) => void;
}) {
  if (violations.length === 0)
    return (
      <div className="table-empty">
        <strong>{el ? "Κανένα εύρημα κανόνων εργασίας" : "No work-rule findings"}</strong>
      </div>
    );
  return <FindingsList violations={violations} el={el} timezone={timezone} labels={labels} onShow={onShow} onOverride={onOverride} />;
}
