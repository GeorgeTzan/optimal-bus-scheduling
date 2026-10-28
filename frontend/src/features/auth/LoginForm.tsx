"use client";
import React, { useState } from "react";
import Link from "next/link";
import { ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useAuth } from "./AuthContext";
import { useI18n } from "../../i18n/context";
import { AuthShell } from "./AuthShell";

export function LoginForm({ onSuccess }: { onSuccess?: () => void }) {
  const { apiFetch, refreshIdentity } = useAuth();
  const { locale } = useI18n();
  const el = locale === "el";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        setError(
          res.status === 429
            ? el
              ? "Πολλές προσπάθειες σύνδεσης. Περιμένετε λίγα λεπτά και δοκιμάστε ξανά."
              : "Too many sign-in attempts. Wait a few minutes and try again."
            : res.status === 403
              ? el
                ? "Ο λογαριασμός σας δεν είναι ενεργός. Επικοινωνήστε με τον διαχειριστή σας."
                : "Your account is inactive. Contact your administrator."
              : res.status === 401
                ? el
                  ? "Το email ή ο κωδικός δεν είναι σωστός. Δοκιμάστε ξανά."
                  : "The email or password is incorrect. Please try again."
                : el
                  ? "Η σύνδεση δεν είναι διαθέσιμη αυτή τη στιγμή. Δοκιμάστε ξανά."
                  : "Sign-in is unavailable right now. Please try again.",
        );
        return;
      }
      await res.arrayBuffer();
      await refreshIdentity();
      onSuccess?.();
    } catch {
      setError(
        el
          ? "Δεν μπορέσαμε να συνδεθούμε. Ελέγξτε τη σύνδεσή σας και δοκιμάστε ξανά."
          : "We could not connect. Check your connection and try again.",
      );
    } finally {
      setLoading(false);
    }
  };
  return (
    <AuthShell>
      <span className="auth-form-icon">
        <LockKeyhole size={22} />
      </span>
      <h2>{el ? "Καλώς ήρθατε" : "Welcome back"}</h2>
      <p className="auth-intro">
        {el
          ? "Συνδεθείτε για να συνεχίσετε στον χώρο εργασίας σας."
          : "Sign in to continue to your workspace."}
      </p>
      <form onSubmit={handleSubmit} className="auth-form">
        {error && (
          <div className="auth-error" role="alert">
            {error}
          </div>
        )}
        <label htmlFor="login-email">
          {el ? "Διεύθυνση email" : "Email address"}
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@ktel.gr"
        />
        <div className="auth-label-row">
          <label htmlFor="login-password">
            {el ? "Κωδικός πρόσβασης" : "Password"}
          </label>
          <Link href="/forgot-password">
            {el ? "Ξεχάσατε τον κωδικό;" : "Forgot password?"}
          </Link>
        </div>
        <div className="auth-password">
          <input
            id="login-password"
            type={visible ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            aria-label={
              visible
                ? el
                  ? "Απόκρυψη κωδικού"
                  : "Hide password"
                : el
                  ? "Εμφάνιση κωδικού"
                  : "Show password"
            }
            aria-pressed={visible}
            onClick={() => setVisible(!visible)}
          >
            {visible ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        </div>
        <button className="auth-submit" type="submit" disabled={loading}>
          {loading
            ? el
              ? "Σύνδεση…"
              : "Signing in…"
            : el
              ? "Σύνδεση"
              : "Sign in"}
          <ArrowRight size={17} />
        </button>
      </form>
      <p className="auth-footnote">
        {el
          ? "Λάβατε πρόσκληση; Ανοίξτε τον σύνδεσμο στο email σας για να δημιουργήσετε λογαριασμό."
          : "Received an invitation? Open the link in your email to create your account."}
      </p>
    </AuthShell>
  );
}
