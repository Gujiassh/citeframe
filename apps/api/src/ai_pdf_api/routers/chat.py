from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.evidence import serialize_evidence_locator
from ai_pdf_api.models import Asset, ChatMessage, ChatThread, MessageCitation, MessageInputEvidence
from ai_pdf_api.routers.deps import WorkspaceAccess, WorkspaceRequest, require_user_id, require_workspace_member
from ai_pdf_api.schemas.chat import (
    ChatStreamRequest,
    Citation,
    CreateThreadRequest,
    CreateThreadResponse,
    InputEvidence,
    Message,
    SourceVersions,
    ThreadListResponse,
    ThreadMessagesResponse,
    ThreadSummary,
)
from ai_pdf_api.services.chat import ChatError, active_message_path, fail_chat, finalize_chat, prepare_chat
from ai_pdf_api.services.providers import ModelProviderError

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["chat"])


def to_thread_summary(thread: ChatThread) -> ThreadSummary:
    return ThreadSummary(
        id=thread.id,
        workspaceId=thread.workspace_id,
        title=thread.title,
        lastMessageAt=thread.last_message_at.astimezone(UTC).isoformat(),
        createdAt=thread.created_at.astimezone(UTC).isoformat(),
    )


def to_citation(db: Session, citation: MessageCitation) -> Citation:
    asset = db.get(Asset, citation.asset_id)
    return Citation(
        id=citation.id,
        messageId=citation.message_id,
        citationIndex=citation.citation_index,
        assetId=citation.asset_id,
        assetKind=citation.asset_kind_snapshot,
        assetTitle=citation.asset_title_snapshot,
        sourceAvailable=asset is not None and asset.deleted_at is None,
        excerpt=citation.excerpt_snapshot,
        locator=serialize_evidence_locator(
            db,
            citation.evidence_locator_id,
            workspace_id=citation.workspace_id,
            asset_id=citation.asset_id,
            processing_generation=citation.processing_generation_snapshot,
            representation_id=citation.representation_id_snapshot,
        ),
        sourceVersions=SourceVersions(
            parserVersion=citation.parser_version_snapshot,
            processingGeneration=citation.processing_generation_snapshot,
            representationId=citation.representation_id_snapshot,
            indexVersion=citation.index_version_snapshot,
        ),
    )


def to_input_evidence(db: Session, evidence: MessageInputEvidence) -> InputEvidence:
    asset = db.get(Asset, evidence.asset_id)
    return InputEvidence(
        id=evidence.id,
        messageId=evidence.message_id,
        targetOrder=evidence.target_order,
        assetId=evidence.asset_id,
        assetKind=evidence.asset_kind_snapshot,
        assetTitle=evidence.asset_title_snapshot,
        sourceAvailable=asset is not None and asset.deleted_at is None,
        excerpt=evidence.excerpt_snapshot,
        locator=serialize_evidence_locator(
            db,
            evidence.evidence_locator_id,
            workspace_id=evidence.workspace_id,
            asset_id=evidence.asset_id,
            processing_generation=evidence.processing_generation_snapshot,
            representation_id=evidence.representation_id_snapshot,
        ),
        sourceVersions=SourceVersions(
            parserVersion=evidence.parser_version_snapshot,
            processingGeneration=evidence.processing_generation_snapshot,
            representationId=evidence.representation_id_snapshot,
            indexVersion=evidence.index_version_snapshot,
        ),
    )


def to_message(
    db: Session,
    message: ChatMessage,
    citations: list[MessageCitation],
    input_evidence: list[MessageInputEvidence],
) -> Message:
    return Message(
        id=message.id,
        workspaceId=message.workspace_id,
        threadId=message.thread_id,
        parentMessageId=message.parent_message_id,
        role=message.role,
        content=message.content,
        status=message.status,
        modelProvider=message.model_provider,
        modelName=message.model_name,
        createdAt=message.created_at.astimezone(UTC).isoformat(),
        citations=[to_citation(db, citation) for citation in citations],
        inputEvidence=[to_input_evidence(db, evidence) for evidence in input_evidence],
    )


def get_workspace_thread(db: Session, workspace_id: str, thread_id: str) -> ChatThread:
    thread = db.scalar(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.workspace_id == workspace_id,
            ChatThread.archived_at.is_(None),
        )
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found.")
    return thread


