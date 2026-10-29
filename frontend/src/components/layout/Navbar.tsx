"use client";
import React, { useState, useEffect } from "react";
import { ChevronRight, Sun, Moon, LogOut } from "lucide-react";
import { useI18n } from "../../i18n/context";
import { useAuth } from "../../features/auth/AuthContext";
import type { ShellTab } from "./Shell";
export function Navbar({ currentTab }: { currentTab: ShellTab }) {
  const { locale, setLocale } = useI18n();
  const { user, logout, error } = useAuth();
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const d = localStorage.getItem("ktel_theme") === "dark";
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
  }, []);
  const toggle = () => {
    setDark(!dark);
    document.documentElement.classList.toggle("dark", !dark);
    localStorage.setItem("ktel_theme", !dark ? "dark" : "light");
  };
  const names = {
    scheduling: ["Προγραμματισμός", "Scheduling Studio"],
    dashboard: ["Επισκόπηση", "Overview"],
    operations: ["Λειτουργία", "Operations"],
    drivers: ["Οδηγοί", "Drivers"],
    fleet: ["Στόλος", "Fleet"],
    timetables: ["Δρομολόγια", "Timetables"],
    planning: ["Ημέρα υπηρεσίας", "Service day"],
    imports: ["Εισαγωγές", "Data imports"],
    office: ["Γραφείο", "Office"],
    team: ["Ομάδα", "Team"],
    reports: ["Αναφορές", "Reports"],
    archive: ["Αρχείο αναφοράς", "Reference archive"],
  };
  return (
    <header className="app-topbar">
      <div className="breadcrumb">
        <span>{locale === "el" ? "Χώρος εργασίας" : "Workspace"}</span>
        <ChevronRight size={13} />
        <strong>{names[currentTab][locale === "el" ? 0 : 1]}</strong>
      </div>
      {error === "logout_unavailable" && (
        <span role="alert">
          {locale === "el"
            ? "Η αποσύνδεση απέτυχε. Δοκιμάστε ξανά."
            : "Sign-out failed. Please try again."}
        </span>
      )}
      <div className="topbar-actions">
        <div className="locale-switch">
          <button
            className={locale === "el" ? "active" : ""}
            onClick={() => setLocale("el")}
          >
            ΕΛ
          </button>
          <button
            className={locale === "en" ? "active" : ""}
            onClick={() => setLocale("en")}
          >
            EN
          </button>
        </div>
        <button
          className="icon-button"
          onClick={toggle}
          aria-label="Toggle theme"
        >
          {dark ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <span className="topbar-divider" />
        <div className="user-avatar">
          {user?.fullName.slice(0, 2).toUpperCase()}
        </div>
        <div className="user-identity">
          <strong>{user?.fullName}</strong>
          <small>
            {
              {
                admin: ["Διαχειριστής", "Administrator"],
                dispatcher: ["Δρομολογητής", "Dispatcher"],
                fleet_manager: ["Υπεύθυνος στόλου", "Fleet manager"],
                driver: ["Οδηγός", "Driver"],
                management: ["Διοίκηση", "Management"],
                viewer: ["Προβολή", "Viewer"],
              }[user?.role ?? "viewer"][locale === "el" ? 0 : 1]
            }
          </small>
        </div>
        <button
          className="icon-button"
          onClick={() => void logout()}
          aria-label={locale === "el" ? "Αποσύνδεση" : "Sign out"}
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  );
}
