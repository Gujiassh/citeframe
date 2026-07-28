export type EvaluationGate = "not_evaluable" | "pass" | "fail";
export type EvaluationMode = "quick" | "research";

export type RatioMetric = {
  value: number | null;
  sampleCount: number;
  notEvaluableReason: string | null;
};

export type EvaluationSuite = {
  id: string;
  suiteKey: string;
  version: number;
  title: string;
  fixtureManifestSha256: string;
  scorerVersion: string;
  caseCount: number;
  createdAt: string;
};

export type EvaluationRunSummary = {
  id: string;
  workspaceId: string;
  suiteId: string;
  mode: EvaluationMode;
  status: "not_evaluable" | "completed" | "failed";
  researchRunId: string | null;
  baselineEvaluationRunId: string | null;
  fixtureManifestSha256: string;
  assetScopeSha256: string;
  provider: string;
  model: string;
  providerProfileSha256: string;
  scorerVersion: string;
  workflowVersionId: string | null;
  promptBindingSha256: string | null;
  wallTimeMs: number | null;
  providerCalls: number;
  inputTokens: number;
  outputTokens: number;
  cost: { currency: string; amountMicros: number };
  parallelSpeedup: number | null;
  retryRate: RatioMetric;
  recoveryRate: RatioMetric;
  claimSupportRate: RatioMetric;
  evidenceRecall: RatioMetric;
  evidencePrecision: RatioMetric;
  locatorAccuracy: RatioMetric;
  conflictDetectionRate: RatioMetric;
  refusalCorrectness: RatioMetric;
  engineeringGate: EvaluationGate;
  modelQualityGate: EvaluationGate;
  userValueGate: EvaluationGate;
  sourceReportSha256: string;
  createdAt: string;
  completedAt: string | null;
  failure: { code: string; message: string } | null;
};

export type EvaluationCaseSummary = {
  id: string;
  caseKey: string;
  caseType: string;
  expectedDisposition: "answer" | "refuse" | "not_evaluable";
  observedDisposition: "answer" | "refuse" | "not_evaluable";
  claimSupportRate: RatioMetric;
  evidenceRecall: RatioMetric;
  evidencePrecision: RatioMetric;
  locatorAccuracy: RatioMetric;
  conflictDetectionRate: RatioMetric;
  refusalCorrectness: RatioMetric;
  wallTimeMs: number | null;
  providerCalls: number;
  cost: { currency: string; amountMicros: number };
  unsupportedClaimCount: number;
  humanInterventionCount: number;
  humanWaitMs: number;
  failureCode: string | null;
};

export type EvaluationClaimResult = {
  id: string;
  claimKey: string;
  supportResult: "supported" | "unsupported" | "not_evaluable";
  locatorResult: "accurate" | "inaccurate" | "not_evaluable";
  conflictResult: "none" | "detected" | "missed" | "not_evaluable";
  expectedEvidenceCount: number;
  observedEvidenceCount: number;
  failureCode: string | null;
};

export type EvaluationSuiteListResponse = { items: EvaluationSuite[] };
export type EvaluationRunListResponse = { items: EvaluationRunSummary[]; nextCursor: string | null };
export type EvaluationRunResponse = { evaluation: EvaluationRunSummary };
export type EvaluationCaseListResponse = { items: EvaluationCaseSummary[] };
export type EvaluationCaseResponse = { case: EvaluationCaseSummary & { claims: EvaluationClaimResult[] } };
