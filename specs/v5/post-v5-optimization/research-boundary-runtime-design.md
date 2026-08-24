# Research Boundary And Distributed Runtime Design

Status: **Design re-audit and A1/A1b are accepted; A2a initial snapshot `20d411e` received independent Critical `REWORK` (`High=1`, `Medium=5`, `Low=1`). The bounded rework on `work/research-boundary-runtime-20260824` is implementer-complete but remains uncommitted and unpushed; a new independent Critical re-audit against an immutable repair snapshot is pending. No A2a `ACCEPT` is claimed. R0/R1/R2/W1 and downstream remain blocked**
Date: 2026-08-20
Owner decision: same-database adapter for `internal_preview`; A1b/A2-foundation was
independently accepted on 2026-08-21 by the follow-up Critical review
(`High=0`, `Medium=0`, `Low=0`). A2a initial snapshot `20d411e` received independent Critical `REWORK` (`High=1`, `Medium=5`, `Low=1`). The bounded rework on `work/research-boundary-runtime-20260824` is implementer-complete but remains uncommitted and unpushed; a new independent Critical re-audit against an immutable repair snapshot is pending. No A2a `ACCEPT` is claimed. R0/R1/R2/W1 and downstream remain blocked. This document
does not authorize schema/API/save/replay/permission changes, G/M/P work, GitHub settings,
paid provider runs, or user research.

A1 implementer status (2026-08-20): `citeframe-backend-contracts` is implemented with
neutral DTO/Protocol definitions, legacy identity-preserving re-exports, API/Worker
path-source integration, contracts-only Docker/CI smoke, and focused verification. This
A1 implementation was independently accepted on 2026-08-20. A1b/A2-foundation was
independently accepted on 2026-08-21 by the follow-up Critical review
(`High=0`, `Medium=0`, `Low=0`). A2a initial snapshot `20d411e` received independent Critical `REWORK` (`High=1`, `Medium=5`, `Low=1`). The bounded rework on `work/research-boundary-runtime-20260824` is implementer-complete but remains uncommitted and unpushed; a new independent Critical re-audit against an immutable repair snapshot is pending. No A2a `ACCEPT` is claimed. R0/R1/R2/W1 and downstream remain blocked.

This is the implementation-ready detail for the Research portion of the Post-V5
Optimization plan. It deliberately separates three states:

| State | Meaning |
| --- | --- |
| Current fact | What the checked-in runtime does today; retained until a named slice lands |
| Approved target | Owner-authorized architecture and invariants for the next implementation slices |
| Not implemented | A target rule that must not be described as a shipped capability |

## 1. A0 Decision And Ownership

### 1.1 Approved target

For `internal_preview`, API and Worker use a **same-PostgreSQL-database adapter**. This
is a modular two-process deployment, not an internal HTTP service split. The ownership
contract is:

| Concern | Owner in target | Process/runtime meaning |
| --- | --- | --- |
| HTTP, authentication, Alembic execution, schema governance | API | API remains the public business gateway and migration executor |
| Research orchestration and provider/tool execution | Worker | Worker claims and dispatches persisted Research work |
| Research job runtime transaction/UoW commit process | Worker-side UoW | The Worker process commits the one claimed attempt transaction; this is not API-process commit |
| DTOs and Protocols | `citeframe-backend-contracts` / `citeframe_contracts` | Pure Python distribution/import; no ORM, settings, provider client, or persistence side effects |
| All SQLAlchemy mappings and the unique Base/metadata | `citeframe-backend-persistence` / `citeframe_persistence` | Neutral mapping distribution for Research and API core/other models; one model set and one metadata identity |
| Research persistence behavior | `citeframe-research-persistence` / `citeframe_research_persistence` | Research repositories, UoW, commands, locks; depends on the two distributions above; never copies mappings or imports `ai_pdf_api` |

The API owns HTTP/auth/Alembic execution and schema governance. The Worker owns
Research orchestration. The Worker-side UoW is the Research job runtime
commit-process owner. Both processes call the same `citeframe_research_persistence`
commands; there is no copied model set, transition implementation, or second ledger.

`citeframe_contracts` may import only Python standard-library typing/serialization
primitives and explicitly approved pure dependencies. It must not import SQLAlchemy,
`ai_pdf_api`, application settings, provider clients, or object-store clients.
`citeframe_persistence` physically owns every Research and API core/other SQLAlchemy
mapping plus the unique DeclarativeBase/metadata.
`citeframe_research_persistence` owns Research repositories/UoW/commands/lock primitives
and must not import `ai_pdf_api` or define a second Base/metadata/model set.

