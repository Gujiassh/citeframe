from __future__ import annotations

import base64
import logging
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from ai_pdf_api.core.metrics import observe_provider_request
from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.capabilities import vision_profile_snapshot_fields
from ai_pdf_api.services.capability_errors import (
    normalize_vision_api_key,
    require_configured_vision_profile,
)
from ai_pdf_api.services.providers import ModelProviderError

logger = logging.getLogger(__name__)


class ImageCaptionProvider(Protocol):
    provider: str
    model: str
    version: str
    detail: str
    max_output_tokens: int
    config_fingerprint: str

    def caption(self, payload: bytes, *, content_type: str) -> str: ...


class OpenAIImageCaptionProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        version: str,
        detail: str,
        api_key: str | None,
        api_base: str,
        timeout_seconds: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        if detail not in {"low", "high", "original", "auto"}:
            raise ValueError("Unsupported image caption detail level")
        self.model = model
        self.version = version
        self.detail = detail
        self.max_output_tokens = max_output_tokens
        # Blank/whitespace-only keys normalize to None so preflight matches readiness.
        self._api_key = normalize_vision_api_key(api_key)
        self._api_base = _normalize_openai_base(api_base)
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.config_fingerprint = ""

    def caption(self, payload: bytes, *, content_type: str) -> str:
        if content_type != "image/png" or not payload:
            raise ModelProviderError(
                "image_caption_input_invalid",
                "Image caption provider requires a non-empty canonical PNG.",
            )
        # Fail closed before metrics/HTTP so missing/blank secrets never leave the process.
        if normalize_vision_api_key(self._api_key) is None:
            raise ModelProviderError(
                "image_caption_provider_not_configured",
                "OpenAI image caption API key is not configured.",
            )
        with observe_provider_request(self.provider, "image_caption"):
            encoded = base64.b64encode(payload).decode("ascii")
            response = self._post(
                f"{self._api_base}/responses",
                {
                    "model": self.model,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "Describe the image as retrieval evidence. State the visible "
                                        "subject, important entities, relationships, trends, labels, "
                                        "and conclusions. Be factual, concise, and self-contained. "
                                        "Do not use markdown or infer details that are not visible."
                                    ),
                                },
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{encoded}",
                                    "detail": self.detail,
                                },
                            ],
                        }
                    ],
                    "max_output_tokens": self.max_output_tokens,
                },
            )
            return _extract_response_text(response)

    def _post(self, url: str, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
        except httpx.RequestError as error:
            logger.error(
                "model_provider_request_failed provider=openai kind=image_caption error_type=%s",
                type(error).__name__,
            )
            raise ModelProviderError(
                "image_caption_provider_unreachable",
                "Image caption provider is unreachable.",
            ) from error
        if response.is_error:
            raise ModelProviderError(
                "image_caption_provider_error",
                f"Image caption provider returned HTTP {response.status_code}.",
            )
        try:
            data = response.json()
        except ValueError as error:
            raise ModelProviderError(
                "image_caption_invalid_response",
                "Image caption provider returned invalid JSON.",
            ) from error
        if not isinstance(data, dict):
            raise ModelProviderError(
                "image_caption_invalid_response",
                "Image caption provider returned an invalid payload.",
            )
        return data


def get_image_caption_provider() -> ImageCaptionProvider:
    # Production factory only. Tests inject ImageCaptionProvider fakes and skip this path.
    profile = require_configured_vision_profile()
    provider = OpenAIImageCaptionProvider(
        model=settings.image_caption_model,
        version=settings.image_caption_version,
        detail=settings.image_caption_detail,
        api_key=normalize_vision_api_key(settings.openai_api_key),
        api_base=settings.openai_api_base,
        timeout_seconds=settings.image_caption_timeout_seconds,
        max_output_tokens=settings.image_caption_max_output_tokens,
    )
    provider.config_fingerprint = profile.config_fingerprint
    setattr(provider, "capability_profile", profile)
    return provider


def image_caption_config_snapshot() -> dict[str, object]:
    return vision_profile_snapshot_fields()


def _normalize_openai_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    path = urlsplit(base).path.rstrip("/")
    return base if path.endswith("/v1") else f"{base}/v1"


def _extract_response_text(response: dict) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = response.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts and "".join(parts).strip():
            return "".join(parts).strip()
    raise ModelProviderError(
        "image_caption_invalid_response",
        "Image caption provider returned no caption text.",
    )
