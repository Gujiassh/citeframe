import { expect, test, type Page } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/**
 * V5-D D-WEB gap-closing coverage (mocked BFF, no live API secrets).
 *
 * Covers desktop (1440x1000) and mobile (390x844) primary mixed flows:
 * PDF + Image + Markdown asset list/kind labels, selected scope Quick Chat,
 * three-modality Citation open, Research start with selected scope, and
 * unavailable source fail-closed state.
 *
 * This is engineering/UI regression evidence. Full production-start live
 * mixed PDF+Image+Markdown still requires external standalone server + state
 * (see d-web-lane-report.md).
 */

const workspaceId = "e2e-v5d-mixed-workspace";
const pdfAssetId = "e2e-mixed-pdf";
const imageAssetId = "e2e-mixed-image";
const documentAssetId = "e2e-mixed-document";
const threadId = "e2e-mixed-thread";
const userMessageId = "e2e-mixed-user-message";
const assistantMessageId = "e2e-mixed-assistant-message";
const runId = "e2e-mixed-research-run";
const decisionId = "e2e-mixed-plan-decision";
const documentRepresentationId = "rep_document_normalized_fixture_v1";
const imageRepresentationId = "rep_image_caption_fixture_v1";
const now = "2026-08-11T00:00:00Z";

const repositoryRoot = path.resolve(process.cwd(), "../..");
const artifactRoot = path.resolve(
  process.env.PLAYWRIGHT_V5D_MIXED_ARTIFACT_DIR
    ?? path.join(repositoryRoot, "docs/evals/artifacts/v5d-20260811-01"),
);

const researchQuestion = "Summarize mixed PDF, image, and markdown evidence.";
const quickQuestion = "What do the three mixed assets say together?";

type DocumentFixture = {
  normalizedText: string;
  normalizedContentSha256: string;
  parserVersion: string;
  normalizationVersion: string;
  blocks: Array<{
    blockId: string;
    blockOrder: number;
    blockKind: string;
    headingLevel: number | null;
    headingPath: string[];
    charStart: number;
    charEnd: number;
    textSha256: string;
    text: string;
  }>;
};

function assetSummary(input: {
  id: string;
  kind: "pdf" | "image" | "document";
  title: string;
  sourceFilename: string;
  mimeType: string;
  byteSize: number;
}) {
  return {
    id: input.id,
    workspaceId,
    kind: input.kind,
    title: input.title,
    sourceFilename: input.sourceFilename,
    mimeType: input.mimeType,
    byteSize: input.byteSize,
    status: "ready",
    currentProcessingGeneration: 1,
    currentIndexVersion: 1,
    lastErrorCode: null,
    lastErrorMessage: null,
    createdAt: now,
    updatedAt: now,
  };
}

const pdfAsset = assetSummary({
  id: pdfAssetId,
  kind: "pdf",
  title: "Mixed PDF Fixture",
  sourceFilename: "pdf-coordinate-fixture.pdf",
  mimeType: "application/pdf",
  byteSize: 12_000,
});

const imageAsset = assetSummary({
  id: imageAssetId,
  kind: "image",
  title: "Mixed Image Fixture",
  sourceFilename: "image-coordinate-fixture.png",
  mimeType: "image/png",
  byteSize: 21_546,
});

const documentAsset = assetSummary({
  id: documentAssetId,
  kind: "document",
  title: "Mixed Markdown Fixture",
  sourceFilename: "markdown-note.md",
  mimeType: "text/markdown",
  byteSize: 114,
});

const assets = [pdfAsset, imageAsset, documentAsset];

const workspace = {
  id: workspaceId,
  name: "V5-D Mixed Workspace",
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
  assetCount: 3,
  noteCount: 0,
  threadCount: 1,
  createdAt: now,
  updatedAt: now,
};

const threadSummary = {
  id: threadId,
  workspaceId,
  title: "Mixed evidence thread",
  lastMessageAt: now,
  createdAt: now,
};

