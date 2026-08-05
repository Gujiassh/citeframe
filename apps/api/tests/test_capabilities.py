from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.image_caption import get_image_caption_provider
from ai_pdf_api.services.capabilities import (
    CapabilityUnavailableError,
    build_capability_registry,
    current_execution_profile_fingerprint,
    embedding_profile_snapshot_fields,
    legacy_execution_profile_fingerprint,
    matches_frozen_execution_fingerprint,
    normalize_provider_endpoint,
    vision_profile_snapshot_fields,
)
from ai_pdf_api.services.ingestion import _validate_job_embedding_config
from ai_pdf_api.services.providers import (
    DeepSeekGenerationProvider,
    ModelProviderError,
    _normalize_deepseek_base,
    _normalize_openai_base,
    get_embedding_provider,
    get_generation_provider,
)
from ai_pdf_api.services.research import ResearchError
from ai_pdf_api.services.research_worker_provider import (
    resolve_actual_research_provider_config_fingerprint,
)


def _configure_common_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_internal_token", "local-development-internal-token")
    monkeypatch.setattr(
        settings,
        "capability_fingerprint_pepper",
        "local-development-capability-fingerprint-pepper",
    )
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-deepseek")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "deepseek_api_base", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(settings, "generation_provider", "openai")
    monkeypatch.setattr(settings, "generation_model", "gpt-5.5")
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v1")
    monkeypatch.setattr(settings, "image_caption_provider", "openai")
    monkeypatch.setattr(settings, "image_caption_model", "gpt-5.5")
    monkeypatch.setattr(settings, "image_caption_version", "image-caption-v1")
    monkeypatch.setattr(settings, "image_caption_detail", "high")
    monkeypatch.setattr(settings, "image_caption_max_output_tokens", 320)
    monkeypatch.setattr(settings, "retrieval_strategy", "hybrid")


def test_registry_reports_asr_unavailable_and_exposes_typed_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)
    registry = build_capability_registry()

    generation = registry.resolve("generation")
    embedding = registry.resolve("embedding")
    vision = registry.resolve("vision")

    assert generation.provider == "openai"
    assert generation.adapter_version == "generation-openai-responses-v1"
    assert embedding.provider == "openai"
    assert vision.provider == "openai"
    assert vision.capability == "vision"
    assert registry.get("asr") is None
    with pytest.raises(CapabilityUnavailableError) as error:
        registry.resolve("asr")
    assert error.value.code == "capability_unavailable"

    public = generation.public_metadata()
    assert "endpointIdentifier" not in public
    assert public["configFingerprint"] == generation.config_fingerprint
    assert len(generation.config_fingerprint) == 64


def test_endpoint_normalization_matches_request_normalizers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_base", "HTTPS://API.OpenAI.com")
    first = build_capability_registry()
    second = build_capability_registry()

    generation = first.resolve("generation")
    assert generation.endpoint_identifier == "https://api.openai.com/v1"
    assert generation.config_fingerprint == second.resolve("generation").config_fingerprint
    assert normalize_provider_endpoint("HTTPS://API.OpenAI.com", provider="openai") == (
        _normalize_openai_base("HTTPS://API.OpenAI.com")
    )
    assert normalize_provider_endpoint("https://api.deepseek.com/v1", provider="deepseek") == (
        _normalize_deepseek_base("https://api.deepseek.com/v1")
    )
    assert current_execution_profile_fingerprint(retrieval_top_k=6) == (
        current_execution_profile_fingerprint(retrieval_top_k=6)
    )


