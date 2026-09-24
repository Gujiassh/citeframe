from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import Workspace, WorkspaceModelConfig
from ai_pdf_api.schemas.model_settings import UpdateModelSettingsRequest
from ai_pdf_api.services.model_config_types import Capability, ModelConfigurationError, ModelConnection, WorkspaceModels
from ai_pdf_api.services.model_endpoint import validate_base_url
from ai_pdf_api.services.model_secrets import decrypt_key, encrypt_key, encryption_key


def lock_workspace_models(db: Session, workspace_id: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update().execution_options(populate_existing=True))
    if workspace is None:
        raise ModelConfigurationError("workspace_not_found", "Workspace not found.", 404)
    return workspace


def server_connection(capability: Capability) -> ModelConnection:
    if capability == "generation":
        deepseek = settings.generation_provider == "deepseek"
        return ModelConnection(capability, "server", 0, "anthropic_messages" if deepseek else "openai_responses",
            settings.generation_provider, settings.generation_model,
            settings.deepseek_api_base if deepseek else settings.openai_api_base,
            settings.deepseek_api_key if deepseek else settings.openai_api_key,
            settings.generation_timeout_seconds, max_output_tokens=settings.generation_max_output_tokens)
    ollama = settings.embedding_provider == "ollama"
    return ModelConnection(capability, "server", 0, "ollama" if ollama else "openai_embeddings",
        settings.embedding_provider, settings.embedding_model, settings.ollama_base_url if ollama else settings.openai_api_base,
        None if ollama else settings.openai_api_key, settings.embedding_timeout_seconds,
        dimensions=settings.embedding_dimensions, version=settings.embedding_version, query_instruction=settings.embedding_query_instruction)


def configuration_row(db: Session, workspace_id: str, capability: Capability):
    return db.get(WorkspaceModelConfig, (workspace_id, capability), populate_existing=True)


def resolve_connection(db: Session, workspace_id: str, capability: Capability) -> ModelConnection:
    row = configuration_row(db, workspace_id, capability)
    return connection_from_row(workspace_id, capability, row)


def connection_from_row(workspace_id: str, capability: Capability, row) -> ModelConnection:
    default = server_connection(capability)
    if row is None or row.mode == "inherit":
        return replace(default, revision=row.revision if row else 0)
    return replace(default, source="workspace", revision=row.revision, provider="openai", protocol=row.protocol,
                   model=row.model, base_url=validate_base_url(row.base_url), api_key=decrypt_key(row.encrypted_api_key, workspace_id, capability))


def resolve_workspace_models(db: Session, workspace_id: str) -> WorkspaceModels:
    rows = read_configuration_rows(db, workspace_id)
    return WorkspaceModels(workspace_id, connection_from_row(workspace_id, "generation", rows.get("generation")),
                           connection_from_row(workspace_id, "embedding", rows.get("embedding")))


def read_configuration_rows(db: Session, workspace_id: str) -> dict:
    return {row.capability: row for row in db.scalars(select(WorkspaceModelConfig).where(
        WorkspaceModelConfig.workspace_id == workspace_id).execution_options(populate_existing=True)).all()}


def update_model_settings(db: Session, workspace_id: str, user_id: str, request: UpdateModelSettingsRequest) -> None:
    lock_workspace_models(db, workspace_id)
    now = datetime.now(UTC)
    changes = []
    for capability in ("generation", "embedding"):
        command = getattr(request, capability)
        if command is None:
            continue
        row = configuration_row(db, workspace_id, capability)
        if command.expectedRevision != (row.revision if row else 0):
            raise ModelConfigurationError("model_settings_conflict", "Model settings changed. Reload before saving.", 409)
        values = dict(mode="inherit", protocol=None, base_url=None, model=None, encrypted_api_key=None)
        if command.action == "save":
            allowed = {"openai_responses", "openai_chat_completions"} if capability == "generation" else {"openai_embeddings"}
            if command.protocol not in allowed:
                raise ModelConfigurationError("model_settings_invalid", "The protocol is not supported for this capability.")
            base = validate_base_url(command.baseUrl)
            model = command.model.strip()
            if not model or any(ord(char) < 32 for char in model):
                raise ModelConfigurationError("model_settings_invalid", "Enter a valid model name.")
            key = command.apiKey.get_secret_value() if command.apiKey is not None else None
            if key is not None and (not key.strip() or len(key) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in key)):
                raise ModelConfigurationError("model_settings_invalid", "Enter a nonempty API key without control characters.")
            if key is None:
                if row is None or row.mode != "override" or row.base_url != base:
                    raise ModelConfigurationError("model_key_required", "Enter an API key for the new endpoint.")
                key = decrypt_key(row.encrypted_api_key, workspace_id, capability)
            values = dict(mode="override", protocol=command.protocol, base_url=base, model=model,
                          encrypted_api_key=encrypt_key(key.strip(), workspace_id, capability))
        changes.append((capability, row, values))
    for capability, row, values in changes:
        if row is None:
            row = WorkspaceModelConfig(workspace_id=workspace_id, capability=capability, revision=0)
            db.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        row.revision += 1
        row.updated_at, row.updated_by_user_id = now, user_id
    db.flush()


def connection_view(workspace_id: str, capability: Capability, row) -> dict:
    default = server_connection(capability)
    value = dict(source="workspace" if row and row.mode == "override" else "server", revision=row.revision if row else 0,
                 protocol=row.protocol if row and row.mode == "override" else default.protocol,
                 baseUrl=row.base_url if row and row.mode == "override" else "",
                 model=row.model if row and row.mode == "override" else default.model,
                 apiKeyConfigured=False, status="unconfigured", errorCode=None)
    try:
        connection = connection_from_row(workspace_id, capability, row)
        configured = bool(connection.api_key and connection.api_key.strip()) or connection.protocol == "ollama"
        value.update(apiKeyConfigured=bool(connection.api_key), status="configured" if configured else "unconfigured")
    except ModelConfigurationError as error:
        value.update(status="unavailable", errorCode=error.code)
    return value


def settings_view(db: Session, workspace_id: str) -> dict:
    try:
        encryption_key()
        encryption_ready = True
    except ModelConfigurationError:
        encryption_ready = False
    rows = read_configuration_rows(db, workspace_id)
    generation = connection_view(workspace_id, "generation", rows.get("generation"))
    embedding = connection_view(workspace_id, "embedding", rows.get("embedding"))
    from ai_pdf_api.services.workspace_index_status import reindex_asset_ids
    ids = reindex_asset_ids(db, workspace_id, connection_from_row(workspace_id, "embedding", rows.get("embedding"))) if embedding["status"] != "unavailable" else []
    embedding.update(dimensions=1024, reindexRequired=bool(ids), reindexAssetIds=ids)
    return dict(encryptionReady=encryption_ready, generation=generation, embedding=embedding)
