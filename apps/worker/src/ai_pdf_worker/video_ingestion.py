"""Video ingestion adapter. Not production-enabled until S0 catalog/registry handoff.

ASR must be configured before any video representation or content-unit persist.
Never invents transcripts when ASR is missing or returns empty segments.
Keyframes are deferred: never invent frames when extraction tooling is missing.
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
from ai_pdf_api.modalities.video import (
    VIDEO_ASR_ADAPTER_VERSION,
    VIDEO_FORMAT,
    VIDEO_KEYFRAME_VERSION,
    VIDEO_MIME_TYPES,
    VIDEO_NORMALIZATION_VERSION,
    VIDEO_PARSER_VERSION,
    stable_video_segment_id,
    validate_video_mime_type,
)
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    VideoLocatorDetail,
    VideoNormalizedContent,
    VideoTranscriptSegment,
)
from ai_pdf_api.services.capability_errors import (
    ASR_SEGMENT_CONTRACT_CODE,
    require_configured_asr_profile,
)
from ai_pdf_api.services.capabilities import asr_profile_snapshot_fields
from ai_pdf_api.services.providers import ModelProviderError

NORMALIZED_CONTENT_TYPE = "application/json; charset=utf-8"

__all__ = [
    "VideoIngestionAdapter",
    "delete_video_content",
    "replace_video_content",
]


class VideoTranscriber(Protocol):
    def __call__(
        self,
        payload: bytes,
        *,
        mime_type: str,
        filename: str,
    ) -> TranscriptionResult: ...


def build_video_normalized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/video-normalized.json"
    )


def replace_video_content(
    db: Session,
    *,
    asset: Asset,
    payload: bytes,
    transcription: TranscriptionResult,
    processing_generation: int,
    created_at: datetime,
    normalized_object_key: str,
    mime_type: str,
    keyframe_count: int = 0,
) -> None:
    if asset.asset_kind != "video":
        raise IngestionError(
            "video_asset_kind_invalid",
            "Video adapter received a non-video asset (must not use audio kind).",
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
        representation_kind="video_source",
        processing_generation=processing_generation,
        generator_provider="video",
        generator_version=VIDEO_PARSER_VERSION,
        object_key=asset.object_key,
        content_sha256=source_sha256,
        created_at=created_at,
    )
    db.add(source_representation)

    normalized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="video_normalized",
        processing_generation=processing_generation,
        generator_provider="asr",
        generator_version=transcription.adapter_version or VIDEO_ASR_ADAPTER_VERSION,
        object_key=normalized_object_key,
        content_sha256=transcription.content_sha256,
        created_at=created_at,
    )
    db.add(normalized_representation)
    db.flush()

    db.add(
        VideoNormalizedContent(
            representation_id=normalized_representation.id,
            format=VIDEO_FORMAT,
            parser_version=VIDEO_PARSER_VERSION,
            normalization_version=VIDEO_NORMALIZATION_VERSION,
            asr_adapter_version=transcription.adapter_version or VIDEO_ASR_ADAPTER_VERSION,
            mime_type=mime_type,
            duration_ms=transcription.duration_ms,
            content_sha256=transcription.content_sha256,
            segment_count=len(transcription.segments),
            keyframe_count=keyframe_count,
            transcript_text=transcription.full_text,
        )
    )

    for order, segment in enumerate(transcription.segments):
        segment_id = stable_video_segment_id(
            source_sha256=source_sha256,
            parser_version=VIDEO_PARSER_VERSION,
            asr_adapter_version=transcription.adapter_version or VIDEO_ASR_ADAPTER_VERSION,
            segment_order=order,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            text_sha256_value=segment.text_sha256,
        )
        segment_row = VideoTranscriptSegment(
            id=str(uuid4()),
            representation_id=normalized_representation.id,
            segment_id=segment_id,
            segment_order=order,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            speaker=segment.speaker,
            text_sha256=segment.text_sha256,
            text_content=segment.text,
            normalization_version=VIDEO_NORMALIZATION_VERSION,
        )
        db.add(segment_row)
        db.flush()

        locator = _persist_video_locator(
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
                unit_kind="video_transcript_segment",
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


def delete_video_content(db: Session, asset_id: str) -> None:
    db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset_id))
    db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset_id))


class VideoIngestionAdapter:
    asset_kind = "video"

    def __init__(
        self,
        *,
        transcriber: VideoTranscriber | None = None,
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
        # Fail closed before any video representation or content-unit persist.
        try:
            profile = require_configured_asr_profile()
        except ModelProviderError as error:
            raise IngestionError(error.code, error.message) from error

        _validate_video_config(config_snapshot, profile)
        try:
            mime_type = validate_video_mime_type(asset.mime_type)
        except ValueError as error:
            raise IngestionError("asset_mime_mismatch", str(error)) from error
        if mime_type not in VIDEO_MIME_TYPES:
            raise IngestionError(
                "asset_mime_mismatch",
                f"Video adapter only accepts {sorted(VIDEO_MIME_TYPES)}.",
            )
        if not payload:
            raise IngestionError("video_payload_empty", "Video upload body is empty.")

        source_sha256 = sha256(payload).hexdigest()
        if asset.source_sha256 is not None and asset.source_sha256.lower() != source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "Video source SHA-256 does not match the asset record.",
            )

        filename = asset.source_filename or f"video{_extension_for_mime(mime_type)}"
        try:
            transcription = self._run_transcription(
                payload,
                mime_type=mime_type,
                filename=filename,
            )
        except ModelProviderError as error:
            raise IngestionError(error.code, error.message) from error

        # Keyframes deferred: do not invent frames without extraction tooling.
        keyframe_count = 0

        normalized_key = build_video_normalized_object_key(asset, processing_generation)
        replace_video_content(
            db,
            asset=asset,
            payload=payload,
            transcription=transcription,
            processing_generation=processing_generation,
            created_at=created_at,
            normalized_object_key=normalized_key,
            mime_type=mime_type,
            keyframe_count=keyframe_count,
        )
        import json

        segments_payload = []
        # segments already validated by replace; rebuild stable ids for JSON body
        source_sha256 = sha256(payload).hexdigest()
        for order, segment in enumerate(transcription.segments):
            segment_id = stable_video_segment_id(
                source_sha256=source_sha256,
                parser_version=VIDEO_PARSER_VERSION,
                asr_adapter_version=transcription.adapter_version or VIDEO_ASR_ADAPTER_VERSION,
                segment_order=order,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text_sha256_value=segment.text_sha256,
            )
            segments_payload.append(
                {
                    "segmentId": segment_id,
                    "segmentOrder": order,
                    "startMs": segment.start_ms,
                    "endMs": segment.end_ms,
                    "speaker": segment.speaker,
                    "text": segment.text,
                    "textSha256": segment.text_sha256,
                }
            )

        body = json.dumps(
            {
                "format": VIDEO_FORMAT,
                "parserVersion": VIDEO_PARSER_VERSION,
                "normalizationVersion": VIDEO_NORMALIZATION_VERSION,
                "asrAdapterVersion": transcription.adapter_version,
                "keyframeVersion": VIDEO_KEYFRAME_VERSION,
                "durationMs": transcription.duration_ms,
                "segmentCount": len(transcription.segments),
                "keyframeCount": keyframe_count,
                "keyframes": [],
                "transcriptText": transcription.full_text,
                "contentSha256": transcription.content_sha256,
                "segments": segments_payload,
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
        delete_video_content(db, asset.id)

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
        # Reuse audio ASR path; Whisper accepts video containers with audio tracks.
        return transcribe_audio_payload(payload, mime_type=mime_type, filename=filename)


def _extension_for_mime(mime_type: str) -> str:
    return {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }.get(mime_type, ".bin")


def _validate_video_config(snapshot: Mapping[str, object], profile) -> None:
    expected = {
        "videoFormat": VIDEO_FORMAT,
        "videoParserVersion": VIDEO_PARSER_VERSION,
        "videoNormalizationVersion": VIDEO_NORMALIZATION_VERSION,
        "asrAdapterVersion": VIDEO_ASR_ADAPTER_VERSION,
    }
    for key, value in expected.items():
        if key not in snapshot or snapshot[key] != value:
            raise IngestionError(
                "video_configuration_mismatch",
                "Video parser/ASR configuration does not match the job snapshot.",
            )
    from ai_pdf_api.services.capabilities import require_matching_snapshot_fingerprint

    snapshot_fields = asr_profile_snapshot_fields(profile)
    require_matching_snapshot_fingerprint(
        snapshot,
        field_name="asrProfileFingerprint",
        actual_fingerprint=snapshot_fields.get("asrProfileFingerprint"),
        error_code="video_configuration_mismatch",
        error_message="Video ASR profile fingerprint does not match the job snapshot.",
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
                ("video_source", "video_normalized", "video_keyframe_set")
            ),
        )
    )
    if existing is not None:
        raise IngestionError(
            "video_generation_already_exists",
            "Video processing generation is already materialized and immutable.",
        )


def _persist_video_locator(
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
        or representation.representation_kind != "video_normalized"
    ):
        raise IngestionError(
            "video_evidence_representation_invalid",
            "Video locator requires the normalized representation for this generation.",
        )
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="video_range",
        locator_version=1,
        processing_generation_snapshot=processing_generation,
        representation_id_snapshot=representation.id,
        created_at=created_at,
    )
    db.add(locator)
    db.flush()
    db.add(
        VideoLocatorDetail(
            locator_id=locator.id,
            segment_id=segment_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text_sha256=text_sha256_value,
            normalization_version=VIDEO_NORMALIZATION_VERSION,
        )
    )
    return locator
