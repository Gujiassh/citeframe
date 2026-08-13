"""Audio modality helpers: closed MIME freeze, segment schema, locator validation.

F-AUDIO ships types and validation only for production enablement later (S0).
ASR must be configured before any audio representation or content-unit persist.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Iterable, Protocol

AUDIO_FORMAT = "audio"
AUDIO_PARSER_VERSION = "audio-parser-v1"
AUDIO_NORMALIZATION_VERSION = "audio-normalization-v1"
AUDIO_ASR_ADAPTER_VERSION = "asr-openai-transcriptions-v1"

# Frozen closed list (F-AUDIO / v5f §4.5). Do not expand without fixture audit.
AUDIO_MIME_TYPES = frozenset(
    {
        "audio/mpeg",
        "audio/wav",
        "audio/mp4",
        "audio/webm",
    }
)

AUDIO_MIME_EXTENSIONS = {
    "audio/mpeg": (".mp3", ".mpeg", ".mpga"),
    "audio/wav": (".wav",),
    "audio/mp4": (".m4a", ".mp4"),
    "audio/webm": (".webm",),
}


class AudioIntegrityError(ValueError):
    """Raised when persisted audio normalized content or segments are corrupt."""


class AudioNormalizedLike(Protocol):
    format: str
    parser_version: str
    normalization_version: str
    asr_adapter_version: str
    duration_ms: int
    content_sha256: str
    segment_count: int
    mime_type: str


class AudioTranscriptSegmentLike(Protocol):
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
        raise AudioIntegrityError(f"audio requires a lowercase hex SHA-256 {field_name}")
    return value


def validate_audio_time_range(*, start_ms: int, end_ms: int) -> None:
    if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
        raise AudioIntegrityError("audio start_ms must be a non-negative integer")
    if not isinstance(end_ms, int) or isinstance(end_ms, bool) or end_ms <= start_ms:
        raise AudioIntegrityError("audio end_ms must be greater than start_ms")


def validate_optional_speaker(speaker: object) -> str | None:
    if speaker is None:
        return None
    if not isinstance(speaker, str) or not speaker or len(speaker) > 128:
        raise AudioIntegrityError("audio speaker must be a non-empty string <= 128 chars")
    if any(ch in speaker for ch in ("\x00", "\n", "\r")):
        raise AudioIntegrityError("audio speaker contains forbidden characters")
    return speaker


def stable_audio_segment_id(
    *,
    source_sha256: str,
    parser_version: str,
    asr_adapter_version: str,
    segment_order: int,
    start_ms: int,
    end_ms: int,
    text_sha256_value: str,
) -> str:
    if parser_version != AUDIO_PARSER_VERSION:
        raise ValueError(f"Unsupported audio parser version: {parser_version}")
    if asr_adapter_version != AUDIO_ASR_ADAPTER_VERSION:
        raise ValueError(f"Unsupported ASR adapter version: {asr_adapter_version}")
    if segment_order < 0:
        raise ValueError("segment_order must be non-negative")
    validate_audio_time_range(start_ms=start_ms, end_ms=end_ms)
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
    return f"audseg_{digest[:32]}"


def _looks_like_wav(header: bytes) -> bool:
    return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"


def _looks_like_webm(header: bytes) -> bool:
    return len(header) >= 4 and header[:4] == b"\x1a\x45\xdf\xa3"


def _looks_like_mp4_audio(header: bytes) -> bool:
    if len(header) < 12:
        return False
    if header[4:8] != b"ftyp":
        return False
    brand = header[8:12]
    # Common M4A / MP4 audio brands
    return brand in {
        b"M4A ",
        b"M4B ",
        b"mp41",
        b"mp42",
        b"isom",
        b"iso2",
        b"MSNV",
    }


def _looks_like_mpeg_audio(header: bytes) -> bool:
    if header.startswith(b"ID3"):
        return True
    # MPEG frame sync: 11 set bits
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return True
    return False


def detect_audio_mime_type(header: bytes) -> str | None:
    """Byte inspector for the frozen audio MIME set. Returns None when unknown."""
    if not header:
        return None
    if _looks_like_wav(header):
        return "audio/wav"
    if _looks_like_webm(header):
        return "audio/webm"
    if _looks_like_mp4_audio(header):
        return "audio/mp4"
    if _looks_like_mpeg_audio(header):
        return "audio/mpeg"
    return None


def validate_audio_upload_payload(payload: bytes) -> None:
    if not payload:
        raise ValueError("Audio upload body is empty")
    detected = detect_audio_mime_type(payload[:4096])
    if detected is None or detected not in AUDIO_MIME_TYPES:
        raise ValueError(
            "File signature does not match a supported audio MIME type: "
            + ", ".join(sorted(AUDIO_MIME_TYPES))
        )


def validate_audio_mime_type(mime_type: str) -> str:
    normalized = mime_type.lower().strip()
    if normalized not in AUDIO_MIME_TYPES:
        raise ValueError(f"Unsupported audio MIME type: {mime_type}")
    return normalized


def validate_audio_transcript_segment(segment: AudioTranscriptSegmentLike) -> str:
    if not segment.segment_id:
        raise AudioIntegrityError("audio segment requires a stable segment_id")
    if segment.segment_order < 0:
        raise AudioIntegrityError("audio segment_order is invalid")
    if segment.normalization_version != AUDIO_NORMALIZATION_VERSION:
        raise AudioIntegrityError("audio segment normalization_version is invalid")
    validate_audio_time_range(start_ms=segment.start_ms, end_ms=segment.end_ms)
    validate_optional_speaker(segment.speaker)
    if not isinstance(segment.text_content, str) or not segment.text_content.strip():
        raise AudioIntegrityError("audio segment text_content must be non-empty")
    digest = validate_hex_sha256(segment.text_sha256, field_name="text_sha256")
    if digest != text_sha256(segment.text_content):
        raise AudioIntegrityError("audio segment text_sha256 does not match text_content")
    return segment.text_content


def validate_audio_transcript_segments(
    segments: Iterable[AudioTranscriptSegmentLike],
    *,
    expected_segment_count: int | None = None,
    duration_ms: int | None = None,
) -> list[AudioTranscriptSegmentLike]:
    ordered = list(segments)
    if expected_segment_count is not None and len(ordered) != expected_segment_count:
        raise AudioIntegrityError("audio segment_count does not match persisted segments")
    if not ordered:
        raise AudioIntegrityError("audio requires at least one non-empty transcript segment")
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    for segment in ordered:
        if segment.segment_order in seen_orders:
            raise AudioIntegrityError("audio segment_order is not unique")
        if segment.segment_id in seen_ids:
            raise AudioIntegrityError("audio segment_id is not unique")
        seen_orders.add(segment.segment_order)
        seen_ids.add(segment.segment_id)
        validate_audio_transcript_segment(segment)
        if duration_ms is not None and segment.end_ms > duration_ms:
            raise AudioIntegrityError("audio segment end_ms exceeds duration_ms")
    return ordered


def validate_audio_normalized_content(normalized: AudioNormalizedLike) -> None:
    if normalized.format != AUDIO_FORMAT:
        raise AudioIntegrityError("audio normalized content format is invalid")
    if normalized.parser_version != AUDIO_PARSER_VERSION:
        raise AudioIntegrityError("audio normalized content parser_version is invalid")
    if normalized.normalization_version != AUDIO_NORMALIZATION_VERSION:
        raise AudioIntegrityError("audio normalized content normalization_version is invalid")
    if normalized.asr_adapter_version != AUDIO_ASR_ADAPTER_VERSION:
        raise AudioIntegrityError("audio normalized content asr_adapter_version is invalid")
    if normalized.duration_ms < 0:
        raise AudioIntegrityError("audio duration_ms is invalid")
    if normalized.segment_count < 1:
        raise AudioIntegrityError("audio segment_count must be at least 1")
    validate_audio_mime_type(normalized.mime_type)
    validate_hex_sha256(normalized.content_sha256, field_name="content_sha256")


def validate_audio_range(
    *,
    start_ms: int,
    end_ms: int,
    text_sha256_value: str,
    segment: AudioTranscriptSegmentLike,
) -> None:
    validate_audio_time_range(start_ms=start_ms, end_ms=end_ms)
    digest = validate_hex_sha256(text_sha256_value, field_name="text_sha256")
    validate_audio_transcript_segment(segment)
    if start_ms < segment.start_ms or end_ms > segment.end_ms:
        raise AudioIntegrityError("audio_range is outside the stored segment bounds")
    # Locators bind to segment transcript text via text_sha256.
    if digest != segment.text_sha256:
        raise AudioIntegrityError("audio_range text_sha256 does not match segment text")
