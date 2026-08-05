from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry, IngestionError
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    ImageLocatorDetail,
    ImageRepresentationGeometry,
    IngestionJob,
    SpatialLocatorRegion,
)
from ai_pdf_api.services.ingestion import process_ingestion_job
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_worker.image_ingestion import ImageIngestionAdapter, extract_image_text_with_ocr
from ai_pdf_worker.ocr import OcrRegionResult, OcrTextResult

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
IMAGE_FIXTURE = (
    REPOSITORY_ROOT
    / "docs"
    / "fixtures"
    / "evidence-contract"
    / "image-coordinate-fixture.png"
)


class StaticCaptionProvider:
    provider = "test-vision"
    model = "test-caption-model"
    version = "test-caption-v1"
    detail = "high"
    max_output_tokens = 320

    def caption(self, payload: bytes, *, content_type: str) -> str:
        assert payload.startswith(b"\x89PNG")
        assert content_type == "image/png"
        return "A chart shows latency falling after the third release."


class StaticEmbeddingProvider:
    provider = "test-embedding"
    model = "test-embedding-model"
    dimensions = 3
    version = "test-embedding-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), float(len(text)), 1.0] for index, text in enumerate(texts)]

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _caption_config() -> dict[str, str]:
    return {
        "imageCaptionProvider": StaticCaptionProvider.provider,
        "imageCaptionModel": StaticCaptionProvider.model,
        "imageCaptionVersion": StaticCaptionProvider.version,
        "imageCaptionDetail": StaticCaptionProvider.detail,
        "imageCaptionMaxOutputTokens": StaticCaptionProvider.max_output_tokens,
    }


def _job_config() -> dict[str, object]:
    return {
        **_caption_config(),
        "embeddingProvider": StaticEmbeddingProvider.provider,
        "embeddingModel": StaticEmbeddingProvider.model,
        "embeddingDimensions": StaticEmbeddingProvider.dimensions,
        "embeddingVersion": StaticEmbeddingProvider.version,
    }


def _fixture_ocr(_payload: bytes) -> OcrTextResult:
    return OcrTextResult(
        text="Image Evidence Fixture\nObservation",
        regions=(
            OcrRegionResult(
                text="Image Evidence Fixture",
                x=0.06,
                y=0.08,
                width=0.27,
                height=0.04,
                char_start=0,
                char_end=22,
            ),
            OcrRegionResult(
                text="Observation",
                x=0.70,
                y=0.31,
                width=0.11,
                height=0.04,
                char_start=23,
                char_end=34,
            ),
        ),
    )


def test_image_ocr_fixture_returns_normalized_regions_in_oriented_space() -> None:
    recognized = extract_image_text_with_ocr(IMAGE_FIXTURE.read_bytes())

    assert "Image Evidence Fixture" in recognized.text
    assert "Observation" in recognized.text
    assert "caption together." in recognized.text
    assert len(recognized.regions) == 8
    for region in recognized.regions:
        assert 0 <= region.x < 1
        assert 0 <= region.y < 1
        assert region.width > 0
        assert region.height > 0
        assert region.x + region.width <= 1
        assert region.y + region.height <= 1


