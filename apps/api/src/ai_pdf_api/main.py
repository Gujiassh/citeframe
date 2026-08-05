from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from ai_pdf_api.core.logging import configure_application_logging
from ai_pdf_api.core.metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS,
    INGESTION_METRICS_REFRESH_FAILURES,
    refresh_ingestion_job_metrics,
)
from ai_pdf_api.core.research_observability import configure_research_observability
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.modalities.catalog import validate_database_catalog
from ai_pdf_api.modalities.registry import build_production_registry
from ai_pdf_api.routers.assets import router as assets_router
from ai_pdf_api.routers.auth import router as auth_router
from ai_pdf_api.routers.chat import router as chat_router
from ai_pdf_api.routers.evaluation import router as evaluation_router
from ai_pdf_api.routers.jobs import router as jobs_router
from ai_pdf_api.routers.notes import router as notes_router
from ai_pdf_api.routers.research import router as research_router
from ai_pdf_api.routers.workspaces import router as workspaces_router
from ai_pdf_api.services.storage import build_storage_client

configure_application_logging()
logger = logging.getLogger(__name__)
modality_registry = build_production_registry()


def _configure_research_telemetry() -> bool:
    return configure_research_observability(
        service_name=settings.research_otel_service_name,
        endpoint=settings.research_otel_endpoint,
        export_timeout_seconds=settings.research_otel_export_timeout_seconds,
    )


RESEARCH_OBSERVABILITY_CONFIGURED = _configure_research_telemetry()

HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}


class HttpMetricsMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        response_status = 500
        completed = False

        async def observe_send(message: dict[str, Any]) -> None:
            nonlocal response_status, completed
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            await self.app(scope, receive, observe_send)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            raw_method = str(scope.get("method", "other")).upper()
            method = raw_method if raw_method in HTTP_METHODS else "other"
            status_label = str(response_status if completed else 499 if response_status < 500 else 500)
            HTTP_REQUESTS.labels(method=method, route=route_template, status=status_label).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route_template).observe(
                time.perf_counter() - started
            )


app = FastAPI(title="Citeframe API")
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(assets_router)
app.include_router(chat_router)
app.include_router(jobs_router)
app.include_router(notes_router)
app.include_router(research_router)
app.include_router(evaluation_router)


app.add_middleware(HttpMetricsMiddleware)


def _check_database() -> str:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "failed"


def _check_storage() -> str:
    try:
        build_storage_client().list_buckets()
        return "ok"
    except Exception:
        return "failed"


def _check_modality_catalog() -> str:
    try:
        with SessionLocal() as db:
            validate_database_catalog(db, modality_registry)
        return "ok"
    except Exception:
        return "failed"


def _provider_secret_configured(secret: str | None) -> bool:
    """Shared strip semantics with provider constructors: blank/whitespace is missing."""

    return bool(secret and secret.strip())


def _check_embedding_provider() -> str:
    try:
        if settings.embedding_provider == "ollama":
            response = httpx.get(
                f"{settings.ollama_base_url.rstrip('/')}/api/tags",
                timeout=min(settings.embedding_timeout_seconds, 5.0),
            )
        else:
            # Do not call /models when the OpenAI embedding key is blank/whitespace.
            if not _provider_secret_configured(settings.openai_api_key):
                return "not_configured"
            base_url = settings.openai_api_base.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            response = httpx.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key.strip()}"},
                timeout=min(settings.embedding_timeout_seconds, 5.0),
            )
        return "ok" if response.is_success else "failed"
    except Exception:
        return "failed"


def _check_generation_provider() -> str:
    if settings.generation_provider == "openai":
        return "ok" if _provider_secret_configured(settings.openai_api_key) else "not_configured"
    if settings.generation_provider == "deepseek":
        return "ok" if _provider_secret_configured(settings.deepseek_api_key) else "not_configured"
    return "not_configured"


def _check_image_caption_configuration() -> str:
    # Local vision/image-caption readiness only; never probe provider HTTP or expose secrets.
    from ai_pdf_api.services.capability_errors import vision_readiness_status

    status = vision_readiness_status()
    if status == "ok":
        # Keep the historical field-level guards so empty model/version/base still fail closed.
        configured = (
            settings.image_caption_provider == "openai"
            and bool(settings.image_caption_model.strip())
            and bool(settings.image_caption_version.strip())
            and bool(settings.openai_api_key and settings.openai_api_key.strip())
            and bool(settings.openai_api_base.strip())
        )
        return "ok" if configured else "not_configured"
    return "not_configured"


def capability_status() -> dict[str, str]:
    """Bounded capability availability for operators; excluded from readiness hard-gate values."""

    from ai_pdf_api.services.capability_errors import asr_capability_status, vision_readiness_status

    vision = vision_readiness_status()
    return {
        "vision": "ok" if vision == "ok" else "not_configured",
        "asr": asr_capability_status(),
    }


def readiness_checks() -> dict[str, str]:
    checks = {
        "database": _check_database(),
        "modalityCatalog": _check_modality_catalog(),
        "objectStorage": _check_storage(),
        "embeddingProvider": _check_embedding_provider(),
        "generationProvider": _check_generation_provider(),
    }
    if "image" in modality_registry.enabled_asset_kinds:
        checks["imageCaptionConfiguration"] = _check_image_caption_configuration()
    return checks


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/health/ready")
def readiness(response: Response) -> dict[str, object]:
    checks = readiness_checks()
    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    # Keep historical readiness body shape. capability_status() is the explicit
    # vision/ASR status surface and must not hard-fail readiness on ASR=unavailable.
    return {"status": "ok" if ready else "not_ready", "service": "api", "checks": checks}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    try:
        with SessionLocal() as db:
            refresh_ingestion_job_metrics(db)
    except Exception as error:
        INGESTION_METRICS_REFRESH_FAILURES.inc()
        logger.error("metrics_refresh_failed metric=ingestion_jobs error_type=%s", type(error).__name__)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