### 1.2 Current fact and non-claims

The repair checkout has the three staged packages. API still owns HTTP/auth/Alembic/schema governance, while the repaired Worker default composition uses the neutral Research UoW/repository for DB-only transitions; API modules remain compatibility/composition facades and ingestion still uses its shared API/Worker Session/ORM path. This repair state is implementer evidence, not an accepted or shipped boundary. R0/R1 and the later ingestion/composition slices are **not implemented**.
Same-DB adapter means the runtime commit process remains in Worker; it must never be
reported as API-process transaction ownership.

### 1.3 A0 stop rules

- A0 is documentation/ownership freeze only; it does not create packages, migrations,
  endpoints, new tables, or a build target.
- A persistence, API, save, replay, permission, or schema meaning change stops for
  `A-DATA`; this design assumes none.
- Internal HTTP/RPC, Redis/Kafka, a database split, and workspace/provider-wide
  capacity are outside this authorized target.
- G/M/P and GitHub settings remain unauthorized.

## 2. Frozen Save And Data Semantics

The target changes code ownership and runtime dispatch, not the persisted contract:

- one planned subproblem = one `ResearchStep`;
- one retry/lease = one `ResearchStepAttempt`;
- one researcher attempt = zero-to-many `ResearchClaim`;
- R1 target: one dispatcher claim operation creates and leases one Attempt, then one handler operation executes exactly that leased Attempt. This is distinct from the persisted `ResearchClaim` entity.

The last rule describes the dispatcher operation boundary. It is **not** a new Claim entity and
does not change A-DATA, schema, public API, save, replay, permission, or artifact
semantics. Existing `Step`, `Attempt`, `Claim`, `Event`, `state_version`, retry, cancel,
reclaim, conflict, artifact, provenance, budget, and permission meanings remain the
semantic oracle. No new persisted `ResearchState` blob may be introduced. Existing `ResearchStep.input_sha256`
retains its current meaning and is part of the unchanged oracle; R1 does not use it as a
new canonical handler-input hash. Defining and populating a canonical handler-input hash
in that field would be a separate A-DATA design and is outside this round.

## 3. Physical Package And Command Boundary

The target dependency direction is:

```text
Dependency direction (consumer -> dependency):

API adapters/commands ───────────────┐
Worker runtime/handlers ─────────────┼──> citeframe_research_persistence
                                     │        (Research repositories/UoW/locks)
                                     └──> citeframe_contracts (pure DTO/Protocol)

citeframe_research_persistence ──────┬──> citeframe_persistence
                                     └──> citeframe_contracts

API adapters/commands and Worker runtime/handlers may also import
citeframe_persistence only through the approved mapping/Session boundary.
```

`citeframe_research_persistence` exposes commands used by both processes, including claim,
lease refresh/reclaim, admission, handler completion, cancellation, provider/tool
reserve/send/reconcile, conflict/join readiness, and artifact publication. Commands
return contract DTOs and explicit reason codes; they do not leak ORM instances.

The same command implementation owns transition validation, scope checks, the existing
command-specific optimistic `state_version` contract where applicable, lease-token/status/expiry
fencing, event append/sequence allocation, budget ledger atomicity, and object-publication
compensation records. API routes use it for
HTTP-facing mutations; Worker handlers use it for job mutations. No API-only helper is
reimplemented in Worker.

A2a is **Research persistence/ports behavior extraction only** after A1b/A2-foundation.
Its exit requires old runtime behavior and database/payload snapshots to match. A2a must
keep the current behavior in which one `process_one` call can drive multiple steps through
the fixed LangGraph StateGraph; it must not prematurely implement R1 single-attempt
dispatch. Mapping relocation belongs to A1b/A2-foundation, not hidden inside A2a.

## 3.1 Staged Python distributions, manifests, and runtime images

The package boundary is staged and has one canonical ownership sequence. A package must
not appear as an empty or behavior-free scaffold before its named slice:

