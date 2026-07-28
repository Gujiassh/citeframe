from __future__ import annotations

import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai_pdf_api.core.research_observability as observability


def _sample_value(metric, suffix: str, labels: dict[str, str]) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix) and sample.labels == labels:
                return float(sample.value)
    return 0.0


def _install_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    observability.install_research_tracer_for_tests(provider.get_tracer("test.research"))
    return exporter


def test_span_names_attributes_and_errors_are_text_free(caplog: pytest.LogCaptureFixture) -> None:
    exporter = _install_exporter()
    target = logging.getLogger("test.research.telemetry")
    secret = "SECRET prompt and raw Evidence payload"

    with caplog.at_level(logging.INFO, logger=target.name):
        with pytest.raises(RuntimeError, match="SECRET"):
            with observability.research_span(
                "research.provider",
                {
                    "research.run_id": "run-1",
                    "research.node": "researcher",
                    "research.question": secret,
                    "research.prompt_version_id": "prompt-version-1",
                },
            ):
                observability.research_log(
                    target,
                    tag="research_provider",
                    status="started",
                    fields={"run_id": "run-1", "question": secret},
                )
                raise RuntimeError(secret)

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["research.provider"]
    assert spans[0].attributes["research.run_id"] == "run-1"
    assert spans[0].attributes["research.prompt_version_id"] == "prompt-version-1"
    assert "research.question" not in spans[0].attributes
    assert spans[0].events == ()
    assert secret not in str(spans[0].status)
    assert secret not in caplog.text
    assert "tag=research_provider status=started run_id=run-1 trace_id=" in caplog.text


def test_metric_helpers_accept_only_closed_low_cardinality_labels() -> None:
    step_labels = {"step_kind": "verifier", "outcome": "success"}
    before_step = _sample_value(observability.metrics.RESEARCH_STEPS, "_total", step_labels)
    before_retry = _sample_value(
        observability.metrics.RESEARCH_RECOVERY,
        "_total",
        {"kind": "retry"},
    )
    before_error = _sample_value(
        observability.metrics.RESEARCH_STEPS,
        "_total",
        {"step_kind": "verifier", "outcome": "error"},
    )
    before_recovered = _sample_value(
        observability.metrics.RESEARCH_RECOVERY,
        "_total",
        {"kind": "recovered"},
    )
    before_series = len(observability.metrics.RESEARCH_STEPS._metrics)

    observability.observe_research_step("verifier", "success", 0.01, 3)
    observability.observe_research_step("dynamic-user-step", "success", 0.01, 3)
    observability.observe_research_step("verifier", "error", 0.01)
    observability.observe_research_recovery("retry")
    observability.observe_research_recovery("recovered")
    observability.observe_research_recovery("dynamic-user-reason")

    assert _sample_value(observability.metrics.RESEARCH_STEPS, "_total", step_labels) == before_step + 1
    assert _sample_value(
        observability.metrics.RESEARCH_RECOVERY,
        "_total",
        {"kind": "retry"},
    ) == before_retry + 1
    assert _sample_value(
        observability.metrics.RESEARCH_STEPS,
        "_total",
        {"step_kind": "verifier", "outcome": "error"},
    ) == before_error + 1
    assert _sample_value(
        observability.metrics.RESEARCH_RECOVERY,
        "_total",
        {"kind": "recovered"},
    ) == before_recovered + 1
    assert len(observability.metrics.RESEARCH_STEPS._metrics) <= before_series + 2
    assert all("dynamic-user" not in str(key) for key in observability.metrics.RESEARCH_STEPS._metrics)


def test_log_tag_status_are_closed_and_forbidden_fields_are_omitted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = logging.getLogger("test.research.closed-log")
    with caplog.at_level(logging.INFO, logger=target.name):
        observability.research_log(
            target,
            tag="dynamic secret tag",
            status="started",
            fields={"run_id": "run-1"},
        )
        observability.research_log(
            target,
            tag="research_step",
            status="dynamic secret status",
            fields={"run_id": "run-1"},
        )
        observability.research_log(
            target,
            tag="research_step",
            status="succeeded",
            fields={"run_id": "run-1", "content": "SECRET"},
        )

    assert caplog.text.count("tag=research_step status=succeeded run_id=run-1") == 1
    assert "dynamic secret" not in caplog.text
    assert "SECRET" not in caplog.text


def test_exporter_disabled_and_metric_failures_do_not_change_business_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert observability.configure_research_observability(
        service_name="citeframe-test",
        endpoint=None,
    ) is True

    class BrokenMetric:
        def labels(self, **_kwargs):
            raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(observability.metrics, "RESEARCH_STEPS", BrokenMetric())
    observability.observe_research_step("verifier", "success", 0.01)
    with observability.research_span(
        "research.run",
        {"research.run_id": "run-1"},
    ):
        result = "business-result"

    assert result == "business-result"


def test_tracer_failure_is_isolated_from_business_flow() -> None:
    class BrokenTracer:
        def start_as_current_span(self, *_args, **_kwargs):
            raise RuntimeError("exporter unavailable")

    observability.install_research_tracer_for_tests(BrokenTracer())
    with observability.research_span(
        "research.run",
        {"research.run_id": "run-1"},
    ):
        result = "business-result"

    assert result == "business-result"
