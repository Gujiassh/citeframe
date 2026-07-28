import type { EvidenceLocator, SourceVersions } from "../evidence/types";

export type MoneyMicrounits = {
  currency: string;
  amountMicros: number;
};

export type FrozenAssetScope = {
  frozenAt: string;
  assets: Array<{
    assetId: string;
    assetKind: string;
    assetTitle: string;
    processingGeneration: number;
    indexVersion: number;
  }>;
};

export type ResearchRunStatus =
  | "planning"
  | "awaiting_plan_approval"
  | "queued"
  | "running"
  | "awaiting_human_decision"
  | "awaiting_retry"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "cancelled";

export type ResearchStepStatus = "pending" | "queued" | "running" | "waiting" | "succeeded" | "failed" | "cancelled" | "skipped";

export type ResearchFailure = {
  code: string;
  message: string;
  retryable: boolean;
  failedAt: string;
};

export type ResearchStep = {
  id: string;
  runId: string;
  kind: string;
  key: string;
  branchKey: string | null;
  status: ResearchStepStatus;
  stateVersion: number;
  currentAttemptNumber: number;
  maxAttempts: number;
  dependsOnStepIds: string[];
  evidenceCount: number;
  providerCalls: number;
  toolCalls: number;
  startedAt: string | null;
  finishedAt: string | null;
  failure: ResearchFailure | null;
};

export type ResearchDecision = {
  id: string;
  runId: string;
  gateStepId: string;
  type: "plan_approval" | "conflict_resolution";
  status: "pending" | "submitted" | "expired" | "cancelled" | "superseded";
  stateVersion: number;
  inputArtifactId: string;
  inputArtifactSha256: string;
  inputSnapshotSha256: string;
  action: string | null;
  comment: string | null;
};

export type ResearchPlan = {
  version: number;
  status: "proposed" | "approved" | "superseded";
  summary: string;
  subproblems: Array<{ id: string; order: number; question: string; assetIds: string[]; expectedEvidence: string[] }>;
  knownGaps: string[];
  estimatedProviderCalls: number;
  estimatedInputTokens: number | null;
  estimatedOutputTokens: number | null;
  estimatedCost: MoneyMicrounits | null;
  approvedAt: string | null;
};

export type ResearchArtifactSummary = {
  id: string;
  runId: string;
  stepId: string;
  kind: "research_plan" | "evidence_bundle" | "conflict_report" | "final_report" | "trace_export";
  visibility: "user";
  logicalKey: string;
  schemaVersion: string;
  supersedesArtifactId: string | null;
  mediaType: "text/markdown" | "application/json";
  byteSize: number;
  sha256: string;
  evidenceCount: number;
  retentionClass: "workspace_lifetime" | "time_limited_diagnostics";
  expiresAt: string | null;
  createdAt: string;
};

export type ResearchArtifactEvidence = {
  evidenceLocatorId: string;
  assetId: string;
  assetKind: string;
  assetTitle: string;
  sourceAvailable: boolean;
  excerpt: string;
  locator: EvidenceLocator;
  sourceVersions: SourceVersions;
};

export type ResearchArtifactDetail = ResearchArtifactSummary & {
  workflowVersionId: string;
  promptVersions: Array<{ nodeKey: string; promptVersionId: string }>;
  directPromptVersionId: string | null;
  claims: Array<{
    id: string;
    text: string;
    verificationStatus: "supported" | "unsupported";
    conflictStatus: "none" | "conflicted" | "resolved_excluded" | "resolved_unresolved";
    sectionKind: "fact" | "conclusion" | "unresolved" | "conflict";
    evidence: Array<{ evidenceLocatorId: string; relationship: "supports" | "contradicts"; order: number }>;
  }>;
  evidence: ResearchArtifactEvidence[];
};

export type ResearchRunSummary = {
  id: string;
  workspaceId: string;
  createdByUserId: string;
  question: string;
  status: ResearchRunStatus;
  stateVersion: number;
  requestedAssetScope: { mode: "all_ready" } | { mode: "selected"; assetIds: string[] };
  frozenAssetCount: number;
  currentPlanRevisionNumber: number | null;
  currentEventSeq: number;
  estimatedCost: MoneyMicrounits | null;
  consumedCost: MoneyMicrounits;
  createdAt: string;
  updatedAt: string;
  finishedAt: string | null;
};

export type ResearchRunDetail = ResearchRunSummary & {
  frozenAssetScope: FrozenAssetScope | null;
  plan: ResearchPlan | null;
  steps: ResearchStep[];
  pendingDecisions: ResearchDecision[];
  submittedDecisions: ResearchDecision[];
  artifactCount: number;
  failure: ResearchFailure | null;
  startedAt: string | null;
  cancelRequestedAt: string | null;
  cancelledAt: string | null;
};

export type ResearchRunListResponse = { items: ResearchRunSummary[]; nextCursor: string | null };
export type ResearchRunResponse = { run: ResearchRunDetail };
export type ResearchArtifactListResponse = { items: ResearchArtifactSummary[] };
export type ResearchArtifactDetailResponse = { artifact: ResearchArtifactDetail };