def test_dormant_image_adapter_persists_immutable_generation_outputs() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-fixture",
                created_by_user_id="user-image-fixture",
                asset_kind="image",
                title="Image evidence fixture",
                source_filename=IMAGE_FIXTURE.name,
                object_key="workspaces/workspace-image-fixture/assets/source/original.png",
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=StaticCaptionProvider(),
                ocr_extractor=_fixture_ocr,
            )

            first = adapter.ingest(
                db,
                asset=asset,
                payload=source,
                processing_generation=1,
                config_snapshot=_caption_config(),
                created_at=now,
            )
            second = adapter.ingest(
                db,
                asset=asset,
                payload=source,
                processing_generation=2,
                config_snapshot=_caption_config(),
                created_at=now,
            )
            db.flush()

            representations = db.scalars(
                select(AssetRepresentation)
                .where(AssetRepresentation.asset_id == asset.id)
                .order_by(AssetRepresentation.processing_generation)
            ).all()
            geometries = db.scalars(
                select(ImageRepresentationGeometry).where(
                    ImageRepresentationGeometry.asset_id == asset.id
                )
            ).all()

            oriented = [
                item for item in representations if item.representation_kind == "image_oriented"
            ]
            assert [item.processing_generation for item in oriented] == [1, 2]
            assert [item.object_key for item in oriented] == [
                first.generated_objects[0].object_key,
                second.generated_objects[0].object_key,
            ]
            assert first.generated_objects[0].object_key.endswith(
                "/representations/1/image-oriented.png"
            )
            assert second.generated_objects[0].object_key.endswith(
                "/representations/2/image-oriented.png"
            )
            assert first.generated_objects[0].content_sha256 == oriented[0].content_sha256
            assert second.generated_objects[0].content_sha256 == oriented[1].content_sha256
            assert len(geometries) == 2
            assert {
                (item.width_pixels, item.height_pixels, item.orientation_applied)
                for item in geometries
            } == {(1200, 800, True)}
            assert asset.object_key.endswith("/original.png")
            assert asset.source_sha256 == sha256(source).hexdigest()
            units = db.scalars(
                select(ContentUnit)
                .where(ContentUnit.asset_id == asset.id)
                .order_by(ContentUnit.unit_kind, ContentUnit.unit_order)
            ).all()
            assert [(unit.unit_kind, unit.text_content) for unit in units] == [
                ("image_caption", "A chart shows latency falling after the third release."),
                ("image_ocr_region", "Image Evidence Fixture"),
                ("image_ocr_region", "Observation"),
            ]
            assert [
                (unit.char_start, unit.char_end)
                for unit in units
            ] == [(None, None), (None, None), (None, None)]
            locators = db.scalars(
                select(EvidenceLocator).where(EvidenceLocator.asset_id == asset.id)
            ).all()
            assert len(locators) == 6
            assert {locator.locator_kind for locator in locators} == {"image_region"}
            evidence_representations = {
                item.id: item
                for item in representations
                if item.representation_kind in {"image_ocr", "image_caption"}
            }
            assert {
                locator.representation_id_snapshot for locator in locators
            } == set(evidence_representations)
            assert {
                evidence_representations[locator.representation_id_snapshot].processing_generation
                for locator in locators
            } == {1, 2}
            for locator in locators:
                detail = db.get(ImageLocatorDetail, locator.id)
                assert detail is not None
                assert (detail.width_pixels, detail.height_pixels) == (1200, 800)
                assert detail.orientation_applied is True
                assert db.scalars(
                    select(SpatialLocatorRegion).where(
                        SpatialLocatorRegion.locator_id == locator.id
                    )
                ).all()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_dormant_image_job_creates_region_units_and_text_embeddings(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    stored: dict[str, bytes] = {}
    try:
        with Session(engine, expire_on_commit=False) as db:
            asset = Asset(
                workspace_id="workspace-image-job",
                created_by_user_id="user-image-job",
                asset_kind="image",
                title="Image evidence fixture",
                source_filename=IMAGE_FIXTURE.name,
                object_key="workspaces/workspace-image-job/assets/source/original.png",
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            job = IngestionJob(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                job_type="ingest",
                status="running",
                attempt_count=1,
                config_snapshot=_job_config(),
                requested_by_user_id=asset.created_by_user_id,
                queued_at=now,
                started_at=now,
                created_at=now,
            )
            db.add(job)
            db.flush()
            asset.latest_ingestion_job_id = job.id
            db.commit()

            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.download_bytes",
                lambda key: source if key == asset.object_key else b"",
            )
            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.upload_bytes",
                lambda key, payload, _content_type: stored.__setitem__(key, payload),
            )
            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.delete_object_if_exists",
                lambda key: stored.pop(key, None),
            )
            adapter = ImageIngestionAdapter(
                caption_provider=StaticCaptionProvider(),
                ocr_extractor=_fixture_ocr,
            )

            process_ingestion_job(
                db,
                job.id,
                ingestion_adapters=IngestionAdapterRegistry((adapter,)),
                embedding_provider=StaticEmbeddingProvider(),
            )

            assert asset.status == "ready"
            assert asset.current_processing_generation == 1
            assert job.status == "succeeded"
            units = db.scalars(
                select(ContentUnit)
                .where(ContentUnit.asset_id == asset.id)
                .order_by(ContentUnit.unit_kind, ContentUnit.unit_order)
            ).all()
            embeddings = db.scalars(select(ContentUnitEmbedding)).all()
            assert len(units) == 3
            assert len(embeddings) == 3
            assert {embedding.content_unit_id for embedding in embeddings} == {
                unit.id for unit in units
            }
            oriented = db.scalar(
                select(AssetRepresentation).where(
                    AssetRepresentation.asset_id == asset.id,
                    AssetRepresentation.representation_kind == "image_oriented",
                )
            )
            assert oriented is not None
            assert oriented.object_key is not None
            assert set(stored) == {oriented.object_key}
            assert sha256(stored[oriented.object_key]).hexdigest() == oriented.content_sha256
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_image_adapter_fails_before_persistence_on_caption_config_drift() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-drift",
                created_by_user_id="user-image-drift",
                asset_kind="image",
                title="Image evidence fixture",
                source_filename=IMAGE_FIXTURE.name,
                object_key="workspaces/workspace-image-drift/assets/source/original.png",
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=StaticCaptionProvider(),
                ocr_extractor=_fixture_ocr,
            )

            with pytest.raises(ModelProviderError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=source,
                    processing_generation=1,
                    config_snapshot={**_caption_config(), "imageCaptionModel": "drifted"},
                    created_at=now,
                )

            assert captured.value.code == "image_caption_configuration_mismatch"
            assert db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            ).all() == []
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_image_adapter_ingest_fails_closed_on_mismatched_caption_profile_fingerprint() -> None:
    """Non-empty snapshot fingerprint mismatch fails closed before image persistence."""

    class FingerprintedCaptionProvider(StaticCaptionProvider):
        config_fingerprint = "b" * 64

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-fingerprint-mismatch",
                created_by_user_id="user-image-fingerprint-mismatch",
                asset_kind="image",
                title="Image fingerprint mismatch",
                source_filename=IMAGE_FIXTURE.name,
                object_key=(
                    "workspaces/workspace-image-fingerprint-mismatch/assets/source/original.png"
                ),
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=FingerprintedCaptionProvider(),
                ocr_extractor=_fixture_ocr,
            )

            with pytest.raises(ModelProviderError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=source,
                    processing_generation=1,
                    config_snapshot={
                        **_caption_config(),
                        "imageCaptionProfileFingerprint": "a" * 64,
                    },
                    created_at=now,
                )

            assert captured.value.code == "image_caption_configuration_mismatch"
            assert db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            ).all() == []
            assert db.scalars(
                select(ContentUnit).where(ContentUnit.asset_id == asset.id)
            ).all() == []
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_image_adapter_rejects_missing_or_empty_caption_profile_fingerprint() -> None:
    from ai_pdf_api.services.providers import ModelProviderError
    from ai_pdf_worker.image_ingestion import _validate_caption_config

    class Provider:
        provider = "openai"
        model = "gpt-5.5"
        version = "image-caption-v1"
        detail = "high"
        max_output_tokens = 320
        config_fingerprint = ""

    snapshot = {
        "imageCaptionProvider": "openai",
        "imageCaptionModel": "gpt-5.5",
        "imageCaptionVersion": "image-caption-v1",
        "imageCaptionDetail": "high",
        "imageCaptionMaxOutputTokens": 320,
        "imageCaptionProfileFingerprint": "a" * 64,
    }
    with pytest.raises(ModelProviderError) as captured:
        _validate_caption_config(snapshot, Provider())
    assert captured.value.code == "image_caption_configuration_mismatch"

    class MatchingProvider(Provider):
        config_fingerprint = "a" * 64

    _validate_caption_config(snapshot, MatchingProvider())

    legacy = {
        "imageCaptionProvider": "openai",
        "imageCaptionModel": "gpt-5.5",
        "imageCaptionVersion": "image-caption-v1",
        "imageCaptionDetail": "high",
        "imageCaptionMaxOutputTokens": 320,
    }
    _validate_caption_config(legacy, Provider())