| Slice | Newly introduced distribution and responsibility | Manifest/lock change | Forbidden in this slice |
| --- | --- | --- | --- |
| A1 | `citeframe-backend-contracts` / `citeframe_contracts`: pure DTO/Protocol; migrate only those types and keep necessary legacy re-exports | API and Worker add only this local path source | `citeframe_persistence`, `citeframe_research_persistence`, ORM relocation, Research behavior extraction |
| A1b / A2-foundation | `citeframe-backend-persistence` / `citeframe_persistence`: unique DeclarativeBase/metadata and all ORM mappings | On top of A1, API and Worker add this second local path source | `citeframe_research_persistence`, Research repositories/UoW/commands/locks, schema/save changes |
| A2a | `citeframe-research-persistence` / `citeframe_research_persistence`: Research repositories/UoW/commands/locks and ports | On top of A1b, API and Worker add this third local path source | Behavior-free scaffold before A2a, R0, R1, mapping relocation; preserve current multi-step runtime |

A1 creates and versions only the contracts distribution. A1b/A2-foundation creates and
versions persistence only after A1 has landed. A2a creates and versions Research
persistence only after A1b/A2-foundation has passed its mapping oracle. API and Worker
must not declare, copy, add to `PYTHONPATH`, or import a later-stage distribution early.
The three packages share one final dependency direction: Research persistence depends on
persistence and contracts; no package imports `ai_pdf_api` or defines a second mapping set.
The current `ai_pdf_api.models` surface may re-export the same classes during migration.

A2a is **Research persistence/ports behavior extraction only** after A1b/A2-foundation.
Its exit requires old runtime behavior and database/payload snapshots to match. A2a must
keep the current behavior in which one `process_one` call can drive multiple steps through
the fixed LangGraph StateGraph and current mixed lock behavior; it must not prematurely
implement R0 or R1 single-attempt dispatch. Mapping relocation belongs to A1b/A2-foundation,
not hidden inside A2a.

### Stage export and runtime matrix

At every stage, `requirements.deploy.txt` contains only hash-pinned third-party packages.
The commands run from the repository root and omit only local distributions that already
exist at that stage. The legacy Worker always additionally omits `ai-pdf-api`.

| Stage | API local `--no-emit-package` set | Worker local `--no-emit-package` set | API `PYTHONPATH` | Legacy Worker `PYTHONPATH` | Pre-start smoke imports |
| --- | --- | --- | --- | --- | --- |
| A1 | `citeframe-backend-contracts` | `citeframe-backend-contracts`, `ai-pdf-api` | `/app/packages/backend-contracts/src:/app/apps/api/src` | `/app/packages/backend-contracts/src:/app/apps/api/src:/app/apps/worker/src` | `citeframe_contracts` |
| A1b / A2-foundation | contracts, persistence | contracts, persistence, `ai-pdf-api` | `/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/apps/api/src` | `/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/apps/api/src:/app/apps/worker/src` | `citeframe_contracts`, `citeframe_persistence` |
| A2a | contracts, persistence, research-persistence | contracts, persistence, research-persistence, `ai-pdf-api` | `/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/packages/research-persistence/src:/app/apps/api/src` | `/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/packages/research-persistence/src:/app/apps/api/src:/app/apps/worker/src` | all three modules; assert Research path is not under `/app/apps/api` |

For A1, the exact export commands are:

```bash
uv export --project apps/api --frozen --no-dev --format requirements.txt \
  --no-emit-project \
  --no-emit-package citeframe-backend-contracts \
  --output-file apps/api/requirements.deploy.txt

uv export --project apps/worker --frozen --no-dev --format requirements.txt \
  --no-emit-project \
  --no-emit-package citeframe-backend-contracts \
  --no-emit-package ai-pdf-api \
  --output-file apps/worker/requirements.deploy.txt
```

For A1b/A2-foundation, append only `--no-emit-package citeframe-backend-persistence`
to each command. Do not add the Research persistence flag until A2a.

The final A2a export commands are:

```bash
uv export --project apps/api --frozen --no-dev --format requirements.txt \
  --no-emit-project \
  --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --output-file apps/api/requirements.deploy.txt

uv export --project apps/worker --frozen --no-dev --format requirements.txt \
  --no-emit-project \
  --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --no-emit-package ai-pdf-api \
  --output-file apps/worker/requirements.deploy.txt
```

Production Docker uses source-copy runtime, not local-package pip or wheel installation.
At A1 copy only the contracts `pyproject.toml/src`; at A1b add only the persistence
`pyproject.toml/src`; at A2a add the Research persistence `pyproject.toml/src`. Each
stage installs its hash-pinned third-party requirements first, copies the application
source, sets the stage-specific `PYTHONPATH`, and runs its stage smoke in the final
runtime filesystem immediately before application startup. API and legacy Worker keep
using the existing API source path until the later A5 candidate; A5 removes API source,
API `PYTHONPATH`, and the editable API dependency only after its own gate.

