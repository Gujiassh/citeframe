from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Header, HTTPException, status

from ai_pdf_api.core.settings import settings
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import User, Workspace, WorkspaceMembership

UserIdHeader = Annotated[str | None, Header(alias="x-user-id")]
InternalTokenHeader = Annotated[str | None, Header(alias="x-ai-pdf-internal-token")]


def require_internal_api_token(x_internal_token: InternalTokenHeader = None) -> None:
    if not x_internal_token or not secrets.compare_digest(x_internal_token, settings.api_internal_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal API authentication required.",
        )


def require_user_id(
    x_user_id: UserIdHeader = None,
    _internal_token: None = Depends(require_internal_api_token),
) -> str:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return x_user_id


def require_existing_user(
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user not found.",
        )
    return user


def base_workspace_query_for_user(user_id: str) -> Select[tuple[Workspace, str]]:
    return (
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.archived_at.is_(None),
        )
    )


def get_accessible_workspace(db: Session, user_id: str, workspace_id: str) -> tuple[Workspace, str]:
    row = db.execute(
        base_workspace_query_for_user(user_id).where(Workspace.id == workspace_id),
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )
    workspace, role = row
    return workspace, role


@dataclass(frozen=True)
class WorkspaceAccess:
    user_id: str
    workspace_id: str
    role: str
    workspace: Workspace


Payload = TypeVar("Payload")


@dataclass(frozen=True)
class WorkspaceRequest(Generic[Payload]):
    # Returning validated inputs with access avoids validating them again in the endpoint,
    # which would duplicate errors and change validation-versus-permission precedence.
    access: WorkspaceAccess
    payload: Payload


def require_workspace_member(
    workspace_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceAccess:
    workspace, role = get_accessible_workspace(db, user_id, workspace_id)
    return WorkspaceAccess(user_id, workspace_id, role, workspace)


class WorkspaceOwnerDependency:
    def __init__(self, detail: str = "Workspace owner access required.") -> None:
        self.detail = detail

    def check(self, access: WorkspaceAccess) -> WorkspaceAccess:
        if access.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=self.detail)
        return access

    def __call__(
        self, access: WorkspaceAccess = Depends(require_workspace_member),
    ) -> WorkspaceAccess:
        return self.check(access)


require_workspace_owner = WorkspaceOwnerDependency()


def require_workspace_member_existing_user(
    workspace_id: str,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> WorkspaceAccess:
    return require_workspace_member(workspace_id, user.id, db)
