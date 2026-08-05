from datetime import UTC, datetime, timedelta

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.evidence import (
    clone_evidence_locator,
    serialize_evidence_locator,
)
from ai_pdf_api.modalities.pdf_ingestion import (
    PageRegionResult,
)
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
    MessageCitation,
    Note,
    NoteSource,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
)
from ai_pdf_api.services.ingestion import (
    INGESTION_LEASE_TIMEOUT,
    claim_next_ingestion_job,
    process_embedding_job,
    process_ingestion_job,
)
from asset_router_test_support import (
    create_asset,
    create_pdf_content_unit,
    create_user,
    create_workspace_with_membership,
    parsed_page,
    static_pdf_adapters,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_successful_reprocessing_preserves_historical_citation_and_note_evidence(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(
        asset_db_session, email="history-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="ready"
    )
    old_unit = create_pdf_content_unit(
        asset_db_session,
        asset=asset,
        page_number=4,
        text="historical region evidence",
    )
    source_locator = asset_db_session.get(EvidenceLocator, old_unit.source_locator_id)
    source_detail = asset_db_session.get(PdfLocatorDetail, old_unit.source_locator_id)
    assert source_locator is not None and source_detail is not None
    source_locator.locator_kind = "pdf_region"
    source_detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    source_detail.crop_x0_points = 0.0
    source_detail.crop_y0_points = 0.0
    source_detail.crop_x1_points = 612.0
    source_detail.crop_y1_points = 792.0
    source_detail.rotation_degrees = 0
    source_detail.display_width_points = 612.0
    source_detail.display_height_points = 792.0
    asset_db_session.add(
        SpatialLocatorRegion(
            locator_id=source_locator.id,
            region_order=0,
            x=0.2,
            y=0.3,
            width=0.4,
            height=0.1,
        )
    )
    asset_db_session.flush()
    now = datetime.now(UTC)
    citation_locator = clone_evidence_locator(
        asset_db_session, source_locator.id, created_at=now
    )
    note_locator = clone_evidence_locator(
        asset_db_session, citation_locator.id, created_at=now
    )
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        title="History",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    asset_db_session.add(thread)
    asset_db_session.flush()
    message = ChatMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        role="assistant",
        content="Historical answer.",
        status="completed",
        created_at=now,
    )
    note = Note(
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        updated_by_user_id=owner.id,
        title="History note",
        body_md="Historical note.",
        created_at=now,
        updated_at=now,
    )
    asset_db_session.add_all([message, note])
    asset_db_session.flush()
    old_representation = asset_db_session.get(
        AssetRepresentation, source_locator.representation_id_snapshot
    )
    assert old_representation is not None
    citation = MessageCitation(
        workspace_id=workspace.id,
        message_id=message.id,
        citation_index=0,
        evidence_locator_id=citation_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="pdf",
        asset_title_snapshot="Historical title",
        excerpt_snapshot="Historical excerpt.",
        processing_generation_snapshot=1,
        representation_id_snapshot=old_representation.id,
        parser_version_snapshot=old_representation.generator_version,
        index_version_snapshot=1,
        created_at=now,
    )
    asset_db_session.add(citation)
    asset_db_session.flush()
    note_source = NoteSource(
        workspace_id=workspace.id,
        note_id=note.id,
        source_order=0,
        message_citation_id=citation.id,
        evidence_locator_id=note_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="pdf",
        asset_title_snapshot="Historical title",
        excerpt_snapshot="Historical excerpt.",
        processing_generation_snapshot=1,
        representation_id_snapshot=old_representation.id,
        parser_version_snapshot=old_representation.generator_version,
        index_version_snapshot=1,
        created_at=now,
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "retry"},
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    asset_db_session.add_all([note_source, job])
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    before_citation_locator = serialize_evidence_locator(
        asset_db_session,
        citation.evidence_locator_id,
    ).model_dump()
    before_note_locator = serialize_evidence_locator(
        asset_db_session,
        note_source.evidence_locator_id,
    ).model_dump()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([parsed_page(1, "current evidence")]),
    )

    asset_db_session.expire_all()
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_citation = asset_db_session.get(MessageCitation, citation.id)
    refreshed_note_source = asset_db_session.get(NoteSource, note_source.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == 2
    assert refreshed_asset.status == "chunked"
    assert asset_db_session.scalars(
        select(ContentUnit.text_content).where(ContentUnit.asset_id == asset.id)
    ).all() == ["current evidence"]
    assert refreshed_citation is not None and refreshed_note_source is not None
    assert (
        serialize_evidence_locator(
            asset_db_session,
            refreshed_citation.evidence_locator_id,
        ).model_dump()
        == before_citation_locator
    )
    assert (
        serialize_evidence_locator(
            asset_db_session,
            refreshed_note_source.evidence_locator_id,
        ).model_dump()
        == before_note_locator
    )
    assert (
        refreshed_citation.asset_title_snapshot,
        refreshed_citation.excerpt_snapshot,
        refreshed_citation.processing_generation_snapshot,
        refreshed_citation.representation_id_snapshot,
        refreshed_citation.index_version_snapshot,
    ) == ("Historical title", "Historical excerpt.", 1, old_representation.id, 1)
    assert (
        refreshed_note_source.asset_title_snapshot,
        refreshed_note_source.excerpt_snapshot,
        refreshed_note_source.processing_generation_snapshot,
        refreshed_note_source.representation_id_snapshot,
        refreshed_note_source.index_version_snapshot,
    ) == ("Historical title", "Historical excerpt.", 1, old_representation.id, 1)


def test_ingestion_worker_rejects_embedding_config_drift(
    asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="uploaded"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "embeddingProvider": "ollama",
            "embeddingModel": "qwen3-embedding:0.6b",
            "embeddingDimensions": 1024,
            "embeddingVersion": "embedding-v1",
        },
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    class DifferentEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda object_key: b"unreachable",
    )
    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
        embedding_provider=DifferentEmbeddingProvider(),
    )

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "failed"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "embedding_configuration_mismatch"


