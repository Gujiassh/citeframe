# Research Workflow Runtime And Runbook

## Status

- Implemented baseline: V4 R200-R800 engineering scope
- Canonical engineering evidence: [`../evals/artifacts/r800-v1/deployment-20260728-v4/`](../evals/artifacts/r800-v1/deployment-20260728-v4/)
- First provider-backed evidence: [`../evals/artifacts/r803-v1/`](../evals/artifacts/r803-v1/)
- Latest strict provider-backed diagnostic evidence: [`../evals/artifacts/r803-v4/`](../evals/artifacts/r803-v4/)
- Frozen formal campaign contracts: [`../evals/r803-v5-campaign-threshold.md`](../evals/r803-v5-campaign-threshold.md)
- First formal campaign attempt: [`../evals/artifacts/r803-campaign-20260730-v1/`](../evals/artifacts/r803-campaign-20260730-v1/) (`failed`, 0/5 completed rounds; immutable)
- Engineering gate: deterministic R800 baseline `pass`; R803 formal campaign v1 `fail`
- Research boundary status: the design re-audit is **ACCEPT (High=0, Medium=0, Low=0)**; A1 was independently accepted on **2026-08-20**. A1b/A2-foundation was independently accepted on 2026-08-21 by the follow-up Critical review
(`High=0`, `Medium=0`, `Low=0`). A2a initial snapshot `20d411e` received `REWORK (High=1, Medium=5, Low=1)`. A2a is independently `ACCEPTED (High=0, Medium=0, Low=0)` at local production `215cd52565089138704c6b637350e18bc8705c8b`, documentation `95981a499521a28bfd9eb24480d54ef42f485528`, and review `eb97adfa75660867eb31d46a4e7d7712909c348e`; none is pushed. R0 is the only next separately gated implementation slice; R1/R2/W1 and downstream remain blocked. Current evidence is in `../../specs/v5/post-v5-optimization/reviews/a2a-persistence-rework-implementation-2026-08-24.md`.
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
- API owns HTTP/auth/Alembic/schema governance for persistent Research contracts. In the
  repair worktree, neutral `citeframe_persistence` owns mappings/metadata and
  `citeframe_research_persistence` owns DB-only Research transitions; API retains public
  routes, compatibility facades, and external-adapter composition.
- **Accepted A2a fact, local delivery pending:** Worker owns typed
  orchestration/provider/tool execution and uses the neutral Research persistence service,
  UoW, and repository for DB-only transitions. API owns HTTP/auth/Alembic/schema governance
  and compatibility/external-adapter composition; ingestion retains its shared Session/ORM
  boundary.
- **Accepted A2a state, local delivery pending:** the Worker continues to own orchestration and
  the repaired default composition uses the neutral Worker-side Research UoW as runtime commit-process owner; API owns HTTP/auth,
  Alembic execution, and schema governance. Package staging is A1 pure
  `citeframe_contracts`, A1b/A2-foundation neutral `citeframe_persistence` mappings, then
  A2a `citeframe_research_persistence` Research behavior. Each stage adds only its package
  to manifests, source-copy paths, PYTHONPATH, and import smoke; A2a is the first stage
  where the third package may exist. `citeframe_persistence` owns all mappings and the
  unique Base/metadata; `citeframe_research_persistence` owns Research repositories/UoW/
  commands/locks and must not import `ai_pdf_api` or non-DB service implementations.
  API Alembic remains the executor and loads `citeframe_persistence.models` after A1b.
- PostgreSQL is the Research business truth source. MinIO stores immutable plan,
  checkpoint, conflict, and final Artifact bytes. Redis is not a correctness source.

The A2a transition slice must preserve the current behavior in which one `process_one` call
can drive multiple steps through the fixed LangGraph StateGraph. After A2a is accepted,
R0 first normalizes lock acquisition; the later R1 slice then changes runtime execution to
one claimed Attempt per handler in a bounded pool of independent dispatcher loops and
removes LangGraph from runtime step execution. Research-enabled production must run at
least two loops; acceptance proves real branch overlap and wall time below the serialized
sum while the persisted per-Run cap remains the concurrency authority. The implementation-ready target and its current/not-implemented status are recorded in
[`../../specs/v5/post-v5-optimization/research-boundary-runtime-design.md`](../../specs/v5/post-v5-optimization/research-boundary-runtime-design.md). A1 implementation evidence and independent ACCEPT on 2026-08-20 are recorded.
A1b/A2-foundation was independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0);
A2a is independently accepted locally. R0 is the only next separately gated implementation slice; R1/R2/W1 and downstream remain blocked behind R0 or their named gates. No schema/API/save/replay/permission changes are authorized.

