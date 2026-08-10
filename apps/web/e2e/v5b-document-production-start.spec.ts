import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/**
 * V5-B Document production-start E2E (integration lane).
 *
 * Production server must be started externally with the standalone entry used by
 * infra/docker/Dockerfile.web:
 *
 *   pnpm --dir apps/web build
 *   HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
 *   PLAYWRIGHT_STANDALONE_SERVER=1 \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
 *   PLAYWRIGHT_V5B_DOCUMENT_STATE_PATH=... \
 *   pnpm --dir apps/web exec playwright test e2e/v5b-document-production-start.spec.ts
 *
 * This file never sets PLAYWRIGHT_START_WEB and never fakes API behavior.
 */

type BrowserState = {
  schemaVersion: "v5b-document-browser-state-v1";
  email: string;
  password: string;
  workspaceId: string;
  documentAssetId?: string;
  citationId?: string;
  /** Required when citationId is supplied for historical citation reopen proof. */
  expectedProcessingGeneration?: number;
  expectedBlockId?: string;
  expectedCharStart?: number;
  expectedCharEnd?: number;
  expectedTextSha256?: string;
};

type FixtureOracle = {
  sourceSha256: string;
  mimeType: string;
  locatorKind: string;
  parserVersion: string;
  normalizationVersion: string;
  normalizedContentSha256: string;
  normalizedText: string;
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
    normalizationVersion: string;
  }>;
  locatorSnapshots: Array<Record<string, unknown>>;
  contentUnitKinds: string[];
};

type AssetSummary = {
  id: string;
  kind: string;
  mimeType: string;
  status: string;
  currentProcessingGeneration: number;
  title?: string;
  sourceFilename?: string;
  lastErrorCode?: string | null;
  lastErrorMessage?: string | null;
};

type JobStatus = {
  id: string;
  workspaceId: string;
  assetId: string;
  jobType: string;
  status: string;
  attemptCount: number;
  errorCode: string | null;
  errorMessage: string | null;
};

type UploadSessionResponse = {
  asset: AssetSummary;
  upload: {
    url: string;
    objectKey: string;
    headers?: Record<string, string>;
    method?: string;
  };
};

type FinalizeUploadResponse = {
  asset: AssetSummary;
  job: JobStatus;
};

type DocumentAssetDetail = {
  kind: "document";
  format: "markdown";
  parserVersion: string;
  normalizationVersion: string;
  representationId: string;
  blockCount: number;
  headings: Array<{ blockId: string; level: number; text: string; order: number }>;
};

type DocumentNormalizedContent = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "markdown";
  parserVersion: string;
  normalizationVersion: string;
  contentSha256: string;
  normalizedText: string;
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

const statePath = process.env.PLAYWRIGHT_V5B_DOCUMENT_STATE_PATH;
const artifactRoot = path.resolve(
  process.env.PLAYWRIGHT_V5B_DOCUMENT_ARTIFACT_DIR
    ?? path.join(process.cwd(), "../../docs/evals/artifacts/v5b-document-browser-v1"),
);
const fixtureMarkdown = path.resolve(
  process.cwd(),
  "../../docs/fixtures/document-modality/markdown-note.md",
);
const fixtureJson = path.resolve(
  process.cwd(),
  "../../docs/fixtures/document-modality/markdown-note.fixture.json",
);

const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "cancelled"]);
const READY_ASSET_STATUSES = new Set(["ready"]);
const STANDALONE_SERVER_MARKER = "PLAYWRIGHT_STANDALONE_SERVER";

function isStandaloneServerMarked(): boolean {
  return process.env.PLAYWRIGHT_STANDALONE_SERVER === "1";
}

function liveLaneSkipReason(): string | null {
  if (process.env.PLAYWRIGHT_START_WEB === "1") {
    return "Production-start evidence must not set PLAYWRIGHT_START_WEB=1 (dev watcher).";
  }
  if (!isStandaloneServerMarked()) {
    return (
      `Set ${STANDALONE_SERVER_MARKER}=1 to opt into live production-start E2E against an externally started standalone server.`
    );
  }
  if (!process.env.PLAYWRIGHT_BASE_URL) {
    return "PLAYWRIGHT_BASE_URL is required for live production-start E2E.";
  }
  if (!statePath) {
    return "Set PLAYWRIGHT_V5B_DOCUMENT_STATE_PATH to a live browser state JSON to run production-start live checks.";
  }
  return null;
}

