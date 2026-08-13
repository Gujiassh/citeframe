from hashlib import sha256

import pytest

from ai_pdf_api.modalities.audio import (
    AUDIO_MIME_TYPES,
    detect_audio_mime_type,
    normalize_transcript_text,
    stable_audio_segment_id,
    text_sha256,
    validate_audio_range,
    validate_audio_transcript_segment,
    validate_audio_upload_payload,
    AudioIntegrityError,
)
from ai_pdf_api.modalities.registry import (
    AUDIO_MODULE,
    build_audio_ready_registry,
    build_production_registry,
)
from ai_pdf_api.modalities.evidence import PRODUCTION_LOCATOR_CODECS, AudioLocatorCodec
from ai_pdf_api.schemas.chat import AudioRangeLocator


class _Seg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _wav_header() -> bytes:
    # Minimal RIFF/WAVE header (not a full valid WAV, enough for signature detect)
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "


def _id3_header() -> bytes:
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 32


def test_audio_mime_freeze_closed_list() -> None:
    assert AUDIO_MIME_TYPES == frozenset(
        {"audio/mpeg", "audio/wav", "audio/mp4", "audio/webm"}
    )


def test_detect_audio_mime_types() -> None:
    assert detect_audio_mime_type(_wav_header()) == "audio/wav"
    assert detect_audio_mime_type(_id3_header()) == "audio/mpeg"
    assert detect_audio_mime_type(b"\x1a\x45\xdf\xa3webm") == "audio/webm"
    # ftyp M4A
    mp4 = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 8
    assert detect_audio_mime_type(mp4) == "audio/mp4"
    assert detect_audio_mime_type(b"%PDF-1.7") is None
    assert detect_audio_mime_type(b"") is None


def test_validate_audio_upload_payload() -> None:
    validate_audio_upload_payload(_wav_header() + b"\x00" * 64)
    with pytest.raises(ValueError):
        validate_audio_upload_payload(b"")
    with pytest.raises(ValueError):
        validate_audio_upload_payload(b"%PDF-1.7 fake")


def test_segment_schema_and_stable_id() -> None:
    text = normalize_transcript_text("  hello   world ")
    digest = text_sha256(text)
    seg = _Seg(
        segment_id="audseg_test",
        segment_order=0,
        start_ms=0,
        end_ms=1500,
        speaker=None,
        text_sha256=digest,
        text_content=text,
        normalization_version="audio-normalization-v1",
    )
    assert validate_audio_transcript_segment(seg) == text
    bad = _Seg(**{**seg.__dict__, "end_ms": 0})
    with pytest.raises(AudioIntegrityError):
        validate_audio_transcript_segment(bad)

    sid = stable_audio_segment_id(
        source_sha256="a" * 64,
        parser_version="audio-parser-v1",
        asr_adapter_version="asr-openai-transcriptions-v1",
        segment_order=0,
        start_ms=0,
        end_ms=1500,
        text_sha256_value=digest,
    )
    assert sid.startswith("audseg_")


def test_audio_range_validation() -> None:
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
        normalization_version="audio-normalization-v1",
    )
    validate_audio_range(start_ms=100, end_ms=2000, text_sha256_value=digest, segment=seg)
    with pytest.raises(AudioIntegrityError):
        validate_audio_range(start_ms=0, end_ms=50, text_sha256_value=digest, segment=seg)


def test_audio_range_locator_dto() -> None:
    dto = AudioRangeLocator(
        kind="audio_range",
        version=1,
        startMs=0,
        endMs=1200,
        textSha256="ab" * 32,
        segmentId="audseg_1",
        normalizationVersion="audio-normalization-v1",
    )
    assert dto.endMs == 1200
    with pytest.raises(Exception):
        AudioRangeLocator(
            kind="audio_range",
            version=1,
            startMs=10,
            endMs=5,
            textSha256="ab" * 32,
            segmentId="x",
        )


def test_production_registry_enables_audio_after_s0() -> None:
    production = build_production_registry()
    assert "audio" in production.asset_kinds
    assert "audio" in production.enabled_asset_kinds

def test_audio_locator_codec_registered() -> None:
    codec = PRODUCTION_LOCATOR_CODECS.get("audio_range")
    assert isinstance(codec, AudioLocatorCodec)
    assert "audio_range" in PRODUCTION_LOCATOR_CODECS.kinds
