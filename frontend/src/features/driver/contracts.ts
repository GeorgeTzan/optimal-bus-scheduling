export interface Station {
  code: string;
  name_el: string;
  name_en: string;
}
export interface Duty {
  trip_id: string;
  trip_code: string | null;
  start_utc: string;
  end_utc: string;
  origin: Station | null;
  destination: Station | null;
  vehicle_label: string | null;
  cancelled: boolean;
  acknowledged: boolean;
}
export interface DutyDay {
  service_date: string;
  publication_id: string;
  revision_version: number;
  duties: Duty[];
}
export interface DutiesResponse {
  timezone: string;
  days: DutyDay[];
}
export interface DriverMe {
  driver_name: string;
  driver_code: string;
  timezone: string;
}
export interface LeaveItem {
  id: number;
  version: number;
  state: "pending" | "approved" | "rejected" | "cancelled";
  start_utc: string;
  end_utc: string;
  category?: string;
  private_note?: string | null;
  decision_note?: string | null;
}
