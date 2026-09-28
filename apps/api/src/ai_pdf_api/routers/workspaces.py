from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.workspace_models import configuration_row, server_connection
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import Asset, ChatThread, Note, User, Workspace, WorkspaceMembership
from ai_pdf_api.routers.deps import (
    WorkspaceAccess,
    WorkspaceOwnerDependency,
    WorkspaceRequest,
    base_workspace_query_for_user,
    require_user_id,
    require_workspace_member,
    require_workspace_member_existing_user,
)
from ai_pdf_api.schemas.workspace import (
    CreateWorkspaceRequest,
    CreateWorkspaceResponse,
    UpdateWorkspaceSettingsRequest,
    WorkspaceSettingsResponse,
    WorkspaceDetailResponse,
    WorkspaceListResponse,
    WorkspaceSummary,
)

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


def require_existing_user(user_id: str, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user not found.",
        )
    return user


def count_threads_for_workspaces(db: Session, workspace_ids: list[str]) -> dict[str, int]:
    if not workspace_ids:
        return {}
    rows = db.execute(
        select(ChatThread.workspace_id, func.count(ChatThread.id))
        .where(ChatThread.workspace_id.in_(workspace_ids), ChatThread.archived_at.is_(None))
        .group_by(ChatThread.workspace_id),
    ).all()
    return {workspace_id: count for workspace_id, count in rows}


def count_assets_for_workspaces(db: Session, workspace_ids: list[str]) -> dict[str, int]:
    if not workspace_ids:
        return {}
    rows = db.execute(
        select(Asset.workspace_id, func.count(Asset.id))
        .where(Asset.workspace_id.in_(workspace_ids), Asset.deleted_at.is_(None))
        .group_by(Asset.workspace_id),
    ).all()
    return {workspace_id: count for workspace_id, count in rows}


def count_notes_for_workspaces(db: Session, workspace_ids: list[str]) -> dict[str, int]:
    if not workspace_ids:
        return {}
    rows = db.execute(
        select(Note.workspace_id, func.count(Note.id))
        .where(Note.workspace_id.in_(workspace_ids), Note.archived_at.is_(None))
        .group_by(Note.workspace_id),
    ).all()
    return {workspace_id: count for workspace_id, count in rows}


def to_workspace_summary(
    workspace: Workspace,
    role: str,
    asset_count: int = 0,
    thread_count: int = 0,
    note_count: int = 0,
    db: Session | None = None,
) -> WorkspaceSummary:
    generation = server_connection("generation")
    embedding = server_connection("embedding")
    if db is not None:
        from dataclasses import replace
        for capability in ("generation", "embedding"):
            row = configuration_row(db, workspace.id, capability)
            if row and row.mode == "override":
                if capability == "generation":
                    generation = replace(generation, provider="openai", model=row.model)
                else:
                    embedding = replace(embedding, provider="openai", model=row.model)
    return WorkspaceSummary(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        systemPrompt=workspace.system_prompt,
        retrievalTopK=workspace.retrieval_top_k,
        chunkSize=workspace.chunk_size,
        embeddingProvider=embedding.provider,
        embeddingModel=embedding.model,
        embeddingDimensions=settings.embedding_dimensions,
        embeddingVersion=settings.embedding_version,
        generationProvider=generation.provider,
        generationModel=generation.model,
        role=role,
        assetCount=asset_count,
        noteCount=note_count,
        threadCount=thread_count,
        createdAt=workspace.created_at.astimezone(UTC).isoformat(),
        updatedAt=workspace.updated_at.astimezone(UTC).isoformat(),
    )


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces(
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceListResponse:
    require_existing_user(user_id, db)
    rows = db.execute(
        base_workspace_query_for_user(user_id).order_by(Workspace.updated_at.desc(), Workspace.created_at.desc()),
    ).all()
    workspace_ids = [workspace.id for workspace, _role in rows]
    counts = count_assets_for_workspaces(db, workspace_ids)
    note_counts = count_notes_for_workspaces(db, workspace_ids)
    thread_counts = count_threads_for_workspaces(db, workspace_ids)
    items = [
        to_workspace_summary(
            workspace,
            role,
            counts.get(workspace.id, 0),
            thread_counts.get(workspace.id, 0),
            note_counts.get(workspace.id, 0),
            db=db,
        )
        for workspace, role in rows
    ]
    return WorkspaceListResponse(items=items, nextCursor=None)


@router.post("", response_model=CreateWorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: CreateWorkspaceRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> CreateWorkspaceResponse:
    user = require_existing_user(user_id, db)
    now = datetime.now(UTC)
    workspace = Workspace(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(workspace)
    db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    db.commit()
    db.refresh(workspace)
    return CreateWorkspaceResponse(workspace=to_workspace_summary(workspace, membership.role, 0, 0, 0, db=db))


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
def get_workspace(
    workspace_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member_existing_user),
    db: Session = Depends(get_db),
) -> WorkspaceDetailResponse:
    role = access.role
    workspace = access.workspace
    asset_count = count_assets_for_workspaces(db, [workspace.id]).get(workspace.id, 0)
    note_count = count_notes_for_workspaces(db, [workspace.id]).get(workspace.id, 0)
    thread_count = count_threads_for_workspaces(db, [workspace.id]).get(workspace.id, 0)
    return WorkspaceDetailResponse(
        workspace=to_workspace_summary(workspace, role, asset_count, thread_count, note_count, db=db)
    )


update_workspace_settings_owner = WorkspaceOwnerDependency('Only workspace owners can update workspace settings.')


def require_update_workspace_settings_access(
    workspace_id: str,
    payload: UpdateWorkspaceSettingsRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[UpdateWorkspaceSettingsRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    access = update_workspace_settings_owner.check(access)
    return WorkspaceRequest(access, payload)


@router.patch("/{workspace_id}/settings", response_model=WorkspaceSettingsResponse)
def update_workspace_settings(
    workspace_id: str,
    workspace_request: WorkspaceRequest[UpdateWorkspaceSettingsRequest] = Depends(require_update_workspace_settings_access),
    db: Session = Depends(get_db),
) -> WorkspaceSettingsResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    role = access.role

    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    workspace.system_prompt = payload.systemPrompt.strip()
    workspace.retrieval_top_k = payload.retrievalTopK
    workspace.chunk_size = payload.chunkSize
    workspace.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(workspace)
    return WorkspaceSettingsResponse(
        workspace=to_workspace_summary(
            workspace,
            role,
            count_assets_for_workspaces(db, [workspace.id]).get(workspace.id, 0),
            count_threads_for_workspaces(db, [workspace.id]).get(workspace.id, 0),
            count_notes_for_workspaces(db, [workspace.id]).get(workspace.id, 0),
            db=db,
        )
    )


archive_workspace_owner = WorkspaceOwnerDependency('Only workspace owners can archive this workspace.')


def require_archive_workspace_access(
    workspace_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceAccess:
    require_existing_user(user_id, db)
    access = require_workspace_member(workspace_id, user_id, db)
    access = archive_workspace_owner.check(access)
    return access


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_workspace(
    workspace_id: str,
    access: WorkspaceAccess = Depends(require_archive_workspace_access),
    db: Session = Depends(get_db),
) -> Response:
    workspace = access.workspace

    now = datetime.now(UTC)
    workspace.archived_at = now
    workspace.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
