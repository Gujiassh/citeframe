from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
    PdfLocatorDetail,
    PdfPage,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import reindex_asset
from ai_pdf_api.services.embedding_index import (
    EMBEDDING_INDEX_MISMATCH_CODE,
    EMBEDDING_INDEX_MISMATCH_MESSAGE,
    EmbeddingIndexContract,
    assert_current_embeddings_match_contract,
    embedding_index_job_snapshot_fields,
    resolve_embedding_index_contract,
)
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_api.services.retrieval import retrieve_content, retrieve_query_content


class _Provider:
    provider = "provider-a"
    model = "model-a"
    dimensions = 3
    version = "v1"
    config_fingerprint = "a" * 64

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _asset_graph(
    db: Session,
    *,
    status: str = "ready",
    provider: str = "provider-a",
    model: str = "model-a",
    dimensions: int = 3,
    version: str = "v1",
    with_embedding: bool = True,
) -> tuple[Asset, ContentUnit]:
    now = datetime.now(UTC)
    user = User(
        email=f"index-{uuid4()}@example.com",
        name="Index test",
        password_hash="hash",
        avatar_url="",
        created_at=now,
        updated_at=now,
    )
    workspace = Workspace(
        name="Index test",
        created_by_user_id=user.id,
        system_prompt="Evidence only.",
        retrieval_top_k=6,
        chunk_size=1200,
        created_at=now,
        updated_at=now,
    )
    asset = Asset(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="index.pdf",
        source_filename="index.pdf",
        object_key=f"index/{uuid4()}.pdf",
        mime_type="application/pdf",
        byte_size=3,
        source_sha256="a" * 64,
        status=status,
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
        generator_version="test-v1",
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
    page = PdfPage(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        page_number=1,
        extracted_text="index evidence",
        char_count=14,
        legacy_ocr_blocks=[],
        created_at=now,
    )
    unit = ContentUnit(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_order=0,
        text_content="index evidence",
        token_count=2,
        char_start=0,
        char_end=14,
        index_version=1,
        created_at=now,
    )
    db.add(user)
    db.flush()
    workspace.created_by_user_id = user.id
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    asset.workspace_id = workspace.id
    asset.created_by_user_id = user.id
    db.add(asset)
    db.flush()
    representation.workspace_id = workspace.id
    representation.asset_id = asset.id
    db.add(representation)
    db.flush()
    page.workspace_id = workspace.id
    page.asset_id = asset.id
    page.representation_id = representation.id
    db.add(page)
    db.flush()
    locator.workspace_id = workspace.id
    locator.asset_id = asset.id
    locator.representation_id_snapshot = representation.id
    db.add(locator)
    db.flush()
    db.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=1))
    unit.workspace_id = workspace.id
    unit.asset_id = asset.id
    unit.representation_id = representation.id
    unit.source_locator_id = locator.id
    db.add(unit)
    db.flush()
    if with_embedding:
        db.add(
            ContentUnitEmbedding(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                content_unit_id=unit.id,
                processing_generation=1,
                index_version=1,
                is_current=True,
                embedding_space="text",
                provider=provider,
                model=model,
                dimensions=dimensions,
                version=version,
                embedding=[1.0, 0.0, 0.0],
                created_at=now,
            )
        )
        db.flush()
    return asset, unit


def test_resolve_contract_from_provider_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _Provider()
    from_provider = resolve_embedding_index_contract(provider)
    assert from_provider == EmbeddingIndexContract(
        provider="provider-a",
        model="model-a",
        dimensions=3,
        version="v1",
        config_fingerprint="a" * 64,
    )

    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v1")
    from_settings = resolve_embedding_index_contract()
    assert from_settings.provider == "openai"
    assert from_settings.model == "text-embedding-3-small"
    assert from_settings.dimensions == 1024
    assert from_settings.version == "embedding-v1"
    snapshot = embedding_index_job_snapshot_fields(from_provider)
    assert snapshot == {
        "embeddingProvider": "provider-a",
        "embeddingModel": "model-a",
        "embeddingDimensions": 3,
        "embeddingVersion": "v1",
        "embeddingProfileFingerprint": "a" * 64,
    }


