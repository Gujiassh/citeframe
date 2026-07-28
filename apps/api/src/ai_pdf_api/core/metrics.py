from __future__ import annotations

import time
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_pdf_api.models import IngestionJob

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "ai_pdf_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "ai_pdf_http_request_duration_seconds",
    "Full HTTP response lifetime by route template.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 180),
)
PROVIDER_REQUESTS = Counter(
    "ai_pdf_provider_requests_total",
    "Embedding and generation provider requests.",
    ("provider", "kind", "outcome"),
)
PROVIDER_REQUEST_DURATION = Histogram(
    "ai_pdf_provider_request_duration_seconds",
    "Embedding and generation provider operation lifetime, including stream consumption.",
    ("provider", "kind"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 180),
)
RETRIEVAL_REQUESTS = Counter(
    "ai_pdf_retrieval_requests_total",
    "Retrieval requests by strategy and outcome.",
    ("strategy", "outcome"),
)
RETRIEVAL_DURATION = Histogram(
    "ai_pdf_retrieval_duration_seconds",
    "Total retrieval duration by strategy and outcome.",
    ("strategy", "outcome"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 1, 2.5, 5, 10),
)
RETRIEVAL_RESULTS = Histogram(
    "ai_pdf_retrieval_results",
    "Number of pages returned by retrieval.",
    ("strategy",),
    buckets=(0, 1, 2, 3, 4, 6, 10, 20),
)
STORAGE_OPERATIONS = Counter(
    "ai_pdf_storage_operations_total",
    "Object storage operations.",
    ("operation", "outcome"),
)
STORAGE_OPERATION_DURATION = Histogram(
    "ai_pdf_storage_operation_duration_seconds",
    "Object storage operation lifetime, including stream consumption.",
    ("operation",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
INGESTION_JOBS = Gauge(
    "ai_pdf_ingestion_jobs",
    "Current ingestion job count by status.",
    ("status",),
)
INGESTION_METRICS_REFRESH_FAILURES = Counter(
    "ai_pdf_ingestion_metrics_refresh_failures_total",
    "Failed ingestion queue metric refreshes.",
)

RESEARCH_RUNS = Counter(
    "ai_pdf_research_runs_total",
    "Research processing sessions observed by outcome.",
    ("outcome",),
)
RESEARCH_ACTIVE_RUNS = Gauge(
    "ai_pdf_research_active_runs",
    "Research processing sessions active in this process.",
)
RESEARCH_STEPS = Counter(
    "ai_pdf_research_steps_total",
    "Research Steps observed by kind and outcome.",
    ("step_kind", "outcome"),
)
RESEARCH_STEP_DURATION = Histogram(
    "ai_pdf_research_step_duration_seconds",
    "Research Step duration by kind and outcome.",
    ("step_kind", "outcome"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)
RESEARCH_TOOL_CALLS = Counter(
    "ai_pdf_research_tool_calls_total",
    "Research Evidence tool calls by canonical name and outcome.",
    ("tool_name", "outcome"),
)
RESEARCH_TOOL_DURATION = Histogram(
    "ai_pdf_research_tool_duration_seconds",
    "Research Evidence tool duration by canonical name and outcome.",
    ("tool_name", "outcome"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
RESEARCH_PROVIDER_CALLS = Counter(
    "ai_pdf_research_provider_calls_total",
    "Research provider calls by node and outcome.",
    ("node", "outcome"),
)
RESEARCH_PROVIDER_DURATION = Histogram(
    "ai_pdf_research_provider_duration_seconds",
    "Research provider call duration by node and outcome.",
    ("node", "outcome"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
RESEARCH_RECOVERY = Counter(
    "ai_pdf_research_recovery_total",
    "Research retry, timeout, abandon, and recovery observations.",
    ("kind",),
)
RESEARCH_EVIDENCE_COUNT = Histogram(
    "ai_pdf_research_evidence_count",
    "Evidence handles observed at Research Step boundaries.",
    ("step_kind",),
    buckets=(0, 1, 2, 4, 8, 12, 20, 40, 64, 100),
)
RESEARCH_TOKENS = Histogram(
    "ai_pdf_research_tokens",
    "Estimated or actual Research tokens by node and direction.",
    ("node", "direction"),
    buckets=(0, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768),
)
RESEARCH_COST_MICROUNITS = Histogram(
    "ai_pdf_research_cost_microunits",
    "Research provider cost observations in currency microunits.",
    ("node",),
    buckets=(0, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000),
)
RESEARCH_PARALLEL_SPEEDUP = Histogram(
    "ai_pdf_research_parallel_speedup_ratio",
    "Researcher serial-duration sum divided by parallel wall duration.",
    buckets=(1, 1.1, 1.25, 1.5, 2, 2.5, 3, 4, 8, 16),
)
RESEARCH_SSE_CONTRACT = Counter(
    "ai_pdf_research_sse_contract_total",
    "Research SSE reconnect and history availability observations.",
    ("outcome",),
)

INGESTION_JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


@contextmanager
def observe_provider_request(provider: str, kind: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except GeneratorExit:
        PROVIDER_REQUESTS.labels(provider=provider, kind=kind, outcome="cancelled").inc()
        logger.info("provider_request_cancelled provider=%s kind=%s", provider, kind)
        raise
    except Exception as error:
        PROVIDER_REQUESTS.labels(provider=provider, kind=kind, outcome="error").inc()
        logger.error(
            "provider_request_failed provider=%s kind=%s error_type=%s",
            provider,
            kind,
            type(error).__name__,
        )
        raise
    else:
        PROVIDER_REQUESTS.labels(provider=provider, kind=kind, outcome="success").inc()
    finally:
        PROVIDER_REQUEST_DURATION.labels(provider=provider, kind=kind).observe(
            time.perf_counter() - started
        )


@contextmanager
def observe_storage_operation(operation: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except GeneratorExit:
        STORAGE_OPERATIONS.labels(operation=operation, outcome="cancelled").inc()
        logger.info("storage_operation_cancelled operation=%s", operation)
        raise
    except Exception as error:
        STORAGE_OPERATIONS.labels(operation=operation, outcome="error").inc()
        logger.error(
            "storage_operation_failed operation=%s error_type=%s",
            operation,
            type(error).__name__,
        )
        raise
    else:
        STORAGE_OPERATIONS.labels(operation=operation, outcome="success").inc()
    finally:
        STORAGE_OPERATION_DURATION.labels(operation=operation).observe(
            time.perf_counter() - started
        )


def observe_retrieval(strategy: str, outcome: str, duration_ms: float, result_count: int) -> None:
    RETRIEVAL_REQUESTS.labels(strategy=strategy, outcome=outcome).inc()
    RETRIEVAL_DURATION.labels(strategy=strategy, outcome=outcome).observe(duration_ms / 1000)
    if outcome == "success":
        RETRIEVAL_RESULTS.labels(strategy=strategy).observe(result_count)


def refresh_ingestion_job_metrics(db: Session) -> None:
    counts = dict(
        db.execute(
            select(IngestionJob.status, func.count(IngestionJob.id)).group_by(IngestionJob.status)
        ).all()
    )
    for status in INGESTION_JOB_STATUSES:
        INGESTION_JOBS.labels(status=status).set(counts.get(status, 0))
