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


function streamRequest(chunks: Uint8Array[], options: { headers?: Record<string, string>; highWaterMark?: number; stayOpen?: boolean; cancel?: () => void | Promise<void>; failAfter?: number } = {}) {
  const stats = { pulls: 0, cancellations: 0 };
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      stats.pulls++;
      if (index === options.failAfter) throw new Error("fixture-private-read-diagnostic");
      if (index < chunks.length) controller.enqueue(chunks[index++]);
      if (index === chunks.length && !options.stayOpen) controller.close();
    },
    cancel() { stats.cancellations++; return options.cancel?.(); },
  }, { highWaterMark: options.highWaterMark ?? 0 });
  const init: RequestInit & { duplex: "half" } = { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": "original-key", ...options.headers }, body: stream, duplex: "half" };
  const request = new Request(`http://app.invalid/api/workspaces/${workspaceId}/memories`, init);
  request.text = async () => { throw new Error("whole_body_text_forbidden"); };
  request.arrayBuffer = async () => { throw new Error("whole_body_array_buffer_forbidden"); };
  return { request, stats };
}
const encodeBody = (text: string) => new TextEncoder().encode(text);
async function invalidStream(request: Request) {
  const { deps, calls } = harness();
  let sessions = 0;
  deps.session = async () => { sessions++; return null; };
  const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: { code: "invalid_request", message: errors.invalid_request[1], retryable: false, requestId: null } });
  assert.match(response.headers.get("cache-control")!, /private, no-store/);
  assert.equal(response.headers.get("vary"), "Cookie");
  assert.equal(sessions, 0); assert.equal(calls.length, 0);
  assert.equal(request.body?.locked ?? false, false);
}
const createBody = { requestId, kind: "fact", content: "中文😀", conditions: { subject: "Fixture", applicability: "Tests" }, scope: { kind: "workspace" } };
const createReceipt = { requestId, operationId: requestId, resultVersion: 1, memory: { id: requestId, version: 1, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" }, indexState: "not_enabled" };

const transferHeaders: Record<string, string>[] = [{}, { "content-length": "1" }, { "content-length": "1048576" }, { "transfer-encoding": "chunked" }];
for (const headers of transferHeaders) {
  test(`stream overflow stops at first excess chunk regardless of ${JSON.stringify(headers)}`, { timeout: 1000 }, async () => {
    const { request, stats } = streamRequest([new Uint8Array(32768), new Uint8Array(32768), new Uint8Array(1)], { headers, stayOpen: true });
    await invalidStream(request);
    assert.equal(stats.pulls, 3); assert.equal(stats.cancellations, 1);
  });
}

test("default backpressure permits at most one prefetched chunk and cancels before full payload", async () => {
  const chunks = Array.from({ length: 256 }, () => new Uint8Array(4096));
  const { request, stats } = streamRequest(chunks, { highWaterMark: 1 });
  await invalidStream(request);
  assert.ok(stats.pulls >= 17 && stats.pulls <= 18);
  assert.equal(stats.cancellations, 1);
});

for (const cleanup of ["throws", "rejects", "pending"] as const) {
  test(`overflow remains fixed422 and releases lock when producer cancellation ${cleanup}`, { timeout: 1000 }, async () => {
    const { request, stats } = streamRequest([new Uint8Array(65537)], {
      stayOpen: true,
      cancel: () => {
        if (cleanup === "throws") throw new Error("fixture-private-cleanup-diagnostic");
        if (cleanup === "rejects") return Promise.reject(new Error("fixture-private-cleanup-diagnostic"));
        return new Promise<void>(() => {});
      },
    });
    await invalidStream(request);
    assert.equal(stats.pulls, 1); assert.equal(stats.cancellations, 1);
  });
}

for (const failAfter of [0, 1]) {
  test(`read failure after ${failAfter} chunks stays sanitized and releases reader`, async () => {
    const { request } = streamRequest([encodeBody('{"content":"'), encodeBody('unfinished')], { failAfter, stayOpen: true });
    await invalidStream(request);
  });
}

for (const malformed of ["", "{", '{"content":"unterminated', "{}{}"] ) {
  test(`malformed JSON case length${malformed.length} precedes authentication`, async () => {
    const { request, stats } = streamRequest([encodeBody(malformed)]);
    await invalidStream(request);
    assert.equal(stats.cancellations, 0);
  });
}

test("absent body preserves invalid JSON precedence without session/upstream access", async () => {
  await invalidStream(new Request("http://app.invalid", { method: "POST" }));
});

for (const length of [65535, 65536]) {
  test(`valid JSON at ${length} raw bytes authenticates and forwards unchanged command`, async () => {
    const json = JSON.stringify(createBody);
    const bytes = encodeBody(json + " ".repeat(length - encodeBody(json).length));
    const { request, stats } = streamRequest([bytes.slice(0, 31), bytes.slice(31, 32768), bytes.slice(32768)]);
    const { deps, calls } = harness(Response.json(createReceipt, { status: 201 }));
    const session = deps.session; let sessions = 0;
    deps.session = async () => { sessions++; return session(); };
    const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
    assert.equal(response.status, 201); assert.deepEqual(await response.json(), createReceipt);
    assert.equal(sessions, 1); assert.equal(calls.length, 1);
    assert.equal(calls[0].init?.body, json);
    assert.equal(new Headers(calls[0].init?.headers).get("Idempotency-Key"), "original-key");
    assert.equal(calls[0].init?.cache, "no-store"); assert.equal(calls[0].init?.redirect, "error");
    assert.equal(stats.cancellations, 0); assert.equal(request.body?.locked, false);
  });
}

test("cross-chunk UTF8 including BOM and malformed sequences matches standard Request text decoding", async () => {
  const prefix = encodeBody(JSON.stringify({ ...createBody, content: "MARKER" }));
  const marker = encodeBody("MARKER"), at = prefix.findIndex((_, index) => marker.every((value, offset) => prefix[index + offset] === value));
  const content = new Uint8Array([0xe4, 0xb8, 0xad, 0xf0, 0x9f, 0x98, 0x80, 0xc3, 0x28, 0xe2]);
  const bytes = new Uint8Array([0xef, 0xbb, 0xbf, ...prefix.slice(0, at), ...content, ...prefix.slice(at + marker.length)]);
  const standard = JSON.parse(await new Request("http://app.invalid", { method: "POST", body: bytes }).text());
  const { request } = streamRequest(Array.from(bytes, byte => new Uint8Array([byte])));
  const { deps, calls } = harness(Response.json(createReceipt, { status: 201 }));
  assert.equal((await memoryProxy(request, { workspaceId, endpoint: "create" }, deps)).status, 201);
  assert.equal(calls[0].init?.body, JSON.stringify(standard));
  assert.equal(request.body?.locked, false);
});

test("raw-byte cap counts UTF8 bytes rather than decoded characters", async () => {
  const bytes = encodeBody(JSON.stringify({ ...createBody, content: "😀".repeat(17000) }));
  assert.ok(bytes.length > 65536);
  const { request, stats } = streamRequest([bytes.slice(0, 65536), bytes.slice(65536)], { stayOpen: true });
  await invalidStream(request);
  assert.equal(stats.pulls, 2); assert.equal(stats.cancellations, 1);
});

test("bounded syntactically valid body still reaches missing-session401", async () => {
  const { request } = streamRequest([encodeBody(JSON.stringify(createBody))]);
  const { deps, calls } = harness(); deps.session = async () => null;
  const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
  assert.equal(response.status, 401); assert.equal((await response.json()).detail.requestId, null);
  assert.equal(calls.length, 0); assert.equal(request.body?.locked, false);
});


test("F53-R2 Next localhost URL accepts actual 127 Host and browser Origin", async () => {
  const body = { requestId, kind: "fact", content: "Synthetic", conditions: { subject: "Fixture", applicability: "Tests" }, scope: { kind: "workspace" } };
  const receipt = { requestId, operationId: requestId, resultVersion: 1, memory: { id: requestId, version: 1, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" }, indexState: "not_enabled" };
  const { deps, calls } = harness(Response.json(receipt, { status: 201 }));
  const request = new Request(`http://localhost:18430/api/workspaces/${workspaceId}/memories`, { method: "POST", headers: { host: "127.0.0.1:18430", origin: "http://127.0.0.1:18430", "content-type": "application/json", "Idempotency-Key": "original-key" }, body: JSON.stringify(body) });
  const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
  assert.equal(response.status, 201);
  assert.equal(calls.length, 1);
  assert.deepEqual(await response.json(), receipt);
});


function publicOriginFixture(headers: Record<string, string>, internal = "http://localhost:18430") {
  const body = { requestId, kind: "fact", content: "Synthetic", conditions: { subject: "Fixture", applicability: "Tests" }, scope: { kind: "workspace" } };
  const receipt = { requestId, operationId: requestId, resultVersion: 1, memory: { id: requestId, version: 1, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" }, indexState: "not_enabled" };
  const { deps, calls } = harness(Response.json(receipt, { status: 201 }));
  const request = new Request(`${internal}/api/workspaces/${workspaceId}/memories`, { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": "original-key", "x-user-id": "forged-owner", ...headers }, body: JSON.stringify(body) });
  return { request, deps, calls, body, receipt };
}
async function assertOriginDenied(request: Request, deps: ProxyDependencies, calls: unknown[]) {
  const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: { code: "invalid_request", message: errors.invalid_request[1], retryable: false, requestId } });
  assert.match(response.headers.get("cache-control")!, /private, no-store/);
  assert.equal(response.headers.get("vary"), "Cookie");
  assert.equal(calls.length, 0);
}

const publicOriginCases: readonly [string, string, string, string][] = [
  ["hostname target", "http://localhost:18430", "localhost:18430", "http://localhost:18430"],
  ["case-insensitive DNS", "http://localhost:18430", "APP.INVALID:18430", "http://app.invalid:18430"],
  ["HTTP default Host port", "http://localhost:18430", "app.invalid:80", "http://app.invalid"],
  ["HTTP default Origin port", "http://localhost:18430", "app.invalid", "http://app.invalid:80"],
  ["HTTPS default Host port", "https://localhost:3000", "app.invalid:443", "https://app.invalid"],
  ["HTTPS default Origin port", "https://localhost:3000", "app.invalid", "https://app.invalid:443"],
  ["HTTPS explicit port", "https://localhost:3000", "app.invalid:8443", "https://app.invalid:8443"],
  ["IPv6 loopback", "http://localhost:18430", "[::1]:18430", "http://[::1]:18430"],
  ["IPv6 normalized spelling", "http://localhost:18430", "[0:0:0:0:0:0:0:1]:18430", "http://[::1]:18430"],
  ["IPv6 HTTPS default port", "https://localhost:3000", "[2001:db8::1]:443", "https://[2001:db8::1]"],
  ["public IPv4 target", "http://localhost:18430", "192.0.2.1:18430", "http://192.0.2.1:18430"],
];

for (const [name, internal, host, origin] of publicOriginCases) {
  test(`F53-R2 canonical same-origin ${name}`, async () => {
    const { request, deps, calls, receipt, body } = publicOriginFixture({ host, origin }, internal);
    const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, deps);
    assert.equal(response.status, 201); assert.deepEqual(await response.json(), receipt);
    assert.equal(calls.length, 1); assert.equal(calls[0].init?.body, JSON.stringify(body));
    assert.deepEqual(calls[0].init?.headers, { "x-user-id": "signed-owner", "x-ai-pdf-internal-token": "synthetic-internal", "Content-Type": "application/json", "Idempotency-Key": "original-key" });
    assert.match(response.headers.get("cache-control")!, /private, no-store/); assert.equal(response.headers.get("vary"), "Cookie");
  });
}

const deniedOriginCases: readonly [string, string | null, string][] = [
  ["foreign Origin", "127.0.0.1:18430", "https://attacker.invalid"],
  ["internal localhost is not public Origin", "127.0.0.1:18430", "http://localhost:18430"],
  ["foreign Host", "attacker.invalid", "http://127.0.0.1:18430"],
  ["wrong port", "127.0.0.1:18431", "http://127.0.0.1:18430"],
  ["missing Host", null, "http://127.0.0.1:18430"],
  ["empty Host", "", "http://127.0.0.1:18430"],
  ["Host userinfo", "user@app.invalid", "http://app.invalid"],
  ["Host path", "app.invalid/path", "http://app.invalid"],
  ["Host query", "app.invalid?x", "http://app.invalid"],
  ["Host fragment", "app.invalid#x", "http://app.invalid"],
  ["multiple Host values", "app.invalid,attacker.invalid", "http://app.invalid"],
  ["Host backslash", "app.invalid\\evil", "http://app.invalid"],
  ["Host percent escape", "app.invalid%2fextra", "http://app.invalid"],
  ["Host oversized port", "app.invalid:65536", "http://app.invalid"],
  ["Host invalid IPv6", "[::g]:18430", "http://[::1]:18430"],
  ["Host unbracketed IPv6", "::1:18430", "http://[::1]:18430"],
  ["Host empty port", "app.invalid:", "http://app.invalid"],
  ["Host negative port", "app.invalid:-1", "http://app.invalid"],
  ["Host whitespace", "app.invalid :80", "http://app.invalid"],
  ["Host protocol prefix", "http://app.invalid", "http://app.invalid"],
  ["null Origin", "127.0.0.1:18430", "null"],
  ["empty Origin", "127.0.0.1:18430", ""],
  ["Origin path", "app.invalid", "http://app.invalid/private"],
  ["Origin trailing slash", "app.invalid", "http://app.invalid/"],
  ["Origin query", "app.invalid", "http://app.invalid?x"],
  ["Origin fragment", "app.invalid", "http://app.invalid#x"],
  ["Origin userinfo", "app.invalid", "http://user@app.invalid"],
  ["Origin list", "app.invalid", "http://app.invalid,http://attacker.invalid"],
  ["non-HTTP Origin", "app.invalid", "ftp://app.invalid"],
  ["wrong scheme", "127.0.0.1:18430", "https://127.0.0.1:18430"],
];

for (const [name, host, origin] of deniedOriginCases) {
  test(`F53-R2 rejects ${name}`, async () => {
    const value = publicOriginFixture({ ...(host === null ? {} : { host }), origin });
    await assertOriginDenied(value.request, value.deps, value.calls);
  });
}
for (const origin of ["http://127.0.0.1:18430", "https://127.0.0.1:18430"]) {
  test(`F53-R2 forwarded claims cannot select expected origin ${origin}`, async () => {
    const value = publicOriginFixture({ host: "127.0.0.1:18430", origin, "x-forwarded-host": "attacker.invalid", "x-forwarded-proto": "https", forwarded: "host=attacker.invalid;proto=https" });
    if (origin.startsWith("https:")) await assertOriginDenied(value.request, value.deps, value.calls);
    else {
      assert.equal((await memoryProxy(value.request, { workspaceId, endpoint: "create" }, value.deps)).status, 201);
      assert.equal(value.calls.length, 1);
      const headers = new Headers(value.calls[0].init?.headers);
      assert.equal(headers.get("host"), null); assert.equal(headers.get("origin"), null); assert.equal(headers.get("x-forwarded-host"), null); assert.equal(headers.get("x-forwarded-proto"), null);
    }
  });
}
test("F53-R2 ignored forwarded HTTP cannot downgrade framework HTTPS", async () => {
  const value = publicOriginFixture({ host: "app.invalid", origin: "https://app.invalid", "x-forwarded-host": "attacker.invalid", "x-forwarded-proto": "http" }, "https://localhost:3000");
  assert.equal((await memoryProxy(value.request, { workspaceId, endpoint: "create" }, value.deps)).status, 201); assert.equal(value.calls.length, 1);
});
for (const withOrigin of [false, true]) {
  test(`F53-R2 Sec-Fetch-Site cross-site rejects with Origin=${withOrigin}`, async () => {
    const value = publicOriginFixture({ host: "127.0.0.1:18430", ...(withOrigin ? { origin: "http://127.0.0.1:18430" } : {}), "sec-fetch-site": "cross-site" });
    await assertOriginDenied(value.request, value.deps, value.calls);
  });
}
test("F53-R2 same-origin fetch metadata cannot override foreign Origin", async () => {
  const value = publicOriginFixture({ host: "127.0.0.1:18430", origin: "https://attacker.invalid", "sec-fetch-site": "same-origin" });
  await assertOriginDenied(value.request, value.deps, value.calls);
});
for (const host of [undefined, "127.0.0.1:18430"]) {
  test(`F53-R2 no-Origin compatibility Host=${host ?? "absent"}`, async () => {
    const value = publicOriginFixture(host ? { host } : {});
    assert.equal((await memoryProxy(value.request, { workspaceId, endpoint: "create" }, value.deps)).status, 201); assert.equal(value.calls.length, 1);
  });
}
test("F53-R2 malformed present Host fails even without Origin", async () => {
  const value = publicOriginFixture({ host: "app.invalid/path" }); await assertOriginDenied(value.request, value.deps, value.calls);
});
for (const headers of [{ host: "127.0.0.1:18430", origin: "https://attacker.invalid" }, { origin: "http://127.0.0.1:18430" }]) {
  test(`F53-R2 authentication still precedes origin rejection Host=${headers.host ?? "absent"}`, async () => {
    const value = publicOriginFixture({ origin: headers.origin, ...(headers.host ? { host: headers.host } : {}) }); let sessions = 0; value.deps.session = async () => { sessions++; return null; };
    const response = await memoryProxy(value.request, { workspaceId, endpoint: "create" }, value.deps);
    assert.equal(response.status, 401); assert.equal((await response.json()).detail.requestId, null); assert.equal(sessions, 1); assert.equal(value.calls.length, 0);
  });
}
test("F53-R2 malformed JSON still precedes session and origin", async () => {
  const value = publicOriginFixture({ host: "127.0.0.1:18430", origin: "https://attacker.invalid" }); let sessions = 0;
  value.deps.session = async () => { sessions++; return null; };
  const request = new Request(value.request.url, { method: "POST", headers: value.request.headers, body: "{" });
  const response = await memoryProxy(request, { workspaceId, endpoint: "create" }, value.deps);
  assert.equal(response.status, 422); assert.equal((await response.json()).detail.requestId, null); assert.equal(sessions, 0); assert.equal(value.calls.length, 0);
});
for (const method of ["PATCH", "DELETE"] as const) {
  test(`F53-R2 ${method} uses public Host and retains command identity`, async () => {
    const body = { requestId, expectedVersion: 1, ...(method === "PATCH" ? { intent: "inactive" } : {}) };
    const { deps, calls } = harness(Response.json({ detail: { code: "temporarily_unavailable", requestId } }, { status: 503 }));
    const request = new Request(`http://localhost:18430/api/workspaces/${workspaceId}/memories/${id}`, { method, headers: { host: "127.0.0.1:18430", origin: "http://127.0.0.1:18430", "content-type": "application/json", "Idempotency-Key": "original-key" }, body: JSON.stringify(body) });
    const response = await memoryProxy(request, { workspaceId, id, endpoint: method === "PATCH" ? "deactivate" : "delete" }, deps);
    assert.equal(response.status, 503); assert.equal(calls.length, 1); assert.equal(calls[0].init?.method, method); assert.equal(calls[0].init?.body, JSON.stringify(body));
    assert.equal(new Headers(calls[0].init?.headers).get("Idempotency-Key"), "original-key");
  });
}
test("F53-R2 source POST also rejects foreign Origin", async () => {
  const { deps, calls } = harness();
  const request = new Request("http://localhost:18430", { method: "POST", headers: { host: "127.0.0.1:18430", origin: "https://attacker.invalid", "content-type": "application/json" }, body: JSON.stringify({ sourceRef: { sourceId: id, sourceVersion: 1, contentSha256: "a".repeat(64), span: null } }) });
  const response = await memoryProxy(request, { workspaceId, endpoint: "source" }, deps);
  assert.equal(response.status, 422); assert.equal((await response.json()).detail.requestId, null); assert.equal(calls.length, 0);
});
test("F53-R2 overflow cancellation remains before origin/auth checks", async () => {
  const value = streamRequest([new Uint8Array(65537), encodeBody("never consumed")], { headers: { host: "127.0.0.1:18430", origin: "https://attacker.invalid" }, stayOpen: true });
  await invalidStream(value.request); assert.equal(value.stats.pulls, 1); assert.equal(value.stats.cancellations, 1); assert.equal(value.request.body!.locked, false);
});
test("F53-R2 public Host admits actual split UTF8 stream without whole-body methods", async () => {
  const value = publicOriginFixture({ host: "127.0.0.1:18430", origin: "http://127.0.0.1:18430" });
  const bytes = encodeBody(JSON.stringify({ ...value.body, content: "synthetic 中文 😀" }));
  const stream = streamRequest(Array.from(bytes, byte => Uint8Array.of(byte)), { headers: { host: "127.0.0.1:18430", origin: "http://127.0.0.1:18430" } });
  const response = await memoryProxy(stream.request, { workspaceId, endpoint: "create" }, value.deps);
  assert.equal(response.status, 201); assert.equal(value.calls.length, 1); assert.equal(value.calls[0].init?.body, JSON.stringify({ ...value.body, content: "synthetic 中文 😀" }));
  assert.equal(stream.stats.cancellations, 0); assert.equal(stream.request.body!.locked, false);
});


test("F53-R2 matching forged forwarded authority cannot admit foreign Origin", async () => {
  const value = publicOriginFixture({ host: "127.0.0.1:18430", origin: "http://attacker.invalid", "x-forwarded-host": "attacker.invalid", "x-forwarded-proto": "http", forwarded: "host=attacker.invalid;proto=http" });
  await assertOriginDenied(value.request, value.deps, value.calls);
});

const rootedDnsOriginCases: readonly [string, string, string, string][] = [
  ["matching root dot", "http://app.invalid.", "app.invalid.", "http://app.invalid."],
  ["HTTP default Host port", "http://localhost:18430", "app.invalid.:80", "http://app.invalid."],
  ["HTTP default Origin port", "http://localhost:18430", "app.invalid.", "http://app.invalid.:80"],
  ["HTTPS default Host port", "https://localhost:3000", "app.invalid.:443", "https://app.invalid."],
  ["public dotted Host with Next internal localhost URL", "http://localhost:18430", "app.invalid.:18430", "http://app.invalid.:18430"],
  ["public dotted localhost", "http://localhost:18430", "localhost.:18430", "http://localhost.:18430"],
];
for (const [name, internal, host, origin] of rootedDnsOriginCases) {
  test(`F53-R2 root-dot accepts ${name}`, async () => {
    const value = publicOriginFixture({ host, origin, "x-forwarded-host": "attacker.invalid", "x-forwarded-proto": "https" }, internal);
    const response = await memoryProxy(value.request, { workspaceId, endpoint: "create" }, value.deps);
    assert.equal(response.status, 201); assert.deepEqual(await response.json(), value.receipt);
    assert.equal(value.calls.length, 1); assert.equal(value.calls[0].init?.body, JSON.stringify(value.body));
    assert.equal(new Headers(value.calls[0].init?.headers).get("Idempotency-Key"), "original-key");
    assert.match(response.headers.get("cache-control")!, /private, no-store/); assert.equal(response.headers.get("vary"), "Cookie");
  });
}
const rejectedRootedDnsOrigins: readonly [string, string, string][] = [
  ["dotted Host versus undotted Origin", "app.invalid.", "http://app.invalid"],
  ["undotted Host versus dotted Origin", "app.invalid", "http://app.invalid."],
  ["wrong scheme", "app.invalid.:18430", "https://app.invalid.:18430"],
  ["wrong port", "app.invalid.:18430", "http://app.invalid.:18431"],
  ["multiple terminal dots", "app.invalid..", "http://app.invalid.."],
  ["dot after IPv6 bracket", "[::1].:18430", "http://[::1]:18430"],
  ["userinfo before dotted Host", "user@app.invalid.", "http://app.invalid."],
  ["path after dotted Host", "app.invalid./path", "http://app.invalid."],
];
for (const [name, host, origin] of rejectedRootedDnsOrigins) {
  test(`F53-R2 root-dot rejects ${name}`, async () => {
    const value = publicOriginFixture({ host, origin });
    await assertOriginDenied(value.request, value.deps, value.calls);
  });
}
