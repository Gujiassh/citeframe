export type UploadQueueStatus = "queued" | "uploading" | "submitted" | "failed";
export type UploadQueueItem = {
  id: string;
  workspaceId: string;
  filename: string;
  status: UploadQueueStatus;
  error?: string;
};
export type UploadTask = (signal: AbortSignal) => Promise<void>;

export class UploadQueue {
  private items: UploadQueueItem[] = [];
  private tasks = new Map<string, UploadTask>();
  private listeners = new Set<() => void>();
  private pending: string[] = [];
  private active: { id: string; controller: AbortController } | null = null;
  private enabled = false;
  private sequence = 0;

  getSnapshot = () => this.items;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  start() { this.enabled = true; this.drain(); }

  stop() {
    this.enabled = false;
    this.active?.controller.abort();
    this.pending = [];
    this.tasks.clear();
    this.items = [];
    this.emit();
  }

  enqueue(workspaceId: string, files: readonly File[], createTask: (file: File) => UploadTask) {
    if (!this.enabled || !workspaceId) return;
    const added = files.map((file) => {
      const id = String(++this.sequence);
      this.tasks.set(id, createTask(file));
      this.pending.push(id);
      return { id, workspaceId, filename: file.name, status: "queued" as const };
    });
    this.items = [...this.items, ...added];
    this.emit();
    this.drain();
  }

  retry = (id: string) => {
    if (!this.enabled || this.items.find((item) => item.id === id)?.status !== "failed") return;
    this.patch(id, { status: "queued", error: undefined });
    this.pending.push(id);
    this.drain();
  };

  removeWorkspace(workspaceId: string) {
    const ids = new Set(this.items.filter((item) => item.workspaceId === workspaceId).map((item) => item.id));
    if (this.active && ids.has(this.active.id)) this.active.controller.abort();
    for (const id of ids) this.tasks.delete(id);
    this.pending = this.pending.filter((id) => !ids.has(id));
    this.items = this.items.filter((item) => !ids.has(item.id));
    this.emit();
  }

  private emit() { this.listeners.forEach((listener) => listener()); }
  private patch(id: string, patch: Partial<UploadQueueItem>) {
    this.items = this.items.map((item) => item.id === id ? { ...item, ...patch } : item);
    this.emit();
  }

  private drain() {
    if (!this.enabled || this.active) return;
    const id = this.pending.shift();
    if (!id) return;
    const task = this.tasks.get(id)!;
    const controller = new AbortController();
    this.active = { id, controller };
    this.patch(id, { status: "uploading" });
    void (async () => {
      try {
        await task(controller.signal);
        if (!controller.signal.aborted) {
          this.patch(id, { status: "submitted" });
          this.tasks.delete(id);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          this.patch(id, { status: "failed", error: error instanceof Error ? error.message : "Upload failed." });
        }
      } finally {
        this.active = null;
        this.drain();
      }
    })();
  }
}

export function takeSelectedFiles(input: Pick<HTMLInputElement, "files" | "value">): File[] {
  const files = Array.from(input.files ?? []);
  input.value = "";
  return files;
}
