import { expect, test, type Page, type APIResponse } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import type { MutationReceipt, CorrectionReceipt, AvailableMemory, Page as MemoryPage, InstructionSource } from "../src/lib/memory/types";

type Account = { email: string; password: string; id: string };
type Access = { owner: Account; member: Account; other: Account; workspaceId: string; workspaceName: string };
type Network = { actor: string; method: string; path: string; status: number };
const root = path.resolve(__dirname, "../../..");
const evidence = path.join(root, "specs/v5/memory-management/evidence/issue46/live");
const enabled = process.env.MEMORY_LIVE === "1";
test.use({ trace: "off", screenshot: "off", video: "off" });
test.describe.configure({ mode: "serial" });

async function access(): Promise<Access> {
  return JSON.parse((await readFile(path.join(root, ".local-runtime/issue46-management-ui/access.json"), "utf8")).replace(/^\uFEFF/, ""));
}
function observe(page: Page, actor: string, network: Network[]) {
  page.on("response", response => {
    const url = new URL(response.url());
    if (/\/api\/workspaces\/[^/]+\/(memories|sources\/read)/.test(url.pathname)) {
      network.push({ actor, method: response.request().method(), path: url.pathname + url.search, status: response.status() });
    }
  });
}
async function signedIn(page: Page, account: Account) {
  await page.goto("/");
  await page.locator('input[autocomplete="email"]').fill(account.email);
  await page.locator('input[type="password"]').fill(account.password);
  await page.locator('button[type="submit"]').click();
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
}
async function enter(page: Page, scope: Access) {
  await page.getByRole("heading", { name: scope.workspaceName, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/workspaces/${scope.workspaceId}$`));
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
}
const button = (page: Page, name: RegExp) => page.getByRole("button", { name });
const content = (page: Page) => page.getByLabel(/内容.*1–4000|Content.*1–4000/);
async function create(page: Page, subject: string, wording: string): Promise<AvailableMemory> {
  await button(page, /新增记忆|Create memory/).click();
  await page.getByLabel(/主体|Subject/).fill(subject);
  await page.getByLabel(/适用条件|Applicability/).fill("Only synthetic runtime acceptance reports");
  await content(page).fill(wording);
  const response = page.waitForResponse(r => r.request().method() === "POST" && /\/memories$/.test(new URL(r.url()).pathname));
  await button(page, /^保存$|^Save$/).click();
  const result = await response;
  expect(result.status()).toBe(201);
  const receipt = await result.json() as MutationReceipt;
  expect(receipt.memory.contentAvailable).toBe(true);
  await expect(page.getByText(wording, { exact: true })).toBeVisible();
  return receipt.memory as AvailableMemory;
}
async function snapshot(page: Page, name: string) {
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true });
}
function recordHTTP(response: APIResponse, actor: string, method: string, network: Network[]) {
  const url = new URL(response.url());
  network.push({ actor, method, path: url.pathname + url.search, status: response.status() });
}

test("live: normal sign-in, owner lifecycle, real conflict and member isolation", async ({ page, browser }) => {
  test.skip(!enabled, "Requires isolated real API/PostgreSQL runtime; no fixture fallback");
  test.setTimeout(180_000);
  const scope = await access();
  const network: Network[] = [];
  const label = `Runtime ${Date.now()}`;
  observe(page, "owner", network);
  const memberContext = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL });
  const otherContext = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL });
  try {
    await signedIn(page, scope.owner);
    await enter(page, scope);
    await expect(page.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
    await snapshot(page, "01-owner-empty");
    const original = await create(page, `${label} owner`, "Synthetic original statement: use concise owner reports.");
    await button(page, /^刷新$|^Refresh$/).click();
    await expect(page.getByText(original.content, { exact: true })).toBeVisible();
    await button(page, /原始来源 1|Original source 1/).click();
    await expect(page.getByRole("region", { name: /^原始来源$|^Original source$/ }).getByText(original.content, { exact: true })).toBeVisible();
    await snapshot(page, "02-original-source");

    const member = await memberContext.newPage();
    observe(member, "member", network);
    await signedIn(member, scope.member);
    await enter(member, scope);
    await expect(member.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
    const ownerRead = await member.request.get(`/api/workspaces/${scope.workspaceId}/memories/${original.id}`);
    recordHTTP(ownerRead, "member", "GET", network);
    expect(ownerRead.status()).toBe(404);
    const own = await create(member, `${label} member`, "Synthetic member statement remains isolated from the owner.");
    const memberRead = await page.request.get(`/api/workspaces/${scope.workspaceId}/memories/${own.id}`);
    recordHTTP(memberRead, "owner", "GET", network);
    expect(memberRead.status()).toBe(404);
    await button(page, /^刷新$|^Refresh$/).click();
    await expect(page.getByText(own.conditions.subject, { exact: true })).toHaveCount(0);
    await snapshot(member, "03-member-owned-memory");

    await button(page, /^更正$|^Correct$/).click();
    await content(page).fill("Synthetic corrected statement: use concise owner summaries.");
    const correctionResponse = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith(`/memories/${original.id}/corrections`));
    await button(page, /^保存$|^Save$/).click();
    const correction = await correctionResponse;
    expect(correction.status()).toBe(201);
    const corrected = await correction.json() as CorrectionReceipt;
    expect(corrected.supersededMemoryId).toBe(original.id);
    expect(corrected.memory.id).not.toBe(original.id);
    await expect(page.getByText("Synthetic corrected statement: use concise owner summaries.", { exact: true })).toBeVisible();
    await page.getByLabel(/^状态$|^Status$/).selectOption("superseded");
    await button(page, new RegExp(`${label} owner`)).click();
    const predecessorCurrent = page.getByRole("region", { name: /^当前记录$|^Current record$/ });
    await expect(predecessorCurrent.getByText(original.content, { exact: true })).toBeVisible();
    const historyResponse = page.waitForResponse(r => r.request().method() === "GET" && new URL(r.url()).pathname.endsWith(`/memories/${original.id}/revisions`));
    await button(page, /修订历史|Revision history/).click();
    const historyHTTP = await historyResponse;
    expect(historyHTTP.status()).toBe(200);
    const history = await historyHTTP.json() as MemoryPage;
    expect(history.nextCursor).toBeNull();
    expect(history.items).toHaveLength(2);
    expect(history.items.map(item => ({ id: item.id, version: item.version, intent: item.intent, validity: item.validity }))).toEqual([
      { id: original.id, version: original.version, intent: "active", validity: "valid" },
      { id: original.id, version: original.version + 1, intent: "superseded", validity: "valid" },
    ]);
    for (const revision of history.items) {
      expect(revision.contentAvailable).toBe(true);
      if (!revision.contentAvailable) throw new Error("Predecessor history unexpectedly unavailable");
      expect(revision.content).toBe(original.content);
      expect(revision.conditions).toEqual(original.conditions);
      expect(revision.sourceRefs).toEqual(original.sourceRefs);
    }
    const historyRegion = page.getByRole("region", { name: /^修订历史$|^Revision history$/ });
    await expect(historyRegion.getByText(original.content, { exact: true })).toHaveCount(2);
    await expect(historyRegion.getByText(/生效.*版本 1|Active.*Version 1/)).toBeVisible();
    await expect(historyRegion.getByText(/已更正.*版本 2|Superseded.*Version 2/)).toBeVisible();
    await snapshot(page, "04-predecessor-history");
    const sourceResponse = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/sources/read"));
    await historyRegion.getByRole("button", { name: /原始来源 1.*版本 1|Original source 1.*Version 1/ }).click();
    const sourceHTTP = await sourceResponse;
    expect(sourceHTTP.request().postDataJSON()).toEqual({ sourceRef: original.sourceRefs[0] });
    expect(sourceHTTP.status()).toBe(200);
    const exactSource = await sourceHTTP.json() as InstructionSource;
    expect(exactSource.sourceRef).toEqual(original.sourceRefs[0]);
    expect(exactSource.content).toBe(original.content);
    expect(exactSource.provenance).toMatchObject({ actorUserId: scope.owner.id, role: "user", actorAttribution: "authenticated", confirmation: "explicit_remember" });
    await expect(page.getByRole("region", { name: /^原始来源$|^Original source$/ }).getByText(original.content, { exact: true })).toBeVisible();
    page.on("dialog", dialog => dialog.accept());
    const predecessorDelete = page.waitForResponse(r => r.request().method() === "DELETE" && new URL(r.url()).pathname.endsWith(`/memories/${original.id}`));
    await button(page, /^删除$|^Delete$/).click();
    const predecessorDeleted = await predecessorDelete;
    expect(predecessorDeleted.status()).toBe(200);
    expect(predecessorDeleted.request().postDataJSON().expectedVersion).toBe(original.version + 1);
    await expect(page.getByText(original.content, { exact: true })).toHaveCount(0);
    await expect(historyRegion).toHaveCount(0);
    await expect(page.getByRole("region", { name: /^原始来源$|^Original source$/ })).toHaveCount(0);
    for (const suffix of ["", "/revisions?limit=30"]) {
      const denied = await page.request.get(`/api/workspaces/${scope.workspaceId}/memories/${original.id}${suffix}`);
      recordHTTP(denied, "owner-deleted-predecessor", "GET", network);
      expect(denied.status()).toBe(410);
      expect((await denied.json()).detail.code).toBe("erased");
    }
    const erasedSource = await page.request.post(`/api/workspaces/${scope.workspaceId}/sources/read`, { data: { sourceRef: original.sourceRefs[0] } });
    recordHTTP(erasedSource, "owner-deleted-predecessor", "POST", network);
    expect(erasedSource.status()).toBe(410);
    expect((await erasedSource.json()).detail.code).toBe("source_version_unavailable");
    await page.getByLabel(/^状态$|^Status$/).selectOption("active");
    await button(page, new RegExp(`${label} owner`)).click();
    await expect(page.getByText("Synthetic corrected statement: use concise owner summaries.", { exact: true })).toBeVisible();

    await button(page, /^更正$|^Correct$/).click();
    const draft = "My unsent synthetic conflict draft";
    await content(page).fill(draft);
    const competitorContent = "Synthetic concurrent correction committed by the same owner.";
    const concurrent = await page.request.post(`/api/workspaces/${scope.workspaceId}/memories/${corrected.memory.id}/corrections`, {
      headers: { "Idempotency-Key": randomUUID() },
      data: { requestId: randomUUID(), expectedVersion: corrected.memory.version, kind: "constraint", content: competitorContent, conditions: { ...original.conditions, effectiveFrom: "2026-01-01T00:00:00Z" }, pinned: true, validUntil: "2099-12-31T00:00:00Z" },
    });
    recordHTTP(concurrent, "owner-concurrent", "POST", network);
    expect(concurrent.status()).toBe(201);
    const competitor = await concurrent.json() as CorrectionReceipt;
    expect(competitor.supersededMemoryId).toBe(corrected.memory.id);
    expect(competitor.memory.id).not.toBe(corrected.memory.id);
    expect(competitor.memory.version).toBe(1);
    const conflictResponse = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith(`/memories/${corrected.memory.id}/corrections`));
    await button(page, /^保存$|^Save$/).click();
    const failedCorrection = await conflictResponse;
    expect(failedCorrection.status()).toBe(409);
    expect((await failedCorrection.json()).detail.code).toBe("version_conflict");
    expect(failedCorrection.request().postDataJSON()).toMatchObject({ expectedVersion: corrected.memory.version, content: draft });
    await expect(content(page)).toHaveValue(draft);
    await button(page, /^刷新$|^Refresh$/).click();
    await expect(content(page)).toHaveValue(draft);
    const staleTarget = await page.request.get(`/api/workspaces/${scope.workspaceId}/memories/${corrected.memory.id}`);
    recordHTTP(staleTarget, "owner-conflict-read", "GET", network);
    expect(staleTarget.status()).toBe(200);
    expect((await staleTarget.json()).memory).toMatchObject({ id: corrected.memory.id, version: corrected.memory.version + 1, intent: "superseded" });
    await expect(button(page, /使用当前版本|Use current version/)).toHaveCount(0);
    await expect(button(page, /^保存$|^Save$/)).toBeDisabled();
    await snapshot(page, "05-real-correction409-terminal-draft");
    const comparisonWrites: string[] = [];
    const captureWrites = (request: import("@playwright/test").Request) => {
      if (["POST", "PATCH", "DELETE"].includes(request.method()) && new URL(request.url()).pathname.includes("/memories")) comparisonWrites.push(request.method());
    };
    page.on("request", captureWrites);
    await button(page, new RegExp(`${label} owner`)).click();
    const comparison = page.getByRole("region", { name: /后继比较|Successor comparison/ });
    await expect(comparison).toBeVisible();
    await expect(comparison.getByText(competitorContent, { exact: true })).toBeVisible();
    await expect(comparison).toContainText(corrected.memory.id);
    await expect(comparison).toContainText(competitor.memory.id);
    await expect(comparison.getByText(/已更正.*版本 2|Superseded.*Version 2/)).toBeVisible();
    await expect(content(page)).toHaveValue(draft);
    await expect(button(page, /^保存$|^Save$/)).toBeDisabled();
    await button(page, /继续编辑此后继|Continue on this successor/).click();
    await expect(content(page)).toHaveValue(draft);
    await expect(button(page, /^保存$|^Save$/)).toBeEnabled();
    expect(comparisonWrites).toEqual([]);
    page.off("request", captureWrites);
    const resaveResponse = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith(`/memories/${competitor.memory.id}/corrections`));
    await button(page, /^保存$|^Save$/).click();
    const resave = await resaveResponse;
    expect(resave.status()).toBe(201);
    const savedBody = resave.request().postDataJSON();
    expect(savedBody).toEqual({ requestId: expect.any(String), expectedVersion: competitor.memory.version, kind: "preference", content: draft, conditions: original.conditions, pinned: false, validUntil: null });
    expect(savedBody.requestId).not.toBe(failedCorrection.request().postDataJSON().requestId);
    expect(resave.request().headers()["idempotency-key"]).not.toBe(failedCorrection.request().headers()["idempotency-key"]);
    const recovered = await resave.json() as CorrectionReceipt;
    expect(recovered.supersededMemoryId).toBe(competitor.memory.id);
    expect(recovered.memory.id).not.toBe(competitor.memory.id);
    expect(recovered.memory.id).not.toBe(corrected.memory.id);
    expect(recovered.memory.version).toBe(1);
    await expect(content(page)).toHaveCount(0);
    await expect(page.getByText(draft, { exact: true })).toBeVisible();
    await snapshot(page, "05b-explicit-successor-resave");
    const deactivateResponse = page.waitForResponse(r => r.request().method() === "PATCH" && new URL(r.url()).pathname.endsWith(`/memories/${recovered.memory.id}`));
    await button(page, /^停用$|^Deactivate$/).click();
    expect((await deactivateResponse).status()).toBe(200);
    await page.getByLabel(/^状态$|^Status$/).selectOption("inactive");
    await button(page, new RegExp(`${label} owner`)).click();
    await expect(button(page, /^停用$|^Deactivate$/)).toHaveCount(0);
    const deleteResponse = page.waitForResponse(r => r.request().method() === "DELETE" && new URL(r.url()).pathname.endsWith(`/memories/${recovered.memory.id}`));
    await button(page, /^删除$|^Delete$/).click();
    expect((await deleteResponse).status()).toBe(200);
    await expect(page.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
    const erased = await page.request.get(`/api/workspaces/${scope.workspaceId}/memories/${recovered.memory.id}`);
    recordHTTP(erased, "owner", "GET", network);
    expect(erased.status()).toBe(410);
    await page.getByLabel(/^状态$|^Status$/).selectOption("deleted");
    await expect(button(page, /内容已擦除|Content erased/)).toHaveCount(2);
    await snapshot(page, "06-deleted-tombstone");

    const other = await otherContext.newPage();
    await signedIn(other, scope.other);
    await enter(other, scope);
    const forbidden = await other.request.get(`/api/workspaces/${scope.workspaceId}/memories/${original.id}`);
    recordHTTP(forbidden, "other-member", "GET", network);
    expect(forbidden.status()).toBe(404);
    member.on("dialog", dialog => dialog.accept());
    await button(member, /^删除$|^Delete$/).click();
    await expect(member.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
  } finally {
    await mkdir(evidence, { recursive: true });
    await writeFile(path.join(evidence, "lifecycle-network.json"), JSON.stringify(network, null, 2));
    await memberContext.close();
    await otherContext.close();
  }
});


const runtime = path.join(root, ".local-runtime/issue46-management-ui");
type Triple = { method: string; path: string; body: string; requestId: string; key: string };
async function faults(value: { dropNextMutation?: boolean; dropPolls?: boolean }) {
  await writeFile(path.join(runtime, "fault.json"), JSON.stringify(value));
}
async function homeAndBack(page: Page, scope: Access) {
  await page.locator('a[href="/"]').click();
  await expect(page).toHaveURL(/\/$/);
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/workspaces/${scope.workspaceId}$`));
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
}
function mutationTriples(page: Page, memoryPath: string) {
  const triples: Triple[] = [];
  page.on("request", request => {
    if (request.method() !== "PATCH" || new URL(request.url()).pathname !== memoryPath) return;
    const body = request.postData();
    if (!body) throw new Error("Mutation request has no body");
    triples.push({ method: request.method(), path: memoryPath, body, requestId: JSON.parse(body).requestId, key: request.headers()["idempotency-key"] });
  });
  return triples;
}
async function saveNetwork(name: string, network: Network[], assertions: Record<string, unknown>) {
  await mkdir(evidence, { recursive: true });
  await writeFile(path.join(evidence, `${name}.json`), JSON.stringify({ scope: "Real API/PG via Next BFF; automated UI, not external controller acceptance", network, assertions }, null, 2));
}

