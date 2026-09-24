export type ModelCapability = "generation" | "embedding";
export type EditableProtocol = "openai_responses" | "openai_chat_completions" | "openai_embeddings";
export type ModelSettingsView = {
  source: "server" | "workspace";
  revision: number;
  protocol: string;
  baseUrl: string;
  model: string;
  apiKeyConfigured: boolean;
  status: "configured" | "unconfigured" | "unavailable";
  errorCode: string | null;
};
export type WorkspaceModelSettings = {
  encryptionReady: boolean;
  generation: ModelSettingsView;
  embedding: ModelSettingsView & { dimensions: 1024; reindexRequired: boolean; reindexAssetIds: string[] };
};
export type ModelSettingsCommand = {
  action: "save";
  expectedRevision: number;
  protocol: EditableProtocol;
  baseUrl: string;
  model: string;
  apiKey?: string;
} | { action: "reset"; expectedRevision: number };
export type ModelSettingsPatch = Partial<Record<ModelCapability, ModelSettingsCommand>>;
