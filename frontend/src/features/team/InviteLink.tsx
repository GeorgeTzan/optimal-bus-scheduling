"use client";
import { useState } from "react";

export function InviteLink({ email, link, el, onClose, reset = false }: { email: string; link: string; el: boolean; onClose: () => void; reset?: boolean }) {
  const [copied, setCopied] = useState(false);
  const title = reset ? (el ? "Σύνδεσμος νέου κωδικού" : "New password link") : (el ? "Σύνδεσμος πρόσκλησης" : "Invitation link");
  const copy = () => navigator.clipboard.writeText(link).then(() => setCopied(true), () => setCopied(false));
  return (
    <section className="office-panel" aria-labelledby="invite-link-heading">
      <h2 id="invite-link-heading">{title}</h2>
      <p>{el
        ? <>Δώστε αυτόν τον σύνδεσμο στο <strong>{email}</strong>. Ισχύει μία φορά και για {reset ? "30 λεπτά" : "48 ώρες"}. Εμφανίζεται μόνο τώρα· αν χαθεί, δημιουργήστε νέο.</>
        : <>Give this link to <strong>{email}</strong>. It works once and for {reset ? "30 minutes" : "48 hours"}. It is shown only now; if it is lost, create a new one.</>}</p>
      <input readOnly aria-label={title} value={link} onFocus={(e) => e.target.select()} style={{ width: "100%" }} />
      <p>
        <button type="button" className="button primary" onClick={() => void copy()}>{copied ? (el ? "Αντιγράφηκε" : "Copied") : (el ? "Αντιγραφή" : "Copy")}</button>{" "}
        <button type="button" className="button secondary" onClick={onClose}>{el ? "Κλείσιμο" : "Close"}</button>
      </p>
    </section>
  );
}
