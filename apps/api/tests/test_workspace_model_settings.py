import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import User, Workspace, WorkspaceMembership, WorkspaceModelConfig
from ai_pdf_api.routers.model_settings import router
from ai_pdf_api.services.capabilities import connection_profile
from ai_pdf_api.services.model_config_types import ModelConfigurationError
from ai_pdf_api.services.model_secrets import decrypt_key
from ai_pdf_api.services.workspace_models import resolve_connection

KEY = "fixture-only-secret-DO-NOT-ECHO"


@pytest.fixture
def configured_api(monkeypatch):
    monkeypatch.setattr(settings, "model_config_encryption_key", base64.b64encode(b"x" * 32).decode())
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for id in ("owner", "member", "outsider"):
            db.add(User(id=id, email=f"{id}@example.test", name=id, password_hash="unused", avatar_url=""))
        db.flush()
        for id in ("w1", "w2"):
            db.add(Workspace(id=id, name=id, created_by_user_id="owner"))
            db.flush()
            db.add(WorkspaceMembership(workspace_id=id, user_id="owner", role="owner"))
        db.add(WorkspaceMembership(workspace_id="w1", user_id="member", role="member"))
        db.commit()
        app = FastAPI()
        app.include_router(router)
        def dependency():
            try:
                yield db
            finally:
                db.rollback()
        app.dependency_overrides[get_db] = dependency
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def headers(user="owner"):
    return {"x-user-id": user, "x-ai-pdf-internal-token": settings.api_internal_token}


def save(revision=0, key=KEY, base="https://fixture.example/custom/v1"):
    result = dict(action="save", expectedRevision=revision, protocol="openai_chat_completions", baseUrl=base, model="model-a")
    if key is not None:
        result["apiKey"] = key
    return result


def test_encrypted_save_restart_resolution_nonce_and_isolation(configured_api):
    client, db = configured_api
    response = client.patch("/v1/workspaces/w1/model-settings", headers=headers(), json={"generation": save()})
    assert response.status_code == 200, response.text
    assert KEY not in response.text
    assert response.json()["generation"]["baseUrl"] == "https://fixture.example/custom/v1"
    stored = db.scalar(text("select encrypted_api_key from workspace_model_configs"))
    assert stored.startswith("v1:") and KEY not in stored
    db.expire_all()
    before = resolve_connection(db, "w1", "generation")
    assert before.api_key == KEY
    assert resolve_connection(db, "w2", "generation").source == "server"
    response = client.patch("/v1/workspaces/w1/model-settings", headers=headers(), json={"generation": save(1)})
    assert response.status_code == 200
    after = resolve_connection(db, "w1", "generation")
    assert connection_profile(before).config_fingerprint == connection_profile(after).config_fingerprint
    assert db.get(WorkspaceModelConfig, ("w1", "generation")).encrypted_api_key != stored
    assert KEY not in repr(after)
    with pytest.raises(ModelConfigurationError):
        decrypt_key(stored, "w2", "generation")
    with pytest.raises(ModelConfigurationError):
        decrypt_key(stored, "w1", "embedding")


def test_reset_revision_aba_and_atomic_conflict(configured_api):
    client, db = configured_api
    path = "/v1/workspaces/w1/model-settings"
    assert client.patch(path, headers=headers(), json={"generation": save()}).status_code == 200
    reset = client.patch(path, headers=headers(), json={"generation": {"action": "reset", "expectedRevision": 1}})
    assert reset.json()["generation"]["revision"] == 2
    assert reset.json()["generation"]["source"] == "server"
    assert client.patch(path, headers=headers(), json={"generation": save(2)}).json()["generation"]["revision"] == 3
    embedding = {**save(), "protocol": "openai_embeddings"}
    result = client.patch(path, headers=headers(), json={"generation": save(1), "embedding": embedding})
    assert result.status_code == 409
    assert db.get(WorkspaceModelConfig, ("w1", "embedding")) is None
    assert db.get(WorkspaceModelConfig, ("w1", "generation")).revision == 3


