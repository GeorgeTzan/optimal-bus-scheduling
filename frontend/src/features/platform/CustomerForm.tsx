"use client";
import React, { useState } from "react";
import {
  platformCall,
  PlatformError,
  STATUSES,
  statusText,
  type Customer,
  type CustomerStatus,
} from "./platform-api";

export function CreateCustomerForm({
  el,
  onCancel,
  onCreated,
  onUnauthorized,
}: {
  el: boolean;
  onCancel: () => void;
  onCreated: (invitation: { email: string; link: string }) => void;
  onUnauthorized: () => void;
}) {
  const [name, setName] = useState("");
  const [region, setRegion] = useState("");
  const [timezone, setTimezone] = useState("Europe/Athens");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"trial" | "active">("trial");
  const [trialEnd, setTrialEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await platformCall<{
        id: number;
        invitation_link: string;
      }>("/customers", el, {
        method: "POST",
        body: JSON.stringify({
          name,
          region: region.trim() || null,
          timezone,
          status,
          trial_ends_on: status === "trial" && trialEnd ? trialEnd : null,
          admin_email: email,
        }),
      });
      onCreated({ email, link: created.invitation_link });
    } catch (failure) {
      if (failure instanceof PlatformError && failure.status === 401)
        onUnauthorized();
      else
        setError(
          failure instanceof PlatformError ? failure.message : String(failure),
        );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="office-panel" aria-labelledby="create-customer-heading">
      <h2 id="create-customer-heading">
        {el ? "Νέος πελάτης" : "New customer"}
      </h2>
      <form className="resource-form-body platform-form" onSubmit={submit}>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <label>
          {el ? "Όνομα οργανισμού" : "Organization name"}
          <input
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          {el ? "Περιοχή" : "Region"}
          <input
            maxLength={200}
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          />
        </label>
        <label>
          {el ? "Ζώνη ώρας" : "Time zone"}
          <input
            required
            maxLength={64}
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          />
        </label>
        <label>
          {el ? "Email πρώτου διαχειριστή" : "First administrator email"}
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          {el ? "Κατάσταση" : "Status"}
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as "trial" | "active")}
          >
            {(["trial", "active"] as const).map((value) => (
              <option key={value} value={value}>
                {statusText[value][el ? 0 : 1]}
              </option>
            ))}
          </select>
        </label>
        {status === "trial" && (
          <label>
            {el ? "Λήξη δοκιμής" : "Trial ends on"}
            <input
              type="date"
              value={trialEnd}
              onChange={(e) => setTrialEnd(e.target.value)}
            />
          </label>
        )}
        <div className="resource-dialog-actions">
          <button type="submit" className="button primary" disabled={busy}>
            {busy
              ? el
                ? "Δημιουργία…"
                : "Creating…"
              : el
                ? "Δημιουργία πελάτη"
                : "Create customer"}
          </button>
          <button type="button" className="button secondary" onClick={onCancel}>
            {el ? "Ακύρωση" : "Cancel"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function SubscriptionForm({
  customer,
  el,
  onSaved,
  onCancel,
  onFailure,
}: {
  customer: Customer;
  el: boolean;
  onSaved: () => void;
  onCancel: () => void;
  onFailure: (failure: unknown) => void;
}) {
  const [status, setStatus] = useState<CustomerStatus>(customer.status);
  const [trialEnd, setTrialEnd] = useState(customer.trial_ends_on ?? "");
  const [planNote, setPlanNote] = useState(customer.plan_note ?? "");
  const [region, setRegion] = useState(customer.region ?? "");
  const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await platformCall<Customer>(`/customers/${customer.id}`, el, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          trial_ends_on: trialEnd || null,
          plan_note: planNote.trim() || null,
          region: region.trim() || null,
        }),
      });
      onSaved();
    } catch (failure) {
      onFailure(failure);
    } finally {
      setBusy(false);
    }
  };
  const closing =
    status !== customer.status &&
    (status === "suspended" || status === "cancelled");
  return (
    <form
      className="resource-form-body platform-form"
      onSubmit={submit}
      aria-label={
        el ? `Συνδρομή ${customer.name}` : `Subscription ${customer.name}`
      }
    >
      <label>
        {el ? "Κατάσταση" : "Status"}
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as CustomerStatus)}
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {statusText[value][el ? 0 : 1]}
            </option>
          ))}
        </select>
      </label>
      <label>
        {el ? "Λήξη δοκιμής" : "Trial ends on"}
        <input
          type="date"
          value={trialEnd}
          onChange={(e) => setTrialEnd(e.target.value)}
        />
      </label>
      <label>
        {el ? "Περιοχή" : "Region"}
        <input
          maxLength={200}
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        />
      </label>
      <label>
        {el ? "Σημείωση πλάνου" : "Plan note"}
        <textarea
          maxLength={2000}
          rows={2}
          value={planNote}
          onChange={(e) => setPlanNote(e.target.value)}
        />
      </label>
      {closing && (
        <p className="driver-muted">
          {el
            ? "Οι χρήστες του οργανισμού θα αποσυνδεθούν και δεν θα μπορούν να συνδεθούν. Τα δεδομένα διατηρούνται."
            : "The organization's users will be signed out and cannot sign in. Data is kept."}
        </p>
      )}
      <div className="resource-dialog-actions">
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? (el ? "Αποθήκευση…" : "Saving…") : el ? "Αποθήκευση" : "Save"}
        </button>
        <button type="button" className="button secondary" onClick={onCancel}>
          {el ? "Ακύρωση" : "Cancel"}
        </button>
      </div>
    </form>
  );
}
