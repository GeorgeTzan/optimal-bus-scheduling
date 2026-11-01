"use client";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { Field, Modal } from "../timetables/shared";
import { ROLES, TeamError, deliveryText, requestId, roleText, teamCall, type Invitation, type Role, type TeamMember } from "./team-api";

type Confirm =
  | { kind: "role"; member: TeamMember; role: Role }
  | { kind: "deactivate"; member: TeamMember }
  | { kind: "revoke"; invitation: Invitation };

/** Administrators manage who can sign in and in which role. Own row has no actions; risky changes ask first and name the effect. */
export function TeamWorkspace() {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el",
    lang = el ? 0 : 1;
  const [members, setMembers] = useState<TeamMember[] | null>(null),
    [invitations, setInvitations] = useState<Invitation[] | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [email, setEmail] = useState(""),
    [role, setRole] = useState<Role>("dispatcher"),
    [confirm, setConfirm] = useState<Confirm | null>(null),
    attempt = useRef<{ key: string; id: string } | null>(null),
    sequence = useRef(0);
  const load = useCallback(async (signal?: AbortSignal, keepError = false) => {
    const mine = ++sequence.current;  // only the newest load may update the screen
    try {
      const [a, b] = await Promise.all([
        teamCall<{ members: TeamMember[] }>(apiFetch, "/members", { signal }, el),
        teamCall<{ invitations: Invitation[] }>(apiFetch, "/invitations", { signal }, el),
      ]);
      if (signal?.aborted || mine !== sequence.current) return;
      setMembers(a.members); setInvitations(b.invitations);
      if (!keepError) setError("");
    } catch (failure) {
      if (failure instanceof DOMException && failure.name === "AbortError") return;
      if (mine !== sequence.current) return;
      setError((previous) => (keepError && previous ? previous : failure instanceof Error ? failure.message : ""));
      setMembers((current) => current ?? []); setInvitations((current) => current ?? []);
    }
  }, [apiFetch, el]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  async function act(key: string, path: string, options: (id: string) => RequestInit, done: string): Promise<boolean> {
    if (busy) return false;
    attempt.current = attempt.current?.key === key ? attempt.current : { key, id: requestId() };
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await teamCall<{ delivery_status?: string | null }>(apiFetch, path, options(attempt.current.id), el);
      attempt.current = null;
      // When mail is not configured nothing was sent, so the notice says only that: never "sent" or "resent".
      const status = value.delivery_status;
      setNotice(status === undefined || status === null ? done : status === "not_configured" ? deliveryText(status, el) : `${done} ${deliveryText(status, el)}`);
      setConfirm(null);
      await load();
      return true;
    } catch (failure) {
      attempt.current = null;
      setError(failure instanceof TeamError ? failure.message : "");
      setConfirm(null);
      await load(undefined, true);
      return false;
    } finally { setBusy(false); }
  }
  const change = (member: TeamMember, fields: { role?: Role; is_active?: boolean }, done: string) =>
    act(`m:${member.id}:${member.version}:${JSON.stringify(fields)}`, `/members/${member.id}`, (id) => ({ method: "PATCH", body: JSON.stringify({ version: member.version, ...fields, request_id: id }) }), done);
  const wantRole = (member: TeamMember, next: Role) => {
    if (next === member.role) return;
    if (member.role === "admin" || next === "admin") setConfirm({ kind: "role", member, role: next });
    else void change(member, { role: next }, el ? "Ο ρόλος άλλαξε." : "Role changed.");
  };
  async function invite(event: FormEvent) {
    event.preventDefault();
    const address = email.trim();
    const ok = await act(`i:${address}:${role}`, "/invitations", (id) => ({ method: "POST", body: JSON.stringify({ email: address, role, request_id: id }) }), el ? "Η πρόσκληση δημιουργήθηκε." : "Invitation created.");
    if (ok) setEmail("");  // a refused invitation keeps what was typed
  }
  const day = (iso: string) => new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
  const name = (m: TeamMember) => m.full_name ?? m.email;
  if (!members || !invitations) return <p role="status" className="resource-workspace">{el ? "Φόρτωση…" : "Loading…"}</p>;
  return (
    <section className="resource-workspace office-workspace" aria-labelledby="team-heading">
      <header className="resource-heading">
        <div><span className="resource-eyebrow">{el ? "ΟΡΓΑΝΙΣΜΟΣ" : "ORGANIZATION"}</span><h1 id="team-heading">{el ? "Ομάδα και πρόσβαση" : "Team and access"}</h1>
          <p>{el ? "Ποιοι μπορούν να συνδεθούν και με ποιον ρόλο. Οι αλλαγές ισχύουν αμέσως και κλείνουν τις ενεργές συνεδρίες του ατόμου." : "Who can sign in and in which role. Changes apply at once and end that person's active sessions."}</p></div>
      </header>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {notice && <p className="office-summary" role="status">{notice}</p>}
      <section className="office-panel" aria-labelledby="invite-heading">
        <h2 id="invite-heading">{el ? "Πρόσκληση ατόμου" : "Invite a person"}</h2>
        <form onSubmit={invite} className="team-invite">
          <Field label={el ? "Email" : "Email"}><input type="email" required maxLength={254} autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label={el ? "Ρόλος" : "Role"}>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r} value={r}>{roleText[r].name[lang]} — {roleText[r].meaning[lang]}</option>)}</select></Field>
          <button className="button primary" disabled={busy || !email.trim()}>{el ? "Αποστολή πρόσκλησης" : "Send invitation"}</button>
        </form>
        <p className="driver-muted">{el ? "Για οδηγό, στείλτε την πρόσκληση από την εγγραφή του οδηγού στη σελίδα Οδηγοί." : "To invite a driver, use the invitation on the driver's record on the Drivers page."}</p>
      </section>
      <section className="office-panel" aria-labelledby="pending-heading">
        <h2 id="pending-heading">{el ? "Εκκρεμείς προσκλήσεις" : "Pending invitations"}</h2>
        {invitations.length === 0 ? <p className="office-empty">{el ? "Δεν υπάρχουν εκκρεμείς προσκλήσεις." : "No pending invitations."}</p> : (
          <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
            <th>Email</th><th>{el ? "Ρόλος" : "Role"}</th><th>{el ? "Λήξη" : "Expires"}</th><th>{el ? "Αποστολή" : "Delivery"}</th><th /></tr></thead><tbody>
            {invitations.map((item) => (
              <tr key={item.id}>
                <td>{item.email}</td><td>{roleText[item.role].name[lang]}</td>
                <td>{day(item.expires_at)}{item.expired ? ` · ${el ? "έληξε" : "expired"}` : ""}</td>
                <td>{deliveryText(item.delivery_status, el)}</td>
                <td className="office-action-cell">
                  <button className="button secondary" disabled={busy} aria-label={`${el ? "Εκ νέου αποστολή σε" : "Resend to"} ${item.email}`} onClick={() => void act(`r:${item.id}`, `/invitations/${item.id}/resend`, (id) => ({ method: "POST", body: JSON.stringify({ request_id: id }) }), el ? "Η πρόσκληση ανανεώθηκε." : "Invitation renewed.")}>{el ? "Νέα αποστολή" : "Resend"}</button>{" "}
                  <button className="button secondary" disabled={busy} aria-label={`${el ? "Ανάκληση για" : "Revoke for"} ${item.email}`} onClick={() => setConfirm({ kind: "revoke", invitation: item })}>{el ? "Ανάκληση" : "Revoke"}</button></td></tr>))}
          </tbody></table></div>)}
      </section>
      <section className="office-panel" aria-labelledby="members-heading">
        <h2 id="members-heading">{el ? "Μέλη" : "Members"}</h2>
        <div className="resource-table-scroll"><table className="resource-table"><thead><tr>
          <th>{el ? "Όνομα" : "Name"}</th><th>Email</th><th>{el ? "Ρόλος" : "Role"}</th><th>{el ? "Κατάσταση" : "Status"}</th><th /></tr></thead><tbody>
          {members.map((member) => {
            const own = member.user_id === user?.id;
            return (
              <tr key={member.id}>
                <td>{name(member)}{own ? ` (${el ? "εσείς" : "you"})` : ""}</td><td>{member.email}</td>
                <td>{own || member.role === "driver" ? <span title={roleText[member.role].meaning[lang]}>{roleText[member.role].name[lang]}{member.driver_id ? ` · ${el ? "συνδεδεμένος οδηγός" : "linked driver"}` : ""}</span> : (
                  <select aria-label={`${el ? "Ρόλος για" : "Role for"} ${name(member)}`} value={member.role} disabled={busy || !member.is_active} onChange={(e) => wantRole(member, e.target.value as Role)}>
                    {ROLES.map((r) => <option key={r} value={r}>{roleText[r].name[lang]}</option>)}</select>)}</td>
                <td><span className="driver-badge">{member.is_active ? `✓ ${el ? "Ενεργός" : "Active"}` : `– ${el ? "Απενεργοποιημένος" : "Deactivated"}`}</span></td>
                <td className="office-action-cell">{!own && (member.is_active
                  ? <button className="button secondary" disabled={busy} aria-label={`${el ? "Απενεργοποίηση" : "Deactivate"} ${name(member)}`} onClick={() => setConfirm({ kind: "deactivate", member })}>{el ? "Απενεργοποίηση" : "Deactivate"}</button>
                  : <button className="button secondary" disabled={busy} aria-label={`${el ? "Ενεργοποίηση" : "Reactivate"} ${name(member)}`} onClick={() => void change(member, { is_active: true }, el ? "Το μέλος ενεργοποιήθηκε ξανά." : "Member reactivated.")}>{el ? "Ενεργοποίηση" : "Reactivate"}</button>)}</td></tr>);
          })}
        </tbody></table></div>
      </section>
      {confirm && (
        <Modal title={el ? "Επιβεβαίωση" : "Please confirm"} onClose={() => !busy && setConfirm(null)} busy={busy}>
          <div className="resource-form-body">
            <p>{confirm.kind === "role"
              ? (confirm.role === "admin"
                ? (el ? `Το άτομο ${name(confirm.member)} θα μπορεί να διαχειρίζεται την πρόσβαση όλων. Οι συνεδρίες του κλείνουν τώρα.` : `${name(confirm.member)} will be able to manage everyone's access. Their sessions end now.`)
                : (el ? `Το άτομο ${name(confirm.member)} θα χάσει τα δικαιώματα διαχειριστή. Οι συνεδρίες του κλείνουν τώρα.` : `${name(confirm.member)} will lose administrator rights. Their sessions end now.`))
              : confirm.kind === "deactivate"
                ? (el ? `Το άτομο ${name(confirm.member)} δεν θα μπορεί να συνδεθεί. Οι συνεδρίες του κλείνουν τώρα και παραλείπεται από τις εγκρίσεις αδειών.` : `${name(confirm.member)} will not be able to sign in. Their sessions end now and they are skipped as a leave approver.`)
                : (el ? `Ο σύνδεσμος πρόσκλησης για ${confirm.invitation.email} θα πάψει να λειτουργεί.` : `The invitation link for ${confirm.invitation.email} will stop working.`)}</p>
          </div>
          <footer className="resource-dialog-actions">
            <button type="button" className="button secondary" disabled={busy} onClick={() => setConfirm(null)}>{el ? "Ακύρωση" : "Cancel"}</button>
            <button type="button" className="button primary" disabled={busy} onClick={() => {
              if (confirm.kind === "role") void change(confirm.member, { role: confirm.role }, el ? "Ο ρόλος άλλαξε." : "Role changed.");
              else if (confirm.kind === "deactivate") void change(confirm.member, { is_active: false }, el ? "Το μέλος απενεργοποιήθηκε." : "Member deactivated.");
              else void act(`v:${confirm.invitation.id}`, `/invitations/${confirm.invitation.id}/revoke`, (id) => ({ method: "POST", body: JSON.stringify({ request_id: id }) }), el ? "Η πρόσκληση ανακλήθηκε." : "Invitation revoked.");
            }}>{el ? "Επιβεβαίωση" : "Confirm"}</button>
          </footer>
        </Modal>)}
    </section>
  );
}
