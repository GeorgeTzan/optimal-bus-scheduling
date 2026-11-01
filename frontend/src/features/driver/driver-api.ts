import { newRequestId } from "../navigation/request-id";

export class DriverError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}
const known: Record<string, [string, string]> = {
  driver_not_linked: [
    "Ο λογαριασμός σας δεν έχει συνδεθεί ακόμη με εγγραφή οδηγού. Ζητήστε από το γραφείο να τον συνδέσει.",
    "Your sign-in is not linked to a driver record yet. Ask the office to link it.",
  ],
  driver_archived: [
    "Η εγγραφή οδηγού σας είναι αρχειοθετημένη. Επικοινωνήστε με το γραφείο.",
    "Your driver record is archived. Contact the office.",
  ],
  publication_replaced: [
    "Το πρόγραμμα άλλαξε ή δεν ισχύει πια. Φορτώθηκαν οι τρέχουσες υπηρεσίες· ελέγξτε και επιβεβαιώστε ξανά.",
    "The schedule changed or is no longer current. The current duties were reloaded; review and acknowledge again.",
  ],
  not_your_duty: ["Αυτή η υπηρεσία δεν είναι δική σας.", "That duty is not yours."],
  not_cancellable: [
    "Μόνο αίτημα που εκκρεμεί μπορεί να ακυρωθεί εδώ. Ρωτήστε το γραφείο.",
    "Only a request that is still waiting can be cancelled here. Ask the office.",
  ],
  version_conflict: [
    "Το αίτημα άλλαξε. Ανανεώστε και δοκιμάστε ξανά.",
    "This request changed. Reload and try again.",
  ],
  request_changed: [
    "Αυτό το αίτημα χρησιμοποιήθηκε ήδη με άλλα στοιχεία. Δοκιμάστε ξανά.",
    "This request was already used with different details. Try again.",
  ],
};
export const requestId = newRequestId;

/** One call to the driver API. An offline browser, an expired session and a refusal each get an honest, specific message; nothing reports success without a 2xx. */
export async function driverCall<T>(
  apiFetch: (path: string, options?: RequestInit) => Promise<Response>,
  path: string,
  options: RequestInit | undefined,
  el: boolean,
): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(path, options);
  } catch (failure) {
    if (failure instanceof DOMException && failure.name === "AbortError") throw failure;
    throw new DriverError(el ? "Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα." : "No connection. Nothing was saved.", 0, "offline");
  }
  let body: unknown = null;
  try { body = await response.json(); } catch { /* an empty or non-JSON body */ }
  if (response.ok) return body as T;
  const detail = (body as { detail?: unknown } | null)?.detail;
  const code = typeof detail === "object" && detail !== null ? ((detail as { code?: string }).code ?? null) : null;
  const text = code && known[code] ? known[code][el ? 0 : 1] : typeof detail === "string" ? detail : typeof detail === "object" && detail !== null ? ((detail as { message?: string }).message ?? null) : null;
  throw new DriverError(text ?? (el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed."), response.status, code);
}
