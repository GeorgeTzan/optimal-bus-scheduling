"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { WorkRulesError, asClock, getWorkRules, saveWorkRules, type RuleLimit, type WorkRulesView } from "./workrules-api";

const labels: Record<string, [string, string]> = {
  daily_work_normal: ["Ημερήσια εργασία (κανονική)", "Normal daily work"],
  daily_work_max: ["Μέγιστη ημερήσια εργασία", "Maximum daily work"],
  daily_work_emergency: ["Μέγιστη ημερήσια εργασία σε έκτακτη ανάγκη", "Maximum daily work in an emergency"],
  overtime_year: ["Υπερωρίες ανά έτος", "Overtime per year"],
  overtime_year_absolute: ["Απόλυτο όριο υπερωριών ανά έτος", "Absolute yearly overtime cap"],
  weekly_work_normal: ["Εβδομαδιαία εργασία (κανονική)", "Normal weekly work"],
  weekly_work_max: ["Μέγιστη εβδομαδιαία εργασία", "Maximum weekly work"],
  continuous_driving: ["Συνεχής οδήγηση πριν το διάλειμμα", "Continuous driving before a break"],
  break_full: ["Διάλειμμα (ενιαίο)", "Break (single)"],
  break_split_first: ["Διάλειμμα σε δύο μέρη, πρώτο", "Split break, first part"],
  break_split_second: ["Διάλειμμα σε δύο μέρη, δεύτερο", "Split break, second part"],
  urban_break: ["Διάλειμμα αστικών γραμμών", "Urban break"],
  daily_driving_eu: ["Ημερήσια οδήγηση (ΕΕ)", "Daily driving (EU)"],
  daily_driving_eu_extended: ["Ημερήσια οδήγηση, επέκταση (ΕΕ)", "Extended daily driving (EU)"],
  daily_driving_extensions_per_week: ["Επεκτάσεις ημερήσιας οδήγησης ανά εβδομάδα", "Daily driving extensions per week"],
  weekly_driving_eu: ["Εβδομαδιαία οδήγηση (ΕΕ)", "Weekly driving (EU)"],
  fortnight_driving_eu: ["Οδήγηση ανά δεκαπενθήμερο (ΕΕ)", "Fortnight driving (EU)"],
  daily_rest: ["Ημερήσια ανάπαυση", "Daily rest"],
  daily_rest_reduced: ["Μειωμένη ημερήσια ανάπαυση", "Reduced daily rest"],
  reduced_rests_per_week: ["Μειωμένες αναπαύσεις ανά εβδομάδα", "Reduced rests per week"],
  weekly_rest: ["Εβδομαδιαία ανάπαυση", "Weekly rest"],
  workdays_before_weekly_rest: ["Εργάσιμες ημέρες πριν την εβδομαδιαία ανάπαυση", "Working days before weekly rest"],
  sunday_rest_every_weeks: ["Κυριακάτικη ανάπαυση κάθε Χ εβδομάδες", "Sunday rest every N weeks"],
  interruptions_per_week: ["Διακοπές ανά εβδομάδα", "Interruptions per week"],
  interruption_minutes_per_week: ["Λεπτά διακοπών ανά εβδομάδα", "Interruption time per week"],
  interruption_threshold: ["Όριο διακοπής", "Interruption threshold"],
  break_piece_threshold: ["Όριο τμήματος διαλείμματος", "Break piece threshold"],
  vehicle_check: ["Έλεγχος οχήματος", "Vehicle check"],
  dead_run_out: ["Άδεια διαδρομή εξόδου", "Dead run out"],
  dead_run_back: ["Άδεια διαδρομή επιστροφής", "Dead run back"],
  eu_route_km: ["Όριο διαδρομής ΕΕ (χλμ)", "EU route limit (km)"],
};
const warningLabels: Record<string, [string, string]> = {
  overnight_rest_day: ["Ρεπό μετά από διανυκτέρευση", "Rest day after an overnight"],
  no_consecutive_overnight: ["Όχι δύο διανυκτερεύσεις στη σειρά", "No two overnights in a row"],
  shift_rotation: ["Εναλλαγή βαρδιών", "Shift rotation"],
};
export const citation = (source: string, el: boolean) =>
  el ? source.replace(/\bPD\b/g, "ΠΔ").replace(/\bEU\b/g, "ΕΕ").replace(/\bArt\./g, "άρ.") : source;
