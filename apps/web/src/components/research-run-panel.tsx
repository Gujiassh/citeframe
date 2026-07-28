"use client";

import {
  AlertTriangle,
  Check,
  ChevronDown,
  Circle,
  Download,
  LoaderCircle,
  RotateCcw,
  Square,
  X,
} from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { getLocatorSummary } from "@/lib/evidence/types";
import { useTranslation, type TranslationKey } from "@/lib/i18n-context";
import { getResearchArtifactContentUrl } from "@/lib/research/client";
import { RUN_STATUS_KEYS, STEP_KIND_KEYS, STEP_STATUS_KEYS } from "@/lib/research/presentation";
import type { ResearchStreamState } from "@/lib/use-research";
import type {
  ResearchArtifactDetail,
  ResearchArtifactEvidence,
  ResearchArtifactSummary,
  ResearchRunDetail,
  ResearchRunSummary,
  ResearchStep,
} from "@/lib/research/types";

type Props = {
  workspaceId: string;
  run: ResearchRunDetail | null;
  runs: ResearchRunSummary[];
  artifacts: ResearchArtifactSummary[];
  artifactContent: string;
  artifactDetail: ResearchArtifactDetail | null;
  conflictArtifactContent: string;
  conflictArtifactDetail: ResearchArtifactDetail | null;
  canManage: boolean;
  loading: boolean;
  streamState: ResearchStreamState;
  error: string | null;
  onSelectRun: (runId: string) => void;
  onApprove: () => void;
  onRevisePlan: (question: string, comment: string) => void;
  onCancelPlan: () => void;
  onResolveConflict: (action: "exclude_conflicted_claims" | "keep_as_unresolved" | "cancel_run") => void;
  onRetryStep: (step: ResearchStep) => void;
  onOpenEvidence: (evidence: ResearchArtifactEvidence) => void;
  onCancel: () => void;
};

const terminal = new Set(["completed", "failed", "cancelled"]);

function StepIcon({ status }: { status: string }) {
  if (status === "succeeded") return <Check className="h-3.5 w-3.5" />;
  if (status === "running") return <LoaderCircle className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />;
  if (status === "failed") return <AlertTriangle className="h-3.5 w-3.5" />;
  if (status === "waiting") return <Square className="h-3.5 w-3.5" />;
  return <Circle className="h-3.5 w-3.5" />;
}

function streamStatusKey(state: ResearchStreamState): TranslationKey | null {
  if (state === "connecting") return "research.streamConnecting";
  if (state === "reconnecting") return "research.streamReconnecting";
  if (state === "history_unavailable") return "research.streamHistoryUnavailable";
  if (state === "contract_error") return "research.streamContractError";
  return null;
}

function formatCost(currency: string, amountMicros: number): string {
  return `${currency} ${(amountMicros / 1_000_000).toFixed(2)}`;
}