test("live: unknown acknowledgement retains original triple across Home Back and explicit retry", async ({ page }) => {
  test.skip(!enabled, "Requires authorized isolated live runtime and real transport proxy");
  test.setTimeout(120_000);
  const scope = await access();
  const network: Network[] = [];
  const assertions: Record<string, unknown> = {};
  observe(page, "owner", network);
  try {
    await faults({});
    await signedIn(page, scope.owner);
    await enter(page, scope);
    const original = await create(page, `Unknown retry ${Date.now()}`, "Synthetic original unknown-outcome statement.");
    const memoryPath = `/api/workspaces/${scope.workspaceId}/memories/${original.id}`;
    const triples = mutationTriples(page, memoryPath);
    await faults({ dropNextMutation: true, dropPolls: true });
    await button(page, /^停用$|^Deactivate$/).click();
    await expect(button(page, /重试原请求|Retry original request/)).toBeEnabled();
    expect(triples).toHaveLength(1);
    const events = (await readFile(path.join(runtime, "fault-events.jsonl"), "utf8")).trim().split(/\r?\n/).map(line => JSON.parse(line));
    expect(events.some(event => event.method === "PATCH" && event.path === `/v1/workspaces/${scope.workspaceId}/memories/${original.id}` && event.committedUpstreamStatus === 200 && event.dropped === true)).toBe(true);
    assertions.originalMutationCommittedBeforeAcknowledgementDrop = true;
    const first = triples[0];
    expect(first.requestId).toBeTruthy();
    expect(first.key).toBeTruthy();
    expect(JSON.parse(first.body)).toEqual({ expectedVersion: original.version, intent: "inactive", requestId: first.requestId });
    await expect(page.getByText(first.requestId, { exact: true })).toBeVisible();
    await homeAndBack(page, scope);
    await expect(page.getByText(first.requestId, { exact: true })).toBeVisible();
    await expect(button(page, /新增记忆|Create memory/)).toBeDisabled();
    // Observe beyond one polling interval while only poll responses are dropped.
    await page.waitForTimeout(3000);
    expect(triples).toHaveLength(1);
    assertions.noAutomaticResendAfterHomeBack = true;
    const replayResponse = page.waitForResponse(response => response.request().method() === "PATCH" && new URL(response.url()).pathname === memoryPath);
    await button(page, /重试原请求|Retry original request/).click();
    const replay = await replayResponse;
    expect(replay.status()).toBe(200);
    expect(triples).toHaveLength(2);
    expect(triples[1]).toEqual(first);
    const receipt = await replay.json() as MutationReceipt;
    expect(receipt.resultVersion).toBe(original.version + 1);
    assertions.exactMethodPathBodyRequestIdAndKeyRetained = true;
    await faults({});
    const operation = await page.request.get(`/api/workspaces/${scope.workspaceId}/memories/requests/${first.requestId}`);
    recordHTTP(operation, "owner", "GET", network);
    expect(operation.status()).toBe(200);
    const accepted = await operation.json();
    expect(accepted.operationId).toBe(receipt.operationId);
    expect(accepted.resourceId).toBe(original.id);
    expect(accepted.resultVersion).toBe(original.version + 1);
    expect(accepted.currentVersion).toBe(original.version + 1);
    const current = await page.request.get(memoryPath);
    recordHTTP(current, "owner", "GET", network);
    expect(current.status()).toBe(200);
    expect((await current.json()).memory.version).toBe(original.version + 1);
    assertions.replayMatchesAcceptedOperationWithoutSecondVersionAdvance = true;
    await expect(button(page, /重试原请求|Retry original request/)).toHaveCount(0);
    await snapshot(page, "07-unknown-reconciled");
    page.on("dialog", dialog => dialog.accept());
    const deleted = page.waitForResponse(response => response.request().method() === "DELETE" && new URL(response.url()).pathname === memoryPath);
    await button(page, /^删除$|^Delete$/).click();
    expect((await deleted).status()).toBe(200);
  } finally {
    await faults({});
    await saveNetwork("unknown-home-back-network", network, assertions);
  }
});