def test_embedding_failure_does_not_mark_partial_index_ready(
    asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="ready"
    )
    now = datetime.now(UTC)
    chunks = [
        create_pdf_content_unit(
            asset_db_session,
            asset=asset,
            page_number=index,
            text=f"chunk {index}",
        )
        for index in (1, 2)
    ]
    original_embedding = ContentUnitEmbedding(
        workspace_id=workspace.id,
        asset_id=asset.id,
        content_unit_id=chunks[0].id,
        processing_generation=asset.current_processing_generation,
        index_version=chunks[0].index_version,
        is_current=True,
        embedding_space="text",
        provider="fake",
        model="fake-embedding",
        dimensions=3,
        version="fake-v1",
        embedding=[0.0, 1.0, 0.0],
        created_at=now,
    )
    asset_db_session.add(original_embedding)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="embed_chunks",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "embeddingProvider": "fake",
            "embeddingModel": "fake-embedding",
            "embeddingDimensions": 3,
            "embeddingVersion": "fake-v1",
        },
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    class FailingEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def __init__(self) -> None:
            self.calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 1:
                return [[1.0, 0.0, 0.0] for _ in texts]
            raise RuntimeError("provider stopped")

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.settings.embedding_batch_size", 1
    )
    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_embedding_job(asset_db_session, claimed_job_id, FailingEmbeddingProvider())

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    persisted_embeddings = asset_db_session.scalars(
        select(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id)
    ).all()
    assert [embedding.id for embedding in persisted_embeddings] == [
        original_embedding.id
    ]
    assert persisted_embeddings[0].is_current is True
    assert persisted_embeddings[0].embedding == [0.0, 1.0, 0.0]


def test_reindex_queues_embed_job_with_embedding_config_snapshot(
    asset_client: TestClient, asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="ready"
    )
    create_pdf_content_unit(
        asset_db_session, asset=asset, page_number=1, text="reindex text"
    )
    asset_db_session.commit()

    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_provider", "fake")
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.settings.embedding_model", "fake-embedding"
    )
    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_dimensions", 3)
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.settings.embedding_version", "fake-v1"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/reindex",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["jobType"] == "embed_chunks"
    job = asset_db_session.get(IngestionJob, payload["job"]["id"])
    assert job is not None
    assert job.config_snapshot is not None
    assert job.config_snapshot["source"] == "reindex"
    assert job.config_snapshot["embeddingProvider"] == "fake"
    assert job.config_snapshot["embeddingModel"] == "fake-embedding"
    assert job.config_snapshot["embeddingDimensions"] == 3
    assert job.config_snapshot["embeddingVersion"] == "fake-v1"
    assert job.config_snapshot["chunkSize"] == 1200
    assert isinstance(job.config_snapshot["embeddingProfileFingerprint"], str)
    assert len(job.config_snapshot["embeddingProfileFingerprint"]) == 64