const pdfCitation = {
  id: "cit-mixed-pdf",
  messageId: assistantMessageId,
  citationIndex: 0,
  assetId: pdfAssetId,
  assetKind: "pdf",
  assetTitle: pdfAsset.title,
  sourceAvailable: true,
  excerpt: "PDF coordinate page one claim.",
  locator: { kind: "pdf_page", version: 1, pageNumber: 1 },
  sourceVersions: {
    parserVersion: "pdf-v1",
    processingGeneration: 1,
    representationId: "rep-pdf-original",
    indexVersion: 1,
  },
};

const imageCitation = {
  id: "cit-mixed-image",
  messageId: assistantMessageId,
  citationIndex: 1,
  assetId: imageAssetId,
  assetKind: "image",
  assetTitle: imageAsset.title,
  sourceAvailable: true,
  excerpt: "Image region latency observation.",
  locator: {
    kind: "image_region",
    version: 1,
    coordinateSpace: "image_normalized_top_left_v1",
    widthPixels: 1200,
    heightPixels: 800,
    orientationApplied: true,
    regions: [{ x: 0.066667, y: 0.2375, width: 0.566667, height: 0.525 }],
  },
  sourceVersions: {
    parserVersion: "image-caption-v1",
    processingGeneration: 1,
    representationId: imageRepresentationId,
    indexVersion: 1,
  },
};

const documentCitation = {
  id: "cit-mixed-document",
  messageId: assistantMessageId,
  citationIndex: 2,
  assetId: documentAssetId,
  assetKind: "document",
  assetTitle: documentAsset.title,
  sourceAvailable: true,
  excerpt: "Hello world paragraph.",
  locator: {
    kind: "document_anchor",
    version: 1,
    blockId: "docblk_4ee5160d6645659f098b1812f883d683",
    blockKind: "paragraph",
    headingPath: ["Intro"],
    charStart: 6,
    charEnd: 28,
    textSha256: "615bad435819abcd9488e2aaad0a623a9aaca67f299ace86224cc7fe6a4afc28",
    normalizationVersion: "document-normalization-v1",
  },
  sourceVersions: {
    parserVersion: "document-parser-v1",
    processingGeneration: 1,
    representationId: documentRepresentationId,
    indexVersion: 1,
  },
};

const unavailableCitation = {
  id: "cit-mixed-unavailable",
  messageId: assistantMessageId,
  citationIndex: 3,
  assetId: "e2e-deleted-asset",
  assetKind: "document",
  assetTitle: "Deleted Markdown",
  sourceAvailable: false,
  excerpt: "Historical snapshot only.",
  locator: {
    kind: "document_anchor",
    version: 1,
    blockId: "docblk_deleted",
    blockKind: "paragraph",
    headingPath: ["Gone"],
    charStart: 0,
    charEnd: 8,
    textSha256: "a".repeat(64),
    normalizationVersion: "document-normalization-v1",
  },
  sourceVersions: {
    parserVersion: "document-parser-v1",
    processingGeneration: 1,
    representationId: "rep-deleted",
    indexVersion: 1,
  },
};

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
    assets: assets.map((asset) => ({
      assetId: asset.id,
      assetKind: asset.kind,
      assetTitle: asset.title,
      processingGeneration: 1,
      indexVersion: 1,
    })),
  };
}

function planningBudgetLimits() {
  return {
    maxProviderCalls: 2,
    maxInputTokens: 32000,
    maxOutputTokens: 8000,
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
    maxParallelResearchers: 3,
    runTimeoutSeconds: 1800,
    stepTimeoutSeconds: 300,
    providerTimeoutSeconds: 120,
    maxAttemptsPerStep: 3,
  };
}

function researchPromptVersions() {
  return [
    { nodeKey: "planner", promptVersionId: "planner-prompt-v1" },
    { nodeKey: "researchers", promptVersionId: "researchers-prompt-v1" },
    { nodeKey: "verifier", promptVersionId: "verifier-prompt-v1" },
    { nodeKey: "critic", promptVersionId: "critic-prompt-v1" },
    { nodeKey: "synthesizer", promptVersionId: "synthesizer-prompt-v1" },
  ];
}

function planningExecutionSnapshot(generationModel: string) {
  return {
    workflowVersionId: "research-workflow-v1",
    plannerPromptVersionId: "planner-prompt-v1",
    provider: providerSnapshot(generationModel),
    budgetPolicyVersion: "research-budget-v1",
    retryPolicyVersion: "research-retry-v1",
    limits: planningBudgetLimits(),
  };
}

