"""Failure-isolated Research telemetry with a closed, text-free contract."""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from ai_pdf_api.core import metrics

logger = logging.getLogger(__name__)

SPAN_NAMES = frozenset(
    {"research.run", "research.step", "research.tool", "research.provider", "research.publish"}
)
STEP_KINDS = frozenset(
    {
        "planner",
        "plan_approval_gate",
        "researcher",
        "join",
        "verifier",
        "critic",
        "conflict_decision_gate",
        "synthesizer",
        "artifact_publisher",
    }
)
TOOL_NAMES = frozenset({"evidence.search", "evidence.load"})
PROVIDER_NODES = frozenset({"planner", "researcher", "verifier", "critic", "synthesizer"})
OUTCOMES = frozenset({"success", "error", "cancelled", "abandoned", "timeout", "waiting"})
RUN_OUTCOMES = frozenset({"success", "error", "cancelled", "waiting"})
RECOVERY_KINDS = frozenset({"retry", "abandoned", "timeout", "recovered"})
SSE_OUTCOMES = frozenset({"reconnect", "history_unavailable"})
DIRECTIONS = frozenset({"input", "output"})

SAFE_ATTRIBUTE_KEYS = frozenset(
    {
        "research.run_id",
        "research.workspace_id",
        "research.step_id",
        "research.attempt_id",
        "research.execution_snapshot_id",
        "research.workflow_version_id",
        "research.prompt_version_id",
        "research.step_kind",
        "research.tool_name",
        "research.node",
        "research.outcome",
        "research.reason_code",
        "research.attempt_number",
        "research.evidence_count",
        "research.input_tokens",
        "research.output_tokens",
        "research.cost_microunits",
        "research.duration_ms",
        "research.reclaimed_count",
        "research.parallel_researchers",
        "research.parallel_speedup_ratio",
        "research.snapshot_sha256",
    }
)
SAFE_LOG_FIELDS = frozenset(
    {
        "run_id",
        "workspace_id",
        "step_id",
        "attempt_id",
        "execution_snapshot_id",
        "step_kind",
        "tool_name",
        "node",
        "attempt_number",
        "outcome",
        "reason_code",
        "duration_ms",
        "evidence_count",
        "input_tokens",
        "output_tokens",
        "cost_microunits",
        "reclaimed_count",
    }
)
LOG_TAGS = frozenset(
    {
        "research_run",
        "research_step",
        "research_tool",
        "research_provider",
        "research_publish",
        "research_retry",
        "research_recovery",
        "research_telemetry",
    }
)
LOG_STATUSES = frozenset(
    {
        "started",
        "succeeded",
        "error",
        "waiting",
        "retry",
        "recovered",
        "disabled",
        "cancelled",
        "abandoned",
        "timeout",
    }
)
LOG_FIELD_ORDER = (
    "run_id",
    "workspace_id",
    "step_id",
    "attempt_id",
    "execution_snapshot_id",
    "step_kind",
    "tool_name",
    "node",
    "attempt_number",
    "outcome",
    "reason_code",
    "duration_ms",
    "evidence_count",
    "input_tokens",
    "output_tokens",
    "cost_microunits",
    "reclaimed_count",
)
SAFE_REASON_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class TraceCorrelation:
    trace_id: str | None
    span_id: str | None


class ResearchSpan:
    def __init__(self, span: Span | None, started: float) -> None:
        self._span = span
        self._started = started
        self._outcome_set = False

    @property
    def duration_ms(self) -> float:
        return max(0.0, (time.perf_counter() - self._started) * 1000)

    def set_attributes(self, attributes: Mapping[str, object]) -> None:
        if self._span is None:
            return
        for key, value in _safe_attributes(attributes).items():
            try:
                self._span.set_attribute(key, value)
                if key == "research.outcome":
                    self._outcome_set = True
            except Exception:
                continue


_lock = threading.Lock()
_tracer: Tracer = trace.get_tracer("citeframe.research")
_owned_provider: TracerProvider | None = None