def test_key_retention_and_endpoint_change(configured_api):
    client, _ = configured_api
    path = "/v1/workspaces/w1/model-settings"
    assert client.patch(path, headers=headers(), json={"generation": save(key=None)}).status_code == 422
    assert client.patch(path, headers=headers(), json={"generation": save()}).status_code == 200
    assert client.patch(path, headers=headers(), json={"generation": save(1, None)}).status_code == 200
    result = client.patch(path, headers=headers(), json={"generation": save(2, None, "https://other.example/v1")})
    assert result.status_code == 422 and result.json()["detail"]["code"] == "model_key_required"


@pytest.mark.parametrize("payload", [
    {"generation": {"apiKey": KEY}},
    {"generation": {**save(), "apiKey": {"nested": KEY}}},
    {"generation": {**save(), "unknown": KEY}},
    [KEY],
    {"unknown": KEY},
])
def test_validation_never_echoes_input(configured_api, payload, caplog):
    client, _ = configured_api
    result = client.patch("/v1/workspaces/w1/model-settings", headers=headers(), json=payload)
    assert result.status_code == 422
    assert KEY not in result.text and KEY not in caplog.text


def test_malformed_json_does_not_echo(configured_api):
    client, _ = configured_api
    result = client.patch("/v1/workspaces/w1/model-settings", headers={**headers(), "content-type": "application/json"}, content='{"apiKey":"'+KEY)
    assert result.status_code == 422 and KEY not in result.text


def test_ownership(configured_api):
    client, _ = configured_api
    for user, status in (("member", 403), ("outsider", 404)):
        assert client.get("/v1/workspaces/w1/model-settings", headers=headers(user)).status_code == status
        assert client.patch("/v1/workspaces/w1/model-settings", headers=headers(user), json={"generation": save()}).status_code == status


def test_missing_and_wrong_master_key_fail_closed(configured_api, monkeypatch):
    client, db = configured_api
    assert client.patch("/v1/workspaces/w1/model-settings", headers=headers(), json={"generation": save()}).status_code == 200
    for key in (None, "invalid", base64.b64encode(b"y"*32).decode()):
        monkeypatch.setattr(settings, "model_config_encryption_key", key)
        with pytest.raises(ModelConfigurationError):
            resolve_connection(db, "w1", "generation")
        assert client.get("/v1/workspaces/w1/model-settings", headers=headers()).json()["generation"]["status"] == "unavailable"
        assert resolve_connection(db, "w2", "generation").source == "server"


def test_inherited_endpoint_credentials_never_exposed(configured_api, monkeypatch):
    client, _ = configured_api
    monkeypatch.setattr(settings, "openai_api_base", "https://user:CANARY_PASSWORD@example.test/v1?api_key=CANARY_QUERY")
    response = client.get("/v1/workspaces/w1/model-settings", headers=headers())
    assert response.status_code == 200
    assert response.json()["generation"]["baseUrl"] == ""
    assert "CANARY" not in response.text


def test_pair_snapshot_uses_one_select_and_refreshes_identity_map(configured_api):
    from sqlalchemy import event
    from ai_pdf_api.services.workspace_models import resolve_workspace_models
    client, db = configured_api
    payload = {"generation": save(), "embedding": {**save(), "protocol": "openai_embeddings"}}
    assert client.patch("/v1/workspaces/w1/model-settings", headers=headers(), json=payload).status_code == 200
    stale = db.get(WorkspaceModelConfig, ("w1", "generation"))
    db.execute(text("update workspace_model_configs set model='new-model' where workspace_id='w1'"))
    db.commit()
    calls = []
    def before(conn, cursor, statement, parameters, context, executemany):
        if "SELECT" in statement and "workspace_model_configs" in statement:
            calls.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", before)
    try:
        models = resolve_workspace_models(db, "w1")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", before)
    assert len(calls) == 1
    assert models.generation.model == models.embedding.model == "new-model"


def test_settings_repr_does_not_disclose_server_credentials():
    from ai_pdf_api.core.settings import Settings
    value = Settings(_env_file=None, openai_api_key="secret-marker", deepseek_api_key="secret-marker",
        database_url="secret-marker", minio_secret_key="secret-marker", minio_access_key="secret-marker",
        openai_api_base="https://secret-marker.invalid", deepseek_api_base="https://secret-marker.invalid",
        ollama_base_url="https://secret-marker.invalid", api_internal_token="secret-marker-long", capability_fingerprint_pepper="secret-marker-long")
    assert "secret-marker" not in repr(value)