The stage smoke commands are:

```bash
# A1
python -c 'import citeframe_contracts; print("backend-contracts-import-smoke=pass")'
# A1b / A2-foundation
python -c 'import citeframe_contracts, citeframe_persistence; print("backend-persistence-import-smoke=pass")'
# A2a final
python -c 'from pathlib import Path; import citeframe_contracts, citeframe_persistence, citeframe_research_persistence; p = Path(citeframe_research_persistence.__file__).resolve(); assert "/app/apps/api" not in str(p), p; print("backend-package-import-smoke=pass")'
```

No local package is installed through pip, a wheel, or `--require-hashes`; the only pip
input is the relevant third-party `requirements.deploy.txt`. The final A2a COPY paths
are:

```dockerfile
COPY packages/backend-contracts/pyproject.toml /app/packages/backend-contracts/pyproject.toml
COPY packages/backend-contracts/src /app/packages/backend-contracts/src
COPY packages/backend-persistence/pyproject.toml /app/packages/backend-persistence/pyproject.toml
COPY packages/backend-persistence/src /app/packages/backend-persistence/src
COPY packages/research-persistence/pyproject.toml /app/packages/research-persistence/pyproject.toml
COPY packages/research-persistence/src /app/packages/research-persistence/src
```

A1 and A1b use the corresponding prefix of these COPY paths and corresponding prefix
of the `PYTHONPATH` matrix; they must not copy or expose a later-stage package.

## 3.2 Cross-domain dependency matrix and A2a import gate

Current Research service code reads `Asset`, `AssetRepresentation`, `Workspace`, and
`WorkspaceMembership` mappings, and also reaches storage, provider, retrieval, observability,
and agent-registry services. The target separates these concerns:

| Domain | Target home | Allowed dependency from `citeframe_research_persistence` |
| --- | --- | --- |
| `Asset`, `AssetRepresentation`, `Workspace`, `WorkspaceMembership` and all API core/other ORM mappings | `citeframe_persistence.models` | Yes, through the neutral mapping distribution and one Session/UoW; no API package import |
| Research ORM mappings | `citeframe_persistence.models` | Yes, same mapping set; not redefined by Research persistence |
| Storage/object-store, provider, retrieval, observability, agent registry | API/Worker composition adapters (or a future neutral runtime package) | No; expose only `citeframe_contracts` Protocol/DTO ports |
| Research transaction behavior | `citeframe_research_persistence` | Owns DB/transaction commands, repositories, UoW, locks, and fencing only |

A2a import gates must prove `citeframe_research_persistence` imports neither
`ai_pdf_api` nor storage/provider/retrieval/observability/agent-registry implementations;
its only non-stdlib runtime edges are `citeframe_contracts`, `citeframe_persistence`, and
SQLAlchemy. Composition tests prove API and Worker adapters supply the non-DB ports.
## 4. PostgreSQL Business Truth And R1 Runtime Orchestration Target

**Current runtime fact:** the Worker still uses a fixed LangGraph `StateGraph(ResearchState)`
for in-process execution. It is not the persistence/checkpoint/business truth: PostgreSQL
rows and immutable artifacts remain authoritative.

PostgreSQL persisted state is authoritative for the fixed DAG:

- `ResearchStep` and `StepDependency` define topology;
- readiness is recomputed from committed predecessor state;
- join and conflict gates are persisted transitions;
- cancellation, retry, reclaim, and terminal state are database mutations;
- `ResearchEvent.seq` is the replay truth; `Run`/`Step` `state_version` remains the
  existing command/API optimistic concurrency contract, not a universal Worker fence;
- provider/tool reserve, outcome-unknown reconciliation, and budget ledger are durable.

During A2a, the current fixed LangGraph StateGraph remains the in-process executor so
one `process_one` call may continue to drive multiple steps; it is still not a
persistence/checkpoint authority. After A2a is accepted, R1 removes LangGraph from
runtime step execution (it may remain only as a plan-approval topology validator).
The R1 dispatcher must not let LangGraph claim, execute, checkpoint, or publish a
Research step. Each R1 handler starts by rebuilding its input from the database and
validating upstream persisted StepDependency/status, execution snapshot id/hash, and
artifact/claim/evidence provenance and hashes. It carries no cross-step in-memory
`ResearchState`; only contract DTOs for this one handler call may cross the process
boundary.

