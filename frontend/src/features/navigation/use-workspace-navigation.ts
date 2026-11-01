"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ShellTab } from "../../components/layout/Shell";
import {
  locationEvent,
  normalizeWorkspaceUrl,
  readWorkspaceLocation,
  writeWorkspaceUrl,
  type WorkspaceLocation,
} from "./workspace-location";
import { mayLeaveWorkspace } from "./unsaved-changes";

export interface NavigateOptions {
  serviceDate?: string | null;
  entity?: WorkspaceLocation["entity"];
  returnTo?: WorkspaceLocation["returnTo"];
  replace?: boolean;
}
export function useWorkspaceNavigation() {
  const navigationEpoch = useRef(0);
  const [location, setLocation] = useState<WorkspaceLocation>({
    view: "scheduling",
    serviceDate: null,
    entity: null,
    returnTo: null,
  });
  useEffect(() => {
    let previousUrl = window.location.href;
    let previousIndex =
      (window.history.state as { ktelIndex?: number } | null)?.ktelIndex ?? 0;
    let restoring = false;
    const sync = () => {
      navigationEpoch.current += 1;
      const url = normalizeWorkspaceUrl(new URL(window.location.href));
      if (url.href !== window.location.href)
        window.history.replaceState(window.history.state, "", url);
      setLocation(readWorkspaceLocation(url));
      previousUrl = url.href;
      previousIndex =
        (window.history.state as { ktelIndex?: number } | null)?.ktelIndex ?? 0;
    };
    const pop = () => {
      if (restoring) {
        restoring = false;
        return;
      }
      const old = readWorkspaceLocation(new URL(previousUrl)),
        next = readWorkspaceLocation(new URL(window.location.href));
      if (
        (old.view !== next.view ||
          old.serviceDate !== next.serviceDate ||
          old.publicationId !== next.publicationId) &&
        !mayLeaveWorkspace()
      ) {
        const index = (window.history.state as { ktelIndex?: number } | null)
          ?.ktelIndex;
        if (index !== undefined && index !== previousIndex) {
          restoring = true;
          window.history.go(previousIndex - index);
        } else
          window.history.pushState(
            { ...window.history.state, ktelIndex: previousIndex },
            "",
            previousUrl,
          );
        return;
      }
      window.dispatchEvent(new Event(locationEvent));
    };
    sync();
    window.addEventListener("popstate", pop);
    window.addEventListener(locationEvent, sync);
    return () => {
      navigationEpoch.current += 1;
      window.removeEventListener("popstate", pop);
      window.removeEventListener(locationEvent, sync);
    };
  }, []);
  const navigate = useCallback(
    (view: ShellTab, options: NavigateOptions = {}) => {
      navigationEpoch.current += 1;
      const url = new URL(window.location.href),
        current = readWorkspaceLocation(url);
      if (view !== current.view) {
        for (const key of [
          "q",
          "page",
          "resource",
          "batch",
          "entity",
          "return_to",
          "publication",
          "open_only",
        ])
          url.searchParams.delete(key);
      }
      url.searchParams.set(
        "view",
        view === "archive" ? "reference-archive" : view,
      );
      if (options.serviceDate !== undefined) {
        if (options.serviceDate !== current.serviceDate) {
          url.searchParams.delete("publication");
          url.searchParams.delete("page");
        }
        if (options.serviceDate)
          url.searchParams.set("service_date", options.serviceDate);
        else url.searchParams.delete("service_date");
      }
      if (options.entity) {
        url.searchParams.set("entity", options.entity);
        url.searchParams.delete("batch");
      }
      if (options.returnTo) url.searchParams.set("return_to", options.returnTo);
      if (!writeWorkspaceUrl(url, options.replace)) return false;
      // Same-URL navigation still refreshes state after an external import URL update.
      setLocation(readWorkspaceLocation(new URL(window.location.href)));
      return true;
    },
    [],
  );
  return { location, navigate, navigationEpoch };
}
