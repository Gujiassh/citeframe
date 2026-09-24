import { expect, test, type BrowserContext, type Route } from "@playwright/test";

const workspaceId = "report-workspace";
const base = `/api/workspaces/${workspaceId}/research-runs`;
const now = "2026-09-23T00:00:00Z";
const original = "# Original report";
const sha = "a".repeat(64);
const json = (route: Route, payload: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
const run = (id: string) => ({
  id, workspaceId, createdByUserId: "report-user", question: `Report ${id}`, status: "completed", stateVersion: 2,
  currentEventSeq: 1, requestedAssetScope: { mode: "all_ready" }, frozenAssetCount: 0,
  currentPlanRevisionNumber: null, createdAt: id === "run-a" ? now : "2026-09-22T00:00:00Z", updatedAt: now, finishedAt: now,
  frozenAssetScope: { frozenAt: now, assets: [] }, plan: null, researchExecution: null,
  planningUsage: { providerCalls: 0, toolCalls: 0, inputTokens: 0, outputTokens: 0, usageFinal: true, measuredAt: now, usageSource: "actual" },
  researchUsage: null, steps: [], pendingDecisions: [], submittedDecisions: [], artifactCount: 1, failure: null,
  startedAt: now, cancelRequestedAt: null, cancelledAt: null,
});
const artifact = (id: string) => ({
  id: `artifact-${id}`, runId: id, stepId: "publisher", kind: "final_report", visibility: "user", logicalKey: "final-report",
  schemaVersion: "1", supersedesArtifactId: null, mediaType: "text/markdown", byteSize: original.length,
  sha256: sha, evidenceCount: 0, retentionClass: "workspace_lifetime", expiresAt: null, createdAt: now,
});
function gate() { let release!: () => void; const promise = new Promise<void>((resolve) => { release = resolve; }); return { promise, release }; }

async function fixture(context: BrowserContext) {
  const edits = new Map<string, { version: number; markdown: string | null }>();
  const firstGet = gate();
  let holdFirst = true;
  await context.route("**/api/auth/session", (route) => json(route, { user: { userId: "report-user", email: "report@example.com", name: "Report", avatarUrl: null } }));
  await context.route("**/api/workspaces", (route) => json(route, { items: [{ id: workspaceId, name: "Reports", role: "owner", assetCount: 0, noteCount: 0, threadCount: 0,
    createdAt: now, updatedAt: now, retrievalTopK: 6, chunkSize: 1200, embeddingProvider: "scripted", embeddingModel: "fixture", embeddingVersion: "1",
    generationProvider: "scripted", generationModel: "fixture" }], nextCursor: null }));
  for (const name of ["assets", "threads", "notes", "tags"]) {
    await context.route(`**/api/workspaces/${workspaceId}/${name}`, (route) => json(route, { items: [], nextCursor: null }));
  }
  await context.route(`**${base}**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    const id = /\/run-b(?:\/|$)/.test(path) ? "run-b" : "run-a";
    if (path.endsWith("/report-edit")) {
      if (route.request().method() === "GET") {
        if (holdFirst && id === "run-a") await firstGet.promise;
        const edit = edits.get(id) ?? { version: 0, markdown: null };
        return json(route, { originalArtifactId: artifact(id).id, originalSha256: sha,
          version: edit.version, markdown: edit.markdown, actorUserId: edit.version ? "report-user" : null,
          updatedAt: edit.version ? now : null, verificationStatus: "unverified" });
      }
      const body = route.request().postDataJSON() as { expectedVersion: number; markdown: string };
      const edit = edits.get(id) ?? { version: 0, markdown: null };
      if (body.expectedVersion !== edit.version) return json(route, { error: { code: "report_edit_version_conflict", message: "Newer version" } }, 409);
      edits.set(id, { version: edit.version + 1, markdown: body.markdown });
      return json(route, { originalArtifactId: artifact(id).id, originalSha256: sha, version: edit.version + 1,
        markdown: body.markdown, actorUserId: "report-user", updatedAt: now, verificationStatus: "unverified" });
    }
    if (path === base) return json(route, { items: [run("run-a"), run("run-b")], nextCursor: null });
    if (path.endsWith("/artifacts")) return json(route, { items: [artifact(id)] });
    if (path.endsWith("/content")) return route.fulfill({ status: 200, contentType: "text/markdown", body: original });
    if (path.includes("/artifacts/")) return json(route, { artifact: { ...artifact(id), workflowVersionId: "workflow", promptVersions: [], directPromptVersionId: null, claims: [], evidence: [] } });
    if (path.endsWith("/events")) return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": keepalive\n\n" });
    return json(route, { run: run(id) });
  });
  return { edits, releaseFirst: () => { holdFirst = false; firstGet.release(); } };
}

test("report edit saves, restores on refresh, and keeps a conflicting draft", async ({ context, page }) => {
  const f = await fixture(context);
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await expect(page.getByText("Original report", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
  f.releaseFirst();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("textbox", { name: "Report Markdown" }).fill("# My report");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("My report", { exact: true })).toBeVisible();
  await expect(page.getByText("Unverified", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await page.getByRole("tab", { name: "User-edited" }).click();
  await expect(page.getByText("My report", { exact: true })).toBeVisible();
  const second = await context.newPage();
  await second.goto(`/workspaces/${workspaceId}`);
  await second.getByRole("tab", { name: /深度研究|research/i }).click();
  await second.getByRole("button", { name: "Edit", exact: true }).click();
  await second.getByRole("textbox", { name: "Report Markdown" }).fill("# Second tab");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("textbox", { name: "Report Markdown" }).fill("# First tab newer");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await second.getByRole("button", { name: "Save", exact: true }).click();
  await expect(second.getByText("Your draft is preserved.", { exact: false })).toBeVisible();
  await expect(second.getByRole("textbox", { name: "Report Markdown" })).toHaveValue("# Second tab");
  await second.getByRole("button", { name: "Use my draft with latest version" }).click();
  await second.getByRole("button", { name: "Save", exact: true }).click();
  await expect(second.getByText("Second tab", { exact: true })).toBeVisible();
  expect(f.edits.get("run-a")).toEqual({ version: 3, markdown: "# Second tab" });
});
test("late report edit response cannot replace another selected run", async ({ context, page }) => {
  const f = await fixture(context);
  f.edits.set("run-a", { version: 1, markdown: "# A saved edit" });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await expect(page.getByRole("heading", { name: "Report run-a" })).toBeVisible();
  await page.getByRole("combobox", { name: /研究历史|Research history/i }).selectOption("run-b");
  await expect(page.getByRole("heading", { name: "Report run-b" })).toBeVisible();
  f.releaseFirst();
  await expect(page.getByRole("tab", { name: "User-edited" })).toBeEnabled();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Report Markdown" })).toHaveValue(original);
  await expect(page.getByText("A saved edit", { exact: true })).toHaveCount(0);
});
test("late save response stays with the run that initiated it", async ({ context, page }) => {
  const f = await fixture(context);
  f.releaseFirst();
  const pendingSave = gate();
  let saveStarted!: () => void;
  const started = new Promise<void>((resolve) => { saveStarted = resolve; });
  await page.route("**/run-a/report-edit", async (route) => {
    if (route.request().method() === "PUT") { saveStarted(); await pendingSave.promise; }
    await route.fallback();
  });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("textbox", { name: "Report Markdown" }).fill("# A pending save");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await started;
  await page.getByRole("combobox", { name: /研究历史|Research history/i }).selectOption("run-b");
  await expect(page.getByRole("heading", { name: "Report run-b" })).toBeVisible();
  pendingSave.release();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Report Markdown" })).toHaveValue(original);
  await expect(page.getByText("A pending save", { exact: true })).toHaveCount(0);
});

test("report edit load failure offers retry without enabling editing", async ({ context, page }) => {
  const f = await fixture(context);
  f.releaseFirst();
  let fail = true;
  await page.route("**/run-a/report-edit", async (route) => {
    if (route.request().method() === "GET" && fail) return json(route, { error: { code: "temporary", message: "Temporarily unavailable" } }, 503);
    await route.fallback();
  });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Temporarily unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toBeVisible();
});


test("first-save base conflict leaves the draft intact and writes no edition", async ({ context, page }) => {
  const f = await fixture(context);
  f.releaseFirst();
  await page.route("**/run-a/report-edit", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const payload = route.request().postDataJSON();
    expect(payload.originalArtifactId).toBe("artifact-run-a");
    expect(payload.originalSha256).toBe(sha);
    expect(payload.expectedVersion).toBe(0);
    return json(route, { error: { code: "report_edit_base_conflict", message: "The original report has changed. Copy your draft before reloading the run." } }, 409);
  });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("textbox", { name: "Report Markdown" }).fill("# Preserve my old-base draft");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Copy your draft" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Report Markdown" })).toHaveValue("# Preserve my old-base draft");
  expect(f.edits.size).toBe(0);
});
