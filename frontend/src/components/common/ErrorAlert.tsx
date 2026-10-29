"use client";

import React from "react";
import { useI18n } from "../../i18n/context";

interface ErrorAlertProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorAlert({ message, onRetry }: ErrorAlertProps) {
  const { t } = useI18n();
  return (
    <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 flex items-start justify-between">
      <div className="flex items-start space-x-3">
        <span className="text-xl">⚠️</span>
        <div>
          <h4 className="text-sm font-semibold">{t("common.error")}</h4>
          {message && <p className="mt-1 text-xs opacity-90">{message}</p>}
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs font-semibold underline hover:no-underline text-rose-700 dark:text-rose-300 ml-4 shrink-0"
        >
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