### 4.1 R1 one-claimed-attempt dispatcher

R1 changes `process_one` into a dispatcher with this exact unit of work:

```text
claim one eligible queued Step
  -> create exactly one new ResearchStepAttempt and its lease
  -> run exactly that Attempt's one step-kind handler
  -> atomically complete Attempt/Step/Event and newly-ready dependents
  -> return to claim loop
```

The single-Attempt unit is per dispatcher loop, not a process-wide serialism
requirement. Production R1 runs a bounded pool of independent dispatcher loops; each
loop owns its database session/processor and may claim the next Attempt while other
loops execute their handlers. The deployment must configure at least two loops when
Research is enabled, and the pool width plus the persisted per-Run
`maxParallelResearchers` cap bound concurrency. No loop shares cross-step
`ResearchState` or SQLAlchemy identity state with another loop. R1 acceptance includes a
production-shaped two-loop fixture with two researcher Steps that proves real overlap and
wall time materially below the serialized sum, while retaining the V4 branch-parallel
semantics.

Lease lifecycle is deliberately separate from claim and reclaim:

- A normal claim creates a new `ResearchStepAttempt` for a `queued` Step, with a new
  attempt number and lease token. It never refreshes an existing Attempt.
- A heartbeat extends the lease expiry and heartbeat timestamp of that same currently
  `running` Attempt after validating its token and unexpired lease. It never creates an
  Attempt and never revives an expired one.
- Expired reclaim locks the existing Run/Step/Attempt chain under R0, marks the old Attempt
  `abandoned`, synchronizes the Step through its existing `failed`/`queued` retry path
  (or `cancelled`/terminal path), and performs existing provider/tool recovery. A later
  retry claim creates a new Attempt. An expired Attempt is never refreshed or resurrected.

A handler may produce zero-to-many Claims, provider/tool rows, and artifacts allowed
by its step contract, but it cannot claim or execute another Step. It must not run
a whole DAG, fan-out hidden work, or rely on a process-local graph state. The final transaction re-reads the attempt identity and verifies run/step scope,
Attempt status, lease token, and lease expiry policy before committing. It also validates
existing execution snapshot identity/hash, upstream persisted status, and
artifact/claim/evidence provenance/hash semantics; it does not reinterpret `input_sha256`.
`Run`/`Step` `state_version` is checked or incremented only by commands whose existing
API optimistic contract requires it; it is not a blanket Worker completion fence. A stale
or late worker gets a deterministic lease/status fenced rejection and cannot advance a
Step, Event, dependent, or Artifact.

R0 is a separate implementation slice after A2a. A2a must be accepted before R0, and R0
must be accepted before R1 or per-Run admission; no slice may hide another in a shared PR.

### 4.2 R2 real multi-worker proof

R2 is not a unit-test-only gate. Against real PostgreSQL, at least two Worker
processes must race on the same Run and prove unique claim/lease ownership, bounded
parallelism, retry/reclaim, cancel races, provider races, join readiness, conflict
resume, and recovery without duplicate terminal facts. SQLite or an in-memory fake
is insufficient for the Critical gate.

## 5. R0 Lock Normalization, Identity Refresh, And Fencing

**Current runtime fact:** lock acquisition is mixed and conflicting. Many Worker attempt
paths acquire `Attempt -> Step -> Run`; claim acquires `Step -> Run`; API cancel, retry,
and decision paths acquire `Run -> Step`. Claim-versus-cancel therefore has a real
reverse-order deadlock ring. The current A2a behavior retains this fact until R0; it must
not be described as one authoritative lock order or as a safe claim exception.

R0 is a separate implementation slice after A2a and before R1 or per-Run admission.
R0 changes lock acquisition order only. It does not change persistence, API, save,
replay, permission, transition, or payload semantics. The frozen target aggregate-root
order is:

```text
ResearchRun -> ResearchStep -> ResearchStepAttempt -> provider/tool Call -> ResearchBudgetLedger
```

For an attempt or provider/tool Call id path, first read only the parent ids without
locking. Those reads are location hints, not decisions. Then acquire every required row
in the target `Run -> Step -> Attempt -> Call -> Ledger` order, refresh the SQLAlchemy
identity map, and revalidate the complete run/step/attempt/call chain, scope, status,
lease token, and lease expiry. If any parent id or status changed after the location read,
fail the revalidation deterministically; do not continue from stale identity-map facts.

