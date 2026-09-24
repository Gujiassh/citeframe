import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CapabilityForm } from "./capability-form";
import type { ModelSettingsView } from "@/lib/model-settings/types";

const settings: ModelSettingsView = { source: "workspace", revision: 4, protocol: "openai_chat_completions", baseUrl: "https://provider.example/v1", model: "model-a", apiKeyConfigured: true, status: "configured", errorCode: null };
test("generation form renders protocol choices and a blank write-only password", () => {
  const html = renderToStaticMarkup(createElement(CapabilityForm, { capability: "generation", settings, disabled: false, locale: "en", onSave: async () => true, onDirty: () => {} }));
  assert.match(html, /OpenAI Responses/); assert.match(html, /OpenAI Chat Completions/);
  assert.match(html, /type="password"[^>]*value=""/); assert.match(html, /Configured; leave blank to retain/);
  assert.match(html, /Reset to server defaults/); assert.match(html, /r4/);
});
test("embedding form exposes only embedding protocol and the fixed 1024 dimension constraint", () => {
  const html = renderToStaticMarkup(createElement(CapabilityForm, { capability: "embedding", settings, disabled: true, locale: "en", onSave: async () => true, onDirty: () => {} }));
  assert.match(html, /1024 dimensions/); assert.match(html, /OpenAI Embeddings/); assert.doesNotMatch(html, /OpenAI Responses/); assert.match(html, /fieldset disabled/);
});
