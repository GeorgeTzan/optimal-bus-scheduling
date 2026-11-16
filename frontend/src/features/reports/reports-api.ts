export type ApiFetch = (path: string, options?: RequestInit) => Promise<Response>;
export type Status = "within" | "close" | "reached";
export type ExportFormat = "xlsx" | "pdf";

export interface CapRow {
  driver_id: number;
  code: string;
  name: string;
  active: boolean;
  used: number;
  planned: number;
  remaining: number;
  emergency: number;
  absolute_total: number;
  status: Status;
  history_complete: boolean;
  projection_month: string | null;
}
export interface MonthRow {
  driver_id: number;
  code: string;
  name: string;
  overtime: number;
  work: number;
  days: number;
  year_average: number | null;
}
export interface CoverageRow {
  line: string;
  stations: string[];
  names: [string | null, string | null][];
  scheduled: number;
  covered: number;
  uncovered: number;
  cancelled: number;
  rate: number | null;
  reasons: Record<string, number>;
}
export interface LineDay {
  date: string;
  direction: string;
  uncovered: string[];
  cancelled: { trip_code: string; reason: string | null }[];
  reason: string | null;
  note: string | null;
  published_by: string;
  context: { drivers_unavailable: number; vehicles_out: number } | null;
}
export interface MonthlyReport {
  month: string;
  timezone: string;
  overtime: {
    as_of: string;
    known_from: string;
    limit: number;
    absolute_limit: number;
    cap: CapRow[];
    monthly: MonthRow[];
    published_days: number;
  };
  coverage: CoverageRow[];
  last_export: { format: ExportFormat; generated_at: string; by: string } | null;
  changed_since_export: boolean;
}

export const LABELS = {
  statement: ["Προγραμματισμένα στοιχεία από δημοσιευμένα προγράμματα", "Planned figures from published schedules"],
  cap_heading: ["Υπερωρίες έναντι ετήσιου ορίου", "Overtime against the yearly limit"],
  month_heading: ["Σύγκριση μήνα", "Monthly comparison"],
  coverage_heading: ["Κάλυψη ανά γραμμή", "Coverage by line"],
  month: ["Μήνας", "Month"],
  code: ["Κωδικός", "Code"],
  driver: ["Οδηγός", "Driver"],
  inactive: ["Ανενεργός", "Inactive"],
  used: ["Χρησιμοποιημένες (ώ)", "Used (h)"],
  planned: ["Προγραμματισμένες (ώ)", "Planned (h)"],
  limit: ["Όριο (ώ)", "Limit (h)"],
  remaining: ["Υπόλοιπο (ώ)", "Remaining (h)"],
  emergency: ["Έκτακτες (ώ)", "Emergency (h)"],
  absolute_total: ["Απόλυτο σύνολο (ώ)", "Absolute total (h)"],
  absolute_limit: ["Απόλυτο όριο (ώ)", "Absolute limit (h)"],
  status: ["Κατάσταση", "Status"],
  within: ["Εντός ορίων", "Within limits"],
  close: ["Κοντά στο όριο", "Close"],
  reached: ["Συμπληρώθηκε", "Reached"],
  history: ["Ιστορικό", "History"],
  complete: ["Πλήρες", "Complete"],
  at_least: ["τουλάχιστον", "at least"],
  at_most: ["έως", "at most"],
  unknown_before: ["Άγνωστο ιστορικό πριν από", "History unknown before"],
  projection: ["Πρόβλεψη ορίου", "Limit projected"],
  overtime: ["Υπερωρίες (ώ)", "Overtime (h)"],
  work: ["Εργασία (ώ)", "Work (h)"],
  days: ["Ημέρες", "Days"],
  year_average: ["Μέσος όρος έτους (ώ)", "Year average (h)"],
  line: ["Γραμμή", "Line"],
  no_line: ["Χωρίς γραμμή", "No line"],
  scheduled: ["Προγραμματισμένα", "Scheduled"],
  covered: ["Καλυμμένα", "Covered"],
  uncovered: ["Ακάλυπτα", "Uncovered"],
  cancelled: ["Ακυρωμένα", "Cancelled"],
  rate: ["Κάλυψη (%)", "Coverage (%)"],
  reasons: ["Αιτίες", "Reasons"],
  affected_days: ["Ημέρες με ελλείψεις", "Affected days"],
  date: ["Ημερομηνία", "Date"],
  direction: ["Κατεύθυνση", "Direction"],
  reason: ["Αιτία", "Reason"],
  note: ["Σημείωση", "Note"],
  published_by: ["Δημοσίευση από", "Published by"],
  context: ["Πλαίσιο, όχι αιτία", "Context, not a cause"],
  drivers_unavailable: ["οδηγοί μη διαθέσιμοι", "drivers unavailable"],
  vehicles_out: ["οχήματα εκτός λειτουργίας", "vehicles out of service"],
  no_driver: ["Δεν υπήρχε διαθέσιμος οδηγός", "No driver available"],
  driver_leave: ["Άδεια ή ασθένεια οδηγού", "Driver leave or sickness"],
  no_vehicle: ["Δεν υπήρχε διαθέσιμο όχημα", "No vehicle available"],
  work_rules: ["Νόμιμο όριο ωρών εργασίας", "Legal working hours limit"],
  other: ["Άλλο", "Other"],
  unrecorded: ["Δεν καταγράφηκε αιτία", "No reason recorded"],
} satisfies Record<string, [string, string]>;
export type LabelKey = keyof typeof LABELS;

export class ReportsError extends Error {}

async function read<T>(apiFetch: ApiFetch, path: string, signal?: AbortSignal): Promise<T> {
  const response = await apiFetch(path, { signal });
  if (response.ok) return (await response.json()) as T;
  const body = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
  throw new ReportsError(body?.detail?.code ?? String(response.status));
}

export const fetchMonthly = (apiFetch: ApiFetch, month: string, signal?: AbortSignal) =>
  read<MonthlyReport>(apiFetch, `/api/v1/reports/monthly?month=${month}`, signal);

export const fetchLine = (apiFetch: ApiFetch, month: string, line: string, signal?: AbortSignal) =>
  read<LineDay[]>(apiFetch, `/api/v1/reports/coverage/line?month=${month}&line=${encodeURIComponent(line)}`, signal);

export const exportUrl = (month: string, format: ExportFormat, lang: "el" | "en") =>
  `/api/v1/reports/export?month=${month}&format=${format}&lang=${lang}`;
