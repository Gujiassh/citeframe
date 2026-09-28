import { errorDetail, knownCode, MemoryError } from "./errors";
import { object } from "./validation";
export type PendingMutation = Readonly<{ requestId: string; key: string; path: string; method: "POST" | "PATCH" | "DELETE"; body: string }>;
export function prepareMutation(path: string, method: PendingMutation["method"], fields: Record<string, unknown>): PendingMutation {
  const requestId = crypto.randomUUID();
  return Object.freeze({ requestId, key: crypto.randomUUID(), path, method, body: JSON.stringify({ ...fields, requestId }) });
}
export async function memoryRequest<T>(workspaceId: string, path: string, signal: AbortSignal, mutation?: PendingMutation, sourceBody?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/${path}`, {
      method: mutation?.method ?? (sourceBody ? "POST" : "GET"), cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(25000)]),
      headers: mutation ? { "Content-Type": "application/json", "Idempotency-Key": mutation.key } : sourceBody ? { "Content-Type": "application/json" } : {},
      body: mutation?.body ?? (sourceBody ? JSON.stringify(sourceBody) : undefined),
    });
  } catch { throw new MemoryError(errorDetail(mutation ? "outcome_unknown" : "temporarily_unavailable", mutation?.requestId ?? null)); }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok || !object(payload)) {
    const detail = object(payload) && object(payload.detail) ? payload.detail : null;
    if (detail && knownCode(detail.code)) throw new MemoryError(errorDetail(detail.code, mutation?.requestId ?? null, typeof detail.currentVersion === "number" ? detail.currentVersion : undefined));
    throw new MemoryError(errorDetail(mutation ? "outcome_unknown" : "temporarily_unavailable", mutation?.requestId ?? null));
  }
  return payload as T;
}
export function uncertain(error: MemoryError) { return ["outcome_unknown", "temporarily_unavailable", "operation_in_progress"].includes(error.detail.code); }
