import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const workspaceId = "e2e-research-workspace";
const assetId = "e2e-research-asset";
const runId = "e2e-research-run";
const decisionId = "e2e-plan-decision";
const now = "2026-07-27T00:00:00Z";

const researchQuestion = "Compare the frozen evidence and identify conflicts.";
const workflowVersionId = "research-workflow-v1";
const plannerPromptVersionId = "planner-prompt-v1";
const planningSnapshotSha = "e".repeat(64);
const executionSnapshotId = "e2e-research-execution";
const executionSnapshotSha = "f".repeat(64);
const planArtifactId = "plan-artifact";
const planArtifactSha = "a".repeat(64);

function providerSnapshot(generationModel: string) {
  return {
    generationProvider: "scripted",
    generationModel,
    embeddingProvider: "scripted",
    embeddingModel: "fixture-embedding",
    embeddingVersion: "v1",
    retrievalStrategy: "hybrid",
    retrievalTopK: 6,
    providerConfigFingerprint: "a".repeat(64),
    pricingVersion: null,
    dataBoundaryPolicyVersion: "v1",
  };
}

function frozenAssetScope() {
  return {
    frozenAt: now,
    assets: [{
      assetId,
      assetKind: "pdf",
      assetTitle: "Research Fixture",
      processingGeneration: 1,
      indexVersion: 1,
    }],
  };
}

function planningBudgetLimits() {
  return {
    maxProviderCalls: 2,
    maxInputTokens: 32000,
    maxOutputTokens: 8000,
    maxCost: { currency: "USD", amountMicros: 500000 },
    plannerTimeoutSeconds: 300,
    providerTimeoutSeconds: 120,
    maxPlannerAttempts: 3,
  };
}

function researchBudgetLimits() {
  return {
    maxProviderCalls: 32,
    maxToolCalls: 64,
    maxInputTokens: 250000,
    maxOutputTokens: 64000,
    maxCost: { currency: "USD", amountMicros: 5000000 },
    maxParallelResearchers: 3,
    runTimeoutSeconds: 1800,
    stepTimeoutSeconds: 300,
    providerTimeoutSeconds: 120,
    maxAttemptsPerStep: 3,
  };
}

function researchPromptVersions() {
  return [
    { nodeKey: "planner", promptVersionId: plannerPromptVersionId },
    { nodeKey: "researchers", promptVersionId: "researchers-prompt-v1" },
    { nodeKey: "verifier", promptVersionId: "verifier-prompt-v1" },
    { nodeKey: "critic", promptVersionId: "critic-prompt-v1" },
    { nodeKey: "synthesizer", promptVersionId: "synthesizer-prompt-v1" },
  ];
}

function planningExecutionSnapshot(generationModel: string) {
  return {
    workflowVersionId,
    plannerPromptVersionId,
    provider: providerSnapshot(generationModel),
    budgetPolicyVersion: "research-budget-v1",
    retryPolicyVersion: "research-retry-v1",
    limits: planningBudgetLimits(),
  };
}

function executionConfigSnapshot(generationModel: string) {
  return {
    workflowVersionId,
    promptVersions: researchPromptVersions(),
    provider: providerSnapshot(generationModel),
    budgetPolicyVersion: "research-budget-v1",
    retryPolicyVersion: "research-retry-v1",
    limits: researchBudgetLimits(),
  };
}

function planningInputSnapshot(proposedGenerationModel: string) {
  return {
    revisionNumber: 1,
    question: researchQuestion,
    requestedAssetScope: { mode: "all_ready" },
    planningAssetScope: frozenAssetScope(),
    planningExecution: planningExecutionSnapshot("fixture-planning-generation"),
    proposedResearchExecution: executionConfigSnapshot(proposedGenerationModel),
    snapshotSha256: planningSnapshotSha,
    frozenAt: now,
  };
}

