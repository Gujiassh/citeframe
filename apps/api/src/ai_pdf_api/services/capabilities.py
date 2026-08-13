from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Literal, Mapping
from urllib.parse import urlsplit, urlunsplit

from ai_pdf_api.core.settings import settings


CapabilityName = Literal["generation", "embedding", "vision", "asr"]


class CapabilityUnavailableError(RuntimeError):
    def __init__(self, capability: CapabilityName) -> None:
        self.capability = capability
        self.code = "capability_unavailable"
        self.message = f"The {capability} capability is not configured or registered."
        super().__init__(self.message)


@dataclass(frozen=True)
class CapabilityProfile:
    capability: CapabilityName
    provider: str
    model: str
    adapter_version: str
    model_version: str | None
    endpoint_identifier: str | None
    limits: Mapping[str, object]
    pricing_version: str | None
    data_boundary_policy_version: str
    configured: bool
    config_fingerprint: str

    def public_metadata(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "provider": self.provider,
            "model": self.model,
            "adapterVersion": self.adapter_version,
            "modelVersion": self.model_version,
            "limits": dict(self.limits),
            "pricingVersion": self.pricing_version,
            "dataBoundaryPolicyVersion": self.data_boundary_policy_version,
            "configured": self.configured,
            "configFingerprint": self.config_fingerprint,
        }


class CapabilityRegistry:
    def __init__(self, profiles: Mapping[CapabilityName, CapabilityProfile | None]) -> None:
        self._profiles = dict(profiles)

    def get(self, capability: CapabilityName) -> CapabilityProfile | None:
        return self._profiles.get(capability)

    def resolve(self, capability: CapabilityName) -> CapabilityProfile:
        profile = self.get(capability)
        if profile is None:
            raise CapabilityUnavailableError(capability)
        return profile

    def execution_fingerprint(
        self,
        *,
        retrieval_strategy: str,
        retrieval_top_k: int | None = None,
        data_boundary_policy_version: str,
    ) -> str:
        generation = self.resolve("generation")
        embedding = self.resolve("embedding")
        payload: dict[str, object] = {
            "schemaVersion": "citeframe-execution-profile-v2",
            "generationProvider": generation.provider,
            "generationModel": generation.model,
            "generationProfileSha256": generation.config_fingerprint,
            "embeddingProvider": embedding.provider,
            "embeddingModel": embedding.model,
            "embeddingVersion": embedding.model_version,
            "embeddingProfileSha256": embedding.config_fingerprint,
            "retrievalStrategy": retrieval_strategy,
            "dataBoundaryPolicyVersion": data_boundary_policy_version,
        }
        if retrieval_top_k is not None:
            payload["retrievalTopK"] = retrieval_top_k
        return _canonical_sha256(payload)


def build_capability_registry() -> CapabilityRegistry:
    """Build the registry from server configuration without probing providers."""

    from ai_pdf_api.services.research_constants import DATA_BOUNDARY_POLICY, PRICING_VERSION

    generation_provider = settings.generation_provider
    generation_endpoint = normalize_provider_endpoint(
        _generation_base(generation_provider), provider=generation_provider
    )
    generation = _make_profile(
        capability="generation",
        provider=generation_provider,
        model=settings.generation_model,
        adapter_version=_generation_adapter_version(generation_provider),
        model_version=None,
        endpoint_identifier=generation_endpoint,
        limits={
            "timeoutSeconds": settings.generation_timeout_seconds,
            "maxOutputTokens": settings.generation_max_output_tokens,
        },
        pricing_version=PRICING_VERSION,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        secret=_generation_secret(generation_provider),
        secret_required=generation_provider in {"openai", "deepseek"},
    )

    embedding_provider = settings.embedding_provider
    embedding = _make_profile(
        capability="embedding",
        provider=embedding_provider,
        model=settings.embedding_model,
        adapter_version=f"embedding-{embedding_provider}-v1",
        model_version=settings.embedding_version,
        endpoint_identifier=normalize_provider_endpoint(
            _embedding_base(embedding_provider), provider=embedding_provider
        ),
        limits={
            "dimensions": settings.embedding_dimensions,
            "batchSize": settings.embedding_batch_size,
            "timeoutSeconds": settings.embedding_timeout_seconds,
            "queryInstructionSha256": _canonical_sha256(settings.embedding_query_instruction),
        },
        pricing_version=None,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        secret=_embedding_secret(embedding_provider),
        secret_required=embedding_provider == "openai",
    )

    vision_provider = settings.image_caption_provider
    vision = _make_profile(
        capability="vision",
        provider=vision_provider,
        model=settings.image_caption_model,
        adapter_version=f"vision-image-caption-{vision_provider}-responses-v1",
        model_version=settings.image_caption_version,
        endpoint_identifier=normalize_provider_endpoint(
            _vision_base(vision_provider), provider=vision_provider
        ),
        limits={
            "detail": settings.image_caption_detail,
            "timeoutSeconds": settings.image_caption_timeout_seconds,
            "maxOutputTokens": settings.image_caption_max_output_tokens,
        },
        pricing_version=PRICING_VERSION,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        secret=_vision_secret(vision_provider),
        secret_required=vision_provider == "openai",
    )

    asr_provider = settings.asr_provider
    asr = _make_profile(
        capability="asr",
        provider=asr_provider,
        model=settings.asr_model,
        adapter_version=f"asr-{asr_provider}-transcriptions-v1",
        model_version=settings.asr_version,
        endpoint_identifier=normalize_provider_endpoint(
            _asr_base(asr_provider), provider=asr_provider
        ),
        limits={
            "timeoutSeconds": settings.asr_timeout_seconds,
            "maxDurationSeconds": settings.asr_max_duration_seconds,
            "maxFileBytes": settings.asr_max_file_bytes,
        },
        pricing_version=PRICING_VERSION,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        secret=_asr_secret(asr_provider),
        secret_required=asr_provider == "openai",
    )

    return CapabilityRegistry(
        {
            "generation": generation,
            "embedding": embedding,
            "vision": vision,
            "asr": asr,
        }
    )


