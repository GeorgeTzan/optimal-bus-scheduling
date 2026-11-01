"use client";
import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n/context";
import { registerPendingEdit } from "./unsaved-changes";
export function useUnsavedChanges(dirty: boolean) {
  const { locale } = useI18n();
  const current = useRef({ dirty, message: "" });
  current.current = {
    dirty,
    message:
      locale === "el"
        ? "Έχετε μη αποθηκευμένες αλλαγές. Θέλετε να φύγετε και να τις απορρίψετε;"
        : "You have unsaved changes. Leave and discard them?",
  };
  useEffect(() => {
    const remove = registerPendingEdit(() => current.current);
    const unload = (event: BeforeUnloadEvent) => {
      if (current.current.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => {
      remove();
      window.removeEventListener("beforeunload", unload);
    };
  }, []);
}
