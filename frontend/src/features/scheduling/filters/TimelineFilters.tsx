"use client";

import React from "react";
import { useI18n } from "../../../i18n/context";
import type { StudioFilters } from "../types";

interface TimelineFiltersProps {
  filters: StudioFilters;
  stations: string[];
  onChange: (filters: StudioFilters) => void;
}

export function TimelineFilters({ filters, stations, onChange }: TimelineFiltersProps) {
  const { locale } = useI18n();
  const isEl = locale === "el";

  return (
    <div className="flex flex-wrap items-center gap-3 p-3 bg-muted/30 border-b border-border text-xs">
      <div className="flex items-center gap-1.5 flex-1 min-w-[200px]">
        <label htmlFor="search-trip" className="font-medium text-muted-foreground whitespace-nowrap">
          {isEl ? "Αναζήτηση:" : "Search:"}
        </label>
        <input
          id="search-trip"
          type="text"
          value={filters.searchQuery}
          onChange={(e) => onChange({ ...filters, searchQuery: e.target.value })}
          placeholder={isEl ? "Κωδικός δρομολογίου / πόλη..." : "Trip code / station..."}
          className="w-full px-2.5 py-1 text-xs rounded border border-border bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <label htmlFor="station-filter" className="font-medium text-muted-foreground whitespace-nowrap">
          {isEl ? "Σταθμός:" : "Station:"}
        </label>
        <select
          id="station-filter"
          value={filters.station}
          onChange={(e) => onChange({ ...filters, station: e.target.value })}
          className="px-2 py-1 text-xs rounded border border-border bg-background text-foreground focus:outline-none"
        >
          <option value="">{isEl ? "Όλοι οι Σταθμοί" : "All Stations"}</option>
          {stations.map((st) => (
            <option key={st} value={st}>
              {st}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={filters.onlyLocked}
            onChange={(e) => onChange({ ...filters, onlyLocked: e.target.checked })}
            className="rounded border-border text-primary focus:ring-primary"
          />
          <span>{isEl ? "Μόνο Κλειδωμένα" : "Only Locked"}</span>
        </label>

        <label className="flex items-center gap-1.5 cursor-pointer select-none text-red-600 dark:text-red-400">
          <input
            type="checkbox"
            checked={filters.onlyViolations}
            onChange={(e) => onChange({ ...filters, onlyViolations: e.target.checked })}
            className="rounded border-border text-red-600 focus:ring-red-500"
          />
          <span>{isEl ? "Μόνο Παραβιάσεις" : "Only Violations"}</span>
        </label>
      </div>
    </div>
  );
}