@router.get("/threads", response_model=ThreadListResponse)
def list_threads(
    workspace_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ThreadListResponse:
    threads = db.scalars(
        select(ChatThread)
        .where(ChatThread.workspace_id == workspace_id, ChatThread.archived_at.is_(None))
        .order_by(ChatThread.last_message_at.desc(), ChatThread.created_at.desc())
    ).all()
    return ThreadListResponse(items=[to_thread_summary(thread) for thread in threads], nextCursor=None)


def require_create_thread_access(
    workspace_id: str,
    payload: CreateThreadRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[CreateThreadRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/threads", response_model=CreateThreadResponse, status_code=status.HTTP_201_CREATED)
def create_thread(
    workspace_id: str,
    workspace_request: WorkspaceRequest[CreateThreadRequest] = Depends(require_create_thread_access),
    db: Session = Depends(get_db),
) -> CreateThreadResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    user_id = access.user_id
    now = datetime.now(UTC)
    thread = ChatThread(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        title=payload.title.strip() if payload.title and payload.title.strip() else None,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return CreateThreadResponse(thread=to_thread_summary(thread))


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_thread(
    workspace_id: str,
    thread_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
):
    user_id = access.user_id
    role = access.role
    thread = get_workspace_thread(db, workspace_id, thread_id)
    if role != "owner" and thread.created_by_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot archive this thread.")
    thread.archived_at = datetime.now(UTC)
    thread.updated_at = thread.archived_at
    db.commit()
    return None


@router.get("/threads/{thread_id}/messages", response_model=ThreadMessagesResponse)
def list_thread_messages(
    workspace_id: str,
    thread_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ThreadMessagesResponse:
    thread = get_workspace_thread(db, workspace_id, thread_id)
    messages = active_message_path(db, thread)
    citations = db.scalars(
        select(MessageCitation)
        .where(MessageCitation.message_id.in_([message.id for message in messages]))
        .order_by(MessageCitation.message_id, MessageCitation.citation_index)
    ).all() if messages else []
    citation_by_message: dict[str, list[MessageCitation]] = {}
    for citation in citations:
        citation_by_message.setdefault(citation.message_id, []).append(citation)
    input_rows = db.scalars(
        select(MessageInputEvidence)
        .where(MessageInputEvidence.message_id.in_([message.id for message in messages]))
        .order_by(MessageInputEvidence.message_id, MessageInputEvidence.target_order)
    ).all() if messages else []
    input_by_message: dict[str, list[MessageInputEvidence]] = {}
    for evidence in input_rows:
        input_by_message.setdefault(evidence.message_id, []).append(evidence)
    return ThreadMessagesResponse(
        thread=to_thread_summary(thread),
        messages=[
            to_message(
                db,
                message,
                citation_by_message.get(message.id, []),
                input_by_message.get(message.id, []),
            )
            for message in messages
        ],
    )


def require_stream_chat_access(
    workspace_id: str,
    payload: ChatStreamRequest,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[ChatStreamRequest]:
    access = require_workspace_member(workspace_id, user_id, db)
    return WorkspaceRequest(access, payload)


@router.post("/chat/stream")
def stream_chat(
    workspace_id: str,
    workspace_request: WorkspaceRequest[ChatStreamRequest] = Depends(require_stream_chat_access),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    access = workspace_request.access
    payload = workspace_request.payload
    user_id = access.user_id
    thread = get_workspace_thread(db, workspace_id, payload.threadId)
    try:
        parent_message_id = _resolve_parent_message_id(db, thread, payload)
        prepared = prepare_chat(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            thread=thread,
            question=payload.question,
            asset_scope=payload.assetScope,
            selection_text=payload.selectionText,
            evidence_targets=payload.evidenceTargets,
            parent_message_id=parent_message_id,
            use_thread_active_parent=not bool(payload.editMessageId),
        )
    except ChatError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error

    def events():
        yield _sse(
            "meta",
            {
                "threadId": thread.id,
                "userMessageId": prepared.user_message.id,
                "assistantMessageId": prepared.assistant_message.id,
            },
        )
        answer_parts: list[str] = []
        stream_finalized = False
        try:
            for delta in prepared.generation_provider.stream(prepared.generation_messages):
                answer_parts.append(delta)
                yield _sse("delta", {"text": delta})
            completed = finalize_chat(db, prepared, "".join(answer_parts))
            stream_finalized = True
            yield _sse(
                "citations",
                {"items": [to_citation(db, citation).model_dump() for citation in completed.citations]},
            )
            yield _sse("done", {"threadId": thread.id, "assistantMessageId": completed.assistant_message.id})
        except ModelProviderError as error:
            fail_chat(db, prepared, error.code, error.message)
            yield _sse("error", {"code": error.code, "message": error.message})
        except GeneratorExit:
            if not stream_finalized:
                fail_chat(db, prepared, "generation_interrupted", "Chat generation was interrupted.")
            raise
        except Exception:
            fail_chat(db, prepared, "generation_failed", "Chat generation failed.")
            yield _sse("error", {"code": "generation_failed", "message": "Chat generation failed."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _resolve_parent_message_id(db: Session, thread: ChatThread, payload: ChatStreamRequest) -> str | None:
    if payload.editMessageId:
        message = db.scalar(
            select(ChatMessage).where(
                ChatMessage.id == payload.editMessageId,
                ChatMessage.thread_id == thread.id,
                ChatMessage.workspace_id == thread.workspace_id,
            )
        )
        if message is None or message.role != "user" or message.status != "completed":
            raise ChatError("invalid_edit_message", "Only a completed user question can be edited.", 422)
        return message.parent_message_id

    parent_id = payload.parentMessageId if payload.parentMessageId is not None else thread.active_message_id
    if parent_id is None:
        return None
    parent = db.scalar(
        select(ChatMessage).where(
            ChatMessage.id == parent_id,
            ChatMessage.thread_id == thread.id,
            ChatMessage.workspace_id == thread.workspace_id,
        )
    )
    parent_is_replayable_failure = (
        parent is not None
        and parent.role == "assistant"
        and parent.status == "failed"
    )
    if parent is None or (parent.status != "completed" and not parent_is_replayable_failure):
        raise ChatError("invalid_parent_message", "The conversation parent is no longer available.", 422)
    return parent.id
