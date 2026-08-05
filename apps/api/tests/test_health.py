import asyncio
import logging
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import ai_pdf_api.main as main_module
from ai_pdf_api.core.logging import APPLICATION_HANDLER_NAME
from ai_pdf_api.core.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS


def test_application_logs_use_flat_info_formatter() -> None:
    application_logger = logging.getLogger("ai_pdf_api")
    handler = next(
        item for item in application_logger.handlers if item.get_name() == APPLICATION_HANDLER_NAME
    )
    record = logging.LogRecord(
        name="ai_pdf_api.services.retrieval",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="retrieval_complete strategy=hybrid workspace_id=workspace-1 total_ms=1.250",
        args=(),
        exc_info=None,
    )

    assert application_logger.level == logging.INFO
    assert handler.level == logging.INFO
    assert handler.format(record) == "retrieval_complete strategy=hybrid workspace_id=workspace-1 total_ms=1.250"


def test_research_observability_uses_startup_settings(monkeypatch) -> None:
    captured = {}

    def configure(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(main_module, "configure_research_observability", configure)
    monkeypatch.setattr(main_module.settings, "research_otel_service_name", "citeframe-api-test")
    monkeypatch.setattr(main_module.settings, "research_otel_endpoint", "http://collector.test/v1/traces")
    monkeypatch.setattr(main_module.settings, "research_otel_export_timeout_seconds", 2.5)

    assert main_module._configure_research_telemetry() is True
    assert captured == {
        "service_name": "citeframe-api-test",
        "endpoint": "http://collector.test/v1/traces",
        "export_timeout_seconds": 2.5,
    }


def test_liveness_does_not_require_dependencies() -> None:
    client = TestClient(main_module.app)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_readiness_returns_dependency_status_and_503_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "readiness_checks",
        lambda: {
            "database": "ok",
            "modalityCatalog": "ok",
            "objectStorage": "failed",
            "embeddingProvider": "ok",
            "generationProvider": "ok",
        },
    )
    client = TestClient(main_module.app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "api",
        "checks": {
            "database": "ok",
            "modalityCatalog": "ok",
            "objectStorage": "failed",
            "embeddingProvider": "ok",
            "generationProvider": "ok",
        },
    }


def test_readiness_surfaces_enabled_image_caption_configuration_without_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "modality_registry",
        SimpleNamespace(enabled_asset_kinds=frozenset({"pdf", "image"})),
    )
    monkeypatch.setattr(main_module.settings, "image_caption_provider", "openai")
    monkeypatch.setattr(main_module.settings, "image_caption_model", "gpt-5.5")
    monkeypatch.setattr(main_module.settings, "image_caption_version", "image-caption-v1")
    monkeypatch.setattr(main_module.settings, "openai_api_key", "configured-key")
    monkeypatch.setattr(main_module.settings, "openai_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(main_module, "_check_database", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_modality_catalog", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_storage", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_embedding_provider", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_generation_provider", lambda: "ok")

    def reject_provider_call(*_args, **_kwargs):
        raise AssertionError("Image caption readiness must not call a provider.")

    monkeypatch.setattr(main_module.httpx, "get", reject_provider_call)

    assert main_module.readiness_checks() == {
        "database": "ok",
        "modalityCatalog": "ok",
        "objectStorage": "ok",
        "embeddingProvider": "ok",
        "generationProvider": "ok",
        "imageCaptionConfiguration": "ok",
    }


def test_readiness_fails_when_enabled_image_caption_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "openai_api_key", None)
    monkeypatch.setattr(
        main_module,
        "readiness_checks",
        lambda: {
            "database": "ok",
            "modalityCatalog": "ok",
            "objectStorage": "ok",
            "embeddingProvider": "ok",
            "generationProvider": "ok",
            "imageCaptionConfiguration": main_module._check_image_caption_configuration(),
        },
    )
    client = TestClient(main_module.app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["imageCaptionConfiguration"] == "not_configured"


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_embedding_and_generation_readiness_treat_blank_keys_as_not_configured(
    monkeypatch,
    missing_key: str | None,
) -> None:
    http_calls: list[str] = []

    def reject_http(*_args, **_kwargs):
        http_calls.append("called")
        raise AssertionError("whitespace embedding key must not call /models")

    monkeypatch.setattr(main_module.httpx, "get", reject_http)
    monkeypatch.setattr(main_module.settings, "embedding_provider", "openai")
    monkeypatch.setattr(main_module.settings, "generation_provider", "openai")
    monkeypatch.setattr(main_module.settings, "openai_api_key", missing_key)
    monkeypatch.setattr(main_module.settings, "openai_api_base", "https://api.openai.com/v1")

    assert main_module._check_embedding_provider() == "not_configured"
    assert main_module._check_generation_provider() == "not_configured"
    assert http_calls == []

    monkeypatch.setattr(main_module.settings, "generation_provider", "deepseek")
    monkeypatch.setattr(main_module.settings, "deepseek_api_key", missing_key)
    assert main_module._check_generation_provider() == "not_configured"
    if missing_key:
        # readiness paths never surface the raw secret
        assert missing_key not in str(main_module._check_embedding_provider())


def test_readiness_omits_image_caption_configuration_when_image_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "modality_registry",
        SimpleNamespace(enabled_asset_kinds=frozenset({"pdf"})),
    )
    monkeypatch.setattr(main_module, "_check_database", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_modality_catalog", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_storage", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_embedding_provider", lambda: "ok")
    monkeypatch.setattr(main_module, "_check_generation_provider", lambda: "ok")

    assert "imageCaptionConfiguration" not in main_module.readiness_checks()


def test_metrics_exposes_route_template_and_ingestion_job_counts(monkeypatch) -> None:
    class Result:
        def all(self):
            return [("queued", 3), ("failed", 1)]

    class FakeSession:
        def execute(self, _statement):
            return Result()

    @contextmanager
    def fake_session_local():
        yield FakeSession()

    monkeypatch.setattr(main_module, "SessionLocal", fake_session_local)
    client = TestClient(main_module.app)

    assert client.get("/health/live").status_code == 200
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'ai_pdf_http_requests_total{method="GET",route="/health/live",status="200"}' in response.text
    assert 'ai_pdf_ingestion_jobs{status="queued"} 3.0' in response.text
    assert 'ai_pdf_ingestion_jobs{status="running"} 0.0' in response.text
    assert 'ai_pdf_ingestion_jobs{status="failed"} 1.0' in response.text


def test_http_metrics_cover_full_stream_and_bound_custom_methods(monkeypatch) -> None:
    async def streaming_app(_scope, _receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await asyncio.sleep(0.02)
        await send({"type": "http.response.body", "body": b"second", "more_body": False})

    middleware = main_module.HttpMetricsMiddleware(streaming_app)
    counter = HTTP_REQUESTS.labels(method="other", route="unmatched", status="200")
    duration = HTTP_REQUEST_DURATION.labels(method="other", route="unmatched")
    before_counter = counter._value.get()
    before_sum = duration._sum.get()

    async def receive():
        return {"type": "http.request"}

    async def send(_message):
        return None

    asyncio.run(
        middleware(
            {"type": "http", "method": "X-CUSTOM-METRICS", "path": "/stream"},
            receive,
            send,
        )
    )

    assert counter._value.get() == before_counter + 1
    assert duration._sum.get() - before_sum >= 0.02
