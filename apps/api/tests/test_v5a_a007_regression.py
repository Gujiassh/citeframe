"""V5-A A007 Research/Chat production-path regressions (no production code changes)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    ResearchExecutionAsset,
    ResearchToolCall,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.chat import router as chat_router
from ai_pdf_api.services import research_worker_evidence
from ai_pdf_api.services.embedding_index import (
    EMBEDDING_INDEX_MISMATCH_CODE,
    EMBEDDING_INDEX_MISMATCH_MESSAGE,
)
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_api.services.research.research_idempotency import ResearchError
from ai_pdf_api.services.research.research_worker import search_frozen_evidence
from ai_pdf_api.services.research.research_worker_policy import (
    is_transient_failure,
    normalize_failure_code,
)
from research_worker_test_support import assert_research_error, lease_default_step


class _ChatEmbeddingProvider:
    provider = "router-test"
    model = "router-embedding"
    dimensions = 3
    version = "router-v1"

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class _ChatGenerationProvider:
    provider = "router-test"
    model = "router-generation"

    def stream(self, _messages):
        yield "should-not-stream"


def _chat_client() -> tuple[TestClient, Session, User, Workspace]:
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
        email="a007-chat@example.com",
        name="A007",
        password_hash="hash",
        avatar_url="https://example.com/avatar.svg",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="A007 chat workspace",
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

    app.include_router(chat_router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session, user, workspace


def test_search_frozen_evidence_fail_closes_on_real_execution_fingerprint_drift(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production search_frozen_evidence path: drift before provider factory and tool reservation."""

    fixture = research_worker_db
    lease = lease_default_step(fixture)
    fixture.snapshot.provider_config_fingerprint = "0" * 64
    fixture.db.add(
        ResearchExecutionAsset(
            execution_snapshot_id=fixture.snapshot.id,
            workspace_id=fixture.run.workspace_id,
            asset_id=fixture.asset.id,
            asset_order=0,
            asset_kind_snapshot=fixture.asset.asset_kind,
            asset_title_snapshot=fixture.asset.title,
            processing_generation_snapshot=fixture.asset.current_processing_generation,
            index_version_snapshot=fixture.asset.current_index_version,
        )
    )
    fixture.db.commit()

    provider_calls = {"count": 0}

    def fail_if_called():
        provider_calls["count"] += 1
        raise AssertionError("get_embedding_provider must not run after fingerprint drift")

    monkeypatch.setattr(research_worker_evidence, "get_embedding_provider", fail_if_called)

    with pytest.raises(ResearchError) as drift_error:
        search_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="search-provider-drift",
            query="facts",
            asset_ids=(fixture.asset.id,),
            top_k=6,
            # Production path: no injected embedding_provider.
            now=fixture.now + timedelta(seconds=1),
        )

    assert_research_error(drift_error, "research_provider_config_drift", 409)
    assert provider_calls["count"] == 0
    assert fixture.db.scalar(select(ResearchToolCall)) is None


def test_search_frozen_evidence_embedding_index_mismatch_mapping_remains_non_retryable(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Research mapping: embedding_index_mismatch → ResearchError 409, non-retryable tool failure."""

    fixture = research_worker_db
    lease = lease_default_step(fixture)
    fixture.db.add(
        ResearchExecutionAsset(
            execution_snapshot_id=fixture.snapshot.id,
            workspace_id=fixture.run.workspace_id,
            asset_id=fixture.asset.id,
            asset_order=0,
            asset_kind_snapshot=fixture.asset.asset_kind,
            asset_title_snapshot=fixture.asset.title,
            processing_generation_snapshot=fixture.asset.current_processing_generation,
            index_version_snapshot=fixture.asset.current_index_version,
        )
    )
    fixture.db.commit()

    class FakeEmbeddingProvider:
        provider = fixture.snapshot.embedding_provider
        model = fixture.snapshot.embedding_model
        version = fixture.snapshot.embedding_version

        def embed_query(self, query: str) -> list[float]:
            assert query == "facts"
            return [0.25, 0.75]

    def raise_mismatch(*_args, **_kwargs):
        raise ModelProviderError(EMBEDDING_INDEX_MISMATCH_CODE, EMBEDDING_INDEX_MISMATCH_MESSAGE)

    monkeypatch.setattr(research_worker_evidence, "retrieve_query_content", raise_mismatch)

    with pytest.raises(ResearchError) as mismatch_error:
        search_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="search-embedding-index-mismatch-a007",
            query="facts",
            asset_ids=(fixture.asset.id,),
            top_k=6,
            embedding_provider=FakeEmbeddingProvider(),
            now=fixture.now + timedelta(seconds=1),
        )

    assert_research_error(mismatch_error, EMBEDDING_INDEX_MISMATCH_CODE, 409)
    assert mismatch_error.value.message == EMBEDDING_INDEX_MISMATCH_MESSAGE
    call = fixture.db.scalar(select(ResearchToolCall))
    assert call is not None
    assert call.status == "failed"
    assert call.error_code == EMBEDDING_INDEX_MISMATCH_CODE
    reason = normalize_failure_code(EMBEDDING_INDEX_MISMATCH_CODE)
    assert reason == EMBEDDING_INDEX_MISMATCH_CODE
    assert is_transient_failure(reason) is False


def test_chat_stream_http_keeps_embedding_index_mismatch_detail_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat production HTTP: status 502 + {"detail": message}; no error envelope or half-save."""

    client, session, user, workspace = _chat_client()
    headers = {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": user.id,
    }
    now = datetime.now(UTC)
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="A007 chat fixture",
        source_filename="a007.pdf",
        object_key="a007.pdf",
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
        title="A007 mismatch",
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
        extracted_text="stale index",
        char_count=11,
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
        text_content="stale index",
        token_count=2,
        char_start=0,
        char_end=11,
        index_version=1,
        created_at=now,
    )
    session.add(unit)
    session.flush()
    # Only non-matching current vectors in scope → production embedding_index_mismatch.
    session.add(
        ContentUnitEmbedding(
            workspace_id=workspace.id,
            asset_id=asset.id,
            content_unit_id=unit.id,
            processing_generation=1,
            index_version=1,
            is_current=True,
            embedding_space="text",
            provider="stale-provider",
            model="stale-model",
            dimensions=3,
            version="stale-v1",
            embedding=[0.0, 1.0, 0.0],
            created_at=now,
        )
    )
    session.commit()

    monkeypatch.setattr(
        "ai_pdf_api.services.chat.get_embedding_provider",
        lambda: _ChatEmbeddingProvider(),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.chat.get_generation_provider",
        lambda: _ChatGenerationProvider(),
    )

    try:
        response = client.post(
            f"/v1/workspaces/{workspace.id}/chat/stream",
            headers=headers,
            json={
                "threadId": thread.id,
                "question": "Does this hit the old chat contract?",
                "assetScope": {"mode": "selected", "assetIds": [asset.id]},
                "evidenceTargets": [],
            },
        )
        assert response.status_code == 502
        body = response.json()
        assert body == {"detail": EMBEDDING_INDEX_MISMATCH_MESSAGE}
        assert "code" not in body
        assert "error_code" not in body
        assert "error" not in body
        assert session.query(ChatMessage).count() == 0
        assert session.get(ChatThread, thread.id).active_message_id is None
    finally:
        session.close()
