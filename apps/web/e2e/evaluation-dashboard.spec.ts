import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const workspaceId = "e2e-evaluation-workspace";
const now = "2026-07-27T00:00:00Z";
const suiteId = "suite-1";
const researchId = "evaluation-research";
const quickId = "evaluation-quick";
const ratio = (value: number | null, sampleCount = 6) => ({ value, sampleCount, notEvaluableReason: value === null ? "not_measured" : null });

const workspace = {
  id: workspaceId, name: "Evaluation Workspace", description: null, role: "owner", systemPrompt: "Evidence only.",
  retrievalTopK: 6, chunkSize: 1200, embeddingProvider: "openai", embeddingModel: "embedding",
  embeddingDimensions: 1024, embeddingVersion: "v1", generationProvider: "openai", generationModel: "gpt-test",
  assetCount: 1, noteCount: 0, threadCount: 0, createdAt: now, updatedAt: now,
};
const asset = {
  id: "asset-1", workspaceId, kind: "pdf", title: "Fixture", sourceFilename: "fixture.pdf", mimeType: "application/pdf",
  byteSize: 100, status: "ready", currentProcessingGeneration: 1, currentIndexVersion: 1, lastErrorCode: null,
  lastErrorMessage: null, createdAt: now, updatedAt: now,
};
const suite = { id: suiteId, suiteKey: "r100", version: 1, title: "Evidence Research", fixtureManifestSha256: "a".repeat(64), scorerVersion: "r100-v1", caseCount: 6, createdAt: now };

function evaluation(id: string, mode: "quick" | "research") {
  const research = mode === "research";
  return {
    id, workspaceId, suiteId, mode, status: "completed", researchRunId: research ? "research-run-1" : null,
    baselineEvaluationRunId: research ? quickId : null, fixtureManifestSha256: "a".repeat(64), assetScopeSha256: "b".repeat(64),
    provider: "openai", model: "gpt-test", providerProfileSha256: "c".repeat(64), scorerVersion: "r100-v1",
    workflowVersionId: research ? "research-workflow-v1" : null, promptBindingSha256: research ? "d".repeat(64) : null,
    wallTimeMs: research ? 4200 : 1600, providerCalls: research ? 9 : 1, inputTokens: research ? 4800 : 900,
    outputTokens: research ? 1300 : 350, cost: { currency: "USD", amountMicros: research ? 320000 : 80000 },
    parallelSpeedup: research ? 2.35 : null, retryRate: ratio(research ? 0.11 : 0), recoveryRate: ratio(research ? 1 : null, research ? 1 : 0),
    claimSupportRate: ratio(research ? 0.92 : 0.74), evidenceRecall: ratio(research ? 0.88 : 0.63),
    evidencePrecision: ratio(research ? 0.84 : 0.69), locatorAccuracy: ratio(research ? 0.96 : 0.82),
    conflictDetectionRate: ratio(research ? 1 : 0.5, 2), refusalCorrectness: ratio(research ? 1 : 0.5, 2),
    engineeringGate: "pass", modelQualityGate: "not_evaluable", userValueGate: "not_evaluable",
    sourceReportSha256: (research ? "e" : "f").repeat(64), createdAt: research ? "2026-07-27T02:00:00Z" : "2026-07-27T01:00:00Z",
    completedAt: research ? "2026-07-27T02:00:05Z" : "2026-07-27T01:00:02Z", failure: null,
  };
}
const caseResult = {
  id: "case-result-1", caseKey: "compare-01", caseType: "comparison", expectedDisposition: "answer", observedDisposition: "answer",
  claimSupportRate: ratio(1, 2), evidenceRecall: ratio(1, 2), evidencePrecision: ratio(0.8, 2), locatorAccuracy: ratio(1, 2),
  conflictDetectionRate: ratio(1, 1), refusalCorrectness: ratio(null, 0), wallTimeMs: 680, providerCalls: 2,
  cost: { currency: "USD", amountMicros: 45000 }, unsupportedClaimCount: 0, humanInterventionCount: 0, humanWaitMs: 0, failureCode: null,
};

async function mockWorkspace(page: Page, role: "owner" | "member" = "owner") {
  let evaluationRequests = 0;
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { userId: "e2e-user", email: "eval@example.com", name: "Evaluation E2E", avatarUrl: null } }) }));
  await page.route("**/api/workspaces", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ ...workspace, role }], nextCursor: null }) }));
  for (const [suffix, body] of [
    ["assets", { items: [asset], nextCursor: null }], ["threads", { items: [], nextCursor: null }],
    ["notes", { items: [], nextCursor: null }], ["tags", { items: [], nextCursor: null }],
  ] as const) {
    await page.route(`**/api/workspaces/${workspaceId}/${suffix}`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }));
  }
  await page.route(`**/api/workspaces/${workspaceId}/evaluation-suites**`, (route) => {
    evaluationRequests += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [suite] }) });
  });
  await page.route(`**/api/workspaces/${workspaceId}/evaluations**`, (route) => {
    evaluationRequests += 1;
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith(`/evaluations/${researchId}/cases/compare-01`)) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ case: { ...caseResult, claims: [{ id: "claim-result-1", claimKey: "claim-01", supportResult: "supported", locatorResult: "accurate", conflictResult: "detected", expectedEvidenceCount: 2, observedEvidenceCount: 2, failureCode: null }] } }) });
    }
    if (pathname.endsWith(`/evaluations/${researchId}/cases`)) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [caseResult] }) });
    }
    if (pathname.endsWith(`/evaluations/${researchId}`)) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ evaluation: evaluation(researchId, "research") }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [evaluation(quickId, "quick"), evaluation(researchId, "research")], nextCursor: null }) });
  });
  return () => evaluationRequests;
}

for (const viewport of [{ name: "desktop", width: 1440, height: 900 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`Evaluation dashboard preserves evidence layers on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockWorkspace(page);
    await page.goto(`/workspaces/${workspaceId}`);
    await page.getByRole("tab", { name: /配置|settings/i }).click();
    await page.getByRole("tab", { name: /评测|evaluation/i }).click();

    await expect(page.getByText(/工程门|Engineering gate/i)).toBeVisible();
    await expect(page.getByText(/模型质量门|Model quality gate/i)).toBeVisible();
    await expect(page.getByText(/用户价值门|User value gate/i)).toBeVisible();
    await expect(page.getByText(/未评测|Not evaluable/i).first()).toBeVisible();
    await expect(page.getByText(/结论支持率|Claim support/i).first()).toBeVisible();
    await expect(page.getByText("research-workflow-v1", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "compare-01" }).click();
    await expect(page.getByText("claim-01")).toBeVisible();
    await page.getByRole("heading", { name: /^评测$|^Evaluation$/i }).scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.resolve(process.cwd(), `../../docs/evals/artifacts/r700-v1/r700-dashboard-${viewport.name}.png`), fullPage: true });
  });
}

test("Workspace members do not see or request the Evaluation dashboard", async ({ page }) => {
  const requests = await mockWorkspace(page, "member");
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await expect(page.getByRole("tab", { name: /评测|evaluation/i })).toHaveCount(0);
  expect(requests()).toBe(0);
});
