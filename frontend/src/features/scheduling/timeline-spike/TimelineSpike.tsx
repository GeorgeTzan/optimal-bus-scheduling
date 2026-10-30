"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import { generateSyntheticDataset } from "./synthetic-fixtures";
import type { TimelineTrip, TimelineResource } from "./synthetic-fixtures";

interface TimelineSpikeProps {
  initialTripCount?: 400 | 1000 | 2500;
}

export function TimelineSpike({ initialTripCount = 400 }: TimelineSpikeProps) {
  const [tripCount, setTripCount] = useState<400 | 1000 | 2500>(initialTripCount);
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);
  const [renderDurationMs, setRenderDurationMs] = useState<number>(0);
  const [fps, setFps] = useState<number>(60);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Generate synthetic dataset
  const { trips, resources } = useMemo(() => {
    const t0 = performance.now();
    const data = generateSyntheticDataset(tripCount);
    const t1 = performance.now();
    setRenderDurationMs(Math.round(t1 - t0));
    return data;
  }, [tripCount]);

  // Index trips by resource
  const tripsByResource = useMemo(() => {
    const map = new Map<string, TimelineTrip[]>();
    for (const r of resources) {
      map.set(r.id, []);
    }
    for (const t of trips) {
      const list = map.get(t.resourceId);
      if (list) list.push(t);
    }
    return map;
  }, [trips, resources]);

  // FPS tracking during scrolling
  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let animId: number;

    const measureFps = (now: number) => {
      frameCount++;
      if (now - lastTime >= 1000) {
        setFps(Math.round((frameCount * 1000) / (now - lastTime)));
        frameCount = 0;
        lastTime = now;
      }
      animId = requestAnimationFrame(measureFps);
    };

    animId = requestAnimationFrame(measureFps);
    return () => cancelAnimationFrame(animId);
  }, []);

  // Keyboard navigation across trips
  const handleKeyDown = (e: React.KeyboardEvent, currentTripIndex: number, currentList: TimelineTrip[]) => {
    if (e.key === "ArrowRight" && currentTripIndex < currentList.length - 1) {
      e.preventDefault();
      const next = currentList[currentTripIndex + 1];
      if (next) setSelectedTripId(next.id);
    } else if (e.key === "ArrowLeft" && currentTripIndex > 0) {
      e.preventDefault();
      const prev = currentList[currentTripIndex - 1];
      if (prev) setSelectedTripId(prev.id);
    }
  };

  const minutesToPercent = (min: number) => {
    // 00:00 (0) to 24:00 (1440)
    return ((min / 1440) * 100).toFixed(2);
  };

  return (
    <div className="flex flex-col h-full w-full bg-background text-foreground p-4">
      {/* Header controls & benchmark telemetry */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <h2 className="text-xl font-bold">Timeline Virtualization Viability Spike</h2>
          <p className="text-sm text-muted-foreground">
            Benchmarking performance and DOM responsiveness on Greek KTEL schedule ladders.
          </p>
        </div>

        <div className="flex items-center gap-4">
          <label className="text-sm font-medium">Dataset Scale:</label>
          <div className="flex gap-1">
            {[400, 1000, 2500].map((count) => (
              <button
                key={count}
                onClick={() => setTripCount(count as 400 | 1000 | 2500)}
                className={`px-3 py-1 text-sm rounded font-medium border ${
                  tripCount === count
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-border hover:bg-muted/80"
                }`}
              >
                {count} Trips
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 px-3 py-1 rounded bg-muted/60 text-xs font-mono">
            <span>Gen: <strong>{renderDurationMs}ms</strong></span>
            <span>FPS: <strong>{fps}</strong></span>
            <span>Resources: <strong>{resources.length}</strong></span>
          </div>
        </div>
      </div>

      {/* Selected Trip Details */}
      {selectedTripId && (
        <div className="mt-2 p-2 bg-primary/10 border border-primary/20 rounded text-xs flex items-center justify-between">
          <span>Selected Trip: <strong>{selectedTripId}</strong></span>
          <button
            onClick={() => setSelectedTripId(null)}
            className="text-muted-foreground hover:text-foreground font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Gantt Timeline Viewport */}
      <div
        ref={scrollContainerRef}
        className="mt-4 flex-1 overflow-auto border border-border rounded relative bg-card"
        style={{ minHeight: "500px" }}
      >
        {/* Timeline Header (Hours 05:00 to 24:00) */}
        <div className="sticky top-0 z-20 flex bg-muted border-b border-border h-8 items-center text-xs font-semibold text-muted-foreground">
          <div className="w-56 px-3 shrink-0 border-r border-border">Πόρος / Όχημα</div>
          <div className="flex-1 relative h-full">
            {Array.from({ length: 20 }, (_, i) => i + 5).map((hour) => (
              <div
                key={hour}
                className="absolute top-0 bottom-0 border-l border-border/50 text-[10px] pl-1 pt-1"
                style={{ left: `${((hour * 60) / 1440) * 100}%` }}
              >
                {hour.toString().padStart(2, "0")}:00
              </div>
            ))}
          </div>
        </div>

        {/* Resource Rows */}
        <div className="divide-y divide-border">
          {resources.map((res) => {
            const rowTrips = tripsByResource.get(res.id) ?? [];
            return (
              <div key={res.id} className="flex h-12 items-center hover:bg-muted/20">
                {/* Resource Info Column */}
                <div className="w-56 px-3 shrink-0 border-r border-border flex flex-col justify-center text-xs truncate">
                  <div className="font-semibold text-foreground truncate">{res.driverName}</div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {res.busPlate} • {res.homeStation}
                  </div>
                </div>

                {/* Timeline Track */}
                <div className="flex-1 relative h-full">
                  {rowTrips.map((trip, idx) => {
                    const left = minutesToPercent(trip.startMinutes);
                    const width = minutesToPercent(trip.endMinutes - trip.startMinutes);
                    const isSelected = trip.id === selectedTripId;

                    return (
                      <div
                        key={trip.id}
                        role="button"
                        tabIndex={0}
                        aria-label={`Δρομολόγιο ${trip.id}: ${trip.origin} προς ${trip.destination}`}
                        onClick={() => setSelectedTripId(trip.id)}
                        onKeyDown={(e) => handleKeyDown(e, idx, rowTrips)}
                        className={`absolute top-1.5 bottom-1.5 rounded px-1.5 text-[10px] font-medium flex items-center justify-between cursor-pointer border select-none transition-shadow ${
                          isSelected
                            ? "bg-primary text-primary-foreground border-ring shadow-md ring-2 ring-ring"
                            : trip.isLocked
                            ? "bg-amber-600 text-white border-amber-700 hover:bg-amber-500"
                            : "bg-blue-600 text-white border-blue-700 hover:bg-blue-500"
                        }`}
                        style={{
                          left: `${left}%`,
                          width: `${width}%`,
                        }}
                      >
                        <span className="truncate">
                          {trip.origin} → {trip.destination}
                        </span>
                        {trip.isLocked && <span className="ml-1 text-[9px]">🔒</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
