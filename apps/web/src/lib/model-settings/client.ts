import type { ModelSettingsPatch, WorkspaceModelSettings } from "./types";

export class ModelSettingsError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null) { super(message); }
}

export async function modelSettingsRequest(workspaceId: string, signal: AbortSignal, patch?: ModelSettingsPatch): Promise<WorkspaceModelSettings> {
  const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/model-settings`, {
    method: patch ? "PATCH" : "GET", cache: "no-store", signal,
    ...(patch ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) } : {}),
  });
  const payload = await response.json().catch(() => null);
  signal.throwIfAborted();
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : "Model settings request failed.";
    throw new ModelSettingsError(message, response.status, typeof detail?.code === "string" ? detail.code : null);
  }
  return payload as WorkspaceModelSettings;
}