## Orchestration Decision

## Topology freeze (2026-08-15)

**FREEZE**: The production Research topology and role set are closed for ordinary product work:

`Planner -> plan approval -> bounded Researcher fan-out -> join -> Verifier -> Critic -> optional conflict decision -> Synthesizer -> publisher`

- Do **not** add graph nodes, roles, or tool kinds without a new open decision (OD) and budget impact note.
- Prefer reliability, evidence coverage, observability, and contract tests over graph expansion.
- This is **not** a general agent platform; dynamic DAG / plugins remain rejected.
- Module ownership map: [`research-module-map.md`](research-module-map.md).


The implemented topology is fixed and closed:

```text
Planner -> plan approval -> bounded Researcher fan-out -> join -> Verifier
        -> Critic -> optional conflict decision -> Synthesizer -> publisher
```

**Current fact:** `research_executor_engine.py` constructs and invokes a fixed LangGraph
`StateGraph(ResearchState)` inside the Worker process. PostgreSQL state and immutable
artifacts are the persistence/checkpoint/business truth; LangGraph is not the persisted
checkpoint authority and is not allowed to replace the Research ledger.
**Approved R1 target, not implemented:** PostgreSQL remains the persistence and
business authority during A2a; after A2a, R1 makes it the runtime orchestration authority.
R1 removes LangGraph from runtime step execution or retains it only as a plan-approval
topology validator. The target is a one-claimed-attempt dispatcher: claim one eligible
queued Step, create one new Attempt lease, run one step-kind handler, atomically complete
its Attempt/Step/Event and newly-ready dependents, then return to the claim loop. Handlers rebuild and validate existing StepDependency/upstream persisted status, execution
snapshot identity/hash, and artifact/claim/evidence provenance/hash from PostgreSQL; they
carry no cross-step in-memory `ResearchState`. Existing `ResearchStep.input_sha256` keeps
its current meaning and is not reinterpreted as a canonical handler-input hash. Defining
such a hash requires a separate A-DATA design.

The current bounded executor rationale remains valid for the current checkout:

- the graph is versioned and cannot be edited at runtime;
- PostgreSQL state and immutable checkpoints already provide restart semantics;
- provider/tool calls are explicit ports with frozen schemas and budgets;
- adding a second checkpoint authority would create reconciliation ambiguity.

This decision does not authorize a general workflow engine, dynamic plugins,
arbitrary tools, or model-authored graph changes. Reconsidering an external graph
engine requires a separate architecture review and must preserve PostgreSQL as the
only business truth source.

## V5-C Production Contract Rules

V5-C keeps the fixed topology but upgrades Agent I/O to a versioned production
registry. A registry entry binds the strict role schema, prompt/template hash,
validator, runtime adapter, cross-role provenance checks, API/Web mapping and
historical recovery reader. `agentResultSchemaVersion`, `contextPolicyVersion`
and `compactPolicyVersion` are frozen on each planning/execution snapshot.
Historical rows are mapped to a named legacy entry; new Runs never fall back to
an old or loose contract.

`maxInputTokens` and `maxOutputTokens` are per-provider-call gates. Before send,
the worker performs deterministic typed packing, soft compact or batching, and
rejects mandatory overflow with `research_context_limit_exceeded`. The provider
request receives the exact output cap; truncated or incomplete output fails with
`research_provider_output_incomplete`. Cumulative input/output totals are
telemetry only. Provider/tool/time/parallelism/attempt limits remain the hard
Run limits.

Pricing is optional metadata. Missing pricing never blocks Research, unknown
pricing remains null/unavailable, and V5-C usage DTOs do not expose money.

## Concurrency And Locking

