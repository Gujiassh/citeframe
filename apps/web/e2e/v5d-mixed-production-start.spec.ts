import { expect, test, type Page } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/**
 * V5-D mixed PDF+Image+Markdown production-start E2E.
 *
 * Requires an externally started standalone Web server + live API/Worker:
 *
 *   pnpm --dir apps/web build
 *   HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
 *   PLAYWRIGHT_STANDALONE_SERVER=1 \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
 *   PLAYWRIGHT_V5D_MIXED_STATE_PATH=... \
 *   pnpm --dir apps/web exec playwright test e2e/v5d-mixed-production-start.spec.ts
 *
 * Never sets PLAYWRIGHT_START_WEB and never mocks BFF routes.
 */

type MixedBrowserState = {
  schemaVersion: "v5d-mixed-browser-state-v1";
  email: string;
  password: string;
  workspaceId: string;
  threadId: string;
  assets: Record<
    "pdf" | "image" | "document",
    {
      assetId: string;
      kind: string;
      mimeType: string;
      sourceFilename: string;
      title: string;
    }
  >;
  citationIds: {
    pdf: string;
    image: string;
    document: string;
  };
  evidence: {
    document?: {
      expectedProcessingGeneration?: number;
      expectedBlockId?: string;
      expectedCharStart?: number;
      expectedCharEnd?: number;
      expectedTextSha256?: string;
    };
  };
};

const statePath = process.env.PLAYWRIGHT_V5D_MIXED_STATE_PATH;
const artifactRoot = path.resolve(
  process.env.PLAYWRIGHT_V5D_MIXED_ARTIFACT_DIR
    ?? path.join(process.cwd(), "../../docs/evals/artifacts/v5d-20260811-01"),
);
const STANDALONE_SERVER_MARKER = "PLAYWRIGHT_STANDALONE_SERVER";

function isStandaloneServerMarked(): boolean {
  return process.env.PLAYWRIGHT_STANDALONE_SERVER === "1";
}

function liveLaneSkipReason(): string | null {
  if (process.env.PLAYWRIGHT_START_WEB === "1") {
    return "Production-start mixed evidence must not set PLAYWRIGHT_START_WEB=1 (dev watcher).";
  }
  if (!isStandaloneServerMarked()) {
    return (
      `Set ${STANDALONE_SERVER_MARKER}=1 to opt into live production-start mixed E2E against an externally started standalone server.`
    );
  }
  if (!process.env.PLAYWRIGHT_BASE_URL) {
    return "PLAYWRIGHT_BASE_URL is required for live production-start mixed E2E.";
  }
  if (!statePath) {
    return "Set PLAYWRIGHT_V5D_MIXED_STATE_PATH to a live mixed browser state JSON.";
  }
  return null;
}

