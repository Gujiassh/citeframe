"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMemorySession } from "./session-context";
import { memoryRequest, prepareMutation, uncertain, type PendingMutation } from "./client";
import { errorDetail, MemoryError } from "./errors";
import { bodyFree } from "./body-free";
import type { CorrectionOutcome } from "./correction-recovery";
import type { DeleteReceipt, Memory, MutationReceipt, Operation, Page, Status } from "./types";

export type UnavailableTarget = Extract<Memory, { contentAvailable: false }> | "erased" | "source_unavailable" | "not_found";

export function useMemoryManagement(workspaceId: string, onRevoke: () => void) {
  const { pending, setPending, revoke: clearSession, epoch: scopeEpoch } = useMemorySession(workspaceId);
  const life = useRef<AbortController | null>(null);
  const listEpoch = useRef(0);
  const suppressed = useRef<Record<string, UnavailableTarget>>({});
  const [unavailable, setUnavailable] = useState<Record<string, UnavailableTarget>>({});
  const mutationLock = useRef(pending !== null);
  const [page, setPage] = useState<Page | null>(null);
  const [status, setStatus] = useState<Status>("active");
  const currentStatus = useRef<Status>("active");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<MemoryError | null>(null);
  const [busy, setBusy] = useState(false);
  const [correctionEvent, setCorrectionEvent] = useState<CorrectionOutcome | null>(null);
  const notifyCorrection = useCallback((operation: PendingMutation, kind: CorrectionOutcome["kind"], code?: string) => {
    if (operation.method === "POST" && operation.path.endsWith("/corrections")) setCorrectionEvent({ epoch: scopeEpoch, requestId: operation.requestId, method: operation.method, path: operation.path, kind, code });
  }, [scopeEpoch]);
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [completed, setCompleted] = useState(0);
  const [receipt, setReceipt] = useState<{ resultVersion: number; currentVersion: number } | null>(null);
  const invalidate = useCallback((id: string, reason: UnavailableTarget) => {
    suppressed.current = { ...suppressed.current, [id]: reason };
    ++listEpoch.current;
    setUnavailable(suppressed.current);
    setPage(previous => previous ? { ...previous, items: previous.items.flatMap(item => {
      if (item.id !== id) return [item];
      if (typeof reason === "object") return currentStatus.current === "all" || currentStatus.current === reason.displayStatus ? [reason] : [];
      return reason === "source_unavailable" ? [bodyFree(item)] : [];
    }) } : null);
    setLoading(false); setReceipt(null);
  }, []);
  const revoked = useCallback((failure: MemoryError) => {
    if (failure.detail.code === "authentication_required" || failure.detail.code === "workspace_not_found") {
      life.current?.abort(); clearSession(); onRevoke(); return true;
    }
    return false;
  }, [onRevoke, clearSession]);
  const report = useCallback((failure: unknown) => {
    const e = failure instanceof MemoryError ? failure : new MemoryError(errorDetail("temporarily_unavailable"));
    if (!revoked(e)) setError(e);
  }, [revoked]);
  const load = useCallback(async (filter: Status, cursor?: string) => {
    const controller = life.current;
    if (!controller || controller.signal.aborted) return;
    const epoch = ++listEpoch.current;
    setLoading(true); setPage(null);
    try {
      const query = new URLSearchParams({ status: filter, scope: "workspace", limit: "30" });
      if (cursor) query.set("cursor", cursor);
      const result = await memoryRequest<Page>(workspaceId, `memories?${query}`, controller.signal);
      if (!controller.signal.aborted && epoch === listEpoch.current) {
        for (const item of result.items) if (!item.contentAvailable && suppressed.current[item.id] !== "erased" && suppressed.current[item.id] !== "not_found") suppressed.current = { ...suppressed.current, [item.id]: item };
        setUnavailable(suppressed.current);
        setPage({ ...result, items: result.items.flatMap(item => {
          const hidden = suppressed.current[item.id];
          if (hidden === "erased" || hidden === "not_found") return [];
          return [hidden ? bodyFree(item) : item];
        }) });
      }
    } catch (failure) { if (!controller.signal.aborted && epoch === listEpoch.current) report(failure); }
    finally { if (!controller.signal.aborted && epoch === listEpoch.current) setLoading(false); }
  }, [workspaceId, report]);
  useEffect(() => {
    const controller = new AbortController(); life.current = controller;
    void load("active");
    return () => { controller.abort(); life.current = null; };
  }, [load]);
  const refresh = useCallback(() => { setReceipt(null); setError(previous => previous?.detail.code === "version_conflict" || previous?.detail.code === "terminal_memory" ? previous : null); setRevision(n => n + 1); void load(status); }, [load, status]);
  const finish = useCallback((result: MutationReceipt | DeleteReceipt | Operation, operation: PendingMutation) => {
    notifyCorrection(operation, "success");
    setReceipt({ resultVersion: result.resultVersion, currentVersion: "currentVersion" in result ? result.currentVersion : "memory" in result ? result.memory.version : result.version });
    const id = "resourceId" in result ? result.resourceId : "memory" in result ? result.memory.id : result.id;
    const deleted = "memory" in result ? result.memory.intent === "deleted" : result.intent === "deleted";
    setSelected(deleted ? null : id); setPending(null); setError(null); mutationLock.current = false;
    setCompleted(n => n + 1); setRevision(n => n + 1); void load(status);
  }, [load, status, setPending, notifyCorrection]);
  const send = useCallback(async (operation: PendingMutation) => {
    const controller = life.current;
    if (!controller || controller.signal.aborted) return;
    setBusy(true); setError(null);
    try {
      const result = await memoryRequest<MutationReceipt | DeleteReceipt>(workspaceId, operation.path, controller.signal, operation);
      if (!controller.signal.aborted) finish(result, operation);
    } catch (failure) {
      if (controller.signal.aborted) return;
      const e = failure instanceof MemoryError ? failure : new MemoryError(errorDetail("outcome_unknown", operation.requestId));
      if (revoked(e)) return;
      setError(e);
      const target = /^memories\/([^/]+)(?:\/corrections)?$/.exec(operation.path)?.[1];
      if (target && ["erased", "memory_not_found", "source_version_unavailable", "source_not_found"].includes(e.detail.code)) invalidate(target, e.detail.code === "erased" ? "erased" : e.detail.code === "memory_not_found" ? "not_found" : "source_unavailable");
      notifyCorrection(operation, uncertain(e) ? "unknown" : "failure", e.detail.code);
      if (!uncertain(e)) { setPending(null); mutationLock.current = false; }
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }, [workspaceId, finish, revoked, setPending, notifyCorrection, invalidate]);
  const mutate = useCallback((path: string, method: PendingMutation["method"], body: Record<string, unknown>) => {
    if (pending || mutationLock.current) return null;
    mutationLock.current = true;
    const operation = prepareMutation(path, method, body); setPending(operation); void send(operation); return operation;
  }, [send, pending, setPending]);
  useEffect(() => {
    if (!pending || busy) return;
    const controller = life.current;
    if (!controller) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await memoryRequest<Operation>(workspaceId, `memories/requests/${pending.requestId}`, controller.signal);
        if (!stopped && !controller.signal.aborted) { finish(result, pending); return; }
      } catch (failure) {
        if (stopped || controller.signal.aborted) return;
        const e = failure instanceof MemoryError ? failure : new MemoryError(errorDetail("outcome_unknown", pending.requestId));
        if (revoked(e)) return;
        // A 404 lookup cannot prove that the in-flight mutation will not commit.
        if (e.detail.code !== "operation_not_found" && e.detail.code !== "operation_in_progress") setError(e);
      }
      if (!stopped) timer = setTimeout(poll, 2500);
    };
    timer = setTimeout(poll, 1500);
    return () => { stopped = true; clearTimeout(timer); };
  }, [pending, busy, workspaceId, finish, revoked]);
  const changeStatus = (value: Status) => { currentStatus.current = value; setStatus(value); setSelected(null); setError(null); void load(value); };
  return { clearSelection: () => setSelected(null), correctionEvent, unavailable, invalidate, page, status, loading, error, pending, busy, selected, revision, completed, receipt, report, refresh, mutate,
    select: (memory: Memory) => {
      setError(null); setSelected(memory.id);
    }, changeStatus,
    next: () => { if (page?.nextCursor) void load(status, page.nextCursor); },
    retry: () => { if (pending && !busy) void send(pending); },
  };
}