function executionConfigSnapshot(generationModel: string) {
  return {
    workflowVersionId: "research-workflow-v1",
    promptVersions: researchPromptVersions(),
    provider: providerSnapshot(generationModel),
    budgetPolicyVersion: "research-budget-v1",
    retryPolicyVersion: "research-retry-v1",
    limits: researchBudgetLimits(),
  };
}

function planningInputSnapshot() {
  return {
    revisionNumber: 1,
    question: researchQuestion,
    requestedAssetScope: {
      mode: "selected",
      assetIds: [pdfAssetId, imageAssetId, documentAssetId],
    },
    planningAssetScope: frozenAssetScope(),
    planningExecution: planningExecutionSnapshot("fixture-planning-generation"),
    proposedResearchExecution: executionConfigSnapshot("fixture-revision-generation"),
    snapshotSha256: "e".repeat(64),
    frozenAt: now,
  };
}

function researchDetail(status: string, stateVersion: number, currentEventSeq: number) {
  const approved = status === "queued";
  return {
    id: runId,
    workspaceId,
    createdByUserId: "e2e-mixed-user",
    question: researchQuestion,
    status,
    stateVersion,
    requestedAssetScope: {
      mode: "selected",
      assetIds: [pdfAssetId, imageAssetId, documentAssetId],
    },
    frozenAssetCount: 3,
    currentPlanRevisionNumber: 1,
    currentEventSeq,
    createdAt: now,
    updatedAt: now,
    finishedAt: null,
    frozenAssetScope: frozenAssetScope(),
    plan: {
      version: 1,
      status: approved ? "approved" : "proposed",
      inputSnapshot: planningInputSnapshot(),
      summary: "Compare PDF, image, and markdown claims.",
      subproblems: [
        {
          id: "subproblem-1",
          order: 0,
          question: "What does each modality claim?",
          assetIds: [pdfAssetId, imageAssetId, documentAssetId],
          expectedEvidence: ["Typed locators"],
        },
      ],
      knownGaps: [],
      estimatedProviderCalls: 3,
      estimatedInputTokens: null,
      estimatedOutputTokens: null,
      planningUsage: {
        providerCalls: 1,
        toolCalls: 0,
        inputTokens: 0,
        outputTokens: 0,
        usageFinal: true,
        measuredAt: now,
        usageSource: "actual",
      },
      createdAt: now,
      approvedAt: approved ? now : null,
    },
    researchExecution: approved
      ? {
          id: "e2e-mixed-execution",
          inputVersion: 1,
          approvalDecisionId: decisionId,
          approvedPlanArtifactId: "plan-artifact",
          approvedPlanArtifactSha256: "a".repeat(64),
          question: researchQuestion,
          frozenAssetScope: frozenAssetScope(),
          execution: executionConfigSnapshot("fixture-frozen-generation"),
          snapshotSha256: "f".repeat(64),
          createdAt: now,
        }
      : null,
    planningUsage: {
      providerCalls: 1,
      toolCalls: 0,
      inputTokens: 0,
      outputTokens: 0,
      usageFinal: true,
      measuredAt: now,
      usageSource: "actual",
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
    pendingDecisions: approved
      ? []
      : [{
          id: decisionId,
          runId,
          gateStepId: "plan-gate-step",
          type: "plan_approval",
          status: "pending",
          requestNumber: 1,
          stateVersion: 1,
          inputArtifactId: "plan-artifact",
          inputArtifactSha256: "a".repeat(64),
          inputSnapshotSha256: "e".repeat(64),
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

function researchSummary(status: string, stateVersion: number, currentEventSeq: number) {
  return {
    id: runId,
    workspaceId,
    createdByUserId: "e2e-mixed-user",
    question: researchQuestion,
    status,
    stateVersion,
    requestedAssetScope: {
      mode: "selected",
      assetIds: [pdfAssetId, imageAssetId, documentAssetId],
    },
    frozenAssetCount: 3,
    currentPlanRevisionNumber: 1,
    currentEventSeq,
    createdAt: now,
    updatedAt: now,
    finishedAt: null,
  };
}

async function loadDocumentFixture(): Promise<DocumentFixture> {
  return JSON.parse(
    await readFile(
      path.join(repositoryRoot, "docs/fixtures/document-modality/markdown-note.fixture.json"),
      "utf8",
    ),
  ) as DocumentFixture;
}

async function ensureSidebarOpen(page: Page, mobile: boolean): Promise<void> {
  if (!mobile) return;
  const firstAsset = page.locator(`[data-asset-id="${pdfAssetId}"]`);
  if (await firstAsset.isVisible().catch(() => false)) {
    return;
  }
  const expand = page.getByRole("button", { name: /展开侧边栏|expand sidebar/i });
  await expect(expand).toBeVisible({ timeout: 15_000 });
  await expand.click();
  await expect(firstAsset).toBeVisible({ timeout: 30_000 });
}

async function closeMobileNavigation(page: Page): Promise<void> {
  // Mobile drawer uses a full-screen overlay labeled "关闭导航".
  const closeNavigation = page.getByRole("button", {
    name: /关闭导航|关闭导航栏|close navigation/i,
  });
  if (await closeNavigation.count()) {
    await closeNavigation.first().click({ force: true });
  }
  const collapse = page.getByRole("button", { name: /收起侧边栏|collapse sidebar/i });
  if (await collapse.isVisible().catch(() => false)) {
    await collapse.click();
  }
  await expect(
    page.getByRole("button", { name: /关闭导航|关闭导航栏|close navigation/i }),
  ).toHaveCount(0, { timeout: 10_000 });
}

async function closeEvidencePanel(page: Page): Promise<void> {
  const panel = page.locator("[data-evidence-panel]");
  if (await panel.count()) {
    await panel.getByRole("button", { name: /关闭证据面板|close evidence/i }).click();
    await expect(panel).toHaveCount(0);
  }
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const metrics = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewportWidth + 1);
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewportWidth + 1);
}

async function mockMixedWorkspace(page: Page, documentFixture: DocumentFixture) {
  const chatRequests: Array<Record<string, unknown>> = [];
  const researchCreateRequests: Array<Record<string, unknown>> = [];
  let researchCreated = false;
  let researchApproved = false;
  let chatMessages: unknown[] = [];

  const pdfBytes = await readFile(
    path.join(repositoryRoot, "docs/fixtures/evidence-contract/pdf-coordinate-fixture.pdf"),
  );
  const imageBytes = await readFile(
    path.join(repositoryRoot, "docs/fixtures/evidence-contract/image-coordinate-fixture.png"),
  );

  const documentContent = {
    assetId: documentAssetId,
    representationId: documentRepresentationId,
    processingGeneration: 1,
    format: "markdown",
    parserVersion: documentFixture.parserVersion,
    normalizationVersion: documentFixture.normalizationVersion,
    contentSha256: documentFixture.normalizedContentSha256,
    normalizedText: documentFixture.normalizedText,
    blocks: documentFixture.blocks.map((block) => ({
      blockId: block.blockId,
      blockOrder: block.blockOrder,
      blockKind: block.blockKind,
      headingLevel: block.headingLevel,
      headingPath: block.headingPath,
      charStart: block.charStart,
      charEnd: block.charEnd,
      textSha256: block.textSha256,
      text: block.text,
    })),
  };

  const documentDetail = {
    kind: "document",
    format: "markdown",
    parserVersion: documentFixture.parserVersion,
    normalizationVersion: documentFixture.normalizationVersion,
    representationId: documentRepresentationId,
    blockCount: documentFixture.blocks.length,
    headings: documentFixture.blocks
      .filter((block) => block.blockKind === "heading" && block.headingLevel !== null)
      .map((block) => ({
        blockId: block.blockId,
        level: block.headingLevel as number,
        text: block.text,
        order: block.blockOrder,
      })),
  };

  await page.route("**/api/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          userId: "e2e-mixed-user",
          email: "mixed@example.com",
          name: "Mixed E2E",
          avatarUrl: null,
        },
      }),
    });
  });

  await page.route("**/api/workspaces", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [workspace], nextCursor: null }),
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/assets`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: assets, nextCursor: null }),
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/assets/${pdfAssetId}/file**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: pdfBytes,
    });
  });
  await page.route(`**/api/workspaces/${workspaceId}/assets/${pdfAssetId}?*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: pdfAsset,
        detail: {
          kind: "pdf",
          pageCount: 1,
          pages: [{
            pageNumber: 1,
            text: "PDF coordinate page one claim.",
            charCount: 30,
            ocrBlocks: [],
          }],
        },
      }),
    });
  });
  await page.route(`**/api/workspaces/${workspaceId}/assets/${pdfAssetId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: pdfAsset,
        detail: {
          kind: "pdf",
          pageCount: 1,
          pages: [{
            pageNumber: 1,
            text: "PDF coordinate page one claim.",
            charCount: 30,
            ocrBlocks: [],
          }],
        },
      }),
    });
  });

  await page.route(
    `**/api/workspaces/${workspaceId}/assets/${imageAssetId}/representations/**/file**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: imageBytes,
      });
    },
  );
  await page.route(`**/api/workspaces/${workspaceId}/assets/${imageAssetId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: imageAsset,
        detail: {
          kind: "image",
          widthPixels: 1200,
          heightPixels: 800,
          orientationApplied: true,
        },
      }),
    });
  });

  await page.route(
    `**/api/workspaces/${workspaceId}/assets/${documentAssetId}/representations/${documentRepresentationId}/content`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(documentContent),
      });
    },
  );
  await page.route(`**/api/workspaces/${workspaceId}/assets/${documentAssetId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: documentAsset,
        detail: documentDetail,
      }),
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/threads`, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ thread: threadSummary }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [threadSummary], nextCursor: null }),
    });
  });

  await page.route(
    `**/api/workspaces/${workspaceId}/threads/${threadId}/messages`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ thread: threadSummary, messages: chatMessages }),
      });
    },
  );

  await page.route(`**/api/workspaces/${workspaceId}/notes`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], nextCursor: null }),
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/tags`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], nextCursor: null }),
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/chat/stream`, async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    chatRequests.push(payload);
    chatMessages = [
      {
        id: userMessageId,
        workspaceId,
        threadId,
        parentMessageId: null,
        role: "user",
        content: payload.question,
        status: "completed",
        modelProvider: null,
        modelName: null,
        createdAt: now,
        citations: [],
        inputEvidence: [],
      },
      {
        id: assistantMessageId,
        workspaceId,
        threadId,
        parentMessageId: userMessageId,
        role: "assistant",
        content: "Mixed PDF, image, and markdown evidence all support the answer.",
        status: "completed",
        modelProvider: "scripted",
        modelName: "fixture-generation",
        createdAt: now,
        citations: [pdfCitation, imageCitation, documentCitation, unavailableCitation],
        inputEvidence: [],
      },
    ];
    const body = [
      `event: meta\ndata: ${JSON.stringify({ threadId, userMessageId, assistantMessageId })}`,
      `event: delta\ndata: ${JSON.stringify({ text: "Mixed PDF, image, and markdown evidence all support the answer." })}`,
      `event: citations\ndata: ${JSON.stringify({ items: [pdfCitation, imageCitation, documentCitation, unavailableCitation] })}`,
      `event: done\ndata: ${JSON.stringify({ threadId, assistantMessageId })}`,
      "",
    ].join("\n\n");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      headers: { "cache-control": "no-cache" },
      body,
    });
  });

  await page.route(`**/api/workspaces/${workspaceId}/research-runs**`, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const base = `/api/workspaces/${workspaceId}/research-runs`;

    if (pathname === base && request.method() === "POST") {
      researchCreateRequests.push(request.postDataJSON() as Record<string, unknown>);
      researchCreated = true;
      // Return plan-ready detail so refresh after create immediately shows mixed frozen scope.
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          run: researchDetail("awaiting_plan_approval", 3, 3),
        }),
      });
      return;
    }
    if (pathname === base) {
      const items = researchCreated
        ? [researchSummary(
            researchApproved ? "queued" : "awaiting_plan_approval",
            researchApproved ? 4 : 3,
            researchApproved ? 4 : 3,
          )]
        : [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, nextCursor: null }),
      });
      return;
    }
    if (pathname.endsWith(`/plan-decisions/${decisionId}`)) {
      researchApproved = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ decision: { id: decisionId }, run: researchDetail("queued", 4, 4) }),
      });
      return;
    }
    if (pathname.endsWith("/events")) {
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": keepalive\n\n" });
      return;
    }
    if (pathname.endsWith("/artifacts")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
      return;
    }
    if (pathname === `${base}/${runId}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run: researchDetail(
            researchApproved ? "queued" : "awaiting_plan_approval",
            researchApproved ? 4 : 3,
            researchApproved ? 4 : 3,
          ),
        }),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "not_found", message: "Not found" } }),
    });
  });

  return { chatRequests, researchCreateRequests };
}