async function signIn(page: Page, state: MixedBrowserState): Promise<void> {
  const response = await page.context().request.post("/api/auth/login", {
    data: { email: state.email, password: state.password },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

async function ensureSidebarOpen(page: Page, mobile: boolean, preferredAssetId?: string): Promise<void> {
  if (!mobile) return;
  const target = preferredAssetId
    ? page.locator(`[data-asset-id="${preferredAssetId}"]`)
    : page.locator("[data-asset-id]").first();
  if (await target.isVisible().catch(() => false)) {
    return;
  }
  const expand = page.getByRole("button", { name: /展开侧边栏|expand sidebar/i });
  await expect(expand).toBeVisible({ timeout: 15_000 });
  await expand.click();
  if (preferredAssetId) {
    await expect(page.locator(`[data-asset-id="${preferredAssetId}"]`)).toBeVisible({ timeout: 30_000 });
  }
}

async function closeMobileNavigation(page: Page): Promise<void> {
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

async function runMixedProductionFlow(
  page: Page,
  viewportName: "desktop" | "mobile",
  viewport: { width: number; height: number },
): Promise<Record<string, unknown>> {
  const state = JSON.parse(await readFile(statePath as string, "utf8")) as MixedBrowserState;
  expect(state.schemaVersion).toBe("v5d-mixed-browser-state-v1");
  expect(state.assets.pdf).toBeTruthy();
  expect(state.assets.image).toBeTruthy();
  expect(state.assets.document).toBeTruthy();
  expect(state.citationIds.pdf).toBeTruthy();
  expect(state.citationIds.image).toBeTruthy();
  expect(state.citationIds.document).toBeTruthy();

  const mobile = viewportName === "mobile";
  await page.setViewportSize(viewport);
  await signIn(page, state);
  await page.goto(`/workspaces/${state.workspaceId}`, { waitUntil: "domcontentloaded" });
  await ensureSidebarOpen(page, mobile, state.assets.pdf.assetId);

  // Asset list + exact kind labels for PDF/Image/Markdown.
  for (const kind of ["pdf", "image", "document"] as const) {
    const asset = state.assets[kind];
    const row = page.locator(`[data-asset-id="${asset.assetId}"]`);
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText(asset.sourceFilename);
    await expect(row.locator("span.uppercase")).toHaveText(kind);
  }

  // Selected-scope over all three ready modalities.
  for (const kind of ["pdf", "image", "document"] as const) {
    await page.locator(`[data-asset-id="${state.assets[kind].assetId}"] input[type="checkbox"]`).check();
  }
  await expect(page.getByText(/已选择 3 个资产|3 assets selected/i)).toBeVisible();

  if (mobile) {
    await closeMobileNavigation(page);
  }

  // Open historical mixed citations from the seeded thread.
  // Navigate to chat thread if needed by clicking the thread list / reloading messages via URL.
  // Workspace home shows recent chat; open thread messages via BFF-backed UI.
  const pdfCitation = page.locator(`[data-citation-id="${state.citationIds.pdf}"]`);
  const imageCitation = page.locator(`[data-citation-id="${state.citationIds.image}"]`);
  const documentCitation = page.locator(`[data-citation-id="${state.citationIds.document}"]`);

  // If citations are not already visible, open the seeded thread through the chat surface.
  if (!(await pdfCitation.isVisible().catch(() => false))) {
    // Prefer direct thread deep link if the app supports it; otherwise click thread entry.
    await page.goto(`/workspaces/${state.workspaceId}?threadId=${state.threadId}`, {
      waitUntil: "domcontentloaded",
    });
    await ensureSidebarOpen(page, mobile, state.assets.pdf.assetId);
    if (mobile) {
      await closeMobileNavigation(page);
    }
  }

  // Fallback: open chat tab / thread list item by title.
  if (!(await pdfCitation.isVisible().catch(() => false))) {
    const threadEntry = page.getByText(/V5-D Mixed deployment evidence|Mixed deployment/i).first();
    if (await threadEntry.isVisible().catch(() => false)) {
      await threadEntry.click();
    }
  }

  await expect(pdfCitation).toBeVisible({ timeout: 45_000 });
  await expect(imageCitation).toBeVisible({ timeout: 30_000 });
  await expect(documentCitation).toBeVisible({ timeout: 30_000 });

  // PDF citation opens PDF viewer.
  await pdfCitation.click();
  const pdfViewer = page.locator("[data-pdf-viewer]");
  await expect(pdfViewer).toBeVisible({ timeout: 45_000 });
  await expect(pdfViewer.locator("canvas").first()).toBeVisible({ timeout: 45_000 });
  await closeEvidencePanel(page);

  // Image citation opens image viewer with region overlay when available.
  await imageCitation.click();
  const imageViewer = page.locator("[data-image-viewer]");
  await expect(imageViewer).toBeVisible({ timeout: 45_000 });
  await expect(imageViewer.locator("img")).toBeVisible({ timeout: 45_000 });
  // Region overlay is preferred but not required if seed used a full-page image caption locator.
  const region = page.locator("[data-image-evidence-region]");
  const regionVisible = await region.first().isVisible().catch(() => false);
  await closeEvidencePanel(page);

  // Document citation opens document viewer with highlight when block metadata exists.
  await documentCitation.click();
  const documentViewer = page.locator('[data-document-viewer="true"]');
  await expect(documentViewer).toBeVisible({ timeout: 45_000 });
  const documentEvidence = state.evidence?.document;
  if (documentEvidence?.expectedProcessingGeneration != null) {
    await expect(documentViewer).toHaveAttribute(
      "data-document-generation",
      String(documentEvidence.expectedProcessingGeneration),
    );
  }
  if (documentEvidence?.expectedBlockId) {
    await expect(
      page.locator(`[data-document-block-id="${documentEvidence.expectedBlockId}"]`),
    ).toBeVisible({ timeout: 30_000 });
  }
  await closeEvidencePanel(page);

  await assertNoHorizontalOverflow(page);
  await mkdir(artifactRoot, { recursive: true });
  const screenshotName = `v5d-mixed-production-${viewportName}.png`;
  const screenshotPath = path.join(artifactRoot, screenshotName);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const result = {
    schemaVersion: "v5d-mixed-workspace-playwright-v1",
    productionStart: true,
    mockedBff: false,
    standaloneServer: true,
    viewport: { name: viewportName, ...viewport },
    workspaceId: state.workspaceId,
    assets: (["pdf", "image", "document"] as const).map((kind) => ({
      id: state.assets[kind].assetId,
      kind,
      mimeType: state.assets[kind].mimeType,
      sourceFilename: state.assets[kind].sourceFilename,
    })),
    citations: {
      pdf: state.citationIds.pdf,
      image: state.citationIds.image,
      document: state.citationIds.document,
      imageRegionVisible: regionVisible,
    },
    selectedScopeCount: 3,
    screenshotPath: path.relative(path.resolve(process.cwd(), "../.."), screenshotPath),
    passed: true,
  };
  await writeFile(
    path.join(artifactRoot, `v5d-mixed-production-${viewportName}.json`),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8",
  );
  return result;
}

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

test("V5-D mixed production-start on desktop 1440x1000", async ({ page }, testInfo) => {
  const skipReason = liveLaneSkipReason();
  testInfo.skip(Boolean(skipReason), skipReason ?? "live production-start prerequisites missing");
  if (skipReason) return;
  const result = await runMixedProductionFlow(page, "desktop", { width: 1440, height: 1000 });
  expect(result.passed).toBeTruthy();
  expect(result.productionStart).toBe(true);
  expect(result.mockedBff).toBe(false);
});

test("V5-D mixed production-start on mobile 390x844", async ({ page }, testInfo) => {
  const skipReason = liveLaneSkipReason();
  testInfo.skip(Boolean(skipReason), skipReason ?? "live production-start prerequisites missing");
  if (skipReason) return;
  const result = await runMixedProductionFlow(page, "mobile", { width: 390, height: 844 });
  expect(result.passed).toBeTruthy();
  expect(result.productionStart).toBe(true);
  expect(result.mockedBff).toBe(false);
});