const errorText = (error: WorkRulesError, el: boolean) =>
  error.code === "stale_version"
    ? el ? "Οι κανόνες άλλαξαν από άλλον χρήστη. Φορτώθηκαν ξανά οι τρέχουσες τιμές." : "The rules were changed by someone else. The current values have been reloaded."
    : error.code === "looser_than_law"
      ? el ? "Το όριο δεν μπορεί να είναι χαλαρότερο από τον νόμο." : "A company limit cannot be looser than the law."
      : error.code === "offline"
        ? el ? "Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα." : "No connection. Nothing was saved."
        : el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed.";
const counts = new Set(["daily_driving_extensions_per_week", "reduced_rests_per_week", "workdays_before_weekly_rest", "sunday_rest_every_weeks", "interruptions_per_week", "eu_route_km"]);

const show = (id: string, value: number) => (counts.has(id) ? String(value) : asClock(value));
function parse(id: string, text: string): number | null {
  const value = text.trim();
  if (counts.has(id)) return /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : null;
  const match = /^(\d+)(?::([0-5]\d))?$/.exec(value);
  const minutes = match ? Number(match[1]) * 60 + Number(match[2] ?? 0) : null;
  return minutes && minutes > 0 ? minutes : null;
}
function state(limit: RuleLimit, text: string): "legal" | "stricter" | "looser" | "invalid" {
  const value = parse(limit.rule_id, text);
  if (value === null) return "invalid";
  if (value === limit.legal) return "legal";
  if (limit.direction === "fixed") return "invalid";
  return (limit.direction === "max" ? value < limit.legal : value > limit.legal) ? "stricter" : "looser";
}
const pillText: Record<string, [string, string]> = {
  legal: ["νόμιμο", "legal"],
  stricter: ["αυστηρότερο", "stricter"],
  looser: ["χαλαρότερο από νόμο — δεν αποθηκεύεται", "looser than law — cannot be saved"],
  invalid: ["μη έγκυρη τιμή", "invalid value"],
};
const pillClass: Record<string, string> = { legal: "neutral", stricter: "good", looser: "bad", invalid: "bad" };

