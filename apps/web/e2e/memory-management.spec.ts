import { expect, test, type Page, type Route } from "@playwright/test";
import type { AvailableMemory } from "../src/lib/memory/types";
const workspaceId = "00000000-0000-0000-0000-000000000046";
const memoryId = "00000000-0000-0000-0000-000000000001";
const sourceRef = { sourceId: "00000000-0000-0000-0000-000000000002", sourceVersion: 1, contentSha256: "a".repeat(64), span: null };
const now = "2026-09-28T00:00:00Z";
const memory: AvailableMemory = { id: memoryId, workspaceId, ownerUserId: "fixture-user", visibility: "private", scope: { kind: "workspace", threadId: null, runId: null }, version: 1, revisionId: "00000000-0000-0000-0000-000000000003", intent: "active", validity: "valid", displayStatus: "active", kind: "preference", confirmation: "explicit_remember", conditions: { subject: "Synthetic owner preference", applicability: "Synthetic reports", effectiveFrom: null }, pinned: false, validUntil: null, supersedesId: null, createdAt: now, updatedAt: now, contentAvailable: true, content: "Use the exact synthetic wording.", sourceRefs: [sourceRef] };
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
const fixtureWorkspace = { id: workspaceId, name: "Memory fixture workspace", description: null, role: "member", systemPrompt: "", retrievalTopK: 6, chunkSize: 1200, embeddingProvider: "local", embeddingModel: "fixture", embeddingDimensions: 10, embeddingVersion: "v1", generationProvider: "local", generationModel: "fixture", assetCount: 0, noteCount: 0, threadCount: 0, createdAt: now, updatedAt: now };
async function shell(page: Page, role: "member" | "owner" = "member") {
  await page.route("**/api/auth/session", route => json(route, { user: { userId: "fixture-user", name: "Fixture", email: "fixture@example.invalid", avatarUrl: "" } }));
  await page.route("**/api/workspaces", route => json(route, { items: [{ ...fixtureWorkspace, role }], nextCursor: null }));
  for (const suffix of ["assets", "threads", "notes", "tags", "research-runs"]) await page.route(`**/api/workspaces/${workspaceId}/${suffix}**`, route => json(route, { items: [], nextCursor: null }));
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    if (new URL(route.request().url()).pathname.endsWith(`/memories/${memoryId}`)) return json(route, { memory });
    return json(route, { items: [memory], nextCursor: null });
  });
}
async function enter(page: Page) {
  await page.goto(`/workspaces/${workspaceId}`);
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
}
for (const role of ["member", "owner"] as const) {
  test(`fixture: ${role} enters native Settings memory and submits the exact create statement`, async ({ page }) => {
    await shell(page, role);
    const submissions: { body: Record<string, unknown>; key: string }[] = [];
    const created = { ...memory, conditions: { subject: "Unsent synthetic draft", applicability: "Only fixture reports", effectiveFrom: null }, content: "Unsent wording" };
    await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
      const request = route.request();
      if (request.method() === "POST") {
        submissions.push({ body: request.postDataJSON(), key: request.headers()["idempotency-key"] });
        return json(route, { requestId: request.postDataJSON().requestId, operationId: sourceRef.sourceId, resultVersion: 1, memory: created, indexState: "not_enabled" }, 201);
      }
      return json(route, new URL(request.url()).pathname.endsWith(memoryId) ? { memory: created } : { items: submissions.length ? [created] : [], nextCursor: null });
    });
    await enter(page);
    await expect(page.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
    await page.getByRole("button", { name: /新增记忆|Create memory/ }).click();
    await page.getByLabel(/主体|Subject/).fill("Unsent synthetic draft");
    await page.getByLabel(/适用条件|Applicability/).fill("Only fixture reports");
    await page.getByLabel(/内容.*1–4000|Content.*1–4000/).fill("Unsent wording");
    await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeEnabled();
    await expect(page.getByText(/等待 API 集成验收|pending accepted API integration/)).toHaveCount(0);
    await page.getByRole("tab", { name: /^工作区$|^Workspace$/ }).click();
    await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
    await expect(page.getByLabel(/主体|Subject/)).toHaveValue("Unsent synthetic draft");
    await page.getByRole("button", { name: /^保存$|^Save$/ }).click();
    await expect(page.getByText("Unsent wording", { exact: true })).toBeVisible();
    expect(submissions).toHaveLength(1);
    expect(submissions[0].key).toBeTruthy();
    expect(submissions[0].body).toEqual({ requestId: expect.any(String), kind: "preference", content: created.content, conditions: created.conditions, pinned: false, validUntil: null, scope: { kind: "workspace" }, sourceRefs: [] });
  });
}
test("fixture: exact original source, revision page and list cursor", async ({ page }) => {
  await shell(page);
  const seen: string[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const url = new URL(route.request().url()); seen.push(url.search);
    if (url.pathname.endsWith("/revisions")) return json(route, { items: [memory], nextCursor: url.searchParams.has("cursor") ? null : "history-cursor" });
    if (url.pathname.endsWith(memoryId)) return json(route, { memory });
    return json(route, { items: [memory], nextCursor: url.searchParams.has("cursor") ? null : "list-cursor" });
  });
  await page.route(`**/api/workspaces/${workspaceId}/sources/read`, route => {
    expect(route.request().postDataJSON()).toEqual({ sourceRef });
    return json(route, { sourceRef, content: "Exact original synthetic instruction.", contentKind: "explicit_instruction", occurredAt: now, sourceState: "current", provenance: { role: "user", actorUserId: "fixture-user", actorAttribution: "authenticated", threadId: null, runId: null, parentMessageId: null, confirmation: "explicit_remember" }, branchRelation: "other_task", truncated: false, nextCursor: null });
  });
  await enter(page);
  await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
  await expect(page.getByText("Exact original synthetic instruction.")).toBeVisible();
  await page.getByRole("button", { name: /修订历史|Revision history/ }).click();
  const history = page.getByRole("region", { name: /修订历史|Revision history/ });
  await expect(history.getByText(memory.content)).toBeVisible();
  await history.getByRole("button", { name: /下一页|Next page/ }).click();
  await expect.poll(() => seen.some(q => q.includes("cursor=history-cursor"))).toBe(true);
  await page.getByRole("button", { name: /下一页|Next page/ }).click();
  await expect.poll(() => seen.some(q => q.includes("cursor=list-cursor"))).toBe(true);
});
test("fixture: ordinary PATCH conflict preserves draft without silently opening successor recovery", async ({ page }) => {
  await shell(page); let version = 1;
  await page.route(`**/api/workspaces/${workspaceId}/memories/${memoryId}`, route => {
    if (route.request().method() === "PATCH") { version = 2; return json(route, { detail: { code: "version_conflict", currentVersion: 2 } }, 409); }
    return json(route, { memory: { ...memory, version, intent: version === 1 ? "active" : "inactive", displayStatus: version === 1 ? "active" : "inactive" } });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
  await page.getByLabel(/内容.*1–4000|Content.*1–4000/).fill("My unsent correction");
  await page.getByRole("button", { name: /^停用$|^Deactivate$/ }).click();
  await expect(page.getByText("Memory version changed.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await expect(page.getByText(memory.content, { exact: true })).toBeVisible();
  await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveValue("My unsent correction");
  await expect(page.getByRole("button", { name: /继续编辑此后继|Continue on this successor/ })).toHaveCount(0);
});
test("fixture: lost acknowledgement polls and retries the unchanged request, then shows tombstone honestly", async ({ page }) => {
  await shell(page); let settled = false; let erased = false;
  const mutations: { body: string | null; key: string | undefined }[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const request = route.request(); const url = new URL(request.url());
    if (url.pathname.includes("/requests/")) {
      if (!settled) return json(route, { detail: { code: "operation_not_found" } }, 404);
      return json(route, { requestId: url.pathname.split("/").at(-1), accepted: true, operationId: "operation", state: "committed", resourceId: memoryId, resultVersion: 2, currentVersion: 3, intent: "deleted", contentAvailable: false, cleanupState: "completed" });
    }
    if (request.method() === "DELETE") {
      mutations.push({ body: request.postData(), key: request.headers()["idempotency-key"] });
      return json(route, { detail: { code: "outcome_unknown" } }, 503);
    }
    if (url.pathname.endsWith(memoryId)) return erased ? json(route, { detail: { code: "erased" } }, 410) : json(route, { memory });
    return json(route, { items: erased ? [{ id: memoryId, version: 3, intent: "deleted", validity: "valid", displayStatus: "deleted", contentAvailable: false, reason: "erased" }] : [memory], nextCursor: null });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: /^删除$|^Delete$/ }).click();
  await expect(page.getByRole("button", { name: /重试原请求|Retry original request/ })).toBeEnabled();
  await page.getByRole("button", { name: /重试原请求|Retry original request/ }).click();
  await expect.poll(() => mutations.length).toBe(2); expect(mutations[0]).toEqual(mutations[1]);
  await page.getByRole("tab", { name: /AI 问答|AI Chat/ }).click();
  await expect(page.getByRole("tab", { name: /AI 问答|AI Chat/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
  await expect(page.getByText(JSON.parse(mutations[0].body!).requestId, { exact: true })).toBeVisible();
  erased = true; settled = true;
  await expect(page.getByText(/本次操作版本 2.*当前版本 3|Operation result version 2.*Current version 3/)).toBeVisible();
  await expect(page.getByText(memory.content)).toHaveCount(0);
  await page.getByRole("button", { name: /内容已擦除|Content erased/ }).click();
  await expect(page.getByText("Memory content has been erased.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /撤销|Undo/ })).toHaveCount(0);
});
test("fixture: revocation clears private views and unsent draft", async ({ page }) => {
  await shell(page); await enter(page);
  await page.getByRole("button", { name: /新增记忆|Create memory/ }).click();
  await page.getByLabel(/主体|Subject/).fill("Private unsent draft");
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => json(route, { detail: { code: "workspace_not_found" } }, 404));
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: /访问已失效|Access lost/ })).toBeVisible();
  await expect(page.getByLabel(/主体|Subject/)).toHaveCount(0);
  await expect(page.getByText("Synthetic owner preference")).toHaveCount(0);
});

test("fixture: mobile memory preserves the existing compact shell", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await shell(page); await enter(page);
  await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await expect(page.getByText(memory.content)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.screenshot({ path: test.info().outputPath("fixture-mobile-memory.png"), fullPage: true });
});

test("fixture: logout ignores a delayed original-source response and removes drafts", async ({ page }) => {
  await shell(page); await page.route("**/api/auth/logout", route => json(route, {}));
  let release: (() => void) | undefined;
  let started = false;
  await page.route(`**/api/workspaces/${workspaceId}/sources/read`, async route => {
    started = true;
    await new Promise<void>(resolve => { release = resolve; });
    await json(route, { sourceRef, content: "Delayed private source must not flash" }).catch(() => {});
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /新增记忆|Create memory/ }).click();
  await page.getByLabel(/主体|Subject/).fill("Private unsent logout draft");
  await page.getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
  await expect.poll(() => started).toBe(true);
  await page.getByRole("button", { name: /退出登录|Log out|Logout/i }).click();
  await expect(page.getByRole("tab", { name: /^记忆$|^Memory$/ })).toHaveCount(0);
  release?.();
  await expect(page.getByText("Delayed private source must not flash")).toHaveCount(0);
  await expect(page.getByLabel(/主体|Subject/)).toHaveCount(0);
});

test("C1 regression: unreadable current projection clears copied private draft", async ({ page }) => {
  await shell(page); let unavailable = false;
  const suppressed = { id: memoryId, version: 2, intent: "active", validity: "valid", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" };
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const current = new URL(route.request().url()).pathname.endsWith(memoryId);
    return json(route, current ? { memory: unavailable ? suppressed : memory } : { items: unavailable ? [] : [memory], nextCursor: null });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
  await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveValue(memory.content);
  unavailable = true; await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await expect(page.getByRole("region", { name: /当前记录|Current record/ }).getByText(/原始来源不可用|Original source unavailable/)).toBeVisible();
  await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveCount(0);
});

test("C1 regression: erased history removes cached list subject", async ({ page }) => {
  await shell(page);
  await page.route(`**/api/workspaces/${workspaceId}/memories/${memoryId}/revisions**`, route => json(route, { detail: { code: "erased" } }, 410));
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /修订历史|Revision history/ }).click();
  await expect(page.getByText("Memory content has been erased.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toHaveCount(0);
});

test("C1 regression: same-workspace Home/back cannot silently abandon unresolved identity", async ({ page }) => {
  await shell(page); const requests: string[] = [];
  const triples: unknown[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const request=route.request(), path=new URL(request.url()).pathname;
    if (request.method()==="DELETE") { requests.push(request.postDataJSON().requestId); triples.push({ method: request.method(), path, body: request.postData(), key: request.headers()["idempotency-key"] }); return json(route,{detail:{code:"outcome_unknown"}},503); }
    if(path.includes("/requests/")) return json(route,{detail:{code:"operation_not_found"}},404);
    return json(route,path.endsWith(memoryId)?{memory}:{items:[memory],nextCursor:null});
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button",{name:/^删除$|^Delete$/}).click();
  await expect(page.getByRole("button",{name:/重试原请求|Retry original request/})).toBeEnabled();
  const original=requests[0]; await page.locator('a[href="/"]').click(); await page.waitForURL(url => url.pathname === "/", {timeout:5000});
  if (new URL(page.url()).pathname === "/") {
    await page.goBack();
    await page.getByRole("tab", { name: /配置|settings/i }).click();
    await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
  }
  await expect(page.getByText(original,{exact:true})).toBeVisible();
  expect(requests).toHaveLength(1);
  await page.getByRole("button", { name: /重试原请求|Retry original request/ }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(triples[1]).toEqual(triples[0]);
});



for (const code of ["source_version_unavailable", "source_not_found"] as const) {
  test(`R1 exact source ${code} removes all copied projections without claiming erasure`, async ({ page }) => {
    await shell(page);
    await page.route(`**/api/workspaces/${workspaceId}/sources/read`, route => json(route, { detail: { code } }, code === "source_not_found" ? 404 : 410));
    await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
    await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
    await page.getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
    await expect(page.getByRole("region", { name: /当前记录|Current record/ }).getByText(/原始来源不可用|Original source unavailable/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toHaveCount(0);
    await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveCount(0);
    await expect(page.getByText(/内容已擦除|Content erased/)).toHaveCount(0);
  });
}
test("R1 late list cannot restore an erased subject", async ({ page }) => {
  await shell(page); let held = false; let release: (() => void) | undefined;
  await page.route(url => url.pathname === `/api/workspaces/${workspaceId}/memories`, async route => {
    if (new URL(route.request().url()).searchParams.has("cursor")) {
      held = true; await new Promise<void>(resolve => { release = resolve; });
    }
    await json(route, { items: [memory], nextCursor: "late-page" }).catch(() => {});
  });
  await page.route(`**/api/workspaces/${workspaceId}/memories/${memoryId}/revisions**`, route => json(route, { detail: { code: "erased" } }, 410));
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /下一页|Next page/ }).click();
  await expect.poll(() => held).toBe(true);
  await page.getByRole("button", { name: /修订历史|Revision history/ }).click();
  await expect(page.getByText("Memory content has been erased.", { exact: true })).toBeVisible();
  release?.();
  await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toHaveCount(0);
});

const otherWorkspaceId = "00000000-0000-0000-0000-000000000047";
async function twoWorkspaces(page: Page) {
  await shell(page);
  await page.route("**/api/workspaces", route => json(route, { items: [fixtureWorkspace, { ...fixtureWorkspace, id: otherWorkspaceId, name: "Other scope" }], nextCursor: null }));
  for (const suffix of ["assets", "threads", "notes", "tags", "research-runs", "memories"]) await page.route(`**/api/workspaces/${otherWorkspaceId}/${suffix}**`, route => json(route, { items: [], nextCursor: null }));
}
async function homeTo(page: Page, name: string) {
  await page.locator('a[href="/"]').click();
  await page.waitForURL(url => url.pathname === "/");
  await page.getByText(name, { exact: true }).click();
  await page.waitForURL(url => url.pathname.startsWith("/workspaces/"));
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
}
for (const delayed of ["mutation", "poll"] as const) {
  test(`R2 explicit workspace change fences late ${delayed} and clears the old triple`, async ({ page }) => {
    await twoWorkspaces(page);
    let release: (() => void) | undefined;
    let waiting = false;
    let requestId = "";
    let mutations = 0;
    await page.route(`**/api/workspaces/${workspaceId}/memories**`, async route => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() === "PATCH") {
        mutations++; requestId = request.postDataJSON().requestId;
        if (delayed === "poll") return json(route, { detail: { code: "outcome_unknown" } }, 503);
        waiting = true; await new Promise<void>(resolve => { release = resolve; });
        return json(route, { requestId, operationId: memoryId, resultVersion: 2, memory: { ...memory, version: 2, intent: "inactive", displayStatus: "inactive", content: "Late old-scope mutation body" }, indexState: "not_enabled" }).catch(() => {});
      }
      if (url.pathname.includes("/requests/")) {
        waiting = true; await new Promise<void>(resolve => { release = resolve; });
        return json(route, { requestId, accepted: true, operationId: memoryId, state: "committed", resourceId: memoryId, resultVersion: 2, currentVersion: 2, intent: "inactive", contentAvailable: true, cleanupState: "not_required" }).catch(() => {});
      }
      return json(route, url.pathname.endsWith(memoryId) ? { memory } : { items: [memory], nextCursor: null });
    });
    await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
    await page.getByRole("button", { name: /^停用$|^Deactivate$/ }).click();
    await expect.poll(() => waiting).toBe(true);
    const original = requestId;
    await homeTo(page, "Other scope");
    await expect(page.getByText(original, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /新增记忆|Create memory/ })).toBeEnabled();
    release?.();
    await expect(page.getByText("Late old-scope mutation body")).toHaveCount(0);
    await homeTo(page, "Memory fixture workspace");
    await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toBeVisible();
    await expect(page.getByText(original, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /重试原请求|Retry original request/ })).toHaveCount(0);
    expect(mutations).toBe(1);
  });
}
test("R2 logout and actor change cannot adopt an old accepted poll", async ({ page }) => {
  await shell(page);
  let release: (() => void) | undefined; let waiting = false; let requestId = ""; let actorB = false;
  await page.route("**/api/auth/logout", route => json(route, {}));
  await page.route("**/api/auth/login", route => {
    actorB = true;
    return json(route, { user: { id: "actor-b", name: "Actor B", email: "b@example.invalid", avatarUrl: "" } });
  });
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "PATCH") { requestId = request.postDataJSON().requestId; return json(route, { detail: { code: "outcome_unknown" } }, 503); }
    if (url.pathname.includes("/requests/")) {
      waiting = true; await new Promise<void>(resolve => { release = resolve; });
      return json(route, { requestId, accepted: true, operationId: memoryId, state: "committed", resourceId: memoryId, resultVersion: 2, currentVersion: 2, intent: "inactive", contentAvailable: true, cleanupState: "not_required" }).catch(() => {});
    }
    if (actorB) return json(route, { items: [], nextCursor: null });
    return json(route, url.pathname.endsWith(memoryId) ? { memory } : { items: [memory], nextCursor: null });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^停用$|^Deactivate$/ }).click();
  await expect.poll(() => waiting).toBe(true);
  await page.getByRole("button", { name: /退出登录|Log out|Logout/i }).click();
  await expect(page.getByPlaceholder(/电子邮箱|email address/i)).toBeVisible();
  await expect(page.getByText(requestId, { exact: true })).toHaveCount(0);
  await page.getByPlaceholder(/电子邮箱|email address/i).fill("b@example.invalid");
  await page.getByPlaceholder(/输入密码|password/i).fill("synthetic-fixture-password");
  await page.locator("form").getByRole("button", { name: /登录|sign in/i }).click();
  await page.getByText("Memory fixture workspace", { exact: true }).click();
  await page.getByRole("tab", { name: /配置|settings/i }).click();
  await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
  release?.();
  await expect(page.getByText(/此状态下暂无记忆|No memories with this status/)).toBeVisible();
  await expect(page.getByText(requestId, { exact: true })).toHaveCount(0);
  await expect(page.getByText("Synthetic owner preference")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /新增记忆|Create memory/ })).toBeEnabled();
});
test("R2 revocation drops pending identity and fences a late poll across Home Back", async ({ page }) => {
  await shell(page);
  let denied = false; let waiting = false; let release: (() => void) | undefined; let requestId = "";
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "PATCH") { requestId = request.postDataJSON().requestId; return json(route, { detail: { code: "outcome_unknown" } }, 503); }
    if (url.pathname.includes("/requests/")) {
      waiting = true; await new Promise<void>(resolve => { release = resolve; });
      return json(route, { requestId, accepted: true, operationId: memoryId, state: "committed", resourceId: memoryId, resultVersion: 2, currentVersion: 2, intent: "inactive", contentAvailable: true, cleanupState: "not_required" }).catch(() => {});
    }
    if (denied) return json(route, { detail: { code: "workspace_not_found" } }, 404);
    return json(route, url.pathname.endsWith(memoryId) ? { memory } : { items: [memory], nextCursor: null });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^停用$|^Deactivate$/ }).click();
  await expect.poll(() => waiting).toBe(true); denied = true;
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: /访问已失效|Access lost/ })).toBeVisible();
  release?.();
  await page.locator('a[href="/"]').click(); await page.waitForURL(url => url.pathname === "/"); await page.goBack();
  await page.getByRole("tab", { name: /配置|settings/i }).click(); await page.getByRole("tab", { name: /^记忆$|^Memory$/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: /访问已失效|Access lost/ })).toBeVisible();
  await expect(page.getByText(requestId, { exact: true })).toHaveCount(0);
  await expect(page.getByText("Synthetic owner preference")).toHaveCount(0);
});
for (const intent of ["active", "inactive"] as const) {
 test(`C2 reviewer: owner can delete a content-unavailable ${intent} record`, async ({ page }) => {
  await shell(page);
  const unavailable={id:memoryId,version:2,intent,validity:"invalidated",displayStatus:intent==="active"?"invalidated":"inactive",contentAvailable:false,reason:"source_unavailable"};
  const deletes: unknown[]=[];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`,route=>{
    const req=route.request(),url=new URL(req.url());
    if(req.method()==="DELETE"){deletes.push(req.postDataJSON());return json(route,{requestId:req.postDataJSON().requestId,operationId:sourceRef.sourceId,resultVersion:3,id:memoryId,intent:"deleted",version:3,cleanupState:"completed"});}
    if(url.pathname.endsWith(memoryId))return json(route,{memory:unavailable});
    return json(route,{items:url.searchParams.get("status")==="active"?[]:[unavailable],nextCursor:null});
  });
  await enter(page); await page.getByRole("combobox",{name:/状态|Status/}).selectOption(unavailable.displayStatus);
  await page.getByRole("button",{name:/原始来源不可用|Original source unavailable/}).click();
  await expect(page.getByRole("region",{name:/当前记录|Current record/}).getByText(/原始来源不可用|Original source unavailable/)).toBeVisible();
  await expect(page.getByText(memory.content)).toHaveCount(0);
  page.on("dialog",dialog=>dialog.accept());
  await expect(page.getByRole("button",{name:/^删除$|^Delete$/})).toBeVisible();
  await page.getByRole("button",{name:/^删除$|^Delete$/}).click();
  await expect.poll(()=>deletes.length).toBe(1);
  expect(deletes[0]).toMatchObject({expectedVersion:2});
 });
}


test("R5 unavailable lifecycle controls retain fresh CAS and stay locked during an unknown operation", async ({ page }) => {
  await shell(page);
  const unavailable = { id: memoryId, version: 7, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" };
  const patches: unknown[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "PATCH") { patches.push(request.postDataJSON()); return json(route, { detail: { code: "outcome_unknown" } }, 503); }
    if (url.pathname.includes("/requests/")) return json(route, { detail: { code: "operation_not_found" } }, 404);
    return json(route, url.pathname.endsWith(memoryId) ? { memory: unavailable } : { items: [unavailable], nextCursor: null });
  });
  await enter(page); await page.getByRole("combobox", { name: /状态|Status/ }).selectOption("invalidated");
  const row = page.getByRole("button", { name: /原始来源不可用|Original source unavailable/ });
  await row.click();
  await expect(row).toBeVisible();
  await expect(page.getByRole("button", { name: /^更正$|^Correct$/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /原始来源 1|Original source 1/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toBeEnabled();
  await page.getByRole("button", { name: /^停用$|^Deactivate$/ }).click();
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({ expectedVersion: 7, intent: "inactive" });
  await expect(page.getByRole("button", { name: /重试原请求|Retry original request/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^停用$|^Deactivate$/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /修订历史|Revision history/ })).toBeEnabled();
});

test("R5 unavailable inactive history retains metadata and opaque paging without restoring semantic bytes", async ({ page }) => {
  await shell(page);
  const unavailable = { id: memoryId, version: 9, intent: "inactive", validity: "invalidated", displayStatus: "inactive", contentAvailable: false, reason: "source_unavailable" };
  const cursors: (string | null)[] = [];
  const deletes: unknown[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "DELETE") { deletes.push(request.postDataJSON()); return json(route, { detail: { code: "version_conflict", currentVersion: 10 } }, 409); }
    if (url.pathname.endsWith("/revisions")) {
      cursors.push(url.searchParams.get("cursor"));
      return json(route, { items: url.searchParams.has("cursor") ? [{ ...unavailable, version: 1, intent: "active", displayStatus: "invalidated" }] : [{ ...unavailable, version: 2 }, memory], nextCursor: url.searchParams.has("cursor") ? null : "opaque-unavailable-history" });
    }
    return json(route, url.pathname.endsWith(memoryId) ? { memory: unavailable } : { items: [unavailable], nextCursor: null });
  });
  await enter(page); await page.getByRole("combobox", { name: /状态|Status/ }).selectOption("inactive");
  await page.getByRole("button", { name: /原始来源不可用|Original source unavailable/ }).click();
  await expect(page.getByRole("button", { name: /^停用$|^Deactivate$/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^更正$|^Correct$/ })).toHaveCount(0);
  await page.getByRole("button", { name: /修订历史|Revision history/ }).click();
  const history = page.getByRole("region", { name: /修订历史|Revision history/ });
  await expect(history.getByText(/已停用.*版本 2|Inactive.*Version 2/)).toBeVisible();
  await expect(page.getByText(memory.content)).toHaveCount(0);
  await expect(page.getByText(memory.conditions.subject)).toHaveCount(0);
  await history.getByRole("button", { name: /下一页|Next page/ }).click();
  await expect(history.getByText(/已失效.*版本 1|Invalidated.*Version 1/)).toBeVisible();
  expect(cursors).toEqual([null, "opaque-unavailable-history"]);
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: /^删除$|^Delete$/ }).click();
  await expect.poll(() => deletes.length).toBe(1);
  expect(deletes[0]).toMatchObject({ expectedVersion: 9 });
});

for (const resolution of ["metadata", "erased", "scope"] as const) {
  test(`R5 source failure waits for fresh metadata and fences ${resolution} resolution`, async ({ page }) => {
    await twoWorkspaces(page);
    let sourceFailed = false; let waiting = false; let release: (() => void) | undefined;
    const deletes: unknown[] = [];
    await page.route(`**/api/workspaces/${workspaceId}/memories/${memoryId}`, async route => {
      if (route.request().method() === "DELETE") {
        deletes.push(route.request().postDataJSON());
        return json(route, { detail: { code: "version_conflict", currentVersion: 8 } }, 409);
      }
      if (!sourceFailed) return json(route, { memory });
      waiting = true; await new Promise<void>(resolve => { release = resolve; });
      return resolution === "erased" ? json(route, { detail: { code: "erased" } }, 410).catch(() => {}) : json(route, { memory: { ...memory, version: 7, intent: "inactive", displayStatus: "inactive" } }).catch(() => {});
    });
    await page.route(`**/api/workspaces/${workspaceId}/sources/read`, route => { sourceFailed = true; return json(route, { detail: { code: "source_version_unavailable" } }, 410); });
    await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
    await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
    await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeEnabled();
    await page.getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
    await expect.poll(() => waiting).toBe(true);
    await expect(page.getByText(memory.content)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toHaveCount(0);
    await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toHaveCount(0);
    if (resolution === "scope") await homeTo(page, "Other scope");
    release?.();
    if (resolution === "metadata") {
      await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toBeEnabled();
      await expect(page.getByRole("button", { name: /^停用$|^Deactivate$/ })).toHaveCount(0);
      await expect(page.getByRole("button", { name: /^更正$|^Correct$/ })).toHaveCount(0);
      await expect(page.getByText(memory.content)).toHaveCount(0);
      page.on("dialog", dialog => dialog.accept());
      await page.getByRole("button", { name: /^删除$|^Delete$/ }).click();
      await expect.poll(() => deletes.length).toBe(1);
      expect(deletes[0]).toMatchObject({ expectedVersion: 7 });
    } else {
      if (resolution === "erased") await expect(page.getByText("Memory content has been erased.", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toHaveCount(0);
      await expect(page.getByText(memory.content)).toHaveCount(0);
      expect(deletes).toHaveLength(0);
    }
  });
}

test("R5 an unavailable historical revision clears copied bytes and never becomes current CAS metadata", async ({ page }) => {
  await shell(page);
  let unreadable = false;
  const deletes: unknown[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "DELETE") { deletes.push(request.postDataJSON()); return json(route, { detail: { code: "version_conflict", currentVersion: 9 } }, 409); }
    if (url.pathname.endsWith("/revisions")) {
      unreadable = true;
      return json(route, { items: [{ id: memoryId, version: 2, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" }], nextCursor: null });
    }
    const current = unreadable ? { ...memory, version: 8, intent: "inactive", displayStatus: "inactive" } : memory;
    return json(route, url.pathname.endsWith(memoryId) ? { memory: current } : { items: [current], nextCursor: null });
  });
  await enter(page); await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
  await page.getByRole("button", { name: /修订历史|Revision history/ }).click();
  await expect(page.getByRole("region", { name: /修订历史|Revision history/ }).getByText(/已失效.*版本 2|Invalidated.*Version 2/)).toBeVisible();
  await expect(page.getByText(memory.content)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Synthetic owner preference/ })).toHaveCount(0);
  await expect(page.getByLabel(/内容.*1–4000|Content.*1–4000/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^停用$|^Deactivate$/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^删除$|^Delete$/ })).toBeEnabled();
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: /^删除$|^Delete$/ }).click();
  await expect.poll(() => deletes.length).toBe(1);
  expect(deletes[0]).toMatchObject({ expectedVersion: 8 });
});

const adoptSuccessor = (page: Page) => page.getByRole("button", { name: /继续编辑此后继|Continue on this successor/ });
const draftField = (page: Page) => page.getByLabel(/内容.*1–4000|Content.*1–4000/);
const recoverySubject = "Selected successor candidate";
const qId = "00000000-0000-0000-0000-000000000099";
const rId = "00000000-0000-0000-0000-000000000098";
const sId = "00000000-0000-0000-0000-000000000097";
const optionalOriginal: AvailableMemory = { ...memory, kind: "constraint", pinned: true, validUntil: "2099-12-31T00:00:00Z", conditions: { ...memory.conditions, effectiveFrom: "2026-01-01T00:00:00Z" } };
const qMemory: AvailableMemory = { ...memory, id: qId, supersedesId: memoryId, conditions: { ...memory.conditions, subject: recoverySubject }, content: "Competitor committed candidate body", sourceRefs: [{ ...sourceRef, sourceId: rId }] };
type Attempt = { path: string; body: Record<string, unknown>; key: string };
async function recoveryFixture(page: Page, recurrent = false) {
  await twoWorkspaces(page);
  const attempts: Attempt[] = [];
  const currentReads: string[] = [];
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && /\/memories\/[0-9a-f-]{36}$/.test(path)) currentReads.push(path);
  });
  let settled: AvailableMemory | undefined;
  let unavailable: "list" | "detail" | "history" | "source" | undefined;
  let held: Promise<void> | undefined;
  let readHeld = false;
  const original = () => attempts.length ? { ...optionalOriginal, version: 2, intent: "superseded" as const, displayStatus: "superseded" as const } : optionalOriginal;
  const q = () => attempts.length > 1 && recurrent ? { ...qMemory, version: 2, intent: "superseded" as const, displayStatus: "superseded" as const } : qMemory;
  const r: AvailableMemory = { ...qMemory, id: rId, supersedesId: qId, conditions: { ...qMemory.conditions, subject: "Second selected successor" }, content: "Second concurrent successor body" };
  const hidden = { id: qId, version: 1, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" };
  await page.route(`**/api/workspaces/${workspaceId}/memories**`, async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() !== "GET") {
      attempts.push({ path: url.pathname, body: request.postDataJSON(), key: request.headers()["idempotency-key"] });
      if (attempts.length === 1 || (recurrent && attempts.length === 2)) return json(route, { detail: { code: "version_conflict", currentVersion: 2 } }, 409);
      const target = recurrent ? r : qMemory;
      const body = request.postDataJSON();
      settled = { ...target, id: sId, supersedesId: target.id, kind: body.kind, content: body.content, conditions: body.conditions, pinned: body.pinned, validUntil: body.validUntil };
      return json(route, { requestId: body.requestId, operationId: sourceRef.sourceId, resultVersion: 1, memory: settled, supersededMemoryId: target.id, indexState: "not_enabled" }, 201);
    }
    if (url.pathname.endsWith("/revisions")) return unavailable === "history" ? json(route, { items: [hidden], nextCursor: null }) : json(route, { items: [q()], nextCursor: null });
    if (url.pathname.endsWith(qId)) {
      if (held) { readHeld = true; await held; }
      return unavailable === "detail" ? json(route, { detail: { code: "erased" } }, 410) : json(route, { memory: q() });
    }
    if (url.pathname.endsWith(memoryId)) return json(route, { memory: original() });
    if (url.pathname.endsWith(rId)) return json(route, { memory: r });
    if (url.pathname.endsWith(sId)) return json(route, { memory: settled });
    return json(route, { items: settled ? [settled] : unavailable === "list" ? [hidden] : attempts.length > 1 && recurrent ? [r] : attempts.length ? [qMemory] : [optionalOriginal], nextCursor: null });
  });
  await page.route(`**/api/workspaces/${workspaceId}/sources/read`, route => unavailable === "source" ? json(route, { detail: { code: "source_version_unavailable" } }, 410) : json(route, { sourceRef: qMemory.sourceRefs[0], content: qMemory.content, contentKind: "explicit_instruction", occurredAt: now, sourceState: "current", provenance: { role: "user", actorUserId: "fixture-user", actorAttribution: "authenticated", threadId: null, runId: null, parentMessageId: null, confirmation: "explicit_remember" }, branchRelation: "other_task", truncated: false, nextCursor: null }));
  await enter(page);
  await page.getByRole("button", { name: /Synthetic owner preference/ }).click();
  await page.getByRole("button", { name: /^更正$|^Correct$/ }).click();
  await draftField(page).fill("Exact retained recovery draft");
  await page.getByRole("button", { name: /^保存$|^Save$/ }).click();
  await expect(page.getByText("Memory version changed.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  return { attempts, currentReads, deny: (value: typeof unavailable) => { unavailable = value; }, hold: (value: Promise<void>) => { held = value; }, held: () => readHeld };
}

test("fixture: distinct successor comparison/adoption preserves full Statement and requires separate Save", async ({ page }) => {
  const state = await recoveryFixture(page);
  await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  await expect(draftField(page)).toHaveValue("Exact retained recovery draft");
  expect(state.attempts).toHaveLength(1);
  await adoptSuccessor(page).click();
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeEnabled();
  expect(state.attempts).toHaveLength(1);
  await page.getByRole("button", { name: /^保存$|^Save$/ }).click();
  await expect.poll(() => state.attempts.length).toBe(2);
  expect(state.attempts[0].path).toContain(`/${memoryId}/corrections`);
  expect(state.attempts[1].path).toContain(`/${qId}/corrections`);
  expect(state.attempts[1].body).toEqual({ ...state.attempts[0].body, requestId: expect.any(String), expectedVersion: 1 });
  expect(state.attempts[1].body).toMatchObject({ kind: "constraint", pinned: true, validUntil: optionalOriginal.validUntil, conditions: optionalOriginal.conditions });
  expect(state.attempts[1].body.requestId).not.toBe(state.attempts[0].body.requestId);
  expect(state.attempts[1].key).not.toBe(state.attempts[0].key);
});

for (const denial of ["list", "detail", "history", "source"] as const) {
  test(`fixture: proven successor participant ${denial} unavailability clears recovery draft and comparison`, async ({ page }) => {
    const state = await recoveryFixture(page);
    await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
    await expect(adoptSuccessor(page)).toBeEnabled();
    state.deny(denial);
    if (denial === "list") await page.getByRole("combobox", { name: /状态|Status/ }).selectOption("all");
    else if (denial === "history") await page.getByRole("region", { name: /^当前记录$|^Current record$/ }).getByRole("button", { name: /修订历史|Revision history/ }).click();
    else if (denial === "source") await page.getByRole("region", { name: /^当前记录$|^Current record$/ }).getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
    else await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
    await expect(draftField(page)).toHaveCount(0);
    await expect(adoptSuccessor(page)).toHaveCount(0);
    await expect(page.getByText(qMemory.content, { exact: true })).toHaveCount(0);
    expect(state.attempts).toHaveLength(1);
  });
}

test("fixture: recurring correction conflict requires another explicit successor choice and adoption", async ({ page }) => {
  const state = await recoveryFixture(page, true);
  await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  await adoptSuccessor(page).click();
  await page.getByRole("button", { name: /^保存$|^Save$/ }).click();
  await expect.poll(() => state.attempts.length).toBe(2);
  await expect(draftField(page)).toHaveValue("Exact retained recovery draft");
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeDisabled();
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await page.getByRole("button", { name: /Second selected successor/ }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  expect(state.attempts).toHaveLength(2);
  await adoptSuccessor(page).click();
  expect(state.attempts).toHaveLength(2);
  await page.getByRole("button", { name: /^保存$|^Save$/ }).click();
  await expect.poll(() => state.attempts.length).toBe(3);
  expect(state.attempts[2].path).toContain(`/${rId}/corrections`);
  expect(state.attempts[2].body).toMatchObject({ expectedVersion: 1, content: "Exact retained recovery draft", pinned: true, conditions: optionalOriginal.conditions });
});

for (const transition of ["scope", "source"] as const) {
  test(`fixture: late adoption reads cannot restore recovery after ${transition} invalidation`, async ({ page }) => {
    const state = await recoveryFixture(page);
    await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
    await expect(adoptSuccessor(page)).toBeEnabled();
    let release: (() => void) | undefined;
    state.hold(new Promise<void>(resolve => { release = resolve; }));
    await adoptSuccessor(page).click();
    await expect.poll(state.held).toBe(true);
    if (transition === "scope") {
      await homeTo(page, "Other scope");
    } else {
      state.deny("source");
      await page.getByRole("region", { name: /^当前记录$|^Current record$/ }).getByRole("button", { name: /原始来源 1|Original source 1/ }).click();
    }
    await expect(draftField(page)).toHaveCount(0);
    release?.();
    await expect(adoptSuccessor(page)).toHaveCount(0);
    await expect(draftField(page)).toHaveCount(0);
    expect(state.attempts).toHaveLength(1);
  });
}

for (const denial of ["foreign", "unrelated", "cycle", "superseded"] as const) {
  test(`fixture: unproven ${denial} candidate never adopts or discards the separately authorized draft`, async ({ page }) => {
    const state = await recoveryFixture(page);
    await page.route(`**/api/workspaces/${workspaceId}/memories/${qId}`, route => {
      if (denial === "foreign") return json(route, { detail: { code: "memory_not_found" } }, 404);
      const candidate = denial === "unrelated" ? { ...qMemory, supersedesId: null }
        : denial === "cycle" ? { ...qMemory, supersedesId: qId }
        : { ...qMemory, version: 2, intent: "superseded", displayStatus: "superseded" };
      return json(route, { memory: candidate });
    });
    await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(draftField(page)).toHaveValue("Exact retained recovery draft");
    await expect(adoptSuccessor(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeDisabled();
    expect(state.attempts).toHaveLength(1);
  });
}

test("fixture: successor superseded during adoption requires explicit selection of its new successor", async ({ page }) => {
  const state = await recoveryFixture(page);
  await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  const later = { ...qMemory, id: rId, supersedesId: qId, conditions: { ...qMemory.conditions, subject: "Later selected successor" } };
  await page.route(`**/api/workspaces/${workspaceId}/memories/${qId}`, route => json(route, { memory: { ...qMemory, version: 2, intent: "superseded", displayStatus: "superseded" } }));
  await page.route(`**/api/workspaces/${workspaceId}/memories/${rId}`, route => json(route, { memory: later }));
  await page.route(`**/api/workspaces/${workspaceId}/memories?**`, route => json(route, { items: [later], nextCursor: null }));
  await adoptSuccessor(page).click();
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeDisabled();
  await expect(adoptSuccessor(page)).toHaveCount(0);
  await expect(draftField(page)).toHaveValue("Exact retained recovery draft");
  expect(state.attempts).toHaveLength(1);
  await page.getByRole("button", { name: /^刷新$|^Refresh$/ }).click();
  await page.getByRole("button", { name: /Later selected successor/ }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  await adoptSuccessor(page).click();
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeEnabled();
  expect(state.attempts).toHaveLength(1);
});

test("fixture: maximum eight-edge successor proof stays within selection9 and adoption10 current GETs", async ({ page }) => {
  const state = await recoveryFixture(page);
  const intermediates = Array.from({ length: 7 }, (_, index) => `00000000-0000-0000-0000-${String(200 + index).padStart(12, "0")}`);
  for (let index = 0; index < intermediates.length; index++) {
    const id = intermediates[index];
    const record = { ...memory, id, version: 2, supersedesId: intermediates[index + 1] ?? memoryId, intent: "superseded", displayStatus: "superseded" };
    await page.route(`**/api/workspaces/${workspaceId}/memories/${id}`, route => json(route, { memory: record }));
  }
  await page.route(`**/api/workspaces/${workspaceId}/memories/${qId}`, route => json(route, { memory: { ...qMemory, supersedesId: intermediates[0] } }));
  const beforeSelect = state.currentReads.length;
  await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  await page.waitForTimeout(100);
  expect(state.currentReads.slice(beforeSelect)).toHaveLength(9);
  const beforeAdopt = state.currentReads.length;
  await adoptSuccessor(page).click();
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeEnabled();
  await page.waitForTimeout(100);
  expect(state.currentReads.slice(beforeAdopt)).toHaveLength(10);
  expect(state.currentReads.at(-1)).toBe(`/api/workspaces/${workspaceId}/memories/${qId}`);
  expect(state.attempts).toHaveLength(1);
});

test("fixture: original predecessor history and exact source remain readable during comparison without changing draft or target", async ({ page }) => {
  const state = await recoveryFixture(page);
  let historyReads = 0;
  const sourceReads: unknown[] = [];
  await page.route(`**/api/workspaces/${workspaceId}/memories/${memoryId}/revisions?**`, route => {
    historyReads++;
    return json(route, { items: [optionalOriginal, { ...optionalOriginal, version: 2, intent: "superseded", displayStatus: "superseded" }], nextCursor: null });
  });
  await page.route(`**/api/workspaces/${workspaceId}/sources/read`, route => {
    sourceReads.push(route.request().postDataJSON());
    return json(route, { sourceRef, content: optionalOriginal.content, contentKind: "explicit_instruction", occurredAt: now, sourceState: "current", provenance: { role: "user", actorUserId: "fixture-user", actorAttribution: "authenticated", threadId: null, runId: null, parentMessageId: null, confirmation: "explicit_remember" }, branchRelation: "other_task", truncated: false, nextCursor: null });
  });
  await page.getByRole("button", { name: new RegExp(recoverySubject) }).click();
  await expect(adoptSuccessor(page)).toBeEnabled();
  const currentReads = state.currentReads.length;
  const predecessor = page.getByRole("region", { name: /^原始前身$|^Original predecessor$/ });
  await predecessor.getByRole("button", { name: /修订历史|Revision history/ }).click();
  const history = predecessor.getByRole("region", { name: /^修订历史$|^Revision history$/ });
  await expect(history.getByText(optionalOriginal.content, { exact: true })).toHaveCount(2);
  await expect(history.getByText(/生效.*版本 1|Active.*Version 1/)).toBeVisible();
  await expect(history.getByText(/已更正.*版本 2|Superseded.*Version 2/)).toBeVisible();
  await history.getByRole("button", { name: /原始来源 1.*版本 1|Original source 1.*Version 1/ }).click();
  await expect(predecessor.getByRole("region", { name: /^原始来源$|^Original source$/ }).getByText(optionalOriginal.content, { exact: true })).toBeVisible();
  expect(historyReads).toBe(1);
  expect(sourceReads).toEqual([{ sourceRef }]);
  expect(state.currentReads).toHaveLength(currentReads);
  await expect(draftField(page)).toHaveValue("Exact retained recovery draft");
  await expect(page.getByRole("button", { name: /^保存$|^Save$/ })).toBeDisabled();
  await expect(adoptSuccessor(page)).toBeEnabled();
  expect(state.attempts).toHaveLength(1);
});
