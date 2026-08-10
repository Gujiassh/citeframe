from datetime import UTC, datetime

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.pdf_ingestion import (
    PageArtifactResult,
    SpatialRegionResult,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
)
from ai_pdf_api.services import ingestion as ingestion_service
from ai_pdf_api.services.ingestion import (
    claim_next_ingestion_job,
    process_ingestion_job,
)
from asset_router_test_support import (
    create_asset,
    create_pdf_content_unit,
    create_user,
    create_workspace_with_membership,
    failing_pdf_adapters,
    parsed_page,
    static_pdf_adapters,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_ingestion_worker_persists_pages_and_chunks(
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
    asset_db_session.commit()

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"pdf"
    )

    def extract_pages(_payload: bytes):
        return [
            parsed_page(1, "Page one heading\n" + "alpha " * 300),
            parsed_page(2, "Page two body"),
        ]

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    assert claimed_job_id == job.id
    assert asset_db_session.get(Asset, asset.id).status == "parsing"

    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(extract_pages(b"pdf")),
    )

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    pages = asset_db_session.scalars(
        select(PdfPage).where(PdfPage.asset_id == asset.id)
    ).all()
    chunks = asset_db_session.scalars(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    ).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert len(pages) == 2
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert len(pages) == 2
    assert len(chunks) >= 2
    assert {chunk.index_version for chunk in chunks} == {1}
    assert all(page.crop_x0_points == 0.0 for page in pages)
    assert all(page.crop_y1_points == 792.0 for page in pages)
    assert all(page.display_width_points == 612.0 for page in pages)


def test_ingestion_worker_embeds_chunks_and_marks_asset_ready(
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

    class FakeEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(
            [parsed_page(1, "embedding regression text")]
        ),
        embedding_provider=FakeEmbeddingProvider(),
    )

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    chunks = asset_db_session.scalars(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    ).all()
    embeddings = asset_db_session.scalars(
        select(ContentUnitEmbedding).where(
            ContentUnitEmbedding.content_unit_id.in_([chunk.id for chunk in chunks])
        )
    ).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "ready"
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert chunks
    assert embeddings and embeddings[0].embedding == [1.0, 0.0, 0.0]
    assert embeddings[0].provider == "fake"
    assert embeddings[0].dimensions == 3
    assert {
        (
            embedding.asset_id,
            embedding.processing_generation,
            embedding.index_version,
            embedding.is_current,
        )
        for embedding in embeddings
    } == {(asset.id, 1, 1, True)}


