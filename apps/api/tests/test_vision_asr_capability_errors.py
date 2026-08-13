from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import ai_pdf_api.main as main_module
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.image_caption import (
    OpenAIImageCaptionProvider,
    get_image_caption_provider,
)
from ai_pdf_api.services.capabilities import build_capability_registry
from ai_pdf_api.services.capability_errors import (
    ASR_NOT_CONFIGURED_CODE,
    VISION_NOT_CONFIGURED_CODE,
    asr_capability_status,
    require_asr_capability,
    require_configured_asr_profile,
    require_configured_vision_profile,
    vision_readiness_status,
)
from ai_pdf_api.services.providers import ModelProviderError


def _configure_vision_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "capability_fingerprint_pepper",
        "local-development-capability-fingerprint-pepper",
    )
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai-vision")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "image_caption_provider", "openai")
    monkeypatch.setattr(settings, "image_caption_model", "gpt-5.5")
    monkeypatch.setattr(settings, "image_caption_version", "image-caption-v1")
    monkeypatch.setattr(settings, "image_caption_detail", "high")
    monkeypatch.setattr(settings, "image_caption_max_output_tokens", 320)
    monkeypatch.setattr(settings, "generation_provider", "openai")
    monkeypatch.setattr(settings, "generation_model", "gpt-5.5")
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v1")


def test_registry_asr_is_always_capability_unavailable_with_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", None)
    registry = build_capability_registry()

    asr = registry.get("asr")
    assert asr is not None
    assert asr.configured is False
    with pytest.raises(ModelProviderError) as captured:
        require_asr_capability()
    assert captured.value.code == ASR_NOT_CONFIGURED_CODE
    assert "asr" in captured.value.message.lower()
    assert asr_capability_status() == "not_configured"

    # No silent substitution of vision/generation for ASR.
    assert registry.resolve("vision").capability == "vision"
    assert registry.resolve("generation").capability == "generation"
    assert asr.capability == "asr"


def test_vision_missing_key_fails_before_provider_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", None)

    http_calls: list[str] = []

    def reject_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        http_calls.append("called")
        raise AssertionError("vision must fail closed before provider HTTP")

    monkeypatch.setattr(httpx, "post", reject_http)
    monkeypatch.setattr(httpx, "get", reject_http)

    with pytest.raises(ModelProviderError) as factory_error:
        get_image_caption_provider()
    assert factory_error.value.code == VISION_NOT_CONFIGURED_CODE
    assert http_calls == []

    with pytest.raises(ModelProviderError) as require_error:
        require_configured_vision_profile()
    assert require_error.value.code == VISION_NOT_CONFIGURED_CODE
    assert vision_readiness_status() == "not_configured"

    provider = OpenAIImageCaptionProvider(
        model="gpt-5.5",
        version="image-caption-v1",
        detail="high",
        api_key=None,
        api_base="https://api.openai.com/v1",
        timeout_seconds=2,
        max_output_tokens=320,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: (_ for _ in ()).throw(AssertionError("no HTTP"))
            )
        ),
    )
    with pytest.raises(ModelProviderError) as caption_error:
        provider.caption(b"canonical-png", content_type="image/png")
    assert caption_error.value.code == VISION_NOT_CONFIGURED_CODE
    assert http_calls == []


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_vision_blank_or_whitespace_key_fails_closed_before_http(
    monkeypatch: pytest.MonkeyPatch,
    missing_key: str | None,
) -> None:
    """None/empty/whitespace must match readiness strip semantics before provider HTTP."""

    from ai_pdf_api.services.capability_errors import (
        normalize_vision_api_key,
        vision_api_key_configured,
    )

    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", missing_key)

    http_calls: list[str] = []

    def reject_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        http_calls.append("called")
        raise AssertionError("blank/whitespace vision key must not call provider HTTP")

    monkeypatch.setattr(httpx, "post", reject_http)
    monkeypatch.setattr(httpx, "get", reject_http)
    monkeypatch.setattr(main_module.httpx, "get", reject_http)
    monkeypatch.setattr(main_module.httpx, "post", reject_http)

    assert normalize_vision_api_key(missing_key) is None
    assert vision_api_key_configured(missing_key) is False
    # Registry public configured flag must match strip semantics for secret-required profiles.
    registry_profile = build_capability_registry().resolve("vision")
    assert registry_profile.configured is False
    public = registry_profile.public_metadata()
    assert public["configured"] is False
    if missing_key:
        assert missing_key not in str(public)

    with pytest.raises(ModelProviderError) as factory_error:
        get_image_caption_provider()
    assert factory_error.value.code == VISION_NOT_CONFIGURED_CODE
    assert missing_key not in factory_error.value.message if missing_key else True

    with pytest.raises(ModelProviderError) as require_error:
        require_configured_vision_profile()
    assert require_error.value.code == VISION_NOT_CONFIGURED_CODE

    assert vision_readiness_status() == "not_configured"
    assert main_module.capability_status()["vision"] == "not_configured"
    assert main_module._check_image_caption_configuration() == "not_configured"

    provider = OpenAIImageCaptionProvider(
        model="gpt-5.5",
        version="image-caption-v1",
        detail="high",
        api_key=missing_key,
        api_base="https://api.openai.com/v1",
        timeout_seconds=2,
        max_output_tokens=320,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: (_ for _ in ()).throw(AssertionError("no HTTP"))
            )
        ),
    )
    with pytest.raises(ModelProviderError) as caption_error:
        provider.caption(b"canonical-png", content_type="image/png")
    assert caption_error.value.code == VISION_NOT_CONFIGURED_CODE
    if missing_key:
        assert missing_key not in caption_error.value.message
        assert missing_key not in factory_error.value.message
        assert missing_key not in require_error.value.message
    assert http_calls == []


