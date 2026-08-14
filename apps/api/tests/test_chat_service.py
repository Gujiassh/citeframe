from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ai_pdf_api.core.metrics import RETRIEVAL_REQUESTS
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    AssetRepresentation,
    ChatThread,
    Asset,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    MessageRetrievalScope,
    MessageRetrievalScopeAsset,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.schemas.chat import AllReadyAssetScope, SelectedAssetScope
from ai_pdf_api.modalities.evidence import serialize_evidence_locator
from ai_pdf_api.services.chat import (
    ChatError,
    active_message_path,
    complete_chat,
    fail_chat,
    prepare_chat,
)
from ai_pdf_api.services.retrieval import (
    RetrievedChunk,
    _lexical_terms,
    _rrf_merge,
    retrieve_chunks,
    retrieve_lexical_chunks,
    retrieve_query_chunks,
)


class FakeEmbeddingProvider:
    provider = "fake"
    model = "fake-embedding"
    dimensions = 3
    version = "fake-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeGenerationProvider:
    provider = "fake"
    model = "fake-generation"

    def __init__(self) -> None:
        self.messages: list = []

    def generate(self, messages: list) -> str:
        self.messages = messages

        def has_context(message: dict) -> bool:
            content = message.get("content")
            if isinstance(content, str):
                return "Asset evidence context" in content
            if isinstance(content, list):
                return any(
                    isinstance(part, dict)
                    and part.get("type") == "input_text"
                    and "Asset evidence context" in str(part.get("text", ""))
                    for part in content
                )
            return False

        assert any(has_context(message) for message in messages)
        return "The answer is supported by [1]."


