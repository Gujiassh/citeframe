import assert from "node:assert/strict";
import test from "node:test";
import { ModelSettingsError, modelSettingsRequest } from "./client";

test("model settings request carries only explicit patch and does not cache", async (t) => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.equal(url, "/api/workspaces/workspace-a/model-settings"); assert.equal(init.cache, "no-store");
    assert.deepEqual(JSON.parse(init.body as string), { generation: { action: "reset", expectedRevision: 7 } });
    return new Response(JSON.stringify({ encryptionReady: true }), { status: 200 });
  });
  await modelSettingsRequest("workspace-a", new AbortController().signal, { generation: { action: "reset", expectedRevision: 7 } });
});
test("revision conflicts retain status/code and safe actionable message", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ detail: { code: "model_settings_conflict", message: "Configuration changed. Reload before saving." } }), { status: 409 }));
  await assert.rejects(modelSettingsRequest("a", new AbortController().signal), (error: unknown) => error instanceof ModelSettingsError && error.status === 409 && error.code === "model_settings_conflict" && error.message.includes("Reload"));
});
test("aborted configuration response cannot hydrate a different workspace", async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => { controller.abort(); return new Response("{}"); });
  await assert.rejects(modelSettingsRequest("a", controller.signal), { name: "AbortError" });
});
