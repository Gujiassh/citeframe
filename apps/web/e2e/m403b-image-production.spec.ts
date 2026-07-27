import { expect, test, type Locator, type Page, type Response, type TestInfo } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

type BrowserState = {
  schemaVersion: "m403b-browser-state-v1";
  email: string;
  password: string;
  workspaceId: string;
};

type ResponseStatus = {
  method: string;
  path: string;
  status: number;
  requestContentType: string | null;
  responseContentType: string | null;
};

type PixelMeasurement = {
  width: number;
  height: number;
  uniqueColors: number;
  nonWhiteSamples: number;
};

type Bounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const statePath = process.env.PLAYWRIGHT_M403B_BROWSER_STATE_PATH;
const artifactRoot = path.resolve(
  process.env.PLAYWRIGHT_M403B_BROWSER_ARTIFACT_DIR
    ?? path.join(process.cwd(), "../../docs/evals/artifacts/m403b-browser-v1"),
);
const fixturePath = path.resolve(
  process.cwd(),
  "../../docs/fixtures/evidence-contract/image-coordinate-fixture.png",
);
const jpegFixturePath = path.resolve(
  process.cwd(),
  "../../docs/fixtures/evidence-contract/image-ingestion-matrix/orientation-1.jpg",
);
const webpFixturePath = path.resolve(
  process.cwd(),
  "../../docs/fixtures/evidence-contract/image-ingestion-matrix/control.webp",
);

async function signIn(page: Page, state: BrowserState): Promise<void> {
  const response = await page.context().request.post("/api/auth/login", {
    data: { email: state.email, password: state.password },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

async function ensureSidebarOpen(page: Page, mobile: boolean): Promise<void> {
  if (!mobile) return;
  const expand = page.getByRole("button", { name: /展开侧边栏|expand sidebar/i });
  if (await expand.isVisible().catch(() => false)) await expand.click();
  await expect(page.locator('input[type="file"]')).toBeAttached();
}

async function uploadFixture(
  page: Page,
  workspaceId: string,
  responseStatuses: ResponseStatus[],
  fixture: { filename: string; mimeType: string; path: string },
): Promise<{
  assetId: string;
  filename: string;
}> {
  const uploadSessionPath = `/api/workspaces/${workspaceId}/assets/upload-session`;
  const uploadSessionPromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" && url.pathname === uploadSessionPath;
  });

  await page.locator('input[type="file"]').first().setInputFiles({
    name: fixture.filename,
    mimeType: fixture.mimeType,
    buffer: await readFile(fixture.path),
  });
  const uploadSessionResponse = await uploadSessionPromise;
  expect(uploadSessionResponse.status()).toBe(201);
  const uploadSessionPayload = await uploadSessionResponse.json() as { asset?: { id?: unknown } };
  const assetId = uploadSessionPayload.asset?.id;
  if (typeof assetId !== "string" || assetId.length === 0) {
    throw new Error("M403B upload-session response did not contain a fresh asset ID.");
  }

  const row = page.locator(`[data-asset-id="${assetId}"]`);
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toHaveAttribute("data-asset-status", "ready", { timeout: 120_000 });
  await expect.poll(
    () => responseStatuses.some((item) => item.method === "POST" && item.path === uploadSessionPath && item.status === 201),
  ).toBeTruthy();
  await expect.poll(
    () => responseStatuses.some((item) => item.method === "PUT" && item.path.startsWith(`/api/workspaces/${workspaceId}/assets/${assetId}/upload?`) && item.status === 204),
  ).toBeTruthy();
  await expect.poll(
    () => responseStatuses.some((item) => item.method === "POST" && item.path === `/api/workspaces/${workspaceId}/assets/${assetId}/finalize-upload` && item.status === 200),
  ).toBeTruthy();
  return { assetId, filename: fixture.filename };
}

async function sampledImagePixels(image: Locator): Promise<PixelMeasurement> {
  return image.evaluate((element) => {
    const source = element as HTMLImageElement;
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 64;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context || !source.complete || source.naturalWidth === 0 || source.naturalHeight === 0) {
      return { width: source.naturalWidth, height: source.naturalHeight, uniqueColors: 0, nonWhiteSamples: 0 };
    }
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    const colors = new Set<string>();
    let nonWhiteSamples = 0;
    for (let row = 0; row < 16; row += 1) {
      for (let column = 0; column < 24; column += 1) {
        const [red, green, blue, alpha] = context.getImageData(column * 4 + 2, row * 4 + 2, 1, 1).data;
        colors.add(`${red}:${green}:${blue}:${alpha}`);
        if (alpha > 0 && (red < 248 || green < 248 || blue < 248)) nonWhiteSamples += 1;
      }
    }
    return {
      width: source.naturalWidth,
      height: source.naturalHeight,
      uniqueColors: colors.size,
      nonWhiteSamples,
    };
  });
}

