"use client";
import { useEffect } from "react";

export function usePendingNavigation(pending: boolean) {
  useEffect(() => {
    if (!pending) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", unload);
    return () => window.removeEventListener("beforeunload", unload);
  }, [pending]);
}
