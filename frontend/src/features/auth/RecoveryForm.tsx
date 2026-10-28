"use client";
import { useEffect, useState, useRef, type FormEvent } from "react";
import Link from "next/link";
import { KeyRound, Mail, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthContext";
import { useI18n } from "../../i18n/context";
import { AuthShell } from "./AuthShell";

type Mode = "request" | "reset" | "invitation";
export function RecoveryForm({ mode }: { mode: Mode }) {
  const { locale } = useI18n();
  const el = locale === "el";
  const { apiFetch, refreshIdentity } = useAuth();
  const router = useRouter();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [preview, setPreview] = useState<{
    organization_name: string;
    email: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(mode !== "request");
  const [invalid, setInvalid] = useState(false);
  const [error, setError] = useState(false);
  const [done, setDone] = useState(false);
  const secretRef = useRef<string | null>(null);
  useEffect(() => {
    if (mode === "request") return;
    const secret =
      secretRef.current ??
      new URLSearchParams(window.location.hash.slice(1)).get("token") ??
      "";
    secretRef.current = secret;
    // Remove the secret from browser history once this screen has read it.
    window.history.replaceState(null, "", window.location.pathname);
    setToken(secret);
    if (secret.length < 20) {
      setInvalid(true);
      setChecking(false);
      return;
    }
    if (mode === "reset") {
      setChecking(false);
      return;
    }
    let active = true;
    void apiFetch("/api/auth/invitations/preview", {
      method: "POST",
      body: JSON.stringify({ token: secret }),
    })
      .then(async (res) => {
        if (!res.ok) {
          if (active) setInvalid(true);
          return;
        }
        const data = (await res.json()) as {
          organization_name: string;
          email: string;
        };
        if (active) setPreview(data);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [mode, apiFetch]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(false);
    try {
      const route =
        mode === "request"
          ? "password-reset/request"
          : mode === "reset"
            ? "password-reset/confirm"
            : "accept-invitation";
      const body =
        mode === "request"
          ? { email }
          : mode === "reset"
            ? { token, password }
            : { token, password, full_name: fullName };
      const res = await apiFetch(`/api/auth/${route}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        if (res.status === 400 || res.status === 409) setInvalid(true);
        else setError(true);
        return;
      }
      await res.arrayBuffer();
      if (mode === "invitation") {
        await refreshIdentity();
        router.replace("/");
      } else setDone(true);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  const title =
    mode === "request"
      ? el
        ? "Ξεχάσατε τον κωδικό;"
        : "Forgot your password?"
      : mode === "reset"
        ? el
          ? "Ορίστε νέο κωδικό"
          : "Set a new password"
        : el
          ? "Καλώς ήρθατε στην ομάδα"
          : "Welcome to the team";
  return (
    <AuthShell>
      <span className="auth-form-icon">
        {mode === "request" ? (
          <Mail size={22} />
        ) : mode === "reset" ? (
          <KeyRound size={22} />
        ) : (
          <UserRound size={22} />
        )}
      </span>
      <h2>{title}</h2>
      <p className="auth-intro">
        {mode === "request"
          ? el
            ? "Συμπληρώστε το email του λογαριασμού σας. Θα σας στείλουμε σύνδεσμο για νέο κωδικό."
            : "Enter your account email. We’ll send a link to set a new password."
          : el
            ? "Επιλέξτε έναν μοναδικό κωδικό με τουλάχιστον 12 χαρακτήρες."
            : "Choose a unique password with at least 12 characters."}
      </p>
      {checking ? (
        <p className="auth-intro" role="status">
          {el ? "Έλεγχος πρόσκλησης…" : "Checking your invitation…"}
        </p>
      ) : invalid ? (
        <div className="auth-error" role="alert" style={{ marginTop: 24 }}>
          {el
            ? "Ο σύνδεσμος δεν είναι έγκυρος, έχει λήξει ή έχει ήδη χρησιμοποιηθεί. Ζητήστε νέο σύνδεσμο από τον διαχειριστή σας."
            : "This link is invalid, expired or already used. Ask your administrator for a new link."}
        </div>
      ) : done ? (
        <div className="auth-success" role="status">
          {mode === "request"
            ? el
              ? "Ελέγξτε το email σας. Αν ο λογαριασμός είναι ενεργός, θα λάβετε σύνδεσμο επαναφοράς. Αν δεν φτάσει, επικοινωνήστε με τον διαχειριστή σας."
              : "Check your email. If this account is active, you’ll receive a reset link. If it doesn’t arrive, contact your administrator."
            : el
              ? "Ο κωδικός σας ενημερώθηκε. Συνδεθείτε με τον νέο κωδικό."
              : "Your password has been updated. Sign in with your new password."}
        </div>
      ) : (
        <>
          {preview && (
            <div className="auth-summary">
              <strong>{preview.organization_name}</strong>
              <p>{preview.email}</p>
            </div>
          )}
          <form className="auth-form" onSubmit={submit}>
            {error && (
              <div className="auth-error" role="alert">
                {el
                  ? "Δεν μπορέσαμε να ολοκληρώσουμε την ενέργεια. Δοκιμάστε ξανά."
                  : "We could not complete this action. Please try again."}
              </div>
            )}
            {mode === "request" ? (
              <>
                <label htmlFor="recovery-email">
                  {el ? "Διεύθυνση email" : "Email address"}
                </label>
                <input
                  id="recovery-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </>
            ) : (
              <>
                {mode === "invitation" && (
                  <>
                    <label htmlFor="invite-name">
                      {el ? "Ονοματεπώνυμο" : "Full name"}
                    </label>
                    <input
                      id="invite-name"
                      autoComplete="name"
                      maxLength={200}
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      required
                    />
                  </>
                )}
                <label htmlFor="new-password">
                  {el ? "Νέος κωδικός" : "New password"}
                </label>
                <input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  aria-describedby="password-help"
                />
                <small id="password-help" className="auth-intro">
                  {el
                    ? "Τουλάχιστον 12 χαρακτήρες. Μπορείτε να χρησιμοποιήσετε μια φράση."
                    : "At least 12 characters. A memorable phrase works well."}
                </small>
              </>
            )}
            <button
              className="auth-submit"
              type="submit"
              disabled={busy || (mode === "invitation" && !preview)}
            >
              {busy
                ? el
                  ? "Επεξεργασία…"
                  : "Please wait…"
                : mode === "request"
                  ? el
                    ? "Αποστολή συνδέσμου"
                    : "Send reset link"
                  : mode === "reset"
                    ? el
                      ? "Αποθήκευση κωδικού"
                      : "Save password"
                    : el
                      ? "Δημιουργία λογαριασμού"
                      : "Create account"}
            </button>
          </form>
        </>
      )}
      <Link className="auth-back" href="/">
        {el ? "← Επιστροφή στη σύνδεση" : "← Back to sign in"}
      </Link>
    </AuthShell>
  );
}
