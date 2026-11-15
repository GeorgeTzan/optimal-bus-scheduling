"use client";
import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { Field, Modal } from "../timetables/shared";
import type { PersistedRevision, Violation } from "./revision-api";
import { FindingsList, type FindingLabels } from "./WorkRulesTab";

const failures: Record<string, [string, string]> = {
  legal_finding: ["Μόνο οι προειδοποιήσεις κανόνων εταιρείας μπορούν να παρακαμφθούν.", "Only company-rule warnings can be overridden."],
  finding_not_found: ["Το εύρημα δεν υπάρχει πια στον τρέχοντα έλεγχο.", "This finding is no longer in the current check."],
  forbidden: ["Δεν έχετε δικαίωμα έγκρισης για παράκαμψη.", "You do not have permission to override."],
  conflict: ["Το πρόγραμμα έχει δημοσιευτεί και δεν αλλάζει.", "The schedule is published and cannot change."],
  offline: ["Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα.", "No connection. Nothing was saved."],
  failed: ["Η παράκαμψη δεν αποθηκεύτηκε.", "The override was not saved."],
};

export function OverrideDialog({
  revisionId,
  finding,
  timezone,
  labels,
  onClose,
  onDone,
}: {
  revisionId: string;
  finding: Violation;
  timezone: string;
  labels: FindingLabels;
  onClose: () => void;
  onDone: (revision: PersistedRevision) => void;
}) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [code, setCode] = useState("");
  const text = reason.trim();
  const valid = text.length >= 1 && text.length <= 1000;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setCode("");
    let saved: PersistedRevision | null = null;
    try {
      const response = await apiFetch(`/api/v1/scheduling/revisions/${revisionId}/work-rule-overrides`, {
        method: "POST",
        body: JSON.stringify({ finding_key: finding.finding_key, reason: text }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
        const known = body?.detail?.code;
        setCode(
          known && known in failures ? known : response.status === 403 ? "forbidden" : response.status === 409 ? "conflict" : "failed",
        );
        return;
      }
      const fresh = await apiFetch(`/api/v1/scheduling/revisions/${revisionId}`);
      if (!fresh.ok) {
        setCode("failed");
        return;
      }
      saved = (await fresh.json()) as PersistedRevision;
    } catch {
      setCode("offline");
    } finally {
      setBusy(false);
    }
    if (saved) onDone(saved);
  }
  return (
    <Modal title={el ? "Παράκαμψη κανόνα εταιρείας" : "Override company rule"} onClose={() => !busy && onClose()} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="resource-form-body">
          <FindingsList violations={[finding]} el={el} timezone={timezone} labels={labels} />
          <Field label={el ? "Αιτιολογία" : "Reason"}>
            <textarea
              required
              rows={3}
              maxLength={1000}
              value={reason}
              disabled={busy}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
          {code && (
            <p className="import-alert" role="alert">
              {failures[code]![el ? 0 : 1]}
            </p>
          )}
        </div>
        <footer className="resource-dialog-actions">
          <button type="button" className="button secondary" disabled={busy} onClick={onClose}>
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button className="button primary" disabled={!valid || busy}>
            {el ? "Παράκαμψη" : "Override"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
