"use client";
import { useCallback, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import type { PendingMutation } from "@/lib/memory/client";
import { usePendingNavigation } from "@/lib/memory/use-pending-navigation";
import { alignSession, newSession, updatePending, revokeSession } from "@/lib/memory/session-state";

import { MemorySessionContext } from "@/lib/memory/session-context";

export function MemorySessionProvider({ children }: { children: ReactNode }) {
  const { user, isHydrating } = useAuth();
  const pathname = usePathname();
  const actor = !isHydrating && user ? user.userId : null;
  const [stored, setStored] = useState(() => newSession(actor, pathname));
  const session = alignSession(stored, actor, pathname);
  // Render-phase alignment prevents an old scope from reaching any consumer render.
  if (session !== stored) setStored(session);
  const epoch = session.epoch;
  const setPending = useCallback((pending: PendingMutation | null) => {
    setStored(current => updatePending(current, epoch, pending));
  }, [epoch]);
  const revoke = useCallback(() => {
    setStored(current => revokeSession(current, epoch));
  }, [epoch]);
  usePendingNavigation(session.pending !== null);
  return <MemorySessionContext.Provider value={{ ...session, setPending, revoke }}>{children}</MemorySessionContext.Provider>;
}
