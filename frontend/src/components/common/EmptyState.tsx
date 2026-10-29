"use client";

import React from "react";
import { useI18n } from "../../i18n/context";

interface EmptyStateProps {
  title?: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
}

export function EmptyState({ title, description, actionText, onAction }: EmptyStateProps) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
      <div className="w-12 h-12 mb-3 text-slate-400 dark:text-slate-500 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
        🚌
      </div>
      <h3 className="text-base font-semibold text-slate-800 dark:text-slate-200">
        {title ?? t("common.empty")}
      </h3>
      {description && (
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 max-w-sm">
          {description}
        </p>
      )}
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="mt-4 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition"
        >
          {actionText}
        </button>
      )}
    </div>
  );
}
