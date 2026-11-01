"use client";
import { useEffect, useState, type ReactNode } from "react";
import { LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";

/** Small phone-first frame for drivers: no office navigation, only language, theme and sign out. */
export function DriverShell({ name, tab, onTab, children }: { name: string; tab: "duties" | "leave"; onTab: (tab: "duties" | "leave") => void; children: ReactNode }) {
  const { locale, setLocale } = useI18n(),
    { logout, error } = useAuth(),
    el = locale === "el";
  const [dark, setDark] = useState(false);
  useEffect(() => {
    try {
      const saved = localStorage.getItem("ktel_theme") === "dark";
      setDark(saved);
      document.documentElement.classList.toggle("dark", saved);
    } catch { /* storage may be unavailable; the light theme stays */ }
  }, []);
  const toggle = () => {
    setDark(!dark);
    document.documentElement.classList.toggle("dark", !dark);
    try { localStorage.setItem("ktel_theme", !dark ? "dark" : "light"); } catch { /* not persisted */ }
  };
  return (
    <div className="driver-app">
      <header className="driver-top">
        <div>
          <small>{el ? "Πύλη οδηγού" : "Driver portal"}</small>
          <strong>{name}</strong>
        </div>
        <div className="driver-tools">
          <div className="locale-switch">
            <button className={el ? "active" : ""} aria-pressed={el} onClick={() => setLocale("el")}>ΕΛ</button>
            <button className={!el ? "active" : ""} aria-pressed={!el} onClick={() => setLocale("en")}>EN</button>
          </div>
          <button className="icon-button" onClick={toggle} aria-label={el ? "Αλλαγή θέματος" : "Toggle theme"}>{dark ? <Sun size={17} /> : <Moon size={17} />}</button>
          <button className="icon-button" onClick={() => void logout()} aria-label={el ? "Αποσύνδεση" : "Sign out"}><LogOut size={16} /></button>
        </div>
      </header>
      {error === "logout_unavailable" && <p className="auth-error" role="alert">{el ? "Η αποσύνδεση δεν ολοκληρώθηκε. Δοκιμάστε ξανά." : "Sign-out did not complete. Try again."}</p>}
      <nav className="driver-tabs" aria-label={el ? "Ενότητες" : "Sections"}>
        <button className={`button ${tab === "duties" ? "primary" : "secondary"}`} aria-current={tab === "duties" ? "page" : undefined} onClick={() => onTab("duties")}>{el ? "Οι υπηρεσίες μου" : "My duties"}</button>
        <button className={`button ${tab === "leave" ? "primary" : "secondary"}`} aria-current={tab === "leave" ? "page" : undefined} onClick={() => onTab("leave")}>{el ? "Άδειες" : "Leave"}</button>
      </nav>
      <main className="driver-main">{children}</main>
    </div>
  );
}
