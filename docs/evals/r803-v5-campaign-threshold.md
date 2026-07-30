# R803 V5 Campaign Threshold And Evaluator

## Decision

Owner-approved prospective R803 release threshold and evaluator-only campaign
infrastructure are frozen before any further paid provider run.

- Claim scope is only the frozen six-case synthetic suite for the configured
  model/workflow.
- The formal campaign requires five prospective paired rounds:
  `5 × 6 cases × 2 modes = 60` case executions.
- `r803-v1` through `r803-v4` remain immutable diagnostic history and are
  excluded from the formal campaign denominator.
- Quick and Research are judged independently against absolute zero-tolerance
  gates. Paired deltas, cost, latency, tokens, retries, recovery, and speedup
  are observations only; no automatic winner is selected.
- M404 remains `not_evaluable` and product stage remains `internal_preview`.
- Formal attempt `artifacts/r803-campaign-20260730-v1/` has executed and is immutable failed evidence: it froze before round-01 completed (`0/5` rounds, `0/60` completed case executions, engineering `fail`, model quality `not_evaluable`). It must not be resumed or overwritten.

## Frozen Contracts

| Artifact | Version / path |
| --- | --- |
| Threshold | [`r803-release-threshold-v1.json`](r803-release-threshold-v1.json) |
| Package | [`r803-evaluation-package-v5.json`](r803-evaluation-package-v5.json) |
| Case suite | `docs/evals/r100-research-cases-v2.json` (v1 bytes preserved; v2 adds claim-local negation/forbidden/positiveAssertion oracles) |
| Scorer | `r100-v2` (evaluator-only; v1 path retained for historical packages) |
| Diagnostics | `r803-raw-output-diagnostics-v1` |
| Campaign report | `r803-campaign-report-v1` |
| Round report | `r803-campaign-round-v1` |
| Round start | `r803-campaign-round-start-v1` exclusive durable marker before first provider call |

Threshold SHA-256 is bound into package v5. Package/threshold/scorer implementation
SHA, Quick/Research prompt-binding hashes, a deterministic recursive AST import closure rooted at
`ai_pdf_worker.r803_evaluation_campaign` (exact sorted path→SHA map + digest),
provider-profile fingerprint, and the planned five-round order are frozen into
`campaign-plan.json` before the first provider call of a formal campaign. Formal
evidence requires `provider=None` so the runner uses the configured frozen provider;
any injected provider needs `allow_test_provider=True` and is marked non-formal.
The public low-level `run_campaign_round` API is always test-only/non-formal.

## Formal Campaign V1 Outcome

`artifacts/r803-campaign-20260730-v1/` was started only after independent Critical review and deterministic preflight. Its durable round-start attestation records the configured `openai / gpt-5.5` profile with `formalEvidence=true`, plus the frozen package, threshold, scorer, prompt-binding, 55-module evaluator-closure, and plan hashes.

The threshold JSON remains byte-for-byte frozen with its pre-run `formalCampaignStatus=not_run` declaration; changing that field after execution would invalidate the package/plan evidence graph. Runtime status is authoritative only in the immutable campaign terminal report.

The run raised `R803EvaluationError` before any round artifact completed. The runner correctly froze a terminal report with:

- `status=failed`
- `engineering=fail`
- `modelQuality=not_evaluable`
- `completedRounds=0`
- `totalCaseExecutionsCompleted=0`

Terminal resume recomputes the same report without writes. The interruption detail intentionally excludes raw exception text and retained only the class name, so the exact internal evaluator-integrity code is unknown. Do not infer a model failure or provider outage from elapsed time or missing artifacts. Before any newly approved v2 attempt, the runner must record an allowlisted, non-secret internal error code and pass independent review. V1 remains immutable and must not be resumed, replaced, deleted, or relabeled.

## Post-V1 Runner Hardening

The current runner code adds two forward-only integrity fixes without changing the
formal v1 directory or its interpretation:

- A successful Research execution that selects only part of the required claim set
  now binds the missing-claim failure to the final Synthesizer output and remains a
  model-quality failure. It no longer becomes an engineering interruption solely
  because the omitted claim has no Researcher claim text to bind.
- A frozen interruption now records the exact partial-round file set, every file
  SHA-256, and a closure hash. Terminal resume rejects added, removed, or modified
  partial files instead of checking only `round-start.json`.

These fixes apply only to a future, separately approved campaign directory. They do
not authorize v2 and do not close the remaining requirement for an allowlisted,
non-secret internal evaluator error code.