def test_old_provider_vectors_fail_closed_with_stable_code() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(
            db,
            provider="provider-old",
            model="model-old",
            dimensions=3,
            version="v-old",
        )
        db.commit()
        contract = resolve_embedding_index_contract(_Provider())
        with pytest.raises(ModelProviderError) as error:
            assert_current_embeddings_match_contract(
                db,
                asset.workspace_id,
                contract,
            )
        assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
        assert "explicit reindex" in error.value.message.lower()

        with pytest.raises(ModelProviderError) as retrieval_error:
            retrieve_content(
                db,
                asset.workspace_id,
                [1.0, 0.0, 0.0],
                embedding_provider=_Provider(),
            )
        assert retrieval_error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
    finally:
        db.close()


def test_matching_vectors_allow_retrieval() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
        )
        assert len(results) == 1
        assert results[0].asset.id == asset.id
    finally:
        db.close()


def test_normal_empty_scope_does_not_report_mismatch() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db, with_embedding=False)
        db.commit()
        assert retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
        ) == []
        assert retrieve_query_content(
            db,
            asset.workspace_id,
            "index evidence",
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
            strategy="dense",
        ) == []
        assert retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            asset_ids=[],
            embedding_provider=_Provider(),
        ) == []
    finally:
        db.close()


def test_settings_change_does_not_auto_reindex_or_rewrite_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        asset, unit = _asset_graph(
            db,
            provider="provider-old",
            model="model-old",
            dimensions=3,
            version="v-old",
        )
        db.commit()
        monkeypatch.setattr(settings, "embedding_provider", "provider-a")
        monkeypatch.setattr(settings, "embedding_model", "model-a")
        monkeypatch.setattr(settings, "embedding_dimensions", 3)
        monkeypatch.setattr(settings, "embedding_version", "v1")

        with pytest.raises(ModelProviderError) as error:
            retrieve_content(
                db,
                asset.workspace_id,
                [1.0, 0.0, 0.0],
                embedding_provider=_Provider(),
            )
        assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE

        embeddings = db.scalars(
            select(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id)
        ).all()
        assert len(embeddings) == 1
        assert embeddings[0].provider == "provider-old"
        assert embeddings[0].model == "model-old"
        assert embeddings[0].version == "v-old"
        assert embeddings[0].is_current is True
        assert unit.id == embeddings[0].content_unit_id
        assert db.scalar(select(IngestionJob.id).where(IngestionJob.asset_id == asset.id)) is None
    finally:
        db.close()


def test_reindex_snapshot_uses_active_contract_and_does_not_bypass_delete() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        user = db.get(User, asset.created_by_user_id)
        assert user is not None
        workspace = db.get(Workspace, asset.workspace_id)
        assert workspace is not None
        db.commit()

        response = reindex_asset(asset.workspace_id, asset.id, user, db)
        assert response.job.jobType == "embed_chunks"
        job = db.get(IngestionJob, response.job.id)
        assert job is not None
        assert job.config_snapshot is not None
        assert job.config_snapshot["source"] == "reindex"
        assert job.config_snapshot["chunkSize"] == workspace.chunk_size
        for key in (
            "embeddingProvider",
            "embeddingModel",
            "embeddingDimensions",
            "embeddingVersion",
            "embeddingProfileFingerprint",
        ):
            assert key in job.config_snapshot
        assert isinstance(job.config_snapshot["embeddingProfileFingerprint"], str)

        delete_job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="delete_cleanup",
            status="queued",
            attempt_count=1,
            requested_by_user_id=user.id,
            queued_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db.add(delete_job)
        db.flush()
        asset.latest_ingestion_job_id = delete_job.id
        asset.status = "deleting"
        db.commit()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            reindex_asset(asset.workspace_id, asset.id, user, db)
        assert error.value.status_code == 409
        detail = str(error.value.detail).lower()
        assert "delet" in detail
        db.expire_all()
        assert db.get(Asset, asset.id).latest_ingestion_job_id == delete_job.id
        assert db.get(IngestionJob, delete_job.id).status == "queued"
    finally:
        db.close()


def test_coexisting_matching_provider_does_not_fail_closed() -> None:
    db = _session()
    try:
        asset, unit = _asset_graph(
            db,
            provider="provider-old",
            model="model-old",
            dimensions=3,
            version="v-old",
        )
        now = datetime.now(UTC)
        db.add(
            ContentUnitEmbedding(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                content_unit_id=unit.id,
                processing_generation=1,
                index_version=1,
                is_current=True,
                embedding_space="text",
                provider="provider-a",
                model="model-a",
                dimensions=3,
                version="v1",
                embedding=[0.0, 1.0, 0.0],
                created_at=now,
            )
        )
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [0.0, 1.0, 0.0],
            embedding_provider=_Provider(),
        )
        assert len(results) == 1
    finally:
        db.close()