@pytest.fixture(autouse=True)
def _block_storage_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not hit MinIO; retrieval-auto crop soft-skips on loader errors."""

    def _unavailable(_object_key: str) -> bytes:
        raise RuntimeError("storage unavailable in unit test")

    monkeypatch.setattr("ai_pdf_api.services.chat.download_bytes", _unavailable)


def build_session() -> tuple[Session, str, ChatThread]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    now = datetime.now(UTC)
    user = User(
        id=str(uuid4()),
        email="owner@example.com",
        name="Owner",
        password_hash="hash",
        avatar_url="https://example.com/avatar.svg",
    )
    workspace = Workspace(id=str(uuid4()), name="Research", created_by_user_id=user.id, created_at=now, updated_at=now)
    session.add_all([user, workspace])
    session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    asset = Asset(
        asset_kind="pdf",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Source PDF",
        source_filename="source.pdf",
        object_key="source.pdf",
        mime_type="application/pdf",
        byte_size=10,
        status="ready",
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(asset)
    session.flush()
    representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="fixture-parser-v1",
        created_at=now,
    )
    session.add(representation)
    session.flush()
    page = PdfPage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        page_number=4,
        extracted_text="retrieval evidence",
        char_count=19,
        created_at=now,
    )
    session.add(page)
    session.flush()
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    session.add(locator)
    session.flush()
    session.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=4))
    unit = ContentUnit(
            id=str(uuid4()),
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=representation.id,
            source_locator_id=locator.id,
            unit_kind="pdf_text_chunk",
            unit_order=0,
            text_content="retrieval evidence",
            token_count=2,
            char_start=0,
            char_end=19,
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
            provider="fake",
            model="fake-embedding",
            dimensions=3,
            version="fake-v1",
            embedding=[1.0, 0.0, 0.0],
            created_at=now,
        )
    )
    thread = ChatThread(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=None,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(thread)
    session.commit()
    return session, workspace.id, thread


def add_pdf_unit(
    session: Session,
    *,
    asset: Asset,
    page_number: int,
    text: str,
    unit_order: int,
    index_version: int,
    unit_id: str | None = None,
) -> tuple[ContentUnit, PdfLocatorDetail, PdfPage]:
    now = datetime.now(UTC)
    representation = session.query(AssetRepresentation).filter_by(asset_id=asset.id).one()
    page = session.query(PdfPage).filter_by(asset_id=asset.id, page_number=page_number).one_or_none()
    if page is None:
        page = PdfPage(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_id=representation.id,
            page_number=page_number,
            extracted_text=text,
            char_count=len(text),
            created_at=now,
        )
        session.add(page)
        session.flush()
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    session.add(locator)
    session.flush()
    detail = PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=page_number)
    unit = ContentUnit(
        id=unit_id or str(uuid4()),
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_order=unit_order,
        text_content=text,
        token_count=1,
        char_start=0,
        char_end=len(text),
        index_version=index_version,
        created_at=now,
    )
    session.add_all([detail, unit])
    session.flush()
    return unit, detail, page


def test_retrieval_is_workspace_and_provider_scoped() -> None:
    session, workspace_id, _thread = build_session()
    provider = FakeEmbeddingProvider()

    results = retrieve_chunks(session, workspace_id, [1.0, 0.0, 0.0], embedding_provider=provider)

    assert len(results) == 1
    assert session.get(PdfLocatorDetail, results[0].locator.id).page_number == 4
    assert results[0].asset.title == "Source PDF"


def test_retrieval_rejects_cross_workspace_asset_links() -> None:
    session, workspace_id, _thread = build_session()
    asset = session.query(Asset).one()
    asset.workspace_id = str(uuid4())
    session.flush()

    results = retrieve_chunks(
        session,
        workspace_id,
        [1.0, 0.0, 0.0],
        embedding_provider=FakeEmbeddingProvider(),
    )

    assert results == []


def test_lexical_and_hybrid_retrieval_preserve_workspace_scope() -> None:
    session, workspace_id, _thread = build_session()
    provider = FakeEmbeddingProvider()

    lexical = retrieve_lexical_chunks(session, workspace_id, "retrieval evidence")
    hybrid = retrieve_query_chunks(
        session,
        workspace_id,
        "retrieval evidence",
        [1.0, 0.0, 0.0],
        embedding_provider=provider,
        limit=3,
        strategy="hybrid",
    )

    assert [session.get(PdfLocatorDetail, item.locator.id).page_number for item in lexical] == [4]
    assert [session.get(PdfLocatorDetail, item.locator.id).page_number for item in hybrid] == [4]


def test_dense_strategy_does_not_execute_lexical_query(monkeypatch: pytest.MonkeyPatch) -> None:
    import ai_pdf_api.services.retrieval as retrieval_service

    session, workspace_id, _thread = build_session()

    def fail_lexical(*_args, **_kwargs):
        raise AssertionError("dense retrieval must not execute lexical retrieval")

    monkeypatch.setattr(retrieval_service, "retrieve_lexical_chunks", fail_lexical)

    results = retrieve_query_chunks(
        session,
        workspace_id,
        "retrieval evidence",
        [1.0, 0.0, 0.0],
        embedding_provider=FakeEmbeddingProvider(),
        strategy="dense",
    )

    assert [session.get(PdfLocatorDetail, item.locator.id).page_number for item in results] == [4]


def test_lexical_retrieval_ignores_stale_index_versions() -> None:
    session, workspace_id, _thread = build_session()
    asset = session.query(Asset).one()
    add_pdf_unit(
        session,
        asset=asset,
        page_number=4,
        text="stale-only-keyword",
        unit_order=1,
        index_version=0,
    )
    session.commit()

    assert retrieve_lexical_chunks(session, workspace_id, "stale-only-keyword") == []


def test_lexical_retrieval_expands_candidates_past_stale_chunks() -> None:
    session, workspace_id, _thread = build_session()
    asset = session.query(Asset).one()
    current_chunk = session.query(ContentUnit).one()
    current_chunk.text_content = "目标答案"
    for index in range(3):
        add_pdf_unit(
            session,
            asset=asset,
            page_number=4,
            text="目标答案",
            unit_order=index + 1,
            index_version=0,
            unit_id=f"00000000-0000-0000-0000-00000000000{index}",
        )
    session.commit()

    results = retrieve_lexical_chunks(session, workspace_id, "目标答案", limit=1)

    assert [item.content_unit.id for item in results] == [current_chunk.id]


def test_rrf_merges_by_asset_page_and_keeps_stable_page_order() -> None:
    session, _workspace_id, _thread = build_session()
    asset = session.query(Asset).one()
    chunk_one = session.query(ContentUnit).one()
    detail_one = session.query(PdfLocatorDetail).one()
    locator_one = session.get(EvidenceLocator, detail_one.locator_id)
    duplicate_chunk, duplicate_detail, _page = add_pdf_unit(
        session, asset=asset, page_number=4, text="duplicate page chunk", unit_order=1, index_version=1
    )
    second_page_chunk, second_detail, page_two = add_pdf_unit(
        session, asset=asset, page_number=5, text="second page", unit_order=0, index_version=1
    )
    duplicate_locator = session.get(EvidenceLocator, duplicate_detail.locator_id)
    second_locator = session.get(EvidenceLocator, second_detail.locator_id)
    dense = [
        RetrievedChunk(chunk_one, asset, locator_one, "text", 0.1, (asset.id, "pdf_page:4")),
        RetrievedChunk(duplicate_chunk, asset, duplicate_locator, "text", 0.2, (asset.id, "pdf_page:4")),
        RetrievedChunk(second_page_chunk, asset, second_locator, "text", 0.3, (asset.id, "pdf_page:5")),
    ]
    lexical = [
        RetrievedChunk(second_page_chunk, asset, second_locator, "text", 0.1, (asset.id, "pdf_page:5")),
        RetrievedChunk(chunk_one, asset, locator_one, "text", 0.2, (asset.id, "pdf_page:4")),
    ]

    merged = _rrf_merge(dense, lexical, limit=3, constant=60)

    assert [session.get(PdfLocatorDetail, item.locator.id).page_number for item in merged] == [4, 5]


def test_rrf_keeps_distinct_regions_on_the_same_page_independent() -> None:
    session, _workspace_id, _thread = build_session()
    asset = session.query(Asset).one()
    first_unit, first_detail, page = add_pdf_unit(
        session,
        asset=asset,
        page_number=6,
        text="first region",
        unit_order=1,
        index_version=1,
    )
    second_unit, second_detail, _page = add_pdf_unit(
        session,
        asset=asset,
        page_number=6,
        text="second region",
        unit_order=2,
        index_version=1,
    )
    first_locator = session.get(EvidenceLocator, first_detail.locator_id)
    second_locator = session.get(EvidenceLocator, second_detail.locator_id)
    assert first_locator is not None and second_locator is not None
    for index, (locator, detail) in enumerate(
        ((first_locator, first_detail), (second_locator, second_detail))
    ):
        locator.locator_kind = "pdf_region"
        detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
        detail.crop_x0_points = 0.0
        detail.crop_y0_points = 0.0
        detail.crop_x1_points = 612.0
        detail.crop_y1_points = 792.0
        detail.rotation_degrees = 0
        detail.display_width_points = 612.0
        detail.display_height_points = 792.0
        session.add(
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=0,
                x=0.1 + index * 0.4,
                y=0.2,
                width=0.2,
                height=0.1,
            )
        )
    session.flush()

    dense = [RetrievedChunk(first_unit, asset, first_locator, "text", 0.1, (asset.id, first_locator.id))]
    lexical = [RetrievedChunk(second_unit, asset, second_locator, "text", 0.1, (asset.id, second_locator.id))]

    merged = _rrf_merge(dense, lexical, limit=3, constant=60)

    assert [item.locator.id for item in merged] == sorted(
        [first_locator.id, second_locator.id]
    )


def test_mixed_language_lexical_terms_use_exact_latin_terms() -> None:
    assert _lexical_terms("Shape Up 为什么不使用 backlog？") == ["shape", "up", "backlog"]


def test_retrieval_logs_flat_strategy_counts_and_stage_timings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    session, workspace_id, _thread = build_session()

    before = RETRIEVAL_REQUESTS.labels(strategy="hybrid", outcome="success")._value.get()
    retrieval_logger = logging.getLogger("ai_pdf_api.services.retrieval")
    previous_disabled = retrieval_logger.disabled
    retrieval_logger.disabled = False
    retrieval_logger.addHandler(caplog.handler)
    try:
        retrieval_logger.setLevel(logging.INFO)
        retrieve_query_chunks(
            session,
            workspace_id,
            "retrieval evidence",
            [1.0, 0.0, 0.0],
            embedding_provider=FakeEmbeddingProvider(),
            strategy="hybrid",
        )
    finally:
        retrieval_logger.removeHandler(caplog.handler)
        retrieval_logger.disabled = previous_disabled

    message = caplog.messages[-1]
    assert "strategy=hybrid" in message
    assert "dense_count=1 lexical_count=1 result_count=1" in message
    assert "total_ms=" in message
    assert RETRIEVAL_REQUESTS.labels(strategy="hybrid", outcome="success")._value.get() == before + 1


def test_retrieval_records_error_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    session, workspace_id, _thread = build_session()
    errors = RETRIEVAL_REQUESTS.labels(strategy="hybrid", outcome="error")
    before = errors._value.get()

    def fail_dense(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("ai_pdf_api.services.retrieval.retrieve_content", fail_dense)

    with pytest.raises(RuntimeError, match="database unavailable"):
        retrieve_query_chunks(
            session,
            workspace_id,
            "retrieval evidence",
            [1.0, 0.0, 0.0],
            embedding_provider=FakeEmbeddingProvider(),
            strategy="hybrid",
        )

    assert errors._value.get() == before + 1


def test_complete_chat_persists_messages_and_citation_snapshot() -> None:
    session, workspace_id, thread = build_session()

    result = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="What is the evidence?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )

    assert result.assistant_message.content == "The answer is supported by [1]."
    assert len(result.citations) == 1
    assert result.citations[0].asset_kind_snapshot == "pdf"
    assert result.citations[0].asset_title_snapshot == "Source PDF"
    scope = session.get(MessageRetrievalScope, result.user_message.id)
    assert scope is not None and scope.scope_mode == "all_ready"
    assert session.query(MessageRetrievalScopeAsset).filter_by(message_id=result.user_message.id).count() == 1
    assert thread.title == "What is the evidence?"
    assert session.query(ContentUnit).count() == 1


def test_complete_chat_clones_pdf_region_evidence_without_geometry_drift() -> None:
    session, workspace_id, thread = build_session()
    unit = session.query(ContentUnit).one()
    locator = session.get(EvidenceLocator, unit.source_locator_id)
    detail = session.get(PdfLocatorDetail, unit.source_locator_id)
    representation = session.get(AssetRepresentation, unit.representation_id)
    assert locator is not None and detail is not None and representation is not None
    locator.locator_kind = "pdf_region"
    unit.unit_kind = "pdf_ocr_region"
    representation.representation_kind = "pdf_ocr"
    detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 612.0
    detail.crop_y1_points = 792.0
    detail.rotation_degrees = 0
    detail.display_width_points = 612.0
    detail.display_height_points = 792.0
    session.add_all(
        [
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=0,
                x=0.1,
                y=0.2,
                width=0.3,
                height=0.1,
            ),
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=1,
                x=0.1,
                y=0.4,
                width=0.5,
                height=0.1,
            ),
        ]
    )
    session.commit()

    result = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="What is the regional evidence?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )

    serialized = serialize_evidence_locator(
        session,
        result.citations[0].evidence_locator_id,
    ).model_dump()
    assert serialized == {
        "kind": "pdf_region",
        "version": 1,
        "pageNumber": 4,
        "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
        "pageGeometry": {
            "cropBoxPoints": [0.0, 0.0, 612.0, 792.0],
            "rotationDegrees": 0,
            "displayWidthPoints": 612.0,
            "displayHeightPoints": 792.0,
        },
        "regions": [
            {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
            {"x": 0.1, "y": 0.4, "width": 0.5, "height": 0.1},
        ],
    }


def test_selected_asset_scope_is_rejected_before_provider_calls() -> None:
    session, workspace_id, thread = build_session()

    class ProviderMustNotRun(FakeEmbeddingProvider):
        def embed_query(self, _text: str) -> list[float]:
            raise AssertionError("provider must not run before scope validation")

    with pytest.raises(ChatError, match="selected assets are not available"):
        complete_chat(
            session,
            workspace_id=workspace_id,
            user_id="owner",
            thread=thread,
            question="What is the evidence?",
            asset_scope=SelectedAssetScope(mode="selected", assetIds=[str(uuid4())]),
            embedding_provider=ProviderMustNotRun(),
            generation_provider=FakeGenerationProvider(),
        )


def test_chat_messages_form_ordered_branches_and_active_path() -> None:
    session, workspace_id, thread = build_session()

    first = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="First question",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )
    second = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="Follow-up question",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        parent_message_id=first.assistant_message.id,
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )

    assert first.user_message.parent_message_id is None
    assert first.assistant_message.parent_message_id == first.user_message.id
    assert second.user_message.parent_message_id == first.assistant_message.id
    assert thread.active_message_id == second.assistant_message.id
    assert [message.id for message in active_message_path(session, thread)] == [
        first.user_message.id,
        first.assistant_message.id,
        second.user_message.id,
        second.assistant_message.id,
    ]

    edited = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="Edited first question",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        parent_message_id=None,
        use_thread_active_parent=False,
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )

    assert edited.user_message.parent_message_id is None
    assert [message.id for message in active_message_path(session, thread)] == [
        edited.user_message.id,
        edited.assistant_message.id,
    ]


def test_failed_first_chat_becomes_a_replayable_active_branch() -> None:
    session, _workspace_id, thread = build_session()
    unit = session.query(ContentUnit).one()
    locator = session.get(EvidenceLocator, unit.source_locator_id)
    detail = session.get(PdfLocatorDetail, unit.source_locator_id)
    representation = session.get(AssetRepresentation, unit.representation_id)
    assert locator is not None and detail is not None and representation is not None
    locator.locator_kind = "pdf_region"
    unit.unit_kind = "pdf_ocr_region"
    representation.representation_kind = "pdf_ocr"
    detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 612.0
    detail.crop_y1_points = 792.0
    detail.rotation_degrees = 0
    detail.display_width_points = 612.0
    detail.display_height_points = 792.0
    session.add_all([
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.1,
        ),
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=1,
            x=0.1,
            y=0.4,
            width=0.5,
            height=0.1,
        ),
    ])
    session.commit()
    baseline = {
        "locators": session.query(EvidenceLocator).count(),
        "details": session.query(PdfLocatorDetail).count(),
        "regions": session.query(SpatialLocatorRegion).count(),
    }
    prepared = prepare_chat(
        session,
        workspace_id=thread.workspace_id,
        user_id="owner",
        thread=thread,
        question="Question whose generation fails",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )
    assert session.query(EvidenceLocator).count() == baseline["locators"] + 1
    assert session.query(PdfLocatorDetail).count() == baseline["details"] + 1
    assert session.query(SpatialLocatorRegion).count() == baseline["regions"] + 2
    prepared_user_id = prepared.user_message.id
    prepared_assistant_id = prepared.assistant_message.id
    session.rollback()
    connection = session.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    session.commit()

    fail_chat(session, prepared, "generation_provider_unreachable", "Generation provider is unreachable.")

    session.refresh(thread)
    path = active_message_path(session, thread)
    assert [message.id for message in path] == [
        prepared_user_id,
        prepared_assistant_id,
    ]
    assert path[-1].status == "failed"
    assert path[-1].content == "Generation provider is unreachable."
    assert thread.active_message_id == prepared_assistant_id
    assert session.query(EvidenceLocator).count() == baseline["locators"]
    assert session.query(PdfLocatorDetail).count() == baseline["details"]
    assert session.query(SpatialLocatorRegion).count() == baseline["regions"]
    assert session.get(ContentUnit, unit.id).source_locator_id == locator.id


def test_chat_can_continue_from_a_failed_assistant_leaf() -> None:
    session, workspace_id, thread = build_session()
    prepared = prepare_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="Question whose generation fails",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )
    fail_chat(session, prepared, "generation_provider_unreachable", "Generation provider is unreachable.")
    failed_assistant_id = prepared.assistant_message.id

    generation = FakeGenerationProvider()
    completed = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="Continue after the failed answer",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=generation,
    )

    assert completed.user_message.parent_message_id == failed_assistant_id
    assert [message["content"] for message in generation.messages if message["role"] == "user"][0] == (
        "Question whose generation fails"
    )
    assert all("Generation provider is unreachable." not in message["content"] for message in generation.messages)
    assert [message.id for message in active_message_path(session, thread)] == [
        prepared.user_message.id,
        failed_assistant_id,
        completed.user_message.id,
        completed.assistant_message.id,
    ]


def test_chat_uses_persisted_workspace_prompt_and_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    import ai_pdf_api.services.chat as chat_service

    session, workspace_id, thread = build_session()
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    workspace.system_prompt = "Use the workspace review policy."
    workspace.retrieval_top_k = 3
    session.commit()

    captured: dict[str, int] = {}
    original_retrieve = chat_service.retrieve_query_content

    def capture_limit(*args, **kwargs):
        captured["limit"] = kwargs["limit"]
        return original_retrieve(*args, **kwargs)

    monkeypatch.setattr(chat_service, "retrieve_query_content", capture_limit)
    generation = FakeGenerationProvider()
    complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="What is the evidence?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=generation,
    )

    assert captured["limit"] == 3
    assert generation.messages[0] == {
        "role": "system",
        "content": "Use the workspace review policy.",
    }



def test_retrieval_pdf_region_auto_crops_into_generation() -> None:
    """P1: retrieved pdf_region hits attach PNG crops without explicit evidenceTargets."""
    session, workspace_id, thread = build_session()
    unit = session.query(ContentUnit).one()
    locator = session.get(EvidenceLocator, unit.source_locator_id)
    detail = session.get(PdfLocatorDetail, unit.source_locator_id)
    representation = session.get(AssetRepresentation, unit.representation_id)
    asset = session.get(Asset, unit.asset_id)
    assert locator is not None and detail is not None and representation is not None and asset is not None
    locator.locator_kind = "pdf_region"
    unit.unit_kind = "pdf_ocr_region"
    representation.representation_kind = "pdf_ocr"
    detail.page_number = 1
    detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 300.0
    detail.crop_y1_points = 400.0
    detail.rotation_degrees = 0
    detail.display_width_points = 300.0
    detail.display_height_points = 400.0
    session.add(
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=0.1,
            y=0.2,
            width=0.5,
            height=0.3,
        )
    )
    session.commit()

    import fitz

    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 80), "Hello PDF crop fixture")
    page.draw_rect(fitz.Rect(40, 100, 200, 220), color=(0, 0, 1), width=2)
    pdf_bytes = document.tobytes()
    document.close()

    generation = FakeGenerationProvider()
    result = complete_chat(
        session,
        workspace_id=workspace_id,
        user_id="owner",
        thread=thread,
        question="What is in the figure region?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=generation,
        image_bytes_loader=lambda _key: pdf_bytes,
    )

    assert result.assistant_message.status == "completed"
    user_input = generation.messages[-1]
    assert user_input["role"] == "user"
    content = user_input["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "input_text"
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_collect_retrieval_pdf_crop_soft_skips_loader_errors() -> None:
    from ai_pdf_api.modalities.pdf_evidence_targets import collect_retrieval_pdf_crop_payloads
    from ai_pdf_api.services.retrieval import RetrievedContent

    session, _workspace_id, _thread = build_session()
    unit = session.query(ContentUnit).one()
    locator = session.get(EvidenceLocator, unit.source_locator_id)
    detail = session.get(PdfLocatorDetail, unit.source_locator_id)
    asset = session.get(Asset, unit.asset_id)
    assert locator is not None and detail is not None and asset is not None
    locator.locator_kind = "pdf_region"
    detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 300.0
    detail.crop_y1_points = 400.0
    detail.rotation_degrees = 0
    detail.display_width_points = 300.0
    detail.display_height_points = 400.0
    session.add(
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=0.1,
            y=0.1,
            width=0.2,
            height=0.2,
        )
    )
    session.commit()
    session.refresh(locator)
    session.refresh(asset)

    item = RetrievedContent(
        content_unit=unit,
        asset=asset,
        locator=locator,
        channel="text",
        distance=0.1,
        location_key=("pdf_region", locator.id),
    )
    crops = collect_retrieval_pdf_crop_payloads(
        session,
        [item],
        image_bytes_loader=lambda _key: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert crops == ()

