"use client";

import React from "react";
import { useI18n } from "../../i18n/context";

export function LoadingState({ message }: { message?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center p-8 space-y-3 text-slate-500 dark:text-slate-400">
      <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-sm font-medium">{message ?? t("common.loading")}</p>
    </div>
  );
}
