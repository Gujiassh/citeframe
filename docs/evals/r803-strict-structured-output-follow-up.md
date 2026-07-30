# R803 Strict Structured-Output Follow-Up

## Decision

The evaluator-only strict structured-output repair is implemented and the first
stable follow-up run is retained in [`artifacts/r803-v4/`](artifacts/r803-v4/).
Quick completed all six cases. Research completed five and failed
`r100-refuse-customer` at the complete local Researcher schema. R803 remains open,
model quality and M404 remain `not_evaluable`, and the product stays
`internal_preview`.

No repeated run was selected to hide that model failure. The v4 result is the
first run after the strict transport and evidenced retry policy were both stable.

## Contract Boundary

- Frozen package: [`r803-evaluation-package-v4.json`](r803-evaluation-package-v4.json)
- Provider/model: `openai / gpt-5.5`
- API protocol: Responses v1 with evaluator-only `text.format=json_schema`
- Structured-output transport: `responses-json-schema-v1`
- Provider schema set: `r803-provider-output-schemas-v2`
- Retry policy: `r803-provider-retry-v3`, three attempts with 5/15 second backoff
- Cases, Assets, scorer, provider profile, and all six comparison keys: unchanged
  from v1

The production `OpenAIGenerationProvider`, production Research V2 prompt variables,
PromptVersion rows, WorkflowVersion, and persisted execution snapshots are unchanged.
Only the offline R803 provider adapter sends the strict Responses format.

The complete semantic schemas remain the local validation authority. The provider
schema retains closed objects, required properties, types, enums, and non-empty
Evidence arrays. The SourcesData endpoint accepts `minItems` but returns HTTP 502 for
`uniqueItems`; unsupported transport keywords are therefore omitted from the
provider schema and still enforced locally. No JSON fragment extraction, prefix
stripping, duplicate coercion, or schema downgrade is allowed.

## Provider Accounting And Retry

The first strict wrapper could not return usage when an HTTP 200 response contained
no final answer text. The evaluator now owns the raw Responses request so every
parseable response records its final input/output usage even when the call fails.
It distinguishes permanent 4xx errors from 429/5xx, connection failures, incomplete
responses, and completed responses without answer text.

Only transport-level transient codes are retried. Local JSON decoding, complete
schema validation, Evidence handle validation, and scorer failures are never
retried. Every attempt remains in `providerCallRecords`; retry and recovery rates,
tokens, and cost include failed attempts when the provider supplies usage.

## Immutable Run History

| Run | Quick | Research | Interpretation |
| --- | --- | --- | --- |
| `r803-v2` | 5/6 | 0/6 | Non-canonical diagnostic: strict transport first exposed provider no-text responses, but the wrapper could not retain their usage; do not use its cost as complete evidence |
| `r803-v3` | 1/6 | 1/6 | Valid outage evidence: repeated `ConnectTimeout`/no-text failures dominated both modes; failed attempts and retry facts are retained |
| `r803-v4` | 6/6 | 5/6 | Current canonical strict run; transport recovered, one Researcher output still failed the complete local schema |

No directory was overwritten. Each package and report set remains byte-addressed
by its own SHA-256 values.

## V4 Results

| Metric | Quick | Research |
| --- | ---: | ---: |
| Completed cases | 6/6 | 5/6 |
| Engineering gate | pass | fail |
| Provider calls | 6 | 36 |
| Input tokens | 28,402 | 168,117 |
| Output tokens | 1,004 | 9,858 |
| Wall time | 47.330 s | 264.144 s |
| Cost | USD 0.086065 | USD 0.568163 |
| Retry rate | 0/6 | 1/36 |
| Recovery rate | not applicable | 1/1 |
| Parallel speedup | not applicable | 1.5897 |

`r100-refuse-customer` completed its Planner and three provider-backed Researcher
calls, then failed as `researcher_invalid_output` before verifier/scorer success.
The paired report retains that node-level code; the R700-compatible report keeps
the closed case value `scorer_error` and top-level `schema_violation`.

The strict transport removed the v1 concatenated-object failure pattern: no
permissive parser was added, and `r100-refuse-energy` completed in v4. The remaining
customer failure shows that provider JSON Schema conformance does not replace the
complete local semantic validator.

One execution per case and mode still has no approved release threshold. These
results are observational and cannot select a Quick/Research winner, pass model
quality, set M404 user value, or advance the product stage.

## Artifact Integrity

```text
paired-quality-report.json  3a247a044b5e2625d9d4195f2d1301635809e8f956874fc855d81946da32fda2
quick-evaluation.json        6ac6a6e079d835cbea524a967ca58ef98e5e9c78e3edc311826bb48638a26a27
research-evaluation.json     72b4395ff5bfa2f6ce65dc14e1d2c79bb61528dff844826a61bebdcdf7e81728
```

`sha256sum -c SHA256SUMS` passes inside `r803-v2`, `r803-v3`, and `r803-v4`.

## Verification

- R803/Research focused tests: `37 passed`
- Worker full suite: `160 passed`
- Ruff and `compileall`: passed
- R700 import parsing: passed for every retained Quick/Research report
- V1/v4 comparison-key equality: passed
- V4 prompt/schema/retry binding reverse oracle: passed
- Canonical artifact checksums: passed
- Relative Markdown links, fence balance, secret scan, and `git diff --check`: passed

## Next Gate

The approved sample/release threshold and evaluator-only campaign infrastructure
are frozen in [`r803-v5-campaign-threshold.md`](r803-v5-campaign-threshold.md),
[`r803-release-threshold-v1.json`](r803-release-threshold-v1.json), and
[`r803-evaluation-package-v5.json`](r803-evaluation-package-v5.json).

This v4 diagnostic sample is not relabeled. Research semantic observations from
completed v4 cases remain: evidence precision `0.5`, Evidence-target exactness /
legacy `locatorAccuracy` `0.0`, conflict detection `0.8`, refusal correctness
`0.0`. The exact `r100-refuse-customer` schema root cause is still unknown because
v4 lacked raw diagnostics. Under the approved v5 policy, a future model-successful
local-schema failure counts as a campaign quality failure and stays in the
denominator.

The first formal attempt is now retained at
[`artifacts/r803-campaign-20260730-v1/`](artifacts/r803-campaign-20260730-v1/).
It failed before round-01 completed and therefore produced no model-quality
denominator: `engineering=fail`, `modelQuality=not_evaluable`, `0/5` completed
rounds, and `0/60` completed case executions. Its safe interruption detail only
retained `R803EvaluationError`, so the exact evaluator-integrity root cause is
unknown and must not be guessed. V1 is immutable and cannot be resumed or replaced.
Before any separately approved v2, future runner diagnostics must retain an
allowlisted internal error code without persisting raw exception text.

R803 remains open. Do not rerun or overwrite v4 or formal v1. M404 remains a
separate target-user evidence gate.
