from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import base64
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.evidence import EvidenceContractError, clone_evidence_locator
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    EvidenceLocator,
    MessageCitation,
    MessageInputEvidence,
    MessageRetrievalScope,
    MessageRetrievalScopeAsset,
    Workspace,
)
from ai_pdf_api.schemas.chat import AssetScope, EvidenceTargetRequest
from ai_pdf_api.modalities.pdf_evidence_targets import collect_retrieval_pdf_crop_payloads
from ai_pdf_api.services.evidence_targets import (
    EvidenceTargetError,
    ImageBytesLoader,
    ResolvedEvidenceTarget,
    resolve_evidence_targets,
)
from ai_pdf_api.services.storage import download_bytes
from ai_pdf_api.services.providers import (
    EmbeddingProvider,
    GenerationProvider,
    GenerationMessage,
    ModelProviderError,
    get_embedding_provider,
    get_generation_provider,
)
from ai_pdf_api.services.retrieval import RetrievedContent, retrieve_query_content


class ChatError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class CompletedChat:
    user_message: ChatMessage
    assistant_message: ChatMessage
    citations: list[MessageCitation]


@dataclass(frozen=True)
class PreparedChat:
    thread: ChatThread
    user_message: ChatMessage
    assistant_message: ChatMessage
    citations: list[MessageCitation]
    generation_messages: list[GenerationMessage]
    generation_provider: GenerationProvider


def prepare_chat(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
    thread: ChatThread,
    question: str,
    asset_scope: AssetScope,
    selection_text: str | None = None,
    evidence_targets: list[EvidenceTargetRequest] | None = None,
    parent_message_id: str | None = None,
    use_thread_active_parent: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    generation_provider: GenerationProvider | None = None,
    image_bytes_loader: ImageBytesLoader | None = None,
) -> PreparedChat:
    del user_id
    question_text = question.strip()
    if not question_text:
        raise ChatError("question_required", "Question must not be empty.", 422)

    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise ChatError("workspace_not_found", "Workspace not found.", 404)

    scoped_assets = _resolve_asset_scope(db, workspace_id, asset_scope)
    target_requests = evidence_targets or []
    scoped_asset_ids = {asset.id for asset in scoped_assets}
    if any(target.assetId not in scoped_asset_ids for target in target_requests):
        raise ChatError(
            "evidence_target_outside_scope",
            "Every evidence target must belong to the current asset scope.",
            422,
        )
    parent_id = thread.active_message_id if parent_message_id is None and use_thread_active_parent else parent_message_id
    if parent_id is not None:
        parent = db.scalar(
            select(ChatMessage).where(
                ChatMessage.id == parent_id,
                ChatMessage.thread_id == thread.id,
                ChatMessage.workspace_id == workspace_id,
            )
        )
        parent_is_replayable_failure = (
            parent is not None
            and parent.role == "assistant"
            and parent.status == "failed"
        )
        if parent is None or (parent.status != "completed" and not parent_is_replayable_failure):
            raise ChatError("invalid_parent_message", "The conversation parent is no longer available.", 422)

    try:
        now = datetime.now(UTC)
        resolved_targets = resolve_evidence_targets(
            db,
            workspace_id=workspace_id,
            targets=target_requests,
            created_at=now,
            **({"image_bytes_loader": image_bytes_loader} if image_bytes_loader else {}),
        )
        embedding = embedding_provider or get_embedding_provider()
        generation = generation_provider or get_generation_provider()
        query_embedding = embedding.embed_query(question_text)
        retrieved = retrieve_query_content(
            db,
            workspace_id,
            question_text,
            query_embedding,
            asset_ids=[asset.id for asset in scoped_assets],
            embedding_provider=embedding,
            limit=workspace.retrieval_top_k,
        )
        if not retrieved and not resolved_targets:
            raise ChatError(
                "no_retrieval_results",
                "No ready asset content matched this question in the selected scope.",
                422,
            )
        prior_messages = _get_message_lineage(db, thread.id, parent_id)
        context = _build_retrieval_context(retrieved)
        user_prompt = _build_user_prompt(question_text, context, selection_text)
        loader = image_bytes_loader or download_bytes
        retrieval_crop_payloads = collect_retrieval_pdf_crop_payloads(
            db,
            retrieved,
            image_bytes_loader=loader,
        )
        generation_messages = [
            {
                "role": "system",
                "content": workspace.system_prompt.strip(),
            },
            *({"role": message.role, "content": message.content} for message in prior_messages),
            _build_generation_user_message(
                user_prompt,
                resolved_targets,
                extra_image_payloads=retrieval_crop_payloads,
            ),
        ]

        user_message = ChatMessage(
            id=str(uuid4()),
            workspace_id=workspace_id,
            thread_id=thread.id,
            parent_message_id=parent_id,
            role="user",
            content=question_text,
            status="completed",
            created_at=now,
        )
        assistant_message = ChatMessage(
            id=str(uuid4()),
            workspace_id=workspace_id,
            thread_id=thread.id,
            parent_message_id=user_message.id,
            role="assistant",
            content="",
            status="streaming",
            model_provider=generation.provider,
            model_name=generation.model,
            created_at=now,
        )
        db.add_all([user_message, assistant_message])
        db.flush()
        db.add(
            MessageRetrievalScope(
                message_id=user_message.id,
                workspace_id=workspace_id,
                scope_mode=asset_scope.mode,
                created_at=now,
            )
        )
        db.flush()
        db.add_all(
            [
                MessageRetrievalScopeAsset(
                    message_id=user_message.id,
                    asset_id=asset.id,
                    asset_order=index,
                    asset_kind_snapshot=asset.asset_kind,
                    asset_title_snapshot=asset.title,
                )
                for index, asset in enumerate(scoped_assets)
            ]
        )
        input_evidence = [
            MessageInputEvidence(
                id=str(uuid4()),
                workspace_id=workspace_id,
                message_id=user_message.id,
                target_order=index,
                evidence_locator_id=target.locator.id,
                asset_id=target.asset.id,
                asset_kind_snapshot=target.asset.asset_kind,
                asset_title_snapshot=target.asset.title,
                excerpt_snapshot=target.excerpt,
                processing_generation_snapshot=target.locator.processing_generation_snapshot,
                representation_id_snapshot=target.locator.representation_id_snapshot,
                parser_version_snapshot=target.representation.generator_version,
                index_version_snapshot=target.asset.current_index_version,
                created_at=now,
            )
            for index, target in enumerate(resolved_targets)
        ]
        db.add_all(input_evidence)

        citations: list[MessageCitation] = []
        for index, item in enumerate(retrieved):
            locator = clone_evidence_locator(
                db,
                item.content_unit.source_locator_id,
                created_at=now,
                workspace_id=workspace_id,
                asset_id=item.asset.id,
                representation_id=item.content_unit.representation_id,
            )
            representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
            if representation is None:
                raise ChatError("evidence_representation_missing", "Evidence representation is missing.", 500)
            citations.append(MessageCitation(
                id=str(uuid4()),
                workspace_id=workspace_id,
                message_id=assistant_message.id,
                citation_index=index,
                evidence_locator_id=locator.id,
                asset_id=item.asset.id,
                asset_kind_snapshot=item.asset.asset_kind,
                asset_title_snapshot=item.asset.title,
                excerpt_snapshot=item.content_unit.text_content[:800],
                processing_generation_snapshot=locator.processing_generation_snapshot,
                representation_id_snapshot=locator.representation_id_snapshot,
                parser_version_snapshot=representation.generator_version,
                index_version_snapshot=item.content_unit.index_version,
                created_at=now,
            ))
        db.add_all(citations)
        thread.title = thread.title or question_text[:80]
        thread.last_message_at = now
        thread.updated_at = now
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)
        return PreparedChat(
            thread=thread,
            user_message=user_message,
            assistant_message=assistant_message,
            citations=citations,
            generation_messages=generation_messages,
            generation_provider=generation,
        )
    except ChatError:
        db.rollback()
        raise
    except ModelProviderError as error:
        db.rollback()
        raise ChatError(error.code, error.message, 502) from error
    except EvidenceContractError as error:
        db.rollback()
        raise ChatError(
            "evidence_contract_invalid",
            "Retrieved content contains invalid evidence.",
            500,
        ) from error
    except EvidenceTargetError as error:
        db.rollback()
        raise ChatError(error.code, error.message, error.status_code) from error
    except Exception:
        db.rollback()
        raise