Claim uses the new Run-first protocol: select candidate Runs that have queued work with
`FOR UPDATE SKIP LOCKED`, ordered by each Run's minimum eligible Step tuple `(queued_at, created_at, step_id)`, then Run id.
Lock the candidate Run first, revalidate Run scope/status and the frozen cap, then lock
one eligible queued Step belonging to that Run using the exact existing global order
`queued_at`, `created_at`, then Step ID, and create the Attempt. Candidate Runs are
ordered by the minimum eligible Step tuple `(queued_at, created_at, step_id)`, then Run
ID, so the Run-first protocol changes lock order without changing which Step wins ties. It never locks a Step and then waits for its Run. Cancel remains Run-first:
lock the Run, then lock the affected Steps in stable Step-id order. Complete, heartbeat,
reclaim, retry, join, conflict decision, provider/tool reserve/send/reconcile/cancel,
and artifact publication all use the same target order and refresh/revalidate before
mutating.

R0 must not add deadlock retries to hide a lock-order regression. Its acceptance requires
real PostgreSQL `pg_locks` and lock-timeout evidence for claim-versus-cancel,
claim-versus-complete, reclaim-versus-provider/tool, two claims on one Run, and claims on
different Runs. The semantic oracle is unchanged save/API/payload behavior with only lock
acquisition order changed.

`Run`/`Step` `state_version` continues to be read, incremented, and checked only by the
existing command/API optimistic contracts that already require it; it is not imposed as a
global Worker completion precondition. Late completion is rejected after the final ordered
revalidation. Provider/tool reserve, send, reconcile, and cancel retain the existing
outcome-unknown semantics: an already-sent call may be reconciled after Run cancellation
when usage is billable, while a reserved unsent call after cancellation cannot be sent.
Object publication retains commit-unknown compensation/reconciliation semantics.

Lease lifecycle is exact: normal claim creates a new Attempt for a queued Step; heartbeat
only extends that same running Attempt; expiry reclaim marks the old Attempt `abandoned`,
synchronizes Step through its existing failed/queued retry or cancellation path, and a
later retry claim creates a new Attempt. An expired Attempt is never refreshed or revived.

## 6. Per-Run Researcher Admission Without Schema Change

No slot table or schema change is authorized. Existing `ResearchStepAttempt` rows are
the durable slot records. R1 admission is implemented only after R0 and serializes on
the same `ResearchRun` row under the target Run-first order.

Within that Run-row critical section:

1. Use database time, never a Worker wall clock, for lease validity.
2. Count effective running researcher attempts whose lease is unexpired.
3. Admit a new Researcher attempt only when the count is below frozen
   `maxParallelResearchers` (`1` and `N` are both valid frozen values).
4. An expired attempt does not consume a slot for new admission, but its existing
   recovery path must atomically synchronize Attempt/Step status before reuse.
5. Release/reclaim/cancel/complete updates the same Run/Step/Attempt facts under the
   same ordered lock protocol.

`claim_next_research_step` starts from a candidate Run with queued work, ordered by
that Run's minimum eligible Step tuple `(queued_at, created_at, step_id)`, then Run ID.
It locks that Run first and
revalidates scope/status/cap. A cap-full Run causes the entire claim transaction to
rollback, releasing the Run lock; the worker records the Run id in local
`excluded_run_ids` and continues scanning in a new transaction. It must not lock a Step,
change any status, create an Attempt, or append an Event for that Run. Only after the Run
passes the cap check does the transaction lock an eligible queued Step using the exact existing `queued_at`, then `created_at`, then Step ID
ordering, and create the Attempt. Query-level cap filtering is an efficiency prefilter only;
correctness comes from the locked Run recheck. The invocation must not head-block or
return empty prematurely while another eligible Run exists.

The R2 matrix includes a cap-full Run plus another queued eligible Run, repeated claims
under contention, an equal-`queued_at`/`created_at` tie fixture proving Step ID parity, and a no-starvation/fairness assertion: the eligible Run continues to
be claimable while the cap-full Run remains queued, without mutating the cap-full Run's
Step or Event state. Workspace-wide and provider-wide capacity remain future scope.

## 7. Independent W1 Research SSE

