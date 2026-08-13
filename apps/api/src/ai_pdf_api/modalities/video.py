"""Video modality helpers: closed MIME freeze, segment schema, locator validation.

F-VIDEO ships types and validation only for production enablement later (S0).
ASR must be configured before any video representation or content-unit persist.
Keyframes are optional; never invent frames when tooling is missing.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Iterable, Protocol

VIDEO_FORMAT = "video"
VIDEO_PARSER_VERSION = "video-parser-v1"
VIDEO_NORMALIZATION_VERSION = "video-normalization-v1"
VIDEO_ASR_ADAPTER_VERSION = "asr-openai-transcriptions-v1"
VIDEO_KEYFRAME_VERSION = "video-keyframe-v1"

# Frozen closed list (F-VIDEO / v5f). Do not expand without fixture audit.
VIDEO_MIME_TYPES = frozenset(
    {
        "video/mp4",
        "video/webm",
    }
)

VIDEO_MIME_EXTENSIONS = {
    "video/mp4": (".mp4", ".m4v"),
    "video/webm": (".webm",),
}


class VideoIntegrityError(ValueError):
    """Raised when persisted video normalized content or segments are corrupt."""


class VideoNormalizedLike(Protocol):
    format: str
    parser_version: str
    normalization_version: str
    asr_adapter_version: str
    duration_ms: int
    content_sha256: str
    segment_count: int
    mime_type: str
    keyframe_count: int


class VideoTranscriptSegmentLike(Protocol):
    segment_id: str
    segment_order: int
    start_ms: int
    end_ms: int
    speaker: str | None
    text_sha256: str
    text_content: str
    normalization_version: str


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def normalize_transcript_text(text: str) -> str:
    """Normalize transcript text before hashing or persistence."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def validate_hex_sha256(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise VideoIntegrityError(f"video requires a lowercase hex SHA-256 {field_name}")
    return value


def validate_video_time_range(*, start_ms: int, end_ms: int) -> None:
    if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
        raise VideoIntegrityError("video start_ms must be a non-negative integer")
    if not isinstance(end_ms, int) or isinstance(end_ms, bool) or end_ms <= start_ms:
        raise VideoIntegrityError("video end_ms must be greater than start_ms")


def validate_optional_speaker(speaker: object) -> str | None:
    if speaker is None:
        return None
    if not isinstance(speaker, str) or not speaker or len(speaker) > 128:
        raise VideoIntegrityError("video speaker must be a non-empty string <= 128 chars")
    if any(ch in speaker for ch in ("\x00", "\n", "\r")):
        raise VideoIntegrityError("video speaker contains forbidden characters")
    return speaker


def stable_video_segment_id(
    *,
    source_sha256: str,
    parser_version: str,
    asr_adapter_version: str,
    segment_order: int,
    start_ms: int,
    end_ms: int,
    text_sha256_value: str,
) -> str:
    if parser_version != VIDEO_PARSER_VERSION:
        raise ValueError(f"Unsupported video parser version: {parser_version}")
    if asr_adapter_version != VIDEO_ASR_ADAPTER_VERSION:
        raise ValueError(f"Unsupported ASR adapter version: {asr_adapter_version}")
    if segment_order < 0:
        raise ValueError("segment_order must be non-negative")
    validate_video_time_range(start_ms=start_ms, end_ms=end_ms)
    material = "\n".join(
        [
            source_sha256,
            parser_version,
            asr_adapter_version,
            str(segment_order),
            str(start_ms),
            str(end_ms),
            text_sha256_value,
        ]
    )
    digest = sha256(material.encode("utf-8")).hexdigest()
    return f"vidseg_{digest[:32]}"


def _looks_like_webm(header: bytes) -> bool:
    return len(header) >= 4 and header[:4] == b"\x1a\x45\xdf\xa3"


def _looks_like_mp4(header: bytes) -> bool:
    if len(header) < 12:
        return False
    if header[4:8] != b"ftyp":
        return False
    brand = header[8:12]
    return brand in {
        b"isom",
        b"iso2",
        b"mp41",
        b"mp42",
        b"avc1",
        b"MSNV",
        b"M4V ",
        b"dash",
        b"mp71",
    }


def detect_video_mime_type(header: bytes) -> str | None:
    """Byte inspector for the frozen video MIME set. Returns None when unknown."""
    if not header:
        return None
    if _looks_like_webm(header):
        return "video/webm"
    if _looks_like_mp4(header):
        return "video/mp4"
    return None


def validate_video_upload_payload(payload: bytes) -> None:
    if not payload:
        raise ValueError("Video upload body is empty")
    detected = detect_video_mime_type(payload[:4096])
    if detected is None or detected not in VIDEO_MIME_TYPES:
        raise ValueError(
            "File signature does not match a supported video MIME type: "
            + ", ".join(sorted(VIDEO_MIME_TYPES))
        )


def validate_video_mime_type(mime_type: str) -> str:
    normalized = mime_type.lower().strip()
    if normalized not in VIDEO_MIME_TYPES:
        raise ValueError(f"Unsupported video MIME type: {mime_type}")
    return normalized