async function pathExists(target: string): Promise<boolean> {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

async function signIn(page: Page, state: BrowserState): Promise<void> {
  const response = await page.context().request.post("/api/auth/login", {
    data: { email: state.email, password: state.password },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

async function loadFixtureOracle(): Promise<FixtureOracle> {
  return JSON.parse(await readFile(fixtureJson, "utf8")) as FixtureOracle;
}

function assertJobEnvelope(
  payload: unknown,
  expected: { workspaceId: string; assetId: string; jobId?: string },
): JobStatus {
  expect(payload, "jobs BFF must return an object envelope").toBeTruthy();
  expect(typeof payload).toBe("object");
  expect(Array.isArray(payload)).toBeFalsy();
  const envelope = payload as { job?: JobStatus };
  expect(
    envelope.job,
    "jobs BFF must return exact envelope { job: JobStatus }; direct-unwrapped payloads are rejected",
  ).toBeTruthy();
  const job = envelope.job as JobStatus;
  expect(job.id, "job.id is required").toBeTruthy();
  if (expected.jobId) {
    expect(job.id).toBe(expected.jobId);
  }
  expect(job.workspaceId, "job.workspaceId must match scoped workspace").toBe(expected.workspaceId);
  expect(job.assetId, "job.assetId must match scoped asset").toBe(expected.assetId);
  expect(job.jobType, "job.jobType must be ingest").toBe("ingest");
  expect(typeof job.status, "job.status must be present").toBe("string");
  expect("errorCode" in job, "job.errorCode field must be present").toBeTruthy();
  expect("errorMessage" in job, "job.errorMessage field must be present").toBeTruthy();
  return job;
}

async function pollJobUntilTerminal(
  request: APIRequestContext,
  workspaceId: string,
  jobId: string,
  assetId: string,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<JobStatus> {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const intervalMs = options.intervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;
  let lastStatus = "unknown";
  let lastBody = "";
  while (Date.now() < deadline) {
    const response = await request.get(`/api/workspaces/${workspaceId}/jobs/${jobId}`);
    lastBody = await response.text();
    expect(
      response.status(),
      `job poll must return HTTP 200; status=${response.status()} jobId=${jobId} body=${lastBody}`,
    ).toBe(200);
    const payload = JSON.parse(lastBody) as unknown;
    const job = assertJobEnvelope(payload, { workspaceId, assetId, jobId });
    lastStatus = job.status;
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(
    `job poll timed out jobId=${jobId} lastStatus=${lastStatus} body=${lastBody}`,
  );
}

function assertBlocksMatchFixture(
  actualBlocks: DocumentNormalizedContent["blocks"],
  fixture: FixtureOracle,
): void {
  expect(actualBlocks.length, "block count must match fixture oracle").toBe(fixture.blocks.length);
  for (let index = 0; index < fixture.blocks.length; index += 1) {
    const actual = actualBlocks[index];
    const expected = fixture.blocks[index];
    expect(actual, `missing block at index=${index}`).toBeTruthy();
    expect(actual.blockId, `blockId index=${index}`).toBe(expected.blockId);
    expect(actual.blockOrder, `blockOrder index=${index}`).toBe(expected.blockOrder);
    expect(actual.blockKind, `blockKind index=${index}`).toBe(expected.blockKind);
    expect(actual.headingLevel, `headingLevel index=${index}`).toBe(expected.headingLevel);
    expect(actual.headingPath, `headingPath index=${index}`).toEqual(expected.headingPath);
    expect(actual.charStart, `charStart index=${index}`).toBe(expected.charStart);
    expect(actual.charEnd, `charEnd index=${index}`).toBe(expected.charEnd);
    expect(actual.textSha256, `textSha256 index=${index}`).toBe(expected.textSha256);
    expect(actual.text, `text index=${index}`).toBe(expected.text);
  }
}

function requireHistoricalCitationExpectations(state: BrowserState): {
  expectedProcessingGeneration: number;
  expectedBlockId: string;
  expectedCharStart: number;
  expectedCharEnd: number;
  expectedTextSha256: string;
} {
  expect(state.citationId, "historical citation path requires citationId").toBeTruthy();
  expect(
    typeof state.expectedProcessingGeneration,
    "citationId requires expectedProcessingGeneration",
  ).toBe("number");
  expect(state.expectedBlockId, "citationId requires expectedBlockId").toBeTruthy();
  expect(typeof state.expectedCharStart, "citationId requires expectedCharStart").toBe("number");
  expect(typeof state.expectedCharEnd, "citationId requires expectedCharEnd").toBe("number");
  expect(state.expectedTextSha256, "citationId requires expectedTextSha256").toBeTruthy();
  return {
    expectedProcessingGeneration: state.expectedProcessingGeneration as number,
    expectedBlockId: state.expectedBlockId as string,
    expectedCharStart: state.expectedCharStart as number,
    expectedCharEnd: state.expectedCharEnd as number,
    expectedTextSha256: state.expectedTextSha256 as string,
  };
}

function findBlockOracle(
  blocks: Array<{
    blockId: string;
    charStart: number;
    charEnd: number;
    textSha256: string;
    text: string;
  }>,
  expected: {
    expectedBlockId: string;
    expectedCharStart: number;
    expectedCharEnd: number;
    expectedTextSha256: string;
  },
) {
  const block = blocks.find((entry) => entry.blockId === expected.expectedBlockId);
  expect(
    block,
    `content/fixture oracle missing expected blockId=${expected.expectedBlockId}`,
  ).toBeTruthy();
  expect(block!.charStart, `charStart for blockId=${expected.expectedBlockId}`).toBe(
    expected.expectedCharStart,
  );
  expect(block!.charEnd, `charEnd for blockId=${expected.expectedBlockId}`).toBe(
    expected.expectedCharEnd,
  );
  expect(block!.textSha256, `textSha256 for blockId=${expected.expectedBlockId}`).toBe(
    expected.expectedTextSha256,
  );
  return block!;
}

test.describe.configure({ mode: "serial" });

test("V5-B document fixture oracle is present for production-start lane", async () => {
  const markdown = await readFile(fixtureMarkdown);
  const fixture = await loadFixtureOracle();
  const digest = createHash("sha256").update(markdown).digest("hex");
  expect(digest).toBe(fixture.sourceSha256);
  expect(fixture.mimeType).toBe("text/markdown");
  expect(fixture.locatorKind).toBe("document_anchor");
  expect(fixture.parserVersion).toBe("document-parser-v1");
  expect(fixture.normalizationVersion).toBe("document-normalization-v1");
  expect(fixture.contentUnitKinds).toEqual(["document_text_chunk"]);
  expect(fixture.blocks.every((block) => "headingLevel" in block)).toBeTruthy();
  expect(fixture.blocks.some((block) => block.blockKind === "heading" && block.headingLevel === 1)).toBeTruthy();
});

test("V5-B document production-start upload/ready smoke against live API", async ({ page }, testInfo) => {
  const skipReason = liveLaneSkipReason();
  testInfo.skip(Boolean(skipReason), skipReason ?? "live production-start prerequisites missing");
  if (skipReason) return;

  const state = JSON.parse(await readFile(statePath as string, "utf8")) as BrowserState;
  expect(state.schemaVersion).toBe("v5b-document-browser-state-v1");
  const fixture = await loadFixtureOracle();
  await mkdir(artifactRoot, { recursive: true });
  await signIn(page, state);
  await page.goto(`/workspaces/${state.workspaceId}`);

  const markdownBytes = await readFile(fixtureMarkdown);
  const uploadSessionPath = `/api/workspaces/${state.workspaceId}/assets/upload-session`;
  const sessionResponse = await page.context().request.post(uploadSessionPath, {
    data: {
      sourceFilename: "markdown-note.md",
      mimeType: "text/markdown",
      byteSize: markdownBytes.byteLength,
      title: "Markdown Note",
    },
  });
  expect(sessionResponse.status(), await sessionResponse.text()).toBe(201);
  const sessionBody = await sessionResponse.json() as UploadSessionResponse;
  expect(sessionBody.asset.kind).toBe("document");
  expect(sessionBody.asset.mimeType).toBe("text/markdown");
  expect(sessionBody.upload.objectKey, "upload session must return exact objectKey").toBeTruthy();
  expect(sessionBody.upload.url, "upload session must return BFF upload url").toBeTruthy();

  const putResponse = await page.context().request.fetch(sessionBody.upload.url, {
    method: sessionBody.upload.method ?? "PUT",
    headers: sessionBody.upload.headers,
    data: markdownBytes,
  });
  expect([200, 201, 204], await putResponse.text()).toContain(putResponse.status());

  const finalizeResponse = await page.context().request.post(
    `/api/workspaces/${state.workspaceId}/assets/${sessionBody.asset.id}/finalize-upload`,
    { data: { objectKey: sessionBody.upload.objectKey } },
  );
  const finalizeText = await finalizeResponse.text();
  expect(
    finalizeResponse.status(),
    `finalize-upload must return 200; status=${finalizeResponse.status()} body=${finalizeText}`,
  ).toBe(200);
  const finalizeBody = JSON.parse(finalizeText) as FinalizeUploadResponse;
  expect(finalizeBody.asset.id).toBe(sessionBody.asset.id);
  expect(finalizeBody.job.id, "finalize-upload must return job id").toBeTruthy();
  expect(finalizeBody.job.assetId).toBe(sessionBody.asset.id);
  expect(finalizeBody.job.workspaceId).toBe(state.workspaceId);
  expect(finalizeBody.job.jobType).toBe("ingest");

  const terminalJob = await pollJobUntilTerminal(
    page.context().request,
    state.workspaceId,
    finalizeBody.job.id,
    sessionBody.asset.id,
  );
  if (terminalJob.status !== "succeeded") {
    throw new Error(
      `ingestion job did not succeed jobId=${terminalJob.id} status=${terminalJob.status} `
      + `errorCode=${terminalJob.errorCode ?? "null"} errorMessage=${terminalJob.errorMessage ?? "null"}`,
    );
  }
  expect(terminalJob.workspaceId).toBe(state.workspaceId);
  expect(terminalJob.assetId).toBe(sessionBody.asset.id);
  expect(terminalJob.jobType).toBe("ingest");
  expect(terminalJob.errorCode).toBeNull();
  expect(terminalJob.errorMessage).toBeNull();

  const assetDetailResponse = await page.context().request.get(
    `/api/workspaces/${state.workspaceId}/assets/${sessionBody.asset.id}`,
  );
  const assetDetailText = await assetDetailResponse.text();
  expect(
    assetDetailResponse.status(),
    `asset detail must return 200; body=${assetDetailText}`,
  ).toBe(200);
  const assetDetailBody = JSON.parse(assetDetailText) as {
    asset: AssetSummary;
    detail: DocumentAssetDetail;
  };
  expect(assetDetailBody.asset.id).toBe(sessionBody.asset.id);
  expect(assetDetailBody.asset.kind).toBe("document");
  expect(assetDetailBody.asset.mimeType).toBe("text/markdown");
  expect(
    READY_ASSET_STATUSES.has(assetDetailBody.asset.status),
    `asset must be ready after succeeded job; status=${assetDetailBody.asset.status} `
    + `errorCode=${assetDetailBody.asset.lastErrorCode ?? "null"} `
    + `errorMessage=${assetDetailBody.asset.lastErrorMessage ?? "null"}`,
  ).toBeTruthy();
  expect(assetDetailBody.detail.kind).toBe("document");
  expect(assetDetailBody.detail.format).toBe("markdown");
  expect(assetDetailBody.detail.parserVersion).toBe(fixture.parserVersion);
  expect(assetDetailBody.detail.normalizationVersion).toBe(fixture.normalizationVersion);
  expect(assetDetailBody.detail.representationId, "document detail requires representationId").toBeTruthy();
  expect(assetDetailBody.detail.blockCount).toBe(fixture.blocks.length);
  expect(assetDetailBody.asset.currentProcessingGeneration).toBeGreaterThanOrEqual(1);

  const contentResponse = await page.context().request.get(
    `/api/workspaces/${state.workspaceId}/assets/${sessionBody.asset.id}/representations/${assetDetailBody.detail.representationId}/content`,
  );
  const contentText = await contentResponse.text();
  expect(
    contentResponse.status(),
    `document content must return 200; body=${contentText}`,
  ).toBe(200);
  const contentBody = JSON.parse(contentText) as DocumentNormalizedContent;
  expect(contentBody.assetId).toBe(sessionBody.asset.id);
  expect(contentBody.representationId).toBe(assetDetailBody.detail.representationId);
  expect(contentBody.processingGeneration).toBe(assetDetailBody.asset.currentProcessingGeneration);
  expect(contentBody.parserVersion).toBe(fixture.parserVersion);
  expect(contentBody.normalizationVersion).toBe(fixture.normalizationVersion);
  expect(contentBody.contentSha256).toBe(fixture.normalizedContentSha256);
  expect(contentBody.normalizedText).toBe(fixture.normalizedText);
  assertBlocksMatchFixture(contentBody.blocks, fixture);

  // Representation ownership: detail + content must bind the same generation-scoped representation.
  expect(contentBody.processingGeneration).toBe(assetDetailBody.asset.currentProcessingGeneration);
  expect(assetDetailBody.detail.representationId).toBe(contentBody.representationId);

  const artifact = {
    schemaVersion: "v5b-document-browser-artifact-v1",
    productionStart: true,
    playWrightStartWeb: process.env.PLAYWRIGHT_START_WEB ?? null,
    playWrightStandaloneServer: process.env.PLAYWRIGHT_STANDALONE_SERVER ?? null,
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    assetId: sessionBody.asset.id,
    assetKind: sessionBody.asset.kind,
    mimeType: sessionBody.asset.mimeType,
    objectKey: sessionBody.upload.objectKey,
    finalizeUploadStatus: finalizeResponse.status(),
    jobId: finalizeBody.job.id,
    jobStatus: terminalJob.status,
    jobType: terminalJob.jobType,
    jobWorkspaceId: terminalJob.workspaceId,
    jobAssetId: terminalJob.assetId,
    jobErrorCode: terminalJob.errorCode,
    jobErrorMessage: terminalJob.errorMessage,
    assetStatus: assetDetailBody.asset.status,
    processingGeneration: assetDetailBody.asset.currentProcessingGeneration,
    representationId: assetDetailBody.detail.representationId,
    contentSha256: contentBody.contentSha256,
    blockCount: contentBody.blocks.length,
    dockerfileWebCmd: ["node", "apps/web/server.js"],
    standaloneEntry: "apps/web/.next/standalone/apps/web/server.js",
  };
  await writeFile(
    path.join(artifactRoot, "production-start-upload.json"),
    `${JSON.stringify(artifact, null, 2)}\n`,
  );
});

test("V5-B document production-start historical citation remains addressable when state provides citationId", async ({ page }, testInfo) => {
  const skipReason = liveLaneSkipReason();
  testInfo.skip(Boolean(skipReason), skipReason ?? "live production-start prerequisites missing");
  if (skipReason) return;

  const state = JSON.parse(await readFile(statePath as string, "utf8")) as BrowserState;
  testInfo.skip(!state.citationId, "Browser state has no citationId for historical document evidence.");
  if (!state.citationId) return;

  const expected = requireHistoricalCitationExpectations(state);
  const fixture = await loadFixtureOracle();
  findBlockOracle(fixture.blocks, expected);

  await signIn(page, state);
  await page.goto(`/workspaces/${state.workspaceId}`);

  // Prefer live BFF content oracle when documentAssetId is available; otherwise
  // the checked-in fixture block oracle above remains the exact range/hash source.
  let contentOracleBlock = findBlockOracle(fixture.blocks, expected);
  let contentOracleSource: "fixture" | "bff-content" = "fixture";
  if (state.documentAssetId) {
    const assetDetailResponse = await page.context().request.get(
      `/api/workspaces/${state.workspaceId}/assets/${state.documentAssetId}`,
    );
    const assetDetailText = await assetDetailResponse.text();
    expect(
      assetDetailResponse.status(),
      `asset detail must return 200 for historical citation content oracle; body=${assetDetailText}`,
    ).toBe(200);
    const assetDetailBody = JSON.parse(assetDetailText) as {
      asset: AssetSummary;
      detail: DocumentAssetDetail;
    };
    expect(assetDetailBody.asset.currentProcessingGeneration).toBe(
      expected.expectedProcessingGeneration,
    );
    expect(assetDetailBody.detail.representationId).toBeTruthy();

    const contentResponse = await page.context().request.get(
      `/api/workspaces/${state.workspaceId}/assets/${state.documentAssetId}/representations/${assetDetailBody.detail.representationId}/content`,
    );
    const contentText = await contentResponse.text();
    expect(
      contentResponse.status(),
      `document content must return 200 for historical citation oracle; body=${contentText}`,
    ).toBe(200);
    const contentBody = JSON.parse(contentText) as DocumentNormalizedContent;
    expect(contentBody.processingGeneration).toBe(expected.expectedProcessingGeneration);
    contentOracleBlock = findBlockOracle(contentBody.blocks, expected);
    contentOracleSource = "bff-content";
  }

  const button = page.locator(`[data-citation-id="${state.citationId}"]`).first();
  await expect(button).toBeVisible({ timeout: 30_000 });
  await button.click();

  // Honest document viewer proof, not panel-only visibility.
  const viewer = page.locator('[data-document-viewer="true"]');
  await expect(viewer).toBeVisible({ timeout: 30_000 });
  await expect(viewer).toHaveAttribute(
    "data-document-generation",
    String(expected.expectedProcessingGeneration),
  );
  await expect(viewer).toHaveAttribute("data-document-highlight-status", "ready");

  const targetBlock = page.locator(
    `[data-document-block-id="${expected.expectedBlockId}"]`,
  ).first();
  await expect(targetBlock).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(`#document-block-${expected.expectedBlockId}`)).toBeVisible({
    timeout: 30_000,
  });

  const highlighted = page.locator(
    `[data-document-block-id="${expected.expectedBlockId}"] [data-document-highlight-range="true"]`,
  ).first();
  await expect(highlighted).toBeVisible({ timeout: 30_000 });

  // Viewer DOM currently exposes block/status attributes, not range/hash attrs.
  // Exact range/hash therefore comes from the BFF content/fixture oracle above.
  expect(contentOracleBlock.charStart).toBe(expected.expectedCharStart);
  expect(contentOracleBlock.charEnd).toBe(expected.expectedCharEnd);
  expect(contentOracleBlock.textSha256).toBe(expected.expectedTextSha256);

  await mkdir(artifactRoot, { recursive: true });
  await viewer.screenshot({ path: path.join(artifactRoot, "document-historical-citation.png") });
  await writeFile(
    path.join(artifactRoot, "document-historical-citation.json"),
    `${JSON.stringify({
      schemaVersion: "v5b-document-browser-artifact-v1",
      citationId: state.citationId,
      expectedProcessingGeneration: expected.expectedProcessingGeneration,
      expectedBlockId: expected.expectedBlockId,
      expectedCharStart: expected.expectedCharStart,
      expectedCharEnd: expected.expectedCharEnd,
      expectedTextSha256: expected.expectedTextSha256,
      contentOracleSource,
      requiredViewer: true,
      requiredHighlightReady: true,
      requiredHighlightedSpan: true,
      playWrightStandaloneServer: process.env.PLAYWRIGHT_STANDALONE_SERVER ?? null,
      playWrightStartWeb: process.env.PLAYWRIGHT_START_WEB ?? null,
    }, null, 2)}\n`,
  );
});

test("production Dockerfile.web standalone command is the required server entry", async () => {
  const dockerfile = await readFile(
    path.resolve(process.cwd(), "../../infra/docker/Dockerfile.web"),
    "utf8",
  );
  expect(dockerfile).toContain('CMD ["node", "apps/web/server.js"]');
  expect(dockerfile).toContain("apps/web/.next/standalone");
  // Local production-start uses the build output path that maps to the same server entry.
  const localStandalone = path.resolve(process.cwd(), ".next/standalone/apps/web/server.js");
  // Presence is optional before build; document the expected path for operators.
  const exists = await pathExists(localStandalone);
  await mkdir(artifactRoot, { recursive: true });
  await writeFile(
    path.join(artifactRoot, "standalone-entry-check.json"),
    `${JSON.stringify({
      dockerfileCmd: ["node", "apps/web/server.js"],
      localStandaloneEntry: "apps/web/.next/standalone/apps/web/server.js",
      localStandaloneExists: exists,
      playWrightStartWeb: process.env.PLAYWRIGHT_START_WEB ?? null,
      playWrightStandaloneServer: process.env.PLAYWRIGHT_STANDALONE_SERVER ?? null,
      note: "E2E must be pointed at a process started from the standalone entry, not pnpm dev. Live upload/citation tests require PLAYWRIGHT_STANDALONE_SERVER=1.",
    }, null, 2)}\n`,
  );
});