async function runMixedPrimaryFlow(
  page: Page,
  viewportName: "desktop" | "mobile",
  viewport: { width: number; height: number },
): Promise<Record<string, unknown>> {
  const documentFixture = await loadDocumentFixture();
  const mocks = await mockMixedWorkspace(page, documentFixture);
  const mobile = viewportName === "mobile";

  await page.setViewportSize(viewport);
  await page.goto(`/workspaces/${workspaceId}`, { waitUntil: "domcontentloaded" });
  await ensureSidebarOpen(page, mobile);

  // Asset list + exact kind labels for PDF/Image/Markdown.
  for (const asset of assets) {
    const row = page.locator(`[data-asset-id="${asset.id}"]`);
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText(asset.sourceFilename);
    await expect(row.locator("span.uppercase")).toHaveText(asset.kind);
  }

  // Selected-scope Quick Chat over all three ready modalities.
  for (const asset of assets) {
    await page.locator(`[data-asset-id="${asset.id}"] input[type="checkbox"]`).check();
  }
  await expect(page.getByText(/已选择 3 个资产|3 assets selected/i)).toBeVisible();

  if (mobile) {
    await closeMobileNavigation(page);
  }

  const quickComposer = page.getByRole("textbox", {
    name: /针对当前工作区的可用资产提问|Ask about ready assets in this workspace/i,
  });
  await expect(quickComposer).toBeEnabled({ timeout: 15_000 });
  await quickComposer.fill(quickQuestion);
  await page.getByRole("button", { name: /发送问题|Send question/i }).click();

  await expect(page.locator('[data-chat-message="assistant"]').last()).toContainText(
    "Mixed PDF, image, and markdown",
    { timeout: 30_000 },
  );
  expect(mocks.chatRequests).toHaveLength(1);
  expect(mocks.chatRequests[0]).toMatchObject({
    question: quickQuestion,
    assetScope: {
      mode: "selected",
      assetIds: [pdfAssetId, imageAssetId, documentAssetId],
    },
  });

  await expect(page.locator(`[data-citation-id="${pdfCitation.id}"]`)).toBeVisible();
  await expect(page.locator(`[data-citation-id="${imageCitation.id}"]`)).toBeVisible();
  await expect(page.locator(`[data-citation-id="${documentCitation.id}"]`)).toBeVisible();

  const unavailableButton = page.locator(`[data-citation-id="${unavailableCitation.id}"]`);
  await expect(unavailableButton).toBeVisible();
  await expect(unavailableButton).toBeDisabled();
  await expect(unavailableButton).toContainText(/源资产已删除|Source asset deleted/i);

  // PDF citation opens PDF viewer at page 1.
  await page.locator(`[data-citation-id="${pdfCitation.id}"]`).click();
  const pdfViewer = page.locator("[data-pdf-viewer]");
  await expect(pdfViewer).toBeVisible({ timeout: 30_000 });
  await expect(pdfViewer.locator("[data-pdf-page-input]")).toHaveValue("1");
  await expect(pdfViewer.locator("canvas").first()).toBeVisible({ timeout: 30_000 });
  await closeEvidencePanel(page);

  // Image citation opens image viewer with region overlay.
  await page.locator(`[data-citation-id="${imageCitation.id}"]`).click();
  const imageViewer = page.locator("[data-image-viewer]");
  await expect(imageViewer).toBeVisible({ timeout: 30_000 });
  await expect(imageViewer.locator("img")).toBeVisible();
  await expect(page.locator("[data-image-evidence-region]").first()).toBeVisible({ timeout: 15_000 });
  await closeEvidencePanel(page);

  // Document citation opens document viewer with exact block highlight.
  await page.locator(`[data-citation-id="${documentCitation.id}"]`).click();
  const documentViewer = page.locator('[data-document-viewer="true"]');
  await expect(documentViewer).toBeVisible({ timeout: 30_000 });
  await expect(documentViewer).toHaveAttribute("data-document-highlight-status", "ready");
  await expect(documentViewer).toHaveAttribute("data-document-generation", "1");
  await expect(
    page.locator(`[data-document-block-id="${documentCitation.locator.blockId}"]`),
  ).toBeVisible();
  await expect(
    page.locator(
      `[data-document-block-id="${documentCitation.locator.blockId}"] [data-document-highlight-range="true"]`,
    ),
  ).toBeVisible();
  await closeEvidencePanel(page);

  // Research primary path with the same selected mixed scope.
  await page.getByRole("tab", { name: /深度研究|research/i }).click();
  const researchComposer = page.getByPlaceholder(/多步骤查证|multi-step evidence/i);
  await expect(researchComposer).toBeEnabled();
  await researchComposer.fill(researchQuestion);
  await page.getByRole("button", { name: /开始研究|start research/i }).click();

  await expect(page.getByRole("heading", { name: researchQuestion })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/研究计划 v1|Research plan v1/i)).toBeVisible();
  await expect(page.getByText(/冻结范围|Frozen scope/i)).toBeVisible();
  // Research plan freezes the three titles in one definition string, not as
  // separate exact text nodes.
  await expect(
    page.getByText(
      new RegExp(
        `${pdfAsset.title}.*${imageAsset.title}.*${documentAsset.title}|` +
          `${pdfAsset.title}, ${imageAsset.title}, ${documentAsset.title}`,
      ),
    ),
  ).toBeVisible();
  expect(mocks.researchCreateRequests).toHaveLength(1);
  expect(mocks.researchCreateRequests[0]).toMatchObject({
    question: researchQuestion,
    assetScope: {
      mode: "selected",
      assetIds: [pdfAssetId, imageAssetId, documentAssetId],
    },
  });

  await assertNoHorizontalOverflow(page);

  await mkdir(artifactRoot, { recursive: true });
  const screenshotName = `v5d-mixed-primary-${viewportName}.png`;
  const screenshotPath = path.join(artifactRoot, screenshotName);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const result = {
    schemaVersion: "v5d-mixed-workspace-playwright-v1",
    productionStart: false,
    mockedBff: true,
    viewport: { name: viewportName, ...viewport },
    assets: assets.map((asset) => ({ id: asset.id, kind: asset.kind, mimeType: asset.mimeType })),
    quickChat: {
      requestCount: mocks.chatRequests.length,
      assetScope: mocks.chatRequests[0]?.assetScope ?? null,
    },
    research: {
      requestCount: mocks.researchCreateRequests.length,
      assetScope: mocks.researchCreateRequests[0]?.assetScope ?? null,
    },
    citations: {
      pdf: pdfCitation.id,
      image: imageCitation.id,
      document: documentCitation.id,
      unavailableDisabled: true,
    },
    screenshotPath: path.relative(repositoryRoot, screenshotPath),
    passed: true,
  };
  await writeFile(
    path.join(artifactRoot, `v5d-mixed-primary-${viewportName}.json`),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8",
  );
  return result;
}

test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);

test("V5-D mixed PDF+Image+Markdown primary flow on desktop 1440x1000", async ({ page }) => {
  const result = await runMixedPrimaryFlow(page, "desktop", { width: 1440, height: 1000 });
  expect(result.passed).toBeTruthy();
});

test("V5-D mixed PDF+Image+Markdown primary flow on mobile 390x844", async ({ page }) => {
  const result = await runMixedPrimaryFlow(page, "mobile", { width: 390, height: 844 });
  expect(result.passed).toBeTruthy();
});
