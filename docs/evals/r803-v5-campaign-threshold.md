# Prospective campaign protocol

The [frozen threshold](r803-release-threshold-v1.json), [package](r803-evaluation-package-v5.json), and [six-case suite](r100-research-cases-v2.json) define the protocol. Their original bytes remain unchanged.

A formal campaign requires five prospective paired rounds: six cases in Quick and Research per round, sixty executions total. Each mode is judged independently. Historical diagnostic rounds are excluded. No automatic winner is selected.

Every execution must complete with valid output. Claim support, evidence recall/precision, exact target location, conflict detection, and refusal correctness must reach 1.0; unsupported, extra, negated, and forbidden claims have zero tolerance. Required refusals have no final claims. False or missed conflicts fail.

All five rounds are required for success. The first model-quality failure freezes the campaign. Provider exhaustion or evaluator/integrity failure freezes engineering failure with model quality unavailable. Failed/completed rounds cannot be replaced. Preflight failure before formal start consumes no round.

Before calls, freeze package/threshold/scorer/prompt/provider and recursive implementation-closure hashes in the campaign plan. Outputs and round/terminal artifacts retain checksums. Raw output capture is restricted to non-confidential synthetic fixtures; headers, keys, hidden reasoning, and provider requests are not persisted by the protocol. Injected providers and low-level round execution are test-only/non-formal.

Recorded result status comes from immutable terminal reports, not the threshold's pre-run status field. This six-case suite does not establish general model quality, user value, Beta readiness, or a product-stage change. Costs, latency, tokens, retry/recovery, and paired deltas are observations.

From repository root, inspect command options:

```bash
uv run --project tools/evaluation python -m citeframe_evaluation.cli.campaign --help
```

See [evaluation and reproducibility](../development/evaluation.md) for scenario invariants and service boundaries.
