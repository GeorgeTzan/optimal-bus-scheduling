"use client";
import { FileSpreadsheet } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { openImport } from "../navigation/workspace-location";
import type { Destination, Entity } from "./contracts";

export function BulkImportButton({
  entity,
  returnTo,
  primary = false,
  label,
}: {
  entity: Entity | "all";
  returnTo: Destination;
  primary?: boolean;
  label?: string;
}) {
  const { user } = useAuth(),
    { locale } = useI18n();
  const capability =
    entity === "drivers"
      ? "drivers.write"
      : entity === "vehicles"
        ? "fleet.write"
        : "timetable.write";
  if (
    !user?.permissions.includes("imports.write") ||
    !user.permissions.includes(capability)
  )
    return null;
  return (
    <button
      type="button"
      className={`button ${primary ? "primary" : "secondary"}`}
      onClick={() => openImport(entity, returnTo)}
    >
      <FileSpreadsheet size={16} />
      {label ??
        (locale === "el" ? "Εισαγωγή από Excel/CSV" : "Import from Excel/CSV")}
    </button>
  );
}
