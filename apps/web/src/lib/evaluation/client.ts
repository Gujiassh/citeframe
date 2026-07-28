import type {
  EvaluationCaseListResponse,
  EvaluationCaseResponse,
  EvaluationRunListResponse,
  EvaluationRunResponse,
  EvaluationSuiteListResponse,
} from "./types";

class EvaluationApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "EvaluationApiError";
  }
}

async function json<T>(response: Response): Promise<T> {
  let payload: unknown;
  try { payload = await response.json(); } catch { payload = undefined; }
  if (!response.ok) {
    const error = payload && typeof payload === "object"
      ? payload as { error?: { message?: string }; detail?: string }
      : undefined;
    throw new EvaluationApiError(error?.error?.message ?? error?.detail ?? "Evaluation request failed.", response.status);
  }
  return payload as T;
}

function root(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}`;
}

export async function listEvaluationSuites(workspaceId: string): Promise<EvaluationSuiteListResponse> {
  return json(await fetch(`${root(workspaceId)}/evaluation-suites`, { cache: "no-store" }));
}

export async function listEvaluationRuns(workspaceId: string, suiteId: string): Promise<EvaluationRunListResponse> {
  const query = new URLSearchParams({ suiteId });
  return json(await fetch(`${root(workspaceId)}/evaluations?${query}`, { cache: "no-store" }));
}

export async function getEvaluationRun(workspaceId: string, evaluationId: string): Promise<EvaluationRunResponse> {
  return json(await fetch(`${root(workspaceId)}/evaluations/${encodeURIComponent(evaluationId)}`, { cache: "no-store" }));
}

export async function listEvaluationCases(workspaceId: string, evaluationId: string): Promise<EvaluationCaseListResponse> {
  return json(await fetch(`${root(workspaceId)}/evaluations/${encodeURIComponent(evaluationId)}/cases`, { cache: "no-store" }));
}

export async function getEvaluationCase(workspaceId: string, evaluationId: string, caseKey: string): Promise<EvaluationCaseResponse> {
  return json(await fetch(`${root(workspaceId)}/evaluations/${encodeURIComponent(evaluationId)}/cases/${encodeURIComponent(caseKey)}`, { cache: "no-store" }));
}