def finalize_chat(db: Session, prepared: PreparedChat, answer: str) -> CompletedChat:
    if not answer.strip():
        fail_chat(db, prepared, "generation_empty", "Generation provider returned an empty answer.")
        raise ModelProviderError("generation_empty", "Generation provider returned an empty answer.")

    prepared.assistant_message.content = answer.strip()
    prepared.assistant_message.status = "completed"
    prepared.thread.active_message_id = prepared.assistant_message.id
    prepared.thread.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(prepared.user_message)
    db.refresh(prepared.assistant_message)
    return CompletedChat(
        user_message=prepared.user_message,
        assistant_message=prepared.assistant_message,
        citations=prepared.citations,
    )


def fail_chat(db: Session, prepared: PreparedChat, code: str, message: str) -> None:
    db.rollback()
    assistant = db.get(ChatMessage, prepared.assistant_message.id)
    thread = db.get(ChatThread, prepared.thread.id)
    locator_ids = db.scalars(
        select(MessageCitation.evidence_locator_id).where(
            MessageCitation.message_id == prepared.assistant_message.id
        )
    ).all()
    db.execute(delete(MessageCitation).where(MessageCitation.message_id == prepared.assistant_message.id))
    if locator_ids:
        db.execute(delete(EvidenceLocator).where(EvidenceLocator.id.in_(locator_ids)))
    if assistant is not None:
        assistant.status = "failed"
        assistant.content = message
    if thread is not None:
        if assistant is not None:
            thread.active_message_id = assistant.id
        thread.updated_at = datetime.now(UTC)
    db.commit()


