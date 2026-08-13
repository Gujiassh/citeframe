from __future__ import annotations

import httpx
import pytest

import ai_pdf_api.main as main_module
from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.capabilities import (
    asr_profile_snapshot_fields,
    build_capability_registry,
)
from ai_pdf_api.services.capability_errors import (
    ASR_NOT_CONFIGURED_CODE,
    ASR_PROVIDER_ERROR_CODE,
    ASR_SEGMENT_CONTRACT_CODE,
    ASR_TIMEOUT_CODE,
    asr_api_key_configured,
    asr_capability_status,
    normalize_asr_api_key,
    require_asr_capability,
    require_configured_asr_profile,
)
from ai_pdf_api.services.providers import ModelProviderError


def _configure_asr_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "capability_fingerprint_pepper",
        "local-development-capability-fingerprint-pepper",
    )
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai-asr")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "asr_provider", "openai")
    monkeypatch.setattr(settings, "asr_model", "whisper-1")
    monkeypatch.setattr(settings, "asr_version", "asr-v1")
    monkeypatch.setattr(settings, "asr_timeout_seconds", 90.0)
    monkeypatch.setattr(settings, "asr_max_duration_seconds", 480.0)
    monkeypatch.setattr(settings, "asr_max_file_bytes", 12 * 1024 * 1024)
    monkeypatch.setattr(settings, "generation_provider", "openai")
    monkeypatch.setattr(settings, "generation_model", "gpt-5.5")
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)
    monkeypatch.setattr(settings, "embedding_version", "embedding-v1")
    monkeypatch.setattr(settings, "image_caption_provider", "openai")
    monkeypatch.setattr(settings, "image_caption_model", "gpt-5.5")


def test_configured_asr_profile_is_typed_and_does_not_transcribe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_asr_baseline(monkeypatch)
    profile = require_configured_asr_profile()
    same = require_asr_capability()

    assert profile.capability == "asr"
    assert profile.provider == "openai"
    assert profile.model == "whisper-1"
    assert profile.adapter_version == "asr-openai-transcriptions-v1"
    assert profile.model_version == "asr-v1"
    assert profile.configured is True
    assert profile.limits == {
        "timeoutSeconds": 90.0,
        "maxDurationSeconds": 480.0,
        "maxFileBytes": 12 * 1024 * 1024,
    }
    assert same.config_fingerprint == profile.config_fingerprint
    assert asr_capability_status() == "ok"
    assert not hasattr(profile, "transcribe")
    snapshot = asr_profile_snapshot_fields(profile)
    assert snapshot["asrProfileFingerprint"] == profile.config_fingerprint
    public = profile.public_metadata()
    assert "endpointIdentifier" not in public
    assert "sk-test-openai-asr" not in str(public)


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_asr_blank_or_whitespace_key_fails_closed_before_http(
    monkeypatch: pytest.MonkeyPatch,
    missing_key: str | None,
) -> None:
    _configure_asr_baseline(monkeypatch)
    monkeypatch.setattr(settings, "openai_api_key", missing_key)

    http_calls: list[str] = []

    def reject_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        http_calls.append("called")
        raise AssertionError("unconfigured ASR must not call provider HTTP")

    monkeypatch.setattr(httpx, "post", reject_http)
    monkeypatch.setattr(httpx, "get", reject_http)
    monkeypatch.setattr(main_module.httpx, "get", reject_http)
    monkeypatch.setattr(main_module.httpx, "post", reject_http)

    assert normalize_asr_api_key(missing_key) is None
    assert asr_api_key_configured(missing_key) is False
    profile = build_capability_registry().resolve("asr")
    assert profile.configured is False
    assert asr_capability_status() == "not_configured"
    assert main_module.capability_status()["asr"] == "not_configured"

    with pytest.raises(ModelProviderError) as captured:
        require_asr_capability()
    assert captured.value.code == ASR_NOT_CONFIGURED_CODE
    if missing_key:
        assert missing_key not in captured.value.message
    assert http_calls == []


def test_asr_secret_timeout_and_limit_drift_change_fingerprint_without_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_asr_baseline(monkeypatch)
    baseline = build_capability_registry().resolve("asr").config_fingerprint

    monkeypatch.setattr(settings, "openai_api_key", "sk-rotated-asr")
    secret_drift = build_capability_registry().resolve("asr")
    assert secret_drift.config_fingerprint != baseline
    assert "sk-rotated-asr" not in secret_drift.config_fingerprint
    assert "sk-rotated-asr" not in str(secret_drift.public_metadata())

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai-asr")
    monkeypatch.setattr(settings, "asr_timeout_seconds", 30.0)
    timeout_drift = build_capability_registry().resolve("asr")
    assert timeout_drift.config_fingerprint != baseline

    monkeypatch.setattr(settings, "asr_timeout_seconds", 90.0)
    monkeypatch.setattr(settings, "asr_model", "whisper-large-v3")
    model_drift = build_capability_registry().resolve("asr")
    assert model_drift.config_fingerprint != baseline


def test_asr_error_codes_are_frozen() -> None:
    assert ASR_NOT_CONFIGURED_CODE == "asr_not_configured"
    assert ASR_TIMEOUT_CODE == "asr_timeout"
    assert ASR_PROVIDER_ERROR_CODE == "asr_provider_error"
    assert ASR_SEGMENT_CONTRACT_CODE == "asr_segment_contract_invalid"


def test_asr_capability_coexists_with_s0_audio_video_registry() -> None:
    """ASR capability freeze is independent; S0 enables audio/video kinds."""
    registry = main_module.modality_registry
    assert "audio" in registry.enabled_asset_kinds
    assert "video" in registry.enabled_asset_kinds