def legacy_execution_profile_fingerprint() -> str:
    """Historical Research provider_config_fingerprint preimage (pre-capability registry)."""

    from ai_pdf_api.services.research_constants import DATA_BOUNDARY_POLICY
    from ai_pdf_api.services.research_idempotency import canonical_sha256

    return canonical_sha256(
        {
            "generationProvider": settings.generation_provider,
            "generationModel": settings.generation_model,
            "embeddingProvider": settings.embedding_provider,
            "embeddingModel": settings.embedding_model,
            "embeddingVersion": settings.embedding_version,
            "retrievalStrategy": settings.retrieval_strategy,
            "dataBoundaryPolicyVersion": DATA_BOUNDARY_POLICY,
        }
    )


def current_execution_profile_fingerprint(*, retrieval_top_k: int | None = None) -> str:
    from ai_pdf_api.services.research_constants import DATA_BOUNDARY_POLICY

    registry = build_capability_registry()
    return registry.execution_fingerprint(
        retrieval_strategy=settings.retrieval_strategy,
        retrieval_top_k=retrieval_top_k,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
    )


def matches_frozen_execution_fingerprint(
    frozen_fingerprint: str,
    *,
    retrieval_top_k: int | None = None,
) -> bool:
    """Bounded dual-read for Research fingerprint cutover.

    - New revisions write the v2 capability execution fingerprint.
    - Historical pending/approved rows keep their frozen value and may continue when
      either the current v2 fingerprint or the legacy preimage still matches.
    - Endpoint/secret/adapter/limit drift still fails closed for pure v2 snapshots
      because those inputs only affect the v2 fingerprint.
    """

    if not frozen_fingerprint:
        return False
    current_v2 = current_execution_profile_fingerprint(retrieval_top_k=retrieval_top_k)
    if frozen_fingerprint == current_v2:
        return True
    return frozen_fingerprint == legacy_execution_profile_fingerprint()


def embedding_profile_snapshot_fields(profile: CapabilityProfile | None = None) -> dict[str, object]:
    resolved = profile or build_capability_registry().resolve("embedding")
    return {
        "embeddingProvider": resolved.provider,
        "embeddingModel": resolved.model,
        "embeddingDimensions": resolved.limits.get("dimensions", settings.embedding_dimensions),
        "embeddingVersion": resolved.model_version or settings.embedding_version,
        "embeddingProfileFingerprint": resolved.config_fingerprint,
    }


def asr_profile_snapshot_fields(profile: CapabilityProfile | None = None) -> dict[str, object]:
    resolved = profile or build_capability_registry().resolve("asr")
    return {
        "asrProvider": resolved.provider,
        "asrModel": resolved.model,
        "asrVersion": resolved.model_version or settings.asr_version,
        "asrTimeoutSeconds": resolved.limits.get("timeoutSeconds", settings.asr_timeout_seconds),
        "asrMaxDurationSeconds": resolved.limits.get(
            "maxDurationSeconds", settings.asr_max_duration_seconds
        ),
        "asrMaxFileBytes": resolved.limits.get("maxFileBytes", settings.asr_max_file_bytes),
        "asrProfileFingerprint": resolved.config_fingerprint,
    }


def vision_profile_snapshot_fields(profile: CapabilityProfile | None = None) -> dict[str, object]:
    resolved = profile or build_capability_registry().resolve("vision")
    return {
        "imageCaptionProvider": resolved.provider,
        "imageCaptionModel": resolved.model,
        "imageCaptionVersion": resolved.model_version or settings.image_caption_version,
        "imageCaptionDetail": resolved.limits.get("detail", settings.image_caption_detail),
        "imageCaptionMaxOutputTokens": resolved.limits.get(
            "maxOutputTokens", settings.image_caption_max_output_tokens
        ),
        "imageCaptionProfileFingerprint": resolved.config_fingerprint,
    }


