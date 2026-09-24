import type { FinalizeUploadResponseDto, JobStatusDto } from "./types";

export type ReindexState = { workspaceId: string; assetId: string; submitting: boolean; job?: JobStatusDto; error?: string };
export function reindexActive(item?: ReindexState): boolean {
  return Boolean(item?.submitting || (item?.job && ["queued", "running"].includes(item.job.status)));
}

export function completedReindexVersion(rows: ReindexState[], workspaceId: string): string {
  return rows.filter((row) => row.workspaceId === workspaceId && row.job && !["queued", "running"].includes(row.job.status))
    .map((row) => `${row.job!.id}:${row.job!.status}`).sort().join(",");
}

export class ReindexTracker {
  private rows: ReindexState[] = [];
  private listeners = new Set<() => void>();
  private controllers = new Map<string, AbortController>();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private enabled = false;
  constructor(private readonly pollDelay = 1500) {}
  getSnapshot = () => this.rows;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  start() { this.enabled = true; }
  stop() {
    this.enabled = false;
    this.controllers.forEach((controller) => controller.abort()); this.controllers.clear();
    this.timers.forEach(clearTimeout); this.timers.clear(); this.rows = []; this.emit();
  }
  private key(workspaceId: string, assetId: string) { return `${workspaceId}/${assetId}`; }
  private emit() { this.listeners.forEach((listener) => listener()); }
  private put(row: ReindexState) {
    this.rows = [...this.rows.filter((old) => old.workspaceId !== row.workspaceId || old.assetId !== row.assetId), row]; this.emit();
  }
  private async request<T>(url: string, signal: AbortSignal, method = "GET"): Promise<T> {
    const response = await fetch(url, { method, cache: "no-store", signal });
    const payload = await response.json().catch(() => undefined); signal.throwIfAborted();
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : "Reindex request failed.");
    }
    return payload as T;
  }
  submit = async (workspaceId: string, assetId: string) => {
    const key = this.key(workspaceId, assetId);
    if (!this.enabled || reindexActive(this.rows.find((row) => this.key(row.workspaceId, row.assetId) === key))) return;
    const controller = new AbortController(); this.controllers.set(key, controller);
    this.put({ workspaceId, assetId, submitting: true });
    try {
      const payload = await this.request<FinalizeUploadResponseDto>(`/api/workspaces/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/reindex`, controller.signal, "POST");
      if (!payload?.job || payload.job.workspaceId !== workspaceId || payload.job.assetId !== assetId) throw new Error("Invalid reindex job response.");
      const row = { workspaceId, assetId, submitting: false, job: payload.job };
      this.put(row); this.schedule(row, controller);
    } catch (error) {
      if (!controller.signal.aborted) this.put({ workspaceId, assetId, submitting: false, error: error instanceof Error ? error.message : "Reindex request failed." });
    }
  };
  resume = (workspaceId: string, assetId: string) => {
    const key = this.key(workspaceId, assetId);
    const row = this.rows.find((row) => this.key(row.workspaceId, row.assetId) === key);
    if (!this.enabled || !row?.job || !row.error) return;
    const controller = new AbortController(); this.controllers.get(key)?.abort(); this.controllers.set(key, controller);
    this.put({ ...row, error: undefined }); void this.poll(row, controller);
  };
  private schedule(row: ReindexState, controller: AbortController) {
    if (!controller.signal.aborted && reindexActive(row)) {
      const key = this.key(row.workspaceId, row.assetId);
      this.timers.set(key, setTimeout(() => { this.timers.delete(key); void this.poll(row, controller); }, this.pollDelay));
    }
  }
  private async poll(row: ReindexState, controller: AbortController) {
    try {
      const payload = await this.request<{ job: JobStatusDto }>(`/api/workspaces/${encodeURIComponent(row.workspaceId)}/jobs/${encodeURIComponent(row.job!.id)}`, controller.signal);
      if (!payload?.job || payload.job.id !== row.job!.id || payload.job.workspaceId !== row.workspaceId || payload.job.assetId !== row.assetId) throw new Error("Invalid reindex job response.");
      const next = { ...row, job: payload.job, error: undefined };
      this.put(next); this.schedule(next, controller);
    } catch (error) {
      if (!controller.signal.aborted) this.put({ ...row, error: error instanceof Error ? error.message : "Failed to read reindex progress." });
    }
  }
}
