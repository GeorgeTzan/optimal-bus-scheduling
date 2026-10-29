"use client";

import React from "react";
import { useI18n } from "../../i18n/context";

interface KPICardsProps {
  totalTrips: number;
  assignedTrips: number;
  unassignedTrips: number;
  busesUsed: number;
  totalBuses: number;
  totalDrivingMinutes: number;
  totalIdleMinutes: number;
}

function CircularRing({ percent, color }: { percent: number; color: string }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, percent));
  const strokeDashoffset = circumference - (clamped / 100) * circumference;

  const strokeColors: Record<string, string> = {
    teal: "text-teal-500",
    sky: "text-sky-500",
    emerald: "text-emerald-500",
    violet: "text-violet-500",
    rose: "text-rose-500",
  };

  return (
    <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
      <svg className="h-12 w-12 -rotate-90 transform">
        <circle
          cx="24"
          cy="24"
          r={radius}
          className="text-slate-200 dark:text-slate-800"
          strokeWidth="3.5"
          stroke="currentColor"
          fill="transparent"
        />
        <circle
          cx="24"
          cy="24"
          r={radius}
          className={`${strokeColors[color] || "text-sky-500"} transition-all duration-700 ease-out`}
          strokeWidth="3.5"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
        />
      </svg>
      <span className="absolute text-[11px] font-bold text-slate-700 dark:text-slate-200">
        {clamped}%
      </span>
    </div>
  );
}

export function KPICards({
  totalTrips,
  assignedTrips,
  unassignedTrips,
  busesUsed,
  totalBuses,
  totalDrivingMinutes,
  totalIdleMinutes,
}: KPICardsProps) {
  const { locale } = useI18n();
  const isEl = locale === "el";

  const tripCoveragePercent =
    totalTrips > 0 ? Math.round((assignedTrips / totalTrips) * 100) : 0;
  const busUtilPercent =
    totalBuses > 0 ? Math.round((busesUsed / totalBuses) * 100) : 0;

  const driveHours = Math.floor(totalDrivingMinutes / 60);
  const driveMins = totalDrivingMinutes % 60;

  const idleHours = Math.floor(totalIdleMinutes / 60);
  const idleMins = totalIdleMinutes % 60;

  return (
    <div className="mb-6 grid grid-cols-1 gap-4 font-sans sm:grid-cols-2 lg:grid-cols-5">
      {/* 1. Scheduled Trips */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start space-x-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-lg text-teal-600 dark:bg-teal-950/60 dark:text-teal-400">
            🚌
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {isEl ? "Ανατεθειμένα Δρομολόγια" : "Assigned Trips"}
            </p>
            <h3 className="mt-0.5 text-xl font-bold text-slate-900 dark:text-white">
              {assignedTrips}
            </h3>
            <p className="text-[11px] text-slate-400">
              / {totalTrips} {isEl ? "σύνολο" : "total"}
            </p>
          </div>
        </div>
        <CircularRing percent={tripCoveragePercent} color="teal" />
      </div>

      {/* 2. Buses in Service */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start space-x-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-lg text-sky-600 dark:bg-sky-950/60 dark:text-sky-400">
            🚍
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {isEl ? "Λεωφορεία σε Χρήση" : "Buses in Service"}
            </p>
            <h3 className="mt-0.5 text-xl font-bold text-slate-900 dark:text-white">
              {busesUsed}
            </h3>
            <p className="text-[11px] text-slate-400">
              / {totalBuses} {isEl ? "διαθέσιμα" : "available"}
            </p>
          </div>
        </div>
        <CircularRing percent={busUtilPercent} color="sky" />
      </div>

      {/* 3. Total Driving Time */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start space-x-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-lg text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
            ⏱️
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {isEl ? "Χρόνος Οδήγησης" : "Total Driving Time"}
            </p>
            <h3 className="mt-0.5 text-xl font-bold text-slate-900 dark:text-white">
              {driveHours}h {driveMins}m
            </h3>
            <p className="text-[11px] text-slate-400">
              {totalDrivingMinutes} {isEl ? "λεπτά" : "mins"}
            </p>
          </div>
        </div>
      </div>

      {/* 4. Total Idle Time */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start space-x-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-lg text-violet-600 dark:bg-violet-950/60 dark:text-violet-400">
            ⌛
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {isEl ? "Χρόνος Αναμονής (Idle)" : "Total Idle Time"}
            </p>
            <h3 className="mt-0.5 text-xl font-bold text-slate-900 dark:text-white">
              {idleHours}h {idleMins}m
            </h3>
            <p className="text-[11px] text-slate-400">
              {totalIdleMinutes} {isEl ? "λεπτά" : "mins"}
            </p>
          </div>
        </div>
      </div>

      {/* 5. Unassigned Trips / Base Mismatch */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start space-x-3">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg ${
              unassignedTrips > 0
                ? "bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400"
                : "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400"
            }`}
          >
            {unassignedTrips > 0 ? "⚠️" : "✓"}
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {isEl ? "Ανεκτέλεστα Δρομολόγια" : "Unassigned Trips"}
            </p>
            <h3
              className={`mt-0.5 text-xl font-bold ${
                unassignedTrips > 0
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {unassignedTrips}
            </h3>
            <p className="text-[11px] text-slate-400">
              {unassignedTrips > 0
                ? isEl
                  ? "Απαιτείται ανάθεση"
                  : "Assignment needed"
                : totalTrips > 0
                  ? isEl
                    ? "Όλα τα δρομολόγια έχουν ανάθεση"
                    : "All trips assigned"
                  : isEl
                    ? "Δεν υπάρχουν δρομολόγια"
                    : "No trips loaded"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
