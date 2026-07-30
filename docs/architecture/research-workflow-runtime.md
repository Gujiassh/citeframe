# Research Workflow Runtime And Runbook

## Status

- Implemented baseline: V4 R200-R800 engineering scope
- Canonical engineering evidence: [`../evals/artifacts/r800-v1/deployment-20260728-v4/`](../evals/artifacts/r800-v1/deployment-20260728-v4/)
- First provider-backed evidence: [`../evals/artifacts/r803-v1/`](../evals/artifacts/r803-v1/)
- Latest strict provider-backed diagnostic evidence: [`../evals/artifacts/r803-v4/`](../evals/artifacts/r803-v4/)
- Frozen formal campaign contracts: [`../evals/r803-v5-campaign-threshold.md`](../evals/r803-v5-campaign-threshold.md)
- First formal campaign attempt: [`../evals/artifacts/r803-campaign-20260730-v1/`](../evals/artifacts/r803-campaign-20260730-v1/) (`failed`, 0/5 completed rounds; immutable)
- Engineering gate: deterministic R800 baseline `pass`; R803 formal campaign v1 `fail`
- Latest interpretable paired diagnostic gates (v4): Quick `pass`; Research `fail` with 5/6 completed cases
- Model-quality gate: `not_evaluable` because formal v1 interrupted before any round completed
- User-value gate: `not_evaluable` until M404 contains qualified target-user evidence
- Product stage: `internal_preview`

## Runtime Boundaries

The Research workflow is a separate, explicit mode. Quick Chat, Chat SSE, Citation,
NoteSource, Asset scope, and Note save semantics remain unchanged.

The production path is split by ownership:

- Web selects Quick or Research, renders persisted Run/Step/Event state, and submits
  creator-only plan/conflict decisions through BFF routes.
- FastAPI owns every persistent Research contract: Workflow/Prompt versions,
  PlanRevision, ExecutionSnapshot, Run/Step/Attempt/Event, decisions, Artifact/Claim/
  Evidence provenance, provider/tool ledgers, budgets, idempotency, and Evaluation.
- Worker owns typed orchestration and provider/tool execution. It accesses Research
  state only through API service ports and does not own ORM models or migrations.
- PostgreSQL is the Research business truth source. MinIO stores immutable plan,
  checkpoint, conflict, and final Artifact bytes. Redis is not a correctness source.

## Orchestration Decision

The implemented topology is fixed and closed:

```text
Planner -> plan approval -> bounded Researcher fan-out -> join -> Verifier
        -> Critic -> optional conflict decision -> Synthesizer -> publisher
```

The runtime uses a typed `BoundedResearchExecutor`, not LangGraph. This is an
intentional bounded choice, not a generic agent framework:

- the graph is versioned and cannot be edited at runtime;
- PostgreSQL state and immutable checkpoints already provide restart semantics;
- provider/tool calls are explicit ports with frozen schemas and budgets;
- adding a second checkpoint authority would create reconciliation ambiguity.

This decision does not authorize a general workflow engine, dynamic plugins,
arbitrary tools, or model-authored graph changes. Reconsidering an external graph
engine requires a separate architecture review and must preserve PostgreSQL as the
only business truth source.

## Concurrency And Locking

Provider/tool reservation and completion serialize shared ledger updates through a
single lock order:

```text
ResearchStepAttempt -> ResearchStep -> ResearchRun -> call row -> ResearchBudgetLedger
```

Every blocking query refreshes existing SQLAlchemy identity-map state. Completion
may reconcile an already-sent provider call after Run cancellation because usage is
still billable, while sending a reserved call after cancellation remains forbidden.
Do not add deadlock retries to hide a lock-order regression.

Lease reclaim follows the same Attempt/Step/Run-before-call/ledger direction. New
code that touches more than one of these records must document and test its lock
order before entering the runtime path.

## Verification Runbook

### Fast checks

Run focused API and Worker coverage after changing Research state, tools, provider,
or executor code:

```bash
cd apps/api
.venv/bin/python -m pytest \
  tests/test_research_worker_lease_plan.py \
  tests/test_research_worker_budget_recovery.py \
  tests/test_research_worker_evidence_publication.py -q

cd ../worker
.venv/bin/python -m pytest \
  tests/test_research_executor.py \
  tests/test_research_runtime.py \
  tests/test_research_runtime_integration.py -q
```

Run full regressions before delivery:

```bash
cd apps/api && .venv/bin/python -m pytest -q
cd ../worker && .venv/bin/python -m pytest -q
```

### Isolated R800 acceptance

Use a new output directory and Compose project for every run:

```bash
bash infra/scripts/run-r800-acceptance.sh \
  --output-dir docs/evals/artifacts/r800-v1/deployment-YYYYMMDD-vN \
  --project citeframe-r800-deployment-vN
```

The command must finish with all of these true:

```bash
jq '{engineeringGate,releaseGatePassed,engineeringChecks,cleanup}' \
  docs/evals/artifacts/r800-v1/deployment-YYYYMMDD-vN/report.json
jq '.checks' \
  docs/evals/artifacts/r800-v1/deployment-YYYYMMDD-vN/scenarios.json
jq '.verification' \
  docs/evals/artifacts/r800-v1/deployment-YYYYMMDD-vN/verification.json
```

Required R800 scenario checks are `mainCompleted`, `parallelFanout`,
`unsupportedWithheld`, `conflictResume`, `transientRetry`, `leaseReclaim`,
`sseReplay`, `cancelNoFinal`, `membershipRemoval`, and `uniqueFinal`.