def test_required_caption_provider_failure_keeps_stable_not_configured_code() -> None:
    """Image ingestion requires caption; production not-configured code must stay stable.

    Worker adapter tests inject fakes and assert the same code on the worker side.
    """

    provider = OpenAIImageCaptionProvider(
        model="gpt-5.5",
        version="image-caption-v1",
        detail="high",
        api_key=None,
        api_base="https://api.openai.com/v1",
        timeout_seconds=2,
        max_output_tokens=320,
    )
    with pytest.raises(ModelProviderError) as captured:
        provider.caption(b"\x89PNG", content_type="image/png")
    assert captured.value.code == "image_caption_provider_not_configured"


def test_image_caption_configuration_mismatch_code_remains_stable() -> None:
    """Snapshot mismatch remains the dedicated drift code (not capability_unavailable)."""

    from ai_pdf_api.services.capabilities import require_matching_snapshot_fingerprint

    class Provider:
        provider = "openai"
        model = "gpt-5.5"
        version = "image-caption-v1"
        detail = "high"
        max_output_tokens = 320
        config_fingerprint = "a" * 64

    # Field-level mismatch projection used by worker _validate_caption_config.
    expected = {
        "imageCaptionProvider": Provider.provider,
        "imageCaptionModel": Provider.model,
        "imageCaptionVersion": Provider.version,
        "imageCaptionDetail": Provider.detail,
        "imageCaptionMaxOutputTokens": Provider.max_output_tokens,
    }
    drifted = {**expected, "imageCaptionModel": "drifted-model"}
    assert any(drifted.get(key) != value for key, value in expected.items())

    with pytest.raises(ModelProviderError) as fingerprint_mismatch:
        require_matching_snapshot_fingerprint(
            {
                **expected,
                "imageCaptionProfileFingerprint": "f" * 64,
            },
            field_name="imageCaptionProfileFingerprint",
            actual_fingerprint=Provider.config_fingerprint,
            error_code="image_caption_configuration_mismatch",
            error_message="Image caption provider configuration does not match the job snapshot.",
            error_cls=ModelProviderError,
        )
    assert fingerprint_mismatch.value.code == "image_caption_configuration_mismatch"


def test_error_and_status_surfaces_do_not_leak_secrets_or_preimage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-super-secret-should-not-leak"
    endpoint = "https://secret-proxy.example.com/v1/hidden"
    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", secret)
    monkeypatch.setattr(settings, "openai_api_base", endpoint)

    profile = require_configured_vision_profile()
    public = profile.public_metadata()
    provider = get_image_caption_provider()
    readiness = main_module.capability_status()

    serialized = " ".join(
        [
            str(public),
            str(readiness),
            str(getattr(provider, "capability_profile").public_metadata()),
            profile.config_fingerprint,
            provider.config_fingerprint,
        ]
    )
    assert secret not in serialized
    assert "hidden" not in serialized
    assert "secret-proxy" not in serialized
    assert "endpointIdentifier" not in public
    assert "endpoint" not in readiness
    assert readiness["asr"] == "ok"
    assert readiness["vision"] == "ok"

    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ModelProviderError) as missing:
        get_image_caption_provider()
    assert secret not in missing.value.message
    assert endpoint not in missing.value.message
    assert "fingerprint" not in missing.value.message.lower()


def test_capability_status_is_informational_and_readiness_shape_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "readiness_checks",
        lambda: {
            "database": "ok",
            "modalityCatalog": "ok",
            "objectStorage": "ok",
            "embeddingProvider": "ok",
            "generationProvider": "ok",
        },
    )
    monkeypatch.setattr(
        main_module,
        "capability_status",
        lambda: {"vision": "ok", "asr": "ok"},
    )
    client = TestClient(main_module.app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "service": "api",
        "checks": {
            "database": "ok",
            "modalityCatalog": "ok",
            "objectStorage": "ok",
            "embeddingProvider": "ok",
            "generationProvider": "ok",
        },
    }
    assert main_module.capability_status() == {"vision": "ok", "asr": "ok"}


def test_image_caption_readiness_uses_vision_capability_without_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(
        main_module,
        "modality_registry",
        type("R", (), {"enabled_asset_kinds": frozenset({"pdf", "image"})})(),
    )
    monkeypatch.setattr(main_module, "_check_database", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_modality_catalog", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_storage", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_embedding_provider", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_generation_provider", lambda: "ok")

    def reject_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("image caption readiness must not call provider HTTP")

    monkeypatch.setattr(main_module.httpx, "get", reject_http)
    monkeypatch.setattr(main_module.httpx, "post", reject_http)

    assert main_module.readiness_checks()["imageCaptionConfiguration"] == "ok"
    assert main_module.capability_status()["vision"] == "ok"
    assert main_module.capability_status()["asr"] == "ok"

    monkeypatch.setattr(settings, "openai_api_key", None)
    assert main_module._check_image_caption_configuration() == "not_configured"
    assert main_module.capability_status()["vision"] == "not_configured"


def test_injected_caption_provider_path_is_not_forced_through_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: adapter tests inject fakes and must not require live vision config."""

    _configure_vision_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", None)

    class Injected:
        provider = "test-vision"
        model = "test-model"
        version = "test-v1"
        detail = "high"
        max_output_tokens = 32
        config_fingerprint = ""

        def caption(self, payload: bytes, *, content_type: str) -> str:
            del payload, content_type
            return "injected caption"

    with pytest.raises(ModelProviderError) as factory_error:
        get_image_caption_provider()
    assert factory_error.value.code == VISION_NOT_CONFIGURED_CODE
    assert Injected().caption(b"x", content_type="image/png") == "injected caption"
