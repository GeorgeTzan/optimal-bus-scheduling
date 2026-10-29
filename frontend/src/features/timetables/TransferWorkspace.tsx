"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  HelpCircle,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { BulkImportButton } from "../imports/BulkImportButton";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { checked, stationName } from "./shared";
import type { Resource } from "../resources/ResourceWorkspace";

interface Direction {
  id: number | null;
  version: number | null;
  origin_station_id: number;
  destination_station_id: number;
  origin_version: number;
  destination_version: number;
  minutes: number | null;
  needs_review: boolean;
  can_edit: boolean;
}
interface Pair {
  key: string;
  origin: Resource;
  destination: Resource;
  forward: Direction;
  reverse: Direction;
}
interface EditorData {
  items: Pair[];
  total: number;
  page: number;
  page_size: number;
  counts: {
    required_directions: number;
    saved_directions: number;
    missing_directions: number;
    review_directions: number;
  };
}
interface Draft {
  direction: Direction;
  value: string;
}
const keyOf = (direction: Direction) =>
  `${direction.origin_station_id}:${direction.destination_station_id}`;

export function TransferWorkspace({
  date,
  onSaved,
  refreshToken,
  onDirtyChange,
}: {
  date: string;
  onSaved: () => Promise<void>;
  refreshToken?: unknown;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el",
    canWrite = !!user?.permissions.includes("timetable.write");
  const [data, setData] = useState<EditorData | null>(null),
    [filter, setFilter] = useState("required"),
    [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({}),
    [copies, setCopies] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [help, setHelp] = useState(false);
  const currentDate = useRef(date);
  currentDate.current = date;
  const dirty = Object.keys(drafts).length > 0;
  useUnsavedChanges(dirty);
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);
  useEffect(() => {
    setDrafts({});
    setCopies({});
    setPage(1);
    setData(null);
    setLoading(true);
    setNotice("");
  }, [date]);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const result = await checked<EditorData>(
          await apiFetch(
            `/api/v1/transfers/editor?service_date=${date}&filter=${filter}&page=${page}`,
            { signal },
          ),
          el,
        );
        if (signal?.aborted || currentDate.current !== date) return;
        setData(result);
        if (result.total > 0 && (page - 1) * result.page_size >= result.total)
          setPage(Math.ceil(result.total / result.page_size));
      } catch (e) {
        if (!signal?.aborted && currentDate.current === date)
          setError(
            e instanceof Error
              ? e.message
              : el
                ? "Δεν φορτώθηκαν οι χρόνοι."
                : "Travel times could not load.",
          );
      } finally {
        if (!signal?.aborted && currentDate.current === date) setLoading(false);
      }
    },
    [apiFetch, date, filter, page, el],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshToken]);
  function edit(direction: Direction, value: string) {
    setDrafts((existing) => {
      const next = {...existing};
      if (!direction.needs_review && value === (direction.minutes === null ? "" : String(direction.minutes))) delete next[keyOf(direction)];
      else next[keyOf(direction)] = {direction, value};
      return next;
    });
    setNotice("");
  }
  function valueOf(direction: Direction) {
    return (
      drafts[keyOf(direction)]?.value ??
      (direction.minutes === null ? "" : String(direction.minutes))
    );
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    const entries = Object.values(drafts).filter(
      (item) => item.value.trim() !== "",
    );
    if (!entries.length) return;
    if (entries.length > 100) {
      setError(
        el
          ? "Αποθηκεύστε έως 100 κατευθύνσεις κάθε φορά."
          : "Save up to 100 directions at a time.",
      );
      return;
    }
    if (
      entries.some(
        (item) =>
          !Number.isInteger(Number(item.value)) ||
          Number(item.value) < 0 ||
          Number(item.value) > 1440,
      )
    ) {
      setError(
        el
          ? "Χρησιμοποιήστε ολόκληρα λεπτά από 0 έως 1440."
          : "Use whole minutes from 0 to 1440.",
      );
      return;
    }
    const selectedDate = date;
    setBusy(true);
    try {
      await checked(
        await apiFetch("/api/v1/transfers/editor", {
          method: "POST",
          body: JSON.stringify({
            items: entries.map(({ direction, value }) => ({
              origin_station_id: direction.origin_station_id,
              destination_station_id: direction.destination_station_id,
              origin_version: direction.origin_version,
              destination_version: direction.destination_version,
              expected_version: direction.version,
              minutes: Number(value),
            })),
          }),
        }),
        el,
      );
      if (currentDate.current !== selectedDate) return;
      setDrafts({});
      setCopies({});
      await load();
      await onSaved();
      if (currentDate.current === selectedDate)
        setNotice(
          el ? "Οι χρόνοι μετακίνησης αποθηκεύτηκαν." : "Travel times saved.",
        );
    } catch (e) {
      if (currentDate.current === selectedDate)
        setError(
          e instanceof Error
            ? e.message
            : el
              ? "Η αποθήκευση απέτυχε."
              : "Save failed.",
        );
    } finally {
      if (currentDate.current === selectedDate) setBusy(false);
    }
  }
  const entered = Object.values(drafts).filter(
    (item) => item.value.trim() !== "",
  ).length;
  return (
    <section
      className="planning-section transfer-workspace"
      aria-label={el ? "Μετακίνηση κενού οχήματος" : "Travel between trips"}
    >
      <div className="planning-section-heading">
        <span className="planning-number">2</span>
        <div>
          <h2>{el ? "Μετακίνηση κενού οχήματος" : "Travel between trips"}</h2>
          <p>
            {el
              ? "Πόσα λεπτά χρειάζεται το λεωφορείο για να φτάσει από έναν σταθμό στην επόμενη αφετηρία;"
              : "Time to move an empty bus to the next departure station."}
          </p>
        </div>
      </div>
      <div className="transfer-tools">
        <button
          className="button secondary"
          aria-expanded={help}
          onClick={() => setHelp((v) => !v)}
        >
          <HelpCircle size={16} />
          {el ? "Γιατί χρειάζονται αυτοί οι χρόνοι;" : "Why is this needed?"}
        </button>
        <BulkImportButton entity="transfers" returnTo="planning" />
      </div>
      {help && (
        <div className="planning-guide transfer-example">
          <div>
            <strong>
              {el
                ? "Παράδειγμα · διαφορετικό από το δρομολόγιο με επιβάτες"
                : "Example · travelling without passengers"}
            </strong>
            <p>
              {el
                ? "Το λεωφορείο τελειώνει στο Κιάτο στις 09:10. Το επόμενο δρομολόγιο ξεκινά από την Κόρινθο στις 10:00. Αν χρειάζεται 25 λεπτά μετακίνησης χωρίς επιβάτες, φτάνει στις 09:35. Αυτόν τον χρόνο δηλώνετε εδώ."
                : "A bus finishes at Kiato at 09:10. Its next trip departs Corinth at 10:00. A 25-minute transfer without passengers gets it there at 09:35. Enter that transfer time here."}
            </p>
            <p>
              {el
                ? "Οι τιμές αποθηκεύονται μία φορά και χρησιμοποιούνται στις επόμενες ημέρες. Η επιστροφή μπορεί να διαφέρει. Το κενό δεν σημαίνει μηδέν."
                : "Save these reusable values once. The return direction may differ. A blank never means zero."}
            </p>
          </div>
        </div>
      )}
      {error && (
        <div className="import-alert" role="alert">
          <p>{error}</p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => {
              setError("");
              void load();
            }}
          >
            <RefreshCw size={15} />
            {el ? "Ανανέωση αποθηκευμένων τιμών" : "Refresh saved values"}
          </button>
          <p className="resource-help">
            {el
              ? "Οι αλλαγές σας παραμένουν στα πεδία. Ελέγξτε τις τρέχουσες τιμές πριν αποθηκεύσετε ξανά."
              : "Your edits stay in the fields. Review the current saved values before saving again."}
          </p>
        </div>
      )}
      {notice && (
        <p className="resource-saved" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      {data && (
        <div className="transfer-summary">
          <strong>
            {el
              ? `${data.counts.saved_directions} από ${data.counts.required_directions} κατευθύνσεις είναι έτοιμες για αυτή την ημέρα.`
              : `${data.counts.saved_directions} of ${data.counts.required_directions} directions are ready for this day.`}
          </strong>
          <p>
            {el
              ? `Λείπουν ${data.counts.missing_directions} · Χρειάζονται επανέλεγχο ${data.counts.review_directions}. Απαιτούνται για τους σταθμούς των δρομολογίων και τις αρχικές έδρες της ομάδας.`
              : `${data.counts.missing_directions} missing · ${data.counts.review_directions} need review. Required for this day's trip stations and the crew's starting bases.`}
          </p>
          <p>
            {el
              ? "Οι αποθηκευμένες τιμές παραμένουν ορατές και διορθώνονται παρακάτω."
              : "Saved values remain visible and can be edited below."}
          </p>
        </div>
      )}
      <div className="transfer-filter">
        <label>
          {el ? "Εμφάνιση" : "Show"}
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="required">
              {el ? "Απαιτούνται αυτή την ημέρα" : "Required for this day"}
            </option>
            <option value="missing">
              {el ? "Λείπουν ή χρειάζονται έλεγχο" : "Missing or need review"}
            </option>
            <option value="all">
              {el
                ? "Όλες οι αποθηκευμένες διαδρομές"
                : "All saved station pairs"}
            </option>
          </select>
        </label>
      </div>
      {loading && !data ? (
        <p role="status">{el ? "Φόρτωση χρόνων…" : "Loading travel times…"}</p>
      ) : (
        data && (
          <form onSubmit={save}>
            {!data.items.length ? (
              <p className="planning-empty">
                {data.counts.required_directions === 0
                  ? el
                    ? "Οι απαιτούμενες διαδρομές εμφανίζονται όταν υπάρχουν δρομολόγια και αρχικές έδρες για την ημέρα. Μπορείτε να εισαγάγετε αποθηκευμένους χρόνους από Excel."
                    : "Required station pairs appear when services and starting bases are selected for the day. You can also import travel times from Excel."
                  : el
                    ? "Δεν υπάρχουν διαδρομές σε αυτό το φίλτρο."
                    : "No station pairs match this filter."}
              </p>
            ) : (
              <div className="transfer-pairs">
                {data.items.map((pair) => {
                  const pairName = `${stationName(pair.origin, el)} ↔ ${stationName(pair.destination, el)}`;
                  return (
                    <article className="transfer-pair" key={pair.key}>
                      <div className="transfer-pair-title">
                        <strong>{pairName}</strong>
                        <small>
                          {el
                            ? "Ελέγξτε κάθε κατεύθυνση ξεχωριστά."
                            : "Review each direction separately."}
                        </small>
                      </div>
                      <div className="transfer-directions">
                        {[pair.forward, pair.reverse].map(
                          (direction, index) => {
                            const name =
                              index === 0
                                ? `${stationName(pair.origin, el)} → ${stationName(pair.destination, el)}`
                                : `${stationName(pair.destination, el)} → ${stationName(pair.origin, el)}`;
                            const draft = drafts[keyOf(direction)],
                              changedSource =
                                !!draft &&
                                (draft.direction.version !==
                                  direction.version ||
                                  draft.direction.origin_version !==
                                    direction.origin_version ||
                                  draft.direction.destination_version !==
                                    direction.destination_version);
                            return (
                              <div
                                className="transfer-direction"
                                key={keyOf(direction)}
                              >
                                <label>
                                  {el ? "Λεπτά" : "Minutes"}: {name}
                                  <input
                                    type="number"
                                    min={0}
                                    max={1440}
                                    step={1}
                                    required={direction.minutes !== null}
                                    disabled={
                                      busy || !canWrite || !direction.can_edit
                                    }
                                    value={valueOf(direction)}
                                    placeholder={el ? "Λείπει" : "Missing"}
                                    onChange={(e) => {
                                      edit(direction, e.target.value);
                                      if (
                                        index === 0 &&
                                        copies[pair.key] &&
                                        pair.reverse.can_edit
                                      )
                                        edit(pair.reverse, e.target.value);
                                      if (index === 1)
                                        setCopies((v) => ({
                                          ...v,
                                          [pair.key]: false,
                                        }));
                                    }}
                                  />
                                </label>
                                <small
                                  className={
                                    direction.needs_review
                                      ? "transfer-review"
                                      : ""
                                  }
                                >
                                  {!direction.can_edit
                                    ? el
                                      ? "Αρχειοθετημένος σταθμός"
                                      : "Archived station"
                                    : direction.needs_review
                                      ? el
                                        ? "Χρειάζεται επανέλεγχο"
                                        : "Needs review"
                                      : direction.minutes === null
                                        ? el
                                          ? "Δεν έχει αποθηκευτεί τιμή"
                                          : "No saved value"
                                        : el
                                          ? `Αποθηκευμένο: ${direction.minutes} λεπτά`
                                          : `Saved: ${direction.minutes} minutes`}
                                </small>
                                {direction.needs_review &&
                                  canWrite &&
                                  direction.can_edit && (
                                    <button
                                      type="button"
                                      className="transfer-text-action"
                                      disabled={
                                        busy || direction.minutes === null
                                      }
                                      onClick={() =>
                                        edit(direction, valueOf(direction))
                                      }
                                    >
                                      {el
                                        ? "Επιβεβαίωση της ελεγμένης τιμής"
                                        : "Confirm reviewed value"}
                                    </button>
                                  )}
                                {changedSource && (
                                  <div className="transfer-conflict">
                                    <small>
                                      {el
                                        ? "Τα στοιχεία άλλαξαν από την τελευταία επεξεργασία σας."
                                        : "Saved details changed since you edited."}
                                    </small>
                                    <button
                                      type="button"
                                      className="transfer-text-action"
                                      disabled={busy}
                                      onClick={() =>
                                        edit(direction, draft.value)
                                      }
                                    >
                                      {el
                                        ? "Έλεγξα τις τιμές · Κρατώ την αλλαγή μου"
                                        : "Reviewed values · Keep my edit"}
                                    </button>
                                  </div>
                                )}
                              </div>
                            );
                          },
                        )}
                      </div>
                      {canWrite && (
                        <label className="planning-check transfer-copy">
                          <input
                            type="checkbox"
                            checked={copies[pair.key] ?? false}
                            disabled={
                              busy ||
                              !pair.reverse.can_edit ||
                              valueOf(pair.forward) === ""
                            }
                            onChange={(e) => {
                              setCopies((v) => ({
                                ...v,
                                [pair.key]: e.target.checked,
                              }));
                              if (e.target.checked)
                                edit(pair.reverse, valueOf(pair.forward));
                            }}
                          />
                          {el
                            ? "Ίδιος χρόνος και στην επιστροφή"
                            : "Use the same time for return"}
                          : {pairName}
                        </label>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
            <div className="planning-section-footer">
              <p>
                {el
                  ? `${data.total} ζεύγη σταθμών · Αποθηκεύστε όσα γνωρίζετε. Οι κενές τιμές παραμένουν κενές.`
                  : `${data.total} station pairs · Save the values you know. Blank values stay blank.`}
              </p>
              {canWrite && (
                <button
                  className="button primary"
                  disabled={busy || entered === 0}
                >
                  {busy
                    ? el
                      ? "Αποθήκευση…"
                      : "Saving…"
                    : el
                      ? "Αποθήκευση χρόνων μετακίνησης"
                      : "Save travel times"}
                </button>
              )}
            </div>
            {data.total > data.page_size && (
              <div className="planning-pagination">
                <button
                  type="button"
                  className="button secondary"
                  disabled={page === 1 || busy}
                  onClick={() => setPage((v) => v - 1)}
                >
                  <ArrowLeft size={14} />
                  {el ? "Προηγούμενη" : "Previous"}
                </button>
                <span>
                  {page} / {Math.ceil(data.total / data.page_size)}
                </span>
                <button
                  type="button"
                  className="button secondary"
                  disabled={page * data.page_size >= data.total || busy}
                  onClick={() => setPage((v) => v + 1)}
                >
                  {el ? "Επόμενη" : "Next"}
                  <ArrowRight size={14} />
                </button>
              </div>
            )}
          </form>
        )
      )}
      {!canWrite && (
        <p className="resource-help">
          {el
            ? "Ο υπεύθυνος δρομολογίων μπορεί να συμπληρώσει ή να επιβεβαιώσει αυτές τις τιμές."
            : "Your timetable manager can add or confirm these values."}
        </p>
      )}
    </section>
  );
}
