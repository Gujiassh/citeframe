from __future__ import annotations

from collections.abc import Generator, Mapping
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.image_ingestion import (
    IMAGE_ORIENTED_CONTENT_TYPE,
    ImageAnalysisResult,
    ImageNormalizationResult,
    ImageOcrRegionResult,
    build_image_oriented_object_key,
    delete_image_content,
    persist_image_analysis,
    persist_image_orientation,
)
from ai_pdf_api.modalities.ingestion import (
    GeneratedObject,
    IngestionAdapterRegistry,
    IngestionError,
    IngestionResult,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ImageRepresentationGeometry,
    IngestionJob,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import get_asset_detail
from ai_pdf_api.services.ingestion import process_ingestion_job
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NORMALIZED_PAYLOAD = b"canonical-image-png"
NORMALIZED_SHA256 = sha256(NORMALIZED_PAYLOAD).hexdigest()
SOURCE_PAYLOAD = b"immutable-source-image"
SOURCE_SHA256 = sha256(SOURCE_PAYLOAD).hexdigest()


class StaticImageAdapter:
    asset_kind = "image"

    def ingest(
        self,
        db: Session,
        *,
        asset: Asset,
        payload: bytes,
        processing_generation: int,
        config_snapshot: Mapping[str, object],
        created_at: datetime,
    ) -> IngestionResult:
        del payload, config_snapshot
        result = ImageNormalizationResult(
            payload=NORMALIZED_PAYLOAD,
            content_sha256=NORMALIZED_SHA256,
            width_pixels=8,
            height_pixels=12,
            orientation_applied=True,
        )
        object_key = build_image_oriented_object_key(asset, processing_generation)
        persist_image_orientation(
            db,
            asset=asset,
            result=result,
            object_key=object_key,
            processing_generation=processing_generation,
            created_at=created_at,
        )
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=object_key,
                    payload=result.payload,
                    content_type=IMAGE_ORIENTED_CONTENT_TYPE,
                    content_sha256=result.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_image_content(db, asset.id)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _create_image_asset(db: Session, *, status: str = "parsing") -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id="workspace-image",
        created_by_user_id="user-image",
        asset_kind="image",
        title="Orientation fixture",
        source_filename="orientation-6.jpg",
        object_key="workspaces/workspace-image/assets/source/original.jpg",
        mime_type="image/jpeg",
        byte_size=len(SOURCE_PAYLOAD),
        source_sha256=SOURCE_SHA256,
        status=status,
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def _create_job(db: Session, asset: Asset, *, job_type: str = "ingest") -> IngestionJob:
    now = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        job_type=job_type,
        status="running",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=asset.created_by_user_id,
        queued_at=now,
        started_at=now,
        created_at=now,
    )
    db.add(job)
    db.flush()
    asset.latest_ingestion_job_id = job.id
    db.commit()
    return job


def test_generated_image_object_and_geometry_commit_together(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    job = _create_job(db_session, asset)
    uploads: list[tuple[str, bytes, str]] = []
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: SOURCE_PAYLOAD,
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.upload_bytes",
        lambda key, payload, content_type: uploads.append((key, payload, content_type)),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda _key: None,
    )

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    representation = db_session.scalar(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    )
    assert representation is not None
    geometry = db_session.get(ImageRepresentationGeometry, representation.id)
    assert geometry is not None
    assert (geometry.width_pixels, geometry.height_pixels, geometry.orientation_applied) == (
        8,
        12,
        True,
    )
    assert representation.content_sha256 == NORMALIZED_SHA256
    assert uploads == [
        (representation.object_key, NORMALIZED_PAYLOAD, IMAGE_ORIENTED_CONTENT_TYPE)
    ]
    assert asset.object_key == "workspaces/workspace-image/assets/source/original.jpg"
    assert asset.source_sha256 == SOURCE_SHA256
    assert asset.status == "chunked"
    assert job.status == "succeeded"


