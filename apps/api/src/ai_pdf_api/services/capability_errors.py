from __future__ import annotations

from typing import NoReturn

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.capabilities import (
    CapabilityName,
    CapabilityProfile,
    CapabilityUnavailableError,
    build_capability_registry,
)
from ai_pdf_api.services.providers import ModelProviderError

VISION_NOT_CONFIGURED_CODE = "image_caption_provider_not_configured"
VISION_NOT_CONFIGURED_MESSAGE = "OpenAI image caption API key is not configured."
CAPABILITY_UNAVAILABLE_CODE = "capability_unavailable"
ASR_NOT_CONFIGURED_CODE = "asr_not_configured"
ASR_NOT_CONFIGURED_MESSAGE = "OpenAI ASR API key is not configured."
ASR_TIMEOUT_CODE = "asr_timeout"
ASR_PROVIDER_ERROR_CODE = "asr_provider_error"
ASR_SEGMENT_CONTRACT_CODE = "asr_segment_contract_invalid"


def capability_unavailable_message(capability: CapabilityName) -> str:
    return f"The {capability} capability is not configured or registered."


def raise_capability_unavailable(capability: CapabilityName) -> NoReturn:
    """Fail closed for an unregistered or permanently unavailable capability."""

    raise ModelProviderError(
        CAPABILITY_UNAVAILABLE_CODE,
        capability_unavailable_message(capability),
    )


def require_capability_profile(capability: CapabilityName) -> CapabilityProfile:
    """Resolve a registered capability profile or raise a stable provider error."""

    try:
        return build_capability_registry().resolve(capability)
    except CapabilityUnavailableError as error:
        raise ModelProviderError(error.code, error.message) from error


def normalize_vision_api_key(api_key: str | None) -> str | None:
    """Treat blank/whitespace-only secrets as missing (aligned with registry strip semantics)."""

    if api_key is None:
        return None
    stripped = api_key.strip()
    return stripped or None


def vision_api_key_configured(api_key: str | None | object = ...) -> bool:
    """True only when the vision/OpenAI key has non-whitespace content."""

    if api_key is ...:
        candidate = settings.openai_api_key
    else:
        candidate = api_key if isinstance(api_key, str) or api_key is None else None
    return normalize_vision_api_key(candidate) is not None


def require_configured_vision_profile() -> CapabilityProfile:
    """Resolve the vision/image-caption profile and fail before any provider HTTP.

    Missing registry entry -> capability_unavailable.
    Present but missing/blank/whitespace secret or registry-unconfigured
    -> image_caption_provider_not_configured.
    Injected test caption providers never go through this helper.

    Registry secret-required profiles already strip-normalize secrets; this gate
    rechecks the live settings key so factory/status stay fail-closed together.
    """

    profile = require_capability_profile("vision")
    if not profile.configured or not vision_api_key_configured():
        raise ModelProviderError(VISION_NOT_CONFIGURED_CODE, VISION_NOT_CONFIGURED_MESSAGE)
    return profile


def normalize_asr_api_key(api_key: str | None) -> str | None:
    """Treat blank/whitespace-only secrets as missing (aligned with registry strip semantics)."""

    return normalize_vision_api_key(api_key)


def asr_api_key_configured(api_key: str | None | object = ...) -> bool:
    """True only when the ASR/OpenAI key has non-whitespace content."""

    if api_key is ...:
        candidate = settings.openai_api_key
    else:
        candidate = api_key if isinstance(api_key, str) or api_key is None else None
    return normalize_asr_api_key(candidate) is not None


def require_configured_asr_profile() -> CapabilityProfile:
    """Resolve the ASR profile and fail before any provider HTTP or audio persist.

    Missing registry entry -> capability_unavailable.
    Present but missing/blank/whitespace secret or registry-unconfigured
    -> asr_not_configured.

    This is configuration readiness only. It does not transcribe audio and must
    not be used as a fake adapter.
    """

    profile = require_capability_profile("asr")
    if not profile.configured or not asr_api_key_configured():
        raise ModelProviderError(ASR_NOT_CONFIGURED_CODE, ASR_NOT_CONFIGURED_MESSAGE)
    return profile


def require_asr_capability() -> CapabilityProfile:
    """Fail closed for unconfigured ASR; never fall back to vision/generation.

    Configured servers receive the frozen profile so a later audio ingest slice
    can persist a snapshot. This helper never invents transcripts.
    """

    return require_configured_asr_profile()


def vision_readiness_status() -> str:
    """Local configuration readiness for image caption; never probes provider HTTP."""

    profile = build_capability_registry().get("vision")
    if profile is None:
        return "not_configured"
    # Registry configured already uses strip; live settings recheck keeps status aligned.
    if not profile.configured or not vision_api_key_configured():
        return "not_configured"
    return "ok"


def asr_capability_status() -> str:
    """Local ASR configuration readiness; never probes provider HTTP."""

    profile = build_capability_registry().get("asr")
    if profile is None:
        return "not_configured"
    if not profile.configured or not asr_api_key_configured():
        return "not_configured"
    return "ok"