def test_image_adapter_required_caption_failure_preserves_not_configured_code() -> None:
    """Caption is required; stable image_caption_provider_not_configured must surface as-is."""

    from ai_pdf_api.services.providers import ModelProviderError

    class NotConfiguredCaptionProvider(StaticCaptionProvider):
        def caption(self, payload: bytes, *, content_type: str) -> str:
            del payload, content_type
            raise ModelProviderError(
                "image_caption_provider_not_configured",
                "OpenAI image caption API key is not configured.",
            )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-not-configured",
                created_by_user_id="user-image-not-configured",
                asset_kind="image",
                title="Image caption not configured",
                source_filename=IMAGE_FIXTURE.name,
                object_key=(
                    "workspaces/workspace-image-not-configured/assets/source/original.png"
                ),
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=NotConfiguredCaptionProvider(),
                ocr_extractor=_fixture_ocr,
            )
            with pytest.raises(ModelProviderError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=source,
                    processing_generation=1,
                    config_snapshot=_caption_config(),
                    created_at=now,
                )
            assert captured.value.code == "image_caption_provider_not_configured"
            assert db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            ).all() == []
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_image_adapter_reports_ocr_failure_before_caption_or_persistence() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    caption_calls = 0

    class CountingCaptionProvider(StaticCaptionProvider):
        def caption(self, payload: bytes, *, content_type: str) -> str:
            nonlocal caption_calls
            caption_calls += 1
            return super().caption(payload, content_type=content_type)

    def fail_ocr(_payload: bytes) -> OcrTextResult:
        raise RuntimeError("ocr backend failed")

    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-ocr-failure",
                created_by_user_id="user-image-ocr-failure",
                asset_kind="image",
                title="Image evidence fixture",
                source_filename=IMAGE_FIXTURE.name,
                object_key="workspaces/workspace-image-ocr-failure/assets/source/original.png",
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=CountingCaptionProvider(),
                ocr_extractor=fail_ocr,
            )

            with pytest.raises(IngestionError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=source,
                    processing_generation=1,
                    config_snapshot=_caption_config(),
                    created_at=now,
                )

            assert captured.value.code == "image_ocr_failed"
            assert caption_calls == 0
            assert db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            ).all() == []
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_image_without_ocr_text_persists_caption_as_full_image_evidence() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    source = IMAGE_FIXTURE.read_bytes()
    try:
        with Session(engine) as db:
            asset = Asset(
                workspace_id="workspace-image-caption-only",
                created_by_user_id="user-image-caption-only",
                asset_kind="image",
                title="Caption-only image",
                source_filename=IMAGE_FIXTURE.name,
                object_key="workspaces/workspace-image-caption-only/assets/source/original.png",
                mime_type="image/png",
                byte_size=len(source),
                source_sha256=sha256(source).hexdigest(),
                status="parsing",
                current_processing_generation=1,
                current_index_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            db.flush()
            adapter = ImageIngestionAdapter(
                caption_provider=StaticCaptionProvider(),
                ocr_extractor=lambda _payload: OcrTextResult(text="", regions=()),
            )

            adapter.ingest(
                db,
                asset=asset,
                payload=source,
                processing_generation=1,
                config_snapshot=_caption_config(),
                created_at=now,
            )
            db.flush()

            unit = db.scalar(select(ContentUnit).where(ContentUnit.asset_id == asset.id))
            assert unit is not None
            assert unit.unit_kind == "image_caption"
            regions = db.scalars(
                select(SpatialLocatorRegion).where(
                    SpatialLocatorRegion.locator_id == unit.source_locator_id
                )
            ).all()
            assert [(region.x, region.y, region.width, region.height) for region in regions] == [
                (0.0, 0.0, 1.0, 1.0)
            ]
            assert db.scalars(
                select(AssetRepresentation).where(
                    AssetRepresentation.asset_id == asset.id,
                    AssetRepresentation.representation_kind == "image_ocr",
                )
            ).all() == []
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
