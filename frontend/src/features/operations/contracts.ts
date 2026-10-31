export interface OperationalEvent {
  id: number;
  kind:
    | "delay"
    | "breakdown"
    | "note"
    | "departure"
    | "completion"
    | "resolution";
  description: string;
  delay_minutes: number | null;
  actor_id: number;
  actor_name: string;
  recorded_at: string;
  resolved_event_id: number | null;
  state_version: number;
}
export interface LinkedOperationalEvent extends OperationalEvent {
  source_state_version: number;
  source_publication: Publication;
  is_open: boolean;
}
export interface OperationalTrip {
  trip_id: string;
  trip: {
    trip_code: string;
    origin: { code: string; name_el: string; name_en?: string };
    destination: { code: string; name_el: string; name_en?: string };
  };
  resource: {
    driver_name: string;
    driver_code: string;
    vehicle_label: string;
    vehicle_code: string;
  } | null;
  start_minutes: number;
  end_minutes: number;
  is_cancelled: boolean;
  cancellation_reason: string | null;
  linked_events: LinkedOperationalEvent[];
  linked_open_count: number;
  version: number;
  reported_status: "planned" | "departure" | "completion";
  open_count: number;
  events: OperationalEvent[];
}
export interface Publication {
  publication_id: string;
  revision_id: string;
  published_at: string;
  published_by: string;
}
export interface OperationsDay {
  service_date: string;
  timezone: string;
  service_day_start_utc?: string;
  day_boundaries_minutes?: number[];
  publications: Publication[];
  publication: Publication | null;
  newer_publication: boolean;
  items: OperationalTrip[];
  total: number;
  open_count: number;
  page: number;
  page_size: number;
}
export interface ReportTarget {
  row: OperationalTrip;
  publication: Publication;
  serviceDate: string;
  timezone: string;
  event?: OperationalEvent;
}
export const updateLabel = (kind: OperationalEvent["kind"], el: boolean) =>
  ({
    delay: el ? "Καθυστέρηση" : "Delay",
    breakdown: el ? "Βλάβη οχήματος" : "Vehicle breakdown",
    note: el ? "Άλλη ενημέρωση" : "Other update",
    departure: el ? "Επιβεβαίωση αναχώρησης" : "Departure confirmation",
    completion: el ? "Επιβεβαίωση ολοκλήρωσης" : "Completion confirmation",
    resolution: el ? "Επίλυση" : "Resolution",
  })[kind];
