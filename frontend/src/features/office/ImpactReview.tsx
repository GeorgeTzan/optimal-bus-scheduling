"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { formatInstant, officeCall } from "./office-api";
import { RepairDayDialog } from "./RepairDayDialog";
import { useNames } from "./office-ui";

interface Impact {
  service_date: string;
  status: string;
  revision_id: string;
  resource_id: string;
  trip_id: string;
  trip_code: string | null;
  driver_id: number;
  vehicle_id: number;
  start_utc: string;
  end_utc: string;
  cause: "driver" | "vehicle" | "both" | "unknown";
  operated: boolean;
}
interface ImpactPage {
  items: Impact[];
  total: number;
  needs_review: number;
}
/** Read-only. Shows where current availability puts scheduled work at risk, and links to the existing reviewed-change tools. */
export function ImpactReview({ zone, from, to, onOpenStudio }: { zone: string; from: string; to: string; onOpenStudio: (date: string) => void }) {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el",
    drivers = useNames("drivers"),
    vehicles = useNames("vehicles");
  const [data, setData] = useState<ImpactPage | null>(null),
    [error, setError] = useState(""),
    [repair, setRepair] = useState<string | null>(null),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    void officeCall<ImpactPage>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), `/impacts?date_from=${from}&date_to=${to}&page_size=100`, undefined, el)
      .then((page) => { if (!controller.signal.aborted) setData(page); })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, from, to, refresh]);
  const days = [...new Set((data?.items ?? []).filter((row) => row.status === "published" && !row.operated).map((row) => row.service_date))];
  const cause = { driver: [el ? "Οδηγός" : "Driver"], vehicle: [el ? "Όχημα" : "Vehicle"], both: [el ? "Οδηγός και όχημα" : "Driver and vehicle"], unknown: [el ? "Άγνωστο ωράριο οδηγού" : "Driver working time unknown"] };
  return (
    <section aria-labelledby="impact-heading" className="office-panel">
      <header className="office-panel-head">
        <div><h2 id="impact-heading">{el ? "Επηρεασμένα δρομολόγια" : "Affected trips"}</h2>
          <p>{el
            ? "Δρομολόγια που δεν ταιριάζουν πια με τη διαθεσιμότητα. Τίποτα δεν έχει αλλάξει: η δημοσιευμένη ημέρα παραμένει σε ισχύ μέχρι να δημοσιευτεί διάδοχη. Δεν έχει σταλεί καμία ειδοποίηση."
            : "Trips that no longer fit availability. Nothing has been changed: the published day stays current until a successor is published. No notification was sent."}</p></div>
      </header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {!data && !error ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : data?.items.length === 0 ? (
        <p className="office-empty">{el ? "Κανένα επηρεασμένο δρομολόγιο αυτό τον μήνα." : "No affected trips this month."}</p>
      ) : data && (
        <>
          {data.total > data.items.length && <p className="office-summary">{el ? `Εμφανίζονται τα πρώτα ${data.items.length} από ${data.total}.` : `Showing the first ${data.items.length} of ${data.total}. Narrow the month to see the rest.`}</p>}
          {user?.permissions.includes("schedule.write") && days.length > 0 && (
            <div className="office-actions">{days.map((day) => <button key={day} className="button primary" onClick={() => setRepair(day)}>{el ? `Επισκευή ${day} με μία αλλαγή` : `Repair ${day} in one change`}</button>)}</div>)}
          <p className="office-summary" role="status">{el ? `${data.needs_review} ${data.needs_review === 1 ? "δρομολόγιο χρειάζεται" : "δρομολόγια χρειάζονται"} έλεγχο.` : `${data.needs_review} ${data.needs_review === 1 ? "trip needs" : "trips need"} review.`}</p>
          <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
            <th>{el ? "Ημερομηνία" : "Date"}</th><th>{el ? "Δρομολόγιο" : "Trip"}</th><th>{el ? "Οδηγός" : "Driver"}</th><th>{el ? "Όχημα" : "Vehicle"}</th>
            <th>{el ? "Ώρα" : "Time"}</th><th>{el ? "Αιτία" : "Cause"}</th><th>{el ? "Έκδοση" : "Version"}</th><th /></tr></thead><tbody>
            {data.items.map((row) => (
              <tr key={`${row.revision_id}:${row.trip_id}`}>
                <td>{row.service_date}</td><td>{row.trip_code ?? row.trip_id}</td>
                <td>{drivers.get(row.driver_id) ?? `#${row.driver_id}`}</td><td>{vehicles.get(row.vehicle_id) ?? `#${row.vehicle_id}`}</td>
                <td>{formatInstant(row.start_utc, zone, el)}</td><td>{cause[row.cause][0]}</td>
                <td>{row.status === "published" ? (el ? "Δημοσιευμένο" : "Published") : el ? "Πρόχειρο" : "Draft"}
                  {row.operated ? <small> · {el ? "έχει ήδη εκτελεστεί, δεν αλλάζει" : "already operated, cannot change"}</small> : null}</td>
                <td className="office-action-cell"><button className="button secondary" disabled={row.operated} onClick={() => onOpenStudio(row.service_date)}>{el ? "Άνοιγμα στον Προγραμματισμό" : "Open in Scheduling Studio"}</button></td>
              </tr>))}
          </tbody></table></div>
        </>)}
      {repair && <RepairDayDialog serviceDate={repair} names={drivers} onClose={() => setRepair(null)}
        onSaved={(date) => { setRepair(null); setRefresh((n) => n + 1); onOpenStudio(date); }} />}
    </section>
  );
}