async function memberAccess(action: "revoke" | "restore") {
  const python = process.env.MEMORY_RUNTIME_PYTHON;
  if (!python) throw new Error("MEMORY_RUNTIME_PYTHON must name the lane Python with its PostgreSQL driver");
  const environment = JSON.parse((await readFile(path.join(runtime, "environment.json"), "utf8")).replace(/^\uFEFF/, ""));
  await new Promise<void>((resolve, reject) => {
    execFile(python, ["-B", path.join(runtime, "membership.py"), action], {
      env: { ...process.env, AI_PDF_DATABASE_URL: environment.AI_PDF_DATABASE_URL, PYTHONDONTWRITEBYTECODE: "1" }, windowsHide: true,
    }, error => error ? reject(new Error(`Isolated membership ${action} failed; inspect local runtime privately`)) : resolve());
  });
}

test("live upstream + held real transport: revocation fences an accepted late poll and clears pending draft", async ({ page }) => {
  test.skip(!enabled, "Requires authorized isolated live runtime and real transport proxy");
  test.setTimeout(120_000);
  const scope = await access();
  const network: Network[] = [];
  const assertions: Record<string, unknown> = { transport: "Only request lookup response held in test RAM after actual Next/API200; exact APIResponse released unchanged" };
  let revoked = false;
  let release: (() => void) | undefined;
  let heldRequestId: string | undefined;
  let releaseAttempted = false;
  let releaseOutcome: "accepted-by-route" | "request-canceled" | undefined;
  observe(page, "member", network);
  try {
    await faults({});
    await signedIn(page, scope.member);
    await enter(page, scope);
    const original = await create(page, `Revocation race ${Date.now()}`, "Synthetic private body must disappear after real membership revocation.");
    const draft = "Synthetic unsent correction removed by real revocation";
    await button(page, /^更正$|^Correct$/).click();
    await content(page).fill(draft);
    const memoryPath = `/api/workspaces/${scope.workspaceId}/memories/${original.id}`;
    const triples = mutationTriples(page, memoryPath);
    const hold = new Promise<void>(resolve => { release = resolve; });
    await page.route(`**/api/workspaces/${scope.workspaceId}/memories/requests/*`, async route => {
      const actual = await route.fetch();
      expect(actual.status()).toBe(200);
      const accepted = await actual.json();
      expect(triples).toHaveLength(1);
      expect(accepted.requestId).toBe(triples[0].requestId);
      expect(accepted.resourceId).toBe(original.id);
      expect(accepted.state).toBe("committed");
      recordHTTP(actual, "member-real-upstream-held", "GET", network);
      heldRequestId = accepted.requestId;
      await hold;
      releaseAttempted = true;
      // Preserve the actual status, headers and bytes; never synthesize success.
      try {
        await route.fulfill({ response: actual });
        releaseOutcome = "accepted-by-route";
      } catch (error) {
        const failure = route.request().failure()?.errorText;
        const expectedCancellation = failure && /ERR_ABORTED|cancell?ed|aborted/i.test(failure)
          && error instanceof Error && /cancell?ed|aborted|Invalid InterceptionId/i.test(error.message);
        if (!expectedCancellation) throw error;
        releaseOutcome = "request-canceled";
      }
    });
    await faults({ dropNextMutation: true });
    await button(page, /^停用$|^Deactivate$/).click();
    await expect(button(page, /重试原请求|Retry original request/)).toBeEnabled();
    await expect.poll(() => heldRequestId).toBeTruthy();
    const requestId = heldRequestId!;
    await expect(content(page)).toHaveValue(draft);
    revoked = true;
    await memberAccess("revoke");
    const denied = page.waitForResponse(response => response.request().method() === "GET" && new URL(response.url()).pathname === `/api/workspaces/${scope.workspaceId}/memories` && response.status() === 404);
    await button(page, /^刷新$|^Refresh$/).click();
    await denied;
    const accessLost = page.getByRole("alert").filter({ hasText: /访问已失效|Access lost/ });
    await expect(accessLost).toBeVisible();
    await expect(content(page)).toHaveCount(0);
    await expect(page.getByText(original.content, { exact: true })).toHaveCount(0);
    await expect(page.getByText(original.conditions.subject, { exact: true })).toHaveCount(0);
    await expect(page.getByText(requestId, { exact: true })).toHaveCount(0);
    await expect(button(page, /重试原请求|Retry original request/)).toHaveCount(0);
    release?.();
    await expect.poll(() => releaseAttempted).toBe(true);
    await expect.poll(() => releaseOutcome).toBeTruthy();
    assertions.releaseAttempted = true;
    assertions.transportReleaseOutcome = releaseOutcome;
    assertions.browserDeliveryClaimed = false;
    await page.waitForTimeout(3000);
    await expect(accessLost).toBeVisible();
    await expect(content(page)).toHaveCount(0);
    await expect(page.getByText(original.content, { exact: true })).toHaveCount(0);
    await expect(page.getByText(requestId, { exact: true })).toHaveCount(0);
    expect(triples).toHaveLength(1);
    assertions.realRevocationClearsDraftAndPending = true;
    assertions.latePreviouslyAcceptedPollCannotRestorePrivateViewOrResend = true;
    await snapshot(page, "08-revoked-late-poll");
    await memberAccess("restore");
    revoked = false;
    await faults({});
    await homeAndBack(page, scope);
    await expect(accessLost).toBeVisible();
    await expect(button(page, /重试原请求|Retry original request/)).toHaveCount(0);
    await expect(content(page)).toHaveCount(0);
    expect(triples).toHaveLength(1);
    assertions.sameSessionHomeBackDoesNotResurrectRevokedState = true;
    const cleanup = await page.request.delete(memoryPath, {
      headers: { "Idempotency-Key": randomUUID() }, data: { requestId: randomUUID(), expectedVersion: original.version + 1 },
    });
    recordHTTP(cleanup, "member-restored-cleanup", "DELETE", network);
    expect(cleanup.status()).toBe(200);
  } finally {
    release?.();
    try {
      if (revoked) await memberAccess("restore");
    } finally {
      await faults({});
      await saveNetwork("revocation-held-real-poll-network", network, assertions);
    }
  }
});
