"use client";

import React, { useState } from "react";
import { useI18n } from "../../i18n/context";

interface Disruption {
  id: string;
  type: string;
  route: string;
  details: string;
  impact: "High" | "Medium" | "Low";
  status: "In progress" | "Reassigning" | "Monitoring" | "Ongoing";
  eta?: string;
  timestamp: string;
}

interface RecoveryAction {
  id: string;
  title: string;
  description: string;
  priority: "High" | "Medium" | "Low";
  approved?: boolean;
  rejected?: boolean;
}

export function OperationsControlCenter() {
  const { locale } = useI18n();

  const [selectedRegion, setSelectedRegion] = useState("all");
  const [recoveryActions, setRecoveryActions] = useState<RecoveryAction[]>([
    {
      id: "rec-1",
      title:
        locale === "el"
          ? "Αποστολή εφεδρικού λεωφορείου"
          : "Deploy replacement bus",
      description:
        locale === "el"
          ? "Αποστολή KTEL-520 από Θεσσαλονίκη προς Ιωάννινα (Εκτιμώμενη άφιξη 1h 10m) για παραλαβή 28 επιβατών."
          : "Send KTEL-520 from Thessaloniki to Ioannina (ETA 1h 10m) to pick up 28 passengers.",
      priority: "High",
    },
    {
      id: "rec-2",
      title:
        locale === "el" ? "Ανάθεση εφεδρικού οδηγού" : "Assign backup driver",
      description:
        locale === "el"
          ? "Ανάθεση διαθέσιμου οδηγού (ID: D-7842) στο όχημα KTEL-310 (Θεσσαλονίκη → Βόλος)."
          : "Assign available driver (ID: D-7842) to KTEL-310 (Thessaloniki → Volos).",
      priority: "Medium",
    },
    {
      id: "rec-3",
      title:
        locale === "el"
          ? "Προαιρετική αναδρομολόγηση μέσω Τρικάλων"
          : "Reroute via Trikala (optional)",
      description:
        locale === "el"
          ? "Πρόταση εναλλακτικής διαδρομής για τις επόμενες 3 αναχωρήσεις λόγω έντονης βροχόπτωσης."
          : "Consider rerouting for next 3 departures due to severe weather conditions.",
      priority: "Low",
    },
  ]);

  const disruptions: Disruption[] = [
    {
      id: "d1",
      type: locale === "el" ? "Μηχανική βλάβη λεωφορείου" : "Bus breakdown",
      route: "Ioannina → Athens",
      details: "KTEL-402 (Κοντά στο Μέτσοβο) — 28 επιβάτες εντός",
      impact: "High",
      status: "In progress",
      timestamp: "4 min ago",
    },
    {
      id: "d2",
      type: locale === "el" ? "Απουσία οδηγού" : "Driver absence",
      route: "Thessaloniki → Volos",
      details: "KTEL-310 — Προγραμματισμένος οδηγός δεν προσήλθε",
      impact: "Medium",
      status: "Reassigning",
      eta: "25 min",
      timestamp: "12 min ago",
    },
    {
      id: "d3",
      type: locale === "el" ? "Έντονα καιρικά φαινόμενα" : "Severe weather",
      route: "Central Greece",
      details: "Λαμία - Καρπενήσι — Πιθανές καθυστερήσεις 15-40 min",
      impact: "Medium",
      status: "Monitoring",
      eta: "1-2 hrs",
      timestamp: "28 min ago",
    },
    {
      id: "d4",
      type: locale === "el" ? "Συμφόρηση σταθμού" : "Station congestion",
      route: "Athens Kifissos",
      details: "Υψηλός όγκος επιβατών κατά την αναχώρηση",
      impact: "Low",
      status: "Ongoing",
      timestamp: "41 min ago",
    },
  ];

  const handleAction = (id: string, decision: "approve" | "reject") => {
    setRecoveryActions((prev) =>
      prev.map((a) =>
        a.id === id
          ? {
              ...a,
              approved: decision === "approve",
              rejected: decision === "reject",
            }
          : a,
      ),
    );
  };

  return (
    <div className="space-y-6 font-sans">
      {/* Top Operations Header */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-900 p-6 text-white shadow-xl lg:flex-row lg:items-center">
        <div>
          <div className="mb-1 flex items-center space-x-3">
            <span className="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/20 px-2.5 py-0.5 text-xs font-semibold text-emerald-400">
              <span className="mr-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              {locale === "el" ? "Ζωντανή Λειτουργία" : "Live Operations"}
            </span>
            <span className="text-xs text-slate-400">
              {new Date().toLocaleDateString(
                locale === "el" ? "el-GR" : "en-US",
                {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                },
              )}
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            {locale === "el"
              ? "Κέντρο Επιχειρησιακού Ελέγχου"
              : "Operations Control Center"}
          </h1>
          <p className="mt-0.5 text-sm text-slate-400">
            {locale === "el"
              ? "Ζωντανή εικόνα δικτύου, διαχειρίσεις συμβάντων και εγκρίσεις ανάκαμψης σε πραγματικό χρόνο."
              : "Live network view, disruption triage, and dispatcher recovery actions across all KTEL routes."}
          </p>
        </div>

        {/* Region Pills */}
        <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-700/60 bg-slate-800/80 p-1.5 text-xs font-medium">
          {[
            {
              id: "all",
              label: locale === "el" ? "Όλες οι Περιφέρειες" : "All Regions",
            },
            { id: "attica", label: locale === "el" ? "Αττική" : "Attica" },
            {
              id: "thessaly",
              label: locale === "el" ? "Θεσσαλία" : "Thessaly",
            },
            {
              id: "peloponnese",
              label: locale === "el" ? "Πελοπόννησος" : "Peloponnese",
            },
            {
              id: "macedonia",
              label: locale === "el" ? "Μακεδονία" : "Macedonia",
            },
          ].map((reg) => (
            <button
              key={reg.id}
              onClick={() => setSelectedRegion(reg.id)}
              className={`rounded-lg px-3 py-1.5 transition ${
                selectedRegion === reg.id
                  ? "bg-sky-500 font-semibold text-white shadow-xs"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {reg.label}
            </button>
          ))}
        </div>
      </div>

      {/* Primary 3-Column Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Network Map + Disruption Table (8 Cols) */}
        <div className="space-y-6 lg:col-span-8">
          {/* Greek Route Network Topology */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {locale === "el"
                    ? "Χάρτης Δικτύου & Διαδρομών"
                    : "Network Topology Map"}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {locale === "el"
                    ? "Κύριοι συγκοινωνιακοί κόμβοι και κατάσταση γραμμών"
                    : "Primary intercity transit corridors and real-time status"}
                </p>
              </div>
              <div className="flex items-center space-x-3 text-xs">
                <span className="flex items-center space-x-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  <span className="text-slate-600 dark:text-slate-300">
                    {locale === "el" ? "Κανονικό (184)" : "On time (184)"}
                  </span>
                </span>
                <span className="flex items-center space-x-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                  <span className="text-slate-600 dark:text-slate-300">
                    {locale === "el" ? "Καθυστέρηση (21)" : "Delayed (21)"}
                  </span>
                </span>
                <span className="flex items-center space-x-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                  <span className="text-slate-600 dark:text-slate-300">
                    {locale === "el" ? "Διακοπή (4)" : "Disrupted (4)"}
                  </span>
                </span>
              </div>
            </div>

            {/* Stylized Greece Map SVG */}
            <div className="relative flex h-64 w-full items-center justify-center overflow-hidden rounded-xl bg-slate-950 p-4">
              <svg className="h-full w-full" viewBox="0 0 600 300" fill="none">
                {/* Route lines */}
                <path
                  d="M 330 45 L 310 115 L 290 145 L 360 210 L 320 270"
                  stroke="#0284c7"
                  strokeWidth="3"
                  strokeDasharray="4 2"
                />
                <path
                  d="M 330 45 L 200 90 L 230 180 L 360 210"
                  stroke="#10b981"
                  strokeWidth="2.5"
                />
                <path
                  d="M 360 210 L 460 280"
                  stroke="#10b981"
                  strokeWidth="2"
                />
                <path d="M 200 90 L 310 115" stroke="#ef4444" strokeWidth="3" />

                {/* Cities / Stations */}
                {/* Thessaloniki */}
                <circle cx="330" cy="45" r="7" fill="#38bdf8" />
                <text
                  x="345"
                  y="50"
                  fill="#f8fafc"
                  fontSize="12"
                  fontWeight="bold"
                >
                  Θεσσαλονίκη
                </text>

                {/* Ioannina */}
                <circle cx="200" cy="90" r="6" fill="#ef4444" />
                <text x="135" y="95" fill="#f8fafc" fontSize="11">
                  Ιωάννινα ⚠️
                </text>

                {/* Larissa */}
                <circle cx="310" cy="115" r="5" fill="#10b981" />
                <text x="325" y="120" fill="#94a3b8" fontSize="10">
                  Λάρισα
                </text>

                {/* Volos */}
                <circle cx="350" cy="135" r="5" fill="#f59e0b" />
                <text x="365" y="140" fill="#f59e0b" fontSize="10">
                  Βόλος (+12m)
                </text>

                {/* Patras */}
                <circle cx="230" cy="180" r="6" fill="#38bdf8" />
                <text x="180" y="185" fill="#f8fafc" fontSize="11">
                  Πάτρα
                </text>

                {/* Athens */}
                <circle
                  cx="360"
                  cy="210"
                  r="8"
                  fill="#38bdf8"
                  stroke="#ffffff"
                  strokeWidth="2"
                />
                <text
                  x="378"
                  y="215"
                  fill="#38bdf8"
                  fontSize="13"
                  fontWeight="bold"
                >
                  Αθήνα (Κηφισός)
                </text>

                {/* Kalamata */}
                <circle cx="320" cy="270" r="5" fill="#10b981" />
                <text x="260" y="275" fill="#94a3b8" fontSize="10">
                  Καλαμάτα
                </text>

                {/* Heraklion */}
                <circle cx="460" cy="280" r="6" fill="#38bdf8" />
                <text x="475" y="285" fill="#f8fafc" fontSize="11">
                  Ηράκλειο
                </text>
              </svg>
            </div>
          </div>

          {/* Active Disruptions Table */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {locale === "el"
                    ? "Ενεργά Συμβάντα & Καθυστερήσεις"
                    : "Active Disruptions & Incidents"}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {disruptions.length}{" "}
                  {locale === "el"
                    ? "περιστατικά σε εξέλιξη"
                    : "incidents in progress"}
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-400 dark:border-slate-800">
                    <th className="px-3 py-2.5">
                      {locale === "el" ? "Τύπος" : "Type"}
                    </th>
                    <th className="px-3 py-2.5">
                      {locale === "el" ? "Διαδρομή" : "Route"}
                    </th>
                    <th className="px-3 py-2.5">
                      {locale === "el" ? "Περιγραφή" : "Details"}
                    </th>
                    <th className="px-3 py-2.5">
                      {locale === "el" ? "Επίπτωση" : "Impact"}
                    </th>
                    <th className="px-3 py-2.5">
                      {locale === "el" ? "Κατάσταση" : "Status"}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {disruptions.map((d) => (
                    <tr
                      key={d.id}
                      className="transition hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-3 py-3 font-semibold text-slate-800 dark:text-slate-200">
                        {d.type}
                      </td>
                      <td className="px-3 py-3 font-medium text-slate-600 dark:text-slate-300">
                        {d.route}
                      </td>
                      <td className="px-3 py-3 text-slate-500 dark:text-slate-400">
                        {d.details}
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className={`inline-block rounded-md px-2 py-0.5 text-[10px] font-semibold ${
                            d.impact === "High"
                              ? "border border-rose-500/20 bg-rose-500/10 text-rose-500"
                              : d.impact === "Medium"
                                ? "border border-amber-500/20 bg-amber-500/10 text-amber-500"
                                : "border border-sky-500/20 bg-sky-500/10 text-sky-500"
                          }`}
                        >
                          {d.impact}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <span className="font-medium text-slate-700 dark:text-slate-300">
                          {d.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Dispatcher Recovery Actions (4 Cols) */}
        <div className="space-y-6 lg:col-span-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="flex items-center space-x-2 text-base font-bold text-slate-900 dark:text-white">
                  <span>
                    {locale === "el"
                      ? "Προτεινόμενες Ενέργειες"
                      : "Recommended Actions"}
                  </span>
                  <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] font-bold text-sky-500">
                    {
                      recoveryActions.filter((a) => !a.approved && !a.rejected)
                        .length
                    }
                  </span>
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {locale === "el"
                    ? "Απαιτείται ανθρώπινη έγκριση σταθμάρχη (Phase 5)"
                    : "Dispatcher signoff required prior to publication"}
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {recoveryActions.map((action) => (
                <div
                  key={action.id}
                  className={`rounded-xl border p-4 transition ${
                    action.approved
                      ? "border-emerald-500/40 bg-emerald-50 dark:bg-emerald-950/20"
                      : action.rejected
                        ? "border-slate-300 bg-slate-100 opacity-60 dark:border-slate-700 dark:bg-slate-800/40"
                        : "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60"
                  }`}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span
                      className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${
                        action.priority === "High"
                          ? "bg-rose-500/20 text-rose-500"
                          : action.priority === "Medium"
                            ? "bg-amber-500/20 text-amber-500"
                            : "bg-sky-500/20 text-sky-500"
                      }`}
                    >
                      {action.priority} Priority
                    </span>
                    {action.approved && (
                      <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                        ✓ {locale === "el" ? "Εγκρίθηκε" : "Approved"}
                      </span>
                    )}
                    {action.rejected && (
                      <span className="text-xs font-bold text-slate-400">
                        ✗ {locale === "el" ? "Απορρίφθηκε" : "Rejected"}
                      </span>
                    )}
                  </div>

                  <h4 className="mb-1 text-sm font-bold text-slate-900 dark:text-white">
                    {action.title}
                  </h4>
                  <p className="mb-4 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                    {action.description}
                  </p>

                  {!action.approved && !action.rejected && (
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleAction(action.id, "approve")}
                        className="flex-1 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-sky-500"
                      >
                        {locale === "el" ? "Έγκριση" : "Approve"}
                      </button>
                      <button
                        onClick={() => handleAction(action.id, "reject")}
                        className="rounded-lg bg-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                      >
                        {locale === "el" ? "Απόρριψη" : "Reject"}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
