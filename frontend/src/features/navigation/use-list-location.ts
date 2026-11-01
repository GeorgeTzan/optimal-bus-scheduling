"use client";
import { useCallback, useEffect, useState } from "react";
import {
  listPage,
  locationEvent,
  writeWorkspaceUrl,
} from "./workspace-location";

export function useListLocation() {
  const [value, setValue] = useState({ q: "", page: 1 });
  useEffect(() => {
    const sync = () => {
      const url = new URL(window.location.href);
      setValue({
        q: (url.searchParams.get("q") ?? "").slice(0, 160),
        page: listPage(url.searchParams.get("page")),
      });
    };
    sync();
    window.addEventListener(locationEvent, sync);
    return () => {
      window.removeEventListener(locationEvent, sync);
    };
  }, []);
  const setQuery = useCallback((q: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("q", q.slice(0, 160));
    url.searchParams.delete("page");
    writeWorkspaceUrl(url, true);
    setValue({ q: q.slice(0, 160), page: 1 });
  }, []);
  const setPage = useCallback(
    (page: number | ((current: number) => number)) => {
      const url = new URL(window.location.href),
        current = listPage(url.searchParams.get("page"));
      const selected = typeof page === "function" ? page(current) : page;
      url.searchParams.set("page", String(selected));
      writeWorkspaceUrl(url);
      setValue({
        q: (url.searchParams.get("q") ?? "").slice(0, 160),
        page: listPage(String(selected)),
      });
    },
    [],
  );
  return { query: value.q, page: value.page, setQuery, setPage };
}
