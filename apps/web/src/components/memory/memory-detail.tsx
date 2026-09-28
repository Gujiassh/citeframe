"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n-context";
import { memoryRequest } from "@/lib/memory/client";
import { bodyFree } from "@/lib/memory/body-free";
import type { UnavailableTarget } from "@/lib/memory/use-memory-management";
import { MemoryError } from "@/lib/memory/errors";
import type { AvailableMemory, InstructionSource, Memory, Page, SourceRef } from "@/lib/memory/types";
import { button } from "./memory-form";
import { MemorySource } from "./memory-source";
import { MemoryRecord } from "./memory-record";

type Props = { readOnly?: boolean; labelKey?: "memory.detail" | "memory.originalPredecessor"; unavailable?: UnavailableTarget; invalidate: (id: string, reason: UnavailableTarget) => void; workspaceId: string; id: string; revision: number; completed: number; busy: boolean; lifecycleLocked: boolean; correctionOpen: boolean; onCorrect: (memory: AvailableMemory) => void; managed?: boolean; projection?: AvailableMemory | null; report: (error: unknown) => void; mutate: (path: string, method: "POST" | "PATCH" | "DELETE", body: Record<string, unknown>) => void };
export function MemoryDetail({ readOnly = false, labelKey = "memory.detail", workspaceId, id, revision, completed, busy, lifecycleLocked, correctionOpen, onCorrect, managed = false, projection, report, mutate, invalidate, unavailable }: Props) {
  const { t } = useTranslation();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [history, setHistory] = useState<Page | null>(null);
  const [source, setSource] = useState<InstructionSource | null>(null);
  const [readBusy, setReadBusy] = useState(false);
  const [loadedRevision, setLoadedRevision] = useState(-1);
  const life = useRef<AbortController | null>(null);
  const readEpoch = useRef(0);
  const suppressed = !!unavailable;
  const [observed, setObserved] = useState({ revision, completed, suppressed, managed, projection });
  if (observed.revision !== revision || observed.completed !== completed || observed.managed !== managed || observed.projection !== projection || observed.suppressed !== suppressed) {
    setObserved({ revision, completed, suppressed, managed, projection });
    if (observed.revision !== revision || observed.completed !== completed) {
      setMemory(null); setHistory(null); setSource(null); setReadBusy(false);
    }
    if (observed.suppressed !== suppressed) {
      setMemory(null); setSource(null);
      setHistory(previous => previous ? { ...previous, items: previous.items.map(bodyFree) } : null);
    }
    if (observed.managed !== managed || observed.projection !== projection) { setHistory(null); setSource(null); setReadBusy(false); }
  }
  useEffect(() => {
    const controller = new AbortController(); life.current = controller;
    if (managed) return () => controller.abort();
    void memoryRequest<{ memory: Memory }>(workspaceId, `memories/${id}`, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        const current = suppressed ? bodyFree(result.memory) : result.memory;
        if (!current.contentAvailable) { setSource(null); invalidate(id, current); }
        setMemory(current); setLoadedRevision(revision);
      }
    }).catch(error => {
      if (controller.signal.aborted) return;
      if (error instanceof MemoryError && (error.status === 410 || error.detail.code === "memory_not_found")) { invalidate(id, error.detail.code === "erased" ? "erased" : "not_found"); }
      report(error);
    });
    return () => controller.abort();
  }, [workspaceId, id, revision, report, invalidate, suppressed, managed, projection]);
  const read = async (kind: "history" | "source", ref?: SourceRef, cursor?: string) => {
    const controller = life.current;
    if (!controller || controller.signal.aborted) return;
    const epoch = ++readEpoch.current; setReadBusy(true); setSource(null); setHistory(null);
    try {
      if (kind === "source") {
        const result = await memoryRequest<InstructionSource>(workspaceId, "sources/read", controller.signal, undefined, { sourceRef: ref });
        if (!controller.signal.aborted && epoch === readEpoch.current) setSource(result);
      } else {
        const query = new URLSearchParams({ limit: "30" }); if (cursor) query.set("cursor", cursor);
        const result = await memoryRequest<Page>(workspaceId, `memories/${id}/revisions?${query}`, controller.signal);
        if (!controller.signal.aborted && epoch === readEpoch.current) {
          const unreadable = result.items.some(item => !item.contentAvailable);
          setHistory(suppressed || unreadable ? { ...result, items: result.items.map(bodyFree) } : result);
          if (unreadable && !suppressed) {
            setMemory(null); setSource(null);
            invalidate(id, "source_unavailable");
          }
        }
      }
    } catch (error) {
      if (!controller.signal.aborted && epoch === readEpoch.current) {
        if (error instanceof MemoryError && (error.detail.code === "erased" || error.detail.code === "memory_not_found" || error.detail.code === "source_version_unavailable" || error.detail.code === "source_not_found")) { invalidate(id, error.detail.code === "erased" ? "erased" : error.detail.code === "memory_not_found" ? "not_found" : "source_unavailable"); }
        report(error);
      }
    } finally { if (!controller.signal.aborted && epoch === readEpoch.current) setReadBusy(false); }
  };
  const current = managed ? (suppressed ? null : projection) : loadedRevision === revision ? memory : null;
  return <section aria-label={t(labelKey)} className="space-y-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
    <h4 className="text-sm font-semibold">{t(labelKey)}</h4>
    {current ? <>
      <MemoryRecord memory={current} />
      <div className="flex flex-wrap gap-2">
        {!readOnly && current.contentAvailable && current.intent === "active" && <button className={button} disabled={busy || correctionOpen} onClick={() => onCorrect(current)}>{t("memory.correct")}</button>}
        {!readOnly && current.intent === "active" && <button className={button} disabled={busy || lifecycleLocked} onClick={() => mutate(`memories/${id}`, "PATCH", { expectedVersion: current.version, intent: "inactive" })}>{t("memory.deactivate")}</button>}
        {!readOnly && current.intent !== "deleted" && <button className={button} disabled={busy || lifecycleLocked} onClick={() => { if (window.confirm(t("memory.deleteWarning"))) mutate(`memories/${id}`, "DELETE", { expectedVersion: current.version }); }}>{t("memory.delete")}</button>}
        <button className={button} disabled={readBusy} onClick={() => void read("history")}>{t("memory.history")}</button>
        {current.contentAvailable && current.sourceRefs.map((ref, index) => <button key={`${ref.sourceId}:${ref.sourceVersion}`} className={button} disabled={readBusy} onClick={() => void read("source", ref)}>{t("memory.originalSource")} {index + 1}</button>)}
      </div>
    </> : <p role="status" className="text-xs">{t(suppressed ? "memory.sourceUnavailable" : "memory.loading")}</p>}
    {readBusy && <p role="status" className="text-xs">{t("memory.loading")}</p>}
    {history && <section aria-label={t("memory.history")} className="space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-800"><h5 className="text-xs font-semibold">{t("memory.history")}</h5>{history.items.map(item => <div key={`${item.id}:${item.version}`} className="space-y-2"><MemoryRecord memory={item} />{item.contentAvailable && item.sourceRefs.map((ref, index) => <button key={`${ref.sourceId}:${ref.sourceVersion}`} className={button} disabled={readBusy} onClick={() => void read("source", ref)}>{t("memory.originalSource")} {index + 1} · {t("memory.version")} {item.version}</button>)}</div>)}{history.nextCursor && <button className={button} onClick={() => void read("history", undefined, history.nextCursor!)}>{t("memory.next")}</button>}</section>}
    {source && <MemorySource source={source} />}
  </section>;
}
