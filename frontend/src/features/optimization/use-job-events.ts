"use client";
import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/context";
import { useAuth } from "../auth/AuthContext";
import type { Verification } from "../scheduling/revision-api";
export interface JobCandidate {
  id: string;
  assignments: Array<{ trip_id: string; resource_id: string }>;
  metrics: {
    assigned_trips_count: number;
    unassigned_trips_count: number;
    resource_count: number;
    total_driving_minutes: number;
    total_idle_minutes: number;
  };
  verification: Verification;
  solver_version: string;
  iteration: number;
}
export interface UseJobEventsState {
  status: string;
  snapshotId: string | null;
  runId: string | null;
  progressPct: number;
  candidates: JobCandidate[];
  error: string | null;
  isConnected: boolean;
}
const initial: UseJobEventsState = {
  status: "loading",
  snapshotId: null,
  runId: null,
  progressPct: 0,
  candidates: [],
  error: null,
  isConnected: false,
};
export function useJobEvents(
  jobId: string | null,
  expectedSnapshotId?: string | null,
): UseJobEventsState {
  const { apiFetch, isAuthenticated } = useAuth();
  const { locale } = useI18n();
  const [state, setState] = useState(initial);
  useEffect(() => {
    setState(initial);
    if (!jobId || !isAuthenticated || expectedSnapshotId === null) return;
    const abort = new AbortController();
    let cursor = 0;
    let terminal = false;
    let inFlight: Promise<void> | null = null;
    const unavailable = (
      message: string,
      snapshotId = expectedSnapshotId ?? null,
    ) => {
      terminal = true;
      if (!abort.signal.aborted)
        setState({
          ...initial,
          runId: jobId,
          snapshotId,
          status: "unavailable",
          error: message,
        });
    };
    const readState = async () => {
      const [run, earlierCandidates] = await Promise.all([
        apiFetch(`/api/optimization/runs/${jobId}`, { signal: abort.signal }),
        apiFetch(`/api/optimization/runs/${jobId}/candidates`, {
          signal: abort.signal,
        }),
      ]);
      if (run.status === 404) {
        unavailable(
          locale === "el"
            ? "Η αποθηκευμένη αναζήτηση δεν είναι διαθέσιμη. Μπορείτε να ξεκινήσετε νέα εκτέλεση."
            : "This saved search is unavailable. You can start a new run.",
        );
        return;
      }
      if (!run.ok)
        throw new Error(
          locale === "el"
            ? "Δεν ήταν δυνατός ο έλεγχος της αναζήτησης. Γίνεται επανασύνδεση."
            : "The search status could not be checked. Reconnecting.",
        );
      const r = (await run.json()) as {
        status: string;
        snapshot_id: string;
        progress_pct?: number;
        error_message?: string;
      };
      if (expectedSnapshotId && r.snapshot_id !== expectedSnapshotId) {
        unavailable(
          locale === "el"
            ? "Αυτή η αναζήτηση αφορά άλλο πρόγραμμα. Ξεκινήστε νέα εκτέλεση για αυτή την ημέρα."
            : "This search belongs to another schedule. Start a new run for this day.",
          r.snapshot_id,
        );
        return;
      }
      // A terminal status must be observed before reading its final candidates.
      // Parallel reads can otherwise retain an earlier empty list permanently.
      const candidates = ["completed", "failed", "cancelled"].includes(r.status)
        ? await apiFetch(`/api/optimization/runs/${jobId}/candidates`, {
            signal: abort.signal,
          })
        : earlierCandidates;
      if (!candidates.ok)
        throw new Error(
          locale === "el"
            ? "Δεν ανακτήθηκαν οι προτάσεις. Γίνεται νέα προσπάθεια."
            : "Proposals could not be retrieved. Retrying.",
        );
      const c = (await candidates.json()) as { candidates: JobCandidate[] };
      terminal = ["completed", "failed", "cancelled"].includes(r.status);
      if (!abort.signal.aborted)
        setState((prev) => ({
          ...prev,
          status: r.status,
          snapshotId: r.snapshot_id,
          runId: jobId,
          progressPct: r.progress_pct ?? 0,
          candidates: c.candidates ?? [],
          error: r.error_message ?? null,
        }));
    };
    const reconcile = async () => {
      if (inFlight) return inFlight;
      inFlight = readState();
      try {
        await inFlight;
      } finally {
        inFlight = null;
      }
    };
    const pause = () =>
      new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 1500);
        abort.signal.addEventListener(
          "abort",
          () => {
            clearTimeout(timer);
            resolve();
          },
          { once: true },
        );
      });
    const stream = async () => {
      while (!abort.signal.aborted && !terminal) {
        try {
          await reconcile();
          if (terminal) break;
          const response = await apiFetch(`/api/events?cursor=${cursor}`, {
            headers: { Accept: "text/event-stream" },
            signal: abort.signal,
          });
          if (!response.ok || !response.body)
            throw new Error("Progress stream unavailable");
          setState((prev) => ({ ...prev, isConnected: true }));
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          try {
            while (!abort.signal.aborted && !terminal) {
              const { done, value } = await reader.read();
              if (done) break;
              buffer += decoder
                .decode(value, { stream: true })
                .replace(/\r\n/g, "\n");
              let boundary: number;
              while ((boundary = buffer.indexOf("\n\n")) >= 0) {
                const frame = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);
                const id = Number(
                  frame
                    .split("\n")
                    .find((l) => l.startsWith("id:"))
                    ?.slice(3)
                    .trim(),
                );
                if (!id || id <= cursor) continue;
                cursor = id;
                const data = frame
                  .split("\n")
                  .filter((l) => l.startsWith("data:"))
                  .map((l) => l.slice(5).trim())
                  .join("\n");
                if (!data) continue;
                const event = JSON.parse(data) as {
                  job_id?: string;
                  progress_pct?: number;
                  status?: string;
                };
                if (event.job_id !== jobId) continue;
                // REST is authoritative for both intermediate and terminal candidates.
                await reconcile();
              }
              if (buffer.length > 1_000_000)
                throw new Error("Oversized event stream");
            }
          } finally {
            await reader.cancel().catch(() => undefined);
          }
        } catch (e) {
          if (!abort.signal.aborted)
            setState((prev) => ({
              ...prev,
              error:
                e instanceof Error
                  ? e.message
                  : "Progress connection interrupted",
            }));
        } finally {
          if (!abort.signal.aborted)
            setState((prev) => ({ ...prev, isConnected: false }));
        }
        if (!terminal && !abort.signal.aborted) await pause();
      }
    };
    void stream();
    // Reconcile even when a proxy silently drops events but keeps the stream open.
    const poll = setInterval(() => {
      if (!terminal) void reconcile().catch(() => undefined);
    }, 4000);
    return () => {
      abort.abort();
      clearInterval(poll);
    };
  }, [jobId, expectedSnapshotId, isAuthenticated, apiFetch, locale]);
  return state;
}
