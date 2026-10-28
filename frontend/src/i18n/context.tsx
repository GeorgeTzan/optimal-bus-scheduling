"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import elCatalog from "./el.json";
import enCatalog from "./en.json";

export type Locale = "el" | "en";

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
  formatTime: (minutesSinceMidnight: number) => string;
  formatDate: (date: Date | string) => string;
}

const catalogs: Record<Locale, Record<string, unknown>> = {
  el: elCatalog,
  en: enCatalog,
};

const I18nContext = createContext<I18nContextType | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("el");

  useEffect(() => {
    const saved = localStorage.getItem("ktel_locale") as Locale;
    if (saved === "el" || saved === "en") {
      setLocaleState(saved);
    }
  }, []);

  useEffect(() => { document.documentElement.lang = locale; }, [locale]);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem("ktel_locale", newLocale);
  };

  const t = (path: string): string => {
    const keys = path.split(".");
    let current: unknown = catalogs[locale];
    for (const key of keys) {
      if (current && typeof current === "object" && key in (current as Record<string, unknown>)) {
        current = (current as Record<string, unknown>)[key];
      } else {
        return path;
      }
    }
    return typeof current === "string" ? current : path;
  };

  const formatTime = (minutesSinceMidnight: number): string => {
    const hours = Math.floor(minutesSinceMidnight / 60) % 24;
    const mins = minutesSinceMidnight % 60;
    const hh = hours.toString().padStart(2, "0");
    const mm = mins.toString().padStart(2, "0");
    return `${hh}:${mm}`;
  };

  const formatDate = (date: Date | string): string => {
    const d = typeof date === "string" ? new Date(date) : date;
    return new Intl.DateTimeFormat(locale === "el" ? "el-GR" : "en-US", {
      timeZone: "Europe/Athens",
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(d);
  };

  return (
    <I18nContext.Provider value={{ locale, setLocale, t, formatTime, formatDate }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextType {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
