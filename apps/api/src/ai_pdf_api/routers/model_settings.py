from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import get_accessible_workspace, require_user_id
from ai_pdf_api.schemas.model_settings import UpdateModelSettingsRequest, WorkspaceModelSettingsResponse
from ai_pdf_api.services.model_config_types import ModelConfigurationError
from ai_pdf_api.services.workspace_models import settings_view, update_model_settings


class SecretSafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(422, detail={"code": "model_settings_invalid", "message": "Invalid model settings."}) from None
            except ModelConfigurationError as error:
                raise HTTPException(error.status, detail={"code": error.code, "message": error.message}) from None
        return handler


router = APIRouter(prefix="/v1/workspaces/{workspace_id}/model-settings", tags=["workspaces"], route_class=SecretSafeRoute)


def _require_owner(db, workspace_id, user_id):
    _, role = get_accessible_workspace(db, user_id, workspace_id)
    if role != "owner":
        raise HTTPException(403, detail="Only workspace owners can manage model settings.")


@router.get("", response_model=WorkspaceModelSettingsResponse)
def get_model_settings(workspace_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)):
    _require_owner(db, workspace_id, user_id)
    return settings_view(db, workspace_id)


@router.patch("", response_model=WorkspaceModelSettingsResponse)
def patch_model_settings(workspace_id: str, payload: UpdateModelSettingsRequest,
                         user_id: str = Depends(require_user_id), db: Session = Depends(get_db)):
    _require_owner(db, workspace_id, user_id)
    update_model_settings(db, workspace_id, user_id, payload)
    result = settings_view(db, workspace_id)
    db.commit()
    return result
