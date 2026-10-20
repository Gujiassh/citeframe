import test from "node:test";
import assert from "node:assert/strict";
import { validBody, validKey, validQuery } from "./validation";
const requestId = "00000000-0000-0000-0000-000000000001";
const create = { requestId, kind: "preference", content: "Exact wording", conditions: { subject: "Me", applicability: "Reports", effectiveFrom: null }, scope: { kind: "workspace" }, pinned: false, validUntil: null, sourceRefs: [] };
test("mandatory conditions, Unicode bounds, no transformation", () => {
  assert.ok(validBody("create", create));
  assert.ok(validBody("create", { ...create, content: "😀".repeat(4000) }));
  assert.ok(validBody("create", { ...create, content: " " }));
  for (const content of ["", "a".repeat(4001), true, 12]) assert.equal(validBody("create", { ...create, content }), false);
  for (const conditions of [{ subject: "Me" }, { applicability: "Reports" }, { ...create.conditions, subject: "a".repeat(257) }, { ...create.conditions, applicability: "a".repeat(2001) }, { ...create.conditions, effectiveFrom: "2026-09-28T12:00:00" }]) assert.equal(validBody("create", { ...create, conditions }), false);
});
test("authority, scopes, sources and unsupported mutations fail closed", () => {
  for (const field of ["ownerUserId", "workspaceId", "confirmation", "actor", "visibility"]) assert.equal(validBody("create", { ...create, [field]: "forged" }), false);
  assert.equal(validBody("create", { ...create, scope: { kind: "thread" } }), false);
  assert.equal(validBody("create", { ...create, sourceRefs: [{}] }), false);
  assert.equal(validBody("create", { ...create, pinned: true }), false);
  assert.ok(validBody("create", { ...create, kind: "constraint", pinned: true }));
  for (const expectedVersion of [true, "1", 0, 1.5]) assert.equal(validBody("deactivate", { requestId, expectedVersion, intent: "inactive" }), false);
  assert.ok(validBody("deactivate", { requestId, expectedVersion: 1, intent: "inactive" }));
  assert.equal(validBody("deactivate", { requestId, expectedVersion: 1, intent: "active" }), false);
  assert.equal(validBody("delete", { requestId, expectedVersion: 1, pinned: false }), false);
});
test("exact source version/hash/span only", () => {
  const sourceRef = { sourceId: requestId, sourceVersion: 1, contentSha256: "a".repeat(64), span: null };
  assert.ok(validBody("source", { sourceRef }));
  for (const delta of [{ sourceVersion: "1" }, { sourceVersion: true }, { contentSha256: "A".repeat(64) }, { span: [0, 5] }, { url: "https://example.com" }]) assert.equal(validBody("source", { sourceRef: { ...sourceRef, ...delta } }), false);
});
test("query/key allowlists reject ambiguity", () => {
  assert.ok(validQuery("list", new URLSearchParams("status=all&scope=workspace&limit=100&cursor=opaque")));
  for (const value of ["status=active&status=all", "limit=101", "limit=1.5", "ownerUserId=x", "scope=global", "cursor=" + "a".repeat(4097)]) assert.equal(validQuery("list", new URLSearchParams(value)), false);
  assert.equal(validQuery("revisions", new URLSearchParams("status=all")), false);
  assert.ok(validKey("original-key"));
  for (const key of [null, "short", "space key", "a".repeat(129), "你好12345678"]) assert.equal(validKey(key), false);
});
