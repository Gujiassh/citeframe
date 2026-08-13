from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.asr_transcription import TranscriptSegment, TranscriptionResult
from ai_pdf_api.modalities.audio import (
    AUDIO_ASR_ADAPTER_VERSION,
    AUDIO_FORMAT,
    AUDIO_NORMALIZATION_VERSION,
    AUDIO_PARSER_VERSION,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import IngestionError
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    AudioLocatorDetail,
    AudioNormalizedContent,
    AudioTranscriptSegment,
    ContentUnit,
    EvidenceLocator,
)
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_worker.audio_ingestion import AudioIngestionAdapter


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _wav_bytes() -> bytes:
    return b"RIFF" + (100).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 80


def _audio_config() -> dict[str, object]:
    return {
        "audioFormat": AUDIO_FORMAT,
        "audioParserVersion": AUDIO_PARSER_VERSION,
        "audioNormalizationVersion": AUDIO_NORMALIZATION_VERSION,
        "asrAdapterVersion": AUDIO_ASR_ADAPTER_VERSION,
        "embeddingProvider": "test",
        "embeddingModel": "test",
        "embeddingDimensions": 3,
        "embeddingVersion": "test-v1",
    }


def _make_asset(db: Session, *, payload: bytes) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id="workspace-audio",
        created_by_user_id="user-audio",
        asset_kind="audio",
        title="Clip",
        source_filename="clip.wav",
        object_key="workspaces/workspace-audio/assets/source/original.wav",
        mime_type="audio/wav",
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status="processing",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def test_audio_adapter_fails_closed_without_asr(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    payload = _wav_bytes()

    def boom() -> None:
        raise ModelProviderError("asr_not_configured", "OpenAI ASR API key is not configured.")

    monkeypatch.setattr(
        "ai_pdf_worker.audio_ingestion.require_configured_asr_profile",
        boom,
    )

    with Session(engine) as db:
        asset = _make_asset(db, payload=payload)
        adapter = AudioIngestionAdapter()
        with pytest.raises(IngestionError) as exc:
            adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_audio_config(),
                created_at=datetime.now(UTC),
            )
        assert exc.value.code == "asr_not_configured"
        assert db.scalar(select(AssetRepresentation.id)) is None
        assert db.scalar(select(ContentUnit.id)) is None


def test_audio_adapter_persists_real_transcription_when_asr_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    payload = _wav_bytes()
    text = "hello from whisper"
    digest = text_sha256(text)

    class FakeProfile:
        configured = True
        provider = "openai"
        model = "whisper-1"
        model_version = "asr-v1"
        config_fingerprint = "fp"
        limits = {}

    monkeypatch.setattr(
        "ai_pdf_worker.audio_ingestion.require_configured_asr_profile",
        lambda: FakeProfile(),
    )
    monkeypatch.setattr(
        "ai_pdf_worker.audio_ingestion.asr_profile_snapshot_fields",
        lambda _p=None: {"asrProfileFingerprint": "fp"},
    )

    def fake_transcribe(payload_bytes: bytes, *, mime_type: str, filename: str) -> TranscriptionResult:
        assert mime_type == "audio/wav"
        assert payload_bytes == payload
        return TranscriptionResult(
            segments=(
                TranscriptSegment(
                    start_ms=0,
                    end_ms=1200,
                    text=text,
                    speaker=None,
                    text_sha256=digest,
                ),
            ),
            duration_ms=1200,
            full_text=text,
            content_sha256=digest,
            adapter_version=AUDIO_ASR_ADAPTER_VERSION,
            profile_snapshot={},
        )

    with Session(engine) as db:
        asset = _make_asset(db, payload=payload)
        adapter = AudioIngestionAdapter(transcriber=fake_transcribe)
        result = adapter.ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=1,
            config_snapshot=_audio_config(),
            created_at=datetime.now(UTC),
        )
        db.commit()
        assert len(result.generated_objects) == 1
        assert db.scalar(select(AudioNormalizedContent).limit(1)) is not None
        segments = list(db.scalars(select(AudioTranscriptSegment)))
        assert len(segments) == 1
        assert segments[0].text_content == text
        units = list(db.scalars(select(ContentUnit)))
        assert len(units) == 1
        assert units[0].unit_kind == "audio_transcript_segment"
        locators = list(db.scalars(select(EvidenceLocator)))
        assert len(locators) == 1
        assert locators[0].locator_kind == "audio_range"
        detail = db.get(AudioLocatorDetail, locators[0].id)
        assert detail is not None
        assert detail.start_ms == 0
        assert detail.end_ms == 1200


def test_audio_adapter_never_invents_empty_success(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    payload = _wav_bytes()

    class FakeProfile:
        configured = True
        provider = "openai"
        model = "whisper-1"
        model_version = "asr-v1"
        config_fingerprint = "fp"
        limits = {}

    monkeypatch.setattr(
        "ai_pdf_worker.audio_ingestion.require_configured_asr_profile",
        lambda: FakeProfile(),
    )
    monkeypatch.setattr(
        "ai_pdf_worker.audio_ingestion.asr_profile_snapshot_fields",
        lambda _p=None: {},
    )

    def empty_transcribe(*_a, **_k) -> TranscriptionResult:
        raise ModelProviderError(
            "asr_segment_contract_invalid",
            "ASR returned no non-empty transcript segments.",
        )

    with Session(engine) as db:
        asset = _make_asset(db, payload=payload)
        adapter = AudioIngestionAdapter(transcriber=empty_transcribe)
        with pytest.raises(IngestionError) as exc:
            adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_audio_config(),
                created_at=datetime.now(UTC),
            )
        assert exc.value.code == "asr_segment_contract_invalid"
        assert db.scalar(select(ContentUnit.id)) is None
