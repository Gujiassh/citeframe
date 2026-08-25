# R1 Single-Attempt Dispatcher Implementation Ledger

Date: 2026-08-24
Status: **runtime rework committed locally; canonical closure handled separately; follow-up Critical review pending; no ACCEPT claimed**

## Delivery Identity

- Source branch/ref: `main` at `8674d4dc407048471f7b14b23b821e72529487bf`, the
  merge commit delivered by PR #21.
- Immutable starting SHA: `8674d4dc407048471f7b14b23b821e72529487bf`.
- Repair branch: `work/research-r1-single-attempt-20260824`.
- Immutable reviewed production candidate:
  `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`f4a1d1d`), local commit.
- Independent Critical review: **REWORK (High=0, Medium=4, Low=0)** against `f4a1d1d`.
- Immutable runtime rework commit:
  `473213d79154f3fbcf6044e1c4e62ed65038e1c1` (`473213d`), parent `f4a1d1d`.
- Push state for `473213d`: local only; the branch has no upstream and no remote R1
  branch.
- Canonical SSoT/spec closure is handled separately from the runtime rework commit.
- The exact non-recursive ledger-closure SHA is owned by the external workbench/delivery
  record and is intentionally not self-recorded in this ledger.
- Schema/API/save/replay/permission contract change: none.

## Root Cause

The accepted A2a runtime still entered `BoundedResearchExecutor.execute()` after one outer
claim. That executor restored a process-local `ResearchState`, claimed additional Steps,
executed the remaining fixed graph, and retained cross-step values in memory. Consequently,
one `process_one()` call was not one claimed Attempt, and production exposed only one
mixed ingestion/Research loop instead of independent Research dispatchers.

## Critical Rework Against `f4a1d1d`

The independent review found two runtime defects, one delivery-ledger/hygiene defect, and
stale canonical SSoT/spec status. This implementation lane owns the first three findings;
canonical SSoT/spec synchronization is assigned to a separate lane and is not edited here.

Runtime rework:

- neutral Research lease ownership now defines the exact Worker-executable kind allowlist;
- `claim_next_research_step` excludes human and unknown kinds from Run candidate minima,
  Run eligibility, and the final Step selection while retaining the existing
  `(queued_at, created_at, step_id), run_id` order among executable Steps;
- `claim_specific_research_step` reads the Step kind as a locator and rejects a human or
  unknown kind before Run/Step locks, membership recovery, Attempt creation, status or
  `state_version` changes, and Event writes;
- `_lease_locked_step` repeats the allowlist check before membership or mutation as a
  defense-in-depth contract;
- `run_worker` now re-raises an iteration failure when a sibling has already set shared
  stop; clean pre-stopped loops and KeyboardInterrupt remain distinct;
- real-loop orchestration tests run the production `run_worker` branch with ingestion and
  two dispatchers failing concurrently and an additional shutdown failure, then prove all
  four causal leaves reach the caller exactly once. The test wrapper changes only retry
  delays and maximum attempts to zero/one; it delegates every loop branch to the real
  `run_worker` implementation.

No per-Run admission, cap, cap-full Run exclusion, or fairness policy was added. Filtering
human-owned kinds is an authority boundary, not Researcher admission.

## Implemented Scope

`ResearchWorkProcessor.process_one()` now performs exactly one outer claim and dispatches
only that Attempt's handler. It never stores the outer lease in the legacy internal-claim
cache and never calls `BoundedResearchExecutor.execute()`.

The explicit persisted step-kind mapping is:

| Persisted kind | R1 owner and behavior |
| --- | --- |
| `planner` | Worker planner handler; proposes and validates one plan, publishes it, then leaves the plan approval gate waiting |
| `plan_approval_gate` | Human/API-owned; neutral Worker claim commands skip/reject it before any lock-backed mutation, Attempt, or Event |
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
- an in-flight iteration error is re-raised even if a sibling set shared stop; only a loop
  with no failing iteration exits cleanly from that stop;
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

The immutable `f4a1d1d` executable differential passed with `equal=true`:

- baseline handled sequence: `[true, true, true, false]`;
- candidate handled sequence:
  `[true, true, true, true, true, true, true, true, false]`;
- candidate neutral UoW entries: `43`;
- process Event byte records: `40`;
- report: `/tmp/citeframe-r1-critical-review-f4a1d1d-a2a.json`;
- report SHA-256:
  `fa9e7dcbee1e8c63087182aa85a3f18461e0eb44740aa22f98273773f03ef739`.

## Verification Evidence

Immutable `f4a1d1d` evidence before Critical REWORK:

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
| Hygiene | failed: `git diff --check 8674d4d..f4a1d1d` found ledger line 3 trailing whitespace |
| Repeatable R1 gate | Worker focused/integration `62 passed`; API A2a/R0/recovery/lease `39 passed`; import smoke and locks passed |

## Critical Rework Verification

Runtime rework evidence is bound to immutable commit `473213d`, whose parent is reviewed
candidate `f4a1d1d`. The reviewer artifact remains separate and is not part of this
implementation ledger.

Completed rework evidence so far:

| Gate | Result |
| --- | --- |
| Real Worker loop/pool/runtime focused set | `64 passed` |
| API lease/plan including human-gate zero-mutation ORM probe | `9 passed`, one existing Starlette warning |
| Human gate `claim_next` | returned no lease; Run, Step, Decision, Attempt count, and Event count unchanged |
| Human gate `claim_specific` | `research_state_conflict`; the same complete before/after snapshot remained equal |
| Real PostgreSQL R0 focused | `6 passed`, one existing Starlette warning |
| Runtime commit delta hygiene | `git show --check 473213d` passed |
| Start-to-ledger-closure hygiene | `git diff --check 8674d4d` passed; the gate checks this combined range |
| Full affected API Research/R0/A2a | `132 passed`, one existing Starlette warning |
| Full Worker suite | `349 passed` |
| Repeatable R1 gate | Worker `64 passed`; API `40 passed`; locks, compile, import smoke, and range hygiene passed |

Commit `473213d` contains exactly the five runtime/test/gate files listed by `git show`; it
does not claim to contain this ledger closure. The external workbench/delivery record binds
the ledger closure identity and final start-to-delivery range without a self-reference.

Exact runtime commit A2a differential:

- `equal=true`, coverage `7/7`;
- candidate HEAD:
  `473213d79154f3fbcf6044e1c4e62ed65038e1c1`;
- baseline handled sequence `[true, true, true, false]`;
- rework handled sequence
  `[true, true, true, true, true, true, true, true, false]`;
- candidate neutral UoW entries: `43`;
- semantic worktree dirty: `false`;
- semantic worktree SHA-256 is the empty-diff digest:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- report: `/tmp/citeframe-r1-runtime-rework-473213d-a2a.json`;
- report SHA-256:
  `988c5b347e21f5bc997afb8519e5b397c6de382ffa2dafbbe52c73c2689880d5`.

The report's broader repair snapshot is dirty only because the separately owned canonical
closure, reviewer artifact, and this non-recursive ledger closure are outside the immutable
runtime commit. Its runtime semantic fingerprint is clean.

Because the neutral lease source changed, R0 PostgreSQL evidence was regenerated rather
than reusing the `f4a1d1d` source-bound report:

- PostgreSQL `17.11`, pgvector `0.8.6`;
- seven of seven scenarios passed;
- deadlocks remained `0 -> 0`;
- new lease source SHA-256:
  `1f65e0a66e1de6bed14a29f2f79cdf221567575d1054feb66c400c088ac60090`;
- report: `/tmp/citeframe-r1-rework-r0-contention-20260824.json`;
- report SHA-256:
  `823889721119953a092485a37024f39eaf7ad77f7d75fdc1540d4f2a111fcacc`.

Historical `f4a1d1d` R0 report, superseded only for rework source binding:

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
