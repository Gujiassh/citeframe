import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const email = process.env.PLAYWRIGHT_E2E_EMAIL;
const password = process.env.PLAYWRIGHT_E2E_PASSWORD;
const imageWorkspaceId = process.env.PLAYWRIGHT_E2E_IMAGE_WORKSPACE_ID;
const imageAssetId = process.env.PLAYWRIGHT_E2E_IMAGE_ASSET_ID;

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByPlaceholder(/电子邮箱|email address/i).fill(email!);
  await page.getByPlaceholder(/输入密码|password/i).fill(password!);
  await page.locator("form").getByRole("button", { name: /登录|sign in/i }).click();
  await expect(page.getByRole("heading", { name: /工作区|workspaces/i })).toBeVisible();
}

test("unauthenticated auth shell renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Citeframe" })).toBeVisible();
  await expect(page.getByPlaceholder(/电子邮箱|email address/i)).toBeVisible();
});

test.describe("authenticated workspace smoke", () => {
  test.beforeEach(async ({}, testInfo) => {
    testInfo.skip(!email || !password, "Set PLAYWRIGHT_E2E_EMAIL and PLAYWRIGHT_E2E_PASSWORD to run the real smoke.");
  });

  test("login, create workspace, and persist settings", async ({ page }) => {
    await signIn(page);

    const workspaceName = `e2e-${Date.now()}`;
    await page.getByRole("button", { name: /创建新工作区|create workspace/i }).click();
    await page.locator('input[placeholder*="例如"]').fill(workspaceName);
    await page.getByRole("button", { name: /创建并进入/i }).click();
    await page.getByText(workspaceName, { exact: true }).click();
    await expect(page).toHaveURL(/\/workspaces\//);

    await page.getByRole("tab", { name: /配置|settings/i }).click();
    const prompt = page.locator("textarea").first();
    await expect(prompt).toBeVisible();
    await prompt.fill("Answer with a concise evidence checklist.");
    await page.getByRole("button", { name: /保存系统配置|save configs/i }).click();
    await expect(page.getByText(/已保存|saved/i)).toBeVisible();
    await page.reload();
    await page.getByRole("tab", { name: /配置|settings/i }).click();
    await expect(page.locator("textarea").first()).toHaveValue("Answer with a concise evidence checklist.");
  });

  test("upload, render source PDF, OCR-select, stream chat, and edit branch", async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    const pdfPath = process.env.PLAYWRIGHT_E2E_PDF_PATH;
    testInfo.skip(!pdfPath, "Set PLAYWRIGHT_E2E_PDF_PATH to run the document smoke.");
    await signIn(page);
    await page.getByRole("button", { name: /创建新工作区|create workspace/i }).click();
    const workspaceName = `pdf-e2e-${Date.now()}`;
    await page.locator('input[placeholder*="例如"]').fill(workspaceName);
    await page.getByRole("button", { name: /创建并进入/i }).click();
    await page.getByText(workspaceName, { exact: true }).click();
    await expect(page).toHaveURL(/\/workspaces\//);

    await page.locator('input[type="file"]').first().setInputFiles(pdfPath!);
    await page.locator('[data-asset-status="ready"]', { hasText: path.basename(pdfPath!) }).click({ timeout: 120_000 });
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 120_000 });
    await page.getByRole("button", { name: /新会话|new chat/i }).click();

    const question = process.env.PLAYWRIGHT_E2E_QUESTION ?? "Summarize the selected evidence.";
    await page.locator(".textLayer").first().evaluate((element) => {
      const textNode = element.firstChild;
      if (!textNode) return;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    });
    const askButton = page.getByRole("button", { name: /问 AI|ask ai/i });
    await expect(askButton).toBeVisible();
    await askButton.click();
    await page.getByPlaceholder(/针对当前工作区|ask about/i).fill(question);
    await page.getByRole("button", { name: /发送|send/i }).click();
    await expect(page.locator('[data-chat-message="assistant"]').last()).toContainText(/.+/, { timeout: 120_000 });

    const userMessage = page.locator('[data-chat-message="user"]').first();
    const editButton = userMessage.getByRole("button", { name: "编辑问题" });
    await expect(editButton).toBeVisible();
    await editButton.click();
    const editor = userMessage.locator("textarea");
    await expect(editor).toBeVisible();
    await editor.fill(`${question} with one more caveat`);
    await editor.press("Control+Enter");
    await expect(page.locator('[data-chat-message="assistant"]').last()).toContainText(/.+/, { timeout: 120_000 });
  });

  test("current image recovers from generation drift and preserves touch and Escape behavior", async ({ page }, testInfo) => {
    testInfo.skip(
      !imageWorkspaceId || !imageAssetId,
      "Set PLAYWRIGHT_E2E_IMAGE_WORKSPACE_ID and PLAYWRIGHT_E2E_IMAGE_ASSET_ID to run the image Viewer smoke.",
    );
    const imageBytes = readFileSync(path.resolve(
      process.cwd(),
      "../../docs/fixtures/evidence-contract/image-coordinate-fixture.png",
    ));
    let detailRequests = 0;
    let recoveryDetailRequests = 0;
    let generationDriftObserved = false;
    const currentGenerations: string[] = [];
    const assetSummary = {
      id: imageAssetId!,
      workspaceId: imageWorkspaceId!,
      kind: "image",
      title: "Synthetic Image Evidence Fixture",
      sourceFilename: "image-coordinate-fixture.png",
      mimeType: "image/png",
      byteSize: imageBytes.byteLength,
      status: "ready",
      currentIndexVersion: 1,
      lastErrorCode: null,
      lastErrorMessage: null,
      createdAt: "2026-07-18T00:00:00Z",
      updatedAt: "2026-07-18T00:00:00Z",
    };

    await page.route(
      `**/api/workspaces/${imageWorkspaceId}/assets/${imageAssetId}`,
      async (route) => {
        detailRequests += 1;
        const generation = generationDriftObserved ? 2 : 1;
        if (generationDriftObserved) {
          recoveryDetailRequests += 1;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            asset: { ...assetSummary, currentProcessingGeneration: generation },
            detail: {
              kind: "image",
              widthPixels: 1200,
              heightPixels: 800,
              orientationApplied: true,
            },
          }),
        });
      },
    );
    await page.route(
      `**/api/workspaces/${imageWorkspaceId}/assets/${imageAssetId}/representations/current-image-oriented/file?*`,
      async (route) => {
        const generation = new URL(route.request().url()).searchParams.get("processingGeneration") ?? "";
        currentGenerations.push(generation);
        if (generation === "1") {
          generationDriftObserved = true;
          await route.fulfill({
            status: 409,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Current image representation changed. Reload the asset detail." }),
          });
          return;
        }
        await route.fulfill({ status: 200, contentType: "image/png", body: imageBytes });
      },
    );

    const loginResponse = await page.context().request.post("/api/auth/login", {
      data: { email, password },
    });
    expect(loginResponse.ok()).toBeTruthy();
    await page.goto(`/workspaces/${imageWorkspaceId}`);
    await expect(page.getByText("image-coordinate-fixture.png").first()).toBeVisible({ timeout: 30_000 });
    await page.getByText("image-coordinate-fixture.png").first().click();
    await expect(page.locator('[data-image-viewer-error="error"]')).toBeVisible();
    await page.getByRole("button", { name: /重试|retry/i }).click();
    await expect(page.locator("[data-image-viewer] img")).toBeVisible();
    await expect(page.locator('[data-image-viewer-error="error"]')).toHaveCount(0);
    await expect.poll(() => recoveryDetailRequests).toBe(1);
    expect(detailRequests).toBeGreaterThanOrEqual(2);
    expect(currentGenerations).toEqual(["1", "2"]);
    await expect(page.locator("[data-image-viewer] img")).toHaveAttribute(
      "src",
      /current-image-oriented\/file\?processingGeneration=2$/,
    );

    await page.locator("[data-image-actual-size]").click();
    const viewport = page.locator("[data-image-viewport]");
    await viewport.evaluate((element) => {
      element.scrollLeft = 200;
      element.scrollTop = 100;
    });
    const surfaceBounds = await page.locator("[data-image-surface]").boundingBox();
    if (!surfaceBounds) {
      throw new Error("Image surface is unavailable.");
    }
    const cdp = await page.context().newCDPSession(page);
    const startX = surfaceBounds.x + Math.min(320, surfaceBounds.width / 2);
    const startY = surfaceBounds.y + Math.min(240, surfaceBounds.height / 2);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: startX, y: startY, id: 0 }],
    });
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: startX - 80, y: startY - 60, id: 0 }],
    });
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await expect.poll(() => viewport.evaluate((element) => element.scrollLeft)).toBe(280);
    await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBe(160);

    await page.locator("[data-image-fit]").click();
    const selectionButton = page.locator("[data-image-region-select]");
    await selectionButton.click();
    await page.locator("[data-image-surface]").focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Shift+ArrowRight");
    await expect(page.locator("[data-image-selected-region]")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-image-viewer]")).toBeVisible();
    await expect(page.locator("[data-image-selected-region]")).toHaveCount(0);
    await expect(selectionButton).toHaveAttribute("aria-pressed", "false");
  });
});