export function ResearchRunPanel({
  workspaceId,
  run,
  runs,
  artifacts,
  artifactContent,
  artifactDetail,
  conflictArtifactContent,
  conflictArtifactDetail,
  canManage,
  loading,
  streamState,
  error,
  onSelectRun,
  onApprove,
  onRevisePlan,
  onCancelPlan,
  onResolveConflict,
  onRetryStep,
  onOpenEvidence,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const [editingPlan, setEditingPlan] = useState(false);
  const [revisionQuestion, setRevisionQuestion] = useState("");
  const [revisionComment, setRevisionComment] = useState("");

  if (!run) {
    return <div className="flex min-h-[45vh] items-center justify-center text-xs text-zinc-500">{t("research.empty")}</div>;
  }

  const planDecision = run.pendingDecisions.find((item) => item.type === "plan_approval");
  const conflictDecision = run.pendingDecisions.find((item) => item.type === "conflict_resolution");
  const trace = artifacts.find((item) => item.kind === "trace_export");
  const conflictReportReady = Boolean(
    conflictDecision
    && conflictArtifactContent
    && conflictArtifactDetail?.id === conflictDecision.inputArtifactId
    && conflictArtifactDetail.sha256 === conflictDecision.inputArtifactSha256
    && conflictArtifactDetail.kind === "conflict_report",
  );
  const streamKey = streamStatusKey(streamState);
  const submitRevision = () => {
    if (!revisionQuestion.trim() || !revisionComment.trim()) return;
    onRevisePlan(revisionQuestion.trim(), revisionComment.trim());
  };

  return (
    <div className="mx-auto w-full max-w-4xl divide-y divide-border">
      <header className="flex flex-col gap-4 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[10px] font-bold uppercase text-emerald-700 dark:text-emerald-400">
              {t(RUN_STATUS_KEYS[run.status] as TranslationKey)}
            </p>
            {streamState === "live" ? <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-label={t("research.streamLive")} /> : null}
            {streamKey ? <span className="text-[10px] text-amber-700 dark:text-amber-400">{t(streamKey)}</span> : null}
          </div>
          <h3 className="mt-1 text-sm font-semibold text-zinc-950 dark:text-white">{run.question}</h3>
          <p className="mt-1 text-[11px] text-zinc-500">
            {t("research.runCounts").replace("{assets}", String(run.frozenAssetCount)).replace("{artifacts}", String(run.artifactCount))}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {runs.length > 1 ? (
            <label className="relative">
              <span className="sr-only">{t("research.runHistory")}</span>
              <select
                value={run.id}
                onChange={(event) => onSelectRun(event.target.value)}
                disabled={loading}
                className="h-8 max-w-44 appearance-none rounded-md border border-border bg-background pl-2.5 pr-7 text-[11px] font-medium outline-none focus:border-zinc-400 disabled:opacity-50"
              >
                {runs.map((item, index) => (
                  <option key={item.id} value={item.id}>
                    {index === 0 ? `${t("research.latestRun")}: ` : ""}{item.question}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-zinc-400" />
            </label>
          ) : null}
          {canManage && !terminal.has(run.status) && !planDecision ? (
            <button type="button" disabled={loading} onClick={onCancel} className="h-8 rounded-md border border-border px-3 text-xs font-semibold text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-950 disabled:opacity-50 dark:text-zinc-300 dark:hover:bg-zinc-900 dark:hover:text-white">
              {t("research.cancel")}
            </button>
          ) : null}
        </div>
      </header>

      {error ? <p role="alert" className="py-3 text-xs text-red-600 dark:text-red-400">{error}</p> : null}

      {run.plan ? (
        <section className="py-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">
              {t("research.planVersion").replace("{version}", String(run.plan.version))}
            </h4>
            {canManage && planDecision && !editingPlan ? (
              <div className="flex items-center gap-2">
                <button type="button" disabled={loading} onClick={() => setEditingPlan(true)} className="h-8 rounded-md border border-border px-3 text-xs font-semibold transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-900">
                  {t("research.revisePlan")}
                </button>
                <button type="button" disabled={loading} onClick={onApprove} className="h-8 rounded-md bg-zinc-950 px-3 text-xs font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-50 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-100">
                  {t("research.approvePlan")}
                </button>
              </div>
            ) : null}
          </div>

          {editingPlan ? (
            <div className="mt-3 space-y-3 border-y border-border py-3">
              <label className="block">
                <span className="mb-1 block text-[10px] font-semibold text-zinc-500">{t("research.revisedQuestion")}</span>
                <textarea value={revisionQuestion} onChange={(event) => setRevisionQuestion(event.target.value)} rows={3} className="w-full resize-y border border-border bg-background px-3 py-2 text-xs leading-5 outline-none focus:border-zinc-400" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-semibold text-zinc-500">{t("research.revisionReason")}</span>
                <textarea value={revisionComment} onChange={(event) => setRevisionComment(event.target.value)} rows={2} className="w-full resize-y border border-border bg-background px-3 py-2 text-xs leading-5 outline-none focus:border-zinc-400" />
              </label>
              <div className="flex items-center justify-between gap-2">
                <button type="button" disabled={loading} onClick={onCancelPlan} className="h-8 text-xs font-semibold text-red-600 disabled:opacity-50 dark:text-red-400">{t("research.cancelPlan")}</button>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setEditingPlan(false)} className="flex h-8 w-8 items-center justify-center rounded-md border border-border" title={t("research.closeRevision")} aria-label={t("research.closeRevision")}><X className="h-4 w-4" /></button>
                  <button type="button" disabled={loading || !revisionQuestion.trim() || !revisionComment.trim()} onClick={submitRevision} className="h-8 rounded-md bg-zinc-950 px-3 text-xs font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-950">{t("research.submitRevision")}</button>
                </div>
              </div>
            </div>
          ) : (
            <>
              <p className="mt-2 text-xs leading-5 text-zinc-600 dark:text-zinc-300">{run.plan.summary}</p>
              <dl className="mt-3 grid grid-cols-1 gap-x-5 gap-y-3 border-y border-border py-3 text-xs sm:grid-cols-3">
                <div>
                  <dt className="text-[10px] font-semibold text-zinc-500">{t("research.frozenScope")}</dt>
                  <dd className="mt-1 text-zinc-800 dark:text-zinc-200">
                    {(run.frozenAssetScope?.assets ?? []).map((asset) => asset.assetTitle).join(", ")}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold text-zinc-500">{t("research.estimatedCalls")}</dt>
                  <dd className="mt-1 text-zinc-800 dark:text-zinc-200">{run.plan.estimatedProviderCalls}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold text-zinc-500">{t("research.estimatedCost")}</dt>
                  <dd className="mt-1 text-zinc-800 dark:text-zinc-200">
                    {run.plan.estimatedCost
                      ? formatCost(run.plan.estimatedCost.currency, run.plan.estimatedCost.amountMicros)
                      : t("research.costUnavailable")}
                  </dd>
                </div>
              </dl>
              <div className="mt-3 text-xs">
                <h5 className="text-[10px] font-semibold text-zinc-500">{t("research.knownGaps")}</h5>
                {run.plan.knownGaps.length ? (
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-zinc-700 dark:text-zinc-300">
                    {run.plan.knownGaps.map((gap) => <li key={gap}>{gap}</li>)}
                  </ul>
                ) : <p className="mt-1 text-zinc-500">{t("research.noKnownGaps")}</p>}
              </div>
              <ol className="mt-3 divide-y divide-border border-y border-border">
                {run.plan.subproblems.map((item) => (
                  <li key={item.id} className="flex gap-3 py-2.5 text-xs">
                    <span className="w-5 shrink-0 text-zinc-400">{item.order + 1}</span>
                    <span>{item.question}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      ) : null}

      {conflictDecision ? (
        <section className="py-5">
          <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("research.conflictTitle")}</h4>
          {conflictReportReady ? (
            <div className="mt-3 divide-y divide-border border-y border-border">
              {conflictArtifactDetail?.claims.map((claim) => (
                <div key={claim.id} className="py-3">
                  <p className="text-xs leading-5 text-zinc-800 dark:text-zinc-200">{claim.text}</p>
                  <p className="mt-1 text-[10px] text-zinc-500">
                    {t("research.conflictEvidenceCount").replace("{count}", String(claim.evidence.length))}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
          {canManage && conflictReportReady ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={loading} onClick={() => onResolveConflict("exclude_conflicted_claims")} className="h-8 rounded-md bg-zinc-950 px-3 text-xs font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-50 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-100">{t("research.excludeConflicts")}</button>
              <button type="button" disabled={loading} onClick={() => onResolveConflict("keep_as_unresolved")} className="h-8 rounded-md border border-border px-3 text-xs font-semibold transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-900">{t("research.keepUnresolved")}</button>
              <button type="button" disabled={loading} onClick={() => onResolveConflict("cancel_run")} className="h-8 px-2 text-xs font-semibold text-red-600 disabled:opacity-50 dark:text-red-400">{t("research.cancel")}</button>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="py-5">
        <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("research.progress")}</h4>
        <div className="mt-3 divide-y divide-border border-y border-border">
          {run.steps.map((step) => (
            <div key={step.id} className="flex min-h-11 items-center gap-3 py-2 text-xs">
              <span className="text-zinc-500"><StepIcon status={step.status} /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{t((STEP_KIND_KEYS[step.kind] ?? "research.stageUnknown") as TranslationKey)}</span>
                {step.failure ? <span className="mt-0.5 block text-[10px] text-red-600 dark:text-red-400">{step.failure.message}</span> : null}
              </span>
              <span className="text-[10px] text-zinc-500">{t(STEP_STATUS_KEYS[step.status] as TranslationKey)}</span>
              {step.evidenceCount ? <span className="hidden text-[10px] text-emerald-600 sm:inline">{t("research.evidenceCount").replace("{count}", String(step.evidenceCount))}</span> : null}
              {canManage && run.status === "awaiting_retry" && step.status === "failed" && step.failure?.retryable ? (
                <button type="button" onClick={() => onRetryStep(step)} disabled={loading} title={t("research.retryBranch")} aria-label={t("research.retryBranch")} className="flex h-8 w-8 items-center justify-center rounded-md border border-border hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-900"><RotateCcw className="h-3.5 w-3.5" /></button>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      {artifactContent ? (
        <section className="py-5">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("research.report")}</h4>
            <span className="font-mono text-[10px] text-zinc-500">{artifacts.find((item) => item.kind === "final_report")?.sha256.slice(0, 12)}</span>
          </div>
          <article className="mt-3 max-w-none text-sm leading-6 text-zinc-700 [&_a]:text-emerald-700 [&_a]:underline [&_h1]:mb-3 [&_h1]:mt-6 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-base [&_h2]:font-semibold [&_li]:my-1 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-3 [&_strong]:font-semibold [&_strong]:text-zinc-950 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 dark:text-zinc-200 dark:[&_a]:text-emerald-400 dark:[&_strong]:text-white">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifactContent}</ReactMarkdown>
          </article>

          {artifactDetail?.evidence.length ? (
            <div className="mt-5 border-t border-border pt-4">
              <h5 className="text-[10px] font-bold uppercase text-zinc-500">{t("research.reportEvidence")}</h5>
              <div className="mt-2 divide-y divide-border border-y border-border">
                {artifactDetail.evidence.map((evidence) => (
                  <button
                    key={evidence.evidenceLocatorId}
                    type="button"
                    disabled={!evidence.sourceAvailable}
                    onClick={() => onOpenEvidence(evidence)}
                    className="flex w-full items-start justify-between gap-3 py-2.5 text-left text-xs hover:text-emerald-700 disabled:cursor-not-allowed disabled:text-zinc-400 dark:hover:text-emerald-400"
                  >
                    <span className="min-w-0"><span className="block truncate font-medium">{evidence.assetTitle}</span><span className="mt-0.5 block line-clamp-2 text-[10px] leading-4 text-zinc-500">{evidence.excerpt}</span></span>
                    <span className="shrink-0 text-[10px]">{evidence.sourceAvailable ? getLocatorSummary(evidence.locator) : t("viewer.sourceUnavailable")}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {trace ? (
        <footer className="py-4">
          <a href={getResearchArtifactContentUrl(workspaceId, run.id, trace.id)} download className="inline-flex h-8 items-center gap-2 text-xs font-semibold text-zinc-600 hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-white">
            <Download className="h-3.5 w-3.5" />
            {t("research.downloadTrace")}
          </a>
        </footer>
      ) : null}
    </div>
  );
}
