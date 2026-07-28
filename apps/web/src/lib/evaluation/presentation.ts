import type { EvaluationGate, EvaluationRunSummary, RatioMetric } from "./types";

export function sortEvaluationRunsLatest(items: EvaluationRunSummary[]): EvaluationRunSummary[] {
  return [...items].sort((left, right) => right.createdAt.localeCompare(left.createdAt) || right.id.localeCompare(left.id));
}

export function latestResearchEvaluation(items: EvaluationRunSummary[]): EvaluationRunSummary | null {
  return sortEvaluationRunsLatest(items.filter((item) => item.mode === "research"))[0] ?? null;
}

export function pairedQuickEvaluation(
  research: EvaluationRunSummary | null,
  items: EvaluationRunSummary[],
): EvaluationRunSummary | null {
  if (!research?.baselineEvaluationRunId) return null;
  const baseline = items.find((item) => item.id === research.baselineEvaluationRunId && item.mode === "quick") ?? null;
  if (!baseline) return null;
  const keys = ["suiteId", "fixtureManifestSha256", "assetScopeSha256", "provider", "model", "providerProfileSha256", "scorerVersion"] as const;
  return keys.every((key) => baseline[key] === research[key]) ? baseline : null;
}

export function ratioPercent(metric: RatioMetric): number | null {
  return metric.value === null ? null : Math.round(metric.value * 1000) / 10;
}

export const GATE_KEYS: Record<EvaluationGate, string> = {
  pass: "evaluation.gatePass",
  fail: "evaluation.gateFail",
  not_evaluable: "evaluation.gateNotEvaluable",
};