## V4 Semantic Observations (Not Relabeled)

`artifacts/r803-v4/` remains the latest provider-backed diagnostic sample. It
must not be rewritten as a formal pass/fail under the new threshold.

Observed Research aggregates from that diagnostic sample:

| Metric | Research value | Sample notes |
| --- | ---: | --- |
| Evidence precision | 0.5 | Completed cases only under scorer `r100-v1` |
| Evidence-target exactness / legacy `locatorAccuracy` | 0.0 | Exact Evidence-ID set equality, not geometry |
| Conflict detection | 0.8 | One missed-conflict completed case |
| Refusal correctness | 0.0 | One completed refusal failed; one refusal case aborted |

`r100-refuse-customer` failed as `researcher_invalid_output` after Planner and
Researcher calls. Exact schema root cause is **unknown** because v4 retained
failure codes/cost/calls but not raw provider output, node path, or local rule
path. The failure is therefore not post-hoc reclassified as a proven contract
defect or a proven model defect; under v5 it is measured as a campaign quality
failure if the model returns successful transport output that still violates the
frozen local semantic contract.

## Scorer V2 Rules

`r100-v2` is used only by package/campaign v5:

1. Model-successful output that violates the frozen local semantic contract is a
   model/workflow conformance/quality failure and remains in the campaign
   denominator.
2. Every observed final claim must map to exactly one approved expected claim
   with positive semantics and exact approved Evidence IDs.
3. Extra, negated, duplicated, or unsupported observed claims fail.
4. Refusal cases must end as refusal with zero selected final claims and no
   forbidden answer.
5. Conflict and non-conflict expectations are both enforced.
6. `evidenceTargetExactness` is the precise campaign term. R700 import reports
   continue to expose the same exact Evidence-ID equality under the legacy field
   `locatorAccuracy`; this does not measure geometry.

Provider outages, evaluator/integrity defects, or exhausted transport retries
freeze engineering failure and leave model quality `not_evaluable`. Start a new
campaign after repair; never replace a completed or failed round.

## Diagnostics Boundary

Evaluator-only raw provider **outputs** are persisted under each round's
`raw-outputs/` directory with a checksummed manifest. Captured only for the
frozen non-confidential synthetic fixtures. The campaign must not persist:

- provider requests
- headers
- API keys / secrets
- hidden reasoning

Each model-output failure diagnostic records stage, rule, JSON path, node key,
logical call key, and raw output SHA-256.

## Campaign Runner

```bash
uv run --project apps/worker python apps/worker/scripts/evaluate_r803_campaign.py \
  --package docs/evals/r803-evaluation-package-v5.json \
  --campaign-dir docs/evals/artifacts/r803-campaign-YYYYMMDD-vN
```

Resume is fail-closed:

1. Existing `campaign-plan.json` (+ companion hash) and exact recursive round
   checksum closures are verified.
2. Completed/failed rounds are immutable and never overwritten.
3. Terminal resume recomputes the campaign report from contiguous verified rounds
   and requires canonical equality; an interruption permits exactly the referenced
   started-but-incomplete partial round.
4. Success requires all five rounds with zero quality failures.
5. The first zero-tolerance quality failure freezes `modelQuality=fail` and
   stops; the first engineering/outage/interruption freeze leaves
   `modelQuality=not_evaluable`. Interruption detail stores allowlisted class/code
   only, never raw exception text.
6. Preflight configuration failure before formal start aborts without consuming
   a round.

## Budget Estimate

Based on `r803-v4` single-round cost/time scaled to five rounds:

- about **USD 3.27**
- about **26 minutes**

This was the pre-run estimate for a complete five-round campaign. Formal v1 started but failed before round-01 completion; its actual cost is not derivable from persisted case/round usage because no round artifact completed.

## Product Gates

| Gate | Status |
| --- | --- |
| Engineering campaign readiness | formal v1 failed before round-01 completion; root cause unknown pending safer internal error-code diagnostics |
| Model quality | `not_evaluable`; formal v1 produced no completed round denominator |
| User value (M404) | `not_evaluable` |
| Product stage | `internal_preview` |

## Explicit Non-Goals

- No R700 persistence/API/database contract changes
- No production Research behavior, PromptVersion, WorkflowVersion, Chat,
  Citation, NoteSource, or save semantic changes
- No general production raw-output recorder
- No automatic Quick/Research product-default selection
- No claim of general model quality or Beta readiness
