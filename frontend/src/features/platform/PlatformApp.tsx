"use client";
import React, { useCallback, useEffect, useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useI18n } from "../../i18n/context";
import { AuthShell } from "../auth/AuthShell";
import { InviteLink } from "../team/InviteLink";
import { CustomerList } from "./CustomerList";
import { CreateCustomerForm } from "./CustomerForm";
import {
  platformCall,
  PlatformError,
  type Customer,
  type Operator,
} from "./platform-api";

function OperatorSignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const { locale } = useI18n();
  const el = locale === "el";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await platformCall<void>("/auth/login", el, {
        method: "POST",
        body: JSON.stringify({ email, password, code }),
      });
      onSignedIn();
    } catch (failure) {
      setError(
        failure instanceof PlatformError ? failure.message : String(failure),
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell>
      <span className="auth-form-icon">
        <ShieldCheck size={22} />
      </span>
      <h2>{el ? "Πίνακας πλατφόρμας" : "Platform panel"}</h2>
      <p className="auth-intro">
        {el
          ? "Σύνδεση διαχειριστή πλατφόρμας με κωδικό επαλήθευσης."
          : "Platform operator sign-in with a verification code."}
      </p>
      <form onSubmit={submit} className="auth-form">
        {error && (
          <div className="auth-error" role="alert">
            {error}
          </div>
        )}
        <label htmlFor="operator-email">
          {el ? "Διεύθυνση email" : "Email address"}
        </label>
        <input
          id="operator-email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <label htmlFor="operator-password">
          {el ? "Κωδικός πρόσβασης" : "Password"}
        </label>
        <input
          id="operator-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <label htmlFor="operator-code">
          {el
            ? "Κωδικός επαλήθευσης (6 ψηφία)"
            : "Verification code (6 digits)"}
        </label>
        <input
          id="operator-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          required
          value={code}
          onChange={(e) => setCode(e.target.value.trim())}
        />
        <button className="auth-submit" type="submit" disabled={busy}>
          {busy
            ? el
              ? "Σύνδεση…"
              : "Signing in…"
            : el
              ? "Σύνδεση"
              : "Sign in"}
          <ArrowRight size={17} />
        </button>
      </form>
    </AuthShell>
  );
}

export function PlatformApp() {
  const { locale, setLocale } = useI18n();
  const el = locale === "el";
  const [operator, setOperator] = useState<Operator | null | undefined>(
    undefined,
  );
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [invitation, setInvitation] = useState<{
    email: string;
    link: string;
  } | null>(null);
  const failed = useCallback((failure: unknown) => {
    if (failure instanceof PlatformError && failure.status === 401)
      setOperator(null);
    else
      setError(
        failure instanceof PlatformError ? failure.message : String(failure),
      );
  }, []);
  const load = useCallback(async () => {
    try {
      setCustomers(await platformCall<Customer[]>("/customers", el));
      setError(null);
    } catch (failure) {
      failed(failure);
    }
  }, [el, failed]);
  const identify = useCallback(async () => {
    try {
      setOperator(await platformCall<Operator>("/me", el));
    } catch (failure) {
      if (failure instanceof PlatformError && failure.status === 401)
        setOperator(null);
      else
        setError(
          failure instanceof PlatformError ? failure.message : String(failure),
        );
    }
  }, [el]);
  useEffect(() => {
    void identify();
  }, [identify]);
  useEffect(() => {
    if (operator) void load();
  }, [operator, load]);
  const signOut = async () => {
    try {
      await platformCall<void>("/auth/logout", el, { method: "POST" });
      setOperator(null);
      setCustomers([]);
      setInvitation(null);
    } catch (failure) {
      failed(failure);
    }
  };
  if (operator === undefined)
    return error ? (
      <p className="auth-error" role="alert">
        {error}
      </p>
    ) : null;
  if (operator === null)
    return <OperatorSignIn onSignedIn={() => void identify()} />;
  return (
    <main className="resource-workspace office-workspace platform-workspace">
      <header className="resource-heading">
        <div>
          <span className="resource-eyebrow">
            {el ? "Πίνακας πλατφόρμας" : "Platform panel"}
          </span>
          <h1>{el ? "Πελάτες" : "Customers"}</h1>
          <p>{operator.email}</p>
        </div>
        <div className="resource-heading-actions">
          <button
            type="button"
            className="button secondary"
            onClick={() => setLocale(el ? "en" : "el")}
          >
            {el ? "EN" : "EL"}
          </button>
          <button
            type="button"
            className="button primary"
            onClick={() => setCreating(true)}
            disabled={creating}
          >
            {el ? "Νέος πελάτης" : "New customer"}
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => void signOut()}
          >
            {el ? "Αποσύνδεση" : "Sign out"}
          </button>
        </div>
      </header>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {invitation && (
        <InviteLink
          email={invitation.email}
          link={invitation.link}
          el={el}
          onClose={() => setInvitation(null)}
        />
      )}
      {creating && (
        <CreateCustomerForm
          el={el}
          onCancel={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            setInvitation(created);
            void load();
          }}
          onUnauthorized={() => setOperator(null)}
        />
      )}
      <CustomerList
        customers={customers}
        el={el}
        onChanged={load}
        onFailure={failed}
      />
    </main>
  );
}
