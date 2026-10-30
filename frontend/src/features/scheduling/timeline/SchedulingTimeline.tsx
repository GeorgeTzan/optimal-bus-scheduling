"use client";
import React, { useMemo, useState, useRef, useEffect } from "react";
import { BusFront, UserRound, LockKeyhole, AlertTriangle } from "lucide-react";
import { useI18n } from "../../../i18n/context";
import type { StudioTrip, StudioResource } from "../types";
import { scheduleDisplay, type ScheduleDisplayContext } from "../display";
interface Props {
  displayContext?: ScheduleDisplayContext;
  resources: StudioResource[];
  trips: StudioTrip[];
  selectedTripId: string | null;
  onSelectTrip: (id: string) => void;
  onRequestMove?: (tripId: string, resourceId: string) => void;
  grouping?: "buses" | "drivers";
  day?: number;
  zoom?: number;
}
const ROW_HEIGHT = 54,
  LABEL_WIDTH = 200;
export function SchedulingTimeline({
  displayContext,
  resources,
  trips,
  selectedTripId,
  onSelectTrip,
  onRequestMove,
  grouping = "buses",
  day = 0,
  zoom = 1,
}: Props) {
  const { locale } = useI18n();
  const el = locale === "el";
  const { stationName, timeLabel, dayWindow } = scheduleDisplay(displayContext);
  const scroller = useRef<HTMLDivElement>(null);
  const [scroll, setScroll] = useState(0);
  const [dragged, setDragged] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const draggingTrip = trips.find((item) => item.id === dragged);
  const [height, setHeight] = useState(400);
  useEffect(() => {
    if (!scroller.current) return;
    const observer = new ResizeObserver((entries) =>
      setHeight(entries[0]?.contentRect.height ?? 400),
    );
    observer.observe(scroller.current);
    return () => observer.disconnect();
  }, []);
  const { start, end } = dayWindow(day);
  const pxPerMinute = 1.15 * zoom;
  const trackWidth = (end - start) * pxPerMinute;
  const rows = useMemo(() => {
    const all: StudioResource[] = [
      {
        id: "UNASSIGNED",
        code: "—",
        driverName: el ? "Χωρίς ανάθεση" : "Unassigned",
        busPlate: "—",
        homeStation: "",
      },
      ...resources,
    ];
    const index = new Map(all.map((r) => [r.id, [] as StudioTrip[]]));
    trips
      .filter((t) => t.startMinutes < end && t.endMinutes > start)
      .forEach((t) => index.get(t.resourceId)?.push(t));
    return all
      .map((r) => ({ resource: r, trips: index.get(r.id)! }))
      .filter(
        (r) =>
          r.resource.id !== "UNASSIGNED" || r.trips.length > 0 || !!dragged,
      );
  }, [resources, trips, start, end, el, dragged]);
  const first = Math.max(0, Math.floor((scroll - 40) / ROW_HEIGHT) - 4);
  const last = Math.min(
    rows.length,
    first + Math.ceil(height / ROW_HEIGHT) + 9,
  );
  useEffect(() => {
    if (scroller.current) {
      scroller.current.scrollLeft = 4 * 60 * pxPerMinute;
    }
  }, [day, pxPerMinute]); // Focus the operating morning, retaining full 24h navigation.
  useEffect(() => {
    if (!selectedTripId || !scroller.current) return;
    const index = rows.findIndex((row) =>
      row.trips.some((t) => t.id === selectedTripId),
    );
    const trip = rows[index]?.trips.find((t) => t.id === selectedTripId);
    if (index < 0 || !trip) return;
    scroller.current.scrollTop = Math.max(0, index * ROW_HEIGHT - ROW_HEIGHT);
    scroller.current.scrollLeft = Math.max(
      0,
      (trip.startMinutes - start) * pxPerMinute - 80,
    );
  }, [selectedTripId, rows, start, pxPerMinute]);
  return (
    <div
      className="timeline-scroll"
      ref={scroller}
      onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
      data-testid="schedule-timeline"
    >
      <div style={{ width: LABEL_WIDTH + trackWidth, minWidth: "100%" }}>
        <div className="time-axis">
          <div className="resource-axis" style={{ width: LABEL_WIDTH }}>
            {grouping === "buses"
              ? el
                ? "ΟΧΗΜΑ / ΟΔΗΓΟΣ"
                : "BUS / DRIVER"
              : el
                ? "ΟΔΗΓΟΣ / ΟΧΗΜΑ"
                : "DRIVER / BUS"}
          </div>
          <div className="hours-axis" style={{ width: trackWidth }}>
            {Array.from(
              { length: Math.floor((end - start) / 60) + 1 },
              (_, hour) => (
                <div
                  key={hour}
                  className="hour-tick"
                  style={{ left: hour * 60 * pxPerMinute }}
                >
                  {timeLabel(start + hour * 60)}
                </div>
              ),
            )}
          </div>
        </div>
        <div style={{ height: rows.length * ROW_HEIGHT, position: "relative" }}>
          {rows
            .slice(first, last)
            .map(({ resource: r, trips: rowTrips }, index) => {
              const total = rowTrips.reduce(
                (sum, t) =>
                  sum +
                  Math.min(t.endMinutes, end) -
                  Math.max(t.startMinutes, start),
                0,
              );
              return (
                <div
                  className={`resource-row ${(first + index) % 2 ? "alternate" : ""} ${hovered === r.id && dragged ? "drop-target" : ""}`}
                  key={r.id}
                  onDragOver={(event) => {
                    if (dragged && onRequestMove) {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setHovered(r.id);
                    }
                  }}
                  onDragLeave={(event) => {
                    if (
                      !event.currentTarget.contains(
                        event.relatedTarget as Node | null,
                      )
                    )
                      setHovered(null);
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const id = dragged;
                    setDragged(null);
                    setHovered(null);
                    if (id && draggingTrip && draggingTrip.resourceId !== r.id)
                      onRequestMove?.(id, r.id);
                  }}
                  style={{
                    top: (first + index) * ROW_HEIGHT,
                    height: ROW_HEIGHT,
                  }}
                >
                  <div
                    className="resource-label"
                    data-resource-id={r.id}
                    style={{ width: LABEL_WIDTH }}
                  >
                    <span
                      className={`resource-symbol ${r.id === "UNASSIGNED" ? "warning" : ""}`}
                    >
                      {r.id === "UNASSIGNED" ? (
                        <AlertTriangle size={17} />
                      ) : grouping === "buses" ? (
                        <BusFront size={18} />
                      ) : (
                        <UserRound size={18} />
                      )}
                    </span>
                    <div>
                      <strong>
                        {r.id === "UNASSIGNED"
                          ? r.driverName
                          : grouping === "buses"
                            ? `${el ? "Όχημα" : "Bus"} ${r.code}`
                            : `${el ? "Οδηγός" : "Driver"} ${r.driverName}`}
                      </strong>
                      <small>
                        {r.id === "UNASSIGNED"
                          ? `${rowTrips.length} ${el ? "δρομολόγια" : "trips"}`
                          : grouping === "buses"
                            ? `${el ? "Οδηγός" : "Driver"} ${r.driverName} · ${stationName(r.homeStation, el)}`
                            : `${el ? "Όχημα" : "Bus"} ${r.code} · ${Math.floor(total / 60)}h ${total % 60}m`}
                      </small>
                    </div>
                    <span className="resource-count">{rowTrips.length}</span>
                  </div>
                  <div
                    className="resource-track"
                    style={{
                      width: trackWidth,
                      backgroundSize: `${60 * pxPerMinute}px 100%`,
                    }}
                  >
                    {draggingTrip &&
                      hovered === r.id &&
                      draggingTrip.resourceId !== r.id && (
                        <div
                          className="timeline-drop-preview"
                          style={{
                            left:
                              (Math.max(draggingTrip.startMinutes, start) -
                                start) *
                              pxPerMinute,
                            width: Math.max(
                              (Math.min(draggingTrip.endMinutes, end) -
                                Math.max(draggingTrip.startMinutes, start)) *
                                pxPerMinute,
                              120,
                            ),
                          }}
                        >
                          <strong>
                            {r.id === "UNASSIGNED"
                              ? el
                                ? "Χωρίς ανάθεση"
                                : "Unassigned"
                              : `${r.driverName} · ${r.busPlate}`}
                          </strong>
                          <small>
                            {timeLabel(draggingTrip.startMinutes)} –{" "}
                            {timeLabel(draggingTrip.endMinutes)} ·{" "}
                            {el ? "Αφήστε για έλεγχο" : "Release to review"}
                          </small>
                        </div>
                      )}
                    {rowTrips.map((t) => {
                      const left =
                        (Math.max(t.startMinutes, start) - start) * pxPerMinute;
                      const width =
                        (Math.min(t.endMinutes, end) -
                          Math.max(t.startMinutes, start)) *
                        pxPerMinute;
                      const color = Number(t.startStation) % 4;
                      return (
                        <button
                          key={t.id}
                          data-trip-id={t.id}
                          draggable={!!onRequestMove && !t.isLocked}
                          onDragStart={(event) => {
                            if (!onRequestMove || t.isLocked) {
                              event.preventDefault();
                              return;
                            }
                            event.dataTransfer.setData("text/plain", t.id);
                            event.dataTransfer.effectAllowed = "move";
                            setDragged(t.id);
                          }}
                          onDragEnd={() => {
                            setDragged(null);
                            setHovered(null);
                          }}
                          aria-label={`${t.tripCode}: ${t.startStation} to ${t.endStation}`}
                          title={`${t.tripCode} · ${stationName(t.startStation, el)} → ${stationName(t.endStation, el)}\n${timeLabel(t.startMinutes)}–${timeLabel(t.endMinutes)}${t.violationMessage ? "\n" + t.violationMessage : ""}`}
                          onClick={() => onSelectTrip(t.id)}
                          className={`timeline-trip route-${color} ${t.hasViolation ? "has-conflict" : ""} ${t.isLocked ? "is-locked" : ""} ${selectedTripId === t.id ? "is-selected" : ""} ${dragged === t.id ? "is-dragging" : ""}`}
                          style={{ left, width: Math.max(width, 8) }}
                        >
                          <strong>
                            {stationName(t.startStation, el)} →{" "}
                            {stationName(t.endStation, el)}
                          </strong>
                          <small>
                            {timeLabel(t.startMinutes)} –{" "}
                            {timeLabel(t.endMinutes)}
                          </small>
                          {t.isLocked && <LockKeyhole size={11} />}
                        </button>
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
