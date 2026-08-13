from hashlib import sha256

import pytest

from ai_pdf_api.modalities.video import (
    VIDEO_MIME_TYPES,
    detect_video_mime_type,
    normalize_transcript_text,
    stable_video_segment_id,
    text_sha256,
    validate_video_frame,
    validate_video_range,
    validate_video_transcript_segment,
    validate_video_upload_payload,
    VideoIntegrityError,
)
from ai_pdf_api.modalities.registry import (
    VIDEO_MODULE,
    build_production_registry,
    build_video_ready_registry,
)
from ai_pdf_api.modalities.evidence import (
    PRODUCTION_LOCATOR_CODECS,
    VideoFrameLocatorCodec,
    VideoLocatorCodec,
)
from ai_pdf_api.schemas.chat import VideoFrameLocator, VideoRangeLocator


class _Seg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _webm_header() -> bytes:
    return b"\x1a\x45\xdf\xa3webm" + b"\x00" * 32


def _mp4_header() -> bytes:
    return b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8


def test_video_mime_freeze_closed_list() -> None:
    assert VIDEO_MIME_TYPES == frozenset({"video/mp4", "video/webm"})


def test_detect_video_mime_types() -> None:
    assert detect_video_mime_type(_webm_header()) == "video/webm"
    assert detect_video_mime_type(_mp4_header()) == "video/mp4"
    assert detect_video_mime_type(b"%PDF-1.7") is None
    assert detect_video_mime_type(b"") is None
    # audio signatures must not be claimed as video when not matching
    assert detect_video_mime_type(b"ID3\x03\x00\x00") is None
    assert detect_video_mime_type(b"RIFF" + (36).to_bytes(4, "little") + b"WAVE") is None


def test_validate_video_upload_payload() -> None:
    validate_video_upload_payload(_webm_header() + b"\x00" * 64)
    with pytest.raises(ValueError):
        validate_video_upload_payload(b"")
    with pytest.raises(ValueError):
        validate_video_upload_payload(b"%PDF-1.7 fake")


def test_segment_schema_and_stable_id() -> None:
    text = normalize_transcript_text("  hello   world ")
    digest = text_sha256(text)
    seg = _Seg(
        segment_id="vidseg_test",
        segment_order=0,
        start_ms=0,
        end_ms=1500,
        speaker=None,
        text_sha256=digest,
        text_content=text,
        normalization_version="video-normalization-v1",
    )
    assert validate_video_transcript_segment(seg) == text
    bad = _Seg(**{**seg.__dict__, "end_ms": 0})
    with pytest.raises(VideoIntegrityError):
        validate_video_transcript_segment(bad)

    sid = stable_video_segment_id(
        source_sha256="a" * 64,
        parser_version="video-parser-v1",
        asr_adapter_version="asr-openai-transcriptions-v1",
        segment_order=0,
        start_ms=0,
        end_ms=1500,
        text_sha256_value=digest,
    )
    assert sid.startswith("vidseg_")


def test_video_range_validation() -> None:
    text = "hello"
    digest = text_sha256(text)
    seg = _Seg(
        segment_id="s1",
        segment_order=0,
        start_ms=100,
        end_ms=2000,
        speaker=None,
        text_sha256=digest,
        text_content=text,
        normalization_version="video-normalization-v1",
    )
    validate_video_range(start_ms=100, end_ms=2000, text_sha256_value=digest, segment=seg)
    with pytest.raises(VideoIntegrityError):
        validate_video_range(start_ms=0, end_ms=50, text_sha256_value=digest, segment=seg)


def test_video_frame_validation() -> None:
    validate_video_frame(timestamp_ms=1200, frame_index=None, keyframe_object_key=None)
    validate_video_frame(timestamp_ms=None, frame_index=3, keyframe_object_key="k/frames/3.jpg")
    with pytest.raises(VideoIntegrityError):
        validate_video_frame(timestamp_ms=None, frame_index=None, keyframe_object_key=None)


def test_video_range_locator_dto() -> None:
    dto = VideoRangeLocator(
        kind="video_range",
        version=1,
        startMs=0,
        endMs=1200,
        textSha256="ab" * 32,
        segmentId="vidseg_1",
        normalizationVersion="video-normalization-v1",
    )
    assert dto.endMs == 1200
    with pytest.raises(Exception):
        VideoRangeLocator(
            kind="video_range",
            version=1,
            startMs=10,
            endMs=5,
            textSha256="ab" * 32,
            segmentId="x",
        )
    frame = VideoFrameLocator(
        kind="video_frame",
        version=1,
        timestampMs=500,
        frameIndex=None,
        keyframeObjectKey=None,
    )
    assert frame.timestampMs == 500


def test_production_registry_does_not_enable_video() -> None:
    production = build_production_registry()
    assert "video" not in production.asset_kinds
    assert "audio" not in production.asset_kinds
    assert production.asset_kinds == frozenset({"pdf", "image", "document"})
    ready = build_video_ready_registry()
    assert ready.get("video") is VIDEO_MODULE
    assert VIDEO_MODULE.supported_mime_types == VIDEO_MIME_TYPES
    assert VIDEO_MODULE.asset_kind == "video"
    assert VIDEO_MODULE.asset_kind != "audio"


def test_video_locator_codecs_registered() -> None:
    codec = PRODUCTION_LOCATOR_CODECS.get("video_range")
    assert isinstance(codec, VideoLocatorCodec)
    frame = PRODUCTION_LOCATOR_CODECS.get("video_frame")
    assert isinstance(frame, VideoFrameLocatorCodec)
    assert "video_range" in PRODUCTION_LOCATOR_CODECS.kinds
    assert "video_frame" in PRODUCTION_LOCATOR_CODECS.kinds
