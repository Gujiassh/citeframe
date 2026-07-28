"use client";

import { AlertTriangle, BarChart3, CheckCircle2, CircleSlash2, LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getEvaluationCase,
  getEvaluationRun,
  listEvaluationCases,
  listEvaluationRuns,
  listEvaluationSuites,
} from "@/lib/evaluation/client";
import { GATE_KEYS, latestResearchEvaluation, pairedQuickEvaluation, ratioPercent, sortEvaluationRunsLatest } from "@/lib/evaluation/presentation";
import type { EvaluationCaseResponse, EvaluationCaseSummary, EvaluationGate, EvaluationRunSummary, EvaluationSuite, RatioMetric } from "@/lib/evaluation/types";
import { useTranslation, type TranslationKey } from "@/lib/i18n-context";

type Props = { workspaceId: string };

const METRICS = [
  ["claimSupportRate", "evaluation.claimSupport"],
  ["evidenceRecall", "evaluation.evidenceRecall"],
  ["evidencePrecision", "evaluation.evidencePrecision"],
  ["locatorAccuracy", "evaluation.locatorAccuracy"],
  ["conflictDetectionRate", "evaluation.conflictDetection"],
  ["refusalCorrectness", "evaluation.refusalCorrectness"],
] as const;

function Gate({ label, value }: { label: string; value: EvaluationGate }) {
  const { t } = useTranslation();
  const Icon = value === "pass" ? CheckCircle2 : value === "fail" ? AlertTriangle : CircleSlash2;
  const color = value === "pass"
    ? "text-emerald-700 dark:text-emerald-400"
    : value === "fail"
      ? "text-red-700 dark:text-red-400"
      : "text-zinc-500";
  return (
    <div className="min-w-0 border-l border-border pl-3">
      <dt className="text-[10px] font-semibold text-zinc-500">{label}</dt>
      <dd className={`mt-1 flex items-center gap-1.5 text-xs font-semibold ${color}`}>
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span>{t(GATE_KEYS[value] as TranslationKey)}</span>
      </dd>
    </div>
  );
}

function Metric({ label, research, quick }: { label: string; research: RatioMetric; quick: RatioMetric | null }) {
  const { t } = useTranslation();
  const researchValue = ratioPercent(research);
  const quickValue = quick ? ratioPercent(quick) : null;
  return (
    <div className="grid min-h-12 grid-cols-[minmax(7rem,1fr)_minmax(8rem,2fr)] items-center gap-4 border-b border-border py-2.5 text-xs last:border-b-0">
      <div>
        <p className="font-medium text-zinc-800 dark:text-zinc-200">{label}</p>
        <p className="mt-0.5 text-[10px] text-zinc-500">{research.sampleCount} {t("evaluation.samples")}</p>
      </div>
      <div className="space-y-1.5">
        <div className="grid grid-cols-[4.5rem_1fr_3rem] items-center gap-2">
          <span className="text-[10px] text-zinc-500">{t("evaluation.research")}</span>
          <span className="h-1.5 overflow-hidden bg-zinc-200 dark:bg-zinc-800">
            <span className="block h-full bg-emerald-500" style={{ width: `${researchValue ?? 0}%` }} />
          </span>
          <span className="text-right font-mono text-[10px]">{researchValue === null ? t("evaluation.notEvaluableShort") : `${researchValue}%`}</span>
        </div>
        <div className="grid grid-cols-[4.5rem_1fr_3rem] items-center gap-2">
          <span className="text-[10px] text-zinc-500">{t("evaluation.quick")}</span>
          <span className="h-1.5 overflow-hidden bg-zinc-200 dark:bg-zinc-800">
            <span className="block h-full bg-zinc-500" style={{ width: `${quickValue ?? 0}%` }} />
          </span>
          <span className="text-right font-mono text-[10px]">{quickValue === null ? t("evaluation.notEvaluableShort") : `${quickValue}%`}</span>
        </div>
      </div>
    </div>
  );
}

function formatCost(value: { currency: string; amountMicros: number }): string {
  return `${value.currency} ${(value.amountMicros / 1_000_000).toFixed(2)}`;
}

