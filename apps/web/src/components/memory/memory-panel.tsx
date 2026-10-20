"use client";
import { useCallback, useState } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import { useTranslation } from "@/lib/i18n-context";
import { useMemorySession } from "@/lib/memory/session-context";
import { useCorrectionRecovery } from "@/lib/memory/use-correction-recovery";
import { MemoryRecovery } from "./memory-recovery";
import { useMemoryManagement } from "@/lib/memory/use-memory-management";
import { statuses, type Statement, type Status } from "@/lib/memory/types";
import { MemoryDetail } from "./memory-detail";
import { MemoryForm, button, control } from "./memory-form";

export function MemoryPanel({ workspaceId }: { workspaceId: string }) {
  const { user, isHydrating } = useAuth();
  const { t } = useTranslation();
  const session = useMemorySession(workspaceId);
  if (!user || isHydrating || !session.matches) return null;
  if (session.revoked) return <p role="alert" className="p-4 text-xs">{t("memory.accessLost")}</p>;
  return <MemoryScope key={`${user.userId}:${workspaceId}:${session.epoch}`} workspaceId={workspaceId} />;
}
function MemoryScope({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const [revoked, setRevoked] = useState(false);
  const revoke = useCallback(() => setRevoked(true), []);
  if (revoked) return <p role="alert" className="p-4 text-xs">{t("memory.accessLost")}</p>;
  return <MemoryManagement workspaceId={workspaceId} onRevoke={revoke} />;
}
function MemoryManagement({ workspaceId, onRevoke }: { workspaceId: string; onRevoke: () => void }) {
  const { t } = useTranslation();
  const state = useMemoryManagement(workspaceId, onRevoke);
  const [create, setCreate] = useState<number | null>(null);
  const creating = create !== null && create === state.completed;
  const locked = state.busy || !!state.pending;
  const recovery = useCorrectionRecovery({ workspaceId, unavailable: state.unavailable, outcome: state.correctionEvent, completed: state.completed, locked, selectedId: state.selected, clearSelection: state.clearSelection, invalidate: state.invalidate, report: state.report, mutate: state.mutate });
  const recovering = recovery.recovering;
  const managedDetail = recovering || (!!recovery.state?.proof && recovery.state.proof.candidate.id === state.selected);
  const unavailable = state.selected ? state.unavailable[state.selected] : undefined;
  const submit = (statement: Statement) => state.mutate("memories", "POST", { ...statement, scope: { kind: "workspace" }, sourceRefs: [] });
  return <div className="h-full overflow-y-auto p-4 sm:p-8"><div className="mx-auto max-w-3xl space-y-4 text-zinc-900 dark:text-zinc-100">
    <p className="text-xs text-zinc-500">{t("memory.privacy")}</p>
    <div className="flex flex-wrap items-center gap-2">
      <label className="min-w-36 text-xs"><span className="sr-only">{t("memory.status")}</span><select className={control} aria-label={t("memory.status")} value={state.status} disabled={state.loading || locked} onChange={e => state.changeStatus(e.target.value as Status)}>{statuses.map(s => <option key={s} value={s}>{t(`memory.${s}`)}</option>)}</select></label>
      <button className={button} onClick={() => { state.refresh(); recovery.refresh(); }}>{t("memory.refresh")}</button>
      <button className={button} disabled={locked || creating || !!recovery.state} onClick={() => setCreate(state.completed)}>{t("memory.create")}</button>
    </div>
    {state.error && <p role="alert" className="text-xs text-red-600">{state.error.message}</p>}
    {state.pending && <div role="status" className="space-y-2 text-xs"><p>{t("memory.pending")}</p><p className="break-all font-mono">{state.pending.requestId}</p><button className={button} disabled={state.busy} onClick={state.retry}>{t("memory.retryOriginal")}</button></div>}
    {state.receipt && <p role="status" className="text-xs text-zinc-500">{t("memory.resultVersion")} {state.receipt.resultVersion} · {t("memory.currentVersion")} {state.receipt.currentVersion}</p>}
    {creating && <MemoryForm key={create} busy={locked} conflict={false} onSubmit={submit} onCancel={() => setCreate(null)} />}
    {state.loading && <p role="status" className="text-xs">{t("memory.loading")}</p>}
    {state.page && <>
      {state.page.items.length === 0 ? <p className="py-6 text-xs text-zinc-500">{t("memory.empty")}</p> : <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">{state.page.items.map(item => <li key={item.id}><button className="w-full space-y-1 px-4 py-3 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-900" aria-pressed={state.selected === item.id} disabled={locked} onClick={() => { state.select(item); recovery.choose(item.id); }}><span className="block break-words">{item.contentAvailable ? item.conditions.subject : t(item.reason === "erased" ? "memory.erased" : "memory.sourceUnavailable")}</span><span className="text-zinc-500">{t(`memory.${item.displayStatus}`)} · {t("memory.version")} {item.version}</span></button></li>)}</ul>}
      {state.page.nextCursor && <button className={button} disabled={state.loading} onClick={state.next}>{t("memory.next")}</button>}
    </>}
    <MemoryRecovery recovery={recovery} locked={locked} originalDetail={recovery.state?.proof && <MemoryDetail readOnly labelKey="memory.originalPredecessor" key={recovery.state.proof.original.id} workspaceId={workspaceId} id={recovery.state.proof.original.id} revision={state.revision} completed={state.completed} busy={locked} lifecycleLocked correctionOpen onCorrect={recovery.begin} managed projection={recovery.state.proof.original} unavailable={state.unavailable[recovery.state.proof.original.id]} invalidate={state.invalidate} report={state.report} mutate={state.mutate} />} />
    {state.selected && (unavailable === "erased" || unavailable === "not_found") ? <section aria-label={t("memory.detail")} className="rounded-xl border p-4 text-xs">
      <p>{t(unavailable === "erased" ? "memory.erased" : "memory.recordUnavailable")}</p>
    </section> : state.selected && (!managedDetail || recovery.state?.proof?.candidate.id === state.selected) && <MemoryDetail unavailable={unavailable} invalidate={state.invalidate} key={state.selected} workspaceId={workspaceId} id={state.selected} revision={state.revision} completed={state.completed} busy={locked} lifecycleLocked={recovering} correctionOpen={!!recovery.state || creating} onCorrect={recovery.begin} managed={managedDetail} projection={recovery.state?.proof?.candidate.id === state.selected ? recovery.state.proof.candidate : null} report={state.report} mutate={state.mutate} />}
  </div></div>;
}
