import type { ScheduleDisplayContext, StationLabel } from "./display";
import type { StudioRevision, StudioTrip, StudioResource } from "./types";

export interface Verification {
  valid: boolean;
  violations: Array<{ rule_id: string; message: string; entity_ids: string[] }>;
  coverage_percent: number;
  unassigned_trips: string[];
}
export interface PersistedRevision {
  revision_id: string;
  version: number;
  status: StudioRevision["status"];
  author: string;
  source_kind: "operational" | "reference_archive";
  source_hash?: string;
  source_review_required: boolean;
  timezone: string;
  service_day_start_utc: string;
  day_boundaries_minutes: number[];
  source_stations: StationLabel[];
  source_resources: Array<{
    resource_id?: string;
    busId?: string;
    driver_name?: string;
    driver_code?: string;
    driver_version?: number;
    vehicle_version?: number;
    vehicle_code?: string;
    vehicle_label?: string;
    home_station_code?: string;
  }>;
  updated_at: string;
  assignments: Array<{
    trip_id: string;
    resource_id: string;
    is_locked: boolean;
  }>;
  problem: {
    service_date: string;
    trips: Array<{
      id: string;
      start_minutes: number;
      end_minutes: number;
      start_station: string;
      end_station: string;
      allowed_bus_types: string[];
    }>;
    resources: Array<{
      resource_id: string;
      driver_id: string;
      bus_id: string;
      home_station: string;
    }>;
  };
  source_trips: Array<{
    id: string;
    trip_code?: string;
    is_cancelled?: boolean;
    cancellation_reason?: string | null;
    distance_km?: number | null;
    origin?: StationLabel;
    destination?: StationLabel;
    properties?: { distance: number };
    classification?: { roadType: string };
  }>;
  verification: Verification;
}
export function studioRevision(rev: PersistedRevision): StudioRevision {
  return {
    revisionId: rev.revision_id,
    version: rev.version,
    status: rev.status,
    author: rev.author,
    updatedAt: rev.updated_at,
  };
}
export function studioTrips(rev: PersistedRevision): StudioTrip[] {
  const assigned = new Map(rev.assignments.map((a) => [a.trip_id, a]));
  const source = new Map(rev.source_trips.map((t) => [t.id, t]));
  return rev.problem.trips.map((t) => {
    const assignment = assigned.get(t.id);
    const errors = rev.verification.violations.filter((v) =>
      v.entity_ids.includes(t.id),
    );
    return {
      id: t.id,
      tripCode: source.get(t.id)?.trip_code ?? t.id,
      resourceId: assignment?.resource_id ?? "UNASSIGNED",
      startMinutes: t.start_minutes,
      endMinutes: t.end_minutes,
      startStation: t.start_station,
      endStation: t.end_station,
      allowedBusTypes: t.allowed_bus_types,
      isLocked: assignment?.is_locked ?? false,
      hasViolation: errors.length > 0,
      violationMessage: errors
        .map((v) => `${v.rule_id}: ${v.message}`)
        .join("\n"),
      distanceKm:
        source.get(t.id)?.distance_km ?? source.get(t.id)?.properties?.distance,
      roadType: source.get(t.id)?.classification?.roadType,
    };
  });
}
export function studioResources(rev: PersistedRevision): StudioResource[] {
  const source = new Map(
    rev.source_resources.map((record) => [
      record.resource_id ?? record.busId,
      record,
    ]),
  );
  return rev.problem.resources.map((r) => {
    const record = source.get(r.resource_id);
    return {
      id: r.resource_id,
      code: record?.vehicle_code ?? r.bus_id,
      driverName: record?.driver_name ?? r.driver_id,
      busPlate: record?.vehicle_label ?? r.bus_id,
      homeStation: record?.home_station_code ?? r.home_station,
    };
  });
}
export function studioDisplay(rev: PersistedRevision): ScheduleDisplayContext {
  return {
    stations: rev.source_stations,
    timezone: rev.timezone,
    serviceDayStartUtc: rev.service_day_start_utc,
    dayBoundariesMinutes: rev.day_boundaries_minutes,
  };
}
