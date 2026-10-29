"use client";
import {
  useEffect,
  useRef,
  useId,
  isValidElement,
  cloneElement,
  type ReactNode,
  type ReactElement,
} from "react";
import { X } from "lucide-react";
import { useI18n } from "../../i18n/context";
import type { Resource } from "../resources/ResourceWorkspace";
export interface Timetable {
  id: number;
  version: number;
  trip_code: string;
  origin: Resource;
  destination: Resource;
  departure_time: string;
  arrival_time: string;
  arrival_day_offset: number;
  operating_weekdays: number[] | null;
  valid_from: string | null;
  valid_until: string | null;
  allowed_bus_types: string[] | null;
  distance_km: number | null;
  is_active: boolean;
  calendar_ready: boolean;
}
export const weekdays = [
  ["Δευτέρα", "Monday"],
  ["Τρίτη", "Tuesday"],
  ["Τετάρτη", "Wednesday"],
  ["Πέμπτη", "Thursday"],
  ["Παρασκευή", "Friday"],
  ["Σάββατο", "Saturday"],
  ["Κυριακή", "Sunday"],
];
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="resource-field">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children)
        ? cloneElement(children as ReactElement<{ id: string }>, { id })
        : children}
    </div>
  );
}
export function Modal({
  title,
  subtitle,
  onClose,
  busy,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  busy?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    { locale } = useI18n();
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="resource-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      aria-label={title}
    >
      <header>
        <div>
          <span className="resource-eyebrow">{subtitle}</span>
          <h2>{title}</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          disabled={busy}
          onClick={onClose}
          aria-label={locale === "el" ? "Κλείσιμο" : "Close"}
        >
          <X size={19} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export async function checked<T>(response: Response, el: boolean): Promise<T> {
  const data: unknown = await response.json();
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data ? data.detail : null;
    const code =
      detail && typeof detail === "object" && "code" in detail
        ? detail.code
        : null;
    throw Error(
      response.status === 409
        ? el
          ? "Τα στοιχεία άλλαξαν. Ανανεώστε τη λίστα και ελέγξτε ξανά."
          : "These records changed. Refresh the list and review them again."
        : response.status === 403
          ? el
            ? "Ο ρόλος σας δεν επιτρέπει αυτή την αλλαγή."
            : "Your role does not permit this change."
          : code === "duplicate_pairing"
            ? el
              ? "Ο οδηγός ή το όχημα έχει ήδη επιλεγεί."
              : "This driver or vehicle is already paired."
            : el
              ? "Ελέγξτε τα στοιχεία. Δεν αποθηκεύτηκαν αλλαγές."
              : "Check your entries. No changes were saved.",
    );
  }
  return data as T;
}
export function stationName(row: Resource, el: boolean) {
  return (el ? row.name_el : row.name_en) || row.name_el || row.code;
}
