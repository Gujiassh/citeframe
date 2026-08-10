import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import (
    finalize_upload,
    reindex_asset,
    retry_asset,
    upload_asset_binary,
)
from ai_pdf_api.schemas.asset import FinalizeUploadRequest
from ai_pdf_api.services import ingestion
from ai_pdf_api.services.ingestion import claim_next_ingestion_job, process_embedding_job


class _Provider:
    provider = "provider-a"
    model = "model-a"
    dimensions = 3
    version = "v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _asset_graph(db: Session) -> tuple[Asset, ContentUnit]:
    now = datetime.now(UTC)
    user = User(
        email=f"scope-{uuid4()}@example.com",
        name="Scope test",
        password_hash="hash",
        avatar_url="",
        created_at=now,
        updated_at=now,
    )
    workspace = Workspace(
        name="Scope test",
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
        title="scope.pdf",
        source_filename="scope.pdf",
        object_key=f"scope/{uuid4()}.pdf",
        mime_type="application/pdf",
        byte_size=3,
        source_sha256="a" * 64,
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
    unit = ContentUnit(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_order=0,
        text_content="scope evidence",
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
    locator.workspace_id = workspace.id
    locator.asset_id = asset.id
    locator.representation_id_snapshot = representation.id
    db.add(locator)
    db.flush()
    unit.workspace_id = workspace.id
    unit.asset_id = asset.id
    unit.representation_id = representation.id
    unit.source_locator_id = locator.id
    db.add(unit)
    db.flush()
    return asset, unit


def test_reembedding_one_provider_preserves_other_current_provider() -> None:
    db = _session()
    try:
        asset, unit = _asset_graph(db)
        now = datetime.now(UTC)
        db.add_all(
            [
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
                ),
                ContentUnitEmbedding(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    content_unit_id=unit.id,
                    processing_generation=1,
                    index_version=1,
                    is_current=True,
                    embedding_space="text",
                    provider="provider-b",
                    model="model-b",
                    dimensions=3,
                    version="v1",
                    embedding=[0.0, 0.0, 1.0],
                    created_at=now,
                ),
            ]
        )
        job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="embed_chunks",
            status="queued",
            attempt_count=1,
            config_snapshot={
                "embeddingProvider": "provider-a",
                "embeddingModel": "model-a",
                "embeddingDimensions": 3,
                "embeddingVersion": "v1",
            },
            requested_by_user_id=asset.created_by_user_id,
            queued_at=now,
            created_at=now,
        )
        db.add(job)
        db.flush()
        asset.latest_ingestion_job_id = job.id
        db.commit()
        process_embedding_job(db, claim_next_ingestion_job(db), _Provider())
        embeddings = db.scalars(
            select(ContentUnitEmbedding)
            .where(ContentUnitEmbedding.asset_id == asset.id)
            .order_by(ContentUnitEmbedding.provider)
        ).all()
        assert [(item.provider, item.is_current) for item in embeddings] == [
            ("provider-a", True),
            ("provider-b", True),
        ]
    finally:
        db.close()


def test_superseded_embedding_job_is_cancelled_without_touching_asset() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        now = datetime.now(UTC)
        job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="embed_chunks",
            status="running",
            attempt_count=1,
            requested_by_user_id=asset.created_by_user_id,
            queued_at=now,
            started_at=now,
            created_at=now,
        )
        newer_job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="embed_chunks",
            status="queued",
            attempt_count=1,
            requested_by_user_id=asset.created_by_user_id,
            queued_at=now,
            created_at=now,
        )
        db.add_all([job, newer_job])
        db.flush()
        asset.latest_ingestion_job_id = newer_job.id
        db.commit()
        process_embedding_job(db, job.id, _Provider())
        assert db.get(IngestionJob, job.id).status == "cancelled"
        assert db.get(IngestionJob, job.id).error_code == "ingestion_job_superseded"
        assert db.get(Asset, asset.id).status == "ready"
    finally:
        db.close()