function approvedResearchExecutionSnapshot() {
  return {
    id: executionSnapshotId,
    inputVersion: 1,
    approvalDecisionId: decisionId,
    approvedPlanArtifactId: planArtifactId,
    approvedPlanArtifactSha256: planArtifactSha,
    question: researchQuestion,
    frozenAssetScope: frozenAssetScope(),
    execution: executionConfigSnapshot("fixture-frozen-generation"),
    snapshotSha256: executionSnapshotSha,
    createdAt: now,
  };
}

const workspace = {
  id: workspaceId,
  name: "Research Evidence Workspace",
  description: null,
  role: "owner",
  systemPrompt: "Answer only from evidence.",
  retrievalTopK: 6,
  chunkSize: 1200,
  embeddingProvider: "scripted",
  embeddingModel: "fixture-embedding",
  embeddingDimensions: 1024,
  embeddingVersion: "v1",
  generationProvider: "scripted",
  generationModel: "fixture-generation",
  assetCount: 1,
  noteCount: 0,
  threadCount: 0,
  createdAt: now,
  updatedAt: now,
};

const asset = {
  id: assetId,
  workspaceId,
  kind: "pdf",
  title: "Research Fixture",
  sourceFilename: "research-fixture.pdf",
  mimeType: "application/pdf",
  byteSize: 4096,
  status: "ready",
  currentProcessingGeneration: 1,
  currentIndexVersion: 1,
  lastErrorCode: null,
  lastErrorMessage: null,
  createdAt: now,
  updatedAt: now,
};

function summary(status: string, stateVersion: number, currentEventSeq: number) {
  return {
    id: runId,
    workspaceId,
    createdByUserId: "e2e-user",
    question: researchQuestion,
    status,
    stateVersion,
    requestedAssetScope: { mode: "all_ready" },
    frozenAssetCount: 1,
    costCurrency: "USD",
    currentPlanRevisionNumber: 1,
    currentEventSeq,
    estimatedCost: null,
    consumedCost: { currency: "USD", amountMicros: 0 },
    createdAt: now,
    updatedAt: now,
    finishedAt: null,
  };
}

function detail(status: string, stateVersion: number, currentEventSeq: number) {
  const approved = status === "queued";
  return {
    ...summary(status, stateVersion, currentEventSeq),
    frozenAssetScope: frozenAssetScope(),
    plan: {
      version: 1,
      status: approved ? "approved" : "proposed",
      inputSnapshot: planningInputSnapshot("fixture-revision-generation"),
      summary: "Compare the source claims, verify support, and report unresolved conflicts.",
      subproblems: [
        { id: "subproblem-1", order: 0, question: "What claims are directly supported?", assetIds: [assetId], expectedEvidence: ["Typed locators"] },
        { id: "subproblem-2", order: 1, question: "Which claims conflict?", assetIds: [assetId], expectedEvidence: ["Contradicting excerpts"] },
      ],
      knownGaps: [],
      estimatedProviderCalls: 3,
      estimatedInputTokens: null,
      estimatedOutputTokens: null,
      estimatedCost: null,
      planningUsage: {
        providerCalls: 1,
        toolCalls: 0,
        inputTokens: 0,
        outputTokens: 0,
        cost: { currency: "USD", amountMicros: 0 },
        usageFinal: true,
        measuredAt: now,
      },
      createdAt: now,
      approvedAt: approved ? now : null,
    },
    researchExecution: approved ? approvedResearchExecutionSnapshot() : null,
    planningUsage: {
      providerCalls: 1,
      toolCalls: 0,
      inputTokens: 0,
      outputTokens: 0,
      cost: { currency: "USD", amountMicros: 0 },
      usageFinal: true,
      measuredAt: now,
    },
    researchUsage: null,
    steps: [
      {
        id: "planner-step",
        runId,
        kind: "planner",
        key: "planner",
        branchKey: null,
        status: "succeeded",
        stateVersion: 2,
        currentAttemptNumber: 1,
        maxAttempts: 2,
        dependsOnStepIds: [],
        evidenceCount: 0,
        providerCalls: 1,
        toolCalls: 0,
        startedAt: now,
        finishedAt: now,
        failure: null,
      },
      {
        id: "plan-gate-step",
        runId,
        kind: "plan_approval_gate",
        key: "plan-gate",
        branchKey: null,
        status: approved ? "succeeded" : "waiting",
        stateVersion: approved ? 3 : 2,
        currentAttemptNumber: 0,
        maxAttempts: 1,
        dependsOnStepIds: ["planner-step"],
        evidenceCount: 0,
        providerCalls: 0,
        toolCalls: 0,
        startedAt: now,
        finishedAt: approved ? now : null,
        failure: null,
      },
    ],
    pendingDecisions: approved ? [] : [{
      id: decisionId,
      runId,
      gateStepId: "plan-gate-step",
      type: "plan_approval",
      status: "pending",
      requestNumber: 1,
      stateVersion: 1,
      inputArtifactId: planArtifactId,
      inputArtifactSha256: planArtifactSha,
      inputSnapshotSha256: planningSnapshotSha,
      requestedAt: now,
      expiresAt: null,
      decidedByUserId: null,
      action: null,
      comment: null,
      decidedAt: null,
    }],
    submittedDecisions: [],
    artifactCount: 1,
    failure: null,
    startedAt: approved ? now : null,
    cancelRequestedAt: null,
    cancelledAt: null,
  };
}

