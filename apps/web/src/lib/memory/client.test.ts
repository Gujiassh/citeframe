import test from "node:test";
import assert from "node:assert/strict";
import { memoryRequest, prepareMutation, uncertain } from "./client";
import { MemoryError } from "./errors";
test("unknown outcome retries retain exact body/request ID/key", async () => {
  const operation = prepareMutation("memories/fixture", "DELETE", { expectedVersion: 4 });
  const calls: RequestInit[] = []; const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, init) => { calls.push(init!); throw new Error("lost acknowledgement"); };
  try {
    for (let i = 0; i < 2; i++) await assert.rejects(memoryRequest("workspace", operation.path, new AbortController().signal, operation), e => e instanceof MemoryError && uncertain(e) && e.detail.requestId === operation.requestId);
    assert.equal(calls[0].body, calls[1].body); assert.deepEqual(calls[0].headers, calls[1].headers);
    assert.equal(JSON.parse(String(calls[0].body)).requestId, operation.requestId); assert.ok(Object.isFrozen(operation));
  } finally { globalThis.fetch = originalFetch; }
});
