"use client";
import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { Field, Modal } from "../timetables/shared";
import type { Leave } from "./contracts";
import { newRequestId, OfficeError, post } from "./office-api";

/** Decide a pending request, or cancel one. The server decides who may; this only offers what it said is possible. */
export function LeaveDecisionDialog({ leave, mode, driverName, onClose, onSaved }: {
  leave: Leave; mode: "decide" | "cancel"; driverName: string; onClose: () => void; onSaved: (impactCount?: number) => void;
}) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    options = leave.decision;
  const [basis, setBasis] = useState<string>(options?.member ? "member" : String(options?.external[0]?.id ?? "")),
    [decision, setDecision] = useState<"approved" | "rejected">("approved"),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [requestId, setRequestId] = useState(newRequestId);
  useUnsavedChanges(!!text || busy);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  const external = basis !== "member" && basis !== "" ? Number(basis) : null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const common = { expected_version: leave.version, external_route_id: external };
      const result = mode === "decide" ? await post<{ impact_count?: number }>(apiFetch, `/leave-requests/${leave.id}/decision`, { ...common, decision, note: text.trim() || null }, requestId, el)
        : await post<{ impact_count?: number }>(apiFetch, `/leave-requests/${leave.id}/cancel`, { ...common, reason: text.trim() }, requestId, el);
      setRequestId(newRequestId());
      onSaved(result.impact_count);
    } catch (failure) {
      setError(failure instanceof OfficeError ? failure.message : el ? "Δεν αποθηκεύτηκε." : "Not saved.");
    } finally { setBusy(false); }
  };
  const choices = (options?.member ? 1 : 0) + (options?.external.length ?? 0);
  return (
    <Modal title={mode === "decide" ? (el ? "Απόφαση για άδεια" : "Decide leave") : (el ? "Ακύρωση άδειας" : "Cancel leave")} subtitle={driverName} onClose={close} busy={busy}>
      <form onSubmit={submit}>
        <div className="resource-form-body">
          {error && <p className="auth-error" role="alert">{error}</p>}
          {choices > 1 && (
            <Field label={el ? "Ενεργώ ως" : "Acting as"}>
              <select value={basis} onChange={(e) => setBasis(e.target.value)}>
                {options?.member && <option value="member">{el ? "Υπεύθυνος έγκρισης (εγώ)" : "Approver (me)"}</option>}
                {options?.external.map((contact) => (
                  <option key={contact.id} value={contact.id}>{el ? "Καταγραφή απόφασης του/της " : "Record a decision by "}{contact.name}</option>
                ))}
              </select>
            </Field>
          )}
          {external !== null && (
            <p className="resource-form-intro">
              {el ? "Καταγράφετε απόφαση που σας δόθηκε εκτός εφαρμογής. Θα αποθηκευτεί ποιος την κατέγραψε και ποιος την έδωσε." : "You are recording a decision made outside the app. Both you and the stated decision-maker are saved."}
            </p>
          )}
          {mode === "decide" && (
            <fieldset className="office-days"><legend>{el ? "Απόφαση" : "Decision"}</legend>
              {(["approved", "rejected"] as const).map((value) => (
                <label key={value}><input type="radio" name="decision" checked={decision === value} onChange={() => setDecision(value)} />
                  {value === "approved" ? (el ? "Έγκριση" : "Approve") : el ? "Απόρριψη" : "Reject"}</label>))}
            </fieldset>)}
          <Field label={mode === "decide" ? (el ? "Σημείωση (προαιρετική)" : "Note (optional)") : (el ? "Αιτιολογία" : "Reason")}>
            <input required={mode === "cancel"} maxLength={mode === "cancel" ? 1000 : 500} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          {mode === "decide" && decision === "approved" && (
            <p className="office-summary">{el ? "Η έγκριση δεν μετακινεί ούτε ακυρώνει δρομολόγια. Τυχόν επηρεασμένα δρομολόγια θα εμφανιστούν για έλεγχο." : "Approving does not move or cancel trips. Affected trips are shown for review."}</p>)}
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Άκυρο" : "Close"}</button>
          <button className="button primary" disabled={busy || (mode === "cancel" && !text.trim())}>
            {mode === "decide" ? (decision === "approved" ? (el ? "Έγκριση" : "Approve") : el ? "Απόρριψη" : "Reject") : el ? "Ακύρωση άδειας" : "Cancel leave"}</button>
        </footer>
      </form>
    </Modal>
  );
}