def _attach_index_job(
    db: Session,
    asset: Asset,
    *,
    config_snapshot: dict[str, object] | None,
    job_type: str = "embed_chunks",
    status: str = "succeeded",
    finished_at: datetime | None = None,
    created_at: datetime | None = None,
    set_as_latest: bool = True,
) -> IngestionJob:
    now = datetime.now(UTC)
    created = created_at or now
    finished = finished_at if finished_at is not None else (created if status == "succeeded" else None)
    job = IngestionJob(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        job_type=job_type,
        status=status,
        attempt_count=1,
        config_snapshot=config_snapshot,
        requested_by_user_id=asset.created_by_user_id,
        queued_at=created,
        started_at=created,
        finished_at=finished,
        created_at=created,
    )
    db.add(job)
    db.flush()
    if set_as_latest:
        asset.latest_ingestion_job_id = job.id
        db.flush()
    return job


def _attach_succeeded_index_job(
    db: Session,
    asset: Asset,
    *,
    config_snapshot: dict[str, object],
    job_type: str = "embed_chunks",
) -> IngestionJob:
    return _attach_index_job(
        db,
        asset,
        config_snapshot=config_snapshot,
        job_type=job_type,
        status="succeeded",
    )


def test_fingerprint_only_drift_on_latest_successful_job_fails_closed() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        _attach_succeeded_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "b" * 64,
            },
        )
        db.commit()
        with pytest.raises(ModelProviderError) as error:
            retrieve_content(
                db,
                asset.workspace_id,
                [1.0, 0.0, 0.0],
                embedding_provider=_Provider(),
            )
        assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
        assert "explicit reindex" in error.value.message.lower()
    finally:
        db.close()


def test_legacy_successful_job_without_fingerprint_remains_compatible() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        _attach_succeeded_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
            },
            job_type="ingest",
        )
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
        )
        assert len(results) == 1
    finally:
        db.close()


def test_matching_job_fingerprint_allows_retrieval() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        _attach_succeeded_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "a" * 64,
            },
        )
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
        )
        assert len(results) == 1
    finally:
        db.close()


def test_asset_latest_pointer_is_not_used_for_fingerprint_resolution() -> None:
    """Corrupt/cross-scope Asset.latest_ingestion_job_id must not select the snapshot."""

    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        other_asset, _other_unit = _asset_graph(db)
        older = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "a" * 64,
            },
            finished_at=older,
            created_at=older,
            set_as_latest=False,
        )
        foreign_job = _attach_succeeded_index_job(
            db,
            other_asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "b" * 64,
            },
        )
        # Corrupt pointer must not select the foreign snapshot or fail open/closed on it.
        asset.latest_ingestion_job_id = foreign_job.id
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
            asset_ids=[asset.id],
        )
        assert len(results) == 1
    finally:
        db.close()


def test_stale_successful_index_job_still_checked_when_later_reindex_failed() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        older = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        newer = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
        _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "b" * 64,
            },
            finished_at=older,
            created_at=older,
            set_as_latest=False,
        )
        failed_reindex = _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "a" * 64,
            },
            status="failed",
            finished_at=newer,
            created_at=newer,
            set_as_latest=True,
        )
        assert asset.latest_ingestion_job_id == failed_reindex.id
        db.commit()
        with pytest.raises(ModelProviderError) as error:
            retrieve_content(
                db,
                asset.workspace_id,
                [1.0, 0.0, 0.0],
                embedding_provider=_Provider(),
            )
        assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
        assert "explicit reindex" in error.value.message.lower()
    finally:
        db.close()


def test_matching_successful_index_job_passes_when_later_reindex_failed() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        older = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        newer = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
        _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "a" * 64,
            },
            job_type="embed_chunks",
            finished_at=older,
            created_at=older,
            set_as_latest=False,
        )
        failed_reindex = _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "c" * 64,
            },
            job_type="embed_chunks",
            status="failed",
            finished_at=newer,
            created_at=newer,
            set_as_latest=True,
        )
        assert asset.latest_ingestion_job_id == failed_reindex.id
        db.commit()
        results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
        )
        assert len(results) == 1
        assert results[0].asset.id == asset.id
    finally:
        db.close()


