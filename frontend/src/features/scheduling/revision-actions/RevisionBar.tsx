"use client";

import React from "react";
import { useI18n } from "../../../i18n/context";
import type { StudioRevision } from "../types";

interface RevisionBarProps {
  revision: StudioRevision;
  userRole?: string;
  isPublishing?: boolean;
  onRequestApproval: () => void;
  onApprove: () => void;
  onPublish: () => void;
}

export function RevisionBar({
  revision,
  userRole = "dispatcher",
  isPublishing = false,
  onRequestApproval,
  onApprove,
  onPublish,
}: RevisionBarProps) {
  const { locale } = useI18n();
  const isEl = locale === "el";

  const statusColors: Record<StudioRevision["status"], string> = {
    draft: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300",
    approval_requested: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300 border-blue-300",
    approved: "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300 border-purple-300",
    published: "bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-300 border-green-300",
  };

  const statusLabels: Record<StudioRevision["status"], { el: string; en: string }> = {
    draft: { el: "Προσχέδιο", en: "Draft" },
    approval_requested: { el: "Σε Έγκριση", en: "Pending Approval" },
    approved: { el: "Εγκεκριμένο", en: "Approved" },
    published: { el: "Δημοσιευμένο (Κλειδωμένο)", en: "Published (Locked)" },
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 p-3 bg-card border-b border-border">
      <div className="flex items-center gap-3">
        <div className="font-bold text-sm tracking-wide">
          {isEl ? "Έκδοση" : "Revision"} <span className="font-mono text-primary">v{revision.version}</span>
        </div>

        <span
          className={`px-2.5 py-0.5 text-xs font-semibold rounded-full border ${
            statusColors[revision.status]
          }`}
        >
          {statusLabels[revision.status][isEl ? "el" : "en"]}
        </span>

        <span className="text-xs text-muted-foreground hidden sm:inline">
          {isEl ? "Συντάκτης" : "Author"}: <strong>{revision.author}</strong>
        </span>
      </div>

      <div className="flex items-center gap-2">
        {revision.status === "draft" && (
          <button
            onClick={onRequestApproval}
            className="px-3 py-1.5 text-xs font-medium rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border"
          >
            {isEl ? "Αίτηση Έγκρισης" : "Request Approval"}
          </button>
        )}

        {revision.status === "approval_requested" && userRole === "admin" && (
          <button
            onClick={onApprove}
            className="px-3 py-1.5 text-xs font-medium rounded bg-purple-600 text-white hover:bg-purple-500 shadow-sm"
          >
            {isEl ? "Έγκριση Προγράμματος" : "Approve Schedule"}
          </button>
        )}

        {(revision.status === "approved" || revision.status === "draft") && (
          <button
            onClick={onPublish}
            disabled={isPublishing}
            className="px-4 py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 shadow-sm"
          >
            {isPublishing
              ? isEl ? "Έλεγχος & Δημοσίευση..." : "Verifying & Publishing..."
              : isEl ? "Επίσημη Δημοσίευση" : "Publish Schedule"}
          </button>
        )}

        {revision.status === "published" && (
          <span className="text-xs text-green-700 dark:text-green-400 font-medium flex items-center gap-1">
            <span>✓</span> {isEl ? "Αμετάβλητο Πρόγραμμα" : "Immutable Schedule"}
          </span>
        )}
      </div>
    </div>
  );
}
