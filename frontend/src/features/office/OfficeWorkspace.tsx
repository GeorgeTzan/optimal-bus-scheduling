"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { AccessPanel } from "./AccessPanel";
import type { Capabilities } from "./contracts";
import { ImpactReview } from "./ImpactReview";
import { LeavePanel } from "./LeavePanel";
import { MaintenancePanel } from "./MaintenancePanel";
import { monthRange, officeCall } from "./office-api";
import { WorkingTimePanel } from "./WorkingTimePanel";

type Tab = "leave" | "working" | "fleet" | "impacts" | "access";
const currentMonth = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`; };
export function OfficeWorkspace({ onOpenStudio }: { onOpenStudio: (date: string) => void }) {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el";
  const [caps, setCaps] = useState<Capabilities | null>(null),
    [failed, setFailed] = useState(""),
    [month, setMonth] = useState(currentMonth),
    [tab, setTab] = useState<Tab>("leave"),
    [capsVersion, setCapsVersion] = useState(0),
    [notice, setNotice] = useState<number | null>(null),
    showImpacts = useCallback((count?: number) => setNotice(count ?? null), []);
  useEffect(() => {
    const controller = new AbortController();
    void officeCall<Capabilities>((p, o) => apiFetch(p, { ...o, signal: controller.signal }), "/capabilities", undefined, el)
      .then((data) => { if (!controller.signal.aborted) setCaps(data); })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setFailed(failure instanceof Error ? failure.message : ""); });
    return () => controller.abort();
  }, [apiFetch, el, capsVersion]);
  if (failed) return <section className="resource-empty"><h1>{el ? "Γραφείο" : "Office"}</h1><p role="alert">{failed}</p></section>;
  if (!caps) return <section className="resource-empty"><p role="status">{el ? "Φόρτωση…" : "Loading…"}</p></section>;
  const has = (capability: string) => caps.capabilities.includes(capability),
    tabs: [Tab, string, boolean][] = [
      ["leave", el ? "Άδειες" : "Leave", true],
      ["working", el ? "Ωράριο οδηγών" : "Driver working time", has("availability.manage")],
      ["fleet", el ? "Συντήρηση οχημάτων" : "Vehicle maintenance", has("maintenance.manage")],
      ["impacts", el ? "Επηρεασμένα δρομολόγια" : "Affected trips", !!user?.permissions.includes("schedule.read")],
      ["access", el ? "Πρόσβαση" : "Access", !!user?.permissions.includes("members.manage")],
    ],
    visible = tabs.filter(([, , shown]) => shown),
    active = visible.some(([id]) => id === tab) ? tab : "leave",
    { from, to } = monthRange(month);
  return (
    <section className="resource-workspace office-workspace">
      <div className="resource-heading">
        <div><span className="resource-eyebrow">{el ? "Γραφείο κίνησης" : "Operations office"}</span><h1>{el ? "Γραφείο" : "Office"}</h1>
          <p>{el ? "Ωράριο, άδειες και κατάσταση οχημάτων. Οι ώρες εμφανίζονται στη ζώνη ώρας του οργανισμού σας" : "Working time, leave and vehicle status. Times are shown in your organization's time zone"} ({caps.timezone}).</p></div>
        <label className="office-month">{el ? "Μήνας" : "Month"}
          <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} /></label>
      </div>
      {caps.capabilities.length === 0 && !user?.permissions.includes("members.manage") && (
        <p className="office-summary">{el ? "Ο οργανισμός σας δεν σας έχει δώσει ενέργειες γραφείου. Μπορείτε να δείτε μόνο ό,τι αφορά τις άδειες που εγκρίνετε." : "Your organization has not granted you office actions. You can only see leave you are set to approve."}</p>)}
      <nav className="office-tabs" aria-label={el ? "Ενότητες γραφείου" : "Office sections"}>
        {visible.map(([id, text]) => <button key={id} className={`button ${active === id ? "primary" : "secondary"}`} aria-current={active === id ? "page" : undefined} onClick={() => { setTab(id); setNotice(null); }}>{text}</button>)}
      </nav>
      {notice !== null && (
        <p className="office-summary" role="status">
          {notice === 0 ? (el ? "Αποθηκεύτηκε. Κανένα δρομολόγιο δεν επηρεάζεται τις επόμενες 31 ημέρες." : "Saved. No trips are affected in the next 31 days.")
            : el ? `Αποθηκεύτηκε. Αυτή τη στιγμή ${notice} ${notice === 1 ? "δρομολόγιο χρειάζεται" : "δρομολόγια χρειάζονται"} έλεγχο. Δεν άλλαξε κανένα δρομολόγιο και δεν στάλθηκε ειδοποίηση.` : `Saved. Currently ${notice} ${notice === 1 ? "trip needs" : "trips need"} review. No trip was changed and no notification was sent.`}{" "}
          {notice > 0 && <button className="button secondary" onClick={() => { setTab("impacts"); setNotice(null); }}>{el ? "Δείτε τα δρομολόγια" : "Review the trips"}</button>}
        </p>)}
      {active === "leave" && <LeavePanel zone={caps.timezone} from={from} to={to} canRecord={has("availability.manage")} onImpacts={showImpacts} />}
      {active === "working" && <WorkingTimePanel zone={caps.timezone} from={from} to={to} onImpacts={showImpacts} />}
      {active === "fleet" && <MaintenancePanel zone={caps.timezone} from={from} to={to} canRelease={has("maintenance.release")} onImpacts={showImpacts} />}
      {active === "impacts" && <ImpactReview zone={caps.timezone} from={from} to={to} onOpenStudio={onOpenStudio} />}
      {active === "access" && <AccessPanel onGrantChange={() => setCapsVersion((n) => n + 1)} />}
    </section>
  );
}
