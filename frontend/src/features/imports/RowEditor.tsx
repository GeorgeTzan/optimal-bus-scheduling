"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useI18n } from "../../i18n/context";
import { Field, Modal } from "../timetables/shared";
import { RecordPicker } from "../resources/RecordPicker";
import type { Resource } from "../resources/ResourceWorkspace";
import {
  displayCell,
  type Cell,
  type Column,
  type ImportRow,
} from "./contracts";

export function RowEditor({
  row,
  columns,
  busy,
  error,
  onSave,
  onClose,
}: {
  row: ImportRow;
  columns: Column[];
  busy: boolean;
  error: string | null;
  onSave: (
    values: Record<string, Cell>,
    resolution?: Record<string, unknown>,
    stations?: Record<string, unknown>[],
  ) => Promise<void>;
  onClose: () => void;
}) {
  const { locale } = useI18n(),
    el = locale === "el";
  const [edits, setEdits] = useState<Record<string, Cell>>({});
  const [mode, setMode] = useState<"" | "new" | "existing">("");
  const [person, setPerson] = useState<Resource | null>(null);
  const [station, setStation] = useState<Resource | null>(null);
  const [stationField, setStationField] = useState("");
  const matchable = ["drivers", "vehicles", "stations"].includes(row.entity);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const target =
        form.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ??
        form.current?.querySelector<HTMLElement>(
          row.action === "resolve" ? ".import-match input" : "input, select",
        );
      target?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [row.action]);
  const text = (column: Column) =>
    String(
      edits[column.key] !== undefined
        ? (edits[column.key] ?? "")
        : (row.raw[column.key] ?? ""),
    );
  const fields = (items: Column[]) =>
    items.map((column) => (
      <Field key={column.key} label={column.label}>
        {column.kind === "boolean" ? (
          <select
            value={displayCell(
              edits[column.key] !== undefined
                ? (edits[column.key] ?? "")
                : (row.values[column.key] ?? ""),
            )}
            onChange={(e) =>
              setEdits({
                ...edits,
                [column.key]:
                  e.target.value === "" ? null : e.target.value === "true",
              })
            }
          >
            <option value="">
              {el ? "Χωρίς αλλαγή" : "Keep existing value"}
            </option>
            <option value="true">{el ? "Ναι" : "Yes"}</option>
            <option value="false">{el ? "Όχι" : "No"}</option>
          </select>
        ) : (
          <input
            value={text(column)}
            maxLength={512}
            onChange={(e) =>
              setEdits({ ...edits, [column.key]: e.target.value })
            }
            aria-invalid={
              row.issues.some((issue) => issue.field === column.key) ||
              undefined
            }
          />
        )}
      </Field>
    ));
  async function submit(event: FormEvent) {
    event.preventDefault();
    const resolution =
      mode === "new"
        ? { mode }
        : mode === "existing" && person
          ? { mode, target_id: person.id, target_version: person.version }
          : undefined;
    const stations =
      station && stationField
        ? [
            {
              name: String(row.raw[stationField]),
              mode: "existing",
              target_id: station.id,
              target_version: station.version,
            },
          ]
        : undefined;
    await onSave(edits, resolution, stations);
  }
  return (
    <Modal
      title={el ? `Έλεγχος γραμμής ${row.row}` : `Review row ${row.row}`}
      subtitle={`${row.sheet} · ${row.proposed_ref ?? ""}`}
      busy={busy}
      onClose={onClose}
    >
      <form ref={form} onSubmit={(e) => void submit(e)}>
        {!!row.issues.length && (
          <div className="import-issues">
            {row.issues.map((issue, i) => (
              <p key={i}>
                <strong>{issue.cell ?? issue.column}</strong> {issue.message}
              </p>
            ))}
          </div>
        )}
        <p className="resource-help">
          {el
            ? "Οι διορθώσεις ελέγχονται πριν αποθηκευτούν στο μητρώο σας. Τα κενά προαιρετικά πεδία διατηρούν τις υπάρχουσες τιμές."
            : "Corrections are checked before saving to your register. Blank optional fields preserve existing values."}
        </p>
        {row.changed_fields.length > 0 && (
          <div className="import-differences">
            <h3>{el ? "Τι θα αλλάξει" : "What will change"}</h3>
            {row.changed_fields
              .filter((key) => !key.endsWith("_id"))
              .map((key) => (
                <p key={key}>
                  <strong>
                    {columns.find((column) => column.key === key)?.label ?? key}
                  </strong>
                  <span>{displayCell(row.before[key] ?? "—")}</span>
                  <span aria-hidden="true">→</span>
                  <span>{displayCell(row.proposed[key] ?? "—")}</span>
                </p>
              ))}
          </div>
        )}
        <div className="resource-form-grid">
          {fields(columns.filter((column) => column.required))}
        </div>
        <details
          open={
            row.issues.some(
              (issue) =>
                !columns.find((column) => column.key === issue.field)?.required,
            ) || undefined
          }
        >
          <summary>
            {el
              ? "Κωδικός και πρόσθετα στοιχεία"
              : "Reference and additional details"}
          </summary>
          <div className="resource-form-grid">
            {fields(columns.filter((column) => !column.required))}
          </div>
        </details>
        {matchable && (
          <fieldset className="import-match">
            <legend>
              {el
                ? "Σε ποια εγγραφή αντιστοιχεί;"
                : "Which record does this belong to?"}
            </legend>
            <label>
              <input
                type="radio"
                name="match"
                checked={mode === ""}
                onChange={() => setMode("")}
              />
              {el ? "Διατήρηση αντιστοίχισης" : "Keep current matching"}
            </label>
            <label>
              <input
                type="radio"
                name="match"
                checked={mode === "new"}
                onChange={() => setMode("new")}
              />
              {el ? "Προσθήκη νέας εγγραφής" : "Add a new record"}
            </label>
            <label>
              <input
                type="radio"
                name="match"
                checked={mode === "existing"}
                onChange={() => setMode("existing")}
              />
              {el ? "Αντιστοίχιση με υπάρχουσα" : "Match an existing record"}
            </label>
            {!!row.candidates.length && (
              <p className="resource-help">
                {el ? "Πιθανές αντιστοιχίσεις: " : "Possible matches: "}
                {row.candidates
                  .map((item) => `${item.label} · ${item.reference}`)
                  .join(", ")}
              </p>
            )}
            {mode === "existing" && (
              <RecordPicker
                kind={row.entity as "drivers" | "vehicles" | "stations"}
                label={el ? "Αναζήτηση εγγραφής" : "Find existing record"}
                value={person}
                onChange={setPerson}
              />
            )}
          </fieldset>
        )}
        {row.issues.some(
          (issue) =>
            issue.code.startsWith("station_") ||
            issue.code === "ambiguous_station",
        ) && (
          <details open>
            <summary>{el ? "Αντιστοίχιση σταθμού" : "Resolve station"}</summary>
            <Field label={el ? "Πεδίο σταθμού" : "Station field"}>
              <select
                value={stationField}
                onChange={(e) => setStationField(e.target.value)}
              >
                <option value="">{el ? "Επιλέξτε" : "Choose"}</option>
                {columns
                  .filter(
                    (column) =>
                      ["origin", "destination", "home_station"].includes(
                        column.key,
                      ) && row.raw[column.key],
                  )
                  .map((column) => (
                    <option key={column.key} value={column.key}>
                      {column.label}: {String(row.raw[column.key])}
                    </option>
                  ))}
              </select>
            </Field>
            <RecordPicker
              kind="stations"
              label={el ? "Αποθηκευμένος σταθμός" : "Saved station"}
              value={station}
              onChange={setStation}
            />
          </details>
        )}
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <footer>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={onClose}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button
            className="button primary"
            disabled={
              busy ||
              (mode === "existing" && !person) ||
              (!Object.keys(edits).length && !mode && !station)
            }
          >
            {busy
              ? el
                ? "Έλεγχος…"
                : "Checking…"
              : el
                ? "Αποθήκευση διόρθωσης"
                : "Save correction"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