def test_embedding_failure_cannot_overwrite_queued_delete() -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        now = datetime.now(UTC)
        embed_job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="embed_chunks",
            status="running",
            attempt_count=1,
            requested_by_user_id=asset.created_by_user_id,
            queued_at=now,
            started_at=now,
            created_at=now,
        )
        db.add(embed_job)
        db.flush()
        asset.latest_ingestion_job_id = embed_job.id
        db.commit()

        class _DeletingProvider(_Provider):
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                delete_job = IngestionJob(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    job_type="delete_cleanup",
                    status="queued",
                    attempt_count=1,
                    requested_by_user_id=asset.created_by_user_id,
                    queued_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
                db.add(delete_job)
                db.flush()
                asset.latest_ingestion_job_id = delete_job.id
                asset.status = "deleting"
                db.commit()
                raise RuntimeError("embedding failed after delete was queued")

        process_embedding_job(db, embed_job.id, _DeletingProvider())

        db.expire_all()
        refreshed_asset = db.get(Asset, asset.id)
        refreshed_embed_job = db.get(IngestionJob, embed_job.id)
        delete_job = db.scalar(
            select(IngestionJob).where(
                IngestionJob.asset_id == asset.id,
                IngestionJob.job_type == "delete_cleanup",
            )
        )
        assert refreshed_asset is not None
        assert refreshed_embed_job is not None
        assert delete_job is not None
        assert refreshed_embed_job.status == "cancelled"
        assert refreshed_embed_job.error_code == "ingestion_job_superseded"
        assert delete_job.status == "queued"
        assert refreshed_asset.status == "deleting"
        assert refreshed_asset.latest_ingestion_job_id == delete_job.id
    finally:
        db.close()


@pytest.mark.parametrize("operation", ["retry", "reindex"])
def test_asset_work_cannot_supersede_queued_delete(operation: str) -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        user = db.get(User, asset.created_by_user_id)
        assert user is not None
        delete_job = IngestionJob(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            job_type="delete_cleanup",
            status="queued",
            attempt_count=1,
            requested_by_user_id=asset.created_by_user_id,
            queued_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db.add(delete_job)
        db.flush()
        asset.latest_ingestion_job_id = delete_job.id
        asset.status = "failed" if operation == "retry" else "ready"
        db.commit()

        with pytest.raises(HTTPException, match="Asset deletion is already running") as error:
            if operation == "retry":
                retry_asset(asset.workspace_id, asset.id, user, db)
            else:
                reindex_asset(asset.workspace_id, asset.id, user, db)

        assert error.value.status_code == 409
        db.expire_all()
        assert db.get(Asset, asset.id).latest_ingestion_job_id == delete_job.id
        assert db.get(IngestionJob, delete_job.id).status == "queued"
    finally:
        db.close()


def test_claim_locks_asset_before_publishing_running_state(monkeypatch: pytest.MonkeyPatch) -> None:
    job = SimpleNamespace(
        id="embed-job",
        asset_id="asset-id",
        status="queued",
        job_type="embed_chunks",
        queued_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
        attempt_count=1,
        error_code=None,
        error_message=None,
    )
    asset = SimpleNamespace(
        id="asset-id",
        deleted_at=None,
        latest_ingestion_job_id=job.id,
        status="ready",
        last_error_code=None,
        last_error_message=None,
        updated_at=None,
    )
    db = Mock()
    db.scalar.side_effect = [job, asset]
    monkeypatch.setattr(ingestion, "recover_stale_ingestion_jobs", lambda *_args: None)

    assert claim_next_ingestion_job(db) == job.id
    asset_statement = db.scalar.call_args_list[1].args[0]
    assert "FOR UPDATE" in str(asset_statement.compile(dialect=postgresql.dialect()))
    assert job.status == "running"
    assert asset.status == "embedding"


def test_binary_upload_does_not_recreate_object_after_delete_is_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        payload = b"%PDF-1.7 upload race"
        asset.status = "pending_upload"
        # First-upload race path: source identity is still unset.
        asset.source_sha256 = None
        asset.byte_size = len(payload)
        db.commit()
        uploaded: list[str] = []
        monkeypatch.setattr(
            "ai_pdf_api.routers.assets.upload_stream",
            lambda object_key, *_args: uploaded.append(object_key),
        )

        class _DeletingRequest:
            headers = {
                "content-type": "application/pdf",
                "content-length": str(len(payload)),
            }

            async def stream(self):
                delete_job = IngestionJob(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    job_type="delete_cleanup",
                    status="queued",
                    attempt_count=1,
                    requested_by_user_id=asset.created_by_user_id,
                    queued_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
                db.add(delete_job)
                db.flush()
                asset.latest_ingestion_job_id = delete_job.id
                asset.status = "deleting"
                db.commit()
                yield payload

        with pytest.raises(HTTPException) as error:
            asyncio.run(
                upload_asset_binary(
                    asset.workspace_id,
                    asset.id,
                    _DeletingRequest(),
                    asset.object_key,
                    asset.created_by_user_id,
                    db,
                )
            )

        assert error.value.status_code == 409
        assert error.value.detail == "Asset is not awaiting upload."
        assert uploaded == []
        db.expire_all()
        refreshed_asset = db.get(Asset, asset.id)
        assert refreshed_asset is not None
        assert refreshed_asset.status == "deleting"
        assert db.get(IngestionJob, refreshed_asset.latest_ingestion_job_id).status == "queued"
    finally:
        db.close()


def test_finalize_locks_pending_asset_before_creating_ingest_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        asset, _unit = _asset_graph(db)
        user = db.get(User, asset.created_by_user_id)
        assert user is not None
        asset.status = "pending_upload"
        # Finalize requires a persisted source hash and matching stored bytes.
        source_bytes = b"pdf"
        asset.byte_size = len(source_bytes)
        asset.source_sha256 = sha256(source_bytes).hexdigest()
        db.commit()
        monkeypatch.setattr("ai_pdf_api.routers.assets.object_exists", lambda _key: True)
        monkeypatch.setattr(
            "ai_pdf_api.routers.assets.download_bytes",
            lambda _key: source_bytes,
        )
        refresh_calls: list[bool | dict] = []
        original_refresh = db.refresh

        def recording_refresh(instance, *args, with_for_update=None, **kwargs):
            if instance is asset:
                refresh_calls.append(with_for_update)
            return original_refresh(
                instance,
                *args,
                with_for_update=with_for_update,
                **kwargs,
            )

        monkeypatch.setattr(db, "refresh", recording_refresh)

        response = finalize_upload(
            asset.workspace_id,
            asset.id,
            FinalizeUploadRequest(objectKey=asset.object_key),
            user,
            db,
        )

        assert refresh_calls[0] is True
        assert response.asset.status == "uploaded"
        assert response.job.jobType == "ingest"
    finally:
        db.close()