type MockResearchOptions = {
  sessionUserId?: string;
  initialCreated?: boolean;
  scenario?: "plan" | "conflict" | "malformed";
};

const conflictArtifactId = "e2e-conflict-artifact";
const conflictArtifactSha = "c".repeat(64);
const conflictDecisionId = "e2e-conflict-decision";
const conflictArtifact = {
  id: conflictArtifactId,
  runId,
  stepId: "critic-step",
  kind: "conflict_report",
  visibility: "user",
  logicalKey: "conflict-report",
  schemaVersion: "1",
  supersedesArtifactId: null,
  mediaType: "application/json",
  byteSize: 84,
  sha256: conflictArtifactSha,
  evidenceCount: 1,
  retentionClass: "workspace_lifetime",
  expiresAt: null,
  createdAt: now,
};

function conflictDetail() {
  const run = detail("awaiting_human_decision", 8, 8);
  run.plan.status = "approved";
  run.pendingDecisions = [{
    id: conflictDecisionId,
    runId,
    gateStepId: "conflict-gate-step",
    type: "conflict_resolution",
    status: "pending",
    requestNumber: 1,
    stateVersion: 1,
    inputArtifactId: conflictArtifactId,
    inputArtifactSha256: conflictArtifactSha,
    inputSnapshotSha256: "d".repeat(64),
    requestedAt: now,
    expiresAt: null,
    decidedByUserId: null,
    action: null,
    comment: null,
    decidedAt: null,
  }];
  run.artifactCount = 2;
  return run;
}

function malformedDetail() {
  const run = detail("awaiting_plan_approval", 3, 3);
  run.researchExecution = null;
  // Intentionally incomplete selected frozen provider; cast keeps the payload malformed for fail-closed UI.
  run.plan.inputSnapshot = {
    ...planningInputSnapshot("fixture-revision-generation"),
    proposedResearchExecution: {
      ...executionConfigSnapshot("fixture-revision-generation"),
      provider: { generationProvider: "scripted" },
    },
  } as unknown as typeof run.plan.inputSnapshot;
  return run;
}

