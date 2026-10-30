export type Entity =
  | "drivers"
  | "vehicles"
  | "stations"
  | "timetable"
  | "pairings"
  | "transfers"
  | "connections";
export type Destination = "drivers" | "fleet" | "timetables" | "planning";
export type Cell = string | number | boolean | null;
export interface Column {
  key: string;
  label: string;
  required: boolean;
  kind: string;
}
export interface Issue {
  code: string;
  message: string;
  sheet?: string;
  row?: number;
  field?: string;
  cell?: string;
  column?: string;
}
export interface Candidate {
  id: number;
  version: number;
  reference: string;
  label: string;
}
export interface ImportRow {
  row_id: number;
  entity: Entity;
  sheet: string;
  row: number;
  raw: Record<string, Cell>;
  values: Record<string, unknown>;
  action: "new" | "update" | "unchanged" | "invalid" | "resolve";
  proposed_ref: string | null;
  changed_fields: string[];
  before: Record<string, unknown>;
  proposed: Record<string, unknown>;
  issues: Issue[];
  candidates: Candidate[];
}
export interface Summary {
  new: number;
  updated: number;
  unchanged: number;
  invalid: number;
  needs_match: number;
  new_stations: number;
  will_archive: number;
  pairings_need_confirmation: number;
  by_entity: Partial<
    Record<Entity, { new: number; updated: number; unchanged: number }>
  >;
}
export interface Batch {
  batch_id: string;
  version: number;
  status: string;
  filename: string;
  row_count: number;
  summary: Summary;
  result: Summary | null;
  entities: Entity[];
  issues: Issue[];
  stations: { name: string; code?: string; name_el?: string }[];
  station_count: number;
  raw_available: boolean;
  expires_at: string;
  created_at?: string;
  rows: ImportRow[];
  rows_total: number;
  page: number;
  page_size: number;
  source_locale: "en" | "el";
}
export interface Capabilities {
  write_entities: Entity[];
  entities: Entity[];
  columns: Record<Entity, Column[]>;
  limits: { max_rows: number; max_upload_bytes: number };
}
export const entityNames: Record<Entity, [string, string]> = {
  drivers: ["Οδηγοί", "Drivers"],
  vehicles: ["Οχήματα", "Vehicles"],
  stations: ["Σταθμοί", "Stations"],
  timetable: ["Δρομολόγια", "Timetable"],
  pairings: ["Ζεύγη ημέρας", "Daily pairings"],
  transfers: ["Χρόνοι μετακίνησης", "Travel times"],
  connections: ["Συνδέσεις δρομολογίων", "Connections"],
};
export const destinations: Record<Entity, Destination> = {
  drivers: "drivers",
  vehicles: "fleet",
  stations: "timetables",
  timetable: "timetables",
  pairings: "planning",
  transfers: "planning",
  connections: "timetables",
};
export async function importResponse<T>(
  response: Response,
  el: boolean,
): Promise<T> {
  const data: unknown = await response.json();
  if (!response.ok) {
    const detail = (data as { detail?: { message?: string; code?: string } })
      .detail;
    if (response.status === 409)
      throw Error(
        el
          ? "Τα αποθηκευμένα στοιχεία άλλαξαν. Ανανεώστε την προεπισκόπηση και ελέγξτε ξανά."
          : "Saved records changed. Refresh the preview and review it again.",
      );
    if (response.status === 404)
      throw Error(
        el
          ? "Αυτή η εισαγωγή δεν είναι διαθέσιμη στον χώρο σας. Επιλέξτε νέο αρχείο ή μια πρόσφατη εισαγωγή."
          : "This upload is unavailable in your workspace. Choose a new file or a recent import.",
      );
    if (response.status === 410)
      throw Error(
        el
          ? "Το αντίγραφο του αρχείου έληξε. Τα αποθηκευμένα στοιχεία διατηρούνται. Ανεβάστε ξανά το αρχείο αν χρειάζεται."
          : "The source copy expired. Saved records remain. Upload the file again if needed.",
      );
    if (response.status === 403)
      throw Error(
        el
          ? "Ο ρόλος σας δεν επιτρέπει αυτή την ενέργεια. Ζητήστε βοήθεια από τον διαχειριστή σας."
          : "Your role cannot make this change. Ask your administrator for help.",
      );
    throw Error(
      !el && detail?.message
        ? detail.message
        : el
          ? "Δεν αποθηκεύτηκαν αλλαγές. Ελέγξτε το αρχείο και τα επισημασμένα πεδία."
          : "No changes were saved. Check the file and highlighted fields.",
    );
  }
  return data as T;
}

export function displayCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  )
    return String(value);
  if (Array.isArray(value)) return value.map(displayCell).join(", ");
  return "";
}

export function rowLabel(row: ImportRow): string {
  if (row.entity === "connections") return `${displayCell(row.values.incoming_ref)} → ${displayCell(row.values.outgoing_ref)}`;
  const person = [row.values.first_name, row.values.last_name]
    .map(displayCell)
    .filter(Boolean)
    .join(" ");
  return (
    person ||
    displayCell(
      row.values.registration_plate ??
        row.values.trip_code ??
        row.values.name_el ??
        row.proposed_ref ??
        row.raw.code ??
        row.sheet,
    )
  );
}
