"use client";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { checked, type Timetable } from "./shared";

type Connection = {
  id: number;
  version: number;
  incoming: Pick<Timetable, "trip_code">;
  outgoing: Pick<Timetable, "trip_code">;
};

export function ConnectionPanel() {
  const { locale } = useI18n(),
    el = locale === "el";
  const [open, setOpen] = useState(false);
  return (
    <details
      className="resource-panel connection-panel"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        {el
          ? "Ίδιο όχημα για συνδεδεμένα δρομολόγια"
          : "Keep linked trips on one vehicle"}
      </summary>
      <p>
        {el
          ? "Προαιρετικό. Χρησιμοποιήστε το μόνο όταν δύο διαδοχικά δρομολόγια πρέπει να εκτελούνται από το ίδιο όχημα. Ισχύει τις ημέρες που εκτελούνται και τα δύο."
          : "Optional. Use this when two consecutive trips must use the same vehicle. Applies on dates when both trips operate."}
      </p>
      {open && <Connections />}
    </details>
  );
}
function Connections() {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const canWrite = !!user?.permissions.includes("timetable.write");
  const [rows, setRows] = useState<Connection[]>([]),
    [page, setPage] = useState(1),
    [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [incoming, setIncoming] = useState<Timetable | null>(null),
    [outgoing, setOutgoing] = useState<Timetable | null>(null);
  const [formVersion, setFormVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void apiFetch(
      `/api/v1/connections?active_only=true&page=${page}&page_size=25`,
      { signal: controller.signal },
    )
      .then((r) => checked<{ items: Connection[]; total: number }>(r, el))
      .then((data) => {
        setRows(data.items);
        setTotal(data.total);
        setError("");
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            el
              ? "Δεν φορτώθηκαν οι συνδέσεις. Δοκιμάστε ξανά."
              : "Connections could not load. Try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [apiFetch, page, refresh, el]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!incoming || !outgoing) return;
    setBusy(true);
    setError("");
    try {
      await checked(
        await apiFetch("/api/v1/connections", {
          method: "POST",
          body: JSON.stringify({
            incoming_template_id: incoming.id,
            incoming_template_version: incoming.version,
            outgoing_template_id: outgoing.id,
            outgoing_template_version: outgoing.version,
          }),
        }),
        el,
      );
      setFormVersion(x => x + 1);
      setIncoming(null);
      setOutgoing(null);
      setPage(1);
      setRefresh((x) => x + 1);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : el
            ? "Η αποθήκευση απέτυχε."
            : "Save failed.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function remove(row: Connection) {
    setBusy(true);
    setError("");
    try {
      await checked(
        await apiFetch(`/api/v1/connections/${row.id}`, {
          method: "PATCH",
          body: JSON.stringify({ version: row.version, is_active: false }),
        }),
        el,
      );
      setPage(1);
      setRefresh((x) => x + 1);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : el
            ? "Η αποθήκευση απέτυχε."
            : "Save failed.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {error && (
        <p role="alert" className="auth-error">
          {error}{" "}
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => setRefresh((x) => x + 1)}
          >
            {el ? "Ανανέωση" : "Refresh"}
          </button>
        </p>
      )}
      {canWrite && (
        <form onSubmit={save}>
          <div className="resource-form-grid">
            <TripPicker
              label={el ? "Προηγούμενο δρομολόγιο" : "Incoming trip"}
              key={`incoming-${formVersion}`}
              onChange={setIncoming}
            />
            <TripPicker
              label={el ? "Επόμενο δρομολόγιο" : "Following trip"}
              key={`outgoing-${formVersion}`}
              onChange={setOutgoing}
            />
          </div>
          <button
            className="button secondary"
            disabled={
              busy || !incoming || !outgoing || incoming.id === outgoing.id
            }
          >
            {busy
              ? el
                ? "Αποθήκευση…"
                : "Saving…"
              : el
                ? "Σύνδεση δρομολογίων"
                : "Link trips"}
          </button>
        </form>
      )}
      {loading ? (
        <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p>
      ) : (
        <ul
          className="connection-list"
          aria-label={el ? "Αποθηκευμένες συνδέσεις" : "Saved trip connections"}
        >
          {!rows.length && (
            <li>
              {el ? "Δεν έχετε προσθέσει συνδέσεις." : "No trips linked yet."}
            </li>
          )}
          {rows.map((row) => (
            <li key={row.id}>
              <strong>
                {row.incoming.trip_code} → {row.outgoing.trip_code}
              </strong>
              {canWrite && (
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  aria-label={
                    (el ? "Αφαίρεση σύνδεσης " : "Remove connection ") +
                    row.incoming.trip_code +
                    " → " +
                    row.outgoing.trip_code
                  }
                  onClick={() => void remove(row)}
                >
                  {el ? "Αφαίρεση" : "Remove"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {total > 25 && (
        <div className="planning-pagination">
          <button
            className="button secondary"
            disabled={page === 1 || loading}
            onClick={() => setPage((x) => x - 1)}
          >
            {el ? "Προηγούμενη" : "Previous"}
          </button>
          <span>
            {page} / {Math.ceil(total / 25)}
          </span>
          <button
            className="button secondary"
            disabled={page * 25 >= total || loading}
            onClick={() => setPage((x) => x + 1)}
          >
            {el ? "Επόμενη" : "Next"}
          </button>
        </div>
      )}
    </>
  );
}
function TripPicker({
  label,
  onChange,
}: {
  label: string;
  onChange: (value: Timetable | null) => void;
}) {
  const { apiFetch } = useAuth(),
    { locale } = useI18n(),
    id = useId(),
    el = locale === "el";
  const [text, setText] = useState(""),
    [items, setItems] = useState<Timetable[]>([]),
    [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    const timer = setTimeout(() => {
      void apiFetch(
        `/api/v1/timetables?active_only=true&page_size=25&q=${encodeURIComponent(text.slice(0, 160))}`,
        { signal: controller.signal },
      )
        .then((r) => checked<{ items: Timetable[] }>(r, el))
        .then((data) => {
          setItems(data.items);
          const selected = data.items.find((row) => row.trip_code === text);
          if (selected) onChange(selected);
        })
        .catch(() => {
          if (!controller.signal.aborted) setFailed(true);
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // Selection is controlled by the form; fetching follows the typed reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, apiFetch, el]);
  return (
    <div className="resource-field">
      <label htmlFor={id + "-input"}>{label}</label>
      <input
        id={id + "-input"}
        list={id}
        value={text}
        maxLength={64}
        required
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value);
          onChange(
            items.find((row) => row.trip_code === e.target.value) ?? null,
          );
        }}
      />
      <datalist id={id}>
        {items.map((row) => (
          <option key={row.id} value={row.trip_code}>
            {row.departure_time.slice(0, 5)} → {row.arrival_time.slice(0, 5)}
          </option>
        ))}
      </datalist>
      {failed && (
        <small role="alert">
          {el
            ? "Δεν φορτώθηκαν τα δρομολόγια. Πληκτρολογήστε ξανά."
            : "Trips could not load. Type again to retry."}
        </small>
      )}
    </div>
  );
}
