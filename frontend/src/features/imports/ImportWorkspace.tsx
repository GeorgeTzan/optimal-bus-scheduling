"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowLeft,
  UploadCloud,
  Download,
  Check,
  FileSpreadsheet,
  UsersRound,
  BusFront,
  Route,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { writeWorkspaceUrl } from "../navigation/workspace-location";
import { RowEditor } from "./RowEditor";
import {
  rowLabel,
  destinations,
  entityNames,
  importResponse,
  type Batch,
  type Capabilities,
  type Cell,
  type Destination,
  type Entity,
  type ImportRow,
} from "./contracts";

export function ImportWorkspace({
  onOpen,
  initialEntity = "drivers",
  returnTo = null,
}: {
  onOpen: (tab: Destination) => void;
  initialEntity?: Entity | "all";
  returnTo?: Destination | null;
}) {
  const { apiFetch, user } = useAuth(),
    { locale } = useI18n(),
    el = locale === "el";
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [entity, setEntity] = useState<Entity | "all">(initialEntity),
    [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null),
    [history, setHistory] = useState<Batch[]>([]);
  const [busy, setBusy] = useState(false),
    [initializing, setInitializing] = useState(true),
    [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState(false),
    [editing, setEditing] = useState<ImportRow | null>(null),
    [rowError, setRowError] = useState<string | null>(null);
  const [filter, setFilter] = useState(""),
    [page, setPage] = useState(1);
  const heading = useRef<HTMLHeadingElement>(null);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  useEffect(() => {
    if (!batch) setEntity(initialEntity);
  }, [initialEntity, batch]);
  useEffect(() => {
    if (initializing || batch || !capabilities || !user?.permissions.includes("imports.write")) return;
    const allowed = capabilities.write_entities;
    const selectedAllowed = entity === "all" ? allowed.length === capabilities.entities.length : allowed.includes(entity);
    if (!selectedAllowed && allowed.length) {
      const next = allowed.includes("timetable") ? "timetable" : allowed[0];
      if (!next) return;
      setEntity(next);
      const url = new URL(window.location.href);
      url.searchParams.set("entity", next);
      writeWorkspaceUrl(url, true);
    }
  }, [batch, capabilities, entity, initializing, user]);
  const returnLabel = returnTo
    ? {
        drivers: ["Επιστροφή στους οδηγούς", "Return to drivers"],
        fleet: ["Επιστροφή στον στόλο", "Return to fleet"],
        timetables: ["Επιστροφή στα δρομολόγια", "Return to timetables"],
        planning: ["Επιστροφή στην ημέρα υπηρεσίας", "Return to service day"],
      }[returnTo][el ? 0 : 1]
    : null;
  const chooseEntity = (kind: Entity | "all") => {
    setEntity(kind);
    setFile(null);
    const url = new URL(window.location.href);
    url.searchParams.set("entity", kind);
    writeWorkspaceUrl(url, true);
  };
  const canWrite = !!user?.permissions.includes("imports.write");
  const name = (kind: Entity) => entityNames[kind][el ? 0 : 1];
  const remember = (saved: Batch) => {
    if (!active.current) return;
    setBatch(saved);
    setEntity(saved.entities.length === 1 ? saved.entities[0]! : "all");
    setSummary(false);
    setError(null);
    const url = new URL(window.location.href);
    url.searchParams.set("view", "imports");
    url.searchParams.set("batch", saved.batch_id);
    url.searchParams.set(
      "entity",
      saved.entities.length === 1 ? saved.entities[0]! : "all",
    );
    window.history.replaceState(null, "", url);
  };
  const load = useCallback(
    async (id: string, currentPage = 1, action = "", signal?: AbortSignal) => {
      const response = await apiFetch(
        `/api/v1/imports/${encodeURIComponent(id)}?locale=${locale}&page=${currentPage}${action ? `&action=${action}` : ""}`,
        { signal },
      );
      return importResponse<Batch>(response, el);
    },
    [apiFetch, locale, el],
  );
  useEffect(() => {
    const controller = new AbortController();
    setInitializing(true);
    void (async () => {
      const [caps, recent] = await Promise.all([
        apiFetch(`/api/v1/imports/capabilities?locale=${locale}`, {
          signal: controller.signal,
        }).then((r) => importResponse<Capabilities>(r, el)),
        apiFetch("/api/v1/imports?page_size=10", {
          signal: controller.signal,
        }).then((r) => importResponse<{ items: Batch[] }>(r, el)),
      ]);
      if (controller.signal.aborted) return;
      setCapabilities(caps);
      setHistory(recent.items);
      const id = new URL(window.location.href).searchParams.get("batch");
      if (id) {
        const saved = await load(id, 1, "", controller.signal);
        if (!controller.signal.aborted) {
          setBatch(saved);
          setEntity(saved.entities.length === 1 ? saved.entities[0]! : "all");
          setPage(1);
          setFilter("");
        }
      }
    })()
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setInitializing(false);
      });
    return () => controller.abort();
  }, [apiFetch, locale, el, load]);
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file || !capabilities) return;
    if (file.size > capabilities.limits.max_upload_bytes) {
      setError(
        el
          ? "Το αρχείο είναι πολύ μεγάλο. Χωρίστε το σε μικρότερα αρχεία."
          : "This file is too large. Split it into smaller files.",
      );
      return;
    }
    await perform(async () => {
      const body = new FormData();
      body.append("file", file);
      body.append("entity", entity);
      body.append("locale", locale);
      remember(
        await importResponse<Batch>(
          await apiFetch("/api/v1/imports", { method: "POST", body }),
          el,
        ),
      );
      setPage(1);
      setFilter("");
      requestAnimationFrame(() => heading.current?.focus());
    });
  }
  async function download(url: string, fallback: string) {
    await perform(async () => {
      const response = await apiFetch(url);
      if (!response.ok) {
        await importResponse(response, el);
        return;
      }
      const blob = URL.createObjectURL(await response.blob()),
        anchor = document.createElement("a");
      anchor.href = blob;
      anchor.download =
        response.headers
          .get("content-disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ?? fallback;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(blob), 1000);
    });
  }
  async function mutate(operation: "refresh" | "commit" | "discard") {
    if (!batch) return;
    await perform(async () => {
      const saved = await importResponse<Batch>(
        await apiFetch(`/api/v1/imports/${batch.batch_id}/${operation}`, {
          method: "POST",
          body: JSON.stringify({ version: batch.version }),
        }),
        el,
      );
      remember(saved);
      setPage(1);
      setFilter("");
      requestAnimationFrame(() => heading.current?.focus());
    });
  }
  async function correct(
    values: Record<string, Cell>,
    resolution?: Record<string, unknown>,
    stations?: Record<string, unknown>[],
  ) {
    if (!batch || !editing) return;
    setBusy(true);
    setRowError(null);
    try {
      const rows =
        Object.keys(values).length || resolution
          ? [
              {
                row_id: editing.row_id,
                values,
                ...(resolution ? { resolution } : {}),
              },
            ]
          : [];
      const saved = await importResponse<Batch>(
        await apiFetch(`/api/v1/imports/${batch.batch_id}/rows`, {
          method: "PATCH",
          body: JSON.stringify({
            version: batch.version,
            rows,
            ...(stations ? { stations } : {}),
          }),
        }),
        el,
      );
      remember(saved);
      setPage(1);
      setFilter("");
      setEditing(null);
    } catch (reason) {
      setRowError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  async function browse(next: number, action = filter) {
    if (!batch) return;
    await perform(async () => {
      setBatch(await load(batch.batch_id, next, action));
      setPage(next);
      setFilter(action);
    });
  }
  function startAgain() {
    setBatch(null);
    setFile(null);
    setSummary(false);
    setError(null);
    setPage(1);
    setFilter("");
    const url = new URL(window.location.href);
    url.searchParams.delete("batch");
    window.history.replaceState(null, "", url);
    void apiFetch("/api/v1/imports?page_size=10")
      .then((r) => importResponse<{ items: Batch[] }>(r, el))
      .then((data) => setHistory(data.items))
      .catch(() => undefined);
  }
  if (!user?.permissions.includes("imports.read"))
    return (
      <section className="resource-empty">
        <h1>{el ? "Εισαγωγή στοιχείων" : "Data imports"}</h1>
        <p>
          {el
            ? "Ο διαχειριστής σας μπορεί να δώσει πρόσβαση στην εισαγωγή στοιχείων."
            : "Your administrator can give you access to data imports."}
        </p>
      </section>
    );
  const committed = batch?.status === "committed",
    inactive = batch && ["purged", "discarded"].includes(batch.status);
  const total = batch?.result ?? batch?.summary;
  const step = !batch ? 0 : committed ? 3 : summary ? 2 : 1;
  const headline = !batch
    ? el
      ? "Τα στοιχεία σας, σε έναν χώρο"
      : "Bring your records together"
    : committed
      ? el
        ? "Τα στοιχεία σας αποθηκεύτηκαν"
        : "Your records are saved"
      : summary
        ? el
          ? "Έτοιμα για αποθήκευση"
          : "Ready to save"
        : el
          ? "Ελέγξτε τα στοιχεία σας"
          : "Review your records";
  const primaryEntities: Entity[] = ["drivers", "vehicles", "timetable"];
  return (
    <section className="import-workspace" aria-busy={busy || initializing}>
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "ΕΙΣΑΓΩΓΗ ΣΤΟΙΧΕΙΩΝ" : "DATA IMPORTS"}
          </span>
          <h1 ref={heading} tabIndex={-1}>
            {headline}
          </h1>
          <p>
            {!batch
              ? el
                ? "Ξεκινήστε με όσα γνωρίζετε. Θα ελέγξουμε το αρχείο μαζί, πριν αποθηκευτεί οτιδήποτε."
                : "Start with what you know. Review your file here before anything enters your register."
              : batch.filename ||
                (el
                  ? "Το αντίγραφο του αρχείου δεν είναι πλέον διαθέσιμο."
                  : "The source copy is no longer available.")}
          </p>
        </div>
        {returnTo && !committed && (
          <button className="button secondary" onClick={() => onOpen(returnTo)}>
            <ArrowLeft size={15} />
            {returnLabel}
          </button>
        )}
        {batch && (
          <button
            className="button secondary"
            disabled={busy}
            onClick={startAgain}
          >
            <ArrowLeft size={15} />
            {el ? "Όλες οι εισαγωγές" : "All imports"}
          </button>
        )}
      </header>
      <ol
        className="import-steps"
        aria-label={el ? "Βήματα εισαγωγής" : "Import steps"}
      >
        {(el
          ? ["Επιλογή & αρχείο", "Έλεγχος", "Σύνοψη", "Συνέχεια"]
          : ["Choose & upload", "Review", "Summary", "Continue"]
        ).map((label, i) => (
          <li
            key={label}
            className={i === step ? "current" : i < step ? "done" : ""}
            aria-current={i === step ? "step" : undefined}
          >
            <span>{i < step ? <Check size={13} /> : i + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      {error && (
        <div className="import-alert" role="alert">
          <p>{error}</p>
          {batch && !committed && !inactive && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => void mutate("refresh")}
            >
              <RefreshCw size={14} />
              {el ? "Ανανέωση προεπισκόπησης" : "Refresh preview"}
            </button>
          )}
        </div>
      )}
      {(busy || initializing) && (
        <p className="import-working" role="status">
          {initializing
            ? el
              ? "Φόρτωση των στοιχείων σας…"
              : "Loading your records…"
            : el
              ? "Επεξεργασία… Μπορεί να χρειαστούν λίγα δευτερόλεπτα."
              : "Working… This may take a few seconds."}
        </p>
      )}
      {!batch && !initializing && (
        <>
          <div className="import-layout">
            <div className="import-card">
              <span className="resource-eyebrow">
                {el
                  ? "1 · ΤΙ ΘΑ ΠΡΟΣΘΕΣΕΤΕ;"
                  : "1 · WHAT WOULD YOU LIKE TO ADD?"}
              </span>
              <div className="import-choices">
                {primaryEntities.map((kind, i) => {
                  const Icon = [UsersRound, BusFront, Route][i]!;
                  return (
                    <button
                      key={kind}
                      aria-label={name(kind)}
                      className={entity === kind ? "selected" : ""}
                      aria-pressed={entity === kind}
                      disabled={
                        !capabilities?.write_entities.includes(kind) || busy
                      }
                      onClick={() => {
                        chooseEntity(kind);
                      }}
                    >
                      <Icon size={21} />
                      <strong>{name(kind)}</strong>
                      <span>
                        {kind === "drivers"
                          ? el
                            ? "Ονοματεπώνυμο"
                            : "First and last names"
                          : kind === "vehicles"
                            ? el
                              ? "Πινακίδα ή κωδικός & τύπος"
                              : "Registration or reference & type"
                            : el
                              ? "Διαδρομές, ώρες & ημέρες"
                              : "Routes, times & operating days"}
                      </span>
                    </button>
                  );
                })}
              </div>
              <details className="import-more">
                <summary>
                  {el
                    ? "Σταθμοί, συνδέσεις ή πλήρες αρχείο"
                    : "Stations, connections or a complete workbook"}
                </summary>
                <div className="import-other-choices">
                  {(
                    [
                      "stations",
                      "pairings",
                      "transfers",
                      "connections",
                      "all",
                    ] as const
                  ).map((kind) => (
                    <button
                      className="button secondary"
                      aria-pressed={entity === kind}
                      key={kind}
                      disabled={
                        busy ||
                        (kind === "all"
                          ? capabilities?.write_entities.length !==
                            capabilities?.entities.length
                          : !capabilities?.write_entities.includes(kind))
                      }
                      onClick={() => {
                        chooseEntity(kind);
                      }}
                    >
                      {kind === "all"
                        ? el
                          ? "Πλήρες βιβλίο"
                          : "Complete workbook"
                        : name(kind)}
                    </button>
                  ))}
                </div>
              </details>
              <div className="import-template">
                <FileSpreadsheet size={25} />
                <div>
                  <strong>
                    {entity === "all"
                      ? el
                        ? "Πλήρες βιβλίο"
                        : "Complete workbook"
                      : name(entity)}
                  </strong>
                  <p>
                    {el
                      ? "Κατεβάστε το δικό μας πρότυπο και συμπληρώστε τις επισημασμένες στήλες."
                      : "Download our template and fill in the required columns."}
                  </p>
                </div>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    void download(
                      `/api/v1/imports/templates/${entity}?locale=${locale}`,
                      `ktel-${entity}.xlsx`,
                    )
                  }
                >
                  <Download size={15} />
                  {el ? "Πρότυπο Excel" : "Download Excel template"}
                </button>
              </div>
              {entity !== "all" && (
                <button
                  className="import-text-button"
                  disabled={busy}
                  onClick={() =>
                    void download(
                      `/api/v1/imports/templates/${entity}?locale=${locale}&format=csv`,
                      `ktel-${entity}.csv`,
                    )
                  }
                >
                  {el
                    ? "Εναλλακτικά, πρότυπο CSV"
                    : "Or download a CSV template"}
                </button>
              )}
              <div className="import-upload">
                <UploadCloud size={29} />
                <label htmlFor="import-file">
                  {el ? "Επιλέξτε το αρχείο σας" : "Choose your file"}
                </label>
                <input
                  id="import-file"
                  type="file"
                  accept=".xlsx,.csv"
                  disabled={busy || !canWrite}
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    setError(null);
                  }}
                />
                <p>
                  {el ? "XLSX ή CSV" : "XLSX or CSV"} ·{" "}
                  {capabilities?.limits.max_rows.toLocaleString(locale)}{" "}
                  {el ? "γραμμές ανά αρχείο" : "rows per file"} ·{" "}
                  {Math.round(
                    (capabilities?.limits.max_upload_bytes ?? 0) / 1048576,
                  )}{" "}
                  MB
                </p>
                {file && <strong>{file.name}</strong>}
              </div>
              <footer className="import-actions">
                <span>
                  {el
                    ? "Δεν αποθηκεύεται τίποτα πριν τον έλεγχό σας."
                    : "Nothing is saved to your register until you approve it."}
                </span>
                <button
                  className="button primary"
                  disabled={!file || busy || !canWrite}
                  onClick={() => void upload()}
                >
                  {el ? "Έλεγχος αρχείου" : "Review file"}
                  <ArrowRight size={15} />
                </button>
              </footer>
            </div>
            <aside className="import-guidance">
              <span className="resource-eyebrow">
                {el ? "ΕΝΑ ΒΗΜΑ ΤΗ ΦΟΡΑ" : "ONE STEP AT A TIME"}
              </span>
              <h2>
                {el
                  ? "Δεν χρειάζονται όλα από την αρχή."
                  : "You don’t need everything today."}
              </h2>
              <p>
                {el
                  ? "Ξεκινήστε με ένα μικρό αρχείο. Τα προαιρετικά στοιχεία μπορούν να προστεθούν αργότερα."
                  : "Start with a small file. Optional details can be added later."}
              </p>
              <ul>
                <li>
                  {el
                    ? "Κρατήστε τους κωδικούς ως κείμενο, μαζί με τα αρχικά μηδενικά."
                    : "Keep references as text, including leading zeroes."}
                </li>
                <li>
                  {el
                    ? "Επικολλήστε τιμές, αντί για τύπους Excel."
                    : "Paste values rather than Excel formulas."}
                </li>
                <li>
                  {el
                    ? "Χωρίστε μεγαλύτερα αρχεία σε μικρότερα μέρη."
                    : "Split larger registers into smaller files."}
                </li>
              </ul>
              {entity !== "all" && (
                <>
                  <hr />
                  <h3>{el ? "Μόνο λίγες εγγραφές;" : "Just a few records?"}</h3>
                  <p>
                    {el
                      ? "Μπορείτε να τα προσθέσετε απευθείας."
                      : "You can add them directly instead."}
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => onOpen(destinations[entity])}
                  >
                    {el ? "Χειροκίνητη καταχώριση" : "Enter records manually"}
                    <ArrowRight size={14} />
                  </button>
                </>
              )}
            </aside>
          </div>
          {!!history.length && (
            <div className="import-card import-history">
              <h2>
                {el ? "Οι πρόσφατες εισαγωγές σας" : "Your recent imports"}
              </h2>
              <p>
                {el
                  ? "Συνεχίστε από εκεί που σταματήσατε."
                  : "Pick up where you left off."}
              </p>
              {history.map((item) => (
                <button
                  key={item.batch_id}
                  disabled={busy}
                  onClick={() =>
                    void perform(async () =>
                      remember(await load(item.batch_id)),
                    )
                  }
                >
                  <FileSpreadsheet size={19} />
                  <span>
                    <strong>
                      {item.filename ||
                        (el ? "Αρχειοθετημένη εισαγωγή" : "Archived import")}
                    </strong>
                    <small>
                      {item.row_count} {el ? "γραμμές" : "rows"} ·{" "}
                      {new Date(
                        item.created_at ?? item.expires_at,
                      ).toLocaleDateString(locale)}
                    </small>
                  </span>
                  <span className="status-chip">
                    {item.status === "committed"
                      ? el
                        ? "Αποθηκεύτηκε"
                        : "Saved"
                      : ["discarded", "purged"].includes(item.status)
                        ? el
                          ? "Έκλεισε"
                          : "Closed"
                        : el
                          ? "Συνέχεια ελέγχου"
                          : "Continue review"}
                  </span>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {batch && total && (
        <>
          <div className="import-counts">
            {[
              [el ? "Νέες εγγραφές" : "New records", total.new],
              [el ? "Ενημερώσεις" : "Updates", total.updated],
              [el ? "Χωρίς αλλαγή" : "Unchanged", total.unchanged],
              [
                el ? "Χρειάζονται έλεγχο" : "Need attention",
                total.invalid + total.needs_match,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          {inactive ? (
            <div className="import-card">
              <h2>
                {el
                  ? "Αυτή η εισαγωγή έχει κλείσει."
                  : "This import is closed."}
              </h2>
              <p>
                {el
                  ? "Δεν διαγράφηκαν στοιχεία από το μητρώο σας."
                  : "No records were deleted from your register."}
              </p>
              <button className="button primary" onClick={startAgain}>
                {el ? "Επιλογή νέου αρχείου" : "Choose another file"}
              </button>
            </div>
          ) : committed ? (
            <div className="import-card import-success">
              <span className="import-success-icon">
                <Check size={29} />
              </span>
              <h2>
                {el
                  ? "Έτοιμα για το επόμενο βήμα."
                  : "Ready for the next step."}
              </h2>
              <p>
                {el
                  ? "Οι αλλαγές αποθηκεύτηκαν. Μπορείτε να συνεχίσετε όποτε θέλετε."
                  : "Your changes are saved. You can continue whenever you’re ready."}
              </p>
              {total.pairings_need_confirmation > 0 && (
                <p>
                  {el
                    ? "Τα εισαγόμενα ζεύγη χρειάζονται επιβεβαίωση στην ημέρα υπηρεσίας."
                    : "Imported pairings still need confirmation in Service day."}
                </p>
              )}
              <div className="import-actions">
                <button
                  className="button primary"
                  onClick={() =>
                    onOpen(
                      returnTo ?? destinations[batch.entities[0] ?? "drivers"],
                    )
                  }
                >
                  {returnLabel ??
                    (batch.entities[0] === "drivers"
                      ? el
                        ? "Προβολή οδηγών"
                        : "View drivers"
                      : el
                        ? "Προβολή στοιχείων"
                        : "View records")}
                  <ArrowRight size={15} />
                </button>
                {batch.raw_available && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() =>
                      void download(
                        `/api/v1/imports/${batch.batch_id}/populated.xlsx?locale=${locale}`,
                        "completed.xlsx",
                      )
                    }
                  >
                    <Download size={15} />
                    {el
                      ? "Λήψη συμπληρωμένου αρχείου"
                      : "Download completed workbook"}
                  </button>
                )}
              </div>
            </div>
          ) : summary ? (
            <div className="import-card import-confirm">
              <span className="resource-eyebrow">
                {el ? "Ο ΤΕΛΙΚΟΣ ΕΛΕΓΧΟΣ ΣΑΣ" : "YOUR FINAL CHECK"}
              </span>
              <h2>
                {el
                  ? "Αυτές οι αλλαγές θα αποθηκευτούν μαζί."
                  : "These changes will be saved together."}
              </h2>
              <div className="import-entity-summary">
                {Object.entries(total.by_entity).map(([kind, counts]) => (
                  <div key={kind}>
                    <strong>{name(kind as Entity)}</strong>
                    <span>
                      {counts.new} {el ? "νέες" : "new"} · {counts.updated}{" "}
                      {el ? "ενημερώσεις" : "updates"} · {counts.unchanged}{" "}
                      {el ? "χωρίς αλλαγή" : "unchanged"}
                    </span>
                  </div>
                ))}
              </div>
              {total.will_archive > 0 && (
                <p className="import-issues">
                  {total.will_archive}{" "}
                  {el
                    ? "εγγραφές θα αρχειοθετηθούν. Οι ενεργές συνδέσεις ελέγχονται ξανά κατά την αποθήκευση."
                    : "records will be archived. Active references are checked again when saving."}
                </p>
              )}
              <p>
                {el
                  ? "Εγγραφές που λείπουν από το αρχείο δεν διαγράφονται. Οι αλλαγές δεν επηρεάζουν το ιστορικό δημοσιευμένων προγραμμάτων."
                  : "Records missing from this file will be retained. Published schedule history stays intact."}
              </p>
              <footer className="import-actions">
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => setSummary(false)}
                >
                  {el ? "Πίσω στον έλεγχο" : "Back to review"}
                </button>
                <button
                  className="button primary"
                  disabled={busy || !canWrite || batch.status !== "ready"}
                  onClick={() => void mutate("commit")}
                >
                  {el ? "Αποθήκευση στοιχείων" : "Save records"}
                  <Check size={15} />
                </button>
              </footer>
            </div>
          ) : (
            <div className="import-card import-review">
              <div className="import-review-heading">
                <div>
                  <h2>{el ? "Μία γραμμή τη φορά." : "One row at a time."}</h2>
                  <p>
                    {el
                      ? "Οι διορθώσεις παραμένουν εδώ μέχρι να επιβεβαιώσετε την αποθήκευση."
                      : "Your corrections stay in this preview until you confirm the save."}
                  </p>
                </div>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => void mutate("refresh")}
                >
                  <RefreshCw size={14} />
                  {el ? "Ανανέωση" : "Refresh"}
                </button>
              </div>
              {!!batch.issues.length && (
                <div className="import-issues" role="alert">
                  {batch.issues.map((issue, i) => (
                    <p key={i}>
                      {issue.sheet} {issue.cell}: {issue.message}
                    </p>
                  ))}
                </div>
              )}
              {total.new_stations > 0 && (
                <details className="import-station-review">
                  <summary>
                    {total.new_stations}{" "}
                    {el
                      ? "νέοι σταθμοί από τις διαδρομές σας"
                      : "new stations from your routes"}
                  </summary>
                  <p>
                    {el
                      ? "Ελέγξτε ότι οι ονομασίες αντιστοιχούν σε διαφορετικούς σταθμούς. Μπορείτε να διορθώσετε τις γραμμές του αρχείου."
                      : "Check that these names belong to distinct stations. You can correct their source rows below."}
                  </p>
                  {batch.stations
                    .filter((station) => station.code)
                    .map((station, i) => (
                      <p key={i}>
                        <strong>{station.code}</strong> · {station.name_el}
                      </p>
                    ))}
                </details>
              )}
              <div
                className="import-filters"
                role="group"
                aria-label={el ? "Εμφάνιση γραμμών" : "Show rows"}
              >
                {[
                  ["", el ? "Όλες" : "All rows"],
                  ["invalid", el ? "Διορθώσεις" : "Corrections"],
                  ["resolve", el ? "Αντιστοιχίσεις" : "Matches"],
                  ["update", el ? "Ενημερώσεις" : "Updates"],
                ].map(([value, label]) => (
                  <button
                    className="button secondary"
                    key={value}
                    aria-pressed={filter === value}
                    disabled={busy}
                    onClick={() => void browse(1, value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="import-row-list">
                {batch.rows.map((row) => (
                  <button
                    key={row.row_id}
                    className="import-row"
                    disabled={busy || !canWrite}
                    aria-label={
                      el
                        ? `Έλεγχος γραμμής ${row.row}`
                        : `Review row ${row.row}`
                    }
                    onClick={() => {
                      setEditing(row);
                      setRowError(null);
                    }}
                  >
                    <span className={`import-row-state ${row.action}`}>
                      <FileSpreadsheet size={18} />
                    </span>
                    <span>
                      <strong>{rowLabel(row)}</strong>
                      <small>
                        {row.sheet} · {el ? "Γραμμή" : "Row"} {row.row} ·{" "}
                        {row.proposed_ref ??
                          (typeof row.raw.code === "string"
                            ? row.raw.code
                            : "")}
                      </small>
                      {row.issues.slice(0, 2).map((issue, i) => (
                        <span className="import-row-issue" key={i}>
                          {issue.cell}: {issue.message}
                        </span>
                      ))}
                      {row.changed_fields.length > 0 && (
                        <small>
                          {el ? "Αλλαγές: " : "Changes: "}
                          {row.changed_fields
                            .map(
                              (field) =>
                                capabilities?.columns[row.entity].find(
                                  (column) => column.key === field,
                                )?.label ?? field,
                            )
                            .join(", ")}
                        </small>
                      )}
                    </span>
                    <span className="status-chip">
                      {row.action === "new"
                        ? el
                          ? "Νέα"
                          : "New"
                        : row.action === "update"
                          ? el
                            ? "Ενημέρωση"
                            : "Update"
                          : row.action === "unchanged"
                            ? el
                              ? "Χωρίς αλλαγή"
                              : "Unchanged"
                            : el
                              ? "Έλεγχος"
                              : "Review"}
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
                {batch.rows.length === 0 && (
                  <p className="resource-help">
                    {el
                      ? "Δεν υπάρχουν γραμμές σε αυτή την κατηγορία."
                      : "No rows in this category."}
                  </p>
                )}
              </div>
              <div className="import-pagination">
                <span>
                  {batch.rows_total} {el ? "γραμμές" : "rows"} ·{" "}
                  {el ? "Σελίδα" : "Page"} {page}
                </span>
                <button
                  className="icon-button"
                  aria-label={el ? "Προηγούμενη σελίδα" : "Previous page"}
                  disabled={busy || page === 1}
                  onClick={() => void browse(page - 1)}
                >
                  <ChevronLeft size={17} />
                </button>
                <button
                  className="icon-button"
                  aria-label={el ? "Επόμενη σελίδα" : "Next page"}
                  disabled={busy || page * batch.page_size >= batch.rows_total}
                  onClick={() => void browse(page + 1)}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
              <footer className="import-actions">
                <div>
                  {(total.invalid + total.needs_match > 0 ||
                    batch.issues.length > 0) && (
                    <button
                      className="import-text-button"
                      disabled={busy}
                      onClick={() =>
                        void download(
                          `/api/v1/imports/${batch.batch_id}/errors.csv?locale=${locale}`,
                          "corrections.csv",
                        )
                      }
                    >
                      <Download size={14} />
                      {el
                        ? "Λήψη λίστας διορθώσεων"
                        : "Download correction list"}
                    </button>
                  )}
                  <button
                    className="import-text-button"
                    disabled={busy || !canWrite}
                    onClick={() => void mutate("discard")}
                  >
                    {el ? "Απόρριψη προεπισκόπησης" : "Discard preview"}
                  </button>
                </div>
                <button
                  className="button primary"
                  disabled={busy || !canWrite || batch.status !== "ready"}
                  onClick={() => {
                    setSummary(true);
                    requestAnimationFrame(() => heading.current?.focus());
                  }}
                >
                  {el ? "Συνέχεια στη σύνοψη" : "Continue to summary"}
                  <ArrowRight size={15} />
                </button>
              </footer>
            </div>
          )}
        </>
      )}
      {editing && capabilities && (
        <RowEditor
          row={editing}
          columns={capabilities.columns[editing.entity]}
          busy={busy}
          error={rowError}
          onSave={correct}
          onClose={() => {
            if (!busy) setEditing(null);
          }}
        />
      )}
    </section>
  );
}
