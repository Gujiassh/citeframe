import type { ResearchRunStatus, ResearchRunSummary, ResearchStepStatus } from "./types";

export type WorkspaceQuestionMode = "quick" | "research";

export function canSubmitWorkspaceQuestion(input: {
  mode: WorkspaceQuestionMode;
  question: string;
  assetsReady: boolean;
  quickThreadReady: boolean;
  busy: boolean;
}): boolean {
  if (!input.question.trim() || !input.assetsReady || input.busy) return false;
  return input.mode === "research" || input.quickThreadReady;
}

export function sortResearchRunsLatest(items: ResearchRunSummary[]): ResearchRunSummary[] {
  return [...items].sort((left, right) => {
    const byCreatedAt = right.createdAt.localeCompare(left.createdAt);
    return byCreatedAt || right.id.localeCompare(left.id);
  });
}

export function latestResearchRun(items: ResearchRunSummary[]): ResearchRunSummary | null {
  return sortResearchRunsLatest(items)[0] ?? null;
}

export function canManageResearchRun(run: ResearchRunSummary | null, currentUserId: string | null): boolean {
  return Boolean(run && currentUserId && run.createdByUserId === currentUserId);
}

export const RUN_STATUS_KEYS: Record<ResearchRunStatus, string> = {
  planning: "research.statusPlanning",
  awaiting_plan_approval: "research.statusAwaitingPlanApproval",
  queued: "research.statusQueued",
  running: "research.statusRunning",
  awaiting_human_decision: "research.statusAwaitingDecision",
  awaiting_retry: "research.statusAwaitingRetry",
  cancel_requested: "research.statusCancelRequested",
  completed: "research.statusCompleted",
  failed: "research.statusFailed",
  cancelled: "research.statusCancelled",
};

export const STEP_STATUS_KEYS: Record<ResearchStepStatus, string> = {
  pending: "research.stepPending",
  queued: "research.stepQueued",
  running: "research.stepRunning",
  waiting: "research.stepWaiting",
  succeeded: "research.stepSucceeded",
  failed: "research.stepFailed",
  cancelled: "research.stepCancelled",
  skipped: "research.stepSkipped",
};

export const STEP_KIND_KEYS: Record<string, string> = {
  planner: "research.stagePlanner",
  plan_approval_gate: "research.stagePlanApproval",
  researcher: "research.stageResearch",
  join: "research.stageJoin",
  verifier: "research.stageVerifier",
  critic: "research.stageCritic",
  conflict_decision_gate: "research.stageConflictDecision",
  synthesizer: "research.stageSynthesis",
  artifact_publisher: "research.stagePublish",
};
