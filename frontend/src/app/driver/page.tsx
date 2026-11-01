"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../features/auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { LoginForm } from "../../features/auth/LoginForm";
import { DriverShell } from "../../features/driver/DriverShell";
import { DutiesView } from "../../features/driver/DutiesView";
import { LeaveView } from "../../features/driver/LeaveView";
import type { DriverMe } from "../../features/driver/contracts";
import { DriverError, driverCall } from "../../features/driver/driver-api";

export default function DriverPage() {
  const { isAuthenticated, user, loading } = useAuth(),
    el = useI18n().locale === "el",
    router = useRouter();
  const isDriver = user?.role === "driver";
  useEffect(() => { if (user && !isDriver) router.replace("/"); }, [user, isDriver, router]);
  if (loading) return <div className="session-state" role="status">{el ? "Άνοιγμα…" : "Opening…"}</div>;
  if (!isAuthenticated || !user) return <LoginForm />;
  if (!isDriver) return <div className="session-state" role="status">{el ? "Μετάβαση…" : "Redirecting…"}</div>;
  // Keyed by session: signing out and in as someone else never shows the previous person's name or error.
  return <DriverArea key={`${user.id}:${user.sessionId}`} fullName={user.fullName} />;
}

function DriverArea({ fullName }: { fullName: string }) {
  const { apiFetch } = useAuth(),
    el = useI18n().locale === "el";
  const [me, setMe] = useState<DriverMe | null>(null),
    [problem, setProblem] = useState(""),
    [tab, setTab] = useState<"duties" | "leave">("duties");
  useEffect(() => {
    const controller = new AbortController();
    driverCall<DriverMe>(apiFetch, "/api/v1/driver/me", { signal: controller.signal }, el)
      .then(setMe)
      .catch((failure: unknown) => { if (!controller.signal.aborted) setProblem(failure instanceof DriverError ? failure.message : el ? "Δεν φορτώθηκαν τα στοιχεία σας." : "Your details could not be loaded."); });
    return () => controller.abort();
  }, [apiFetch, el]);
  return (
    <DriverShell name={me?.driver_name ?? fullName} tab={tab} onTab={setTab}>
      {problem ? <p className="auth-error" role="alert">{problem}</p> : !me ? <p role="status">{el ? "Φόρτωση…" : "Loading…"}</p> : tab === "duties" ? <DutiesView /> : <LeaveView timezone={me.timezone} />}
    </DriverShell>
  );
}
