"use client";
import type { ReactNode } from "react";
import { useTranslation } from "@/lib/i18n-context";
import type { useCorrectionRecovery } from "@/lib/memory/use-correction-recovery";
import { MemoryForm, StatementOptions, button } from "./memory-form";
import { MemoryRecord } from "./memory-record";
import { statementOf } from "@/lib/memory/correction-recovery";
export function MemoryRecovery({ recovery, locked, originalDetail }: { recovery: ReturnType<typeof useCorrectionRecovery>; locked: boolean; originalDetail: ReactNode }) {
  const { t } = useTranslation();
  const state = recovery.state;
  if (!state) return null;
  const checking = state.phase === "checking" || state.phase === "rechecking-adoption";
  return <section className="space-y-3" aria-label={t("memory.correctionDraft")}>
    <p className="break-all text-xs">{t("memory.originalPredecessor")}: {state.original.id} · {t("memory.version")} {state.original.version}</p>
    <p className="break-all text-xs">{t("memory.editTarget")}: {state.target.id} · {t("memory.version")} {state.target.version}</p>
    {recovery.recovering && <p className="text-xs">{t("memory.chooseSuccessor")}</p>}
    {state.error && <p role="alert" className="text-xs">{t(`memory.recovery.${state.error}`)}</p>}
    <MemoryForm value={state.draft} onChange={recovery.change} busy={locked || checking} conflict={!['editing', 'editing-adopted'].includes(state.phase)} onSubmit={recovery.submit} onCancel={recovery.cancel} />
    {checking && <p role="status" className="text-xs">{t("memory.loading")}</p>}
    {state.proof && state.phase === "compare-ready" && <section aria-label={t("memory.successorComparison")} className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <h4 className="text-sm font-semibold">{t("memory.successorComparison")}</h4>
      <div className="space-y-2"><p className="break-all text-xs">{t("memory.originalPredecessor")}: {state.proof.original.id} · {t("memory.version")} {state.proof.original.version}</p>{originalDetail}<StatementOptions value={statementOf(state.proof.original)} /></div>
      <div className="space-y-2"><p className="break-all text-xs">{t("memory.selectedSuccessor")}: {state.proof.candidate.id} · {t("memory.version")} {state.proof.candidate.version}</p><MemoryRecord memory={state.proof.candidate} /><StatementOptions value={statementOf(state.proof.candidate)} /></div>
      <button className={button} disabled={locked || checking} onClick={recovery.adopt}>{t("memory.continueSuccessor")}</button>
    </section>}
  </section>;
}