def complete_chat(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
    thread: ChatThread,
    question: str,
    asset_scope: AssetScope,
    selection_text: str | None = None,
    evidence_targets: list[EvidenceTargetRequest] | None = None,
    parent_message_id: str | None = None,
    use_thread_active_parent: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    generation_provider: GenerationProvider | None = None,
    image_bytes_loader: ImageBytesLoader | None = None,
) -> CompletedChat:
    prepared = prepare_chat(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        thread=thread,
        question=question,
        asset_scope=asset_scope,
        selection_text=selection_text,
        evidence_targets=evidence_targets,
        parent_message_id=parent_message_id,
        use_thread_active_parent=use_thread_active_parent,
        embedding_provider=embedding_provider,
        generation_provider=generation_provider,
        image_bytes_loader=image_bytes_loader,
    )
    try:
        answer = prepared.generation_provider.generate(prepared.generation_messages)
        return finalize_chat(db, prepared, answer)
    except ModelProviderError as error:
        fail_chat(db, prepared, error.code, error.message)
        raise
    except Exception as error:
        fail_chat(db, prepared, "generation_failed", str(error))
        raise


def _get_message_lineage(db: Session, thread_id: str, leaf_id: str | None) -> list[ChatMessage]:
    if leaf_id is None:
        return []
    messages = db.scalars(select(ChatMessage).where(ChatMessage.thread_id == thread_id)).all()
    by_id = {message.id: message for message in messages}
    lineage: list[ChatMessage] = []
    current_id: str | None = leaf_id
    visited: set[str] = set()
    while current_id is not None:
        if current_id in visited:
            raise ChatError("invalid_message_graph", "The conversation message graph contains a cycle.", 500)
        visited.add(current_id)
        current = by_id.get(current_id)
        if current is None:
            raise ChatError("invalid_parent_message", "The conversation parent is no longer available.", 422)
        if current.status == "completed":
            lineage.append(current)
        current_id = current.parent_message_id
    lineage.reverse()
    return lineage


def active_message_path(db: Session, thread: ChatThread) -> list[ChatMessage]:
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.thread_id == thread.id).order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()
    if not messages:
        return []
    leaf_id = thread.active_message_id
    if leaf_id is None:
        raise ChatError("invalid_message_graph", "The conversation has messages but no active leaf.", 500)
    by_id = {message.id: message for message in messages}
    path: list[ChatMessage] = []
    visited: set[str] = set()
    current_id: str | None = leaf_id
    while current_id is not None:
        if current_id in visited:
            raise ChatError("invalid_message_graph", "The conversation message graph contains a cycle.", 500)
        visited.add(current_id)
        current = by_id.get(current_id)
        if current is None:
            raise ChatError("invalid_message_graph", "The active conversation leaf is missing.", 500)
        path.append(current)
        current_id = current.parent_message_id
    path.reverse()
    return path


def _build_retrieval_context(items: list[RetrievedContent]) -> str:
    sections = []
    for index, item in enumerate(items, start=1):
        sections.append(
            f"[{index}] {item.asset.title}, {item.locator.locator_kind}\n"
            f"{item.content_unit.text_content[:4000]}"
        )
    return "\n\n".join(sections)


def _build_user_prompt(question: str, context: str, selection_text: str | None) -> str:
    selected = ""
    if selection_text and selection_text.strip():
        selected = f"\n\nSelected text from the PDF:\n{selection_text.strip()[:12000]}"
    return f"Question:\n{question}{selected}\n\nAsset evidence context:\n{context}"


def _build_generation_user_message(
    prompt: str,
    targets: list[ResolvedEvidenceTarget],
    extra_image_payloads: tuple[bytes, ...] = (),
) -> GenerationMessage:
    image_payloads: list[bytes] = []
    for target in targets:
        image_payloads.extend(target.image_payloads)
    image_payloads.extend(extra_image_payloads)
    if not image_payloads:
        return {"role": "user", "content": prompt}
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for payload in image_payloads:
        encoded = base64.b64encode(payload).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": "high",
            }
        )
    return {"role": "user", "content": content}


def _resolve_asset_scope(db: Session, workspace_id: str, scope: AssetScope) -> list[Asset]:
    if scope.mode == "all_ready":
        assets = db.scalars(
            select(Asset)
            .where(
                Asset.workspace_id == workspace_id,
                Asset.status == "ready",
                Asset.deleted_at.is_(None),
            )
            .order_by(Asset.created_at, Asset.id)
        ).all()
    else:
        by_id = {
            asset.id: asset
            for asset in db.scalars(
                select(Asset).where(
                    Asset.id.in_(scope.assetIds),
                    Asset.workspace_id == workspace_id,
                    Asset.deleted_at.is_(None),
                )
            ).all()
        }
        if len(by_id) != len(scope.assetIds):
            raise ChatError(
                "invalid_asset_scope",
                "One or more selected assets are not available in this workspace.",
                422,
            )
        assets = [by_id[asset_id] for asset_id in scope.assetIds]
        if any(asset.status != "ready" for asset in assets):
            raise ChatError("invalid_asset_scope", "Every selected asset must be ready.", 422)
    if not assets:
        raise ChatError("empty_asset_scope", "The question scope contains no ready assets.", 422)
    return assets
