import { newRequestId } from "../navigation/request-id";

export const ROLES = ["admin", "dispatcher", "fleet_manager", "management", "viewer"] as const;
export type Role = (typeof ROLES)[number] | "driver";
export interface TeamMember {
  id: number;
  user_id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  version: number;
  driver_id: number | null;
}
export interface Invitation {
  id: string;
  email: string;
  role: Role;
  driver_id: number | null;
  expires_at: string;
  expired: boolean;
  delivery_status: string | null;
}
/** Plain words and a one-line meaning for each role (kept in step with PERMISSIONS in backend identity/permissions.py). */
export const roleText: Record<Role, { name: [string, string]; meaning: [string, string] }> = {
  admin: { name: ["Διαχειριστής", "Administrator"], meaning: ["Διαχειρίζεται την πρόσβαση όλων και όλες τις ρυθμίσεις", "Manages everyone's access and all settings"] },
  dispatcher: { name: ["Δρομολογητής", "Dispatcher"], meaning: ["Σχεδιάζει, ελέγχει και δημοσιεύει προγράμματα", "Plans, checks and publishes schedules"] },
  fleet_manager: { name: ["Υπεύθυνος στόλου", "Fleet manager"], meaning: ["Διαχειρίζεται οχήματα και βλέπει προγράμματα", "Manages vehicles and reads schedules"] },
  management: { name: ["Διοίκηση", "Management"], meaning: ["Βλέπει προγράμματα και αναφορές", "Reads schedules and reports"] },
  viewer: { name: ["Προβολή", "Viewer"], meaning: ["Βλέπει μόνο προγράμματα", "Reads schedules only"] },
  driver: { name: ["Οδηγός", "Driver"], meaning: ["Βλέπει τις δικές του υπηρεσίες και ζητά άδεια", "Sees their own duties and requests leave"] },
};
const messages: Record<string, [string, string]> = {
  own_membership: ["Δεν μπορείτε να αλλάξετε τον δικό σας ρόλο ή την κατάστασή σας. Ζητήστε από άλλον διαχειριστή.", "You cannot change your own role or status. Ask another administrator."],
  driver_needs_record: ["Η σύνδεση οδηγού δημιουργείται με πρόσκληση από την εγγραφή του οδηγού.", "A driver sign-in is created by inviting from the driver record."],
  member_exists: ["Αυτό το άτομο είναι ήδη στην ομάδα σας. Ενεργοποιήστε το ξανά ή αλλάξτε τον ρόλο του.", "This person is already in your team. Reactivate them or change their role instead."],
  request_changed: ["Το αίτημα χρησιμοποιήθηκε ήδη με άλλα στοιχεία. Δοκιμάστε ξανά.", "This request was already used with different details. Try again."],
  driver_already_linked: ["Ο οδηγός έχει ήδη συνδεδεμένο λογαριασμό.", "This driver already has a linked sign-in."],
  driver_archived: ["Ο οδηγός είναι αρχειοθετημένος.", "This driver is archived."],
};
export class TeamError extends Error {}

/** One call to the identity API. Failures are specific; nothing reports success without a 2xx. */
export async function teamCall<T>(
  apiFetch: (path: string, options?: RequestInit) => Promise<Response>,
  path: string,
  options: RequestInit | undefined,
  el: boolean,
): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`/api/v1/identity${path}`, options);
  } catch (failure) {
    if (failure instanceof DOMException && failure.name === "AbortError") throw failure;
    throw new TeamError(el ? "Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα." : "No connection. Nothing was saved.");
  }
  let body: unknown = null;
  try { body = await response.json(); } catch { /* empty body */ }
  if (response.ok) return body as T;
  const detail = (body as { detail?: unknown } | null)?.detail;
  const code = typeof detail === "object" && detail !== null ? ((detail as { code?: string }).code ?? null) : null;
  const text = code && messages[code] ? messages[code][el ? 0 : 1] : typeof detail === "string" ? detail : typeof detail === "object" && detail !== null ? ((detail as { message?: string }).message ?? null) : null;
  throw new TeamError(text ?? (el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed."));
}
export const requestId = newRequestId;

export function deliveryText(status: string | null, el: boolean): string {
  switch (status) {
    case "not_configured": return el ? "Στήθηκε στην ουρά. Δεν έχει σταλεί email επειδή η αποστολή δεν έχει ρυθμιστεί." : "Queued. No email has been sent because email delivery is not set up.";
    case "queued": case "delivering": return el ? "Το email είναι στην ουρά αποστολής." : "Email is queued for sending.";
    case "sent": return el ? "Το email στάλθηκε (το δέχτηκε ο διακομιστής αλληλογραφίας· δεν είναι απόδειξη παραλαβής)." : "Email sent (accepted by the mail server, not a delivery receipt).";
    case "failed": return el ? "Η αποστολή απέτυχε. Ελέγξτε τις ρυθμίσεις email." : "Sending failed. Check the email settings.";
    case "discarded": return el ? "Αντικαταστάθηκε." : "Replaced.";
    default: return "";
  }
}
