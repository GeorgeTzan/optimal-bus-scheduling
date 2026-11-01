"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { RecordPicker } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import { Field } from "../timetables/shared";
import { OFFICE_CAPABILITIES, type ApprovalRoute, type Grant, type Member } from "./contracts";
import { newRequestId, officeCall, post } from "./office-api";
import { useNames } from "./office-ui";

const capabilityText: Record<string, [string, string]> = {
  "availability.manage": ["Ωράριο και άδειες", "Working time and leave"],
  "maintenance.manage": ["Συντήρηση", "Maintenance"],
  "maintenance.release": ["Αποδέσμευση οχημάτων", "Vehicle release"],
  "office.notes.read": ["Ιδιωτικές σημειώσεις", "Private notes"],
};
/** Administrator-only: per-member office grants (all off by default) and who approves leave. */
export function AccessPanel({ onGrantChange }: { onGrantChange: () => void }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el",
    names = useNames("drivers");
  const [members, setMembers] = useState<Member[]>([]),
    [grants, setGrants] = useState<Grant[]>([]),
    [routes, setRoutes] = useState<ApprovalRoute[]>([]),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0),
    [scope, setScope] = useState<Resource | null>(null),
    [approver, setApprover] = useState(""),
    [contact, setContact] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const call = <T,>(path: string) => officeCall<T>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), path, undefined, el);
    void Promise.all([
      apiFetch("/api/v1/identity/members", { signal: controller.signal }).then((r) => r.json() as Promise<{ members: Member[] }>),
      call<{ grants: Grant[] }>("/grants"), call<{ routes: ApprovalRoute[] }>("/approval-routes"),
    ]).then(([a, b, c]) => { if (!controller.signal.aborted) { setMembers(a.members); setGrants(b.grants); setRoutes(c.routes); } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, refresh]);
  const toggle = async (member: Member, capability: string) => {
    const current = grants.find((g) => g.membership_id === member.id && g.capability === capability);
    setError("");
    try {
      await officeCall(apiFetch, "/grants", { method: "PUT", body: JSON.stringify({ request_id: newRequestId(), membership_id: member.id,
        capability, is_active: !current?.is_active, expected_version: current?.version ?? null }) }, el);
      setRefresh((n) => n + 1);
      onGrantChange();
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); }
  };
  const addRoute = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try {
      await post(apiFetch, "/approval-routes", { driver_id: scope?.id ?? null, membership_id: approver ? Number(approver) : null,
        external_contact_name: approver ? null : contact.trim() }, newRequestId(), el);
      setScope(null); setApprover(""); setContact(""); setRefresh((n) => n + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); }
  };
  const turnOff = async (route: ApprovalRoute) => {
    setError("");
    try {
      await officeCall(apiFetch, `/approval-routes/${route.id}`, { method: "PATCH", body: JSON.stringify({ request_id: newRequestId(), expected_version: route.version, is_active: false }) }, el);
      setRefresh((n) => n + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : ""); }
  };
  const label = (member: Member | undefined) => member ? member.full_name || member.email : "?";
  return (
    <section aria-labelledby="access-heading" className="office-panel">
      <header className="office-panel-head"><div><h2 id="access-heading">{el ? "Πρόσβαση γραφείου" : "Office access"}</h2>
        <p>{el ? "Κανείς δεν έχει αυτές τις ενέργειες αν δεν του δοθούν ρητά, ούτε ο διαχειριστής." : "Nobody has these actions unless you grant them, not even administrators."}</p></div></header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
        <th>{el ? "Μέλος" : "Member"}</th>{OFFICE_CAPABILITIES.map((c) => <th key={c}>{capabilityText[c]?.[el ? 0 : 1]}</th>)}</tr></thead><tbody>
        {members.filter((m) => m.is_active).map((member) => (
          <tr key={member.id}><td>{label(member)}<small> · {member.role}</small></td>
            {OFFICE_CAPABILITIES.map((c) => (
              <td key={c}><input type="checkbox" aria-label={`${label(member)}: ${capabilityText[c]?.[el ? 0 : 1]}`}
                checked={!!grants.find((g) => g.membership_id === member.id && g.capability === c && g.is_active)} onChange={() => void toggle(member, c)} /></td>))}
          </tr>))}
      </tbody></table></div>
      <h3>{el ? "Ποιος εγκρίνει άδειες" : "Who approves leave"}</h3>
      {routes.filter((r) => r.is_active).length === 0 ? <p className="office-empty">{el ? "Δεν έχει οριστεί υπεύθυνος. Οι άδειες μένουν εκκρεμείς." : "No approver is set. Leave stays pending."}</p> : (
        <ul className="office-routes">
          {routes.filter((r) => r.is_active).map((route) => (
            <li key={route.id}><span>{route.driver_id ? names.get(route.driver_id) ?? `#${route.driver_id}` : el ? "Όλοι οι οδηγοί (προεπιλογή)" : "All drivers (default)"} →{" "}
              {route.external_contact_name ? `${route.external_contact_name} (${el ? "εξωτερικός" : "external"})` : label(members.find((m) => m.id === route.membership_id))}</span>
              <button className="button secondary" onClick={() => void turnOff(route)}>{el ? "Απενεργοποίηση" : "Turn off"}</button></li>))}
        </ul>)}
      <form onSubmit={addRoute} className="office-route-form">
        <RecordPicker kind="drivers" label={el ? "Οδηγός (κενό = προεπιλογή)" : "Driver (empty = default for all)"} value={scope} onChange={setScope} />
        <Field label={el ? "Εγκρίνει" : "Approver"}>
          <select value={approver} onChange={(e) => setApprover(e.target.value)}>
            <option value="">{el ? "Εξωτερική επαφή (π.χ. ιδιοκτήτης)" : "External contact (for example the bus owner)"}</option>
            {members.filter((m) => m.is_active).map((m) => <option key={m.id} value={m.id}>{label(m)}</option>)}
          </select>
        </Field>
        {!approver && <Field label={el ? "Όνομα επαφής" : "Contact name"}><input required maxLength={200} value={contact} onChange={(e) => setContact(e.target.value)} /></Field>}
        <button className="button primary">{el ? "Προσθήκη υπευθύνου" : "Add approver"}</button>
      </form>
    </section>
  );
}
