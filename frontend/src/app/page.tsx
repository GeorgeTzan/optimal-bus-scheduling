"use client";

import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
} from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../features/auth/AuthContext";
import { useI18n } from "../i18n/context";
import { ResourceWorkspace } from "../features/resources/ResourceWorkspace";
import { TimetableWorkspace } from "../features/timetables/TimetableWorkspace";
import { ServiceDayWorkspace } from "../features/timetables/ServiceDayWorkspace";
import { ImportWorkspace } from "../features/imports/ImportWorkspace";
import { newRequestId } from "../features/navigation/request-id";
import { useWorkspaceNavigation } from "../features/navigation/use-workspace-navigation";
import { StudioEntry } from "../features/scheduling/StudioEntry";
import { LoginForm } from "../features/auth/LoginForm";
import { Shell } from "../components/layout/Shell";
import { OperationsWorkspace } from "../features/operations/OperationsWorkspace";
import { OverviewWorkspace } from "../features/dashboard/OverviewWorkspace";
import { OfficeWorkspace } from "../features/office/OfficeWorkspace";
import { TeamWorkspace } from "../features/team/TeamWorkspace";
import { SchedulingStudio } from "../features/scheduling/SchedulingStudio";
import { useJobEvents } from "../features/optimization/use-job-events";
import {
  studioRevision,
  studioDisplay,
  studioTrips,
  studioResources,
  type PersistedRevision,
} from "../features/scheduling/revision-api";
import type { CandidatePlan } from "../features/scheduling/CandidateComparisonTray";

export default function HomePage() {
  const { isAuthenticated, user, loading, error, refreshIdentity } = useAuth();
  const { locale } = useI18n();
  if (loading)
    return (
      <div className="session-state" role="status">
        {locale === "el"
          ? "Προετοιμασία του χώρου εργασίας σας…"
          : "Opening your workspace…"}
      </div>
    );
  if (error && !user)
    return (
      <div className="session-state">
        <p role="alert">
          {locale === "el"
            ? "Δεν μπορέσαμε να συνδεθούμε. Δοκιμάστε ξανά."
            : "We could not connect. Please try again."}
        </p>
        <button
          className="btn-primary"
          onClick={() => void refreshIdentity().catch(() => undefined)}
        >
          {locale === "el" ? "Νέα προσπάθεια" : "Try again"}
        </button>
      </div>
    );
  if (!isAuthenticated || !user) return <LoginForm />;
  if (user.role === "driver") return <GoToDriverArea />;
  if (
    !user.permissions.includes("resources.read") &&
    !user.permissions.includes("schedule.read")
  )
    return (
      <Shell currentTab="dashboard" onTabChange={() => undefined}>
        <section className="resource-empty">
          <h1>
            {locale === "el"
              ? "Πρόσβαση στον χώρο εργασίας"
              : "Workspace access"}
          </h1>
          <p>
            {locale === "el"
              ? "Ο λογαριασμός σας δεν έχει πρόσβαση στον χώρο προγραμματισμού."
              : "Your account does not have access to the planning workspace."}
          </p>
          <p>
            {locale === "el"
              ? "Επικοινωνήστε με τον υπεύθυνο προγραμματισμού για βοήθεια."
              : "Contact your scheduling administrator for help."}
          </p>
        </section>
      </Shell>
    );
  // A new authenticated identity gets a fresh workspace; late responses cannot cross sessions.
  return <WorkspacePage key={`${user.id}:${user.sessionId}`} />;
}

function GoToDriverArea() {
  const router = useRouter();
  useEffect(() => { router.replace("/driver"); }, [router]);
  return <div className="session-state" role="status">…</div>;
}