def test_ingestion_persists_artifacts_without_duplicate_embedding_text(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(
        asset_db_session, email="artifact-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Artifacts"
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
        config_snapshot={"source": "artifact-fixture"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    page_text = (
        "Artifact fixture\n"
        "Model Score\n"
        "Evidence-A 91.4\n"
        "Figure 1. Trend rises after the third point.\n"
        "Unrelated page conclusion.\n"
        "Supporting caption in a separate region."
    )
    table_source = "Model Score\nEvidence-A 91.4"
    figure_source = "Figure 1. Trend rises after the third point."
    figure_support = "Supporting caption in a separate region."
    table_start = page_text.index(table_source)
    figure_start = page_text.index(figure_source)
    figure_support_start = page_text.index(figure_support)
    page_result = parsed_page(
        1,
        page_text,
        artifacts=(
            PageArtifactResult(
                text="| Model | Score |\n| --- | --- |\n| Evidence-A | 91.4 |",
                unit_kind="pdf_table",
                regions=(SpatialRegionResult(x=0.1, y=0.2, width=0.7, height=0.2),),
                char_ranges=((table_start, table_start + len(table_source)),),
            ),
            PageArtifactResult(
                text=f"{figure_source}\n{figure_support}",
                unit_kind="pdf_figure",
                regions=(
                    SpatialRegionResult(x=0.15, y=0.5, width=0.6, height=0.25),
                    SpatialRegionResult(x=0.15, y=0.78, width=0.5, height=0.05),
                ),
                char_ranges=(
                    (figure_start, figure_start + len(figure_source)),
                    (figure_support_start, figure_support_start + len(figure_support)),
                ),
            ),
        ),
    )

    class CapturingEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def __init__(self) -> None:
            self.texts: list[str] = []

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.texts.extend(texts)
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    embedding_provider = CapturingEmbeddingProvider()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([page_result]),
        embedding_provider=embedding_provider,
    )

    representations = asset_db_session.scalars(
        select(AssetRepresentation)
        .where(AssetRepresentation.asset_id == asset.id)
        .order_by(AssetRepresentation.representation_kind)
    ).all()
    units = asset_db_session.scalars(
        select(ContentUnit)
        .where(ContentUnit.asset_id == asset.id)
        .order_by(ContentUnit.unit_kind)
    ).all()
    assert {
        representation.representation_kind for representation in representations
    } == {
        "pdf_page_layout",
        "pdf_table",
        "pdf_figure",
    }
    assert {unit.unit_kind for unit in units} == {
        "pdf_text_chunk",
        "pdf_table",
        "pdf_figure",
    }
    assert sum("Evidence-A" in unit.text_content for unit in units) == 1
    assert sum("Trend rises" in unit.text_content for unit in units) == 1
    assert sum("Supporting caption" in unit.text_content for unit in units) == 1
    assert sum("Unrelated page conclusion" in unit.text_content for unit in units) == 1
    assert len(embedding_provider.texts) == len(units)
    assert sorted(embedding_provider.texts) == sorted(
        unit.text_content for unit in units
    )
    assert sum("Evidence-A" in text for text in embedding_provider.texts) == 1
    assert sum("Trend rises" in text for text in embedding_provider.texts) == 1
    assert sum("Supporting caption" in text for text in embedding_provider.texts) == 1
    assert (
        sum("Unrelated page conclusion" in text for text in embedding_provider.texts)
        == 1
    )

    artifact_units = [unit for unit in units if unit.unit_kind != "pdf_text_chunk"]
    assert all(
        unit.char_start is None and unit.char_end is None for unit in artifact_units
    )
    text_units = [unit for unit in units if unit.unit_kind == "pdf_text_chunk"]
    assert all(
        unit.char_start is not None and unit.char_end is not None for unit in text_units
    )
    for unit, expected_regions in zip(
        sorted(artifact_units, key=lambda item: item.unit_kind),
        (
            ((0.15, 0.5, 0.6, 0.25), (0.15, 0.78, 0.5, 0.05)),
            ((0.1, 0.2, 0.7, 0.2),),
        ),
        strict=True,
    ):
        locator = asset_db_session.get(EvidenceLocator, unit.source_locator_id)
        detail = asset_db_session.get(PdfLocatorDetail, unit.source_locator_id)
        regions = asset_db_session.scalars(
            select(SpatialLocatorRegion)
            .where(SpatialLocatorRegion.locator_id == unit.source_locator_id)
            .order_by(SpatialLocatorRegion.region_order)
        ).all()
        assert locator is not None and locator.locator_kind == "pdf_region"
        assert detail is not None
        assert detail.coordinate_space == "pdf_crop_box_normalized_top_left_v1"
        assert [region.region_order for region in regions] == list(
            range(len(expected_regions))
        )
        for region, expected_region in zip(regions, expected_regions, strict=True):
            assert (region.x, region.y, region.width, region.height) == pytest.approx(
                expected_region
            )


def test_failed_reprocessing_restores_previous_generation_content_and_embeddings(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(
        asset_db_session, email="rollback-owner@example.com", name="Owner"
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
        page_number=1,
        text="stable old evidence",
    )
    # Match production settings so _available_asset_status can recognize a complete
    # current retrieval chain after the failed reprocess rolls back.
    old_embedding = ContentUnitEmbedding(
        workspace_id=workspace.id,
        asset_id=asset.id,
        content_unit_id=old_unit.id,
        processing_generation=asset.current_processing_generation,
        index_version=old_unit.index_version,
        is_current=True,
        embedding_space="text",
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        embedding=[1.0] + [0.0] * (settings.embedding_dimensions - 1),
        created_at=datetime.now(UTC),
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "retry"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add_all([old_embedding, job])
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    before_pages = [
        (page.id, page.representation_id, page.extracted_text)
        for page in asset_db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ]
    before_units = [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in asset_db_session.scalars(
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset.id)
            .order_by(ContentUnit.id)
        ).all()
    ]
    before_embeddings = [
        (embedding.id, embedding.content_unit_id, embedding.embedding)
        for embedding in asset_db_session.scalars(
            select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
        ).all()
    ]
    before_representations = [
        representation.id
        for representation in asset_db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ]
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=failing_pdf_adapters(
            [parsed_page(1, "new partial evidence")]
        ),
    )

    asset_db_session.expire_all()
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == 1
    # Prior generation remains retrieval-ready; failed job/error stay recorded.
    assert refreshed_asset.status == "ready"
    assert refreshed_asset.last_error_code == "ingestion_failed"
    assert refreshed_asset.last_error_message is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "ingestion_failed"
    assert [
        (page.id, page.representation_id, page.extracted_text)
        for page in asset_db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ] == before_pages
    assert [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in asset_db_session.scalars(
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset.id)
            .order_by(ContentUnit.id)
        ).all()
    ] == before_units
    assert [
        (embedding.id, embedding.content_unit_id, embedding.embedding)
        for embedding in asset_db_session.scalars(
            select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
        ).all()
    ] == before_embeddings
    assert [
        representation.id
        for representation in asset_db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ] == before_representations


def test_failed_reprocessing_marks_partial_current_chain_failed(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(
        asset_db_session, email="partial-chain-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="ready"
    )
    # Representation + unit + locator exist, but embeddings are missing, so the
    # current retrieval chain is incomplete and must not be treated as ready.
    create_pdf_content_unit(
        asset_db_session,
        asset=asset,
        page_number=1,
        text="partial chain without embeddings",
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "retry-partial"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=failing_pdf_adapters(
            [parsed_page(1, "new partial evidence")]
        ),
    )

    asset_db_session.expire_all()
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == 1
    assert refreshed_asset.status == "failed"
    assert refreshed_asset.last_error_code == "ingestion_failed"
    assert refreshed_asset.last_error_message is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "ingestion_failed"


def test_failed_reprocessing_after_activation_preserves_previous_generation(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback must preserve the prior generation even after activation flips is_current.

    Existing adapter-failure cases never reach _embed_content_units / activation.
    This covers the post-activation transaction path: new generation embeds are
    written, old is_current is cleared, new is_current is set, then the job fails
    before commit and must restore the committed prior generation for retrieval.
    """
    owner = create_user(
        asset_db_session, email="post-activation-owner@example.com", name="Owner"
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
        page_number=1,
        text="stable old evidence",
    )
    old_vector = [1.0] + [0.0] * (settings.embedding_dimensions - 1)
    old_embedding = ContentUnitEmbedding(
        workspace_id=workspace.id,
        asset_id=asset.id,
        content_unit_id=old_unit.id,
        processing_generation=asset.current_processing_generation,
        index_version=old_unit.index_version,
        is_current=True,
        embedding_space="text",
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        embedding=old_vector,
        created_at=datetime.now(UTC),
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "source": "retry-post-activation",
            "embeddingProvider": settings.embedding_provider,
            "embeddingModel": settings.embedding_model,
            "embeddingDimensions": settings.embedding_dimensions,
            "embeddingVersion": settings.embedding_version,
        },
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add_all([old_embedding, job])
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    before_generation = asset.current_processing_generation
    before_index_version = asset.current_index_version
    before_pages = [
        (page.id, page.representation_id, page.extracted_text)
        for page in asset_db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ]
    before_units = [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in asset_db_session.scalars(
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset.id)
            .order_by(ContentUnit.id)
        ).all()
    ]
    before_embeddings = [
        (
            embedding.id,
            embedding.content_unit_id,
            embedding.processing_generation,
            embedding.index_version,
            embedding.is_current,
            embedding.provider,
            embedding.model,
            embedding.dimensions,
            embedding.version,
            embedding.embedding_space,
            list(embedding.embedding),
        )
        for embedding in asset_db_session.scalars(
            select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
        ).all()
    ]
    before_representations = [
        representation.id
        for representation in asset_db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ]
    before_locator_ids = [
        locator.id
        for locator in asset_db_session.scalars(
            select(EvidenceLocator)
            .where(EvidenceLocator.asset_id == asset.id)
            .order_by(EvidenceLocator.id)
        ).all()
    ]
    before_locator_details = [
        (
            detail.locator_id,
            detail.page_id,
            detail.page_number,
            detail.coordinate_space,
            detail.crop_x0_points,
            detail.crop_y0_points,
            detail.crop_x1_points,
            detail.crop_y1_points,
            detail.rotation_degrees,
            detail.display_width_points,
            detail.display_height_points,
        )
        for detail in asset_db_session.scalars(
            select(PdfLocatorDetail)
            .where(PdfLocatorDetail.locator_id.in_(before_locator_ids))
            .order_by(PdfLocatorDetail.locator_id)
        ).all()
    ]

    class MatchingEmbeddingProvider:
        provider = settings.embedding_provider
        model = settings.embedding_model
        dimensions = settings.embedding_dimensions
        version = settings.embedding_version

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.5] + [0.0] * (self.dimensions - 1) for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [0.5] + [0.0] * (self.dimensions - 1)

    real_activate = ingestion_service._activate_current_embeddings

    def activate_then_fail(db, asset_arg, embedding_provider, *, processing_generation):
        real_activate(
            db,
            asset_arg,
            embedding_provider,
            processing_generation=processing_generation,
        )
        # Prove activation already flipped currentness in this open transaction
        # before the forced failure (not a no-op wrapper around a no-op call).
        prior_after_activate = db.get(ContentUnitEmbedding, old_embedding.id)
        assert prior_after_activate is not None
        assert prior_after_activate.is_current is False
        assert prior_after_activate.processing_generation == before_generation
        activated_new = db.scalars(
            select(ContentUnitEmbedding).where(
                ContentUnitEmbedding.asset_id == asset_arg.id,
                ContentUnitEmbedding.processing_generation == processing_generation,
                ContentUnitEmbedding.is_current.is_(True),
            )
        ).all()
        assert activated_new
        assert all(
            embedding.processing_generation > before_generation
            for embedding in activated_new
        )
        raise RuntimeError("forced failure after embedding activation")

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf"
    )
    monkeypatch.setattr(
        ingestion_service,
        "_activate_current_embeddings",
        activate_then_fail,
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(
            [parsed_page(1, "new generation evidence after activation")]
        ),
        embedding_provider=MatchingEmbeddingProvider(),
    )

    asset_db_session.expire_all()
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == before_generation
    assert refreshed_asset.current_index_version == before_index_version
    assert refreshed_asset.status == "ready"
    assert refreshed_asset.last_error_code == "ingestion_failed"
    assert refreshed_asset.last_error_message is not None
    assert "forced failure after embedding activation" in refreshed_asset.last_error_message
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "ingestion_failed"
    assert refreshed_job.error_message is not None
    assert "forced failure after embedding activation" in refreshed_job.error_message

    assert [
        (page.id, page.representation_id, page.extracted_text)
        for page in asset_db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ] == before_pages
    assert [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in asset_db_session.scalars(
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset.id)
            .order_by(ContentUnit.id)
        ).all()
    ] == before_units
    assert [
        representation.id
        for representation in asset_db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ] == before_representations

    after_locator_ids = [
        locator.id
        for locator in asset_db_session.scalars(
            select(EvidenceLocator)
            .where(EvidenceLocator.asset_id == asset.id)
            .order_by(EvidenceLocator.id)
        ).all()
    ]
    assert after_locator_ids == before_locator_ids
    assert [
        (
            detail.locator_id,
            detail.page_id,
            detail.page_number,
            detail.coordinate_space,
            detail.crop_x0_points,
            detail.crop_y0_points,
            detail.crop_x1_points,
            detail.crop_y1_points,
            detail.rotation_degrees,
            detail.display_width_points,
            detail.display_height_points,
        )
        for detail in asset_db_session.scalars(
            select(PdfLocatorDetail)
            .where(PdfLocatorDetail.locator_id.in_(before_locator_ids))
            .order_by(PdfLocatorDetail.locator_id)
        ).all()
    ] == before_locator_details

    after_embeddings = asset_db_session.scalars(
        select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
    ).all()
    assert [
        (
            embedding.id,
            embedding.content_unit_id,
            embedding.processing_generation,
            embedding.index_version,
            embedding.is_current,
            embedding.provider,
            embedding.model,
            embedding.dimensions,
            embedding.version,
            embedding.embedding_space,
            list(embedding.embedding),
        )
        for embedding in after_embeddings
    ] == before_embeddings
    assert len(after_embeddings) == 1
    assert after_embeddings[0].id == old_embedding.id
    assert after_embeddings[0].is_current is True
    assert after_embeddings[0].processing_generation == before_generation
    assert after_embeddings[0].index_version == before_index_version
    assert list(after_embeddings[0].embedding) == old_vector
    assert after_embeddings[0].provider == settings.embedding_provider
    assert after_embeddings[0].model == settings.embedding_model
    assert after_embeddings[0].dimensions == settings.embedding_dimensions
    assert after_embeddings[0].version == settings.embedding_version
    assert after_embeddings[0].embedding_space == "text"

    # No new-generation rows survive the failed transaction.
    assert not asset_db_session.scalars(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation > before_generation,
        )
    ).all()
    assert not asset_db_session.scalars(
        select(ContentUnitEmbedding).where(
            ContentUnitEmbedding.asset_id == asset.id,
            ContentUnitEmbedding.processing_generation > before_generation,
        )
    ).all()
    assert not asset_db_session.scalars(
        select(ContentUnit).where(
            ContentUnit.asset_id == asset.id,
            ContentUnit.id != old_unit.id,
        )
    ).all()
    assert not asset_db_session.scalars(
        select(EvidenceLocator).where(
            EvidenceLocator.asset_id == asset.id,
            EvidenceLocator.processing_generation_snapshot > before_generation,
        )
    ).all()
    assert not asset_db_session.scalars(
        select(PdfLocatorDetail).where(
            PdfLocatorDetail.locator_id.not_in(before_locator_ids)
        )
    ).all()
