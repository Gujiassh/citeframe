# Research Workflow Runtime And Runbook

## Status

- Implemented baseline: V4 R200-R800 engineering scope
- Canonical engineering evidence: [`../evals/artifacts/r800-v1/deployment-20260728-v4/`](../evals/artifacts/r800-v1/deployment-20260728-v4/)
- Engineering gate: `pass`
- Model-quality gate: `not_evaluable` because R800 uses a scripted provider
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