def test_source_object_integrity_mismatch_fails_initial_and_retry(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    first_job = _create_job(db_session, asset)
    adapter_calls = 0

    class CountingImageAdapter(StaticImageAdapter):
        def ingest(self, db: Session, **kwargs: object) -> IngestionResult:
            nonlocal adapter_calls
            adapter_calls += 1
            return super().ingest(db, **kwargs)

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: b"tampered-source-image",
    )
    adapters = IngestionAdapterRegistry((CountingImageAdapter(),))

    process_ingestion_job(db_session, first_job.id, ingestion_adapters=adapters)

    retry_job = _create_job(db_session, asset)
    retry_job.attempt_count = 2
    retry_job.config_snapshot = {"source": "retry"}
    db_session.commit()
    process_ingestion_job(db_session, retry_job.id, ingestion_adapters=adapters)

    db_session.expire_all()
    refreshed_asset = db_session.get(Asset, asset.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "failed"
    assert refreshed_asset.current_processing_generation == 1
    assert refreshed_asset.byte_size == len(SOURCE_PAYLOAD)
    assert refreshed_asset.source_sha256 == SOURCE_SHA256
    assert adapter_calls == 0
    assert first_job.status == "failed"
    assert retry_job.status == "failed"
    assert first_job.error_code == "source_object_integrity_mismatch"
    assert retry_job.error_code == "source_object_integrity_mismatch"
    assert db_session.scalars(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    ).all() == []
    assert db_session.scalars(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    ).all() == []


def test_generated_object_upload_failure_rolls_back_image_rows(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    job = _create_job(db_session, asset)
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: SOURCE_PAYLOAD,
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.upload_bytes",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda _key: None,
    )

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert db_session.scalars(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    ).all() == []
    assert db_session.scalars(
        select(ImageRepresentationGeometry).where(
            ImageRepresentationGeometry.asset_id == asset.id
        )
    ).all() == []
    assert asset.status == "failed"
    assert job.status == "failed"


def test_commit_failure_deletes_uploaded_generated_object(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    job = _create_job(db_session, asset)
    stored: set[str] = set()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: SOURCE_PAYLOAD,
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.upload_bytes",
        lambda key, _payload, _content_type: stored.add(key),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda key: stored.discard(key),
    )
    original_commit = db_session.commit
    commit_calls = 0

    def fail_first_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise RuntimeError("database commit failed")
        original_commit()

    monkeypatch.setattr(db_session, "commit", fail_first_commit)

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert stored == set()
    assert db_session.scalars(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    ).all() == []
    assert asset.status == "failed"
    assert job.status == "failed"


def test_delete_cleanup_removes_original_and_all_image_representations(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session, status="deleting")
    now = datetime.now(UTC)
    for generation in (1, 2):
        result = ImageNormalizationResult(
            payload=NORMALIZED_PAYLOAD,
            content_sha256=NORMALIZED_SHA256,
            width_pixels=8,
            height_pixels=12,
            orientation_applied=True,
        )
        persist_image_orientation(
            db_session,
            asset=asset,
            result=result,
            object_key=build_image_oriented_object_key(asset, generation),
            processing_generation=generation,
            created_at=now,
        )
    job = _create_job(db_session, asset, job_type="delete_cleanup")
    deleted: list[str] = []
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda key: deleted.append(key),
    )
    swept_prefixes: list[str] = []
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_objects_with_prefix",
        lambda prefix: swept_prefixes.append(prefix),
    )

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert set(deleted) == {
        asset.object_key,
        build_image_oriented_object_key(asset, 1),
        build_image_oriented_object_key(asset, 2),
    }
    assert swept_prefixes == [f"workspaces/{asset.workspace_id}/assets/{asset.id}/"]
    assert db_session.scalars(
        select(ImageRepresentationGeometry).where(
            ImageRepresentationGeometry.asset_id == asset.id
        )
    ).all() == []
    assert asset.status == "deleted"
    assert asset.deleted_at is not None
    assert job.status == "succeeded"


def test_ambiguous_upload_success_is_compensated(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    job = _create_job(db_session, asset)
    stored: set[str] = set()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: SOURCE_PAYLOAD,
    )

    def write_then_raise(key: str, _payload: bytes, _content_type: str) -> None:
        stored.add(key)
        raise RuntimeError("response lost after object commit")

    monkeypatch.setattr("ai_pdf_api.services.ingestion.upload_bytes", write_then_raise)
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda key: stored.discard(key),
    )

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert stored == set()
    assert job.status == "failed"
    assert job.error_code == "ingestion_failed"
    assert db_session.scalars(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    ).all() == []


