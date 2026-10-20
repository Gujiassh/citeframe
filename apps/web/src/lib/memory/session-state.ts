import type { PendingMutation } from "./client";
export type MemorySession = { actor: string | null; workspaceId: string | null; epoch: number; revoked: boolean; pending: PendingMutation | null };
const workspaceFromPath = (pathname: string) => /^\/workspaces\/([^/]+)(?:\/|$)/.exec(pathname)?.[1] ?? null;
export function newSession(actor: string | null, pathname: string): MemorySession {
  return { actor, workspaceId: actor ? workspaceFromPath(pathname) : null, epoch: 0, revoked: false, pending: null };
}
export function alignSession(previous: MemorySession, actor: string | null, pathname: string): MemorySession {
  const workspaceId = actor ? workspaceFromPath(pathname) ?? (actor === previous.actor ? previous.workspaceId : null) : null;
  if (actor === previous.actor && workspaceId === previous.workspaceId) return previous;
  return { actor, workspaceId, epoch: previous.epoch + 1, revoked: false, pending: null };
}
export function updatePending(current: MemorySession, epoch: number, pending: PendingMutation | null): MemorySession {
  return current.epoch === epoch && !current.revoked ? { ...current, pending } : current;
}
export function revokeSession(current: MemorySession, epoch: number): MemorySession {
  return current.epoch === epoch ? { ...current, epoch: epoch + 1, revoked: true, pending: null } : current;
}
