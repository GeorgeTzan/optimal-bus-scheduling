"use client";
import React, { useEffect, useState } from "react";
import { platformCall, type Customer, type Health } from "./platform-api";
import { SupportSession } from "./SupportSession";

export function CustomerHealth({
  customer,
  el,
  onFailure,
}: {
  customer: Customer;
  el: boolean;
  onFailure: (failure: unknown) => void;
}) {
  const [health, setHealth] = useState<Health | null>(customer.health);
  useEffect(() => {
    let active = true;
    platformCall<Health>(`/customers/${customer.id}/health`, el)
      .then((loaded) => active && setHealth(loaded))
      .catch((failure) => active && onFailure(failure));
    return () => {
      active = false;
    };
  }, [customer.id, el, onFailure]);
  if (!health) return null;
  const share = health.uncovered_share_latest;
  const items: [string, string, string | number][] = [
    [
      "last",
      el ? "Τελευταία σύνδεση" : "Last sign-in",
      health.last_sign_in
        ? new Date(health.last_sign_in).toLocaleString(el ? "el-GR" : "en-GB")
        : el
          ? "Ποτέ"
          : "Never",
    ],
    ["drivers", el ? "Οδηγοί" : "Drivers", health.drivers],
    ["vehicles", el ? "Οχήματα" : "Vehicles", health.vehicles],
    ["timetables", el ? "Δρομολόγια" : "Timetables", health.timetables],
    [
      "published",
      el ? "Ημέρες δημοσίευσης (30 ημ.)" : "Published days (30 d)",
      health.published_days_30d,
    ],
    [
      "solver",
      el ? "Αποτυχίες επίλυσης (7 ημ.)" : "Solver failures (7 d)",
      health.solver_failed_7d,
    ],
    [
      "mail",
      el ? "Αποτυχίες email (7 ημ.)" : "Mail failures (7 d)",
      health.mail_failed_7d,
    ],
    [
      "uncovered",
      el
        ? "Ακάλυπτο ποσοστό (τελευταία δημοσίευση)"
        : "Uncovered share (latest)",
      share === null ? "—" : `${Math.round(share * 1000) / 10}%`,
    ],
  ];
  return (
    <section
      aria-label={el ? `Υγεία ${customer.name}` : `Health of ${customer.name}`}
    >
      <dl className="platform-health">
        {items.map(([key, label, value]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd data-testid={`health-${key}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <SupportSession customerId={customer.id} el={el} />
    </section>
  );
}
