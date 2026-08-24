# R1 Single-Attempt Dispatcher Implementation Ledger

Date: 2026-08-24  
Status: **implementation complete; independent Critical review pending; no ACCEPT claimed**

## Delivery Identity

- Source branch/ref: `main` at `8674d4dc407048471f7b14b23b821e72529487bf`, the
  merge commit delivered by PR #21.
- Immutable starting SHA: `8674d4dc407048471f7b14b23b821e72529487bf`.
- Repair branch: `work/research-r1-single-attempt-20260824`.
- Commit: none.
- Push: none.
- Schema/API/save/replay/permission contract change: none.

## Root Cause

The accepted A2a runtime still entered `BoundedResearchExecutor.execute()` after one outer
claim. That executor restored a process-local `ResearchState`, claimed additional Steps,
executed the remaining fixed graph, and retained cross-step values in memory. Consequently,
one `process_one()` call was not one claimed Attempt, and production exposed only one
mixed ingestion/Research loop instead of independent Research dispatchers.

## Implemented Scope

`ResearchWorkProcessor.process_one()` now performs exactly one outer claim and dispatches
only that Attempt's handler. It never stores the outer lease in the legacy internal-claim
cache and never calls `BoundedResearchExecutor.execute()`.

The explicit persisted step-kind mapping is:

| Persisted kind | R1 owner and behavior |
| --- | --- |
| `planner` | Worker planner handler; proposes and validates one plan, publishes it, then leaves the plan approval gate waiting |
| `plan_approval_gate` | Human/API-owned; the Worker fails closed if an invalid queued claim reaches it |
| `researcher` | One claimed branch only; rebuilds its frozen execution/subproblem and uses evidence ports scoped to that Attempt |
| `join` | One control completion after all persisted researcher predecessors succeeded |
| `verifier` | Rebuilds all completed branch Claims/Evidence, verifies the exact Claim set, and completes only the verifier Attempt |
| `critic` | Rebuilds persisted verified Claims, records the exact supported conflict set, and completes only the critic Attempt |
| `conflict_decision_gate` | Completes when there are no conflicts; otherwise publishes the conflict decision input and waits without entering synthesis |
| `synthesizer` | Rebuilds persisted resolved Claim state, validates the selection, and stores the existing synthesis checkpoint |
| `artifact_publisher` | Reads and verifies the persisted synthesis checkpoint, then performs the existing atomic final publication |

Production runtime modules now import DTO/Protocol types directly from
`citeframe_contracts`. Importing `ai_pdf_worker.research_runtime` and
`ai_pdf_worker.main` does not import LangGraph or
`ai_pdf_worker.research_executor_engine`. LangGraph remains available only to the legacy
topology/evaluation executor paths.

The new read-only `load_step_handler_input` adapter validates, before each execution
handler:

- Run/Workspace/Step/Attempt identity, current running status, lease token hash, and
  unexpired lease;
- the exact Attempt number and existing `input_sha256` value, including the existing
  Step-ID fallback meaning when `ResearchStep.input_sha256` is null;
- execution snapshot and approved plan artifact identity/hash;
- persisted dependencies and succeeded upstream status;
- Claim statement hashes, producing researcher Step, verification/critic provenance;
- Claim-to-Evidence ownership and evidence snapshot provenance;
- synthesis checkpoint object bytes, content hash, generating Step/Attempt, and selection
  contract before final publication.

No write command, fencing rule, R0 lock order, `state_version` meaning, Event payload, or
object-publication compensation path was reimplemented in the Worker.

## Production Pool

Production `main()` now runs:

- one dedicated ingestion loop, preserving ingestion progress independently of Research;
- a bounded `ResearchDispatcherPool`, default width `2`;
- one long-lived `ResearchWorkProcessor` and unique worker-instance suffix per pool loop;
- independent SQLAlchemy sessions per UoW/port call; no identity map or cross-step state is
  shared between processors;
- existing bounded retry/backoff per loop;
- shared shutdown signaling and a bounded 130-second pool join, covering the frozen
  provider timeout plus cleanup margin;
- fail-fast sibling shutdown and propagated fatal error when a dispatcher exhausts retries;
- `BaseExceptionGroup` aggregation when multiple dispatchers or ingestion and a dispatcher
  fail together, so no background cause is discarded during shutdown.

