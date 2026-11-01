"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { resourceLabel } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import type { OfficeError } from "./office-api";

/** id -> readable label for drivers or vehicles, loaded page by page (bounded). */
export function useNames(kind: "drivers" | "vehicles") {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [names, setNames] = useState<Map<number, string>>(new Map());
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const next = new Map<number, string>();
      for (let page = 1; page <= 20; page++) {
        const response = await apiFetch(
          `/api/v1/${kind}?page=${page}&page_size=100`,
          { signal: controller.signal },
        );
        if (!response.ok) return;
        const data = (await response.json()) as { items: Resource[] };
        data.items.forEach((row) =>
          next.set(row.id, resourceLabel(row, kind, el)),
        );
        if (data.items.length < 100) break;
      }
      if (!controller.signal.aborted) setNames(next);
    })().catch(() => undefined);
    return () => controller.abort();
  }, [apiFetch, kind, el]);
  return names;
}

const foldKey: Record<string, string> = {
  start_local: "fold_start",
  end_local: "fold_end",
  estimated_end_local: "fold_estimate",
  released_at_local: "fold_released",
};
/** Offers the explicit earlier/later choice the server asks for when a clock time repeats. */
export function FoldPicker({
  error,
  folds,
  onChange,
}: {
  error: OfficeError | null;
  folds: Record<string, 0 | 1>;
  onChange: (key: string, value: 0 | 1) => void;
}) {
  const el = useI18n().locale === "el";
  if (error?.code !== "ambiguous_local_time") return null;
  return (
    <>
      {error.issues.map((issue) => {
        const key = foldKey[issue.field ?? ""] ?? "fold_start";
        return (
          <fieldset key={key} className="office-fold">
            <legend>
              {el
                ? `Η ώρα ${issue.clock_time ?? ""} επαναλαμβάνεται`
                : `The time ${issue.clock_time ?? ""} happens twice`}
            </legend>
            {([0, 1] as const).map((value) => (
              <label key={value}>
                <input
                  type="radio"
                  name={key}
                  checked={folds[key] === value}
                  onChange={() => onChange(key, value)}
                />
                {value === 0
                  ? el
                    ? "Η πρώτη φορά (θερινή ώρα)"
                    : "The first time (summer time)"
                  : el
                    ? "Η δεύτερη φορά (χειμερινή ώρα)"
                    : "The second time (winter time)"}
              </label>
            ))}
          </fieldset>
        );
      })}
    </>
  );
}

const tones: Record<string, [string, string, string, string]> = {
  pending: ["warning", "⏳", "Εκκρεμεί", "Pending"],
  approved: ["good", "✓", "Εγκρίθηκε", "Approved"],
  rejected: ["neutral", "✕", "Απορρίφθηκε", "Rejected"],
  cancelled: ["neutral", "⊘", "Ακυρώθηκε", "Cancelled"],
  active: ["warning", "●", "Ενεργό", "Active"],
  released: ["good", "✓", "Αποδεσμεύτηκε", "Released"],
  planned_maintenance: ["neutral", "▦", "Προγραμματισμένη συντήρηση", "Planned maintenance"],
  out_of_service: ["warning", "⚠", "Εκτός λειτουργίας", "Out of service"],
};
/** State is always text plus a symbol, never colour alone. */
export function StatePill({ state }: { state: string }) {
  const el = useI18n().locale === "el",
    tone = tones[state] ?? ["neutral", "•", state, state];
  return (
    <span className={`status-pill ${tone[0]}`}>
      <span aria-hidden="true">{tone[1]} </span>
      {el ? tone[2] : tone[3]}
    </span>
  );
}