def test_ingestion_worker_uses_ocr_for_image_only_pdf(
    asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="uploaded"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"image-pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(
            [
                parsed_page(
                    1,
                    "扫描件第一页",
                    source_kind="ocr",
                    regions=(
                        PageRegionResult(
                            text="扫描件第一页",
                            unit_kind="pdf_ocr_region",
                            x=0.1,
                            y=0.2,
                            width=0.7,
                            height=0.1,
                            char_start=0,
                            char_end=len("扫描件第一页"),
                        ),
                    ),
                    ocr_blocks=[
                        {
                            "text": "扫描件第一页",
                            "x": 0.1,
                            "y": 0.2,
                            "width": 0.7,
                            "height": 0.1,
                        }
                    ],
                ),
                parsed_page(2, "扫描件第二页", source_kind="ocr"),
            ]
        ),
    )

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    pages = asset_db_session.scalars(
        select(PdfPage).where(PdfPage.asset_id == asset.id)
    ).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert [page.extracted_text for page in pages] == ["扫描件第一页", "扫描件第二页"]
    assert pages[0].legacy_ocr_blocks == [
        {"text": "扫描件第一页", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
    ]
    assert pages[1].legacy_ocr_blocks == []
    units = asset_db_session.scalars(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    ).all()
    units_by_page = {
        asset_db_session.get(PdfLocatorDetail, unit.source_locator_id).page_number: unit
        for unit in units
    }
    assert [units_by_page[page].text_content for page in (1, 2)] == [
        "扫描件第一页",
        "扫描件第二页",
    ]
    assert [units_by_page[page].unit_kind for page in (1, 2)] == [
        "pdf_ocr_region",
        "pdf_text_chunk",
    ]
    region_locator = asset_db_session.get(
        EvidenceLocator, units_by_page[1].source_locator_id
    )
    assert region_locator is not None and region_locator.locator_kind == "pdf_region"
    detail = asset_db_session.get(PdfLocatorDetail, region_locator.id)
    assert detail is not None
    assert detail.coordinate_space == "pdf_crop_box_normalized_top_left_v1"
    assert detail.crop_x1_points == 612.0
    stored_regions = asset_db_session.scalars(
        select(SpatialLocatorRegion).where(
            SpatialLocatorRegion.locator_id == region_locator.id
        )
    ).all()
    assert [
        (region.x, region.y, region.width, region.height) for region in stored_regions
    ] == [(0.1, 0.2, 0.7, 0.1)]


def test_ocr_chunk_with_unlocated_text_falls_back_to_page_evidence(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(
        asset_db_session, email="partial-ocr-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="uploaded"
    )
    now = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    text = "located\nunlocated"
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(
            [
                parsed_page(
                    1,
                    text,
                    source_kind="ocr",
                    regions=(
                        PageRegionResult(
                            text="located",
                            unit_kind="pdf_ocr_region",
                            x=0.1,
                            y=0.2,
                            width=0.3,
                            height=0.1,
                            char_start=0,
                            char_end=len("located"),
                        ),
                    ),
                )
            ]
        ),
    )

    unit = asset_db_session.scalar(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    )
    assert unit is not None
    locator = asset_db_session.get(EvidenceLocator, unit.source_locator_id)
    assert locator is not None and locator.locator_kind == "pdf_page"
    assert unit.unit_kind == "pdf_text_chunk"
    assert (
        asset_db_session.scalars(
            select(SpatialLocatorRegion).where(
                SpatialLocatorRegion.locator_id == locator.id
            )
        ).all()
        == []
    )


def test_ingestion_worker_reclaims_stale_job(asset_db_session: Session) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="parsing"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="running",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC) - INGESTION_LEASE_TIMEOUT - timedelta(minutes=1),
        started_at=datetime.now(UTC) - INGESTION_LEASE_TIMEOUT - timedelta(minutes=1),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    claimed_job_id = claim_next_ingestion_job(asset_db_session)

    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert claimed_job_id == job.id
    assert refreshed_job is not None
    assert refreshed_job.status == "running"
    assert refreshed_job.attempt_count == 2
    assert asset_db_session.get(Asset, asset.id).status == "parsing"


def test_ingestion_worker_requires_pdf_adapter(
    asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="uploaded"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _object_key: (_ for _ in ()).throw(
            AssertionError("download must not run")
        ),
    )
    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    assert claimed_job_id == job.id

    process_ingestion_job(asset_db_session, claimed_job_id)

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "failed"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "modality_adapter_unavailable"


def test_token_count_estimate_handles_cjk_and_words() -> None:
    assert estimate_token_count("中文文本") == 4
    assert estimate_token_count("hello world") == 2


def test_pdf_region_text_must_match_its_page_character_range() -> None:
    with pytest.raises(ValueError, match="does not match"):
        parsed_page(
            1,
            "secret",
            source_kind="ocr",
            regions=(
                PageRegionResult(
                    text="WRONG",
                    unit_kind="pdf_ocr_region",
                    x=0.1,
                    y=0.2,
                    width=0.3,
                    height=0.1,
                    char_start=0,
                    char_end=6,
                ),
            ),
        )
