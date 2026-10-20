from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import WorkspaceAccess, WorkspaceRequest, require_user_id, require_workspace_member
from ai_pdf_api.schemas.notes import (
    CreateNoteRequest,
    CreateNoteResponse,
    CreateTagRequest,
    NoteListResponse,
    NoteResponse,
    TagBindingsRequest,
    TagBindingsResponse,
    TagListResponse,
    TagResponse,
    UpdateNoteRequest,
    UpdateTagRequest,
)
from ai_pdf_api.services.notes import (
    NotesError,
    archive_note,
    create_note,
    create_tag,
    delete_tag,
    get_note,
    get_tag,
    list_notes,
    list_tags,
    replace_asset_tags,
    replace_note_tags,
    update_note,
    update_tag,
)

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["notes"])


def _http_error(error: NotesError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.get("/notes", response_model=NoteListResponse)
def list_workspace_notes(
    workspace_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    try:
        return list_notes(db, workspace_id)
    except NotesError as error:
        raise _http_error(error) from error


@router.get("/notes/{note_id}", response_model=NoteResponse)
def get_workspace_note(
    workspace_id: str,
    note_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> NoteResponse:
    try:
        return get_note(db, workspace_id, note_id)
    except NotesError as error:
        raise _http_error(error) from error


def require_create_workspace_note_access(
    workspace_id: str,
    payload: CreateNoteRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[CreateNoteRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/notes", response_model=CreateNoteResponse, status_code=status.HTTP_201_CREATED)
def create_workspace_note(
    workspace_id: str,
    workspace_request: WorkspaceRequest[CreateNoteRequest] = Depends(require_create_workspace_note_access),
    db: Session = Depends(get_db),
) -> CreateNoteResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    user_id = access.user_id
    try:
        return create_note(db, workspace_id, user_id, payload)
    except NotesError as error:
        raise _http_error(error) from error


def require_update_workspace_note_access(
    workspace_id: str,
    payload: UpdateNoteRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[UpdateNoteRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.patch("/notes/{note_id}", response_model=NoteResponse)
def update_workspace_note(
    workspace_id: str,
    note_id: str,
    workspace_request: WorkspaceRequest[UpdateNoteRequest] = Depends(require_update_workspace_note_access),
    db: Session = Depends(get_db),
) -> NoteResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    user_id = access.user_id
    try:
        return update_note(db, workspace_id, note_id, user_id, payload)
    except NotesError as error:
        raise _http_error(error) from error


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace_note(
    workspace_id: str,
    note_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> Response:
    try:
        archive_note(db, workspace_id, note_id)
    except NotesError as error:
        raise _http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tags", response_model=TagListResponse)
def list_workspace_tags(
    workspace_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> TagListResponse:
    try:
        return list_tags(db, workspace_id)
    except NotesError as error:
        raise _http_error(error) from error


@router.get("/tags/{tag_id}", response_model=TagResponse)
def get_workspace_tag(
    workspace_id: str,
    tag_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> TagResponse:
    try:
        return get_tag(db, workspace_id, tag_id)
    except NotesError as error:
        raise _http_error(error) from error


def require_create_workspace_tag_access(
    workspace_id: str,
    payload: CreateTagRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[CreateTagRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_workspace_tag(
    workspace_id: str,
    workspace_request: WorkspaceRequest[CreateTagRequest] = Depends(require_create_workspace_tag_access),
    db: Session = Depends(get_db),
) -> TagResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    user_id = access.user_id
    try:
        return create_tag(db, workspace_id, user_id, payload)
    except NotesError as error:
        raise _http_error(error) from error


def require_update_workspace_tag_access(
    workspace_id: str,
    payload: UpdateTagRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[UpdateTagRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.patch("/tags/{tag_id}", response_model=TagResponse)
def update_workspace_tag(
    workspace_id: str,
    tag_id: str,
    workspace_request: WorkspaceRequest[UpdateTagRequest] = Depends(require_update_workspace_tag_access),
    db: Session = Depends(get_db),
) -> TagResponse:
    payload = workspace_request.payload
    try:
        return update_tag(db, workspace_id, tag_id, payload)
    except NotesError as error:
        raise _http_error(error) from error


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace_tag(
    workspace_id: str,
    tag_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_tag(db, workspace_id, tag_id)
    except NotesError as error:
        raise _http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def require_replace_workspace_asset_tags_access(
    workspace_id: str,
    payload: TagBindingsRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[TagBindingsRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/assets/{asset_id}/tags", response_model=TagBindingsResponse)
def replace_workspace_asset_tags(
    workspace_id: str,
    asset_id: str,
    workspace_request: WorkspaceRequest[TagBindingsRequest] = Depends(require_replace_workspace_asset_tags_access),
    db: Session = Depends(get_db),
) -> TagBindingsResponse:
    payload = workspace_request.payload
    try:
        return replace_asset_tags(db, workspace_id, asset_id, payload.tagIds)
    except NotesError as error:
        raise _http_error(error) from error


def require_replace_workspace_note_tags_access(
    workspace_id: str,
    payload: TagBindingsRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[TagBindingsRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/notes/{note_id}/tags", response_model=TagBindingsResponse)
def replace_workspace_note_tags(
    workspace_id: str,
    note_id: str,
    workspace_request: WorkspaceRequest[TagBindingsRequest] = Depends(require_replace_workspace_note_tags_access),
    db: Session = Depends(get_db),
) -> TagBindingsResponse:
    payload = workspace_request.payload
    try:
        return replace_note_tags(db, workspace_id, note_id, payload.tagIds)
    except NotesError as error:
        raise _http_error(error) from error
