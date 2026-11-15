export type ApiFetch = (path: string, options?: RequestInit) => Promise<Response>;

export interface RuleLimit {
  rule_id: string;
  legal: number;
  value: number;
  direction: "max" | "min" | "fixed";
  source: string;
}
export interface WorkRulesView {
  legal_version: string;
  company_version: number;
  limits: RuleLimit[];
  warning_rules: string[];
  warning_catalogue: string[];
}
export interface WorkRulesBody {
  expected_version: number;
  overrides: Record<string, number>;
  warning_rules: string[];
}
export class WorkRulesError extends Error {
  constructor(
    readonly code: string,
    readonly ruleId: string | null,
  ) {
    super(code);
  }
}

export const getWorkRules = (apiFetch: ApiFetch) => recordCall<WorkRulesView>(apiFetch, "");
export const saveWorkRules = (apiFetch: ApiFetch, body: WorkRulesBody) =>
  recordCall<WorkRulesView>(apiFetch, "", { method: "PUT", body: JSON.stringify(body) });

export interface RouteOption {
  id: number;
  service_type: "intercity" | "urban";
  distance_km: number | null;
  origin: { code: string; name_el: string; name_en: string };
  destination: { code: string; name_el: string; name_en: string };
}
export interface DriverProfile {
  driver_id: number;
  version: number;
  overnight_allowed: boolean;
  split_shift_allowed: boolean;
  must_return_to_base: boolean;
  preferred_route_ids: number[];
  forbidden_route_ids: number[];
}
export interface DriverBaseline {
  driver_id: number;
  version: number;
  as_of: string | null;
  overtime_minutes: number;
  last_duty_end: string | null;
  last_weekly_rest_end: string | null;
  last_weekly_rest_at_base: boolean;
  owed_rest_minutes: number;
}
export interface DriverWeek {
  work_minutes: number;
  weekly_max: number;
  overtime_year_minutes: number;
  overtime_year_max: number;
  last_duty_end: string | null;
  last_weekly_rest: string | null;
}

export async function recordCall<T>(apiFetch: ApiFetch, path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`/api/v1/work-rules${path}`, options);
  } catch {
    throw new WorkRulesError("offline", null);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (response.ok) return body as T;
  const detail = (body as { detail?: { code?: string; rule_id?: string } } | null)?.detail;
  const object = typeof detail === "object" && detail ? detail : null;
  throw new WorkRulesError(object?.code ?? "failed", object?.rule_id ?? null);
}
export const put = <T,>(apiFetch: ApiFetch, path: string, body: object) =>
  recordCall<T>(apiFetch, path, { method: "PUT", body: JSON.stringify(body) });

export const routeName = (route: RouteOption, el: boolean) =>
  `${el ? route.origin.name_el : route.origin.name_en} → ${el ? route.destination.name_el : route.destination.name_en}`;

export const asClock = (minutes: number) => `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;

export function parseHours(text: string): number | null {
  const match = /^(\d+)(?::([0-5]\d))?$/.exec(text.trim());
  return match ? Number(match[1]) * 60 + Number(match[2] ?? 0) : null;
}

export const DEFAULT_TIMEZONE = "Europe/Athens";
const partsIn = (instant: Date, tz: string) => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).formatToParts(instant).map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
};
export const localDateTime = (iso: string | null, tz: string) => (iso ? partsIn(new Date(iso), tz) : "");
export const todayLocal = (tz: string) => partsIn(new Date(), tz).slice(0, 10);
export function toUtc(local: string, tz: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local);
  if (!match) return null;
  const wall = Date.UTC(+match[1]!, +match[2]! - 1, +match[3]!, +match[4]!, +match[5]!);
  let guess = wall;
  for (let i = 0; i < 2; i++) {
    const [d, t] = partsIn(new Date(guess), tz).split("T") as [string, string];
    const [y, mo, da] = d.split("-").map(Number) as [number, number, number];
    const [h, mi] = t.split(":").map(Number) as [number, number];
    guess += wall - Date.UTC(y, mo - 1, da, h, mi);
  }
  return new Date(guess).toISOString();
}
