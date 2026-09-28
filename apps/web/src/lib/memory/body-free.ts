import type { Memory } from "./types";

export function bodyFree(memory: Memory): Extract<Memory, { contentAvailable: false }> {
  return { id: memory.id, version: memory.version, intent: memory.intent, validity: memory.validity,
    displayStatus: memory.displayStatus, contentAvailable: false,
    reason: memory.contentAvailable ? "source_unavailable" : memory.reason };
}
