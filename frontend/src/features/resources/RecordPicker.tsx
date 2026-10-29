"use client";
import { useEffect, useId, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import type { Resource } from "./ResourceWorkspace";
export function resourceLabel(row: Resource, kind: string, el: boolean) {
  const name =
    kind === "drivers"
      ? `${row.first_name ?? ""} ${row.last_name ?? ""}`.trim()
      : kind === "vehicles"
        ? row.registration_plate || row.code
        : (el ? row.name_el : row.name_en) || row.name_el;
  return `${name} · ${row.code}`;
}
export function RecordPicker({
  kind,
  label,
  value,
  onChange,
  onCreate,
  createLabel,
}: {
  kind: "drivers" | "vehicles" | "stations";
  label: string;
  value: Resource | null;
  onChange: (value: Resource | null) => void;
  onCreate?: (name: string) => void;
  createLabel?: string;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el",
    id = useId();
  const [text, setText] = useState(value ? resourceLabel(value, kind, el) : ""),
    [items, setItems] = useState<Resource[]>([]),
    [busy, setBusy] = useState(false),
    [failed, setFailed] = useState(false);
  useEffect(() => {
    if (value) setText(resourceLabel(value, kind, el));
  }, [value, kind, el]);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setFailed(false);
    const timer = setTimeout(() => {
      const query = text.includes(" · ")
        ? (text.split(" · ").at(-1) ?? text)
        : text;
      void apiFetch(
        `/api/v1/${kind}?active_only=true&page_size=25&q=${encodeURIComponent(query.slice(0, 160))}`,
        { signal: controller.signal },
      )
        .then(async (r) => {
          if (!r.ok) throw Error();
          const data = (await r.json()) as { items: Resource[] };
          setItems(data.items);
          const match = data.items.find(
            (row) => resourceLabel(row, kind, el) === text,
          );
          if (
            match &&
            (!value || value.id !== match.id || value.version !== match.version)
          )
            onChange(match);
        })
        .catch(() => {
          if (!controller.signal.aborted) setFailed(true);
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // A selected record is owned by the parent; only a deliberate input edit clears it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, kind, apiFetch, el]);
  return (
    <div className="resource-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        list={`${id}-options`}
        value={text}
        maxLength={400}
        autoComplete="off"
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          onChange(
            items.find((row) => resourceLabel(row, kind, el) === next) ?? null,
          );
        }}
      />
      <datalist id={`${id}-options`}>
        {items.map((row) => (
          <option key={row.id} value={resourceLabel(row, kind, el)} />
        ))}
      </datalist>
      {failed ? (
        <small role="alert">
          {el
            ? "Δεν φορτώθηκαν οι εγγραφές. Δοκιμάστε ξανά."
            : "Records could not load. Try typing again."}
        </small>
      ) : (
        !value &&
        text && (
          <small>
            {busy
              ? el
                ? "Αναζήτηση…"
                : "Searching…"
              : el
                ? "Επιλέξτε μια εγγραφή από τη λίστα."
                : "Choose a record from the suggestions."}
          </small>
        )
      )}
      {onCreate &&
        !value &&
        text.trim() &&
        !busy &&
        !failed &&
        !items.some((row) =>
          [row.name_el, row.name_en].includes(text.trim()),
        ) && (
          <button
            className="button secondary"
            type="button"
            onClick={() => onCreate(text.trim())}
          >
            {createLabel}
          </button>
        )}
    </div>
  );
}
