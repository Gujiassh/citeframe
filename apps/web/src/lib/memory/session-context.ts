"use client";
import { createContext, useContext } from "react";
import type { PendingMutation } from "./client";
import type { MemorySession } from "./session-state";
export type SessionContext = MemorySession & {
  setPending: (operation: PendingMutation | null) => void;
  revoke: () => void;
};
export const MemorySessionContext = createContext<SessionContext | null>(null);
export function useMemorySession(workspaceId: string) {
  const session = useContext(MemorySessionContext);
  if (!session) throw new Error("MemorySessionProvider is required.");
  return { ...session, matches: session.actor !== null && session.workspaceId === workspaceId };
}
