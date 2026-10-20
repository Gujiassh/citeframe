from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import (
    WorkspaceAccess,
    WorkspaceOwnerDependency,
    WorkspaceRequest,
    require_user_id,
    require_workspace_member,
)
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


model_settings_owner = WorkspaceOwnerDependency("Only workspace owners can manage model settings.")


def require_model_settings_update(
    workspace_id: str,
    payload: UpdateModelSettingsRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[UpdateModelSettingsRequest]:
    access = model_settings_owner.check(require_workspace_member(workspace_id, user_id, db))
    return WorkspaceRequest(access, payload)


@router.get("", response_model=WorkspaceModelSettingsResponse)
def get_model_settings(workspace_id: str, access: WorkspaceAccess = Depends(model_settings_owner), db: Session = Depends(get_db)):
    return settings_view(db, workspace_id)


@router.patch("", response_model=WorkspaceModelSettingsResponse)
def patch_model_settings(
    workspace_id: str,
    request: WorkspaceRequest[UpdateModelSettingsRequest] = Depends(require_model_settings_update),
    db: Session = Depends(get_db),
):
    access, payload = request.access, request.payload
    user_id = access.user_id
    update_model_settings(db, workspace_id, user_id, payload)
    result = settings_view(db, workspace_id)
    db.commit()
    return result