async function mockWorkspace(page: Page, options: MockResearchOptions = {}) {
  const scenario = options.scenario ?? "plan";
  const sessionUserId = options.sessionUserId ?? "e2e-user";
  let created = options.initialCreated ?? false;
  let approved = false;
  const createRequests: Array<{ body: Record<string, unknown>; idempotencyKey: string | null }> = [];
  const approvalRequests: Array<{ body: Record<string, unknown>; idempotencyKey: string | null }> = [];

  await page.route("**/api/auth/session", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ user: { userId: sessionUserId, email: "research@example.com", name: "Research E2E", avatarUrl: null } }),
  }));
  await page.route("**/api/workspaces", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [workspace], nextCursor: null }),
  }));
  await page.route(`**/api/workspaces/${workspaceId}/assets`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [asset], nextCursor: null }),
  }));
  await page.route(`**/api/workspaces/${workspaceId}/threads`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [], nextCursor: null }),
  }));
  await page.route(`**/api/workspaces/${workspaceId}/notes`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [], nextCursor: null }),
  }));
  await page.route(`**/api/workspaces/${workspaceId}/tags`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [], nextCursor: null }),
  }));
  await page.route(`**/api/workspaces/${workspaceId}/research-runs**`, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const base = `/api/workspaces/${workspaceId}/research-runs`;

    if (pathname === base && request.method() === "POST") {
      createRequests.push({
        body: request.postDataJSON() as Record<string, unknown>,
        idempotencyKey: request.headers()["idempotency-key"] ?? null,
      });
      created = true;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ run: { ...detail("planning", 1, 1), plan: null, pendingDecisions: [], steps: [] } }) });
      return;
    }
    if (pathname === base) {
      const items = created
        ? [summary(
            scenario === "conflict" ? "awaiting_human_decision" : approved ? "queued" : "awaiting_plan_approval",
            scenario === "conflict" ? 8 : approved ? 4 : 3,
            scenario === "conflict" ? 8 : approved ? 4 : 3,
          )]
        : [];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, nextCursor: null }) });
      return;
    }
    if (pathname.endsWith(`/plan-decisions/${decisionId}`)) {
      approvalRequests.push({
        body: request.postDataJSON() as Record<string, unknown>,
        idempotencyKey: request.headers()["idempotency-key"] ?? null,
      });
      approved = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ decision: { id: decisionId }, run: detail("queued", 4, 4) }) });
      return;
    }
    if (pathname.endsWith(`/artifacts/${conflictArtifactId}/content`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ summary: "Two supported claims conflict and require a decision." }),
      });
      return;
    }
    if (pathname.endsWith(`/artifacts/${conflictArtifactId}`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          artifact: {
            ...conflictArtifact,
            workflowVersionId: "research-workflow-v1",
            promptVersions: [{ nodeKey: "critic", promptVersionId: "critic-v1" }],
            directPromptVersionId: "critic-v1",
            claims: [{
              id: "conflicted-claim",
              text: "The source reports both 12% and 18% for the same frozen metric.",
              verificationStatus: "supported",
              conflictStatus: "conflicted",
              sectionKind: "conflict",
              evidence: [{ evidenceLocatorId: "evidence-1", relationship: "supports", order: 0 }],
            }],
            evidence: [{
              evidenceLocatorId: "evidence-1",
              assetId,
              assetKind: "pdf",
              assetTitle: "Research Fixture",
              sourceAvailable: true,
              excerpt: "The metric is reported as 12% in one section and 18% in another.",
              locator: { kind: "pdf_page", version: 1, pageNumber: 4 },
              sourceVersions: { parserVersion: "pdf-v1", processingGeneration: 1, representationId: "original", indexVersion: 1 },
            }],
          },
        }),
      });
      return;
    }
    if (pathname.endsWith("/artifacts")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: scenario === "conflict" ? [conflictArtifact] : [] }),
      });
      return;
    }
    if (pathname.endsWith("/events")) {
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": keepalive\n\n" });
      return;
    }
    if (pathname === `${base}/${runId}`) {
      const run = scenario === "conflict"
        ? conflictDetail()
        : scenario === "malformed"
          ? malformedDetail()
          : detail(approved ? "queued" : "awaiting_plan_approval", approved ? 4 : 3, approved ? 4 : 3);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ run }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "not_found", message: "Not found" } }) });
  });

  return { createRequests, approvalRequests };
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`Research mode stays explicit and usable on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const requests = await mockWorkspace(page);
    await page.goto(`/workspaces/${workspaceId}`);

    const quickTab = page.getByRole("tab", { name: /快速问答|quick/i });
    const researchTab = page.getByRole("tab", { name: /深度研究|research/i });
    await expect(quickTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("textbox", { name: /针对当前工作区|ask about ready assets/i })).toBeDisabled();

    await researchTab.click();
    await expect(researchTab).toHaveAttribute("aria-selected", "true");
    const composer = page.getByPlaceholder(/多步骤查证|multi-step evidence/i);
    await expect(composer).toBeEnabled();
    await composer.fill(researchQuestion);
    await page.getByRole("button", { name: /开始研究|start research/i }).click();

    await expect(page.getByRole("heading", { name: /Compare the frozen evidence/i })).toBeVisible();
    await expect(page.getByText(/研究计划 v1|Research plan v1/i)).toBeVisible();
    await expect(page.getByText(/计划 revision 冻结快照|Proposed plan revision snapshot/i)).toBeVisible();
    await expect(page.getByText("scripted / fixture-revision-generation", { exact: true })).toBeVisible();
    await expect(page.getByText(/制定研究计划|Draft research plan/i)).toBeVisible();
    await expect(page.getByText(/冻结范围|Frozen scope/i)).toBeVisible();
    await expect(page.getByText("Research Fixture", { exact: true })).toBeVisible();
    await expect(page.getByText(/预计模型调用|Estimated model calls/i)).toBeVisible();
    await expect(page.getByText(/暂无已知缺口|No known gaps/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /批准计划|approve plan/i })).toBeVisible();
    expect(requests.createRequests).toHaveLength(1);
    expect(requests.createRequests[0].idempotencyKey).toBeTruthy();
    expect(requests.createRequests[0].body).toMatchObject({
      question: researchQuestion,
      assetScope: { mode: "all_ready" },
    });

    await page.getByRole("button", { name: /批准计划|approve plan/i }).click();
    await expect(page.getByText(/已排队|Queued/i).first()).toBeVisible();
    await expect(page.getByText(/Run execution 冻结快照|Run execution snapshot/i)).toBeVisible();
    await expect(page.getByText("scripted / fixture-frozen-generation", { exact: true })).toBeVisible();
    expect(requests.approvalRequests).toHaveLength(1);
    expect(requests.approvalRequests[0].idempotencyKey).toBeTruthy();
    expect(requests.approvalRequests[0].body).toMatchObject({ action: "approve", revision: null });

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({
      path: path.resolve(process.cwd(), `../../docs/evals/artifacts/r500-v1/r500-web-${viewport.name}.png`),
      fullPage: true,
    });
  });
}


test("Research readers see the plan without creator-only controls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockWorkspace(page, { sessionUserId: "reader-user", initialCreated: true });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();

  await expect(page.getByText(/研究计划 v1|Research plan v1/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /批准计划|approve plan/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /修改计划|revise plan/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /取消研究|cancel research/i })).toHaveCount(0);
});

test("Conflict actions wait for the exact Decision-bound report", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockWorkspace(page, { initialCreated: true, scenario: "conflict" });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();

  await expect(page.getByText("The source reports both 12% and 18% for the same frozen metric.")).toBeVisible();
  await expect(page.getByText(/关联 1 条证据|1 linked evidence/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /排除冲突结论|exclude conflicted claims/i })).toBeVisible();
});

test("Malformed selected frozen profile stays unavailable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockWorkspace(page, { initialCreated: true, scenario: "malformed" });
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /深度研究|research/i }).click();

  await expect(page.getByText(/研究计划 v1|Research plan v1/i)).toBeVisible();
  await expect(page.getByText(/冻结 profile 不可用|Frozen profile unavailable/i)).toBeVisible();
  await expect(page.getByText(/计划 revision 冻结快照|Proposed plan revision snapshot/i)).toHaveCount(0);
  await expect(page.getByText(/Run execution 冻结快照|Run execution snapshot/i)).toHaveCount(0);
  await expect(page.getByText("scripted / fixture-revision-generation", { exact: true })).toHaveCount(0);
  await expect(page.getByText("scripted / fixture-planning-generation", { exact: true })).toHaveCount(0);
});
