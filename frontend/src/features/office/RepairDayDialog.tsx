"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { mayLeaveWorkspace } from "../navigation/unsaved-changes";
import { Field, Modal } from "../timetables/shared";
import { newRequestId } from "./office-api";

export interface RepairRow {
  trip_id: string;
  trip_code: string | null;
  resource_id: string;
  driver_id: number;
}
interface Crew {
  resource_id: string;
  driver_name: string;
  vehicle_label?: string;
}
interface Revision {
  version: number;
  source_resources: Crew[];
  assignments: { trip_id: string; is_locked: boolean }[];
  problem: { chains: { trip_ids: string[] }[] };
}
interface Preview {
  verification: { valid: boolean; violations: { message: string }[] };
}
type Choice = { action: "unassign" | "move" | "cancel"; target: string };

/** One reviewed change for every affected trip of a published day, whichever drivers or vehicles are involved. The server checks the whole result. */
export function RepairDayDialog({ serviceDate, names, onClose, onSaved }: {
  serviceDate: string; names: Map<number, string>; onClose: () => void; onSaved: (date: string) => void;
}) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [publication, setPublication] = useState<{ id: string; revision: Revision } | null>(null),
    [rows, setRows] = useState<RepairRow[]>([]),
    [choices, setChoices] = useState<Record<string, Choice>>({}),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false),
    attempt = useRef<{ key: string; id: string } | null>(null),
    generation = useRef(0),
    mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);  // re-armed so a development double-mount does not discard answers
  const invalidate = () => { generation.current += 1; setPreview(null); };
  const dirty = !!reason || confirmed || Object.keys(choices).length > 0;
  useUnsavedChanges(!saved && (dirty || busy));
  // Report success only after this dialog has re-rendered as clean, so leaving for the Studio is not blocked by its own pending-edit guard.
  useEffect(() => { if (saved) onSaved(serviceDate); }, [saved, onSaved, serviceDate]);
  const close = () => { if (!busy && mayLeaveWorkspace()) onClose(); };
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const day = await apiFetch(`/api/v1/operations/day?service_date=${serviceDate}`, { signal: controller.signal });
      const data = (await day.json()) as { publication: { publication_id: string; revision_id: string } | null };
      if (!day.ok || !data.publication) throw Error();
      const revision = await apiFetch(`/api/v1/scheduling/revisions/${data.publication.revision_id}`, { signal: controller.signal });
      if (!revision.ok) throw Error();
      // Every affected trip of the day, not only the first page of the list: the change must cover all of them to pass.
      const found: RepairRow[] = [];
      for (let page = 1; page <= 50; page += 1) {
        const response = await apiFetch(`/api/v1/office/impacts?date_from=${serviceDate}&date_to=${serviceDate}&page=${page}&page_size=100`, { signal: controller.signal });
        if (!response.ok) throw Error();
        const batch = (await response.json()) as { items: (RepairRow & { status: string; operated: boolean })[]; total: number };
        found.push(...batch.items.filter((row) => row.status === "published" && !row.operated));
        if (page * 100 >= batch.total) break;
      }
      if (!controller.signal.aborted) setRows(found);
      if (!controller.signal.aborted) setPublication({ id: data.publication.publication_id, revision: (await revision.json()) as Revision });
    })().catch(() => { if (!controller.signal.aborted) setError(el ? "Δεν φορτώθηκε η δημοσίευση. Κλείστε και δοκιμάστε ξανά." : "The publication could not be loaded. Close and try again."); });
    return () => controller.abort();
  }, [apiFetch, serviceDate, el]);
  // A mandatory chain stays together on one crew, so a chained trip can only be moved or cancelled, and its partners follow it.
  const partners = (tripId: string) => [...new Set((publication?.revision.problem.chains ?? []).filter((chain) => chain.trip_ids.includes(tripId)).flatMap((chain) => chain.trip_ids))].filter((id) => id !== tripId);
  const chained = (tripId: string) => partners(tripId).length > 0;
  const choice = (row: RepairRow): Choice => choices[row.trip_id] ?? { action: chained(row.trip_id) ? "move" : "unassign", target: "" };
  const set = (row: RepairRow, next: Partial<Choice>) => { setChoices({ ...choices, [row.trip_id]: { ...choice(row), ...next } }); invalidate(); attempt.current = null; };
  const locked = (tripId: string) => publication?.revision.assignments.find((item) => item.trip_id === tripId)?.is_locked === true;
  const ready = !!publication && rows.length > 0 && !!reason.trim() && confirmed && rows.every((row) => choice(row).action !== "move" || !!choice(row).target);
  function body() {
    const patches = new Map<string, object>();
    const patch = (tripId: string, picked: Choice) => {
      const unlock = locked(tripId) ? { unlock: true } : {};
      patches.set(tripId, picked.action === "cancel" ? { trip_id: tripId, operation: "cancel", reason: reason.trim(), ...unlock }
        : picked.action === "move" ? { trip_id: tripId, new_resource_id: picked.target, ...unlock }
          : { trip_id: tripId, operation: "unassign", ...unlock });
    };
    for (const row of rows) { patch(row.trip_id, choice(row)); }
    for (const row of rows) { for (const partner of partners(row.trip_id)) { if (!patches.has(partner)) patch(partner, choice(row)); } }
    return { publication_id: publication?.id, version: publication?.revision.version, reason: reason.trim(), reviewed_not_started: [...patches.keys()], patches: [...patches.values()] };
  }
  async function send(path: string, extra: object) {
    const response = await apiFetch(path, { method: "POST", body: JSON.stringify({ ...body(), ...extra }) });
    const value = (await response.json()) as Preview & { detail?: { message?: string; verification?: Preview["verification"] } | string };
    return { response, value };
  }
  async function check(event: FormEvent) {
    event.preventDefault();
    if (busy || !ready) return;
    setBusy(true); setError("");
    const asked = generation.current;
    try {
      const { response, value } = await send("/api/v1/scheduling/changes/preview", {});
      if (!response.ok) throw Error(typeof value.detail === "string" ? value.detail : (value.detail?.message ?? (el ? "Δεν ολοκληρώθηκε ο έλεγχος." : "The change could not be checked.")));
      if (mounted.current && asked === generation.current) setPreview(value);  // an answer for choices that have since changed is never shown
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); } finally { setBusy(false); }
  }
  async function save() {
    if (busy || !preview?.verification.valid) return;
    const key = JSON.stringify(body());
    attempt.current = attempt.current?.key === key ? attempt.current : { key, id: newRequestId() };
    setBusy(true); setError("");
    try {
      const { response, value } = await send("/api/v1/scheduling/changes", { request_id: attempt.current.id });
      if (!response.ok) {
        const detail = value.detail;
        if (typeof detail === "object" && detail?.verification) setPreview({ verification: detail.verification });
        throw Error(typeof detail === "string" ? detail : (detail?.message ?? (el ? "Δεν αποθηκεύτηκε." : "The change was not saved.")));
      }
      setSaved(true);
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); } finally { setBusy(false); }
  }
  const crews = (row: RepairRow) => publication?.revision.source_resources.filter((crew) => crew.resource_id !== row.resource_id) ?? [];
  return (
    <Modal title={el ? `Επισκευή ημέρας ${serviceDate}` : `Repair ${serviceDate} in one change`} subtitle={el ? "Επηρεασμένα δρομολόγια" : "Affected trips"} onClose={close} busy={busy}>
      <form onSubmit={check}>
        <div className="resource-form-body">
          <p className="resource-form-intro">{el
            ? "Ένας έλεγχος καλύπτει όλα τα επηρεασμένα δρομολόγια της ημέρας. Δημιουργείται πρόχειρη διάδοχη έκδοση· η δημοσιευμένη παραμένει σε ισχύ μέχρι να δημοσιευτεί. Δεν στέλνεται ειδοποίηση."
            : "One check covers every affected trip of the day, whichever drivers are involved. This creates a draft successor; the published schedule stays current until it is published. No notification is sent."}</p>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <ul className="office-repair-list">
            {rows.map((row) => (
              <li key={row.trip_id}>
                <strong>{row.trip_code ?? row.trip_id}</strong>
                <span>{names.get(row.driver_id) ?? `#${row.driver_id}`}{chained(row.trip_id) ? ` · ${el ? "αλυσίδα μαζί με" : "chained with"} ${partners(row.trip_id).join(", ")}` : ""}{locked(row.trip_id) ? ` · ${el ? "κλειδωμένο, θα ξεκλειδωθεί" : "locked, the lock will be released"}` : ""}</span>
                <select style={{ gridColumn: choice(row).action === "move" ? undefined : "span 2" }} aria-label={`${el ? "Ενέργεια για" : "Action for"} ${row.trip_code ?? row.trip_id}`} value={choice(row).action} onChange={(e) => set(row, { action: e.target.value as Choice["action"] })}>
                  {!chained(row.trip_id) && <option value="unassign">{el ? "Αφήνεται χωρίς ανάθεση" : "Leave unassigned"}</option>}
                  <option value="move">{el ? "Μετακίνηση σε άλλο συνεργείο" : "Move to another crew"}</option>
                  <option value="cancel">{el ? "Ακύρωση δρομολογίου" : "Cancel the service"}</option>
                </select>
                {choice(row).action === "move" && (
                  <select aria-label={`${el ? "Συνεργείο για" : "Crew for"} ${row.trip_code ?? row.trip_id}`} value={choice(row).target} onChange={(e) => set(row, { target: e.target.value })}>
                    <option value="">{el ? "Επιλέξτε συνεργείο" : "Choose a crew"}</option>
                    {crews(row).map((crew) => <option key={crew.resource_id} value={crew.resource_id}>{crew.driver_name}{crew.vehicle_label ? ` · ${crew.vehicle_label}` : ""}</option>)}
                  </select>)}
              </li>))}
          </ul>
          <Field label={el ? "Λόγος (αποθηκεύεται στο ιστορικό)" : "Reason (kept in the history)"}><input required maxLength={1000} value={reason} onChange={(e) => { setReason(e.target.value); invalidate(); attempt.current = null; }} /></Field>
          <label className="office-check"><input type="checkbox" checked={confirmed} onChange={(e) => { setConfirmed(e.target.checked); invalidate(); }} />
            {el ? "Επιβεβαιώνω ότι κανένα από αυτά τα δρομολόγια δεν έχει ξεκινήσει." : "I confirm none of these trips has started."}</label>
          {preview && (preview.verification.valid
            ? <p className="office-summary" role="status">{el ? "Οι έλεγχοι πέρασαν. Μπορείτε να αποθηκεύσετε το πρόχειρο." : "Checks passed. You can save the draft."}</p>
            : <div role="alert" className="auth-error"><strong>{el ? "Δεν μπορεί να αποθηκευτεί ακόμη:" : "Cannot be saved yet:"}</strong><ul>{preview.verification.violations.slice(0, 8).map((item, index) => <li key={index}>{item.message}</li>)}</ul></div>)}
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>{el ? "Κλείσιμο" : "Close"}</button>
          <button className="button secondary" disabled={busy || !ready}>{el ? "Έλεγχος" : "Check"}</button>
          <button type="button" className="button primary" disabled={busy || !preview?.verification.valid} onClick={() => void save()}>{el ? "Αποθήκευση πρόχειρου" : "Save draft"}</button>
        </footer>
      </form>
    </Modal>
  );
}
