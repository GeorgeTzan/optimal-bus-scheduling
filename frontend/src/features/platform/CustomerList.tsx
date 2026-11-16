"use client";
import React, { useState } from "react";
import { SubscriptionForm } from "./CustomerForm";
import { CustomerHealth } from "./CustomerHealth";
import {
  healthFlags,
  statusText,
  trialEnded,
  type Customer,
} from "./platform-api";

export function CustomerList({
  customers,
  el,
  onChanged,
  onFailure,
}: {
  customers: Customer[];
  el: boolean;
  onChanged: () => Promise<void>;
  onFailure: (failure: unknown) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [inspecting, setInspecting] = useState<number | null>(null);
  if (!customers.length)
    return (
      <p className="office-empty">
        {el ? "Δεν υπάρχουν πελάτες ακόμη." : "There are no customers yet."}
      </p>
    );
  return (
    <section className="office-panel" aria-labelledby="customer-list-heading">
      <h2 id="customer-list-heading">
        {el ? "Όλοι οι πελάτες" : "All customers"}
      </h2>
      <div className="resource-table-scroll">
        <table className="resource-table platform-table">
          <thead>
            <tr>
              <th>{el ? "Οργανισμός" : "Organization"}</th>
              <th>{el ? "Κατάσταση" : "Status"}</th>
              <th>{el ? "Υγεία" : "Health"}</th>
              <th>{el ? "Λήξη δοκιμής" : "Trial ends"}</th>
              <th>{el ? "Σημείωση πλάνου" : "Plan note"}</th>
              <th>{el ? "Ενέργειες" : "Actions"}</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer) => (
              <React.Fragment key={customer.id}>
                <tr data-testid={`customer-${customer.id}`}>
                  <td>
                    <strong>{customer.name}</strong>
                    {customer.region && <small>{customer.region}</small>}
                  </td>
                  <td>
                    <span
                      className="platform-chip"
                      data-status={customer.status}
                    >
                      {statusText[customer.status][el ? 0 : 1]}
                    </span>
                    {trialEnded(customer) && (
                      <span className="platform-chip" data-status="warning">
                        {el ? "Η δοκιμή έληξε" : "Trial ended"}
                      </span>
                    )}
                  </td>
                  <td>
                    <HealthChips customer={customer} el={el} />
                  </td>
                  <td>{customer.trial_ends_on ?? "—"}</td>
                  <td>{customer.plan_note ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="button secondary"
                      aria-label={
                        el
                          ? `Διαχείριση ${customer.name}`
                          : `Manage ${customer.name}`
                      }
                      onClick={() =>
                        setEditing(editing === customer.id ? null : customer.id)
                      }
                    >
                      {el ? "Διαχείριση" : "Manage"}
                    </button>
                    <button
                      type="button"
                      className="button secondary"
                      aria-label={
                        el
                          ? `Υγεία ${customer.name}`
                          : `Health ${customer.name}`
                      }
                      onClick={() =>
                        setInspecting(
                          inspecting === customer.id ? null : customer.id,
                        )
                      }
                    >
                      {el ? "Υγεία" : "Health"}
                    </button>
                  </td>
                </tr>
                {inspecting === customer.id && (
                  <tr>
                    <td colSpan={6}>
                      <CustomerHealth
                        customer={customer}
                        el={el}
                        onFailure={onFailure}
                      />
                    </td>
                  </tr>
                )}
                {editing === customer.id && (
                  <tr>
                    <td colSpan={6}>
                      <SubscriptionForm
                        customer={customer}
                        el={el}
                        onCancel={() => setEditing(null)}
                        onFailure={onFailure}
                        onSaved={() => {
                          setEditing(null);
                          void onChanged();
                        }}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HealthChips({ customer, el }: { customer: Customer; el: boolean }) {
  if (!customer.health)
    return (
      <span aria-label={el ? "Άγνωστη κατάσταση" : "Health unknown"}>–</span>
    );
  const { failing, inactive } = healthFlags(customer.health);
  const labels = {
    solver: el ? "Αποτυχίες επίλυσης" : "Solver failures",
    mail: el ? "Αποτυχίες email" : "Mail failures",
    uncovered: el ? "Ακάλυπτα δρομολόγια" : "Uncovered trips",
  };
  if (!failing.length && !inactive)
    return <span className="platform-chip">{el ? "Εντάξει" : "Healthy"}</span>;
  return (
    <>
      {failing.map((flag) => (
        <span key={flag} className="platform-chip" data-status="danger">
          {labels[flag]}
        </span>
      ))}
      {inactive && (
        <span className="platform-chip" data-status="warning">
          {customer.health?.last_sign_in
            ? el
              ? "Χωρίς σύνδεση 14+ ημέρες"
              : "No sign-in for 14+ days"
            : el
              ? "Καμία σύνδεση ακόμη"
              : "Never signed in"}
        </span>
      )}
    </>
  );
}
