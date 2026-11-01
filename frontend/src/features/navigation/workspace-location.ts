import type { ShellTab } from "../../components/layout/Shell";
import type { Destination, Entity } from "../imports/contracts";
import { mayLeaveWorkspace } from "./unsaved-changes";

const views: ShellTab[] = [
  "dashboard",
  "scheduling",
  "operations",
  "drivers",
  "fleet",
  "timetables",
  "planning",
  "imports",
  "office",
  "team",
  "archive",
];
const entities: (Entity | "all")[] = [
  "drivers",
  "vehicles",
  "stations",
  "timetable",
  "pairings",
  "transfers",
  "connections",
  "all",
];
const destinations: Destination[] = [
  "drivers",
  "fleet",
  "timetables",
  "planning",
];
export interface WorkspaceLocation {
  view: ShellTab;
  serviceDate: string | null;
  publicationId?: string | null;
  entity: Entity | "all" | null;
  returnTo: Destination | null;
}
export const locationEvent = "ktel:workspace-location";

export function serviceDay(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const timestamp = Date.parse(value + "T12:00:00Z");
  return Number.isFinite(timestamp) &&
    new Date(timestamp).toISOString().slice(0, 10) === value
    ? value
    : null;
}
export function listPage(value: string | null) {
  const number = value && /^\d+$/.test(value) ? Number(value) : 1;
  return Number.isSafeInteger(number) && number >= 1 && number <= 100000
    ? number
    : 1;
}
export function readWorkspaceLocation(url: URL): WorkspaceLocation {
  const raw = url.searchParams.get("view"),
    view = raw === "reference-archive" ? "archive" : raw;
  const entity = url.searchParams.get("entity"),
    returnTo = url.searchParams.get("return_to");
  return {
    view: views.includes(view as ShellTab) ? (view as ShellTab) : "scheduling",
    serviceDate:
      view === "archive"
        ? null
        : serviceDay(url.searchParams.get("service_date")),
    publicationId:
      view === "operations" &&
      /^[0-9a-f-]{36}$/i.test(url.searchParams.get("publication") ?? "")
        ? url.searchParams.get("publication")
        : null,
    entity: entities.includes(entity as Entity | "all")
      ? (entity as Entity | "all")
      : null,
    returnTo: destinations.includes(returnTo as Destination)
      ? (returnTo as Destination)
      : null,
  };
}
export function normalizeWorkspaceUrl(url: URL) {
  const value = readWorkspaceLocation(url);
  if (value.view === "scheduling") url.searchParams.delete("view");
  else
    url.searchParams.set(
      "view",
      value.view === "archive" ? "reference-archive" : value.view,
    );
  if (value.serviceDate)
    url.searchParams.set("service_date", value.serviceDate);
  else url.searchParams.delete("service_date");
  if (url.searchParams.has("q"))
    url.searchParams.set("q", (url.searchParams.get("q") ?? "").slice(0, 160));
  if (listPage(url.searchParams.get("page")) === 1)
    url.searchParams.delete("page");
  else
    url.searchParams.set(
      "page",
      String(listPage(url.searchParams.get("page"))),
    );
  if (value.view !== "operations" || !value.publicationId)
    url.searchParams.delete("publication");
  if (
    value.view !== "operations" ||
    url.searchParams.get("open_only") !== "true"
  )
    url.searchParams.delete("open_only");
  if (!value.entity) url.searchParams.delete("entity");
  if (!value.returnTo) url.searchParams.delete("return_to");
  return url;
}
export function writeWorkspaceUrl(url: URL, replace = false) {
  normalizeWorkspaceUrl(url);
  if (url.href === window.location.href) return true;
  const current = readWorkspaceLocation(new URL(window.location.href)),
    target = readWorkspaceLocation(url);
  if (
    (current.view !== target.view ||
      current.serviceDate !== target.serviceDate ||
      current.publicationId !== target.publicationId) &&
    !mayLeaveWorkspace()
  )
    return false;
  const state = window.history.state as Record<string, unknown> | null;
  const index = typeof state?.ktelIndex === "number" ? state.ktelIndex : 0;
  if (state?.ktelIndex === undefined)
    window.history.replaceState(
      { ...state, ktelIndex: index },
      "",
      window.location.href,
    );
  window.history[replace ? "replaceState" : "pushState"](
    { ...window.history.state, ktelIndex: replace ? index : index + 1 },
    "",
    url,
  );
  window.dispatchEvent(new Event(locationEvent));
  return true;
}

export function openImport(entity: Entity | "all", returnTo: Destination) {
  const url = new URL(window.location.href);
  for (const key of ["q", "page", "batch", "resource"])
    url.searchParams.delete(key);
  url.searchParams.set("view", "imports");
  url.searchParams.set("entity", entity);
  url.searchParams.set("return_to", returnTo);
  writeWorkspaceUrl(url);
}