def require_matching_snapshot_fingerprint(
    snapshot: Mapping[str, object],
    *,
    field_name: str,
    actual_fingerprint: object,
    error_code: str,
    error_message: str,
    error_cls: type[Exception],
) -> None:
    """When a snapshot freezes a profile fingerprint, require a non-empty equal actual value."""

    if field_name not in snapshot:
        return
    expected = snapshot.get(field_name)
    if not isinstance(actual_fingerprint, str) or not actual_fingerprint:
        raise error_cls(error_code, error_message)
    if expected != actual_fingerprint:
        raise error_cls(error_code, error_message)


def normalize_provider_endpoint(value: str, *, provider: str) -> str | None:
    """Canonical non-secret endpoint identifier shared by fingerprints and request bases."""

    if not value:
        return None
    parts = urlsplit(value.rstrip("/"))
    if not parts.scheme or not parts.hostname:
        return value.rstrip("/") or None
    hostname = parts.hostname.lower()
    netloc = hostname
    if parts.port is not None:
        netloc = f"{hostname}:{parts.port}"
    path = parts.path.rstrip("/")
    if provider == "openai" and not path.endswith("/v1"):
        path = f"{path}/v1"
    elif provider == "deepseek":
        if path.endswith("/anthropic/v1"):
            pass
        elif path.endswith("/anthropic"):
            path = f"{path}/v1"
        elif path.endswith("/v1"):
            path = f"{path[:-3]}/anthropic/v1"
        else:
            path = f"{path}/anthropic/v1"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def _make_profile(
    *,
    capability: CapabilityName,
    provider: str,
    model: str,
    adapter_version: str,
    model_version: str | None,
    endpoint_identifier: str | None,
    limits: Mapping[str, object],
    pricing_version: str | None,
    data_boundary_policy_version: str,
    secret: str | None,
    secret_required: bool,
) -> CapabilityProfile:
    # Blank/whitespace-only secrets are missing for configured + one-way marker semantics.
    normalized_secret = _normalize_secret(secret)
    fingerprint_payload = {
        "schemaVersion": "citeframe-capability-profile-v1",
        "capability": capability,
        "provider": provider,
        "model": model,
        "adapterVersion": adapter_version,
        "modelVersion": model_version,
        "endpointIdentifier": endpoint_identifier,
        "limits": dict(limits),
        "pricingVersion": pricing_version,
        "dataBoundaryPolicyVersion": data_boundary_policy_version,
        # One-way marker detects secret rotation without persisting the secret.
        "secretMaterialFingerprint": _secret_marker(normalized_secret),
    }
    return CapabilityProfile(
        capability=capability,
        provider=provider,
        model=model,
        adapter_version=adapter_version,
        model_version=model_version,
        endpoint_identifier=endpoint_identifier,
        limits=dict(limits),
        pricing_version=pricing_version,
        data_boundary_policy_version=data_boundary_policy_version,
        configured=(normalized_secret is not None if secret_required else True),
        config_fingerprint=_canonical_sha256(fingerprint_payload),
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(payload).hexdigest()


def _normalize_secret(secret: str | None) -> str | None:
    """Treat None/empty/whitespace-only secrets as missing for all secret-required profiles."""

    if secret is None:
        return None
    stripped = secret.strip()
    return stripped or None


def _secret_marker(secret: str | None) -> str:
    normalized = _normalize_secret(secret)
    if normalized is None:
        return "missing"
    return hmac.new(
        settings.capability_fingerprint_pepper.encode("utf-8"),
        normalized.encode("utf-8"),
        sha256,
    ).hexdigest()


def _generation_adapter_version(provider: str) -> str:
    if provider == "openai":
        return "generation-openai-responses-v1"
    if provider == "deepseek":
        return "generation-deepseek-anthropic-messages-v1"
    return f"generation-{provider}-v1"


def _generation_base(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_base
    if provider == "deepseek":
        return settings.deepseek_api_base
    return ""


def _embedding_base(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_base
    if provider == "ollama":
        return settings.ollama_base_url
    return ""


def _vision_base(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_base
    return ""


def _generation_secret(provider: str) -> str | None:
    if provider == "openai":
        return settings.openai_api_key
    if provider == "deepseek":
        return settings.deepseek_api_key
    return None


def _embedding_secret(provider: str) -> str | None:
    return settings.openai_api_key if provider == "openai" else None


def _vision_secret(provider: str) -> str | None:
    return settings.openai_api_key if provider == "openai" else None


def _asr_base(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_base
    return ""


def _asr_secret(provider: str) -> str | None:
    return settings.openai_api_key if provider == "openai" else None


# Backward-compatible private alias used by earlier tests/partial imports.
_normalize_endpoint = normalize_provider_endpoint
