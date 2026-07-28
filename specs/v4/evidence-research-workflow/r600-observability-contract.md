# R600 Research Observability Contract

## Status

Approved implementation input under the Owner's autonomous V4 authorization on 2026-07-27. This contract adds telemetry only; it cannot change Research business state, events, budgets, or saved user data.

## Signals

### Traces

Use OpenTelemetry API/SDK with an OTLP HTTP exporter only when an endpoint is configured. Otherwise the same instrumentation runs with a local no-op exporter. Spans are created for:

- `research.run`
- `research.step`
- `research.tool`
- `research.provider`
- `research.publish`

Allowed attributes are stable IDs, closed enums, version IDs/hashes, attempt number, counts, durations, token/cost aggregates, and safe reason codes. Question/claim/evidence text, prompts, raw provider/tool payloads, object keys, session data, and secrets are forbidden.

A database-polled restart cannot preserve an in-memory parent span without changing the frozen R000 schema. Each processing session therefore creates a new trace and correlates through `research.run_id`, `research.step_id`, and the persisted attempt/event IDs. Telemetry loss never changes ledger behavior.

### Prometheus

Metrics use only closed, low-cardinality labels. IDs and version hashes never become metric labels.

- run outcomes and active runs
- step outcomes and duration by step kind
- tool calls and duration by tool name/outcome
- provider calls and duration by node/outcome
- retry/abandon/timeout/recovery counts
- Evidence counts, token counts, cost microunits, and parallel speedup histograms
- SSE reconnect/history-unavailable contract counters where observable

Ledger tables remain the cost/recovery fact source; metrics are process observations and can reset.

### Logs

Every Research runtime log is one grep-friendly line, for example:

```text
tag=research_step status=succeeded run_id=... step_id=... attempt_id=... step_kind=verifier duration_ms=42 trace_id=...
```

No nested JSON or full object logging. Logs include `trace_id/span_id` when a span is active and omit text-bearing inputs/outputs.

## Langfuse decision

Langfuse is not a required dependency. The approved adapter boundary is OpenTelemetry/OTLP plus sanitized Evaluation imports. A future Langfuse deployment may consume exported spans or implement a separate development-only exporter, but it cannot become the Research ledger, Evaluation persistence layer, prompt store, or production permission boundary. No Langfuse SDK is added in R600.

## Failure policy

Exporter, metrics, or log formatting failures are isolated from business transactions. Instrumentation must not retry provider/tool work, change a lease, write a core ResearchEvent, alter a budget, or block final Artifact publication.

## Acceptance

- unit tests assert span names and safe attributes;
- metric tests assert closed labels and observations for success/failure/retry/recovery;
- log capture asserts flat correlation fields and forbidden-text absence;
- exporter-disabled execution remains functional;
- R000 hashes and 15-event SSE allowlist remain unchanged.
