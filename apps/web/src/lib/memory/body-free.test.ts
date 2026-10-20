import test from "node:test";
import assert from "node:assert/strict";
import { bodyFree } from "./body-free";
import type { AvailableMemory, Memory } from "./types";

test("R5 body-free projection keeps lifecycle metadata without semantic fields", () => {
  const current = { id: "owned-id", version: 9, intent: "inactive", validity: "valid", displayStatus: "inactive",
    contentAvailable: true, content: "obsolete private body", conditions: { subject: "obsolete subject" },
    sourceRefs: [{ contentSha256: "obsolete hash" }] } as AvailableMemory;
  assert.deepEqual(bodyFree(current), { id: "owned-id", version: 9, intent: "inactive", validity: "valid",
    displayStatus: "inactive", contentAvailable: false, reason: "source_unavailable" });
  assert.equal(current.contentAvailable, true);
});

test("R5 unavailable revisions preserve their own intent, version and erasure reason", () => {
  for (const intent of ["active", "inactive", "superseded", "deleted"] as const) {
    const revision: Memory = { id: "owned-id", version: 2, intent, validity: "invalidated",
      displayStatus: intent === "active" ? "invalidated" : intent, contentAvailable: false,
      reason: intent === "deleted" ? "erased" : "source_unavailable" };
    assert.deepEqual(bodyFree(revision), revision);
  }
});
