export interface Capabilities {
  capabilities: string[];
  timezone: string;
}
export interface Pattern {
  id: number;
  version: number;
  driver_id: number;
  weekday_mask: number;
  local_start: string;
  local_end: string;
  ends_next_day: boolean;
  valid_from: string;
  valid_until: string;
  status: string;
}
export interface Period {
  id: number;
  version: number;
  driver_id: number;
  kind: "available" | "unavailable";
  status: string;
  start_utc: string;
  end_utc: string | null;
  category?: string | null;
}
export interface DecisionOptions {
  member: boolean;
  external: { id: number; name: string }[];
}
export interface Leave {
  id: number;
  version: number;
  driver_id: number;
  state: "pending" | "approved" | "rejected" | "cancelled";
  start_utc: string;
  end_utc: string;
  decision_basis: string | null;
  stated_decision_maker: string | null;
  category?: string;
  private_note?: string | null;
  decision: DecisionOptions | null;
}
export interface VehiclePeriod {
  id: number;
  version: number;
  vehicle_id: number;
  kind: "planned_maintenance" | "out_of_service";
  status: "active" | "released" | "cancelled";
  start_utc: string;
  end_utc: string | null;
  estimated_end_utc: string | null;
  responsible_label: string | null;
  released_at: string | null;
}
export interface Grant {
  id: number;
  membership_id: number;
  capability: string;
  is_active: boolean;
  version: number;
}
export interface ApprovalRoute {
  id: number;
  driver_id: number | null;
  membership_id: number | null;
  external_contact_name: string | null;
  is_active: boolean;
  version: number;
}
export interface Member {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  driver_id: number | null;
}
export const OFFICE_CAPABILITIES = [
  "availability.manage",
  "maintenance.manage",
  "maintenance.release",
  "office.notes.read",
] as const;
