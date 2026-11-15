"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { RouteList } from "./RouteList";
import {
  DEFAULT_TIMEZONE, WorkRulesError, asClock, localDateTime, parseHours, put, recordCall, todayLocal, toUtc,
  type DriverBaseline, type DriverProfile, type DriverWeek, type RouteOption,
} from "./workrules-api";

const messages: Record<string, [string, string]> = {
  stale_version: ["Η εγγραφή άλλαξε από άλλον χρήστη. Φορτώθηκαν ξανά οι τρέχουσες τιμές.", "This was changed by someone else. The current values have been reloaded."],
  baseline_locked: ["Υπάρχει ήδη δημοσιευμένο πρόγραμμα για τον οδηγό αυτή την ημερομηνία ή μετά, οπότε η αφετηρία δεν αλλάζει.", "A schedule is already published on or after this date for this driver, so the baseline cannot be changed."],
  baseline_as_of_not_past: ["Η ημερομηνία αφετηρίας πρέπει να είναι πριν από σήμερα.", "The baseline date must be before today."],
  route_both_preferred_and_forbidden: ["Μια γραμμή δεν μπορεί να είναι και προτιμώμενη και απαγορευμένη.", "A route cannot be both preferred and forbidden."],
  unknown_route: ["Επιλέξτε γραμμές του οργανισμού σας.", "Choose routes from your organization."],
  offline: ["Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα.", "No connection. Nothing was saved."],
};
const errorText = (error: unknown, el: boolean) =>
  messages[error instanceof WorkRulesError ? error.code : ""]?.[el ? 0 : 1] ?? (el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed.");
const hours = (minutes: number) => asClock(minutes);

interface BaselineForm {
  asOf: string;
  overtime: string;
  lastDuty: string;
  lastRest: string;
  atBase: boolean;
  owed: string;
}
const formOf = (b: DriverBaseline, tz: string): BaselineForm => ({
  asOf: b.as_of ?? "",
  overtime: hours(b.overtime_minutes),
  lastDuty: localDateTime(b.last_duty_end, tz),
  lastRest: localDateTime(b.last_weekly_rest_end, tz),
  atBase: b.last_weekly_rest_at_base,
  owed: hours(b.owed_rest_minutes),
});

export function DriverWorkProfile({ driverId, homeBase, onDirty }: { driverId: number; homeBase: string; onDirty: (dirty: boolean) => void }) {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el",
    canEdit = !!user?.permissions.includes("drivers.write");
  const [routes, setRoutes] = useState<RouteOption[]>([]),
    [profile, setProfile] = useState<DriverProfile | null>(null),
    [flags, setFlags] = useState({ overnight: true, split: true, base: false }),
    [preferred, setPreferred] = useState<number[]>([]),
    [forbidden, setForbidden] = useState<number[]>([]),
    [baseline, setBaseline] = useState<DriverBaseline | null>(null),
    [form, setForm] = useState<BaselineForm | null>(null),
    [week, setWeek] = useState<DriverWeek | null>(null),
    [profileError, setProfileError] = useState(""),
    [baselineError, setBaselineError] = useState(""),
    [fieldError, setFieldError] = useState<Record<string, string>>({}),
    [notice, setNotice] = useState(""),
    [tz, setTz] = useState(DEFAULT_TIMEZONE),
    [busy, setBusy] = useState(false);
  const base = `/drivers/${driverId}`;
  const adoptProfile = useCallback((value: DriverProfile) => {
    setProfile(value);
    setFlags({ overnight: value.overnight_allowed, split: value.split_shift_allowed, base: value.must_return_to_base });
    setPreferred(value.preferred_route_ids);
    setForbidden(value.forbidden_route_ids);
  }, []);
  const adoptBaseline = useCallback((value: DriverBaseline, zone: string) => {
    setBaseline(value);
    setForm(formOf(value, zone));
  }, []);
  const loadWeek = useCallback(async (zone: string) => {
    try {
      setWeek(await recordCall<DriverWeek>(apiFetch, `${base}/week?date=${todayLocal(zone)}`));
    } catch {
      setWeek(null);
    }
  }, [apiFetch, base]);
  const load = useCallback(async () => {
    let zone = DEFAULT_TIMEZONE;
    try {
      const office = await apiFetch("/api/v1/office/capabilities");
      if (office.ok) zone = ((await office.json()) as { timezone?: string }).timezone || DEFAULT_TIMEZONE;
    } catch {
      zone = DEFAULT_TIMEZONE;
    }
    setTz(zone);
    try {
      const [list, p, b] = await Promise.all([
        recordCall<{ routes: RouteOption[] }>(apiFetch, "/routes"),
        recordCall<DriverProfile>(apiFetch, `${base}/profile`),
        recordCall<DriverBaseline>(apiFetch, `${base}/baseline`),
      ]);
      setRoutes(list.routes);
      adoptProfile(p);
      adoptBaseline(b, zone);
    } catch (failure) {
      setProfileError(errorText(failure, el));
    }
    await loadWeek(zone);
  }, [apiFetch, base, adoptProfile, adoptBaseline, loadWeek, el]);
  const reloadBaseline = useCallback(async () => {
    try {
      adoptBaseline(await recordCall<DriverBaseline>(apiFetch, `${base}/baseline`), tz);
    } catch {
      return;
    }
  }, [apiFetch, base, adoptBaseline, tz]);
  useEffect(() => {
    void load();
  }, [load]);
  const profileDirty =
    !!profile &&
    (flags.overnight !== profile.overnight_allowed || flags.split !== profile.split_shift_allowed || flags.base !== profile.must_return_to_base ||
      preferred.join() !== profile.preferred_route_ids.join() || forbidden.join() !== profile.forbidden_route_ids.join());
  const baselineDirty = !!baseline && !!form && JSON.stringify(form) !== JSON.stringify(formOf(baseline, tz));
  const dirty = profileDirty || baselineDirty;
  useUnsavedChanges(dirty || busy);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  async function saveProfile() {
    if (!profile || busy) return;
    setBusy(true);
    setProfileError("");
    setNotice("");
    try {
      adoptProfile(
        await put<DriverProfile>(apiFetch, `${base}/profile`, {
          expected_version: profile.version,
          overnight_allowed: flags.overnight,
          split_shift_allowed: flags.split,
          must_return_to_base: flags.base,
          preferred_route_ids: preferred,
          forbidden_route_ids: forbidden,
        }),
      );
      setNotice(el ? "Αποθηκεύτηκε." : "Saved.");
    } catch (failure) {
      setProfileError(errorText(failure, el));
      if (failure instanceof WorkRulesError && failure.code === "stale_version") await load();
    } finally {
      setBusy(false);
    }
  }
  async function saveBaseline() {
    if (!baseline || !form || busy) return;
    const problems: Record<string, string> = {};
    const overtime = form.overtime.trim() ? parseHours(form.overtime) : 0;
    const owed = form.owed.trim() ? parseHours(form.owed) : 0;
    const invalidHours = el ? "Δώστε ώρες, π.χ. 12 ή 12:30." : "Enter hours, for example 12 or 12:30.";
    if (!form.asOf) problems.asOf = el ? "Επιλέξτε ημερομηνία." : "Choose a date.";
    if (overtime === null) problems.overtime = invalidHours;
    if (owed === null) problems.owed = invalidHours;
    setFieldError(problems);
    if (Object.keys(problems).length) return;
    setBusy(true);
    setBaselineError("");
    setNotice("");
    try {
      adoptBaseline(
        await put<DriverBaseline>(apiFetch, `${base}/baseline`, {
          expected_version: baseline.version,
          as_of: form.asOf,
          overtime_minutes: overtime,
          last_duty_end: toUtc(form.lastDuty, tz),
          last_weekly_rest_end: toUtc(form.lastRest, tz),
          last_weekly_rest_at_base: form.atBase,
          owed_rest_minutes: owed,
        }),
        tz,
      );
      setNotice(el ? "Αποθηκεύτηκε." : "Saved.");
      await loadWeek(tz);
    } catch (failure) {
      setBaselineError(errorText(failure, el));
      if (failure instanceof WorkRulesError && failure.code === "stale_version") await reloadBaseline();
    } finally {
      setBusy(false);
    }
  }
  const setField = (patch: Partial<BaselineForm>) => form && setForm({ ...form, ...patch });
  const locked = !canEdit || busy || !profile;
  const text = (key: keyof BaselineForm, label: string, type = "text", placeholder?: string) => (
    <div className="resource-field">
      <label htmlFor={`baseline-${key}`}>{label}</label>
      <input
        id={`baseline-${key}`}
        type={type}
        placeholder={placeholder}
        value={form ? String(form[key]) : ""}
        disabled={!canEdit || busy || !form}
        aria-invalid={!!fieldError[key]}
        onChange={(e) => setField({ [key]: e.target.value })}
      />
      {fieldError[key] && <small className="field-error" role="alert">{fieldError[key]}</small>}
    </div>
  );
  const when = (iso: string | null) => (iso ? localDateTime(iso, tz).replace("T", " ") : "–");
  return (
    <div className="driver-work-profile">
      {notice && <p className="office-summary" role="status">{notice}</p>}
      <section className="office-panel" aria-labelledby={`overnight-${driverId}`}>
        <h3 id={`overnight-${driverId}`}>{el ? "Έδρα & διανυκτέρευση" : "Home base & overnight"}</h3>
        {profileError && <p className="auth-error" role="alert">{profileError}</p>}
        <p>
          <strong>{el ? "Έδρα" : "Home base"}:</strong> {homeBase || (el ? "Δεν έχει οριστεί" : "Not set")}
        </p>
        <label className="resource-checkbox">
          <input type="checkbox" checked={flags.overnight} disabled={locked} onChange={(e) => setFlags({ ...flags, overnight: e.target.checked })} />
          {el ? "Επιτρέπεται διανυκτέρευση" : "Overnight allowed"}
        </label>
        <label className="resource-checkbox">
          <input type="checkbox" checked={flags.split} disabled={locked} onChange={(e) => setFlags({ ...flags, split: e.target.checked })} />
          {el ? "Επιτρέπεται διακεκομμένο ωράριο" : "Split shift allowed"}
        </label>
        <label className="resource-checkbox">
          <input type="checkbox" checked={flags.base} disabled={locked} onChange={(e) => setFlags({ ...flags, base: e.target.checked })} />
          {el ? "Πρέπει να επιστρέφει στην έδρα" : "Must return to base"}
        </label>
        <RouteList
          title={el ? "Προτιμά" : "Prefers"}
          addLabel={el ? "Προσθήκη προτιμώμενης γραμμής" : "Add a preferred route"}
          selected={preferred}
          routes={routes}
          blocked={forbidden}
          disabled={locked}
          el={el}
          onChange={setPreferred}
        />
        <RouteList
          title={el ? "Δεν επιτρέπεται" : "Not allowed"}
          addLabel={el ? "Προσθήκη απαγορευμένης γραμμής" : "Add a forbidden route"}
          selected={forbidden}
          routes={routes}
          blocked={preferred}
          disabled={locked}
          el={el}
          onChange={setForbidden}
        />
        {canEdit && (
          <button type="button" className="button primary" disabled={!profileDirty || busy} onClick={() => void saveProfile()}>
            {el ? "Αποθήκευση προτιμήσεων" : "Save preferences"}
          </button>
        )}
      </section>
      <section className="office-panel" aria-labelledby={`baseline-${driverId}`}>
        <h3 id={`baseline-${driverId}`}>{el ? "Αφετηρία πριν το σύστημα" : "Starting position"}</h3>
        <p>{el ? "Τι είχε συσσωρεύσει ο οδηγός πριν ξεκινήσει να χρησιμοποιείται το σύστημα." : "What the driver had already accumulated before this system was used."}</p>
        {baselineError && <p className="auth-error" role="alert">{baselineError}</p>}
        {text("asOf", el ? "Αφετηρία έως" : "Baseline as of", "date")}
        {text("overtime", el ? "Υπερωρίες έτους μέχρι τώρα (ώρες)" : "Overtime so far this year (hours)", "text", "H:MM")}
        {text("lastDuty", el ? "Τέλος τελευταίας υπηρεσίας" : "Last duty ended", "datetime-local")}
        {text("lastRest", el ? "Τέλος τελευταίας εβδομαδιαίας ανάπαυσης" : "Last weekly rest ended", "datetime-local")}
        <label className="resource-checkbox">
          <input type="checkbox" checked={form?.atBase ?? false} disabled={!canEdit || busy || !form} onChange={(e) => setField({ atBase: e.target.checked })} />
          {el ? "Η εβδομαδιαία ανάπαυση έγινε στην έδρα" : "Weekly rest was taken at the home base"}
        </label>
        {text("owed", el ? "Οφειλόμενη αντισταθμιστική ανάπαυση (ώρες)" : "Owed compensatory rest (hours)", "text", "H:MM")}
        {canEdit && (
          <button type="button" className="button primary" disabled={!baselineDirty || busy} onClick={() => void saveBaseline()}>
            {el ? "Αποθήκευση αφετηρίας" : "Save baseline"}
          </button>
        )}
      </section>
      <section className="office-panel" aria-labelledby={`week-${driverId}`}>
        <h3 id={`week-${driverId}`}>{el ? "Αυτή την εβδομάδα" : "This week"}</h3>
        {week ? (
          <dl>
            <dt>{el ? "Εργασία" : "Work"}</dt>
            <dd data-testid="week-work">{hours(week.work_minutes)} / {hours(week.weekly_max)}</dd>
            <dt>{el ? "Υπερωρία έτους" : "Overtime this year"}</dt>
            <dd data-testid="week-overtime">{hours(week.overtime_year_minutes)} / {hours(week.overtime_year_max)}</dd>
            <dt>{el ? "Τελευταία λήξη" : "Last duty end"}</dt>
            <dd>{when(week.last_duty_end)}</dd>
            <dt>{el ? "Εβδομαδιαία ανάπαυση" : "Weekly rest"}</dt>
            <dd>{when(week.last_weekly_rest)}</dd>
          </dl>
        ) : (
          <p>{el ? "Δεν υπάρχουν διαθέσιμα στοιχεία." : "No figures available."}</p>
        )}
      </section>
    </div>
  );
}