def validate_video_transcript_segment(segment: VideoTranscriptSegmentLike) -> str:
    if not segment.segment_id:
        raise VideoIntegrityError("video segment requires a stable segment_id")
    if segment.segment_order < 0:
        raise VideoIntegrityError("video segment_order is invalid")
    if segment.normalization_version != VIDEO_NORMALIZATION_VERSION:
        raise VideoIntegrityError("video segment normalization_version is invalid")
    validate_video_time_range(start_ms=segment.start_ms, end_ms=segment.end_ms)
    validate_optional_speaker(segment.speaker)
    if not isinstance(segment.text_content, str) or not segment.text_content.strip():
        raise VideoIntegrityError("video segment text_content must be non-empty")
    digest = validate_hex_sha256(segment.text_sha256, field_name="text_sha256")
    if digest != text_sha256(segment.text_content):
        raise VideoIntegrityError("video segment text_sha256 does not match text_content")
    return segment.text_content


def validate_video_transcript_segments(
    segments: Iterable[VideoTranscriptSegmentLike],
    *,
    expected_segment_count: int | None = None,
    duration_ms: int | None = None,
) -> list[VideoTranscriptSegmentLike]:
    ordered = list(segments)
    if expected_segment_count is not None and len(ordered) != expected_segment_count:
        raise VideoIntegrityError("video segment_count does not match persisted segments")
    if not ordered:
        raise VideoIntegrityError("video requires at least one non-empty transcript segment")
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    for segment in ordered:
        if segment.segment_order in seen_orders:
            raise VideoIntegrityError("video segment_order is not unique")
        if segment.segment_id in seen_ids:
            raise VideoIntegrityError("video segment_id is not unique")
        seen_orders.add(segment.segment_order)
        seen_ids.add(segment.segment_id)
        validate_video_transcript_segment(segment)
        if duration_ms is not None and segment.end_ms > duration_ms:
            raise VideoIntegrityError("video segment end_ms exceeds duration_ms")
    return ordered


def validate_video_normalized_content(normalized: VideoNormalizedLike) -> None:
    if normalized.format != VIDEO_FORMAT:
        raise VideoIntegrityError("video normalized content format is invalid")
    if normalized.parser_version != VIDEO_PARSER_VERSION:
        raise VideoIntegrityError("video normalized content parser_version is invalid")
    if normalized.normalization_version != VIDEO_NORMALIZATION_VERSION:
        raise VideoIntegrityError("video normalized content normalization_version is invalid")
    if normalized.asr_adapter_version != VIDEO_ASR_ADAPTER_VERSION:
        raise VideoIntegrityError("video normalized content asr_adapter_version is invalid")
    if normalized.duration_ms < 0:
        raise VideoIntegrityError("video duration_ms is invalid")
    if normalized.segment_count < 1:
        raise VideoIntegrityError("video segment_count must be at least 1")
    if normalized.keyframe_count < 0:
        raise VideoIntegrityError("video keyframe_count is invalid")
    validate_video_mime_type(normalized.mime_type)
    validate_hex_sha256(normalized.content_sha256, field_name="content_sha256")


def validate_video_range(
    *,
    start_ms: int,
    end_ms: int,
    text_sha256_value: str,
    segment: VideoTranscriptSegmentLike,
) -> None:
    validate_video_time_range(start_ms=start_ms, end_ms=end_ms)
    digest = validate_hex_sha256(text_sha256_value, field_name="text_sha256")
    validate_video_transcript_segment(segment)
    if start_ms < segment.start_ms or end_ms > segment.end_ms:
        raise VideoIntegrityError("video_range is outside the stored segment bounds")
    if digest != segment.text_sha256:
        raise VideoIntegrityError("video_range text_sha256 does not match segment text")


def validate_video_frame(
    *,
    timestamp_ms: int | None,
    frame_index: int | None,
    keyframe_object_key: str | None,
) -> None:
    """Validate video_frame locator fields. Never invent missing keyframe assets."""
    has_ts = timestamp_ms is not None
    has_idx = frame_index is not None
    if not has_ts and not has_idx:
        raise VideoIntegrityError("video_frame requires timestamp_ms or frame_index")
    if has_ts:
        if not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool) or timestamp_ms < 0:
            raise VideoIntegrityError("video_frame timestamp_ms must be a non-negative integer")
    if has_idx:
        if not isinstance(frame_index, int) or isinstance(frame_index, bool) or frame_index < 0:
            raise VideoIntegrityError("video_frame frame_index must be a non-negative integer")
    if keyframe_object_key is not None:
        if (
            not isinstance(keyframe_object_key, str)
            or not keyframe_object_key
            or len(keyframe_object_key) > 512
        ):
            raise VideoIntegrityError("video_frame keyframe_object_key is invalid")
        if any(ch in keyframe_object_key for ch in ("\x00", "\n", "\r")):
            raise VideoIntegrityError("video_frame keyframe_object_key contains forbidden characters")