W1 is a separate Web/runtime slice; it is not part of A2a or R1. The client may apply
an event only when its payload contains explicit, schema-approved fields that prove
the local state transition. A response with `currentEventSeq < localAppliedSeq` is
discarded; responses for a switched Run are aborted or discarded.

The request policy is single-flight: one active fetch per Run, a dirty bit for changes
observed while it is active, and a small coalescing window as a performance parameter.
The window must never delay terminal events. On `terminal`, refresh immediately.

Artifact list refresh is event-directed: refresh only on artifact/decision/terminal
events (and explicit history-gap recovery), not on every delta. Artifact content is
cached by `(artifactId, sha256)`, not by position or list order.

History gaps or cursor conflicts trigger a full authoritative read.
`LISTEN/NOTIFY` is post-commit wakeup only; persisted events plus periodic replay
remain authoritative when notifications are lost, duplicated, or arrive before a
client can read.

W1 acceptance covers burst coalescing, stale responses, Run switch, reconnect, lost
notify, history gap/cursor conflict, artifact hash replacement, and immediate terminal
visibility.

## 8. Implementation Slices And Gates

| Slice | Scope | Must not include | Exit evidence |
| --- | --- | --- | --- |
| A0 | Freeze ownership, package boundaries, save semantics, lock order, fencing, per-Run admission | Production code, schema/API/save meaning, G/M/P/GitHub settings | This design + SSoT/ADR links; owner authorization recorded |
| A1 | `citeframe-backend-contracts` / `citeframe_contracts` pure DTO/Protocol package | ORM, settings, provider clients, runtime scheduling | Dependency/import proof |
| A1b / A2-foundation | `citeframe-backend-persistence` / `citeframe_persistence`: relocate unique Base/metadata and all API/Research mappings | Second Base/metadata/model set, schema/save change, Research transition logic | Table/column/constraint/index zero drift, one metadata identity, Alembic/runtime table-set equality, import proof |
| A2a | `citeframe-research-persistence` / `citeframe_research_persistence`: Research repositories/UoW/commands/locks; preserve current runtime | R0 lock change, R1 dispatcher, mapping relocation, schema/save change; cannot precede A1b | Current multi-step process_one behavior and old/new DB/payload/event/recovery snapshots; Research-only import smoke |
| R0 | Normalize all multi-row lock acquisition to `Run -> Step -> Attempt -> Call -> Ledger` | Save/API/payload/transition meaning, R1 dispatcher, deadlock retry | Real PostgreSQL lock-timeout/`pg_locks` evidence for claim/cancel/complete/reclaim/provider and two-claim races; semantic oracle equal |
| R1 | One-claimed-attempt dispatcher through bounded concurrent loops and one step handler per loop | A2 extraction or R0 change in same PR, whole-DAG execution, LangGraph runtime authority | One-step handler tests, production-shaped two-loop overlap/wall-time evidence, and state/lease/fencing oracle |
| R2 | Real PostgreSQL multi-Worker contention/recovery proof | SQLite-only or simulated admission claim | 2+ Worker matrix and immutable reports |
| A3/A4 | Nine ingestion modalities and composition-root migration | Research dispatcher changes | Existing modality object/hash/compensation oracle |
| A5 | Candidate API-source-free Worker build | Premature legacy dependency removal | Import/start/ingest/Research/recovery/version-mismatch smoke |
| A6 | Replace legacy target after A5 | Unreviewed fallback/compatibility path | Deploy/restore regression |
| W1 | Research SSE state gate/cache/replay behavior | API/DB contract changes, SSE/Chat contract merge | Browser/network/state evidence and SSE matrix |

A2a may run a **Research-only import smoke** only after A1b/A2-foundation. It cannot claim a complete
API-source-free Worker. Only after A3/A4, R1/R2, composition-root and recovery gates
pass may A5 claim a complete API-source-free Worker candidate.

## 9. Semantic Oracle And Test Matrix

The pre/post comparison is Critical and must retain immutable fixtures. For every
case, capture old/new database snapshots and API/Worker payload snapshots, then compare:

