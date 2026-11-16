import { supportCodeMessages } from "../auth/support-codes";
export type CustomerStatus = "trial" | "active" | "suspended" | "cancelled";
export const STATUSES: CustomerStatus[] = [
  "trial",
  "active",
  "suspended",
  "cancelled",
];
export interface Health {
  tenant_id: number;
  last_sign_in: string | null;
  drivers: number;
  vehicles: number;
  timetables: number;
  published_days_30d: number;
  solver_failed_7d: number;
  mail_failed_7d: number;
  uncovered_share_latest: number | null;
}
export interface Customer {
  id: number;
  name: string;
  region: string | null;
  status: CustomerStatus;
  trial_ends_on: string | null;
  plan_note: string | null;
  created_at: string | null;
  health: Health | null;
}
export interface Operator {
  id: number;
  email: string;
}
export const statusText: Record<CustomerStatus, [string, string]> = {
  trial: ["Δοκιμή", "Trial"],
  active: ["Ενεργός", "Active"],
  suspended: ["Σε αναστολή", "Suspended"],
  cancelled: ["Ακυρωμένος", "Cancelled"],
};
const messages: Record<string, [string, string]> = {
  "Sign in to continue": [
    "Συνδεθείτε για να συνεχίσετε.",
    "Sign in to continue.",
  ],
  "The email, password or code is incorrect. Please try again.": [
    "Το email, ο κωδικός ή ο κωδικός επαλήθευσης δεν είναι σωστός. Δοκιμάστε ξανά.",
    "The email, password or code is incorrect. Please try again.",
  ],
  "Too many sign-in attempts. Please wait and try again.": [
    "Πολλές προσπάθειες σύνδεσης. Περιμένετε λίγα λεπτά και δοκιμάστε ξανά.",
    "Too many sign-in attempts. Wait a few minutes and try again.",
  ],
  "This action could not be verified. Refresh the page and try again.": [
    "Η ενέργεια δεν επαληθεύτηκε. Ανανεώστε τη σελίδα και δοκιμάστε ξανά.",
    "This action could not be verified. Refresh the page and try again.",
  ],
  "An organization with this name already exists": [
    "Υπάρχει ήδη οργανισμός με αυτό το όνομα.",
    "An organization with this name already exists.",
  ],
  "Unknown time zone": ["Άγνωστη ζώνη ώρας.", "Unknown time zone."],
  "Customer not found": ["Ο πελάτης δεν βρέθηκε.", "Customer not found."],
  "A reason is required": ["Γράψτε την αιτία.", "Enter a reason."],
  ...supportCodeMessages,
  organization_suspended: [
    "Ο πελάτης είναι σε αναστολή.",
    "This customer is suspended.",
  ],
};
const fallback: [string, string] = [
  "Η ενέργεια δεν ολοκληρώθηκε. Δοκιμάστε ξανά.",
  "The action did not complete. Please try again.",
];
const offline: [string, string] = [
  "Δεν μπορέσαμε να συνδεθούμε. Ελέγξτε τη σύνδεσή σας και δοκιμάστε ξανά.",
  "We could not connect. Check your connection and try again.",
];

export class PlatformError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function csrfToken() {
  const value = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("ktel_platform_csrf="))
    ?.split("=")
    .slice(1)
    .join("=");
  return value ? decodeURIComponent(value) : "";
}

export async function platformCall<T>(
  path: string,
  el: boolean,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes((options.method ?? "GET").toUpperCase()))
    headers.set("X-CSRF-Token", csrfToken());
  let response: Response;
  try {
    response = await fetch(`/api/v1/platform${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new PlatformError(offline[el ? 0 : 1], 0);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail = body?.detail;
    const key =
      typeof detail === "string"
        ? detail
        : (detail as { code?: string } | null | undefined)?.code;
    const known = key ? messages[key] : undefined;
    throw new PlatformError((known ?? fallback)[el ? 0 : 1], response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function trialEnded(
  customer: Customer,
  today = new Date().toISOString().slice(0, 10),
) {
  return (
    customer.status === "trial" &&
    !!customer.trial_ends_on &&
    customer.trial_ends_on < today
  );
}

const DAY = 86_400_000;
export const UNCOVERED_ALERT_SHARE = 0.25;
export const INACTIVE_DAYS = 14;

export function healthFlags(health: Health | null, now = Date.now()) {
  if (!health) return { failing: [], inactive: false };
  const failing: ("solver" | "mail" | "uncovered")[] = [];
  if (health.solver_failed_7d > 0) failing.push("solver");
  if (health.mail_failed_7d > 0) failing.push("mail");
  if ((health.uncovered_share_latest ?? 0) > UNCOVERED_ALERT_SHARE)
    failing.push("uncovered");
  const inactive =
    !health.last_sign_in ||
    now - new Date(health.last_sign_in).getTime() > INACTIVE_DAYS * DAY;
  return { failing, inactive };
}

export interface SupportState {
  access_until: string | null;
  access_open: boolean;
  session: { ends_at: string } | null;
}
export interface SupportStarted {
  redirect: string;
  ends_at: string;
  mail_status: string;
}