async function measureLayout(
  page: Page,
  panel: Locator,
  viewer: Locator,
  surface: Locator,
): Promise<{
  viewport: { width: number; height: number };
  panel: Bounds;
  viewer: Bounds;
  imageViewport: Bounds;
  surface: Bounds;
  panelWithinViewport: boolean;
  viewerWithinPanel: boolean;
  surfaceWithinImageViewport: boolean;
  imageViewportOverflow: { clientWidth: number; scrollWidth: number };
}> {
  const viewport = page.viewportSize();
  const panelBox = await panel.boundingBox();
  const viewerBox = await viewer.boundingBox();
  const imageViewport = viewer.locator("[data-image-viewport]");
  const imageViewportBox = await imageViewport.boundingBox();
  const surfaceBox = await surface.boundingBox();
  if (!viewport || !panelBox || !viewerBox || !imageViewportBox || !surfaceBox) {
    throw new Error("M403B Viewer layout bounds are unavailable.");
  }
  const imageViewportOverflow = await imageViewport.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  return {
    viewport,
    panel: panelBox,
    viewer: viewerBox,
    imageViewport: imageViewportBox,
    surface: surfaceBox,
    panelWithinViewport: panelBox.x >= -1
      && panelBox.y >= -1
      && panelBox.x + panelBox.width <= viewport.width + 1
      && panelBox.y + panelBox.height <= viewport.height + 1,
    viewerWithinPanel: viewerBox.x >= panelBox.x - 1
      && viewerBox.y >= panelBox.y - 1
      && viewerBox.x + viewerBox.width <= panelBox.x + panelBox.width + 1
      && viewerBox.y + viewerBox.height <= panelBox.y + panelBox.height + 1,
    surfaceWithinImageViewport: surfaceBox.x >= imageViewportBox.x - 1
      && surfaceBox.y >= imageViewportBox.y - 1
      && surfaceBox.x + surfaceBox.width <= imageViewportBox.x + imageViewportBox.width + 1
      && surfaceBox.y + surfaceBox.height <= imageViewportBox.y + imageViewportBox.height + 1,
    imageViewportOverflow,
  };
}

async function measureMobileImageControls(page: Page, viewer: Locator): Promise<Array<{
  name: string;
  width: number;
  height: number;
}>> {
  const controls = [
    { name: "pan", locator: viewer.locator("[data-image-pan]") },
    { name: "region-select", locator: viewer.locator("[data-image-region-select]") },
    { name: "zoom-out", locator: viewer.getByRole("button", { name: /缩小|zoom out/i }) },
    { name: "zoom-in", locator: viewer.getByRole("button", { name: /放大|zoom in/i }) },
    { name: "fit", locator: viewer.locator("[data-image-fit]") },
    { name: "actual-size", locator: viewer.locator("[data-image-actual-size]") },
  ];
  const viewport = page.viewportSize();
  if (!viewport) throw new Error("M403B mobile viewport is unavailable.");
  const measurements = [];
  for (const control of controls) {
    await expect(control.locator).toBeVisible();
    await control.locator.scrollIntoViewIfNeeded();
    const box = await control.locator.boundingBox();
    if (!box) throw new Error(`M403B mobile ${control.name} control has no bounding box.`);
    expect(box.width, control.name).toBeGreaterThanOrEqual(44);
    expect(box.height, control.name).toBeGreaterThanOrEqual(44);
    expect(box.x, control.name).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.width, control.name).toBeLessThanOrEqual(viewport.width + 1);
    measurements.push({ name: control.name, width: box.width, height: box.height });
  }
  return measurements;
}

async function assertNoHorizontalOverflow(page: Page): Promise<{
  viewportWidth: number;
  documentWidth: number;
  bodyWidth: number;
}> {
  const metrics = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewportWidth);
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewportWidth);
  return metrics;
}

