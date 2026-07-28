import assert from "node:assert/strict";
import test from "node:test";

import { researchProxyHeaderPolicy } from "./server-route-policy";

test("Research SSE forwards only stream cursor headers", () => {
  assert.deepEqual(researchProxyHeaderPolicy("GET", "/v1/workspaces/ws/research-runs/run/events?after=1"), {
    request: ["accept", "last-event-id"],
    response: ["content-type", "cache-control", "x-accel-buffering"],
  });
});

test("Research mutations forward JSON and idempotency headers without browser auth or cursor headers", () => {
  const policy = researchProxyHeaderPolicy("POST", "/v1/workspaces/ws/research-runs/run/cancel");
  assert.deepEqual(policy.request, ["content-type", "idempotency-key"]);
  assert.equal(policy.request.includes("x-user-id"), false);
  assert.equal(policy.request.includes("last-event-id"), false);
});

test("Research artifact content preserves immutable response metadata", () => {
  const policy = researchProxyHeaderPolicy("GET", "/v1/workspaces/ws/research-runs/run/artifacts/art/content");
  assert.deepEqual(policy.response, ["content-type", "content-length", "content-disposition", "cache-control", "etag"]);
});
