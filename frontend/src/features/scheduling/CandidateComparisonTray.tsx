"use client";

import React, { useState } from "react";
import { useI18n } from "../../i18n/context";

export interface CandidatePlan {
  id: string;
  name: string;
  subtitle: string;
  algorithm: string;
  generatedAt: string;
  totalTrips: number;
  assignedTrips: number;
  unassignedTrips: number;
  busesUsed: number;
  totalDrivingMinutes: number;
  totalIdleMinutes: number;
  isRecommended?: boolean;
  assignments: Array<{ tripId: string; busId: string; idleTime: number }>;
}

interface CandidateComparisonTrayProps {
  plans: CandidatePlan[];
  selectedPlanId: string;
  onSelectPlan: (planId: string) => void;
  onApplyPlan: (plan: CandidatePlan) => void;
}

export function CandidateComparisonTray({
  plans,
  selectedPlanId,
  onSelectPlan,
  onApplyPlan,
}: CandidateComparisonTrayProps) {
  const { locale } = useI18n();
  const isEl = locale === "el";

  const [activeTab, setActiveTab] = useState<"candidates" | "validation" | "audit">("candidates");

  const selectedPlan = plans.find((p) => p.id === selectedPlanId) || plans[0];

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xs overflow-hidden mt-6 font-sans">
      {/* Header Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-200 dark:border-slate-800 px-6 py-3.5 bg-slate-50/50 dark:bg-slate-800/40 gap-3">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab("candidates")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "candidates"
                ? "bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-xs"
                : "text-slate-500 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            {isEl
              ? `Προτάσεις Αλγορίθμων (${plans.length})`
              : `Algorithm Solutions (${plans.length})`}
          </button>
          <button
            onClick={() => setActiveTab("validation")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 ${
              activeTab === "validation"
                ? "bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-xs"
                : "text-slate-500 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            <span>{isEl ? "Έλεγχοι Εγκυρότητας" : "Legality Verification"}</span>
            <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-[10px] flex items-center justify-center font-bold">
              ✓
            </span>
          </button>
          <button
            onClick={() => setActiveTab("audit")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "audit"
                ? "bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-xs"
                : "text-slate-500 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            {isEl ? "Ιστορικό Επιλύσεων" : "Solver Runs"}
          </button>
        </div>

        {selectedPlan && (
          <div className="flex items-center space-x-3">
            <span className="text-xs text-slate-500">
              {isEl ? "Επιλεγμένο:" : "Active:"}{" "}
              <strong className="text-slate-800 dark:text-slate-200">
                {selectedPlan.name}
              </strong>
            </span>
            <button
              onClick={() => onApplyPlan(selectedPlan)}
              className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-xs shadow-sky-600/30 transition flex items-center space-x-1.5"
            >
              <span>🚀</span>
              <span>{isEl ? "Φόρτωση στο Χρονολόγιο" : "Apply to Timeline"}</span>
            </button>
          </div>
        )}
      </div>

      {/* Real Plans Grid */}
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => {
            const isSelected = plan.id === selectedPlanId;
            const idleHours = Math.round(plan.totalIdleMinutes / 60);
            const drivingHours = Math.round(plan.totalDrivingMinutes / 60);

            return (
              <div
                key={plan.id}
                onClick={() => onSelectPlan(plan.id)}
                className={`cursor-pointer rounded-xl border p-4.5 transition relative ${
                  isSelected
                    ? "border-sky-500 bg-sky-50/30 dark:bg-sky-950/20 shadow-md ring-2 ring-sky-500/20"
                    : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-white dark:bg-slate-900"
                }`}
              >
                {plan.isRecommended && (
                  <span className="absolute -top-2.5 right-4 px-2 py-0.5 rounded-full text-[10px] font-bold bg-teal-500 text-white shadow-xs">
                    ★ {isEl ? "Πρωτεύων Αλγόριθμος" : "Primary CV Solver"}
                  </span>
                )}

                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h4 className="font-bold text-sm text-slate-900 dark:text-white">
                      {plan.name}
                    </h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      {plan.subtitle}
                    </p>
                  </div>
                  <div className="px-2 py-0.5 rounded bg-sky-100 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 font-mono font-bold text-[11px] shrink-0">
                    {plan.algorithm}
                  </div>
                </div>

                {/* Real Metrics Grid */}
                <div className="grid grid-cols-3 gap-2 py-3 border-y border-slate-100 dark:border-slate-800/80 my-3 text-center">
                  <div>
                    <span className="text-[10px] text-slate-400 block">
                      {isEl ? "Ανάθεση" : "Assigned"}
                    </span>
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      {plan.assignedTrips} / {plan.totalTrips}
                    </span>
                    {plan.unassignedTrips > 0 && (
                      <span className="text-[10px] font-semibold text-rose-500 block">
                        {plan.unassignedTrips} {isEl ? "ανεκτέλεστα" : "unassigned"}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">
                      {isEl ? "Λεωφορεία" : "Buses Used"}
                    </span>
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      {plan.busesUsed}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">
                      {isEl ? "Αδράνεια" : "Idle Time"}
                    </span>
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      {idleHours}h {plan.totalIdleMinutes % 60}m
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <span className="text-[11px] text-slate-400">
                    {isEl ? "Οδήγηση" : "Drive"}: {drivingHours}h • {plan.generatedAt}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onApplyPlan(plan);
                    }}
                    className="text-sky-600 dark:text-sky-400 hover:underline font-semibold"
                  >
                    {isEl ? "Εφαρμογή ›" : "Apply ›"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
