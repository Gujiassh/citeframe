export type ReportEdit = {
  originalArtifactId: string;
  originalSha256: string;
  version: number;
  markdown: string | null;
  actorUserId: string | null;
  updatedAt: string | null;
  verificationStatus: "unverified";
};

export class ReportEditError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "ReportEditError";
  }
}

function path(workspaceId: string, runId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/research-runs/${encodeURIComponent(runId)}/report-edit`;
}

async function parse(response: Response): Promise<ReportEdit> {
  const payload = await response.json() as ReportEdit & { error?: { code?: string; message?: string } };
  if (!response.ok) throw new ReportEditError(payload.error?.message ?? "Report edit request failed.", response.status, payload.error?.code);
  return payload;
}

export async function getReportEdit(workspaceId: string, runId: string, signal?: AbortSignal): Promise<ReportEdit> {
  return parse(await fetch(path(workspaceId, runId), { cache: "no-store", signal }));
}

export async function putReportEdit(workspaceId: string, runId: string, expectedVersion: number, markdown: string, base: Pick<ReportEdit, "originalArtifactId" | "originalSha256">, signal?: AbortSignal): Promise<ReportEdit> {
  return parse(await fetch(path(workspaceId, runId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expectedVersion, markdown, originalArtifactId: base.originalArtifactId, originalSha256: base.originalSha256 }),
    signal,
  }));
}
