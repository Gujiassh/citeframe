import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { ReindexTracker, reindexActive } from "./reindex-tracker";
import type { JobStatusDto } from "./types";
const job = (status: string, assetId = "asset-a", workspaceId = "workspace-a"): JobStatusDto => ({ id: `job-${assetId}`, workspaceId, assetId, jobType: "embed_chunks", status, attemptCount: 1, queuedAt: "now", startedAt: null, finishedAt: null, errorCode: null, errorMessage: null });
const json = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status });
async function until(predicate: () => boolean) { for (let i = 0; i < 100; i++) { if (predicate()) return; await new Promise((r) => setTimeout(r, 2)); } assert.fail("Timed out waiting for test condition"); }
function setup(t: TestContext) { const tracker = new ReindexTracker(1); tracker.start(); t.after(() => tracker.stop()); return tracker; }

test("ready asset reindex explicitly polls returned job.id until terminal status", async (t) => {
  const tracker = setup(t); const calls: string[] = []; let polls = 0;
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    calls.push(url);
    if (init.method === "POST") return json({ asset: { status: "ready" }, job: job("queued") });
    return json({ job: job(++polls === 1 ? "running" : "succeeded") });
  });
  await tracker.submit("workspace-a", "asset-a"); await until(() => tracker.getSnapshot()[0].job?.status === "succeeded");
  assert.deepEqual(calls, ["/api/workspaces/workspace-a/assets/asset-a/reindex", "/api/workspaces/workspace-a/jobs/job-asset-a", "/api/workspaces/workspace-a/jobs/job-asset-a"]);
  assert.equal(reindexActive(tracker.getSnapshot()[0]), false);
});
test("poll failure offers status refresh without issuing another reindex POST", async (t) => {
  const tracker = setup(t); let posts = 0; let unavailable = true;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    if (init.method === "POST") { posts++; return json({ job: job("queued") }); }
    return unavailable ? json({ detail: "Unavailable" }, 503) : json({ job: job("succeeded") });
  });
  await tracker.submit("workspace-a", "asset-a"); await until(() => Boolean(tracker.getSnapshot()[0].error));
  await tracker.submit("workspace-a", "asset-a"); assert.equal(posts, 1);
  unavailable = false; tracker.resume("workspace-a", "asset-a"); await until(() => tracker.getSnapshot()[0].job?.status === "succeeded"); assert.equal(posts, 1);
});
test("terminal job failure is retained independently from asset readiness", async (t) => {
  const tracker = setup(t);
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => init.method === "POST" ? json({ job: job("queued") }) : json({ job: { ...job("failed"), errorMessage: "Provider unavailable" } }));
  await tracker.submit("workspace-a", "asset-a"); await until(() => tracker.getSnapshot()[0].job?.status === "failed");
  assert.equal(tracker.getSnapshot()[0].job?.errorMessage, "Provider unavailable"); assert.equal(reindexActive(tracker.getSnapshot()[0]), false);
});
test("job response cannot cross workspace or asset boundaries", async (t) => {
  const tracker = setup(t);
  t.mock.method(globalThis, "fetch", async () => json({ job: job("queued", "asset-a", "another-workspace") }));
  await tracker.submit("workspace-a", "asset-a"); assert.match(tracker.getSnapshot()[0].error!, /Invalid reindex/); assert.equal(tracker.getSnapshot()[0].job, undefined);
});
test("logout clears jobs and rejects a late response", async (t) => {
  const tracker = setup(t); let resolve!: (response: Response) => void;
  t.mock.method(globalThis, "fetch", () => new Promise<Response>((done) => { resolve = done; }));
  const submitting = tracker.submit("workspace-a", "asset-a"); tracker.stop(); resolve(json({ job: job("queued") })); await submitting;
  assert.deepEqual(tracker.getSnapshot(), []);
});