`AI_PDF_RESEARCH_DISPATCHER_LOOPS` may increase the process-local pool, but values below
`2` fail startup. This setting is a process pool width only.

The production-shaped two-loop test uses two real `ResearchWorkProcessor` instances over
one thread-safe claim port. It proves two different researcher Step/Attempt pairs are each
claimed/completed once, the handler sessions are distinct, their execution intervals
overlap, and two 200 ms handlers finish in less than 350 ms total wall time.

## Semantic Oracle And Allowed Delta

R1 intentionally changes scheduling granularity. It is no longer valid to require the
frozen `d1b5945` executor's `process_one()` call count or timing to be byte-identical.

Allowed scheduler delta:

- baseline: three handled calls (`planner`, whole graph to conflict wait, whole graph to
  terminal) followed by idle;
- R1 candidate: eight handled calls (one per persisted Worker-owned Attempt) followed by
  idle;
- wall-clock timing and interleaving between independent researcher Attempts may differ.

Required invariant, still compared exactly:

- normalized terminal rows across all 29 observed relations;
- exact API response bytes;
- exact immutable Research object bytes;
- exact Event bytes, sequence, and semantic partial order;
- terminal Run/Step/Attempt/Claim/Artifact meaning;
- lease fencing, retry/cancel/reclaim recovery, permissions, provider/tool accounting, and
  A2a neutral composition ownership.

The evolved executable differential passed with `equal=true`:

- baseline handled sequence: `[true, true, true, false]`;
- candidate handled sequence:
  `[true, true, true, true, true, true, true, true, false]`;
- candidate neutral UoW entries: `43`;
- process Event byte records: `40`;
- report: `/tmp/citeframe-r1-a2a-differential-20260824.json`;
- report SHA-256:
  `801491510f4ab47bbc187777f3706df6e3ed3d6643d876af4233700bab74191d`;
- final candidate semantic worktree SHA-256:
  `4a3d4e69ff3d5b1675f98e555d8aa97a78e76eff11176d226c8201d645062044`.

## Verification Evidence

Completed evidence:

| Gate | Result |
| --- | --- |
| Focused dispatcher/runtime/main | `58 passed` |
| Full Worker suite | `347 passed` |
| Affected API Research/R0 pre-oracle set | `64 passed`, one existing Starlette deprecation warning |
| API Research plus R0 plus evolved A2a run | `129 passed`, two old-oracle failures identified and repaired; no business test failure |
| Complete A2a differential file after repair | `3 passed`, one existing Starlette warning |
| A2a terminal differential | `equal=true`, 29 relation groups, exact payload/Event/object bytes |
| Production runtime import smoke | LangGraph and executor engine absent from `sys.modules` |
| API and Worker locks | `uv lock --check` passed for both projects |
| Compile | Worker and API Research `compileall` passed |
| Hygiene | `git diff --check` and R1 gate shell syntax passed |
| Repeatable R1 gate | Worker focused/integration `62 passed`; API A2a/R0/recovery/lease `39 passed`; import smoke and locks passed |

Accepted R0 lock behavior was re-run against real PostgreSQL:

- PostgreSQL `17.11`, pgvector `0.8.6`;
- seven of seven contention scenarios passed;
- `deadlocks 0 -> 0`;
- no deadlock retry was added;
- report: `/tmp/citeframe-r1-r0-contention-20260824.json`;
- report SHA-256:
  `e17183d9521d44ebf8a287386507cc19df04fb8814ad2e532545c6e467e31218`.

The first pinned Docker Hub pull failed before execution because
`registry-1.docker.io` reset the connection. The successful run used the already-cached
Daocloud pgvector `pg17` mirror digest
`sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`;
this transport substitution is recorded rather than hidden.

Repeatable focused gate:

```bash
infra/scripts/run-r1-single-attempt-gate.sh
```

## Explicitly Out Of Scope

- Per-Run `maxParallelResearchers` admission/cap enforcement for `1` or `N` is
  **UNAUTHORIZED and not implemented**.
- No fairness policy across cap-full Runs is implemented.
- R2 real multi-process/multi-worker proof is not claimed.
- W1, SSE/downstream performance slices, schema changes, Docker/CI/manifests, and lockfile
  changes are not included.

R2, W1, and downstream work remain blocked pending independent Critical review and owner
acceptance of R1. This implementation ledger records evidence only and does not claim
`ACCEPT`.