| Area | Invariant/evidence |
| --- | --- |
| Save contracts | `Step`, `Attempt`, `Claim`, `Event.seq`, `state_version`, retry, cancel, reclaim, conflict, artifact hash/provenance, budget, permission, and API response meaning are equal |
| Scheduler | A2a preserves one `process_one` call's current multi-step LangGraph behavior and current mixed lock behavior; R0 changes lock order only; R1 changes runtime dispatch after R0 through bounded concurrent loops; production two-loop overlap/wall-time evidence passes; no duplicate Step completion; readiness/join follows committed DB state |
| Locks/fencing | R0 target order `Run -> Step -> Attempt -> Call -> Ledger`; location reads never decide; ordered lock/refresh/revalidate rejects changed chains; stale Attempt status/token/expiry has no late side effects; existing state_version command contracts remain equal |
| Admission | After R0, cap=1 and cap=N never exceed effective unexpired researcher attempts; cap-full rollback releases Run lock and mutates no Step/Event; expired lease recovery is atomic |
| Provider/tool | reserve/send/reconcile/cancel and billable outcome-unknown behavior remains equal; budget ledger is atomic |
| Object publication | commit-unknown path preserves publication hash, compensation, retry, and final artifact meaning |
| Event oracle | A2a current runtime requires byte/row-equal event snapshots. R1/R2 require a per-Run `seq` that starts at 1, is contiguous and unique within that Run, and is allocated atomically across Workers; per-Step `queued < started < terminal`; legal Attempt/lease event order; dependencies succeeded before dependent queued; Run terminal last; dedupe/unique terminal; equal payload schema/error meaning. Independent researcher event interleaving may differ. |
| Research SSE | stale response discarded, Run switch aborts, explicit event gate, artifact `(id, sha256)` cache, terminal immediate, full gap/cursor recovery |
| Boundary | `citeframe_contracts` is pure; `citeframe_persistence` owns one mapping/metadata set; `citeframe_research_persistence` imports neither `ai_pdf_api` nor non-DB service implementations; API and Worker use same commands |
| Scope | no new schema, public API, save/replay/permission meaning, or ResearchState payload |

Required real-PostgreSQL scenarios: R0 claim-versus-cancel, claim-versus-complete,
reclaim-versus-provider/tool, two claims on one Run, claims on different Runs, with
`pg_locks` and lock-timeout evidence; then two or more Workers contending on one Run;
cap=1 and cap=N; lease expiry and late completion; cancel/provider races; join/recovery;
conflict decision/resume; object publication outcome-unknown; budget exhaustion and
reconcile. Required SSE scenarios: burst updates, stale response, reconnect, lost
notification, terminal event, history gap/cursor conflict, Run switch, and artifact
hash/provenance refresh.

A slice is not accepted because tests merely instantiate a new class or because a
SQLite fake is green. The reviewer must record pass/not-applicable/blocked for
contracts, data/save, locking, runtime scheduling, concurrency, SSE, recovery, and
SSoT/spec synchronization.

## 10. Authorization And Current Status

Delivery state on 2026-08-24: PR #20 merged at `origin/main@9f40241`; behavioral baseline `d1b5945`; rejected initial snapshot `20d411e`; initial review record `5a6ee38`; dirty repair branch `work/research-boundary-runtime-20260824`. The repair has implementer evidence (`71` exact-audit API, `122` API Research, `58` Worker Research, differential `equal=true` / `coverage=7`, deploy `6+2`, lock/export/YAML pass). Docker Hub timeout leaves clean-image runtime proof blocked, so no A2a `ACCEPT` is claimed.

Owner authorization covers the A0 ownership/transport direction and conditionally authorizes
A1/A1b/A2-foundation/A2a/R0/R1/R2/W1 within these boundaries. The design re-audit is
`ACCEPT (High=0, Medium=0, Low=0)` and A1 was independently accepted on `2026-08-20`.
A1b/A2-foundation was independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0);
A2a initial snapshot `20d411e` received independent Critical `REWORK` (`High=1`, `Medium=5`, `Low=1`). The bounded rework on `work/research-boundary-runtime-20260824` is implementer-complete but remains uncommitted and unpushed; a new independent Critical re-audit against an immutable repair snapshot is pending. No A2a `ACCEPT` is claimed. R0/R1/R2/W1 and downstream remain blocked. G/M/P and GitHub repository settings remain unapproved.

This text itself does not authorize additional schema/API changes, G/M/P work, GitHub
settings, provider spend, or user research. The implementation sequence is A1 ->
A1b/A2-foundation -> A2a -> R0 -> R1/R2. A2a repair implementation is complete but its next step is a new independent Critical re-audit against an immutable snapshot, including Docker clean-image runtime evidence; R0/R1/R2 remain blocked until their named gates. No schema/API/save/
replay/permission changes are authorized; later slices remain blocked until their named gates.
