from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    PdfLocatorDetail,
    PdfPage,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.chat import router
from ai_pdf_api.services.providers import ModelProviderError


class RouterEmbeddingProvider:
    provider = "router-test"
    model = "router-embedding"
    dimensions = 3
    version = "router-v1"

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class RouterGenerationProvider:
    provider = "router-test"
    model = "router-generation"

    def __init__(self) -> None:
        self.fail = True

    def stream(self, _messages):
        if self.fail:
            self.fail = False
            raise ModelProviderError("generation_provider_unreachable", "Provider unavailable.")
        yield "Recovered answer."


def setup_client() -> tuple[TestClient, Session, User, Workspace]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    now = datetime.now(UTC)
    user = User(
        id=str(uuid4()),
        email="chat-owner@example.com",
        name="Owner",
        password_hash="hash",
        avatar_url="https://example.com/avatar.svg",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Chat workspace",
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add_all([user, workspace])
    session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.commit()

    app = FastAPI()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session, user, workspace


def test_thread_routes_persist_and_archive_threads() -> None:
    client, session, user, workspace = setup_client()
    headers = {"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user.id}
    try:
        created = client.post(
            f"/v1/workspaces/{workspace.id}/threads",
            headers=headers,
            json={"title": "Review"},
        )
        assert created.status_code == 201
        thread_id = created.json()["thread"]["id"]

        listed = client.get(f"/v1/workspaces/{workspace.id}/threads", headers=headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [thread_id]

        messages = client.get(
            f"/v1/workspaces/{workspace.id}/threads/{thread_id}/messages",
            headers=headers,
        )
        assert messages.status_code == 200
        assert messages.json()["messages"] == []

        deleted = client.delete(f"/v1/workspaces/{workspace.id}/threads/{thread_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(f"/v1/workspaces/{workspace.id}/threads", headers=headers).json()["items"] == []
    finally:
        session.close()


def test_thread_messages_returns_active_branch_in_parent_order() -> None:
    client, session, user, workspace = setup_client()
    headers = {"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user.id}
    now = datetime.now(UTC)
    thread = ChatThread(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Branching",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    first_user = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=None,
        role="user",
        content="First question",
        status="completed",
        created_at=now,
    )
    first_answer = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=first_user.id,
        role="assistant",
        content="First answer",
        status="completed",
        created_at=now,
    )
    active_user = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=first_answer.id,
        role="user",
        content="Active question",
        status="completed",
        created_at=now,
    )
    active_answer = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=active_user.id,
        role="assistant",
        content="Active answer",
        status="completed",
        created_at=now,
    )
    hidden_user = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=first_answer.id,
        role="user",
        content="Hidden question",
        status="completed",
        created_at=now,
    )
    hidden_answer = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        parent_message_id=hidden_user.id,
        role="assistant",
        content="Hidden answer",
        status="completed",
        created_at=now,
    )
    thread.active_message_id = active_answer.id
    session.add_all([thread, first_user, first_answer, active_user, active_answer, hidden_user, hidden_answer])
    session.commit()

    try:
        response = client.get(
            f"/v1/workspaces/{workspace.id}/threads/{thread.id}/messages",
            headers=headers,
        )

        assert response.status_code == 200
        messages = response.json()["messages"]
        assert [message["content"] for message in messages] == [
            "First question",
            "First answer",
            "Active question",
            "Active answer",
        ]
        assert messages[2]["parentMessageId"] == first_answer.id
        assert messages[3]["parentMessageId"] == active_user.id
    finally:
        session.close()


def test_chat_stream_continues_from_failed_assistant_parent_over_http(
    monkeypatch,
) -> None:
    client, session, user, workspace = setup_client()
    headers = {"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user.id}
    now = datetime.now(UTC)
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Router fixture",
        source_filename="router.pdf",
        object_key="router.pdf",
        mime_type="application/pdf",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="router-parser-v1",
        created_at=now,
    )
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Failure recovery",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add_all([asset, representation, thread])
    session.flush()
    page = PdfPage(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        page_number=1,
        extracted_text="router evidence",
        char_count=15,
        created_at=now,
    )
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    session.add_all([page, locator])
    session.flush()
    session.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=1))
    unit = ContentUnit(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_order=0,
        text_content="router evidence",
        token_count=2,
        char_start=0,
        char_end=15,
        index_version=1,
        created_at=now,
    )
    session.add(unit)
    session.flush()
    session.add(
        ContentUnitEmbedding(
            workspace_id=workspace.id,
            asset_id=asset.id,
            content_unit_id=unit.id,
            processing_generation=1,
            index_version=1,
            is_current=True,
            embedding_space="text",
            provider="router-test",
            model="router-embedding",
            dimensions=3,
            version="router-v1",
            embedding=[1.0, 0.0, 0.0],
            created_at=now,
        )
    )
    session.commit()
    generation = RouterGenerationProvider()
    monkeypatch.setattr(
        "ai_pdf_api.services.chat.get_embedding_provider",
        lambda: RouterEmbeddingProvider(),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.chat.get_generation_provider",
        lambda: generation,
    )

    try:
        first = client.post(
            f"/v1/workspaces/{workspace.id}/chat/stream",
            headers=headers,
            json={
                "threadId": thread.id,
                "question": "First question",
                "assetScope": {"mode": "selected", "assetIds": [asset.id]},
                "evidenceTargets": [],
            },
        )
        assert first.status_code == 200
        assert "event: error" in first.text
        failed_assistant = session.query(ChatMessage).filter_by(role="assistant").one()
        assert failed_assistant.status == "failed"
        assert session.get(ChatThread, thread.id).active_message_id == failed_assistant.id

        second = client.post(
            f"/v1/workspaces/{workspace.id}/chat/stream",
            headers=headers,
            json={
                "threadId": thread.id,
                "question": "Continue after the failure",
                "assetScope": {"mode": "selected", "assetIds": [asset.id]},
                "parentMessageId": failed_assistant.id,
                "evidenceTargets": [],
            },
        )

        assert second.status_code == 200
        assert "event: done" in second.text
        assert "Recovered answer." in second.text
        continued_user = session.query(ChatMessage).filter_by(
            role="user",
            content="Continue after the failure",
        ).one()
        assert continued_user.parent_message_id == failed_assistant.id
        completed_assistant = session.get(ChatThread, thread.id).active_message_id
        assert session.get(ChatMessage, completed_assistant).status == "completed"

        session.get(ChatMessage, completed_assistant).status = "streaming"
        session.commit()
        rejected = client.post(
            f"/v1/workspaces/{workspace.id}/chat/stream",
            headers=headers,
            json={
                "threadId": thread.id,
                "question": "Do not accept an incomplete parent",
                "assetScope": {"mode": "selected", "assetIds": [asset.id]},
                "parentMessageId": completed_assistant,
                "evidenceTargets": [],
            },
        )
        assert rejected.status_code == 422
        assert session.query(ChatMessage).filter_by(
            role="user",
            content="Do not accept an incomplete parent",
        ).one_or_none() is None
    finally:
        session.close()