def test_failed_compensation_is_durable_and_ingestion_retry_cleans_it(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session)
    failed_job = _create_job(db_session, asset)
    stored: set[str] = set()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _key: SOURCE_PAYLOAD,
    )

    def write_then_raise(key: str, _payload: bytes, _content_type: str) -> None:
        stored.add(key)
        raise RuntimeError("response lost after object commit")

    def fail_when_object_exists(key: str) -> None:
        if key in stored:
            raise RuntimeError("object storage cleanup unavailable")

    monkeypatch.setattr("ai_pdf_api.services.ingestion.upload_bytes", write_then_raise)
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        fail_when_object_exists,
    )

    process_ingestion_job(
        db_session,
        failed_job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    expected_key = build_image_oriented_object_key(asset, 1)
    assert stored == {expected_key}
    assert failed_job.status == "failed"
    assert failed_job.error_code == "generated_object_cleanup_failed"
    assert failed_job.error_message is not None and expected_key in failed_job.error_message

    retry_job = _create_job(db_session, asset)
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda key: stored.discard(key),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.upload_bytes",
        lambda key, _payload, _content_type: stored.add(key),
    )

    process_ingestion_job(
        db_session,
        retry_job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert stored == {expected_key}
    assert retry_job.status == "succeeded"
    assert asset.status == "chunked"
    representation = db_session.scalar(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    )
    assert representation is not None and representation.object_key == expected_key


def test_delete_cleanup_sweeps_untracked_generated_objects(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_image_asset(db_session, status="deleting")
    job = _create_job(db_session, asset, job_type="delete_cleanup")
    orphan_key = build_image_oriented_object_key(asset, 1)
    stored = {asset.object_key, orphan_key}
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda key: stored.discard(key),
    )

    def sweep(prefix: str) -> None:
        stored.difference_update(key for key in tuple(stored) if key.startswith(prefix))

    monkeypatch.setattr("ai_pdf_api.services.ingestion.delete_objects_with_prefix", sweep)

    process_ingestion_job(
        db_session,
        job.id,
        ingestion_adapters=IngestionAdapterRegistry((StaticImageAdapter(),)),
    )

    assert stored == set()
    assert asset.status == "deleted"
    assert job.status == "succeeded"


def test_image_detail_selects_only_current_processing_generation(db_session: Session) -> None:
    now = datetime.now(UTC)
    user = User(
        email="image-detail@example.com",
        name="Image Detail",
        password_hash="hash",
        avatar_url="https://example.com/avatar.png",
    )
    db_session.add(user)
    db_session.flush()
    workspace = Workspace(
        name="Images",
        description=None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner")
    )
    asset = Asset(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="image",
        title="Current generation",
        source_filename="image.jpg",
        object_key="source/image.jpg",
        mime_type="image/jpeg",
        byte_size=128,
        status="chunked",
        current_processing_generation=2,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(asset)
    db_session.flush()
    for generation, dimensions in ((1, (1200, 800)), (2, (800, 1200))):
        persist_image_orientation(
            db_session,
            asset=asset,
            result=ImageNormalizationResult(
                payload=NORMALIZED_PAYLOAD,
                content_sha256=NORMALIZED_SHA256,
                width_pixels=dimensions[0],
                height_pixels=dimensions[1],
                orientation_applied=True,
            ),
            object_key=build_image_oriented_object_key(asset, generation),
            processing_generation=generation,
            created_at=now,
        )
    db_session.commit()

    response = get_asset_detail(
        workspace.id,
        asset.id,
        user_id=user.id,
        db=db_session,
    )

    assert response.detail.kind == "image"
    assert response.detail.widthPixels == 800
    assert response.detail.heightPixels == 1200
    assert response.detail.orientationApplied is True


def test_image_analysis_fails_closed_when_transient_geometry_differs_from_persisted(
    db_session: Session,
) -> None:
    asset = _create_image_asset(db_session)
    now = datetime.now(UTC)
    normalized = ImageNormalizationResult(
        payload=NORMALIZED_PAYLOAD,
        content_sha256=NORMALIZED_SHA256,
        width_pixels=8,
        height_pixels=12,
        orientation_applied=True,
    )
    representation = persist_image_orientation(
        db_session,
        asset=asset,
        result=normalized,
        object_key=build_image_oriented_object_key(asset, 1),
        processing_generation=1,
        created_at=now,
    )

    with pytest.raises(IngestionError) as captured:
        persist_image_analysis(
            db_session,
            asset=asset,
            oriented_representation=representation,
            geometry=ImageNormalizationResult(
                payload=NORMALIZED_PAYLOAD,
                content_sha256=NORMALIZED_SHA256,
                width_pixels=12,
                height_pixels=8,
                orientation_applied=True,
            ),
            result=ImageAnalysisResult(
                ocr_regions=(
                    ImageOcrRegionResult(
                        text="OCR",
                        x=0.1,
                        y=0.2,
                        width=0.3,
                        height=0.1,
                        char_start=0,
                        char_end=3,
                    ),
                ),
                caption="Caption",
                caption_provider="test",
                caption_model="test",
                caption_version="test-v1",
            ),
            processing_generation=1,
            created_at=now,
        )

    assert captured.value.code == "image_geometry_mismatch"
