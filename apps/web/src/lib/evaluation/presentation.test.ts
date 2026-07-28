import assert from "node:assert/strict";
import test from "node:test";

import { latestResearchEvaluation, pairedQuickEvaluation, ratioPercent } from "./presentation";
import type { EvaluationRunSummary } from "./types";

function run(id: string, mode: "quick" | "research", createdAt: string): EvaluationRunSummary {
  const ratio = { value: 0.5, sampleCount: 2, notEvaluableReason: null };
  return {
    id, workspaceId: "ws", suiteId: "suite", mode, status: "completed", researchRunId: mode === "research" ? "run" : null,
    baselineEvaluationRunId: mode === "research" ? "quick" : null, fixtureManifestSha256: "a".repeat(64),
    assetScopeSha256: "b".repeat(64), provider: "openai", model: "gpt", providerProfileSha256: "c".repeat(64),
    scorerVersion: "v1", workflowVersionId: mode === "research" ? "workflow" : null, promptBindingSha256: null, wallTimeMs: 10,
    providerCalls: 1, inputTokens: 2, outputTokens: 3, cost: { currency: "USD", amountMicros: 4 }, parallelSpeedup: null,
    retryRate: ratio, recoveryRate: ratio, claimSupportRate: ratio, evidenceRecall: ratio, evidencePrecision: ratio,
    locatorAccuracy: ratio, conflictDetectionRate: ratio, refusalCorrectness: ratio, engineeringGate: "pass",
    modelQualityGate: "not_evaluable", userValueGate: "not_evaluable", sourceReportSha256: "d".repeat(64),
    createdAt, completedAt: createdAt, failure: null,
  };
}

test("Evaluation selection uses explicit timestamps and pairing keys", () => {
  const quick = run("quick", "quick", "2026-07-27T00:00:00Z");
  const older = run("research-old", "research", "2026-07-27T01:00:00Z");
  const latest = run("research-new", "research", "2026-07-27T02:00:00Z");
  assert.equal(latestResearchEvaluation([older, quick, latest])?.id, latest.id);
  assert.equal(pairedQuickEvaluation(latest, [latest, quick])?.id, quick.id);
  assert.equal(pairedQuickEvaluation({ ...latest, model: "other" }, [quick]), null);
});

test("Evaluation ratios preserve not-evaluable instead of coercing it to zero", () => {
  assert.equal(ratioPercent({ value: null, sampleCount: 0, notEvaluableReason: "no_sample" }), null);
  assert.equal(ratioPercent({ value: 0.876, sampleCount: 5, notEvaluableReason: null }), 87.6);
});
