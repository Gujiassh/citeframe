import test from "node:test";
import assert from "node:assert/strict";
import { memoryProxy, type ProxyDependencies, type ProxyConfig } from "./proxy";
import { errors } from "./errors";
const workspaceId = "00000000-0000-0000-0000-000000000001";
const id = "00000000-0000-0000-0000-000000000002";
const requestId = "00000000-0000-0000-0000-000000000003";
function harness(response = Response.json({ items: [], nextCursor: null })) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const deps: ProxyDependencies = { session: async () => ({ userId: "signed-owner" }), headers: userId => ({ "x-user-id": userId, "x-ai-pdf-internal-token": "synthetic-internal" }), baseUrl: "http://api.invalid", fetch: async (url, init) => { calls.push({ url: String(url), init }); return response; } };
  return { deps, calls };
}
function req(method = "GET", body?: unknown, query = "") {
  return new Request(`http://app.invalid/api/workspaces/${workspaceId}/memories${query}`, { method, headers: { "content-type": "application/json", "Idempotency-Key": "original-key", "x-user-id": "forged-owner", "x-ai-pdf-internal-token": "forged-token", authorization: "forged" }, body: body === undefined ? undefined : JSON.stringify(body) });
}
test("server identity only; allowlisted query; no-store on both sides", async () => {
  const { deps, calls } = harness();
  const response = await memoryProxy(req("GET", undefined, "?status=all&scope=workspace&limit=30&cursor=opaque"), { workspaceId, endpoint: "list" }, deps);
  assert.equal(response.status, 200); assert.match(response.headers.get("cache-control")!, /no-store/);
  assert.deepEqual(calls[0].init?.headers, { "x-user-id": "signed-owner", "x-ai-pdf-internal-token": "synthetic-internal" });
  assert.equal(calls[0].init?.cache, "no-store"); assert.equal(calls[0].init?.redirect, "error");
  assert.equal(calls[0].url, `http://api.invalid/v1/workspaces/${workspaceId}/memories?status=all&scope=workspace&limit=30&cursor=opaque`);
});
test("DELETE preserves CAS body and request key", async () => {
  const { deps, calls } = harness(); const body = { requestId, expectedVersion: 7 };
  await memoryProxy(req("DELETE", body), { workspaceId, id, endpoint: "delete" }, deps);
  assert.equal(calls[0].init?.body, JSON.stringify(body));
  assert.equal(new Headers(calls[0].init?.headers).get("Idempotency-Key"), "original-key");
});
test("foreign fields, URL escapes and query overrides never forward", async () => {
  const { deps, calls } = harness();
  const cases: [Request, ProxyConfig][] = [[req("GET", undefined, "?ownerUserId=foreign"), { workspaceId, endpoint: "list" }], [req(), { workspaceId: "../other", endpoint: "list" }], [req(), { workspaceId, id: "../other", endpoint: "current" }], [req("DELETE", { requestId, expectedVersion: 1, ownerUserId: "foreign" }), { workspaceId, id, endpoint: "delete" }]];
  for (const [request, config] of cases) assert.equal((await memoryProxy(request, config, deps)).status, 422);
  assert.equal(calls.length, 0);
});
test("fixed error matrix suppresses private diagnostics and non-CAS version metadata", async () => {
  for (const [code, [status, message, retryable]] of Object.entries(errors)) {
    const { deps } = harness(Response.json({ detail: { code, message: "PRIVATE EXCEPTION", retryable: !retryable, requestId, currentVersion: 4, input: "PRIVATE INPUT" } }, { status }));
    const result = await memoryProxy(req(), { workspaceId, endpoint: "list" }, deps); const payload = await result.json();
    assert.equal(payload.detail.message, message); assert.equal(payload.detail.retryable, retryable);
    assert.equal(payload.detail.currentVersion, ["version_conflict", "terminal_memory"].includes(code) ? 4 : undefined);
    assert.ok(!JSON.stringify(payload).includes("PRIVATE"));
  }
});
test("unknown outcome keeps original request ID and does not resend", async () => {
  const { deps } = harness(); let calls = 0; deps.fetch = async () => { calls++; throw new Error("private detail"); };
  const response = await memoryProxy(req("DELETE", { requestId, expectedVersion: 1 }), { workspaceId, id, endpoint: "delete" }, deps);
  assert.equal(response.status, 503); assert.equal(calls, 1);
  assert.deepEqual((await response.json()).detail, { code: "outcome_unknown", message: errors.outcome_unknown[1], retryable: true, requestId });
});
for (const endpoint of ["create", "correct"] as const) {
  test(`accepted API activation forwards strict ${endpoint} with unchanged identity and command`, async () => {
    const body = { requestId, kind: "fact", content: "Synthetic", conditions: { subject: "Fixture", applicability: "Tests" }, ...(endpoint === "create" ? { scope: { kind: "workspace" } } : { expectedVersion: 7 }) };
    const receipt = { requestId, operationId: requestId, resultVersion: 1, memory: { id: requestId, version: 1, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" }, indexState: "not_enabled", ...(endpoint === "correct" ? { supersededMemoryId: id } : {}) };
    const { deps, calls } = harness(Response.json(receipt, { status: 201 }));
    const response = await memoryProxy(req("POST", body), { workspaceId, ...(endpoint === "correct" ? { id } : {}), endpoint }, deps);
    assert.equal(response.status, 201); assert.equal(calls.length, 1);
    assert.deepEqual(await response.json(), receipt);
    assert.equal(calls[0].init?.body, JSON.stringify(body));
    assert.equal(calls[0].url, `http://api.invalid/v1/workspaces/${workspaceId}/memories${endpoint === "correct" ? `/${id}/corrections` : ""}`);
    assert.equal(new Headers(calls[0].init?.headers).get("Idempotency-Key"), "original-key");
    assert.equal(new Headers(calls[0].init?.headers).get("x-user-id"), "signed-owner");
  });
}
test("syntax precedes session and initial auth failure has no request ID", async () => {
  const { deps, calls } = harness(); deps.session = async () => null;
  const response = await memoryProxy(req("DELETE", { requestId, expectedVersion: 1 }), { workspaceId, id, endpoint: "delete" }, deps);
  assert.equal(response.status, 401); assert.equal((await response.json()).detail.requestId, null);
  assert.equal((await memoryProxy(new Request("http://app.invalid", { method: "DELETE", body: "{" }), { workspaceId, id, endpoint: "delete" }, deps)).status, 422);
  assert.equal(calls.length, 0);
});
test("cross-origin mutation does not dispatch", async () => {
  const { deps, calls } = harness(); const request = req("DELETE", { requestId, expectedVersion: 1 }); request.headers.set("origin", "http://foreign.invalid");
  assert.equal((await memoryProxy(request, { workspaceId, id, endpoint: "delete" }, deps)).status, 422); assert.equal(calls.length, 0);
});

test("malformed successful mutation stays unknown; content-bearing poll fails closed", async () => {
  const { deps } = harness(Response.json({ saved: true, secret: "unvalidated" }));
  const response = await memoryProxy(req("DELETE", { requestId, expectedVersion: 1 }), { workspaceId, id, endpoint: "delete" }, deps);
  assert.equal(response.status, 503); assert.equal((await response.json()).detail.code, "outcome_unknown");
  const poll = harness(Response.json({ requestId, operationId: id, accepted: true, state: "committed", resourceId: id, resultVersion: 1, currentVersion: 1, intent: "active", contentAvailable: true, cleanupState: "not_required", content: "unvalidated" }));
  assert.equal((await memoryProxy(req(), { workspaceId, id: requestId, endpoint: "request" }, poll.deps)).status, 503);
});

test("R3 wrong deletion/poll targets fail safely without accepting unrelated operations", async () => {
  const operation = { requestId: id, operationId: id, resultVersion: 2, currentVersion: 3, resourceId: id, accepted: true, state: "committed", intent: "deleted", contentAvailable: false, cleanupState: "completed" };
  for (const endpoint of ["request", "operation"] as const) {
    const { deps } = harness(Response.json(operation));
    const response = await memoryProxy(req(), { workspaceId, id: requestId, endpoint }, deps);
    assert.equal(response.status, 503);
  }
  const { deps } = harness(Response.json({ requestId: id, operationId: id, resultVersion: 2, id: requestId, intent: "deleted", version: 3, cleanupState: "completed" }));
  const response = await memoryProxy(req("DELETE", { requestId, expectedVersion: 1 }), { workspaceId, id, endpoint: "delete" }, deps);
  assert.equal(response.status, 503); assert.equal((await response.json()).detail.code, "outcome_unknown");
});