async function runBrowserGate(page: Page, testInfo: TestInfo, viewport: "desktop" | "mobile"): Promise<void> {
  test.skip(!statePath, "Set PLAYWRIGHT_M403B_BROWSER_STATE_PATH to run the live M403B browser gate.");
  const state = JSON.parse(await readFile(statePath!, "utf8")) as BrowserState;
  const mobile = viewport === "mobile";
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
  await signIn(page, state);
  await page.goto(`/workspaces/${state.workspaceId}`);
  await expect(page.getByRole("heading", { name: new RegExp(`M403B Browser`) })).toBeVisible({ timeout: 30_000 });
  await ensureSidebarOpen(page, mobile);

  const responseStatuses: ResponseStatus[] = [];
  const baseOrigin = new URL(testInfo.project.use.baseURL as string).origin;
  const responseListener = (response: Response) => {
    const url = new URL(response.url());
    if (url.origin === baseOrigin && url.pathname.startsWith("/api/") && url.pathname.includes("/assets")) {
      responseStatuses.push({
        method: response.request().method(),
        path: `${url.pathname}${url.search}`,
        status: response.status(),
        requestContentType: response.request().headers()["content-type"] ?? null,
        responseContentType: response.headers()["content-type"] ?? null,
      });
    }
  };
  page.on("response", responseListener);
  try {
    const upload = await uploadFixture(page, state.workspaceId, responseStatuses, {
      filename: `m403b-${viewport}-image.png`,
      mimeType: "image/png",
      path: fixturePath,
    });
    const formatUploads = mobile ? [] : [
      await uploadFixture(page, state.workspaceId, responseStatuses, {
        filename: "m403b-desktop-format.jpg",
        mimeType: "image/jpeg",
        path: jpegFixturePath,
      }),
      await uploadFixture(page, state.workspaceId, responseStatuses, {
        filename: "m403b-desktop-format.webp",
        mimeType: "image/webp",
        path: webpFixturePath,
      }),
    ];
    const row = page.locator(`[data-asset-id="${upload.assetId}"]`);
    if (!mobile) await row.hover();
    const deleteButton = row.getByRole("button", { name: /删除资产|delete asset/i });
    await expect(deleteButton).toBeVisible();
    if (mobile) {
      const box = await deleteButton.boundingBox();
      if (!box) throw new Error("M403B mobile delete control has no bounding box.");
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }

    await row.getByText(upload.filename, { exact: true }).click();
    const evidenceToggle = page.locator("[data-evidence-toggle]");
    await expect(evidenceToggle).toBeEnabled();
    if (mobile) await page.getByTitle(/收起侧边栏|collapse sidebar/i).click();
    const panel = page.locator("[data-evidence-panel]");
    if (!await panel.isVisible().catch(() => false)) await evidenceToggle.click();
    await expect(panel).toBeVisible({ timeout: 30_000 });
    const viewer = panel.locator("[data-image-viewer]");
    const image = viewer.locator("img");
    const surface = viewer.locator("[data-image-surface]");
    await expect(image).toBeVisible({ timeout: 30_000 });
    await expect(surface).toBeVisible();
    await expect.poll(async () => (await sampledImagePixels(image)).uniqueColors).toBeGreaterThan(4);
    const pixels = await sampledImagePixels(image);
    expect(pixels.nonWhiteSamples).toBeGreaterThan(4);

    const detailPath = `/api/workspaces/${state.workspaceId}/assets/${upload.assetId}`;
    const orientedPath = `/api/workspaces/${state.workspaceId}/assets/${upload.assetId}/representations/current-image-oriented/file`;
    await expect.poll(() => responseStatuses.some((item) => (
      item.method === "GET"
      && item.path === detailPath
      && item.status === 200
      && item.responseContentType?.startsWith("application/json")
    ))).toBeTruthy();
    await expect.poll(() => responseStatuses.some((item) => (
      item.method === "GET"
      && item.path.startsWith(`${orientedPath}?`)
      && item.status === 200
      && item.responseContentType?.startsWith("image/png")
    ))).toBeTruthy();

    const layout = await measureLayout(page, panel, viewer, surface);
    expect(layout.panelWithinViewport, JSON.stringify(layout)).toBeTruthy();
    expect(layout.viewerWithinPanel, JSON.stringify(layout)).toBeTruthy();
    expect(layout.surfaceWithinImageViewport, JSON.stringify(layout)).toBeTruthy();
    expect(layout.imageViewportOverflow.scrollWidth).toBeLessThanOrEqual(layout.imageViewportOverflow.clientWidth + 1);
    const pageOverflow = await assertNoHorizontalOverflow(page);
    const mobileImageControls = mobile ? await measureMobileImageControls(page, viewer) : [];

    await mkdir(artifactRoot, { recursive: true });
    const screenshotPath = path.join(artifactRoot, `${viewport}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: false });
    await writeFile(
      path.join(artifactRoot, `${viewport}.json`),
      `${JSON.stringify({
        schemaVersion: "m403b-browser-evidence-v1",
        viewport: { name: viewport, ...layout.viewport },
        upload,
        formatUploads,
        responseStatuses,
        pixels,
        layout,
        pageOverflow,
        mobileImageControls,
        routeInterceptions: 0,
        screenshotPath: path.relative(artifactRoot, screenshotPath),
        passed: true,
      }, null, 2)}\n`,
    );
    await testInfo.attach(`${viewport}-browser-artifact`, { path: screenshotPath, contentType: "image/png" });
  } finally {
    page.off("response", responseListener);
  }
}

test.describe.configure({ mode: "serial", timeout: 240_000 });

test("M403B production Image upload and Viewer render on desktop", async ({ page }, testInfo) => {
  await runBrowserGate(page, testInfo, "desktop");
});

test("M403B production Image upload and Viewer render on 390px mobile", async ({ page }, testInfo) => {
  await runBrowserGate(page, testInfo, "mobile");
});