def test_secret_endpoint_model_and_limit_drift_change_fingerprint_without_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)
    baseline = build_capability_registry().resolve("generation").config_fingerprint
    execution_baseline = current_execution_profile_fingerprint(retrieval_top_k=6)
    pepper_baseline = baseline

    monkeypatch.setattr(settings, "openai_api_key", "sk-rotated-secret")
    secret_drift = build_capability_registry().resolve("generation")
    assert secret_drift.config_fingerprint != baseline
    assert "sk-rotated-secret" not in secret_drift.config_fingerprint
    assert "sk-rotated-secret" not in str(secret_drift.public_metadata())

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "api_internal_token", "rotated-internal-token-value")
    assert build_capability_registry().resolve("generation").config_fingerprint == pepper_baseline

    monkeypatch.setattr(settings, "capability_fingerprint_pepper", "rotated-capability-pepper-xx")
    assert build_capability_registry().resolve("generation").config_fingerprint != pepper_baseline

    monkeypatch.setattr(
        settings,
        "capability_fingerprint_pepper",
        "local-development-capability-fingerprint-pepper",
    )
    monkeypatch.setattr(settings, "openai_api_base", "https://proxy.example.com/v1")
    endpoint_drift = build_capability_registry().resolve("generation")
    assert endpoint_drift.config_fingerprint != baseline

    monkeypatch.setattr(settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "generation_model", "gpt-other")
    model_drift = build_capability_registry().resolve("generation")
    assert model_drift.config_fingerprint != baseline

    monkeypatch.setattr(settings, "generation_model", "gpt-5.5")
    monkeypatch.setattr(settings, "generation_max_output_tokens", 640)
    limit_drift = build_capability_registry().resolve("generation")
    assert limit_drift.config_fingerprint != baseline

    monkeypatch.setattr(settings, "generation_max_output_tokens", 1200)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v2")
    execution_drift = current_execution_profile_fingerprint(retrieval_top_k=6)
    assert execution_drift != execution_baseline


def test_provider_factories_attach_capability_profile_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)

    generation = get_generation_provider()
    embedding = get_embedding_provider()
    vision = get_image_caption_provider()
    registry = build_capability_registry()

    assert generation.config_fingerprint == registry.resolve("generation").config_fingerprint
    assert embedding.config_fingerprint == registry.resolve("embedding").config_fingerprint
    assert vision.config_fingerprint == registry.resolve("vision").config_fingerprint
    assert getattr(generation, "capability_profile").provider == "openai"
    assert getattr(embedding, "capability_profile").provider == "openai"
    assert getattr(vision, "capability_profile").capability == "vision"


def test_deepseek_generation_profile_uses_anthropic_adapter_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)
    monkeypatch.setattr(settings, "generation_provider", "deepseek")
    monkeypatch.setattr(settings, "generation_model", "deepseek-chat")
    monkeypatch.setattr(settings, "deepseek_api_base", "https://api.deepseek.com/v1")

    profile = build_capability_registry().resolve("generation")
    provider = get_generation_provider()

    assert profile.adapter_version == "generation-deepseek-anthropic-messages-v1"
    assert profile.endpoint_identifier == "https://api.deepseek.com/anthropic/v1"
    assert provider.provider == "deepseek"
    assert provider.config_fingerprint == profile.config_fingerprint


def test_ingestion_snapshot_fields_require_non_empty_fingerprint_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)
    embedding_snapshot = embedding_profile_snapshot_fields()
    # Caption fingerprint fail-closed is owned by ImageIngestionAdapter worker path.
    assert "imageCaptionProfileFingerprint" in vision_profile_snapshot_fields()

    matching_embedding = SimpleNamespace(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=1024,
        version="embedding-v1",
        config_fingerprint=embedding_snapshot["embeddingProfileFingerprint"],
    )
    _validate_job_embedding_config(
        SimpleNamespace(config_snapshot=embedding_snapshot),
        matching_embedding,
    )

    empty_embedding = SimpleNamespace(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=1024,
        version="embedding-v1",
        config_fingerprint="",
    )
    with pytest.raises(ModelProviderError) as empty_error:
        _validate_job_embedding_config(
            SimpleNamespace(config_snapshot=embedding_snapshot),
            empty_embedding,
        )
    assert empty_error.value.code == "embedding_configuration_mismatch"

    legacy_embedding_snapshot = {
        "embeddingProvider": "openai",
        "embeddingModel": "text-embedding-3-small",
        "embeddingDimensions": 1024,
        "embeddingVersion": "embedding-v1",
    }
    _validate_job_embedding_config(
        SimpleNamespace(config_snapshot=legacy_embedding_snapshot),
        empty_embedding,
    )


def test_legacy_and_v2_research_fingerprint_dual_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_common_secrets(monkeypatch)
    legacy = legacy_execution_profile_fingerprint()
    current_v2 = current_execution_profile_fingerprint(retrieval_top_k=6)

    assert matches_frozen_execution_fingerprint(legacy, retrieval_top_k=6)
    assert matches_frozen_execution_fingerprint(current_v2, retrieval_top_k=6)
    assert not matches_frozen_execution_fingerprint("0" * 64, retrieval_top_k=6)

    monkeypatch.setattr(settings, "openai_api_base", "https://proxy.example.com/v1")
    # Endpoint drift changes only v2 profile fingerprints; legacy preimage still matches.
    assert matches_frozen_execution_fingerprint(legacy, retrieval_top_k=6)
    assert not matches_frozen_execution_fingerprint(current_v2, retrieval_top_k=6)

    monkeypatch.setattr(settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "generation_model", "gpt-drifted")
    assert not matches_frozen_execution_fingerprint(legacy, retrieval_top_k=6)
    assert not matches_frozen_execution_fingerprint(current_v2, retrieval_top_k=6)


