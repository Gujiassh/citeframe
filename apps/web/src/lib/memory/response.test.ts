import test from "node:test";
import assert from "node:assert/strict";
import { validResponse } from "./response";
const id = "00000000-0000-0000-0000-000000000001";
const owner = "00000000-0000-0000-0000-000000000002";
const workspace = "00000000-0000-0000-0000-000000000003";
const tombstone = { id, version: 3, intent: "deleted", validity: "valid", displayStatus: "deleted", contentAvailable: false, reason: "erased" };
const memory = { id, version: 1, intent: "active", validity: "valid", displayStatus: "active", contentAvailable: true, workspaceId: workspace, ownerUserId: owner, visibility: "private", scope: { kind: "workspace", threadId: null, runId: null }, revisionId: id, kind: "fact", confirmation: "user_confirmed", conditions: { subject: "Synthetic", applicability: "Tests", effectiveFrom: null }, pinned: false, validUntil: null, supersedesId: null, createdAt: "2026-09-28T00:00:00Z", updatedAt: "2026-09-28T00:00:00Z", content: "Synthetic wording", sourceRefs: [{ sourceId: id, sourceVersion: 1, contentSha256: "a".repeat(64), span: null }] };
test("available DTO preserves confirmation and rejects foreign authority", () => {
  assert.ok(validResponse("current", { memory }, workspace, owner));
  for (const delta of [{ ownerUserId: id }, { workspaceId: id }, { visibility: "shared" }, { confirmation: "inferred" }, { intent: "deleted", displayStatus: "deleted" }, { validity: "invalidated" }]) assert.equal(validResponse("current", { memory: { ...memory, ...delta } }, workspace, owner), false);
});
test("unavailable body cannot carry semantic bytes or source hashes", () => {
  assert.ok(validResponse("list", { items: [tombstone], nextCursor: null }, workspace, owner));
  for (const field of ["content", "conditions", "sourceRefs", "contentSha256"]) assert.equal(validResponse("current", { memory: { ...tombstone, [field]: "private" } }, workspace, owner), false);
});
test("operation resultVersion and currentVersion remain separate content-free metadata", () => {
  const operation = { requestId: id, accepted: true, operationId: id, state: "committed", resourceId: id, resultVersion: 1, currentVersion: 3, intent: "deleted", contentAvailable: false, cleanupState: "completed" };
  assert.ok(validResponse("request", operation, workspace, owner));
  assert.equal(validResponse("request", { ...operation, body: "private" }, workspace, owner), false);
  assert.equal(validResponse("request", { ...operation, currentVersion: "3" }, workspace, owner), false);
});
test("successor receipts require verified predecessor and current memory projection", () => {
  const receipt = { requestId: id, operationId: id, resultVersion: 1, memory: { ...memory, id: owner }, indexState: "not_enabled", supersededMemoryId: id };
  assert.ok(validResponse("correct", receipt, workspace, owner));
  assert.equal(validResponse("correct", { ...receipt, indexState: "pending" }, workspace, owner), false);
  assert.equal(validResponse("create", receipt, workspace, owner), false);
});

test("R4 enum primitives and containers are never coerced", () => {
  for (const field of ["intent", "validity", "confirmation", "kind", "displayStatus"]) {
    const value = memory[field as keyof typeof memory];
    for (const malformed of [[value], { toString: () => value }, null, true, 1]) assert.equal(validResponse("current", { memory: { ...memory, [field]: malformed } }, workspace, owner), false);
  }
  assert.equal(validResponse("current", { memory: { ...tombstone, reason: ["erased"] } }, workspace, owner), false);
  const op = { requestId: id, operationId: id, resultVersion: 1, currentVersion: 3, resourceId: id, accepted: true, state: "committed", intent: "deleted", contentAvailable: false, cleanupState: "completed" };
  for (const field of ["intent", "cleanupState", "state"]) assert.equal(validResponse("request", { ...op, [field]: [op[field as keyof typeof op]] }, workspace, owner), false);
});
test("R3 endpoint binding preserves replay aliases and correction successors", () => {
  assert.equal(validResponse("current", { memory }, workspace, owner, owner), false);
  assert.equal(validResponse("revisions", { items: [memory], nextCursor: null }, workspace, owner, owner), false);
  const receipt = { requestId: owner, operationId: owner, resultVersion: 1, memory, indexState: "not_enabled" };
  assert.ok(validResponse("deactivate", receipt, workspace, owner, id));
  assert.equal(validResponse("deactivate", receipt, workspace, owner, owner), false);
  const correction = { ...receipt, memory: { ...memory, id: owner }, supersededMemoryId: id };
  assert.ok(validResponse("correct", correction, workspace, owner, id));
  assert.equal(validResponse("correct", correction, workspace, owner, owner), false);
  const op = { requestId: id, operationId: owner, resultVersion: 1, currentVersion: 3, resourceId: id, accepted: true, state: "committed", intent: "deleted", contentAvailable: false, cleanupState: "completed" };
  assert.ok(validResponse("request", op, workspace, owner, id));
  assert.equal(validResponse("request", op, workspace, owner, owner), false);
  assert.ok(validResponse("operation", op, workspace, owner, owner));
  assert.equal(validResponse("operation", op, workspace, owner, id), false);
  const deletion = { requestId: owner, operationId: owner, resultVersion: 2, id, intent: "deleted", version: 3, cleanupState: "completed" };
  assert.ok(validResponse("delete", deletion, workspace, owner, id));
  assert.equal(validResponse("delete", deletion, workspace, owner, owner), false);
});
