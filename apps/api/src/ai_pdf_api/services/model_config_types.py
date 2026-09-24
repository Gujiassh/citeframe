from dataclasses import dataclass, field
from typing import Literal

Capability = Literal["generation", "embedding"]


class ModelConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(frozen=True)
class ModelConnection:
    capability: Capability
    source: Literal["server", "workspace"]
    revision: int
    protocol: str
    provider: str
    model: str
    base_url: str = field(repr=False)
    api_key: str | None = field(repr=False)
    timeout_seconds: float
    max_output_tokens: int = 1200
    dimensions: int = 1024
    version: str = "embedding-v1"
    query_instruction: str = ""


@dataclass(frozen=True)
class WorkspaceModels:
    workspace_id: str
    generation: ModelConnection
    embedding: ModelConnection
