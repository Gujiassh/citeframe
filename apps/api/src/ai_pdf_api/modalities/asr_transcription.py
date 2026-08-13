"""OpenAI Whisper transcription adapter for F-AUDIO.

Configuration readiness is gated by require_configured_asr_profile().
This module never invents transcript segments on provider or schema failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from ai_pdf_api.core.metrics import observe_provider_request
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.audio import (
    AUDIO_ASR_ADAPTER_VERSION,
    normalize_transcript_text,
    text_sha256,
    validate_audio_time_range,
)
from ai_pdf_api.services.capabilities import CapabilityProfile, asr_profile_snapshot_fields
from ai_pdf_api.services.capability_errors import (
    ASR_PROVIDER_ERROR_CODE,
    ASR_SEGMENT_CONTRACT_CODE,
    ASR_TIMEOUT_CODE,
    normalize_asr_api_key,
    require_configured_asr_profile,
)
from ai_pdf_api.services.providers import ModelProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None
    text_sha256: str


@dataclass(frozen=True)
class TranscriptionResult:
    segments: tuple[TranscriptSegment, ...]
    duration_ms: int
    full_text: str
    content_sha256: str
    adapter_version: str
    profile_snapshot: dict[str, object]


class AsrTranscriptionProvider(Protocol):
    provider: str
    model: str
    version: str
    adapter_version: str
    config_fingerprint: str

    def transcribe(
        self,
        payload: bytes,
        *,
        mime_type: str,
        filename: str,
    ) -> TranscriptionResult: ...


def _normalize_openai_base(api_base: str) -> str:
    raw = api_base.strip().rstrip("/")
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise ValueError("OpenAI API base must include scheme and host")
    return raw


class OpenAIWhisperTranscriptionProvider:
    """Calls OpenAI /audio/transcriptions (whisper) with verbose_json segments."""

    provider = "openai"
    adapter_version = AUDIO_ASR_ADAPTER_VERSION

    def __init__(
        self,
        *,
        model: str,
        version: str,
        api_key: str | None,
        api_base: str,
        timeout_seconds: float,
        max_file_bytes: int,
        max_duration_seconds: float,
        client: httpx.Client | None = None,
        config_fingerprint: str = "",
    ) -> None:
        self.model = model
        self.version = version
        self._api_key = normalize_asr_api_key(api_key)
        self._api_base = _normalize_openai_base(api_base)
        self._timeout_seconds = timeout_seconds
        self._max_file_bytes = max_file_bytes
        self._max_duration_seconds = max_duration_seconds
        self._client = client
        self.config_fingerprint = config_fingerprint

    def transcribe(
        self,
        payload: bytes,
        *,
        mime_type: str,
        filename: str,
    ) -> TranscriptionResult:
        if not payload:
            raise ModelProviderError(
                ASR_SEGMENT_CONTRACT_CODE,
                "ASR requires a non-empty audio payload.",
            )
        if len(payload) > self._max_file_bytes:
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                "Audio payload exceeds configured ASR max file size.",
            )
        if normalize_asr_api_key(self._api_key) is None:
            raise ModelProviderError(
                "asr_not_configured",
                "OpenAI ASR API key is not configured.",
            )

        with observe_provider_request(self.provider, "asr_transcription"):
            response = self._post_multipart(
                f"{self._api_base}/audio/transcriptions",
                payload=payload,
                mime_type=mime_type,
                filename=filename or "audio.bin",
            )
        return self._parse_verbose_json(response)

    def _post_multipart(
        self,
        url: str,
        *,
        payload: bytes,
        mime_type: str,
        filename: str,
    ) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {
            "file": (filename, payload, mime_type),
        }
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    data=data,
                    files=files,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                response = httpx.post(
                    url,
                    data=data,
                    files=files,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
        except httpx.TimeoutException as error:
            raise ModelProviderError(
                ASR_TIMEOUT_CODE,
                "ASR provider timed out.",
            ) from error
        except httpx.RequestError as error:
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                "ASR provider request failed.",
            ) from error

        if response.status_code >= 400:
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                f"ASR provider returned HTTP {response.status_code}.",
            )
        try:
            body = response.json()
        except ValueError as error:
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                "ASR provider returned non-JSON body.",
            ) from error
        if not isinstance(body, dict):
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                "ASR provider returned an invalid JSON object.",
            )
        return body

    def _parse_verbose_json(self, body: dict) -> TranscriptionResult:
        raw_segments = body.get("segments")
        full_text = normalize_transcript_text(str(body.get("text") or ""))
        duration_s = body.get("duration")
        duration_ms = 0
        if isinstance(duration_s, (int, float)) and not isinstance(duration_s, bool):
            duration_ms = max(0, int(round(float(duration_s) * 1000)))
        if duration_ms > int(self._max_duration_seconds * 1000):
            raise ModelProviderError(
                ASR_PROVIDER_ERROR_CODE,
                "Audio duration exceeds configured ASR max duration.",
            )

        segments: list[TranscriptSegment] = []
        if isinstance(raw_segments, list) and raw_segments:
            for index, item in enumerate(raw_segments):
                if not isinstance(item, dict):
                    raise ModelProviderError(
                        ASR_SEGMENT_CONTRACT_CODE,
                        "ASR segment entry is not an object.",
                    )
                start = item.get("start")
                end = item.get("end")
                text = normalize_transcript_text(str(item.get("text") or ""))
                if not text:
                    continue
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                    raise ModelProviderError(
                        ASR_SEGMENT_CONTRACT_CODE,
                        "ASR segment timestamps are invalid.",
                    )
                start_ms = max(0, int(round(float(start) * 1000)))
                end_ms = max(0, int(round(float(end) * 1000)))
                try:
                    validate_audio_time_range(start_ms=start_ms, end_ms=end_ms)
                except ValueError as error:
                    raise ModelProviderError(
                        ASR_SEGMENT_CONTRACT_CODE,
                        "ASR segment time range is invalid.",
                    ) from error
                speaker_raw = item.get("speaker")
                speaker = speaker_raw if isinstance(speaker_raw, str) and speaker_raw.strip() else None
                segments.append(
                    TranscriptSegment(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        speaker=speaker,
                        text_sha256=text_sha256(text),
                    )
                )
        elif full_text:
            # Provider returned text without segments: one synthetic span covering duration.
            end_ms = duration_ms if duration_ms > 0 else 1
            if end_ms <= 0:
                end_ms = 1
            segments.append(
                TranscriptSegment(
                    start_ms=0,
                    end_ms=end_ms,
                    text=full_text,
                    speaker=None,
                    text_sha256=text_sha256(full_text),
                )
            )

        if not segments:
            raise ModelProviderError(
                ASR_SEGMENT_CONTRACT_CODE,
                "ASR returned no non-empty transcript segments.",
            )

        if duration_ms <= 0:
            duration_ms = max(segment.end_ms for segment in segments)

        joined = normalize_transcript_text(" ".join(segment.text for segment in segments))
        content = joined or full_text
        if not content:
            raise ModelProviderError(
                ASR_SEGMENT_CONTRACT_CODE,
                "ASR returned empty transcript text.",
            )

        return TranscriptionResult(
            segments=tuple(segments),
            duration_ms=duration_ms,
            full_text=content,
            content_sha256=text_sha256(content),
            adapter_version=self.adapter_version,
            profile_snapshot={},
        )


def get_asr_transcription_provider(
    profile: CapabilityProfile | None = None,
    *,
    client: httpx.Client | None = None,
) -> OpenAIWhisperTranscriptionProvider:
    """Build a transcription provider after the configured ASR gate."""
    resolved = profile or require_configured_asr_profile()
    api_key = normalize_asr_api_key(settings.openai_api_key)
    if api_key is None:
        raise ModelProviderError(
            "asr_not_configured",
            "OpenAI ASR API key is not configured.",
        )
    return OpenAIWhisperTranscriptionProvider(
        model=resolved.model,
        version=resolved.model_version or settings.asr_version,
        api_key=api_key,
        api_base=settings.openai_api_base,
        timeout_seconds=float(
            resolved.limits.get("timeoutSeconds", settings.asr_timeout_seconds)
        ),
        max_file_bytes=int(resolved.limits.get("maxFileBytes", settings.asr_max_file_bytes)),
        max_duration_seconds=float(
            resolved.limits.get("maxDurationSeconds", settings.asr_max_duration_seconds)
        ),
        client=client,
        config_fingerprint=resolved.config_fingerprint,
    )


def transcribe_audio_payload(
    payload: bytes,
    *,
    mime_type: str,
    filename: str,
    client: httpx.Client | None = None,
) -> TranscriptionResult:
    """Gate on configured ASR, then transcribe. Never invents segments."""
    profile = require_configured_asr_profile()
    provider = get_asr_transcription_provider(profile, client=client)
    result = provider.transcribe(payload, mime_type=mime_type, filename=filename)
    snapshot = asr_profile_snapshot_fields(profile)
    return TranscriptionResult(
        segments=result.segments,
        duration_ms=result.duration_ms,
        full_text=result.full_text,
        content_sha256=result.content_sha256,
        adapter_version=result.adapter_version,
        profile_snapshot=snapshot,
    )
