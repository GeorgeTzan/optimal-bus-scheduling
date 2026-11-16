"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../features/auth/AuthContext";
import { useI18n } from "../i18n/context";

export function SupportBanner() {
  const { user, refreshIdentity } = useAuth();
  const el = useI18n().locale === "el";
  const [now, setNow] = useState(() => Date.now());
  const shown = Boolean(user?.supportSession);
  useEffect(() => {
    if (!shown) return;
    const timer = setInterval(() => {
      setNow(Date.now());
      void refreshIdentity().catch(() => undefined);
    }, 60_000);
    return () => clearInterval(timer);
  }, [shown, refreshIdentity]);
  if (!user?.supportSession) return null;
  if (new Date(user.supportSession.endsAt).getTime() <= now) return null;
  const ends = new Date(user.supportSession.endsAt).toLocaleString(
    el ? "el-GR" : "en-GB",
    { dateStyle: "short", timeStyle: "short" },
  );
  return (
    <div className="support-banner" role="status" data-testid="support-banner">
      <strong>
        {el
          ? "Η υποστήριξη βλέπει αυτή την οργάνωση"
          : "Platform support is viewing this organization"}
      </strong>
      <span>
        {el ? `Μόνο ανάγνωση, έως ${ends}.` : `Read-only, until ${ends}.`}
      </span>
      {user.role === "support" ? (
        <a href="/platform">
          {el ? "Επιστροφή στον πίνακα" : "Back to the panel"}
        </a>
      ) : null}
    </div>
  );
}
