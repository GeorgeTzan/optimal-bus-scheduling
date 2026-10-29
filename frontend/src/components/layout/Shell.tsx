"use client";
import React, { useState } from "react";
import {
  LayoutDashboard,
  CalendarRange,
  Radio,
  UsersRound,
  Users,
  BusFront,
  Upload,
  PanelLeftClose,
  PanelLeftOpen,
  Route,
  ClipboardList,
} from "lucide-react";
import { useAuth } from "../../features/auth/AuthContext";
import { Navbar } from "./Navbar";
import { useI18n } from "../../i18n/context";
export type ShellTab =
  | "dashboard"
  | "scheduling"
  | "operations"
  | "drivers"
  | "fleet"
  | "timetables"
  | "planning"
  | "imports"
  | "office"
  | "team"
  | "reports"
  | "archive";
export function Shell({
  currentTab,
  onTabChange,
  children,
}: {
  currentTab: ShellTab;
  onTabChange: (tab: ShellTab) => void;
  children: React.ReactNode;
}) {
  const { locale } = useI18n();
  const { user } = useAuth();
  const el = locale === "el";
  const [collapsed, setCollapsed] = useState(false);
  const items = [
    {
      id: "dashboard",
      icon: LayoutDashboard,
      el: "Επισκόπηση",
      en: "Overview",
    },
    {
      id: "scheduling",
      icon: CalendarRange,
      el: "Προγραμματισμός",
      en: "Scheduling Studio",
    },
    { id: "operations", icon: Radio, el: "Λειτουργία", en: "Operations" },
    { id: "drivers", icon: UsersRound, el: "Οδηγοί", en: "Drivers" },
    { id: "fleet", icon: BusFront, el: "Στόλος", en: "Fleet" },
    { id: "timetables", icon: Route, el: "Δρομολόγια", en: "Timetables" },
    {
      id: "planning",
      icon: CalendarRange,
      el: "Ημέρα υπηρεσίας",
      en: "Service day",
    },
    { id: "office", icon: ClipboardList, el: "Γραφείο", en: "Office" },
    { id: "team", icon: Users, el: "Ομάδα", en: "Team" },
    { id: "imports", icon: Upload, el: "Εισαγωγές", en: "Data imports" },
  ] as const;
  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar">
        <div className="brand">
          <div className="brand-mark">
            <BusFront size={23} strokeWidth={1.6} />
          </div>
          <div className="brand-type">
            <strong>
              KTEL<span> / </span>
            </strong>
            <small>Operations platform</small>
          </div>
        </div>
        <div className="workspace-selector">
          <span className="workspace-avatar">K</span>
          <div className="sidebar-copy">
            <strong>
              {user?.ktelName ??
                (el ? "Χώρος προγραμματισμού" : "Planning workspace")}
            </strong>
            <small>{el ? "Εσωτερική λειτουργία" : "Internal operations"}</small>
          </div>
        </div>
        <div className="nav-caption">{el ? "ΧΩΡΟΣ ΕΡΓΑΣΙΑΣ" : "WORKSPACE"}</div>
        <nav aria-label={el ? "Κύρια πλοήγηση" : "Main navigation"}>
          {items.filter((item) => {
            const capability = item.id === "team" ? "members.manage" : item.id === "imports" ? "imports.read" : ["drivers","fleet","timetables","planning","dashboard"].includes(item.id) ? "resources.read" : "schedule.read";
            return user?.permissions.includes(capability);
          }).map((item) => (
            <button
              key={item.id}
              aria-current={currentTab === item.id ? "page" : undefined}
              title={el ? item.el : item.en}
              onClick={() => onTabChange(item.id)}
              className={`nav-item ${currentTab === item.id ? "active" : ""}`}
            >
              <item.icon size={18} />
              <span className="sidebar-copy">{el ? item.el : item.en}</span>
              {currentTab === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        {user?.permissions.includes("schedule.read") && <details className="sidebar-advanced">
          <summary>{el ? "Περισσότερα" : "More"}</summary>
          <button
            className={`nav-item ${currentTab === "archive" ? "active" : ""}`}
            onClick={() => onTabChange("archive")}
            title={el ? "Αρχείο αναφοράς" : "Reference archive"}
          >
            <CalendarRange size={18} />
            <span className="sidebar-copy">
              {el ? "Αρχείο αναφοράς" : "Reference archive"}
            </span>
          </button>
        </details>}
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <Route size={22} />
            <strong>
              {el
                ? "Κάθε διαδρομή,\nμε σχέδιο."
                : "Every journey,\nconsidered."}
            </strong>
            <small>KTEL Operations · CV planning</small>
          </div>
          <button
            className="collapse-button"
            onClick={() => setCollapsed(!collapsed)}
            aria-label="Toggle sidebar"
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
            <span className="sidebar-copy">
              {el ? "Σύμπτυξη μενού" : "Collapse navigation"}
            </span>
          </button>
        </div>
      </aside>
      <div className="app-main">
        <Navbar currentTab={currentTab} />
        <main>{children}</main>
      </div>
    </div>
  );
}