def test_newest_successful_index_job_determines_fingerprint_despite_unrelated_latest_pointer() -> None:
    """Production resolver uses newest successful index job, not Asset.latest pointer."""

    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        other_asset, _other_unit = _asset_graph(db)
        older = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        newer = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
        latest_failed = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)

        older_snapshot = {
            "source": "reindex",
            "embeddingProvider": "provider-a",
            "embeddingModel": "model-a",
            "embeddingDimensions": 3,
            "embeddingVersion": "v1",
            "embeddingProfileFingerprint": "b" * 64,
        }
        newer_snapshot = {
            "source": "reindex",
            "embeddingProvider": "provider-a",
            "embeddingModel": "model-a",
            "embeddingDimensions": 3,
            "embeddingVersion": "v1",
            "embeddingProfileFingerprint": "a" * 64,
        }

        _attach_index_job(
            db,
            asset,
            config_snapshot=older_snapshot,
            job_type="ingest",
            finished_at=older,
            created_at=older,
            set_as_latest=False,
        )
        _attach_index_job(
            db,
            asset,
            config_snapshot=newer_snapshot,
            job_type="embed_chunks",
            finished_at=newer,
            created_at=newer,
            set_as_latest=False,
        )
        failed_local = _attach_index_job(
            db,
            asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "c" * 64,
            },
            job_type="embed_chunks",
            status="failed",
            finished_at=latest_failed,
            created_at=latest_failed,
            set_as_latest=False,
        )
        foreign_failed = _attach_index_job(
            db,
            other_asset,
            config_snapshot={
                "source": "reindex",
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
                "embeddingProfileFingerprint": "d" * 64,
            },
            job_type="embed_chunks",
            status="failed",
            finished_at=latest_failed,
            created_at=latest_failed,
            set_as_latest=True,
        )
        # Unrelated/failed pointer must not override newest successful index job.
        asset.latest_ingestion_job_id = foreign_failed.id
        db.commit()
        assert asset.latest_ingestion_job_id != failed_local.id

        matching_results = retrieve_content(
            db,
            asset.workspace_id,
            [1.0, 0.0, 0.0],
            embedding_provider=_Provider(),
            asset_ids=[asset.id],
        )
        assert len(matching_results) == 1
        assert matching_results[0].asset.id == asset.id

        # Flip newest successful fingerprint to force mismatch while pointer stays unrelated.
        newer_succeeded = db.scalars(
            select(IngestionJob)
            .where(
                IngestionJob.asset_id == asset.id,
                IngestionJob.status == "succeeded",
                IngestionJob.job_type == "embed_chunks",
            )
            .order_by(IngestionJob.finished_at.desc())
        ).first()
        assert newer_succeeded is not None
        newer_succeeded.config_snapshot = {
            **newer_snapshot,
            "embeddingProfileFingerprint": "e" * 64,
        }
        db.commit()

        with pytest.raises(ModelProviderError) as error:
            retrieve_content(
                db,
                asset.workspace_id,
                [1.0, 0.0, 0.0],
                embedding_provider=_Provider(),
                asset_ids=[asset.id],
            )
        assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
        assert "explicit reindex" in error.value.message.lower()
    finally:
        db.close()


def test_resolve_contract_never_returns_empty_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoFingerprintProvider(_Provider):
        config_fingerprint = ""

    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v1")
    from_settings = resolve_embedding_index_contract()
    assert isinstance(from_settings.config_fingerprint, str)
    assert from_settings.config_fingerprint

    resolved = resolve_embedding_index_contract(_NoFingerprintProvider())
    assert resolved.config_fingerprint
    assert resolved.provider == "provider-a"


def test_message_requires_explicit_reindex() -> None:
    assert "explicit reindex" in EMBEDDING_INDEX_MISMATCH_MESSAGE.lower()
    from ai_pdf_api.services.embedding_index import raise_embedding_index_mismatch

    with pytest.raises(ModelProviderError) as error:
        raise_embedding_index_mismatch()
    assert error.value.code == EMBEDDING_INDEX_MISMATCH_CODE
    assert "explicit reindex" in error.value.message.lower()
