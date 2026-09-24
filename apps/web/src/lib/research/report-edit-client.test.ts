import assert from "node:assert/strict";
import test from "node:test";

import { getReportEdit, putReportEdit, ReportEditError } from "./report-edit-client";

const originalFetch = globalThis.fetch;
const body = { originalArtifactId: "artifact", originalSha256: "sha", version: 1, markdown: "# edited", actorUserId: "creator", updatedAt: "2026-09-23T00:00:00Z", verificationStatus: "unverified" };

test("report edit client reads uncached authoritative saved version", async () => {
  const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
  globalThis.fetch = (async (input, init) => { calls.push([input, init]); return Response.json(body); }) as typeof fetch;
  try {
    assert.deepEqual(await getReportEdit("workspace", "run"), body);
    assert.equal(calls[0][0], "/api/workspaces/workspace/research-runs/run/report-edit");
    assert.equal(calls[0][1]?.cache, "no-store");
  } finally { globalThis.fetch = originalFetch; }
});

test("report edit client sends optimistic version and preserves conflict code", async () => {
  let captured: RequestInit | undefined;
  globalThis.fetch = (async (_input, init) => { captured = init; return Response.json({ error: { code: "report_edit_version_conflict", message: "Newer version" } }, { status: 409 }); }) as typeof fetch;
  try {
    await assert.rejects(putReportEdit("workspace", "run", 2, "draft", body), (error: unknown) => {
      assert.ok(error instanceof ReportEditError);
      assert.equal(error.status, 409);
      assert.equal(error.code, "report_edit_version_conflict");
      return true;
    });
    assert.equal(captured?.method, "PUT");
    assert.deepEqual(JSON.parse(captured?.body as string), { expectedVersion: 2, markdown: "draft", originalArtifactId: body.originalArtifactId, originalSha256: body.originalSha256 });
  } finally { globalThis.fetch = originalFetch; }
});
