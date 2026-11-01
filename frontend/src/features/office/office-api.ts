import { newRequestId } from "../navigation/request-id";
export interface Issue {
  code?: string;
  field?: string;
  date?: string;
  message?: string;
  clock_time?: string | null;
}
export class OfficeError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
    readonly issues: Issue[],
  ) {
    super(message);
  }
}
const messages: Record<string, [string, string]> = {
  approver_missing: [
    "Δεν έχει οριστεί υπεύθυνος έγκρισης για αυτόν τον οδηγό. Ρυθμίστε τον στην ενότητα Πρόσβαση.",
    "No approver is set for this driver. Set one under Access.",
  ],
  own_leave: [
    "Δεν μπορείτε να αποφασίσετε τη δική σας άδεια.",
    "You cannot decide your own leave.",
  ],
  not_approver: [
    "Δεν είστε υπεύθυνος έγκρισης για αυτόν τον οδηγό.",
    "You are not an approver for this driver.",
  ],
  not_pending: [
    "Το αίτημα έχει ήδη αποφασιστεί. Ανανεώστε τη λίστα.",
    "This request was already decided. Refresh the list.",
  ],
  version_conflict: [
    "Η εγγραφή άλλαξε από άλλον χρήστη. Ανανεώστε και ελέγξτε ξανά.",
    "Someone else changed this record. Refresh and review it again.",
  ],
  linked_to_leave: [
    "Αυτή η απουσία προέρχεται από άδεια. Ακυρώστε την άδεια για να την αλλάξετε.",
    "This absence comes from leave. Cancel the leave request to change it.",
  ],
  driver_archived: [
    "Ο οδηγός είναι αρχειοθετημένος.",
    "This driver is archived.",
  ],
  vehicle_archived: [
    "Το όχημα είναι αρχειοθετημένο.",
    "This vehicle is archived.",
  ],
  not_an_active_hold: [
    "Μόνο ενεργή ακινησία οχήματος μπορεί να αποδεσμευτεί.",
    "Only an active out-of-service period can be released.",
  ],
  invalid_release_time: [
    "Η αποδέσμευση πρέπει να είναι μετά την έναρξη και όχι στο μέλλον.",
    "The release must be after the start and not in the future.",
  ],
  ambiguous_local_time: [
    "Αυτή η ώρα επαναλαμβάνεται λόγω αλλαγής ώρας. Επιλέξτε ποια εμφάνιση εννοείτε.",
    "That clock time happens twice because of the clock change. Choose which one you mean.",
  ],
  nonexistent_local_time: [
    "Αυτή η ώρα δεν υπάρχει λόγω αλλαγής ώρας. Επιλέξτε άλλη ώρα.",
    "That clock time does not exist because of the clock change. Choose another time.",
  ],
  invalid_interval: [
    "Το τέλος πρέπει να είναι μετά την έναρξη.",
    "The end must be after the start.",
  ],
};
function explain(status: number, code: string | null, el: boolean) {
  const known = code ? messages[code] : undefined;
  if (known) return el ? known[0] : known[1];
  if (status === 403)
    return el
      ? "Ο οργανισμός δεν σας έχει δώσει αυτή την ενέργεια."
      : "Your organization has not granted you this action.";
  if (status === 409)
    return el
      ? "Η εγγραφή άλλαξε. Ανανεώστε και ελέγξτε ξανά."
      : "This record changed. Refresh and review it again.";
  if (status === 404)
    return el ? "Δεν βρέθηκε η εγγραφή." : "That record was not found.";
  return el
    ? "Ελέγξτε τα στοιχεία. Δεν αποθηκεύτηκε τίποτα."
    : "Check your entries. Nothing was saved.";
}
/** Calls the office API. Failures keep the server's code so forms can offer a repair (for example a clock-change choice). */
export async function officeCall<T>(
  apiFetch: (path: string, options?: RequestInit) => Promise<Response>,
  path: string,
  init: RequestInit | undefined,
  el: boolean,
): Promise<T> {
  const response = await apiFetch(`/api/v1/office${path}`, init);
  const data: unknown = await response.json().catch(() => null);
  if (response.ok) return data as T;
  const detail =
    data && typeof data === "object" && "detail" in data
      ? (data as { detail: unknown }).detail
      : null;
  const info =
    detail && typeof detail === "object"
      ? (detail as { code?: string; issues?: Issue[] })
      : {};
  const code = info.code ?? null;
  throw new OfficeError(
    explain(response.status, code, el),
    response.status,
    code,
    info.issues ?? [],
  );
}
export function post<T>(
  apiFetch: (path: string, options?: RequestInit) => Promise<Response>,
  path: string,
  body: object,
  requestId: string,
  el: boolean,
) {
  return officeCall<T>(
    apiFetch,
    path,
    { method: "POST", body: JSON.stringify({ request_id: requestId, ...body }) },
    el,
  );
}
export { newRequestId };
/** datetime-local gives YYYY-MM-DDTHH:mm; the API takes seconds. */
export const localTime = (value: string) =>
  value ? (value.length === 16 ? value + ":00" : value) : null;
export function monthRange(month: string) {
  const [year, number] = month.split("-").map(Number) as [number, number];
  const last = new Date(year, number, 0).getDate();
  return { from: `${month}-01`, to: `${month}-${String(last).padStart(2, "0")}` };
}
export function formatInstant(iso: string | null, zone: string, el: boolean) {
  if (!iso) return el ? "Ανοιχτό" : "Open";
  return new Intl.DateTimeFormat(el ? "el-GR" : "en-GB", {
    timeZone: zone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}