export function WorkRulesWorkspace() {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el",
    lang = el ? 0 : 1,
    canEdit = !!user?.permissions.includes("organization.manage");
  const [view, setView] = useState<WorkRulesView | null>(null),
    [texts, setTexts] = useState<Record<string, string>>({}),
    [active, setActive] = useState<string[]>([]),
    [failure, setFailure] = useState<WorkRulesError | null>(null),
    [fieldRule, setFieldRule] = useState<string | null>(null),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const adopt = useCallback((next: WorkRulesView) => {
    setView(next);
    setTexts(Object.fromEntries(next.limits.map((l) => [l.rule_id, show(l.rule_id, l.value)])));
    setActive([...next.warning_rules].sort());
    setFieldRule(null);
  }, []);
  const load = useCallback(async () => {
    try {
      adopt(await getWorkRules(apiFetch));
    } catch (error) {
      if (error instanceof WorkRulesError) setFailure(error);
    }
  }, [apiFetch, adopt]);
  useEffect(() => {
    void load();
  }, [load]);
  const dirty = !!view && (view.limits.some((l) => texts[l.rule_id] !== show(l.rule_id, l.value)) || active.join() !== [...view.warning_rules].sort().join());
  useUnsavedChanges(dirty || busy);
  if (!view) return <p role="status" className="resource-workspace">{failure ? errorText(failure, el) : el ? "Φόρτωση…" : "Loading…"}</p>;
  const states = Object.fromEntries(view.limits.map((l) => [l.rule_id, state(l, texts[l.rule_id] ?? "")]));
  const blocked = Object.values(states).some((s) => s === "looser" || s === "invalid");
  async function save() {
    if (!view || busy || blocked) return;
    setBusy(true);
    setFailure(null);
    setFieldRule(null);
    setNotice("");
    const overrides: Record<string, number> = {};
    for (const l of view.limits) {
      const value = parse(l.rule_id, texts[l.rule_id] ?? "");
      if (value !== null && value !== l.legal) overrides[l.rule_id] = value;
    }
    try {
      adopt(await saveWorkRules(apiFetch, { expected_version: view.company_version, overrides, warning_rules: active }));
      setNotice(el ? "Αποθηκεύτηκε." : "Saved.");
    } catch (error) {
      if (error instanceof WorkRulesError) {
        if (error.code === "stale_version") await load();
        setFailure(error);
        if (error.code === "looser_than_law") setFieldRule(error.ruleId);
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="resource-workspace office-workspace" aria-labelledby="rules-heading">
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">{el ? "ΡΥΘΜΙΣΕΙΣ · ΚΑΝΟΝΕΣ ΕΡΓΑΣΙΑΣ" : "SETTINGS · WORK RULES"}</span>
          <h1 id="rules-heading">{el ? "Όρια εργασίας οδηγών" : "Driver work limits"}</h1>
          <p>
            {el ? "Τα νόμιμα όρια είναι σταθερά. Μπορείτε μόνο να τα κάνετε αυστηρότερα." : "Legal limits are fixed. You can only make them stricter."}{" "}
            <span className="status-pill warning">{el ? "Προς επιβεβαίωση από νομικό" : "To be confirmed by a lawyer"}</span>
          </p>
        </div>
      </header>
      {failure && !(failure.code === "looser_than_law" && fieldRule) && <p className="auth-error" role="alert">{errorText(failure, el)}</p>}
      {notice && <p className="office-summary" role="status">{notice}</p>}
      <section className="office-panel" aria-labelledby="limits-heading">
        <h2 id="limits-heading">{el ? "Νόμιμα όρια (προς επιβεβαίωση)" : "Legal limits (to be confirmed)"}</h2>
        <div className="resource-table-scroll">
          <table className="resource-table">
            <thead>
              <tr>
                <th>{el ? "Κανόνας" : "Rule"}</th>
                <th>{el ? "Νόμιμο όριο" : "Legal limit"}</th>
                <th>{el ? "Πηγή" : "Source"}</th>
                <th>{el ? "Όριο εταιρείας" : "Company limit"}</th>
                <th>{el ? "Κατάσταση" : "Status"}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {view.limits.map((l) => {
                const name = labels[l.rule_id]?.[lang] ?? l.rule_id,
                  current = states[l.rule_id]!,
                  editable = canEdit && l.direction !== "fixed";
                return (
                  <tr key={l.rule_id}>
                    <td>{name}</td>
                    <td>{show(l.rule_id, l.legal)}</td>
                    <td>{citation(l.source, el)}</td>
                    <td>
                      {editable ? (
                        <input
                          aria-label={name}
                          aria-invalid={current === "looser" || current === "invalid"}
                          className={current === "looser" || current === "invalid" ? "rule-invalid" : undefined}
                          placeholder={counts.has(l.rule_id) ? undefined : "H:MM"}
                          size={6}
                          inputMode={counts.has(l.rule_id) ? "numeric" : "text"}
                          value={texts[l.rule_id] ?? ""}
                          disabled={busy}
                          onChange={(e) => setTexts({ ...texts, [l.rule_id]: e.target.value })}
                        />
                      ) : (
                        show(l.rule_id, l.value)
                      )}
                    </td>
                    <td>
                      <span className={`status-pill ${pillClass[current]}`}>{pillText[current]![lang]}</span>
                      {fieldRule === l.rule_id && failure && <small role="alert"> {errorText(failure, el)}</small>}
                    </td>
                    <td className="office-action-cell">
                      {editable && texts[l.rule_id] !== show(l.rule_id, l.legal) && (
                        <button
                          className="button secondary"
                          disabled={busy}
                          aria-label={el ? `Επαναφορά στο νόμιμο: ${name}` : `Reset ${name} to legal`}
                          onClick={() => setTexts({ ...texts, [l.rule_id]: show(l.rule_id, l.legal) })}
                        >
                          {el ? "Νόμιμο" : "Reset"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="office-panel" aria-labelledby="company-rules-heading">
        <h2 id="company-rules-heading">{el ? "Κανόνες εταιρείας (όχι νόμος)" : "Company rules (not law)"}</h2>
        <p className="driver-muted">{el ? "Προειδοποίηση, όχι μπλοκάρισμα." : "A warning, not a block."}</p>
        {view.warning_catalogue.map((id) => (
          <label key={id} style={{ display: "block", margin: "6px 0" }}>
            <input
              type="checkbox"
              disabled={!canEdit || busy}
              checked={active.includes(id)}
              onChange={(e) => setActive(e.target.checked ? [...active, id].sort() : active.filter((x) => x !== id))}
            />{" "}
            {warningLabels[id]?.[lang] ?? id}
          </label>
        ))}
      </section>
      {canEdit && (
        <p>
          <button className="button primary" disabled={busy || blocked || !dirty} onClick={() => void save()}>
            {el ? "Αποθήκευση" : "Save"}
          </button>{" "}
          <span className="driver-muted">{el ? "Κάθε αλλαγή καταγράφεται στο ιστορικό." : "Every change is recorded in the history."}</span>
        </p>
      )}
    </section>
  );
}