**Current fact:** lock acquisition is mixed and conflicting. Many Worker attempt paths use
`Attempt -> Step -> Run`; claim uses `Step -> Run`; API cancel, retry, and decision paths
use `Run -> Step`. Claim-versus-cancel therefore has a real reverse-order deadlock ring.
A2a preserves this current lock behavior; it must not be described as one authoritative
order or as a safe claim exception.

**R0 target, not implemented:** normalize every multi-row mutation to the aggregate-root
order:

```text
ResearchRun -> ResearchStep -> ResearchStepAttempt -> provider/tool Call -> ResearchBudgetLedger
```

Attempt/Call id paths first read parent ids without locks only to locate the aggregate.
They make no decisions from those reads. They then lock and refresh the full chain in
Run -> Step -> Attempt -> Call -> Ledger order, revalidating scope, status, token, and
expiry; any changed locator or status fails closed. Claim selects candidate Runs with
queued work using `FOR UPDATE SKIP LOCKED`, ordered by the minimum eligible Step tuple `(queued_at, created_at, step_id)`, then
Run id, locks Run first, rechecks status/cap, then locks one eligible Step using that exact existing
`queued_at`, `created_at`, then Step ID ordering, and creates Attempt. Cancel also locks Run first, then affected Steps in stable
Step id order. Heartbeat, complete, reclaim, retry, decision, join, provider/tool, and
publication follow the same order. R0 changes lock acquisition only and preserves save,
API, replay, permission, and payload semantics.

R0 is a separate slice after A2a and before R1 or per-Run admission. It must not add
deadlock retries. Real PostgreSQL `pg_locks` and lock-timeout evidence is required for
claim-versus-cancel, claim-versus-complete, reclaim-versus-provider/tool, two claims on
one Run, and claims on different Runs.

Lease lifecycle remains exact: normal claim creates a new Attempt for a queued Step;
heartbeat extends only that running Attempt; expiry reclaim marks the old Attempt
`abandoned`, synchronizes Step through its existing retry or cancellation path, and a
later retry creates a new Attempt. An expired Attempt is never refreshed or revived.
Provider/tool outcome-unknown and object-publication commit-unknown compensation remain
unchanged. Do not use deadlock retry to hide a lock-order regression.

Per-Run `maxParallelResearchers` admission is implemented after R0 under the same Run
lock. A candidate cap-full Run causes rollback of the whole claim transaction, releases
Run locks, records local `excluded_run_ids`, and continues in a new transaction. No Step
is locked and no Attempt, status, or Event mutation occurs for that Run. Only after the
Run passes the cap check does the transaction lock an eligible Step and create Attempt.
Query filtering is an efficiency prefilter, never correctness; another eligible Run must
remain claimable without starvation.

Required R0/R2 evidence includes cap=1 and cap=N, lease expiry/late completion, cancel and
provider races, join/recovery, and the real-PostgreSQL lock matrix above. SQLite-only or
in-memory evidence is insufficient.

The Research Event oracle is byte/row equal for A2a current-runtime snapshots. R1/R2
require per-Run `seq` starting at 1, contiguous and unique within the Run, atomically allocated
across Workers; per-Step `queued < started < terminal`, legal
Attempt/lease event order, dependencies succeeded before dependent queued, Run terminal
last, dedupe/unique terminal, and equal payload schema/error meaning. Independent
Researcher event interleaving may vary.

New code that touches more than one of these records must document and test its lock
order before entering the runtime path.

## Research SSE target (W1, approved direction; not implemented)

Research SSE remains independent from Quick Chat SSE. The client applies an event only
when explicit schema-approved fields prove the transition, and discards a response whose
`currentEventSeq` is below the locally applied sequence. A switched Run aborts or discards
old requests. One active request per Run uses a dirty rerun and bounded coalescing window;
terminal events flush immediately. Artifact lists refresh only for artifact/decision/terminal
events or explicit gap recovery, and artifact content is cached by `(artifactId, sha256)`.

History gaps/cursor conflicts trigger a full authoritative read. `LISTEN/NOTIFY` is only a
post-commit wakeup; persisted events and periodic replay remain authoritative when notify
is lost or duplicated. W1 is an independent slice and does not change the Research API,
save, or event contract.

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
