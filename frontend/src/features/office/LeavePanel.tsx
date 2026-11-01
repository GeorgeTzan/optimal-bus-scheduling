"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { Leave } from "./contracts";
import { LeaveDecisionDialog } from "./LeaveDecisionDialog";
import { LeaveRequestForm } from "./LeaveRequestForm";
import { formatInstant, officeCall } from "./office-api";
import { StatePill, useNames } from "./office-ui";

export function LeavePanel({ zone, from, to, canRecord, onImpacts }: { zone: string; from: string; to: string; canRecord: boolean; onImpacts: (count?: number) => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    names = useNames("drivers");
  const [rows, setRows] = useState<Leave[] | null>(null),
    [error, setError] = useState(""),
    [form, setForm] = useState(false),
    [act, setAct] = useState<{ leave: Leave; mode: "decide" | "cancel" } | null>(null),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null); setError("");
    void officeCall<{ items: Leave[] }>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), `/leave-requests?date_from=${from}&date_to=${to}`, undefined, el)
      .then((data) => { if (!controller.signal.aborted) setRows(data.items); })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, from, to, refresh]);
  const done = (count?: number) => { setForm(false); setAct(null); setRefresh((n) => n + 1); onImpacts(count); };
  const can = (row: Leave) => !!row.decision && (row.decision.member || row.decision.external.length > 0);
  return (
    <section aria-labelledby="leave-heading" className="office-panel">
      <header className="office-panel-head">
        <div><h2 id="leave-heading">{el ? "Άδειες" : "Leave"}</h2>
          <p>{el ? "Τα εκκρεμή αιτήματα προειδοποιούν τον προγραμματισμό. Μόνο οι εγκεκριμένες άδειες δεσμεύουν χρόνο." : "Pending requests warn planners. Only approved leave blocks time."}</p></div>
        {canRecord && <button className="button primary" onClick={() => setForm(true)}>{el ? "Νέο αίτημα" : "New request"}</button>}
      </header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {rows === null && !error ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : rows?.length === 0 ? (
        <p className="office-empty">{el ? "Κανένα αίτημα άδειας αυτό τον μήνα." : "No leave requests this month."}</p>
      ) : rows && (
        <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
          <th>{el ? "Οδηγός" : "Driver"}</th><th>{el ? "Από" : "From"}</th><th>{el ? "Έως" : "Until"}</th><th>{el ? "Κατάσταση" : "Status"}</th><th>{el ? "Απόφαση" : "Decision"}</th><th /></tr></thead><tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{names.get(row.driver_id) ?? `#${row.driver_id}`}{row.category ? <small> · {row.category}</small> : null}</td>
              <td>{formatInstant(row.start_utc, zone, el)}</td><td>{formatInstant(row.end_utc, zone, el)}</td>
              <td><StatePill state={row.state} /></td>
              <td>{row.decision_basis === "external" ? (el ? `Από ${row.stated_decision_maker} (καταγράφηκε από το γραφείο)` : `By ${row.stated_decision_maker} (recorded by the office)`) : row.decision_basis ? (el ? "Από υπεύθυνο έγκρισης" : "By an approver") : "—"}</td>
              <td className="office-action-cell">
                {row.state === "pending" && can(row) && <button className="button primary" onClick={() => setAct({ leave: row, mode: "decide" })}>{el ? "Απόφαση" : "Decide"}</button>}
                {row.state === "pending" && canRecord && <button className="button secondary" onClick={() => setAct({ leave: row, mode: "cancel" })}>{el ? "Ακύρωση" : "Cancel"}</button>}
                {row.state === "approved" && can(row) && <button className="button secondary" onClick={() => setAct({ leave: row, mode: "cancel" })}>{el ? "Ακύρωση άδειας" : "Cancel leave"}</button>}
                {row.state === "pending" && !can(row) && !canRecord && <small>{el ? "Δεν είστε υπεύθυνος έγκρισης" : "You are not an approver for this driver"}</small>}
              </td></tr>))}
        </tbody></table></div>)}
      {form && <LeaveRequestForm onClose={() => setForm(false)} onSaved={() => done()} />}
      {act && <LeaveDecisionDialog leave={act.leave} mode={act.mode} driverName={names.get(act.leave.driver_id) ?? `#${act.leave.driver_id}`} onClose={() => setAct(null)} onSaved={done} />}
    </section>
  );
}
