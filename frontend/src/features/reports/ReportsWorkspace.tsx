"use client";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  LABELS,
  ReportsError,
  exportUrl,
  fetchLine,
  fetchMonthly,
  type ExportFormat,
  type LabelKey,
  type LineDay,
  type MonthlyReport,
} from "./reports-api";

const pad = (value: number) => String(value).padStart(2, "0");
function monthBefore(today: Date, back: number) {
  const day = new Date(today.getFullYear(), today.getMonth() - back, 1);
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}`;
}

export function ReportsWorkspace({ el }: { el: boolean }) {
  const { apiFetch, user } = useAuth();
  const canExport = user?.role !== "support";
  const lang = el ? 0 : 1,
    locale = el ? "el-GR" : "en-GB";
  const t = (key: LabelKey) => LABELS[key][lang];
  const [month, setMonth] = useState(() => monthBefore(new Date(), 1)),
    [loaded, setLoaded] = useState<MonthlyReport | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState<ExportFormat | null>(null),
    [lines, setLines] = useState<
      Record<string, LineDay[] | "loading" | "failed">
    >({}),
    chosen = useRef(month);
  const report = loaded?.month === month ? loaded : null;

  const failure = useCallback(
    (problem: unknown) =>
      problem instanceof ReportsError &&
      problem.message === "month_out_of_range"
        ? el
          ? "Ο μήνας είναι εκτός της περιόδου αναφορών."
          : "This month is outside the reporting period."
        : el
          ? "Η αναφορά δεν φορτώθηκε. Δοκιμάστε ξανά."
          : "The report could not be loaded. Try again.",
    [el],
  );
  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const fresh = await fetchMonthly(apiFetch, month, signal);
        if (signal?.aborted || chosen.current !== month) return;
        setLoaded(fresh);
        setError("");
      } catch (problem) {
        if (signal?.aborted || chosen.current !== month) return;
        setLoaded(null);
        setError(failure(problem));
      }
    },
    [apiFetch, month, failure],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function download(format: ExportFormat) {
    setBusy(format);
    setError("");
    try {
      const response = await apiFetch(
        exportUrl(month, format, el ? "el" : "en"),
      );
      if (!response.ok) throw new ReportsError(String(response.status));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `reports-${month}.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      await load();
    } catch {
      if (chosen.current === month)
        setError(
          el
            ? "Το αρχείο δεν δημιουργήθηκε. Δοκιμάστε ξανά."
            : "The file could not be created. Try again.",
        );
    } finally {
      setBusy(null);
    }
  }
  async function toggle(line: string) {
    const key = `${month}|${line}`;
    if (lines[key]) {
      setLines(({ [key]: _closed, ...rest }) => rest);
      return;
    }
    setLines((current) => ({ ...current, [key]: "loading" }));
    try {
      const days = await fetchLine(apiFetch, month, line);
      setLines((current) =>
        current[key] ? { ...current, [key]: days } : current,
      );
    } catch {
      setLines((current) =>
        current[key] ? { ...current, [key]: "failed" } : current,
      );
    }
  }

  const number = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const hours = (minutes: number | null) =>
    minutes === null ? "—" : number.format(minutes / 60);
  const monthName = (value: string) =>
    new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(
      new Date(`${value}-01T12:00:00`),
    );
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(`${value}T12:00:00`));
  const moment = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: report?.timezone,
    }).format(new Date(value));
  const reason = (key: string) => (key in LABELS ? t(key as LabelKey) : key);

  const overtime = report?.overtime;
  const widest = Math.max(
    1,
    ...(overtime?.monthly ?? []).map((row) => row.overtime),
  );
  const empty = el
    ? `Δεν υπάρχουν δημοσιευμένες ημέρες τον ${monthName(month).replace("ς ", " ")}`
    : `There are no published days in ${monthName(month)}`;

  return (
    <section
      className="resource-workspace office-workspace reports-workspace"
      aria-labelledby="reports-heading"
    >
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΔΙΟΙΚΗΣΗ" : "MANAGEMENT"}
          </span>
          <h1 id="reports-heading">{el ? "Αναφορές" : "Reports"}</h1>
          <p>
            {t("statement")}
            {report ? `, ${report.timezone}` : ""}
          </p>
        </div>
        <div className="resource-heading-actions">
          <label className="office-month">
            {t("month")}
            <input
              type="month"
              value={month}
              max={monthBefore(new Date(), 0)}
              onChange={(event) => {
                if (!event.target.value) return;
                chosen.current = event.target.value;
                setError("");
                setMonth(event.target.value);
              }}
            />
          </label>
          {canExport && (
            <>
              <button
                className="button secondary"
                disabled={busy !== null || !report}
                onClick={() => void download("xlsx")}
              >
                Excel
              </button>
              <button
                className="button secondary"
                disabled={busy !== null || !report}
                onClick={() => void download("pdf")}
              >
                PDF
              </button>
            </>
          )}
        </div>
      </header>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {!report && !error && <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p>}
      {report?.last_export && (
        <p
          className={
            report.changed_since_export ? "reports-changed" : "driver-muted"
          }
          role={report.changed_since_export ? "status" : undefined}
        >
          {report.changed_since_export
            ? el
              ? `Τα στοιχεία άλλαξαν μετά την τελευταία εξαγωγή στις ${moment(report.last_export.generated_at)}. `
              : `The figures changed since the last export on ${moment(report.last_export.generated_at)}. `
            : ""}
          {el ? "Τελευταία εξαγωγή" : "Last export"}:{" "}
          {report.last_export.format === "xlsx" ? "Excel" : "PDF"},{" "}
          {moment(report.last_export.generated_at)}, {report.last_export.by}
        </p>
      )}
      {overtime && overtime.cap.length > 0 && (
        <section className="office-panel" aria-labelledby="reports-cap">
          <h2 id="reports-cap">{t("cap_heading")}</h2>
          <p className="driver-muted">
            {el ? "Έως" : "As of"} {date(overtime.as_of)} · {t("limit")}:{" "}
            {hours(overtime.limit)} · {t("absolute_limit")}:{" "}
            {hours(overtime.absolute_limit)}
          </p>
          <div className="resource-table-scroll">
            <table className="resource-table team-table">
              <thead>
                <tr>
                  <th>{t("driver")}</th>
                  <th>{t("used")}</th>
                  <th>{t("planned")}</th>
                  <th>{t("remaining")}</th>
                  <th>{t("emergency")}</th>
                  <th>{t("absolute_total")}</th>
                  <th>{t("status")}</th>
                  <th>{t("history")}</th>
                  <th>{t("projection")}</th>
                </tr>
              </thead>
              <tbody>
                {overtime.cap.map((row) => {
                  const total = (minutes: number) =>
                    row.history_complete
                      ? hours(minutes)
                      : `${t("at_least")} ${hours(minutes)}`;
                  return (
                    <tr key={row.driver_id}>
                      <td className="team-name">
                        {row.code} · {row.name}
                        {row.active ? "" : ` (${t("inactive")})`}
                      </td>
                      <td data-label={t("used")}>{total(row.used)}</td>
                      <td data-label={t("planned")}>{hours(row.planned)}</td>
                      <td data-label={t("remaining")}>
                        {row.history_complete
                          ? hours(row.remaining)
                          : `${t("at_most")} ${hours(row.remaining)}`}
                      </td>
                      <td data-label={t("emergency")}>
                        {hours(row.emergency)}
                      </td>
                      <td data-label={t("absolute_total")}>
                        {total(row.absolute_total)}
                      </td>
                      <td data-label={t("status")}>
                        <span className={`reports-status ${row.status}`}>
                          {t(row.status)}
                        </span>
                      </td>
                      <td data-label={t("history")}>
                        {row.history_complete
                          ? t("complete")
                          : `${t("unknown_before")} ${date(overtime.known_from)}`}
                      </td>
                      <td data-label={t("projection")}>
                        {row.projection_month
                          ? monthName(row.projection_month)
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {overtime?.published_days === 0 && (
        <p className="office-empty">{empty}</p>
      )}
      {report && overtime && overtime.published_days > 0 ? (
        <>
          <section className="office-panel" aria-labelledby="reports-month">
            <h2 id="reports-month">{t("month_heading")}</h2>
            <div className="resource-table-scroll">
              <table className="resource-table team-table">
                <thead>
                  <tr>
                    <th>{t("driver")}</th>
                    <th>{t("overtime")}</th>
                    <th>{t("work")}</th>
                    <th>{t("days")}</th>
                    <th>{t("year_average")}</th>
                  </tr>
                </thead>
                <tbody>
                  {overtime.monthly.map((row) => (
                    <tr key={row.driver_id}>
                      <td className="team-name">
                        {row.code} · {row.name}
                      </td>
                      <td data-label={t("overtime")}>
                        <span className="reports-bar">
                          <span>{hours(row.overtime)}</span>
                          <i
                            style={{
                              width: `${(row.overtime / widest) * 100}%`,
                            }}
                          />
                        </span>
                      </td>
                      <td data-label={t("work")}>{hours(row.work)}</td>
                      <td data-label={t("days")}>{row.days}</td>
                      <td data-label={t("year_average")}>
                        {hours(row.year_average)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="office-panel" aria-labelledby="reports-coverage">
            <h2 id="reports-coverage">{t("coverage_heading")}</h2>
            <div className="resource-table-scroll">
              <table className="resource-table team-table">
                <thead>
                  <tr>
                    <th>{t("line")}</th>
                    <th>{t("scheduled")}</th>
                    <th>{t("covered")}</th>
                    <th>{t("uncovered")}</th>
                    <th>{t("cancelled")}</th>
                    <th>{t("rate")}</th>
                    <th>{t("reasons")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.coverage.map((row) => {
                    const name =
                      row.names
                        .map((names) => names[lang] || names[0] || "")
                        .join(" – ") || t("no_line");
                    const station = (code: string) => {
                      const names = row.names[row.stations.indexOf(code)];
                      return names ? names[lang] || names[0] || code : code;
                    };
                    const days = lines[`${month}|${row.line}`];
                    const reasons = Object.entries(row.reasons).sort(
                      ([a], [b]) => a.localeCompare(b),
                    );
                    return (
                      <Fragment key={row.line}>
                        <tr>
                          <td className="team-name">
                            {row.uncovered + row.cancelled > 0 ? (
                              <button
                                className="reports-line"
                                aria-expanded={!!days}
                                onClick={() => void toggle(row.line)}
                              >
                                {days ? "▾" : "▸"} {name}
                              </button>
                            ) : (
                              name
                            )}
                          </td>
                          <td data-label={t("scheduled")}>{row.scheduled}</td>
                          <td data-label={t("covered")}>{row.covered}</td>
                          <td data-label={t("uncovered")}>{row.uncovered}</td>
                          <td data-label={t("cancelled")}>{row.cancelled}</td>
                          <td data-label={t("rate")}>
                            {row.rate === null
                              ? "—"
                              : number.format(row.rate * 100)}
                          </td>
                          <td data-label={t("reasons")}>
                            {reasons.length
                              ? reasons
                                  .map(
                                    ([key, count]) =>
                                      `${reason(key)}: ${count}`,
                                  )
                                  .join("; ")
                              : "—"}
                          </td>
                        </tr>
                        {days && (
                          <tr className="reports-days">
                            <td colSpan={7}>
                              <section
                                role="region"
                                aria-label={`${t("affected_days")}: ${name}`}
                              >
                                {days === "loading" ? (
                                  <p role="status">
                                    {el ? "Φόρτωση…" : "Loading…"}
                                  </p>
                                ) : days === "failed" ? (
                                  <p role="alert">
                                    {el
                                      ? "Οι ημέρες δεν φορτώθηκαν."
                                      : "The days could not be loaded."}
                                  </p>
                                ) : (
                                  <table className="resource-table team-table">
                                    <thead>
                                      <tr>
                                        <th>{t("date")}</th>
                                        <th>{t("uncovered")}</th>
                                        <th>{t("cancelled")}</th>
                                        <th>{t("reason")}</th>
                                        <th>{t("note")}</th>
                                        <th>{t("published_by")}</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {days.map((day) => (
                                        <tr
                                          key={`${day.date}|${day.direction}`}
                                        >
                                          <td className="team-name">
                                            {date(day.date)} ·{" "}
                                            {day.direction
                                              .split("→")
                                              .map(station)
                                              .join(" → ")}
                                          </td>
                                          <td data-label={t("uncovered")}>
                                            {day.uncovered.join(", ") || "—"}
                                          </td>
                                          <td data-label={t("cancelled")}>
                                            {day.cancelled
                                              .map((trip) =>
                                                trip.reason
                                                  ? `${trip.trip_code}: ${trip.reason}`
                                                  : trip.trip_code,
                                              )
                                              .join("; ") || "—"}
                                          </td>
                                          <td data-label={t("reason")}>
                                            {day.reason
                                              ? reason(day.reason)
                                              : day.uncovered.length
                                                ? t("unrecorded")
                                                : "—"}
                                            {day.context && (
                                              <small>
                                                {t("context")}:{" "}
                                                {
                                                  day.context
                                                    .drivers_unavailable
                                                }{" "}
                                                {t("drivers_unavailable")},{" "}
                                                {day.context.vehicles_out}{" "}
                                                {t("vehicles_out")}
                                              </small>
                                            )}
                                          </td>
                                          <td data-label={t("note")}>
                                            {day.note || "—"}
                                          </td>
                                          <td data-label={t("published_by")}>
                                            {day.published_by}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </section>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}