### Provider-backed R803 five-round campaign (v5)

Formal model-quality evidence requires the frozen five-round campaign, not a
single paired directory. Package v5 binds threshold v1 and scorer `r100-v2`.

```bash
uv run --project apps/worker python apps/worker/scripts/evaluate_r803_campaign.py \
  --package docs/evals/r803-evaluation-package-v5.json \
  --campaign-dir docs/evals/artifacts/r803-campaign-YYYYMMDD-vN
```

The first formal attempt, `r803-campaign-20260730-v1`, is immutable failed evidence. It froze before round-01 completed with `engineering=fail`, `modelQuality=not_evaluable`, and 0 completed case executions. Its safe interruption detail retained only `R803EvaluationError`, so the exact evaluator-integrity root cause is unknown. Do not overwrite, delete, resume, or infer a model result from this directory. A future v2 requires a runner that records an allowlisted internal error code plus a new owner-approved directory.

Interpret campaign results in this order:

1. `campaign-plan.json` package/threshold/scorer/plan hashes must match the frozen v5 contracts.
2. All five rounds are required for success; failed/completed rounds are immutable and never replaced.
3. Model-successful local semantic violations are quality failures and remain in the denominator.
4. Provider/evaluator integrity failures freeze engineering fail and leave model quality `not_evaluable`.
5. R803 still cannot set M404 user value or move the product beyond `internal_preview`.
6. Historical `r803-v1`..`r803-v4` directories remain diagnostic only.

### Provider-backed R803 paired evaluation

The package validates every fixture/source hash and the effective provider/model/
endpoint before sending a request. Supply the API key only through the existing
Worker settings; never add it to the package, command, log, or report. Use a new
output directory for every execution:

```bash
uv run --project apps/worker python apps/worker/scripts/evaluate_r803.py \
  --package docs/evals/r803-evaluation-package-v4.json \
  --output-dir docs/evals/artifacts/r803-YYYYMMDD-vN

(cd docs/evals/artifacts/r803-YYYYMMDD-vN && sha256sum -c SHA256SUMS)
```

Interpret the result in this order:

1. `comparisonKeysMatch` must be true; otherwise no Quick/Research comparison is valid.
2. Quick and Research engineering gates report execution completeness, not release quality.
3. Any case output that is not one strict JSON object fails closed. Do not extract a later JSON fragment.
4. One execution per case/mode remains observational evidence; formal model quality requires the five-round v5 campaign.
5. R803 cannot set M404 user value or move the product beyond `internal_preview`.
6. Never overwrite a failed run directory; defects and retries require a new immutable directory.

Package v4 uses evaluator-only Responses strict JSON Schema. It does not change the
production provider or Research V2 prompt contract. The provider schema and complete
local semantic schema are hashed separately; local validation remains authoritative.
Transport retries are limited to connection failures, 429/5xx, incomplete responses,
and responses without final text. The frozen policy makes three attempts with 5/15
second backoff and records every attempt plus any final usage returned by the provider.
Local JSON/schema/Evidence failures are never retried.

### Cleanup oracle

The script owns its disposable project and removes containers, volumes, networks,
and the generated secret environment file through its exit trap. Verify zero
residue after both success and failure:

```bash
jq . docs/evals/artifacts/r800-v1/deployment-YYYYMMDD-vN/cleanup.json
docker ps -a --filter label=com.docker.compose.project=citeframe-r800-deployment-vN
docker volume ls --filter label=com.docker.compose.project=citeframe-r800-deployment-vN
docker network ls --filter label=com.docker.compose.project=citeframe-r800-deployment-vN
```

Do not delete a failed artifact directory. Failed runs are regression evidence.

## Failure Triage

1. Read `scenarios.json` before logs; it identifies the failed semantic oracle.
2. Search `api.log`, `worker.log`, and final logs for flat error lines and
   `DeadlockDetected`, `research_state_conflict`, or an executor reason code.
3. Compare `provider-timeline.json` with provider/tool ledger rows in `before.json`.
4. Treat a matching before/after restore SHA as restore evidence only. It does not
   turn a failed scenario gate into a pass.
5. Fix the root cause and run a new deployment directory. Never rewrite an old
   report from fail to pass.

## Evidence Interpretation

R800 v4 proves deterministic engineering behavior on PostgreSQL, MinIO, the real
API/Worker/Web images, and a scripted provider. It proves persistence, concurrency,
recovery, provenance, isolation, and cleanup oracles. It does not evaluate a real
model's research quality and does not replace M404 user-value evidence.

R803 v1 adds one real `openai / gpt-5.5` observation under matching frozen keys.
Quick completed 6/6, while Research completed 4/6 and failed both refusal cases at
strict Researcher JSON parsing. This is a valid failed baseline, not a model-quality
release result. See
[`../evals/r803-real-model-first-run.md`](../evals/r803-real-model-first-run.md).

R803 v4 retains the same comparison keys and adds the versioned strict transport.
Quick completed 6/6 and Research completed 5/6; the remaining
`r100-refuse-customer` Researcher output failed the complete local schema. Diagnostic
v2 and provider-outage v3 runs remain immutable and are not substituted for v4.
R803 is still open and no repeated same-package run may be selected merely to obtain
a green sample. See
[`../evals/r803-strict-structured-output-follow-up.md`](../evals/r803-strict-structured-output-follow-up.md).
