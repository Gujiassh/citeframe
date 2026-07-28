import type {
  ResearchArtifactDetailResponse,
  ResearchArtifactListResponse,
  ResearchRunListResponse,
  ResearchRunResponse,
  ResearchStep,
} from "./types";
import { isEvidenceLocator, isEvidenceSourceVersions } from "../chat/sse";

export class ResearchApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "ResearchApiError";
  }
}

function basePath(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/research-runs`;
}

async function json<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  if (!response.ok) {
    const error = payload && typeof payload === "object" ? (payload as { error?: { code?: string; message?: string }; detail?: string }) : undefined;
    throw new ResearchApiError(error?.error?.message ?? error?.detail ?? "Research request failed.", response.status, error?.error?.code);
  }
  return payload as T;
}

async function requireOk(response: Response, fallback: string): Promise<Response> {
  if (response.ok) return response;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const error = payload && typeof payload === "object"
    ? (payload as { error?: { code?: string; message?: string }; detail?: string })
    : undefined;
  throw new ResearchApiError(error?.error?.message ?? error?.detail ?? fallback, response.status, error?.error?.code);
}

function mutationHeaders(): HeadersInit {
  return { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() };
}

export async function listResearchRuns(workspaceId: string): Promise<ResearchRunListResponse> {
  return json(await fetch(basePath(workspaceId), { cache: "no-store" }));
}

export async function getResearchRun(workspaceId: string, runId: string): Promise<ResearchRunResponse> {
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(runId)}`, { cache: "no-store" }));
}

export async function createResearchRun(
  workspaceId: string,
  question: string,
  assetIds: string[],
): Promise<ResearchRunResponse> {
  return json(await fetch(basePath(workspaceId), {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({ question, assetScope: assetIds.length ? { mode: "selected", assetIds } : { mode: "all_ready" } }),
  }));
}

export async function approveResearchPlan(workspaceId: string, run: ResearchRunResponse["run"]): Promise<ResearchRunResponse> {
  const decision = run.pendingDecisions.find((item) => item.type === "plan_approval");
  if (!decision) throw new ResearchApiError("No pending plan approval.", 409, "research_state_conflict");
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/plan-decisions/${encodeURIComponent(decision.id)}`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({
      expectedStateVersion: run.stateVersion,
      expectedDecisionStateVersion: decision.stateVersion,
      inputArtifactSha256: decision.inputArtifactSha256,
      inputSnapshotSha256: decision.inputSnapshotSha256,
      action: "approve",
      comment: null,
      revision: null,
    }),
  }));
}

export async function reviseResearchPlan(
  workspaceId: string,
  run: ResearchRunResponse["run"],
  question: string,
  comment: string,
): Promise<ResearchRunResponse> {
  const decision = run.pendingDecisions.find((item) => item.type === "plan_approval");
  if (!decision) throw new ResearchApiError("No pending plan approval.", 409, "research_state_conflict");
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/plan-decisions/${encodeURIComponent(decision.id)}`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({
      expectedStateVersion: run.stateVersion,
      expectedDecisionStateVersion: decision.stateVersion,
      inputArtifactSha256: decision.inputArtifactSha256,
      inputSnapshotSha256: decision.inputSnapshotSha256,
      action: "request_revision",
      comment,
      revision: { question, assetScope: run.requestedAssetScope },
    }),
  }));
}

export async function cancelResearchPlan(workspaceId: string, run: ResearchRunResponse["run"]): Promise<ResearchRunResponse> {
  const decision = run.pendingDecisions.find((item) => item.type === "plan_approval");
  if (!decision) throw new ResearchApiError("No pending plan approval.", 409, "research_state_conflict");
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/plan-decisions/${encodeURIComponent(decision.id)}`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({
      expectedStateVersion: run.stateVersion,
      expectedDecisionStateVersion: decision.stateVersion,
      inputArtifactSha256: decision.inputArtifactSha256,
      inputSnapshotSha256: decision.inputSnapshotSha256,
      action: "cancel_run",
      comment: null,
      revision: null,
    }),
  }));
}

export async function resolveResearchConflict(
  workspaceId: string,
  run: ResearchRunResponse["run"],
  action: "exclude_conflicted_claims" | "keep_as_unresolved" | "cancel_run",
): Promise<ResearchRunResponse> {
  const decision = run.pendingDecisions.find((item) => item.type === "conflict_resolution");
  if (!decision) throw new ResearchApiError("No pending conflict decision.", 409, "research_state_conflict");
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/conflict-decisions/${encodeURIComponent(decision.id)}`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({
      expectedStateVersion: run.stateVersion,
      expectedDecisionStateVersion: decision.stateVersion,
      inputArtifactSha256: decision.inputArtifactSha256,
      inputSnapshotSha256: decision.inputSnapshotSha256,
      action,
      comment: null,
    }),
  }));
}

export async function cancelResearchRun(workspaceId: string, run: ResearchRunResponse["run"]): Promise<ResearchRunResponse> {
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/cancel`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({ expectedStateVersion: run.stateVersion, reasonCode: "user_requested" }),
  }));
}

export async function retryResearchStep(
  workspaceId: string,
  run: ResearchRunResponse["run"],
  step: ResearchStep,
): Promise<ResearchRunResponse> {
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(run.id)}/steps/${encodeURIComponent(step.id)}/retry`, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify({
      expectedStateVersion: run.stateVersion,
      expectedStepStateVersion: step.stateVersion,
      failedAttempt: step.currentAttemptNumber,
    }),
  }));
}

export async function getResearchArtifactContent(workspaceId: string, runId: string, artifactId: string): Promise<string> {
  const response = await requireOk(
    await fetch(getResearchArtifactContentUrl(workspaceId, runId, artifactId), { cache: "no-store" }),
    "Failed to load research artifact.",
  );
  return response.text();
}

export function getResearchArtifactContentUrl(workspaceId: string, runId: string, artifactId: string): string {
  return `${basePath(workspaceId)}/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}/content`;
}

export async function getResearchArtifact(
  workspaceId: string,
  runId: string,
  artifactId: string,
): Promise<ResearchArtifactDetailResponse> {
  const payload = await json<ResearchArtifactDetailResponse>(
    await fetch(`${basePath(workspaceId)}/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`, { cache: "no-store" }),
  );
  const evidence = payload?.artifact?.evidence;
  if (!Array.isArray(evidence) || evidence.some((item) => !item || !isEvidenceLocator(item.locator) || !isEvidenceSourceVersions(item.sourceVersions))) {
    throw new ResearchApiError("Research artifact Evidence is invalid.", 502, "research_artifact_invalid");
  }
  return payload;
}

export async function listResearchArtifacts(workspaceId: string, runId: string): Promise<ResearchArtifactListResponse> {
  return json(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(runId)}/artifacts`, { cache: "no-store" }));
}

export async function openResearchEventStream(workspaceId: string, runId: string, afterSeq: number, signal?: AbortSignal): Promise<Response> {
  return requireOk(await fetch(`${basePath(workspaceId)}/${encodeURIComponent(runId)}/events`, {
    cache: "no-store",
    headers: { Accept: "text/event-stream", "Last-Event-ID": String(afterSeq) },
    signal,
  }), "Failed to open research event stream.");
}
