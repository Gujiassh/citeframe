"""Audio ingestion adapter. Not production-enabled until S0 catalog/registry handoff.

ASR must be configured before any audio representation or content-unit persist.
Never invents transcripts when ASR is missing or returns empty segments.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Protocol
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.asr_transcription import (
    AsrTranscriptionProvider,
    TranscriptionResult,
    transcribe_audio_payload,
)
from ai_pdf_api.modalities.audio import (
    AUDIO_ASR_ADAPTER_VERSION,
    AUDIO_FORMAT,
    AUDIO_MIME_TYPES,
    AUDIO_NORMALIZATION_VERSION,
    AUDIO_PARSER_VERSION,
    stable_audio_segment_id,
    validate_audio_mime_type,
)
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    AudioLocatorDetail,
    AudioNormalizedContent,
    AudioTranscriptSegment,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
)
from ai_pdf_api.services.capability_errors import (
    ASR_SEGMENT_CONTRACT_CODE,
    require_configured_asr_profile,
)
from ai_pdf_api.services.capabilities import asr_profile_snapshot_fields
from ai_pdf_api.services.providers import ModelProviderError

NORMALIZED_CONTENT_TYPE = "application/json; charset=utf-8"

__all__ = [
    "AudioIngestionAdapter",
    "delete_audio_content",
    "replace_audio_content",
]


class AudioTranscriber(Protocol):
    def __call__(
        self,
        payload: bytes,
        *,
        mime_type: str,
        filename: str,
    ) -> TranscriptionResult: ...


def build_audio_normalized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/audio-normalized.json"
    )


def replace_audio_content(
    db: Session,
    *,
    asset: Asset,
    payload: bytes,
    transcription: TranscriptionResult,
    processing_generation: int,
    created_at: datetime,
    normalized_object_key: str,
    mime_type: str,
) -> None:
    if asset.asset_kind != "audio":
        raise IngestionError(
            "audio_asset_kind_invalid",
            "Audio adapter received a non-audio asset.",
        )
    if not transcription.segments:
        raise IngestionError(
            ASR_SEGMENT_CONTRACT_CODE,
            "ASR returned no transcript segments to persist.",
        )
    _assert_generation_available(
        db,
        asset_id=asset.id,
        processing_generation=processing_generation,
    )

    source_sha256 = sha256(payload).hexdigest()
    source_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="audio_source",
        processing_generation=processing_generation,
        generator_provider="audio",
        generator_version=AUDIO_PARSER_VERSION,
        object_key=asset.object_key,
        content_sha256=source_sha256,
        created_at=created_at,
    )
    db.add(source_representation)

    normalized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="audio_normalized",
        processing_generation=processing_generation,
        generator_provider="asr",
        generator_version=transcription.adapter_version or AUDIO_ASR_ADAPTER_VERSION,
        object_key=normalized_object_key,
        content_sha256=transcription.content_sha256,
        created_at=created_at,
    )
    db.add(normalized_representation)
    db.flush()

    db.add(
        AudioNormalizedContent(
            representation_id=normalized_representation.id,
            format=AUDIO_FORMAT,
            parser_version=AUDIO_PARSER_VERSION,
            normalization_version=AUDIO_NORMALIZATION_VERSION,
            asr_adapter_version=transcription.adapter_version or AUDIO_ASR_ADAPTER_VERSION,
            mime_type=mime_type,
            duration_ms=transcription.duration_ms,
            content_sha256=transcription.content_sha256,
            segment_count=len(transcription.segments),
            transcript_text=transcription.full_text,
        )
    )

    for order, segment in enumerate(transcription.segments):
        segment_id = stable_audio_segment_id(
            source_sha256=source_sha256,
            parser_version=AUDIO_PARSER_VERSION,
            asr_adapter_version=transcription.adapter_version or AUDIO_ASR_ADAPTER_VERSION,
            segment_order=order,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            text_sha256_value=segment.text_sha256,
        )
        segment_row = AudioTranscriptSegment(
            id=str(uuid4()),
            representation_id=normalized_representation.id,
            segment_id=segment_id,
            segment_order=order,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            speaker=segment.speaker,
            text_sha256=segment.text_sha256,
            text_content=segment.text,
            normalization_version=AUDIO_NORMALIZATION_VERSION,
        )
        db.add(segment_row)
        db.flush()

        locator = _persist_audio_locator(
            db,
            asset=asset,
            representation=normalized_representation,
            processing_generation=processing_generation,
            segment_id=segment_id,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            text_sha256_value=segment.text_sha256,
            created_at=created_at,
        )
        db.add(
            ContentUnit(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                representation_id=normalized_representation.id,
                source_locator_id=locator.id,
                unit_kind="audio_transcript_segment",
                unit_order=order,
                text_content=segment.text,
                token_count=estimate_token_count(segment.text),
                char_start=None,
                char_end=None,
                index_version=asset.current_index_version,
                created_at=created_at,
            )
        )
    db.flush()


def delete_audio_content(db: Session, asset_id: str) -> None:
    db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset_id))
    db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset_id))


class AudioIngestionAdapter:
    asset_kind = "audio"

    def __init__(
        self,
        *,
        transcriber: AudioTranscriber | None = None,
        transcription_provider: AsrTranscriptionProvider | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._transcription_provider = transcription_provider

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
        # Fail closed before any audio representation or content-unit persist.
        try:
            profile = require_configured_asr_profile()
        except ModelProviderError as error:
            raise IngestionError(error.code, error.message) from error

        _validate_audio_config(config_snapshot, profile)
        try:
            mime_type = validate_audio_mime_type(asset.mime_type)
        except ValueError as error:
            raise IngestionError("asset_mime_mismatch", str(error)) from error
        if mime_type not in AUDIO_MIME_TYPES:
            raise IngestionError(
                "asset_mime_mismatch",
                f"Audio adapter only accepts {sorted(AUDIO_MIME_TYPES)}.",
            )
        if not payload:
            raise IngestionError("audio_payload_empty", "Audio upload body is empty.")

        source_sha256 = sha256(payload).hexdigest()
        if asset.source_sha256 is not None and asset.source_sha256.lower() != source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "Audio source SHA-256 does not match the asset record.",
            )

        filename = asset.source_filename or f"audio{ _extension_for_mime(mime_type) }"
        try:
            transcription = self._run_transcription(
                payload,
                mime_type=mime_type,
                filename=filename,
            )
        except ModelProviderError as error:
            raise IngestionError(error.code, error.message) from error

        normalized_key = build_audio_normalized_object_key(asset, processing_generation)
        replace_audio_content(
            db,
            asset=asset,
            payload=payload,
            transcription=transcription,
            processing_generation=processing_generation,
            created_at=created_at,
            normalized_object_key=normalized_key,
            mime_type=mime_type,
        )
        import json

        body = json.dumps(
            {
                "format": AUDIO_FORMAT,
                "parserVersion": AUDIO_PARSER_VERSION,
                "normalizationVersion": AUDIO_NORMALIZATION_VERSION,
                "asrAdapterVersion": transcription.adapter_version,
                "durationMs": transcription.duration_ms,
                "segmentCount": len(transcription.segments),
                "transcriptText": transcription.full_text,
                "contentSha256": transcription.content_sha256,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=normalized_key,
                    payload=body,
                    content_type=NORMALIZED_CONTENT_TYPE,
                    content_sha256=transcription.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_audio_content(db, asset.id)

    def _run_transcription(
        self,
        payload: bytes,
        *,
        mime_type: str,
        filename: str,
    ) -> TranscriptionResult:
        if self._transcriber is not None:
            return self._transcriber(payload, mime_type=mime_type, filename=filename)
        if self._transcription_provider is not None:
            return self._transcription_provider.transcribe(
                payload, mime_type=mime_type, filename=filename
            )
        return transcribe_audio_payload(payload, mime_type=mime_type, filename=filename)


def _extension_for_mime(mime_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
    }.get(mime_type, ".bin")


def _validate_audio_config(snapshot: Mapping[str, object], profile) -> None:
    expected = {
        "audioFormat": AUDIO_FORMAT,
        "audioParserVersion": AUDIO_PARSER_VERSION,
        "audioNormalizationVersion": AUDIO_NORMALIZATION_VERSION,
        "asrAdapterVersion": AUDIO_ASR_ADAPTER_VERSION,
    }
    for key, value in expected.items():
        if key not in snapshot or snapshot[key] != value:
            raise IngestionError(
                "audio_configuration_mismatch",
                "Audio parser/ASR configuration does not match the job snapshot.",
            )
    # Optional frozen ASR fingerprint when present in snapshot.
    from ai_pdf_api.services.capabilities import require_matching_snapshot_fingerprint

    snapshot_fields = asr_profile_snapshot_fields(profile)
    require_matching_snapshot_fingerprint(
        snapshot,
        field_name="asrProfileFingerprint",
        actual_fingerprint=snapshot_fields.get("asrProfileFingerprint"),
        error_code="audio_configuration_mismatch",
        error_message="Audio ASR profile fingerprint does not match the job snapshot.",
        error_cls=IngestionError,
    )


def _assert_generation_available(
    db: Session,
    *,
    asset_id: str,
    processing_generation: int,
) -> None:
    existing = db.scalar(
        select(AssetRepresentation.id).where(
            AssetRepresentation.asset_id == asset_id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind.in_(
                ("audio_source", "audio_normalized")
            ),
        )
    )
    if existing is not None:
        raise IngestionError(
            "audio_generation_already_exists",
            "Audio processing generation is already materialized and immutable.",
        )


def _persist_audio_locator(
    db: Session,
    *,
    asset: Asset,
    representation: AssetRepresentation,
    processing_generation: int,
    segment_id: str,
    start_ms: int,
    end_ms: int,
    text_sha256_value: str,
    created_at: datetime,
) -> EvidenceLocator:
    if (
        representation.asset_id != asset.id
        or representation.processing_generation != processing_generation
        or representation.representation_kind != "audio_normalized"
    ):
        raise IngestionError(
            "audio_evidence_representation_invalid",
            "Audio locator requires the normalized representation for this generation.",
        )
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="audio_range",
        locator_version=1,
        processing_generation_snapshot=processing_generation,
        representation_id_snapshot=representation.id,
        created_at=created_at,
    )
    db.add(locator)
    db.flush()
    db.add(
        AudioLocatorDetail(
            locator_id=locator.id,
            segment_id=segment_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text_sha256=text_sha256_value,
            normalization_version=AUDIO_NORMALIZATION_VERSION,
        )
    )
    return locator