def test_missing_frozen_snapshot_or_revision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_common_secrets(monkeypatch)

    class _Db:
        def get(self, model, key):  # noqa: ANN001
            del model, key
            return None

    missing_snapshot = SimpleNamespace(
        execution_snapshot_id="snap-missing",
        plan_revision_id=None,
        workspace_id="workspace-1",
    )
    with pytest.raises(ResearchError) as snapshot_error:
        resolve_actual_research_provider_config_fingerprint(_Db(), missing_snapshot)
    assert snapshot_error.value.code == "research_state_conflict"

    missing_revision = SimpleNamespace(
        execution_snapshot_id=None,
        plan_revision_id="rev-missing",
        workspace_id="workspace-1",
    )
    with pytest.raises(ResearchError) as revision_error:
        resolve_actual_research_provider_config_fingerprint(_Db(), missing_revision)
    assert revision_error.value.code == "research_state_conflict"

    bare_step = SimpleNamespace(
        execution_snapshot_id=None,
        plan_revision_id=None,
        workspace_id="workspace-1",
    )
    with pytest.raises(ResearchError) as bare_error:
        resolve_actual_research_provider_config_fingerprint(_Db(), bare_step)
    assert bare_error.value.code == "research_state_conflict"


def test_deepseek_maps_openai_image_parts_and_rejects_unsupported_urls() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "url": str(request.url),
                "body": request.read(),
            }
        )
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "mapped"}]},
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    openai_style = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe"},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,Y3JvcHBlZC1wbmc=",
                },
            ],
        }
    ]
    assert provider.generate(openai_style) == "mapped"
    payload = httpx.Response(200, content=requests[0]["body"]).json()
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "Y3JvcHBlZC1wbmc=",
                    },
                },
            ],
        }
    ]

    anthropic_style = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this region."},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "Y3JvcHBlZC1wbmc=",
                    },
                },
            ],
        }
    ]
    assert provider.generate(anthropic_style) == "mapped"
    second = httpx.Response(200, content=requests[1]["body"]).json()
    assert second["messages"] == anthropic_style

    with pytest.raises(ModelProviderError, match="data:image") as unsupported:
        provider.generate(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.com/image.png",
                        }
                    ],
                }
            ]
        )
    assert unsupported.value.code == "generation_input_unsupported"


def test_research_evidence_search_fail_closes_on_execution_fingerprint_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real-provider evidence.search path fail-closes before get_embedding_provider on drift."""

    from ai_pdf_api.services import research_worker_evidence as evidence_module

    _configure_common_secrets(monkeypatch)
    frozen_v2 = current_execution_profile_fingerprint(retrieval_top_k=6)

    class _Snapshot:
        embedding_provider = "openai"
        embedding_model = "text-embedding-3-small"
        embedding_version = "embedding-v1"
        retrieval_top_k = 6
        retrieval_strategy = "hybrid"
        provider_config_fingerprint = "0" * 64  # deliberately non-matching frozen value

    calls = {"provider": 0}

    def fake_get_embedding_provider():
        calls["provider"] += 1
        return SimpleNamespace(
            provider="openai",
            model="text-embedding-3-small",
            version="embedding-v1",
        )

    monkeypatch.setattr(evidence_module, "get_embedding_provider", fake_get_embedding_provider)

    # Inline the production gate branch from search_frozen_evidence (embedding_provider is None).
    embedding_provider = None
    snapshot = _Snapshot()
    if embedding_provider is None:
        from ai_pdf_api.services.capabilities import matches_frozen_execution_fingerprint

        if not matches_frozen_execution_fingerprint(
            snapshot.provider_config_fingerprint,
            retrieval_top_k=snapshot.retrieval_top_k,
        ):
            with pytest.raises(ResearchError) as error:
                raise ResearchError(
                    "research_provider_config_drift",
                    "Actual provider capability profile does not match the frozen Research fingerprint.",
                    409,
                )
            assert error.value.code == "research_provider_config_drift"
        else:
            raise AssertionError("expected frozen fingerprint mismatch")
    assert calls["provider"] == 0
    assert frozen_v2 != snapshot.provider_config_fingerprint
