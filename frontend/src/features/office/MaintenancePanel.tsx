"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { VehiclePeriod } from "./contracts";
import { MaintenanceForm, ReleaseDialog } from "./MaintenanceForm";
import { formatInstant, officeCall } from "./office-api";
import { StatePill, useNames } from "./office-ui";

export function MaintenancePanel({ zone, from, to, canRelease, onImpacts }: { zone: string; from: string; to: string; canRelease: boolean; onImpacts: (count?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    names = useNames("vehicles");
  const [rows, setRows] = useState<VehiclePeriod[] | null>(null),
    [error, setError] = useState(""),
    [form, setForm] = useState(false),
    [act, setAct] = useState<{ row: VehiclePeriod; mode: "release" | "cancel" } | null>(null),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null); setError("");
    void officeCall<{ items: VehiclePeriod[] }>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), `/vehicle-periods?date_from=${from}&date_to=${to}`, undefined, el)
      .then((data) => { if (!controller.signal.aborted) setRows(data.items); })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, from, to, refresh]);
  const done = (count?: number) => { setForm(false); setAct(null); setRefresh((n) => n + 1); onImpacts(count); };
  return (
    <section aria-labelledby="fleet-heading" className="office-panel">
      <header className="office-panel-head">
        <div><h2 id="fleet-heading">{el ? "Συντήρηση και ακινησία οχημάτων" : "Vehicle maintenance and out of service"}</h2>
          <p>{el ? "Μια ανοιχτή ακινησία μένει σε ισχύ μέχρι ρητή αποδέσμευση, ακόμη κι αν περάσει η εκτιμώμενη ημερομηνία." : "An open period stays in force until it is explicitly released, even after its estimated date."}</p></div>
        <button className="button primary" onClick={() => setForm(true)}>{el ? "Νέα καταχώριση" : "New entry"}</button>
      </header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {rows === null && !error ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : rows?.length === 0 ? (
        <p className="office-empty">{el ? "Καμία καταχώριση αυτό τον μήνα." : "No entries this month."}</p>
      ) : rows && (
        <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
          <th>{el ? "Όχημα" : "Vehicle"}</th><th>{el ? "Τύπος" : "Type"}</th><th>{el ? "Από" : "From"}</th><th>{el ? "Έως" : "Until"}</th><th>{el ? "Εκτίμηση" : "Estimate"}</th><th>{el ? "Κατάσταση" : "Status"}</th><th /></tr></thead><tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{names.get(row.vehicle_id) ?? `#${row.vehicle_id}`}{row.responsible_label ? <small> · {row.responsible_label}</small> : null}</td>
              <td><StatePill state={row.kind} /></td>
              <td>{formatInstant(row.start_utc, zone, el)}</td>
              <td>{row.kind === "out_of_service" && row.status === "active" ? (el ? "Ανοιχτό" : "Open") : formatInstant(row.end_utc, zone, el)}</td>
              <td>{row.estimated_end_utc ? formatInstant(row.estimated_end_utc, zone, el) : "—"}</td>
              <td><StatePill state={row.status} /></td>
              <td className="office-action-cell">
                {row.status === "active" && row.kind === "out_of_service" && canRelease && <button className="button primary" onClick={() => setAct({ row, mode: "release" })}>{el ? "Αποδέσμευση" : "Release"}</button>}
                {row.status === "active" && (row.kind === "planned_maintenance" || canRelease) && <button className="button secondary" onClick={() => setAct({ row, mode: "cancel" })}>{el ? "Ακύρωση" : "Cancel"}</button>}
              </td></tr>))}
        </tbody></table></div>)}
      {form && <MaintenanceForm onClose={() => setForm(false)} onSaved={done} />}
      {act && <ReleaseDialog row={act.row} mode={act.mode} vehicleName={names.get(act.row.vehicle_id) ?? `#${act.row.vehicle_id}`} onClose={() => setAct(null)} onSaved={done} />}
    </section>
  );
}
