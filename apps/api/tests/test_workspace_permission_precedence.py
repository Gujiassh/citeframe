from sqlalchemy import func, select

from ai_pdf_api.models import WorkspaceModelConfig
from test_workspace_model_settings import configured_api, headers


def test_invalid_payload_precedes_model_settings_permission(configured_api):
    client, db = configured_api
    before = db.scalar(select(func.count()).select_from(WorkspaceModelConfig))
    for user in ("owner", "member", "outsider"):
        response = client.patch(
            "/v1/workspaces/w1/model-settings", headers=headers(user), json={},
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": {"code": "model_settings_invalid", "message": "Invalid model settings."},
        }
    assert db.scalar(select(func.count()).select_from(WorkspaceModelConfig)) == before


def test_internal_auth_precedes_payload_validation(configured_api):
    client, _ = configured_api
    for auth in ({}, {"x-user-id": "owner"}, {**headers(), "x-ai-pdf-internal-token": "invalid"}):
        response = client.patch("/v1/workspaces/w1/model-settings", headers=auth, json={})
        assert response.status_code == 401
        assert response.json() == {"detail": "Internal API authentication required."}