export function EvaluationDashboard({ workspaceId }: Props) {
  const { t } = useTranslation();
  const [suites, setSuites] = useState<EvaluationSuite[]>([]);
  const [suiteId, setSuiteId] = useState("");
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [evaluationId, setEvaluationId] = useState("");
  const [cases, setCases] = useState<EvaluationCaseSummary[]>([]);
  const [selectedCase, setSelectedCase] = useState<EvaluationCaseResponse["case"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listEvaluationSuites(workspaceId)
      .then((payload) => {
        if (cancelled) return;
        const ordered = [...payload.items].sort((left, right) => right.version - left.version || right.createdAt.localeCompare(left.createdAt) || right.id.localeCompare(left.id));
        setSuites(ordered);
        setLoading(true);
        setSuiteId(ordered[0]?.id ?? "");
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : t("evaluation.loadFailed")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [t, workspaceId]);

  useEffect(() => {
    let cancelled = false;
    if (!suiteId) return;
    void listEvaluationRuns(workspaceId, suiteId)
      .then((payload) => {
        if (cancelled) return;
        const ordered = sortEvaluationRunsLatest(payload.items);
        setRuns(ordered);
        setLoading(true);
        setEvaluationId(latestResearchEvaluation(ordered)?.id ?? "");
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : t("evaluation.loadFailed")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [suiteId, t, workspaceId]);

  useEffect(() => {
    let cancelled = false;
    if (!evaluationId) return;
    void Promise.all([getEvaluationRun(workspaceId, evaluationId), listEvaluationCases(workspaceId, evaluationId)])
      .then(([runPayload, casePayload]) => {
        if (cancelled) return;
        setRuns((current) => sortEvaluationRunsLatest(current.map((item) => item.id === runPayload.evaluation.id ? runPayload.evaluation : item)));
        setCases(casePayload.items);
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : t("evaluation.loadFailed")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [evaluationId, t, workspaceId]);

  const research = useMemo(() => runs.find((item) => item.id === evaluationId && item.mode === "research") ?? null, [evaluationId, runs]);
  const quick = useMemo(() => pairedQuickEvaluation(research, runs), [research, runs]);

  const selectSuite = (nextSuiteId: string) => {
    setSuiteId(nextSuiteId);
    setRuns([]);
    setEvaluationId("");
    setCases([]);
    setSelectedCase(null);
    setError(null);
    setLoading(true);
  };

  const selectEvaluation = (nextEvaluationId: string) => {
    setEvaluationId(nextEvaluationId);
    setCases([]);
    setSelectedCase(null);
    setError(null);
    setLoading(true);
  };

  const openCase = async (item: EvaluationCaseSummary) => {
    try {
      setLoading(true);
      const payload = await getEvaluationCase(workspaceId, evaluationId, item.caseKey);
      setSelectedCase(payload.case);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("evaluation.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  if (loading && !suites.length) {
    return <div className="flex min-h-64 items-center justify-center"><LoaderCircle className="h-5 w-5 animate-spin motion-reduce:animate-none" /></div>;
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-8 sm:py-7">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-zinc-950 dark:text-white"><BarChart3 className="h-4 w-4" />{t("evaluation.title")}</h3>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="text-[10px] font-semibold text-zinc-500">
            {t("evaluation.suite")}
            <select value={suiteId} onChange={(event) => selectSuite(event.target.value)} className="mt-1 block h-8 w-full min-w-44 border border-border bg-background px-2 text-xs">
              {suites.map((suite) => <option key={suite.id} value={suite.id}>{suite.title} v{suite.version}</option>)}
            </select>
          </label>
          <label className="text-[10px] font-semibold text-zinc-500">
            {t("evaluation.run")}
            <select value={evaluationId} onChange={(event) => selectEvaluation(event.target.value)} className="mt-1 block h-8 w-full min-w-44 border border-border bg-background px-2 text-xs">
              {runs.filter((item) => item.mode === "research").map((item) => <option key={item.id} value={item.id}>{item.createdAt.slice(0, 10)} · {item.workflowVersionId ?? t("evaluation.noWorkflow")}</option>)}
            </select>
          </label>
        </div>
      </div>

      {error ? <p role="alert" className="border-b border-border py-3 text-xs text-red-600 dark:text-red-400">{error}</p> : null}
      {!research ? <p className="py-12 text-center text-xs text-zinc-500">{t("evaluation.empty")}</p> : (
        <>
          <section className="border-b border-border py-5">
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Gate label={t("evaluation.engineeringGate")} value={research.engineeringGate} />
              <Gate label={t("evaluation.modelGate")} value={research.modelQualityGate} />
              <Gate label={t("evaluation.userGate")} value={research.userValueGate} />
            </dl>
          </section>

          <section className="grid grid-cols-1 gap-7 border-b border-border py-5 lg:grid-cols-[minmax(0,3fr)_minmax(15rem,2fr)]">
            <div>
              <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("evaluation.quality")}</h4>
              <div className="mt-2 border-y border-border">
                {METRICS.map(([field, key]) => <Metric key={field} label={t(key as TranslationKey)} research={research[field]} quick={quick?.[field] ?? null} />)}
              </div>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("evaluation.execution")}</h4>
              <dl className="mt-2 divide-y divide-border border-y border-border text-xs">
                {[
                  [t("evaluation.wallTime"), research.wallTimeMs === null ? t("evaluation.notEvaluableShort") : `${research.wallTimeMs} ms`],
                  [t("evaluation.providerCalls"), String(research.providerCalls)],
                  [t("evaluation.tokens"), `${research.inputTokens + research.outputTokens}`],
                  [t("evaluation.cost"), formatCost(research.cost)],
                  [t("evaluation.parallelSpeedup"), research.parallelSpeedup === null ? t("evaluation.notEvaluableShort") : `${research.parallelSpeedup.toFixed(2)}x`],
                  [t("evaluation.retryRate"), ratioPercent(research.retryRate) === null ? t("evaluation.notEvaluableShort") : `${ratioPercent(research.retryRate)}%`],
                  [t("evaluation.recoveryRate"), ratioPercent(research.recoveryRate) === null ? t("evaluation.notEvaluableShort") : `${ratioPercent(research.recoveryRate)}%`],
                ].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-4 py-2.5"><dt className="text-zinc-500">{label}</dt><dd className="font-mono text-[10px]">{value}</dd></div>)}
              </dl>
              <dl className="mt-4 space-y-2 text-[10px]">
                <div><dt className="text-zinc-500">{t("evaluation.providerModel")}</dt><dd className="mt-0.5 break-all font-mono">{research.provider} / {research.model}</dd></div>
                <div><dt className="text-zinc-500">{t("evaluation.workflow")}</dt><dd className="mt-0.5 break-all font-mono">{research.workflowVersionId ?? t("evaluation.noWorkflow")}</dd></div>
                <div><dt className="text-zinc-500">{t("evaluation.reportHash")}</dt><dd className="mt-0.5 break-all font-mono">{research.sourceReportSha256.slice(0, 12)}</dd></div>
              </dl>
            </div>
          </section>

          <section className="py-5">
            <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{t("evaluation.cases")}</h4>
            <div className="mt-2 overflow-x-auto border-y border-border">
              <table className="w-full min-w-[38rem] text-left text-xs">
                <thead className="text-[10px] text-zinc-500"><tr><th className="py-2 pr-4 font-semibold">{t("evaluation.case")}</th><th className="px-2 py-2 font-semibold">{t("evaluation.disposition")}</th><th className="px-2 py-2 text-right font-semibold">{t("evaluation.claimSupport")}</th><th className="px-2 py-2 text-right font-semibold">{t("evaluation.unsupported")}</th><th className="pl-2 py-2 text-right font-semibold">{t("evaluation.wallTime")}</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {cases.map((item) => <tr key={item.id}><td className="py-2.5 pr-4"><button type="button" onClick={() => void openCase(item)} className="font-medium hover:text-emerald-700 dark:hover:text-emerald-400">{item.caseKey}</button></td><td className="px-2 py-2.5 text-zinc-500">{item.observedDisposition}</td><td className="px-2 py-2.5 text-right font-mono text-[10px]">{ratioPercent(item.claimSupportRate) ?? t("evaluation.notEvaluableShort")}</td><td className="px-2 py-2.5 text-right font-mono text-[10px]">{item.unsupportedClaimCount}</td><td className="pl-2 py-2.5 text-right font-mono text-[10px]">{item.wallTimeMs ?? t("evaluation.notEvaluableShort")}</td></tr>)}
                </tbody>
              </table>
            </div>
          </section>

          {selectedCase ? (
            <section className="border-t border-border py-5">
              <h4 className="text-xs font-semibold text-zinc-950 dark:text-white">{selectedCase.caseKey}</h4>
              <div className="mt-2 divide-y divide-border border-y border-border">
                {selectedCase.claims.map((claim) => <div key={claim.id} className="grid grid-cols-1 gap-1 py-2.5 text-xs sm:grid-cols-[1fr_auto_auto]"><span className="font-medium">{claim.claimKey}</span><span className="text-[10px] text-zinc-500">{claim.supportResult}</span><span className="text-[10px] text-zinc-500">{claim.locatorResult}</span></div>)}
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
