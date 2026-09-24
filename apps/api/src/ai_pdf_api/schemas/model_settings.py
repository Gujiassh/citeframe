from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ModelSettingsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    action: Literal["save", "reset"]
    expectedRevision: int = Field(ge=0)
    protocol: Literal["openai_responses", "openai_chat_completions", "openai_embeddings"] | None = None
    baseUrl: str | None = Field(default=None, min_length=1, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    apiKey: SecretStr | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def check_action(self):
        if self.action == "save" and (not self.protocol or not self.baseUrl or not self.model):
            raise ValueError("Save requires protocol, baseUrl and model.")
        if self.action == "reset" and any(x is not None for x in (self.protocol, self.baseUrl, self.model, self.apiKey)):
            raise ValueError("Reset accepts only action and expectedRevision.")
        return self


class UpdateModelSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    generation: ModelSettingsCommand | None = None
    embedding: ModelSettingsCommand | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.generation is None and self.embedding is None:
            raise ValueError("At least one capability is required.")
        return self


class ModelSettingsView(BaseModel):
    source: Literal["server", "workspace"]
    revision: int
    protocol: str
    baseUrl: str
    model: str
    apiKeyConfigured: bool
    status: Literal["configured", "unconfigured", "unavailable"]
    errorCode: str | None = None


class EmbeddingSettingsView(ModelSettingsView):
    dimensions: Literal[1024] = 1024
    reindexRequired: bool
    reindexAssetIds: list[str]


class WorkspaceModelSettingsResponse(BaseModel):
    encryptionReady: bool
    generation: ModelSettingsView
    embedding: EmbeddingSettingsView
