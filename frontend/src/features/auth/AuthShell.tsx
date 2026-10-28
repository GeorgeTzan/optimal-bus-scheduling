"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { BusFront, ArrowRight, CalendarDays, Users, Route } from "lucide-react";
import { useI18n } from "../../i18n/context";

export function AuthShell({ children }: { children: ReactNode }) {
  const { locale, setLocale } = useI18n();
  const el = locale === "el";
  return (
    <main className="auth-layout">
      <aside className="auth-story">
        <Link href="/" className="auth-brand">
          <span className="auth-brand-mark">
            <BusFront size={25} />
          </span>
          <span>
            <strong>KTEL</strong>
            <small>Operations Platform</small>
          </span>
        </Link>
        <div className="auth-story-copy">
          <span className="auth-eyebrow">
            {el ? "ΚΑΘΕ ΜΕΡΑ, ΜΕ ΣΧΕΔΙΟ" : "EVERY DAY, A CLEAR PLAN"}
          </span>
          <h1>
            {el
              ? "Η λειτουργία σας.\nΣε μία καθαρή εικόνα."
              : "Your operations.\nOne clear picture."}
          </h1>
          <p>
            {el
              ? "Ένας οργανωμένος χώρος για τους ανθρώπους, τα οχήματα και τα δρομολόγιά σας."
              : "One organized workspace for your people, vehicles and timetables."}
          </p>
          <div className="auth-story-items">
            {[
              [Users, el ? "Άνθρωποι & στόλος" : "People & fleet"],
              [
                CalendarDays,
                el ? "Καθημερινός προγραμματισμός" : "Daily scheduling",
              ],
              [
                Route,
                el ? "Έλεγχος πριν τη δημοσίευση" : "Check before publishing",
              ],
            ].map(([Icon, text], i) => {
              const ItemIcon = Icon as typeof Users;
              return (
                <div key={i}>
                  <ItemIcon size={19} />
                  <span>{text as string}</span>
                  <ArrowRight size={15} />
                </div>
              );
            })}
          </div>
        </div>
        <footer>
          {el
            ? "Συνδέουμε την Ελλάδα. Κάθε μέρα."
            : "Connecting Greece. Every day."}
        </footer>
      </aside>
      <section className="auth-content">
        <div className="auth-utility">
          <span>KTEL Operations</span>
          <div className="locale-switch">
            <button
              type="button"
              aria-pressed={el}
              className={el ? "active" : ""}
              onClick={() => setLocale("el")}
            >
              ΕΛ
            </button>
            <button
              type="button"
              aria-pressed={!el}
              className={!el ? "active" : ""}
              onClick={() => setLocale("en")}
            >
              EN
            </button>
          </div>
        </div>
        <div className="auth-form-area">{children}</div>
        <footer className="auth-help">
          {el
            ? "Χρειάζεστε πρόσβαση; Ο διαχειριστής του ΚΤΕΛ σας μπορεί να σας προσκαλέσει."
            : "Need access? Your KTEL administrator can invite you."}
        </footer>
      </section>
    </main>
  );
}
