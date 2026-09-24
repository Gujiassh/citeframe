import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { createAssetUploadTask } from "./upload-task";
import type { AssetSummaryDto } from "./types";

const asset = { id: "asset-a", workspaceId: "workspace-a", status: "pending_upload" } as AssetSummaryDto;
const session = { asset, upload: { url: "/transfer", method: "PUT", headers: { "x-test": "value" }, objectKey: "object-a" } };
const json = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
function setup(t: TestContext) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const responses: (() => Response | Promise<Response>)[] = [];
  t.mock.method(globalThis, "fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const response = responses.shift(); assert.ok(response, `Unexpected request ${url}`); return response();
  });
  const published: { asset: AssetSummaryDto; created: boolean }[] = [];
  const task = createAssetUploadTask({ file: new File(["content"], "a.md", { type: "text/markdown" }), workspaceId: "workspace-a", locale: "en", onAsset: (asset, created) => published.push({ asset, created }) });
  return { calls, responses, published, task };
}

test("upload task preserves request contracts and reports submitted asset independently of readiness", async (t) => {
  const { task, responses, calls, published } = setup(t);
  responses.push(() => json(session), () => new Response(null, { status: 204 }), () => json({ asset: { ...asset, status: "uploaded" } }));
  await task(new AbortController().signal);
  assert.deepEqual(calls.map((c) => [c.url, c.init?.method]), [
    ["/api/workspaces/workspace-a/assets/upload-session", "POST"], ["/transfer", "PUT"], ["/api/workspaces/workspace-a/assets/asset-a/finalize-upload", "POST"],
  ]);
  assert.deepEqual(JSON.parse(calls[0].init?.body as string), { sourceFilename: "a.md", mimeType: "text/markdown", byteSize: 7 });
  assert.deepEqual(JSON.parse(calls[2].init?.body as string), { objectKey: "object-a" });
  assert.deepEqual(published.map((p) => [p.asset.status, p.created]), [["pending_upload", true], ["uploaded", false]]);
});

test("transfer failure retries the existing session without creating another asset", async (t) => {
  const { task, responses, calls } = setup(t);
  responses.push(() => json(session), () => json({ detail: "Storage unavailable" }, 503));
  await assert.rejects(task(new AbortController().signal), /Storage unavailable/);
  responses.push(() => new Response(null, { status: 204 }), () => json({ asset: { ...asset, status: "uploaded" } }));
  await task(new AbortController().signal);
  assert.equal(calls.filter((c) => c.url.endsWith("upload-session")).length, 1);
  assert.equal(calls.filter((c) => c.url === "/transfer").length, 2);
});

test("lost finalize response checks the existing asset and never repeats successful submission", async (t) => {
  const { task, responses, calls } = setup(t);
  responses.push(() => json(session), () => new Response(null, { status: 204 }), () => { throw new Error("Connection lost"); });
  await assert.rejects(task(new AbortController().signal), /Connection lost/);
  responses.push(() => json({ items: [{ ...asset, status: "failed" }] }));
  await task(new AbortController().signal);
  assert.equal(calls.filter((c) => c.url.endsWith("finalize-upload")).length, 1);
  assert.equal(calls.filter((c) => c.url === "/transfer").length, 1);
});

test("failed finalize retries only finalize when server still awaits submission", async (t) => {
  const { task, responses, calls } = setup(t);
  responses.push(() => json(session), () => new Response(null, { status: 204 }), () => json({ detail: "Unavailable" }, 503));
  await assert.rejects(task(new AbortController().signal), /Unavailable/);
  responses.push(() => json({ items: [asset] }), () => json({ asset: { ...asset, status: "uploaded" } }));
  await task(new AbortController().signal);
  assert.equal(calls.filter((c) => c.url.endsWith("finalize-upload")).length, 2);
  assert.equal(calls.filter((c) => c.url === "/transfer").length, 1);
});

test("unsupported file validation sends no requests", async (t) => {
  const { calls } = setup(t);
  const task = createAssetUploadTask({ file: new File(["x"], "a.exe"), workspaceId: "workspace-a", locale: "en", onAsset: () => assert.fail() });
  await assert.rejects(task(new AbortController().signal), /Choose a PDF/); assert.equal(calls.length, 0);
});

test("aborted owner cannot publish a late response or advance upload stages", async (t) => {
  const { task, responses, calls, published } = setup(t); const controller = new AbortController();
  responses.push(() => { controller.abort(); return json(session); });
  await assert.rejects(task(controller.signal), { name: "AbortError" });
  assert.equal(calls.length, 1); assert.deepEqual(published, []);
});

test("finalize reconciliation cannot use another asset or recreate a removed asset", async (t) => {
  const { task, responses, calls } = setup(t);
  responses.push(() => json(session), () => new Response(null, { status: 204 }), () => { throw new Error("Connection lost"); });
  await assert.rejects(task(new AbortController().signal), /Connection lost/);
  responses.push(() => json({ items: [{ ...asset, id: "another-asset", status: "ready" }] }));
  await assert.rejects(task(new AbortController().signal), /Asset no longer exists/);
  assert.equal(calls.at(-1)?.url, "/api/workspaces/workspace-a/assets");
  assert.equal(calls.filter((c) => c.url.endsWith("upload-session")).length, 1);
});
