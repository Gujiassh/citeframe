import type { EditableProtocol, ModelCapability, ModelSettingsCommand, ModelSettingsView } from "./types";

export type ModelDraft = { protocol: EditableProtocol; baseUrl: string; model: string; apiKey: string };
export function modelDraft(capability: ModelCapability, settings: ModelSettingsView): ModelDraft {
  return {
    protocol: capability === "embedding" ? "openai_embeddings" : settings.protocol === "openai_chat_completions" ? "openai_chat_completions" : "openai_responses",
    baseUrl: settings.baseUrl,
    model: settings.model,
    apiKey: "",
  };
}

export function requiresExplicitKey(settings: ModelSettingsView, baseUrl: string): boolean {
  return settings.source !== "workspace" || !settings.apiKeyConfigured
    || baseUrl.trim().replace(/\/+$/, "") !== settings.baseUrl.replace(/\/+$/, "");
}

export function saveModelCommand(settings: ModelSettingsView, draft: ModelDraft): ModelSettingsCommand {
  return {
    action: "save",
    expectedRevision: settings.revision,
    protocol: draft.protocol,
    baseUrl: draft.baseUrl.trim(),
    model: draft.model.trim(),
    ...(draft.apiKey.trim() ? { apiKey: draft.apiKey.trim() } : {}),
  };
}