function WorkspacePage() {
  const { isAuthenticated, apiFetch, user } = useAuth();
  const { locale } = useI18n();
  const isEl = locale === "el";

  const { location, navigate, navigationEpoch } = useWorkspaceNavigation();
  const activeTab = location.view;
  const serviceDate = location.serviceDate;
  const sourceKind =
    activeTab === "archive" ? "reference_archive" : "operational";
  const [opening, setOpening] = useState(false);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState<PersistedRevision | null>(null);
  const currentRevision = useRef<string | null>(null);
  currentRevision.current = revision?.revision_id ?? null;
  const [jobId, setJobId] = useState<string | null>(null);
  const pendingRun = useRef<{ signature: string; key: string } | null>(null);
  const job = useJobEvents(jobId, revision?.revision_id ?? null);
  const isOptimizing =
    !!jobId &&
    job.runId === jobId &&
    ["queued", "claimed", "running"].includes(job.status);
  const isRestoringRun =
    !!jobId && (job.runId !== jobId || job.status === "loading");
  useEffect(() => {
    if (
      !user?.permissions.includes("optimization.read") ||
      revision?.source_kind !== "operational"
    ) {
      setJobId(null);
      return;
    }
    try {
      setJobId(
        localStorage.getItem(`ktel_job_${user.ktelId}_${revision.revision_id}`),
      );
    } catch {
      setJobId(null);
    }
  }, [user, revision]);
  const [error, setError] = useState<string | null>(null);
  const [plans, setPlans] = useState<CandidatePlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const resources = useMemo(
    () => (revision ? studioResources(revision) : []),
    [revision],
  );
  const trips = useMemo(
    () => (revision ? studioTrips(revision) : []),
    [revision],
  );
  const displayContext = useMemo(
    () => (revision ? studioDisplay(revision) : undefined),
    [revision],
  );
  const reloadRevision = useCallback(
    async (signal?: AbortSignal) => {
      const epoch = navigationEpoch.current;
      const query = new URLSearchParams({ source_kind: sourceKind });
      if (serviceDate) query.set("service_date", serviceDate);
      const response = await apiFetch(
        `/api/v1/scheduling/revisions/active?${query.toString()}`,
        { signal },
      );
      if (signal?.aborted || navigationEpoch.current !== epoch) return;
      if (response.status === 404) {
        setRevision(null);
        return;
      }
      if (!response.ok)
        throw new Error(`Schedule retrieval failed (${response.status})`);
      const loaded = (await response.json()) as PersistedRevision;
      if (!signal?.aborted && navigationEpoch.current === epoch)
        setRevision(loaded);
    },
    [apiFetch, sourceKind, serviceDate, navigationEpoch],
  );

  useEffect(() => {
    if (
      !isAuthenticated ||
      !["dashboard", "scheduling", "archive"].includes(activeTab)
    )
      return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void reloadRevision(controller.signal)
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [isAuthenticated, reloadRevision, activeTab]);
  const selectServiceDate = (date: string, replace = false) => {
    if (!date) return false;
    const changed = navigate(activeTab, { serviceDate: date, replace });
    if (changed) setRevision(null);
    return changed;
  };
  const openServiceDay = (
    tab: "drivers" | "fleet" | "timetables" | "planning" | "imports",
    date?: string,
  ) => {
    if (date && user)
      localStorage.setItem(`ktel-service-date:${user.ktelId}:${user.id}`, date);
    navigate(tab, { serviceDate: date ?? serviceDate });
  };
  const openStudio = async (date: string) => {
    const epoch = navigationEpoch.current;
    setOpening(true);
    try {
      const response = await apiFetch("/api/v1/scheduling/revisions", {
        method: "POST",
        body: JSON.stringify({ service_date: date }),
      });
      if (!response.ok)
        throw Error(
          isEl
            ? "Τα στοιχεία της ημέρας χρειάζονται νέο έλεγχο. Επιστρέψτε στην προετοιμασία ημέρας."
            : "The day's inputs need another review. Return to Service day to check them.",
        );
      const saved = (await response.json()) as PersistedRevision;
      if (navigationEpoch.current !== epoch) return;
      setRevision(saved);
      setError(null);
      navigate("scheduling", { serviceDate: date, replace: true });
    } finally {
      setOpening(false);
    }
  };

  const mutateRevision = async (
    action: string,
    patches?: Array<{
      trip_id: string;
      new_resource_id: string;
      is_locked?: boolean;
    }>,
  ) => {
    if (!revision) return;
    const mutationEpoch = navigationEpoch.current;
    setError(null);
    const res = await apiFetch(
      `/api/v1/scheduling/revisions/${revision.revision_id}/${action}`,
      {
        method: "POST",
        body: JSON.stringify({
          version: revision.version,
          ...(patches ? { patches } : {}),
        }),
      },
    );
    if (!res.ok) {
      if (res.status === 409 && navigationEpoch.current === mutationEpoch)
        await reloadRevision();
      const data = (await res.json()) as {
        detail?: string | { message?: string };
      };
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : (data.detail?.message ?? `Schedule update failed (${res.status})`),
      );
    }
    const saved = (await res.json()) as PersistedRevision;
    if (currentRevision.current === saved.revision_id) setRevision(saved);
  };

  const handleRunCVSolver = async (iterations: number) => {
    if (!revision || !user) return;
    const snapshotId = revision.revision_id;
    const config = {
      iterations,
      seed: 42,
      time_limit_seconds: 120,
      cp_sat_workers: 1,
    };
    const signature = JSON.stringify({ snapshot_id: snapshotId, config });
    if (pendingRun.current?.signature !== signature) {
      try {
        pendingRun.current = { signature, key: newRequestId() };
      } catch {
        throw Error(
          isEl
            ? "Το πρόγραμμα περιήγησης δεν υποστηρίζει ασφαλές αίτημα. Ανοίξτε την εφαρμογή μέσω HTTPS ή localhost."
            : "Your browser cannot start a secure request. Open the application through HTTPS or localhost.",
        );
      }
    }
    let response: Response;
    try {
      response = await apiFetch("/api/optimization/runs", {
        method: "POST",
        body: JSON.stringify({
          snapshot_id: snapshotId,
          config,
          idempotency_key: pendingRun.current.key,
        }),
      });
    } catch {
      throw Error(
        isEl
          ? "Δεν επιβεβαιώθηκε η έναρξη της αναζήτησης. Δοκιμάστε ξανά για ασφαλή ανάκτηση της ίδιας εκτέλεσης."
          : "Could not confirm the search request. Try again to safely recover the same run.",
      );
    }
    if (!response.ok) {
      if (response.status < 500) pendingRun.current = null;
      throw Error(
        response.status === 422
          ? isEl
            ? "Ελέγξτε τις ρυθμίσεις αναζήτησης και δοκιμάστε ξανά."
            : "Check the search settings and try again."
          : response.status === 403 || response.status === 401
            ? isEl
              ? "Η πρόσβαση ή η συνεδρία σας άλλαξε. Ανανεώστε τη σελίδα και δοκιμάστε ξανά."
              : "Your access or session changed. Reload the page and try again."
            : isEl
              ? "Δεν ήταν δυνατή η έναρξη της αναζήτησης. Ελέγξτε την ημέρα ή δοκιμάστε ξανά. Οι αναθέσεις σας δεν άλλαξαν."
              : "The search could not start. Review the service day or try again. Your assignments are unchanged.",
      );
    }
    const data = (await response.json()) as { run_id: string };
    if (typeof data.run_id !== "string")
      throw Error(
        isEl
          ? "Δεν επιβεβαιώθηκε η κατάσταση. Δοκιμάστε ξανά."
          : "The search status could not be confirmed. Try again.",
      );
    pendingRun.current = null;
    try {
      localStorage.setItem(
        `ktel_job_${user.ktelId}_${snapshotId}`,
        data.run_id,
      );
    } catch {}
    if (currentRevision.current === snapshotId) setJobId(data.run_id);
  };
  useEffect(() => {
    if (
      !revision ||
      job.snapshotId !== revision.revision_id ||
      job.runId !== jobId
    ) {
      setPlans([]);
      setSelectedPlanId("");
      return;
    }
    setPlans(
      job.candidates.map((candidate) => ({
        id: `${jobId}-${candidate.id}`,
        name: `CV · ${isEl ? "Επανάληψη" : "Iteration"} ${candidate.iteration}`,
        subtitle: candidate.verification.valid
          ? "Verified candidate"
          : "Candidate has rule findings",
        algorithm: candidate.solver_version,
        generatedAt: `${candidate.iteration}`,
        totalTrips:
          candidate.metrics.assigned_trips_count +
          candidate.metrics.unassigned_trips_count,
        assignedTrips: candidate.metrics.assigned_trips_count,
        unassignedTrips: candidate.metrics.unassigned_trips_count,
        busesUsed: candidate.metrics.resource_count,
        totalDrivingMinutes: candidate.metrics.total_driving_minutes,
        totalIdleMinutes: candidate.metrics.total_idle_minutes,
        assignments: candidate.assignments.map((a) => ({
          tripId: a.trip_id,
          busId: a.resource_id,
          idleTime: 0,
        })),
      })),
    );
  }, [job.candidates, job.snapshotId, job.runId, jobId, isEl, revision]);
  const handleApplyPlan = async (plan: CandidatePlan) => {
    if (!revision) return;
    const assigned = new Map(plan.assignments.map((a) => [a.tripId, a.busId]));
    await mutateRevision(
      "patches",
      trips
        .filter((t) => !t.isLocked)
        .map((t) => ({
          trip_id: t.id,
          new_resource_id: assigned.get(t.id) ?? "UNASSIGNED",
        })),
    );
    setSelectedPlanId(plan.id);
  };

  const studioEpoch = navigationEpoch.current;

  // Unauthenticated -> Show Enterprise Login
  if (!isAuthenticated) {
    return <LoginForm />;
  }

  if (activeTab === "operations")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <OperationsWorkspace
          serviceDate={serviceDate}
          onDate={selectServiceDate}
          onStudio={(date) => navigate("scheduling", { serviceDate: date })}
        />
      </Shell>
    );

  if (activeTab === "team")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        {user?.permissions.includes("members.manage") ? <TeamWorkspace /> : null}
      </Shell>
    );

  if (activeTab === "office")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <OfficeWorkspace onOpenStudio={(date) => navigate("scheduling", { serviceDate: date })} />
      </Shell>
    );

  if (activeTab === "dashboard")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <OverviewWorkspace
          serviceDate={serviceDate}
          revision={revision}
          onDate={selectServiceDate}
          onOpen={(tab, date) => {
            navigate(tab, { serviceDate: date ?? serviceDate });
          }}
          onOpenStudio={openStudio}
        />
      </Shell>
    );

  if (activeTab === "imports")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <ImportWorkspace
          initialEntity={location.entity ?? "drivers"}
          returnTo={location.returnTo}
          onOpen={navigate}
        />
      </Shell>
    );

  if (activeTab === "timetables" || activeTab === "planning")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        {activeTab === "timetables" ? (
          <TimetableWorkspace onPrepare={() => navigate("planning")} />
        ) : (
          <ServiceDayWorkspace
            serviceDate={serviceDate}
            onServiceDateChange={selectServiceDate}
            onOpenStudio={openStudio}
            onTimetables={() => navigate("timetables")}
            onOffice={() => navigate("office")}
          />
        )}
      </Shell>
    );

  if (activeTab === "drivers" || activeTab === "fleet")
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <ResourceWorkspace
          key={activeTab}
          kind={activeTab === "drivers" ? "drivers" : "vehicles"}
        />
      </Shell>
    );
  if (!loading && !revision && !error)
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        {sourceKind === "reference_archive" ? (
          <section className="resource-empty">
            <h1>{isEl ? "Αρχείο αναφοράς" : "Reference archive"}</h1>
            <p>
              {isEl
                ? "Δεν υπάρχει αποθηκευμένο αρχείο αναφοράς στον χώρο σας."
                : "No reference archive is saved in your workspace."}
            </p>
            <button
              className="button primary"
              onClick={() => navigate("scheduling")}
            >
              {isEl
                ? "Επιστροφή στον προγραμματισμό"
                : "Back to Scheduling Studio"}
            </button>
          </section>
        ) : (
          <StudioEntry
            serviceDate={serviceDate}
            busy={opening}
            onDate={selectServiceDate}
            onCreate={openStudio}
            onOpen={openServiceDay}
          />
        )}
      </Shell>
    );

  if (loading || !revision)
    return (
      <Shell currentTab={activeTab} onTabChange={navigate}>
        <div className="resource-empty">
          {loading ? (
            <p role="status">
              {isEl
                ? "Φόρτωση του χώρου εργασίας σας…"
                : "Loading your workspace…"}
            </p>
          ) : (
            <>
              <p role="alert">
                {isEl
                  ? "Δεν μπορέσαμε να φορτώσουμε το πρόγραμμά σας. Δοκιμάστε ξανά."
                  : "We could not load your schedule. Please try again."}
              </p>
              <button
                className="button secondary"
                onClick={() => {
                  setError(null);
                  setLoading(true);
                  void reloadRevision()
                    .catch((e) => setError(String(e)))
                    .finally(() => setLoading(false));
                }}
              >
                {isEl ? "Νέα προσπάθεια" : "Try again"}
              </button>
            </>
          )}
        </div>
      </Shell>
    );

  return (
    <Shell currentTab={activeTab} onTabChange={navigate}>
      <div className="space-y-6 p-6 md:p-8">
        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}
        {/* 2. Scheduling Studio View (Flagship with Real Data) */}
        {(activeTab === "scheduling" || activeTab === "archive") && (
          <div className="-m-6 md:-m-8">
            <SchedulingStudio
              key={revision.revision_id}
              displayContext={displayContext}
              sourceKind={revision.source_kind}
              sourceReviewRequired={revision.source_review_required}
              onReviewSource={() =>
                openServiceDay("planning", revision.problem.service_date)
              }
              initialRevision={studioRevision(revision)}
              persistedRevision={revision}
              onSaveChange={(saved, baseRevisionId) => {
                if (
                  currentRevision.current === baseRevisionId &&
                  navigationEpoch.current === studioEpoch
                )
                  setRevision(saved);
              }}
              serviceDate={revision.problem.service_date}
              onServiceDateChange={selectServiceDate}
              verification={revision.verification}
              onPatchAssignment={async (tripId, newResourceId, isLocked) =>
                mutateRevision("patches", [
                  {
                    trip_id: tripId,
                    new_resource_id: newResourceId,
                    is_locked: isLocked,
                  },
                ])
              }
              onRevisionAction={mutateRevision}
              resources={resources}
              trips={trips}
              plans={plans}
              selectedPlanId={selectedPlanId}
              permissions={user?.permissions ?? []}
              isOptimizing={isOptimizing}
              isRestoringRun={isRestoringRun}
              progressPct={job.progressPct}
              jobStatus={job.status}
              runId={jobId}
              jobError={job.error}
              onSelectPlan={setSelectedPlanId}
              onApplyPlan={handleApplyPlan}
              onRunCVSolver={handleRunCVSolver}
            />
          </div>
        )}

        {/* 6. Imports & Reports Views */}
        {activeTab === "reports" && (
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-8 text-center font-sans shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-50 text-2xl text-sky-500 dark:bg-sky-950/50">
              📥
            </div>
            <h3 className="text-base font-bold text-slate-900 dark:text-white">
              {isEl ? "Επιχειρησιακές Αναφορές" : "Operational Reports"}
            </h3>
            <p className="mx-auto max-w-md text-xs text-slate-500">
              {isEl
                ? "Η ενότητα δεν έχει συνδεθεί ακόμη. Το Studio χρησιμοποιεί εισαγόμενο σύνολο αναφοράς."
                : "This module is not connected yet. The Scheduling Studio uses an explicitly imported reference dataset."}
            </p>
          </div>
        )}
      </div>
    </Shell>
  );
}