def configure_research_observability(
    *,
    service_name: str,
    endpoint: str | None,
    export_timeout_seconds: float = 5.0,
) -> bool:
    """Install an isolated tracer; no endpoint means an SDK no-op exporter."""

    global _tracer, _owned_provider
    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": "citeframe",
                }
            )
        )
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                timeout=export_timeout_seconds,
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
        with _lock:
            previous = _owned_provider
            _owned_provider = provider
            _tracer = provider.get_tracer("citeframe.research")
        if previous is not None:
            try:
                previous.shutdown()
            except Exception:
                pass
        return True
    except Exception as error:
        try:
            logger.warning(
                "tag=research_telemetry status=disabled reason_code=%s",
                type(error).__name__,
            )
        except Exception:
            pass
        return False


def install_research_tracer_for_tests(tracer: Tracer) -> None:
    global _tracer
    with _lock:
        _tracer = tracer


@contextmanager
def research_span(
    name: str,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[ResearchSpan]:
    if name not in SPAN_NAMES:
        yield ResearchSpan(None, time.perf_counter())
        return
    started = time.perf_counter()
    context_manager = None
    span: Span | None = None
    try:
        context_manager = _tracer.start_as_current_span(
            name,
            attributes=_safe_attributes(attributes or {}),
            record_exception=False,
            set_status_on_exception=False,
        )
        span = context_manager.__enter__()
    except Exception:
        context_manager = None
        span = None
    observed = ResearchSpan(span, started)
    error: BaseException | None = None
    try:
        yield observed
    except BaseException as caught:
        error = caught
        if span is not None:
            try:
                span.set_attribute("research.outcome", "error")
                span.set_attribute("research.reason_code", type(caught).__name__)
                span.set_status(Status(StatusCode.ERROR))
            except Exception:
                pass
        raise
    else:
        if span is not None and not observed._outcome_set:
            try:
                span.set_attribute("research.outcome", "success")
                span.set_status(Status(StatusCode.OK))
            except Exception:
                pass
    finally:
        observed.set_attributes({"research.duration_ms": observed.duration_ms})
        if context_manager is not None:
            try:
                if error is None:
                    context_manager.__exit__(None, None, None)
                else:
                    context_manager.__exit__(type(error), error, error.__traceback__)
            except Exception:
                pass


def trace_correlation() -> TraceCorrelation:
    try:
        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return TraceCorrelation(None, None)
        return TraceCorrelation(f"{context.trace_id:032x}", f"{context.span_id:016x}")
    except Exception:
        return TraceCorrelation(None, None)


def research_log(
    target: logging.Logger,
    *,
    tag: str,
    status: str,
    level: int = logging.INFO,
    fields: Mapping[str, object] | None = None,
) -> None:
    try:
        if tag not in LOG_TAGS or status not in LOG_STATUSES:
            return
        values = fields or {}
        parts = [f"tag={_token(tag)}", f"status={_token(status)}"]
        for key in LOG_FIELD_ORDER:
            if key in values and key in SAFE_LOG_FIELDS and _safe_log_value(key, values[key]):
                parts.append(f"{key}={_token(values[key])}")
        correlation = trace_correlation()
        if correlation.trace_id:
            parts.append(f"trace_id={correlation.trace_id}")
        if correlation.span_id:
            parts.append(f"span_id={correlation.span_id}")
        target.log(level, " ".join(parts))
    except Exception:
        return


def research_run_started() -> None:
    _metric(lambda: metrics.RESEARCH_ACTIVE_RUNS.inc())


def research_run_finished(outcome: str) -> None:
    if outcome not in RUN_OUTCOMES:
        return
    _metric(lambda: metrics.RESEARCH_ACTIVE_RUNS.dec())
    _metric(lambda: metrics.RESEARCH_RUNS.labels(outcome=outcome).inc())


def observe_research_step(step_kind: str, outcome: str, duration_seconds: float, evidence_count: int = 0) -> None:
    if step_kind not in STEP_KINDS or outcome not in OUTCOMES:
        return
    _metric(lambda: metrics.RESEARCH_STEPS.labels(step_kind=step_kind, outcome=outcome).inc())
    _metric(
        lambda: metrics.RESEARCH_STEP_DURATION.labels(
            step_kind=step_kind,
            outcome=outcome,
        ).observe(max(0.0, duration_seconds))
    )
    if evidence_count >= 0:
        _metric(
            lambda: metrics.RESEARCH_EVIDENCE_COUNT.labels(step_kind=step_kind).observe(
                evidence_count
            )
        )


def observe_research_tool(tool_name: str, outcome: str, duration_seconds: float, evidence_count: int = 0) -> None:
    if tool_name not in TOOL_NAMES or outcome not in OUTCOMES:
        return
    _metric(lambda: metrics.RESEARCH_TOOL_CALLS.labels(tool_name=tool_name, outcome=outcome).inc())
    _metric(
        lambda: metrics.RESEARCH_TOOL_DURATION.labels(
            tool_name=tool_name,
            outcome=outcome,
        ).observe(max(0.0, duration_seconds))
    )
    if evidence_count >= 0:
        _metric(lambda: metrics.RESEARCH_EVIDENCE_COUNT.labels(step_kind="researcher").observe(evidence_count))


def observe_research_provider(
    node: str,
    outcome: str,
    duration_seconds: float,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_microunits: int = 0,
) -> None:
    if node not in PROVIDER_NODES or outcome not in OUTCOMES:
        return
    _metric(lambda: metrics.RESEARCH_PROVIDER_CALLS.labels(node=node, outcome=outcome).inc())
    _metric(
        lambda: metrics.RESEARCH_PROVIDER_DURATION.labels(
            node=node,
            outcome=outcome,
        ).observe(max(0.0, duration_seconds))
    )
    _metric(lambda: metrics.RESEARCH_TOKENS.labels(node=node, direction="input").observe(max(0, input_tokens)))
    _metric(lambda: metrics.RESEARCH_TOKENS.labels(node=node, direction="output").observe(max(0, output_tokens)))
    _metric(lambda: metrics.RESEARCH_COST_MICROUNITS.labels(node=node).observe(max(0, cost_microunits)))


def observe_research_recovery(kind: str, count: int = 1) -> None:
    if kind not in RECOVERY_KINDS or count < 1:
        return
    _metric(lambda: metrics.RESEARCH_RECOVERY.labels(kind=kind).inc(count))


def observe_parallel_speedup(ratio: float) -> None:
    if not math.isfinite(ratio) or ratio < 1:
        return
    _metric(lambda: metrics.RESEARCH_PARALLEL_SPEEDUP.observe(ratio))


def observe_research_sse(outcome: str) -> None:
    if outcome not in SSE_OUTCOMES:
        return
    _metric(lambda: metrics.RESEARCH_SSE_CONTRACT.labels(outcome=outcome).inc())


def _safe_attributes(attributes: Mapping[str, object]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        normalized = str(key)
        if normalized not in SAFE_ATTRIBUTE_KEYS:
            continue
        if _safe_attribute_value(normalized, value):
            safe[normalized] = value
    return safe


def _safe_scalar(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return math.isfinite(value) and value >= 0
    if isinstance(value, str):
        return bool(value) and len(value) <= 160 and not any(character.isspace() for character in value)
    return False


def _safe_attribute_value(key: str, value: object) -> bool:
    if not _safe_scalar(value):
        return False
    if key == "research.step_kind":
        return value in STEP_KINDS
    if key == "research.tool_name":
        return value in TOOL_NAMES
    if key == "research.node":
        return value in PROVIDER_NODES
    if key == "research.outcome":
        return value in OUTCOMES or value in RUN_OUTCOMES
    if key == "research.reason_code":
        return isinstance(value, str) and SAFE_REASON_CODE.fullmatch(value) is not None
    return True


def _safe_log_value(key: str, value: object) -> bool:
    attribute_key = {
        "step_kind": "research.step_kind",
        "tool_name": "research.tool_name",
        "node": "research.node",
        "outcome": "research.outcome",
        "reason_code": "research.reason_code",
    }.get(key)
    return _safe_attribute_value(attribute_key, value) if attribute_key else _safe_scalar(value)


def _token(value: object) -> str:
    rendered = str(value).strip()
    return "_".join(rendered.split())[:160] or "unknown"


def _metric(operation) -> None:
    try:
        operation()
    except Exception:
        return
