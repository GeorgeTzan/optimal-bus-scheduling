"use client";
import { DriverAccess } from "./DriverAccess";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { confirmDiscardOwn } from "../navigation/unsaved-changes";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Plus,
  Search,
  UsersRound,
  BusFront,
  MapPin,
  X,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { BulkImportButton } from "../imports/BulkImportButton";
import { useListLocation } from "../navigation/use-list-location";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";

type Kind = "drivers" | "vehicles" | "stations";
export interface Resource {
  id: number;
  version: number;
  code: string;
  is_active: boolean;
  first_name?: string;
  last_name?: string;
  phone?: string | null;
  license_number?: string | null;
  registration_plate?: string | null;
  bus_type?: string;
  capacity?: number | null;
  name_el?: string;
  name_en?: string;
  is_depot?: boolean;
  home_station_id?: number | null;
  home_station?: {
    id: number;
    code: string;
    name_el: string;
    name_en: string;
  } | null;
}
interface Listing {
  items: Resource[];
  total: number;
  page: number;
  page_size: number;
}
const words = {
  drivers: {
    title: ["Οδηγοί", "Drivers"],
    singular: ["οδηγού", "driver"],
    add: ["Προσθήκη οδηγού", "Add driver"],
    save: ["Αποθήκευση οδηγού", "Save driver"],
    intro: [
      "Οι άνθρωποι που κρατούν τα δρομολόγιά σας σε κίνηση.",
      "The people who keep your journeys moving.",
    ],
  },
  vehicles: {
    title: ["Στόλος", "Fleet"],
    singular: ["οχήματος", "vehicle"],
    add: ["Προσθήκη οχήματος", "Add vehicle"],
    save: ["Αποθήκευση οχήματος", "Save vehicle"],
    intro: [
      "Τα οχήματά σας, με τα στοιχεία που γνωρίζετε.",
      "Your vehicles, with the details you know.",
    ],
  },
  stations: {
    title: ["Σταθμοί & αμαξοστάσια", "Stations & depots"],
    singular: ["σταθμού", "station"],
    add: ["Προσθήκη σταθμού", "Add station"],
    save: ["Αποθήκευση σταθμού", "Save station"],
    intro: [
      "Ονομασίες που θα αναγνωρίζει όλη η ομάδα.",
      "Familiar names that your whole team can recognize.",
    ],
  },
};
export function ResourceWorkspace({
  kind: initialKind,
}: {
  kind: "drivers" | "vehicles";
}) {
  const { apiFetch, user } = useAuth();
  const { locale } = useI18n();
  const el = locale === "el",
    lang = el ? 0 : 1;
  const [kind, setKind] = useState<Kind>(initialKind);
  const [listing, setListing] = useState<Listing>({
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
  });
  const { page, setPage, query, setQuery } = useListLocation();
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(false);
  const [editing, setEditing] = useState<Resource | "new" | null>(null);
  const [notice, setNotice] = useState(false);
  const addRef = useRef<HTMLButtonElement>(null);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(false);
      try {
        const response = await apiFetch(
          `/api/v1/${kind}?q=${encodeURIComponent(query)}&page=${page}`,
          { signal },
        );
        if (!response.ok) throw new Error();
        const data = (await response.json()) as Listing;
        if (!signal?.aborted) setListing(data);
      } catch {
        if (!signal?.aborted) setError(true);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [apiFetch, kind, query, page],
  );
  useEffect(() => {
    const abort = new AbortController();
    const timer = setTimeout(() => void load(abort.signal), 200);
    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [load]);
  const permission =
    kind === "drivers"
      ? "drivers.write"
      : kind === "vehicles"
        ? "fleet.write"
        : "timetable.write";
  const canEdit = user?.permissions.includes(permission) ?? false;
  const canInvite = user?.permissions.includes("members.manage") ?? false;
  const title = words[kind];
  const Icon =
    kind === "drivers" ? UsersRound : kind === "vehicles" ? BusFront : MapPin;
  const label = (row: Resource) =>
    kind === "drivers"
      ? `${row.first_name} ${row.last_name}`
      : kind === "vehicles"
        ? (row.registration_plate ?? row.code)
        : el
          ? row.name_el
          : row.name_en;
  const close = () => {
    setEditing(null);
    requestAnimationFrame(() => addRef.current?.focus());
  };
  return (
    <section className="resource-workspace">
      {kind === "stations" && (
        <button
          className="resource-back"
          onClick={() => {
            setKind(initialKind);
            setPage(1);
            setQuery("");
          }}
        >
          <ArrowLeft size={14} />
          {el ? "Επιστροφή" : "Back"}
        </button>
      )}
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΟΡΓΑΝΩΣΗ" : "ORGANIZATION"}
          </span>
          <h1>{title.title[lang]}</h1>
          <p>{title.intro[lang]}</p>
        </div>
        <div className="resource-heading-actions">
          <BulkImportButton
            entity={kind}
            returnTo={initialKind === "drivers" ? "drivers" : "fleet"}
            primary={listing.total === 0 && !query}
          />
          {canEdit && (
            <button
              ref={addRef}
              className={`button ${listing.total === 0 && !query && user?.permissions.includes("imports.write") ? "secondary" : "primary"}`}
              onClick={() => setEditing("new")}
            >
              <Plus size={16} />
              {title.add[lang]}
            </button>
          )}
        </div>
      </header>
      {notice && (
        <div className="resource-saved" role="status">
          {el ? "Οι αλλαγές αποθηκεύτηκαν." : "Your changes have been saved."}
          <button
            onClick={() => setNotice(false)}
            aria-label={el ? "Κλείσιμο μηνύματος" : "Dismiss message"}
          >
            <X size={15} />
          </button>
        </div>
      )}
      <div className="resource-panel">
        <div className="resource-tools">
          <label className="resource-search">
            <Search size={16} />
            <span className="sr-only">
              {el ? "Αναζήτηση" : "Search records"}
            </span>
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder={
                el
                  ? "Αναζήτηση με όνομα ή αναφορά…"
                  : "Search by name or reference…"
              }
            />
          </label>
          {kind !== "stations" &&
            user?.permissions.includes("timetable.write") && (
              <button
                className="resource-back"
                onClick={() => {
                  setKind("stations");
                  setPage(1);
                  setQuery("");
                }}
              >
                <MapPin size={14} />
                {el ? "Σταθμοί & αμαξοστάσια" : "Manage stations"}
              </button>
            )}
        </div>
        {error ? (
          <div className="resource-empty">
            <p role="alert">
              {el
                ? "Δεν μπορέσαμε να φορτώσουμε τα στοιχεία."
                : "We could not load your records."}
            </p>
            <button className="button secondary" onClick={() => void load()}>
              {el ? "Νέα προσπάθεια" : "Try again"}
            </button>
          </div>
        ) : loading ? (
          <div className="resource-empty" role="status">
            {el ? "Φόρτωση στοιχείων…" : "Loading your records…"}
          </div>
        ) : listing.total === 0 ? (
          <div className="resource-empty">
            <span className="resource-empty-icon">
              <Icon size={27} />
            </span>
            <h2>
              {query
                ? el
                  ? "Δεν βρέθηκαν αποτελέσματα"
                  : "No matching records"
                : el
                  ? "Ξεκινήστε με τα βασικά"
                  : "Start with the essentials"}
            </h2>
            <p>
              {query
                ? el
                  ? "Δοκιμάστε άλλο όνομα ή αναφορά."
                  : "Try another name or reference."
                : el
                  ? `Επιλέξτε «${title.add[0]}» για την πρώτη εγγραφή. Τα προαιρετικά στοιχεία μπορούν να συμπληρωθούν αργότερα.`
                  : `Choose “${title.add[1]}” for your first record. Optional details can be added later.`}
            </p>
          </div>
        ) : (
          <>
            <div className="resource-table-scroll">
              <table className="resource-table">
                <thead>
                  <tr>
                    <th>{el ? "Όνομα / αναφορά" : "Name / reference"}</th>
                    <th>
                      {kind === "vehicles"
                        ? el
                          ? "Τύπος & θέσεις"
                          : "Type & seats"
                        : kind === "stations"
                          ? el
                            ? "Χρήση"
                            : "Use"
                          : el
                            ? "Τηλέφωνο"
                            : "Phone"}
                    </th>
                    {kind !== "stations" && (
                      <th>{el ? "Έδρα" : "Home base"}</th>
                    )}
                    <th>{el ? "Κατάσταση" : "Status"}</th>
                    <th>
                      <span className="sr-only">
                        {el ? "Ενέργειες" : "Actions"}
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {listing.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{label(row)}</strong>
                        <small>{row.code}</small>
                      </td>
                      <td>
                        {kind === "vehicles" ? (
                          <>
                            <span>{row.bus_type}</span>
                            <small>
                              {row.capacity == null
                                ? el
                                  ? "Δεν έχει καταγραφεί"
                                  : "Not recorded"
                                : `${row.capacity} ${el ? "θέσεις" : "seats"}`}
                            </small>
                          </>
                        ) : kind === "stations" ? (
                          row.is_depot ? (
                            el ? (
                              "Αμαξοστάσιο"
                            ) : (
                              "Depot"
                            )
                          ) : el ? (
                            "Σταθμός"
                          ) : (
                            "Station"
                          )
                        ) : (
                          row.phone || "—"
                        )}
                      </td>
                      {kind !== "stations" && (
                        <td>
                          {row.home_station
                            ? el
                              ? row.home_station.name_el
                              : row.home_station.name_en
                            : "—"}
                        </td>
                      )}
                      <td>
                        <span
                          className={`resource-status ${row.is_active ? "active" : ""}`}
                        >
                          {row.is_active
                            ? el
                              ? "Ενεργό"
                              : "Active"
                            : el
                              ? "Αρχειοθετημένο"
                              : "Archived"}
                        </span>
                      </td>
                      <td>
                        {canEdit && (
                          <button
                            className="resource-edit"
                            onClick={() => setEditing(row)}
                          >
                            {el ? "Επεξεργασία" : "Edit"}
                          </button>
                        )}
                        {kind === "drivers" && canInvite && (
                          <button
                            className="resource-edit"
                            onClick={() => setEditing(row)}
                            aria-label={`${el ? "Πρόσκληση σύνδεσης για" : "Invite to sign in:"} ${label(row)}`}
                          >
                            {el ? "Πρόσκληση σύνδεσης" : "Invite to sign in"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="resource-mobile-list" aria-label={title.title[lang]}>
              {listing.items.map((row) => (
                <li key={row.id} className="resource-mobile-card">
                  <div className="resource-card-heading">
                    <div>
                      <strong>{label(row)}</strong>
                      <small>{row.code}</small>
                    </div>
                    {canEdit && (
                      <button
                        className="resource-edit"
                        onClick={() => setEditing(row)}
                      >
                        {el ? "Επεξεργασία" : "Edit"}
                      </button>
                    )}
                    {kind === "drivers" && canInvite && (
                      <button
                        className="resource-edit"
                        onClick={() => setEditing(row)}
                        aria-label={`${el ? "Πρόσκληση σύνδεσης για" : "Invite to sign in:"} ${label(row)}`}
                      >
                        {el ? "Πρόσκληση σύνδεσης" : "Invite to sign in"}
                      </button>
                    )}
                  </div>
                  <dl>
                    <div>
                      <dt>{el ? "Κατάσταση" : "Status"}</dt>
                      <dd>
                        <span
                          className={`resource-status ${row.is_active ? "active" : ""}`}
                        >
                          {row.is_active
                            ? el
                              ? "Ενεργό"
                              : "Active"
                            : el
                              ? "Αρχειοθετημένο"
                              : "Archived"}
                        </span>
                      </dd>
                    </div>
                    {kind === "vehicles" && (
                      <>
                        <div>
                          <dt>{el ? "Τύπος οχήματος" : "Vehicle type"}</dt>
                          <dd>{row.bus_type}</dd>
                        </div>
                        <div>
                          <dt>{el ? "Θέσεις" : "Seats"}</dt>
                          <dd>
                            {row.capacity ??
                              (el ? "Δεν έχει καταγραφεί" : "Not recorded")}
                          </dd>
                        </div>
                      </>
                    )}
                    {kind === "drivers" && row.phone && (
                      <div>
                        <dt>{el ? "Τηλέφωνο" : "Phone"}</dt>
                        <dd>{row.phone}</dd>
                      </div>
                    )}
                    {row.home_station && (
                      <div>
                        <dt>{el ? "Έδρα" : "Home base"}</dt>
                        <dd>
                          {el
                            ? row.home_station.name_el
                            : row.home_station.name_en}
                        </dd>
                      </div>
                    )}
                    {kind === "stations" && (
                      <div>
                        <dt>{el ? "Χρήση" : "Use"}</dt>
                        <dd>
                          {row.is_depot
                            ? el
                              ? "Αμαξοστάσιο"
                              : "Depot"
                            : el
                              ? "Σταθμός"
                              : "Station"}
                        </dd>
                      </div>
                    )}
                  </dl>
                </li>
              ))}
            </ul>
            <footer className="resource-pagination">
              <span>
                {(page - 1) * 25 + 1}–{Math.min(page * 25, listing.total)}{" "}
                {el ? "από" : "of"} {listing.total}
              </span>
              <div>
                <button
                  className="icon-button"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                  aria-label={el ? "Προηγούμενη σελίδα" : "Previous page"}
                >
                  <ChevronLeft size={17} />
                </button>
                <button
                  className="icon-button"
                  disabled={page * 25 >= listing.total}
                  onClick={() => setPage(page + 1)}
                  aria-label={el ? "Επόμενη σελίδα" : "Next page"}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </footer>
          </>
        )}
      </div>
      {editing && (
        <ResourceForm
          kind={kind}
          record={editing}
          onClose={close}
          onSaved={() => {
            close();
            setNotice(true);
            void load();
          }}
        />
      )}
    </section>
  );
}

export function ResourceForm({
  kind,
  record,
  onClose,
  onSaved,
  initialValues,
}: {
  kind: Kind;
  record: Resource | "new";
  onClose: () => void;
  onSaved: (record: Resource) => void;
  initialValues?: Record<string, string>;
}) {
  const { apiFetch, user } = useAuth();
  const { locale } = useI18n();
  const el = locale === "el",
    lang = el ? 0 : 1,
    title = words[kind];
  const isNew = record === "new";
  const initial: Record<string, string> = isNew ? { ...initialValues } : {};
  if (!isNew)
    for (const [key, value] of Object.entries(record))
      if (value != null && typeof value !== "object")
        initial[key] = String(value);
  const [form, setForm] = useState<Record<string, string>>(initial);
  const [active, setActive] = useState(isNew ? true : record.is_active);
  const [referenceOnly, setReferenceOnly] = useState(
    !isNew && !record.registration_plate,
  );
  const [depot, setDepot] = useState(!isNew && !!record.is_depot);
  const [stations, setStations] = useState<Resource[]>([]),
    [home, setHome] = useState(
      !isNew && record.home_station
        ? `${el ? record.home_station.name_el : record.home_station.name_en} · ${record.home_station.code}`
        : "",
    );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const baseline = useRef(JSON.stringify({form,active,referenceOnly,depot,home}));
  const dirty = JSON.stringify({form,active,referenceOnly,depot,home}) !== baseline.current;
  useUnsavedChanges(dirty || busy);
  const closeGuarded = () => { if (!busy && confirmDiscardOwn(dirty, el)) onClose(); };
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const modal = dialog.current;
    modal?.showModal();
    modal?.querySelector<HTMLInputElement>("input[required]")?.focus();
    return () => modal?.close();
  }, []);
  useEffect(() => {
    if (kind === "stations") return;
    const controller = new AbortController();
    void apiFetch(
      `/api/v1/stations?active_only=true&page_size=25&q=${encodeURIComponent(home.split(" · ")[0] ?? "")}`,
      { signal: controller.signal },
    )
      .then(async (r) => {
        if (r.ok) setStations(((await r.json()) as Listing).items);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [apiFetch, kind, home]);
  const update = (key: string, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setFieldErrors((f) => ({ ...f, [key]: "" }));
  };
  const field = (
    key: string,
    label: string,
    required = false,
    type = "text",
    help?: string,
  ) => (
    <div className="resource-field" key={key}>
      <label htmlFor={`field-${key}`}>
        {label}
        {!required && <span>{el ? "προαιρετικό" : "optional"}</span>}
      </label>
      <input
        autoComplete="off"
        id={`field-${key}`}
        type={type}
        required={required}
        min={type === "number" ? 1 : undefined}
        max={type === "number" ? 200 : undefined}
        maxLength={
          key === "phone"
            ? 40
            : [
                  "code",
                  "license_number",
                  "registration_plate",
                  "bus_type",
                ].includes(key)
              ? 64
              : 160
        }
        value={form[key] ?? ""}
        onChange={(e) => update(key, e.target.value)}
        aria-invalid={!!fieldErrors[key]}
        aria-describedby={help || fieldErrors[key] ? `help-${key}` : undefined}
      />
      {(help || fieldErrors[key]) && (
        <small
          id={`help-${key}`}
          className={fieldErrors[key] ? "field-error" : ""}
        >
          {fieldErrors[key] ?? help}
        </small>
      )}
    </div>
  );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    const homeRecord =
      stations.find(
        (s) => `${el ? s.name_el : s.name_en} · ${s.code}` === home,
      ) ??
      (!isNew &&
      record.home_station &&
      `${el ? record.home_station.name_el : record.home_station.name_en} · ${record.home_station.code}` ===
        home
        ? record.home_station
        : undefined);
    if (home && !homeRecord) {
      setFieldErrors({
        home_station_id: el
          ? "Επιλέξτε έναν σταθμό από τη λίστα."
          : "Choose a station from the suggestions.",
      });
      return;
    }
    const fields =
      kind === "drivers"
        ? ["code", "first_name", "last_name", "phone", "license_number"]
        : kind === "vehicles"
          ? ["code", "registration_plate", "bus_type", "capacity"]
          : ["code", "name_el", "name_en"];
    const body: Record<string, unknown> = { is_active: active };
    for (const key of fields) {
      const value = form[key]?.trim();
      if (value) body[key] = key === "capacity" ? Number(value) : value;
      else if (
        !isNew &&
        ["phone", "license_number", "capacity", "registration_plate"].includes(
          key,
        )
      )
        body[key] = null;
    }
    if (kind === "vehicles" && referenceOnly) body.registration_plate = null;
    if (kind !== "stations") body.home_station_id = homeRecord?.id ?? null;
    else body.is_depot = depot;
    if (!isNew) body.version = record.version;
    setBusy(true);
    try {
      const response = await apiFetch(
        `/api/v1/${kind}${isNew ? "" : "/" + record.id}`,
        { method: isNew ? "POST" : "PATCH", body: JSON.stringify(body) },
      );
      if (!response.ok) {
        const data = (await response.json()) as { detail: unknown };
        if (response.status === 422 && Array.isArray(data.detail)) {
          const errors: Record<string, string> = {};
          for (const issue of data.detail as {
            loc: (string | number)[];
            msg: string;
          }[])
            errors[String(issue.loc.at(-1))] = el
              ? "Ελέγξτε αυτό το πεδίο."
              : "Please check this field.";
          setFieldErrors(errors);
        }
        const code =
          typeof data.detail === "object" &&
          data.detail !== null &&
          "code" in data.detail
            ? String(data.detail.code)
            : "";
        const messages: Record<string, [string, string]> = {
          stale_version: [
            "Κάποιος ενημέρωσε αυτή την εγγραφή. Κλείστε και ανοίξτε ξανά τα αποθηκευμένα στοιχεία για έλεγχο.",
            "Someone updated this record. Close and reopen it to review the saved details.",
          ],
          reference_exists: [
            "Αυτή η αναφορά ή πινακίδα υπάρχει ήδη. Ανοίξτε την υπάρχουσα εγγραφή ή χρησιμοποιήστε διαφορετική αναφορά.",
            "This reference or registration already exists. Open the existing record or use a different reference.",
          ],
          upcoming_pairings: [
            "Αφαιρέστε την εγγραφή από τα σημερινά και μελλοντικά ζεύγη πριν την αρχειοθετήσετε.",
            "Remove this record from current and upcoming daily pairings before archiving it.",
          ],
          station_timetable_in_use: [
            "Ενημερώστε τα ενεργά δρομολόγια ώστε να χρησιμοποιούν άλλον σταθμό πριν τον αρχειοθετήσετε.",
            "Update active timetables to use another station before archiving this station.",
          ],
          station_in_use: [
            "Μεταφέρετε τους ενεργούς οδηγούς και τα οχήματα σε άλλη έδρα πριν αρχειοθετήσετε αυτόν τον σταθμό.",
            "Move active drivers and vehicles to another home base before archiving this station.",
          ],
          driver_account_linked: [
            "Αφαιρέστε τη σύνδεση του ενεργού λογαριασμού αυτού του οδηγού πριν τον αρχειοθετήσετε.",
            "Remove this driver’s active account link before archiving the driver.",
          ],
        };
        setError(
          messages[code]?.[lang] ??
            (el
              ? "Ελέγξτε τα στοιχεία σας. Οι αλλαγές δεν αποθηκεύτηκαν."
              : "Check your details. Your changes have not been saved."),
        );
        return;
      }
      const saved = (await response.json()) as Resource;
      onSaved(saved);
    } catch {
      setError(
        el
          ? "Δεν μπορέσαμε να συνδεθούμε. Τα στοιχεία σας παραμένουν εδώ για νέα προσπάθεια."
          : "We could not connect. Your entries are still here so you can try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="resource-dialog"
      aria-labelledby="resource-form-title"
      onCancel={(e) => {
        e.preventDefault();
        closeGuarded();
      }}
    >
      <form onSubmit={submit}>
        <header>
          <div>
            <span className="resource-eyebrow">
              {isNew
                ? el
                  ? "ΝΕΑ ΕΓΓΡΑΦΗ"
                  : "NEW RECORD"
                : el
                  ? "ΕΠΕΞΕΡΓΑΣΙΑ"
                  : "EDIT RECORD"}
            </span>
            <h2 id="resource-form-title">
              {isNew
                ? title.add[lang]
                : el
                  ? `Στοιχεία ${title.singular[0]}`
                  : `Edit ${title.singular[1]}`}
            </h2>
          </div>
          <button
            className="icon-button"
            disabled={busy}
            onClick={closeGuarded}
            type="button"
            aria-label={el ? "Κλείσιμο" : "Close"}
          >
            <X size={18} />
          </button>
        </header>
        <div className="resource-form-body">
          <p className="resource-form-intro">
            {el
              ? "Συμπληρώστε τα βασικά. Μπορείτε να προσθέσετε περισσότερα στοιχεία αργότερα."
              : "Start with the essentials. You can add more details later."}
          </p>
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}
          {kind === "drivers" ? (
            <div className="resource-form-grid">
              {field("first_name", el ? "Όνομα" : "First name", true)}
              {field("last_name", el ? "Επώνυμο" : "Last name", true)}
            </div>
          ) : kind === "vehicles" ? (
            <>
              {referenceOnly
                ? field("code", el ? "Αναφορά στόλου" : "Fleet reference", true)
                : field(
                    "registration_plate",
                    el ? "Αριθμός κυκλοφορίας" : "Registration",
                    true,
                  )}
              <label className="resource-checkbox">
                <input
                  type="checkbox"
                  checked={referenceOnly}
                  onChange={(e) => setReferenceOnly(e.target.checked)}
                />
                {el
                  ? "Χρήση αναφοράς στόλου αντί πινακίδας"
                  : "Use a fleet reference instead of a registration"}
              </label>
              {field(
                "bus_type",
                el ? "Τύπος οχήματος" : "Vehicle type",
                true,
                "text",
                el
                  ? "Η κατηγορία του στόλου σας για την επιλογή κατάλληλων δρομολογίων."
                  : "Your fleet category, used to match suitable trips.",
              )}
            </>
          ) : (
            field("name_el", el ? "Όνομα σταθμού" : "Station name", true)
          )}
          <details className="resource-details">
            <summary>
              {el
                ? "Πρόσθετα στοιχεία (προαιρετικά)"
                : "Additional details (optional)"}
            </summary>
            {kind === "drivers" ? (
              <>
                {field(
                  "code",
                  el ? "Αναφορά προσωπικού" : "Staff reference",
                  false,
                  "text",
                  el
                    ? "Αν μείνει κενό, θα δημιουργηθεί αυτόματα."
                    : "Leave blank to generate a reference automatically.",
                )}
                {field("phone", el ? "Τηλέφωνο" : "Phone", false, "tel")}
                {field(
                  "license_number",
                  el ? "Αριθμός άδειας" : "License number",
                )}
              </>
            ) : kind === "vehicles" ? (
              field(
                "capacity",
                el ? "Αριθμός θέσεων" : "Seats",
                false,
                "number",
                el
                  ? "Αφήστε κενό αν δεν γνωρίζετε."
                  : "Leave blank if you do not know.",
              )
            ) : (
              <>
                {field("code", el ? "Αναφορά σταθμού" : "Station reference")}
                {field("name_en", el ? "Αγγλική ονομασία" : "English name")}
                <label className="resource-checkbox">
                  <input
                    type="checkbox"
                    checked={depot}
                    onChange={(e) => setDepot(e.target.checked)}
                  />
                  {el ? "Είναι αμαξοστάσιο" : "This is a depot"}
                </label>
              </>
            )}
            {kind !== "stations" && (
              <div className="resource-field">
                <label htmlFor="home-station">
                  {el ? "Έδρα" : "Home base"}
                  <span>{el ? "προαιρετικό" : "optional"}</span>
                </label>
                <input
                  id="home-station"
                  list="station-suggestions"
                  value={home}
                  onChange={(e) => {
                    setHome(e.target.value);
                    setFieldErrors({});
                  }}
                  placeholder={el ? "Αναζήτηση σταθμού…" : "Search stations…"}
                  aria-invalid={!!fieldErrors.home_station_id}
                />
                <datalist id="station-suggestions">
                  {stations.map((s) => (
                    <option
                      key={s.id}
                      value={`${el ? s.name_el : s.name_en} · ${s.code}`}
                    />
                  ))}
                </datalist>
                {fieldErrors.home_station_id && (
                  <small className="field-error">
                    {fieldErrors.home_station_id}
                  </small>
                )}
                <small>
                  {el
                    ? "Προσθέστε σταθμούς από τη διαχείριση σταθμών, όταν χρειαστεί."
                    : "Add stations from Manage stations when you need them."}
                </small>
              </div>
            )}
          </details>
          {!isNew && (
            <label className="resource-checkbox">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
              {el
                ? "Ενεργό για μελλοντικό προγραμματισμό"
                : "Active for future planning"}
            </label>
          )}
          {!isNew && kind === "drivers" && user?.permissions.includes("members.manage") && (
            <DriverAccess driverId={record.id} driverName={`${record.first_name ?? ""} ${record.last_name ?? ""}`.trim()} />
          )}
        </div>
        <footer>
          <button
            type="button"
            className="button secondary"
            onClick={closeGuarded}
            disabled={busy}
          >
            {el ? "Ακύρωση" : "Cancel"}
          </button>
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? (el ? "Αποθήκευση…" : "Saving…") : title.save[lang]}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
