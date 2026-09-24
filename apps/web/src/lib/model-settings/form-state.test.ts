import assert from "node:assert/strict";
import test from "node:test";
import { modelDraft, requiresExplicitKey, saveModelCommand } from "./form-state";
import type { ModelSettingsView } from "./types";

const settings: ModelSettingsView = { source: "workspace", revision: 3, protocol: "openai_responses", baseUrl: "https://provider.example/custom/v1", model: "model-a", apiKeyConfigured: true, status: "configured", errorCode: null };
test("model draft never reads a stored key and retains explicit generation protocol", () => {
  assert.equal(modelDraft("generation", settings).apiKey, "");
  assert.equal(modelDraft("generation", { ...settings, protocol: "openai_chat_completions" }).protocol, "openai_chat_completions");
  assert.equal(modelDraft("embedding", settings).protocol, "openai_embeddings");
});
test("same endpoint key retention omits apiKey; a new key is submitted only when entered", () => {
  const draft = modelDraft("generation", settings);
  const retained = saveModelCommand(settings, { ...draft, model: "changed-model" });
  assert.equal("apiKey" in retained, false);
  assert.equal(retained.expectedRevision, 3);
  assert.equal(requiresExplicitKey(settings, settings.baseUrl + "/"), false);
  const replacement = saveModelCommand(settings, { ...draft, apiKey: "test-only-new-key" });
  assert.ok(replacement.action === "save"); assert.equal(replacement.apiKey, "test-only-new-key");
});
test("initial override and endpoint changes require an explicit key; model changes do not", () => {
  assert.equal(requiresExplicitKey({ ...settings, source: "server" }, settings.baseUrl), true);
  assert.equal(requiresExplicitKey(settings, "https://other.example/v1"), true);
  assert.equal(requiresExplicitKey({ ...settings, apiKeyConfigured: false }, settings.baseUrl), true);
  assert.equal(requiresExplicitKey(settings, settings.baseUrl), false);
});
test("reset/override monotonic revision is used without local increment or reset", () => {
  const inherited = { ...settings, source: "server" as const, revision: 8 };
  assert.equal(saveModelCommand(inherited, { ...modelDraft("generation", inherited), apiKey: "test-only-key" }).expectedRevision, 8);
});
