# R1 Single-Attempt Dispatcher Independent Critical Review

Date: 2026-08-24
Follow-up date: 2026-08-25
Reviewer scope: final module-level follow-up through canonical closure `559997d073cc2d26fb346c30e2ab9f20550b673f`
Initial candidate: `f4a1d1d7451d707d90948612791d1bb2aac410f3`
Runtime rework: `473213d79154f3fbcf6044e1c4e62ed65038e1c1`
Implementation ledger closure: `652cfd47f8bc462038e1bd623afc2b33a4ce511a`
Canonical documentation closure reviewed: `559997d073cc2d26fb346c30e2ab9f20550b673f`
Final delivery-truth closure: `80d395d4fd19c0146b22befc2929bc556cfe62fa`
Starting SHA: `8674d4dc407048471f7b14b23b821e72529487bf`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
Branch: `work/research-r1-single-attempt-20260824`
Verdict: **ACCEPT (High=0, Medium=0, Low=0)**

## Follow-up Finding Closure

### Historical follow-up Medium 1: final delivery contradictions closed by `80d395d`

Follow-up review of `559997d` found three current-state statements that still described
the accepted A2a local chain as awaiting remote delivery. Final docs-only closure
`80d395d4fd19c0146b22befc2929bc556cfe62fa` changes exactly the two named canonical
architecture files and only those three reported statements:

- `docs/architecture/database-design.md:403` now records A2a/R0 delivery through PR #21 at
  `origin/main@8674d4d` and keeps R1 runtime/docs local pending review.
- `docs/architecture/api-worker-boundary-follow-up-2026-08-18.md:173` now states the same
  delivered A2a/R0 fact without the contradictory pending-delivery clause.
- `docs/architecture/api-worker-boundary-follow-up-2026-08-18.md:321` now records PR #21
  delivery and separately identifies local R1 runtime/docs review candidates.

Targeted stale-delivery scan is zero. `git show --check 80d395d` and
`git diff --check 8674d4d..80d395d` pass. The workbench externally binds
`r1_docs_final=80d395d4fd19c0146b22befc2929bc556cfe62fa`. No runtime, test, contract,
schema, API, save/replay/permission, R0, admission, R2, W1, or other documentation scope
was changed. Historical initial-review wording remains historical and is superseded by the
explicit current-state override.

Current findings: **none (High=0, Medium=0, Low=0)**.

## Follow-up Closure Matrix

| Initial finding | Result | Follow-up evidence |
| --- | --- | --- |
| M1 human-owned gate mutation | pass | Real ORM test proves claim-next returns no lease, claim-specific returns 409, and complete Run/Step/Decision rows plus Attempt/Event counts are unchanged. Allowlist is checked in candidate selection, specific locator handling, and locked-step revalidation before membership or mutation. |
| M2 shared-stop causal error loss | pass | Real `run_worker` tests propagate an in-flight error when stop is already set and when retry wait is interrupted. Real main/pool composition returns ingestion, two dispatcher, and shutdown leaves exactly once. |
| M3 ledger/hygiene mismatch | pass | Runtime `473213d`, ledger `652cfd4`, local/no-upstream/no-remote/no-push state, historical f4 evidence, fresh exact-head evidence, and external non-recursive closure binding are truthful. `git diff --check 8674d4d..559997d` passes. |
| M4 canonical SSoT/delivery | pass | Final docs-only `80d395d` changes exactly the two named files/three reported statements; stale delivery scan is zero and workbench binding is exact. |
| Code/architecture/contracts | pass | No remaining production, boundary, save/API/replay/permission, R0, admission, R2, W1, provider/tool/object/Event, or source-shape finding was found. |

## Follow-up Verification

| Verification | Result |
| --- | --- |
| R1 named gate at docs head `559997d` | Worker `64 passed`; API `40 passed`, one existing warning; imports/locks/compile/range hygiene pass |
| Human-gate real ORM oracle | `1 passed`, one existing warning |
| Real shared-stop/main error oracles | `4 passed` |
| Exact runtime A2a report | `equal=true`, candidate `473213d`, coverage `7/7`, handled `3 -> 8`, 29+29 relation groups, 40 process Events, UoW `43`; report SHA `988c5b34...` |
| R0 source-bound PostgreSQL report | `7/7`, PostgreSQL `17.11`, pgvector `0.8.6`, deadlocks `0 -> 0`, no `40P01`/`55P03`; all six source hashes exact; report SHA `82388972...` |
| Runtime import closure | LangGraph and executor engine absent |
| Full Worker | not repeated; `349 passed` is already bound to immutable runtime `473213d`, and later commits are documentation-only |
| Runtime/doc scope | `473213d` changes five bounded runtime/test/gate files; `652cfd4` changes only the implementation ledger; `559997d` changes canonical docs; final `80d395d` changes only two named docs/three stale statements |
| Final delivery-truth closure | `80d395d`; targeted stale scan zero; exact commit and start-to-head hygiene pass; no runtime test repeat required |
| Worktree before reviewer update | only this untracked reviewer artifact |

## Follow-up Final Decision

**ACCEPT (High=0, Medium=0, Low=0).** Runtime `473213d` closes the human-gate and
shared-stop findings without changing schema/API/save/replay/permission or downstream
scope. Ledger closure `652cfd4` truthfully binds the immutable runtime and evidence.
Canonical status `559997d` plus final delivery-truth closure `80d395d` close all durable
SSoT/delivery drift with exact docs-only scope and clean hygiene. The one-Attempt runtime,
production pool, LangGraph import boundary, A2a terminal oracle, R0 lock/fencing evidence,
provider/tool/object/Event semantics, and blocked per-Run admission/R2/W1 boundaries are
acceptable. No finding remains. R1 may proceed through normal local commit/push/PR delivery;
this review does not itself authorize or perform a push. Per-Run admission, R2, W1, and
other downstream work remain governed by their separate gates.

## Initial Review Record (Historical)

## Initial Findings (Historical)

### Medium 1: the Worker mutates a human-owned plan gate before it fails closed

`claim_next_research_step` still treats every queued Step as eligible. The production outer
claim in `ResearchWorkProcessor.claim()` therefore creates an Attempt, changes Run/Step
status and state versions, and appends Events before `SingleAttemptStepDispatcher.execute()`
recognizes `plan_approval_gate` as human-owned and raises
`human_owned_research_step_claimed`.

Relevant code:

- `packages/research-persistence/src/citeframe_research_persistence/lease.py:221` filters
  only on `status == "queued"` and Run identity.
- `apps/worker/src/ai_pdf_worker/research_runtime_processor.py:88` commits the unrestricted
  outer claim.
- `apps/worker/src/ai_pdf_worker/research_runtime_handlers.py:152` rejects the kind only
  after that committed mutation.
- `apps/worker/tests/test_research_single_attempt_dispatcher.py:333` calls the dispatcher
  directly and therefore never exercises the outer claim transaction.

An independent real-ORM probe changed a valid fixture Step to a queued
`plan_approval_gate` and invoked the production neutral claim command. Result:

```text
human_gate_claimed=True step_status=running attempts=0->1 events=0->2 kind=plan_approval_gate
```

This does not submit or approve a human decision, but it violates the explicit R1 authority
boundary and can strand the gate behind a Worker-owned running Attempt. The minimum repair
is to make the production outer claim unable to claim a human-owned Step and add a
production-command regression that proves a queued plan gate leaves Run, Step, Attempt,
Event, state-version, and decision facts byte-for-byte unchanged.

Acceptance oracle for this finding:

```text
queued plan_approval_gate before Worker poll
  -> process_one does not create an Attempt
  -> no Run/Step status or state_version change
  -> no Event or HumanDecision change
  -> no step-kind handler or provider/tool path entered
```

### Medium 2: a dispatcher stop can suppress a simultaneous ingestion failure

`ResearchDispatcherPool._run_loop()` sets the shared stop event when a dispatcher exhausts
retries. If ingestion is already executing and then fails, `run_worker()` catches that
exception, sees the shared stop event, logs `worker_stop_after_iteration_error`, and breaks
without re-raising. `main()` consequently has no ingestion error to include with dispatcher
or shutdown errors.

Relevant code:

- `apps/worker/src/ai_pdf_worker/main.py:201` suppresses the caught iteration exception
  whenever `stop_event.is_set()`.
- `apps/worker/src/ai_pdf_worker/main.py:296` sets that same event on a dispatcher failure.
- `apps/worker/tests/test_main.py:215` claims to preserve ingestion and dispatcher failures,
  but replaces `run_worker` itself. It bypasses the suppression branch being asserted.

Independent production-function probe:

```python
stop = Event()

def ingestion():
    stop.set()
    raise ValueError("simultaneous-ingestion-failure")

run_worker(stop_event=stop, process_job=ingestion, ...)
```

Observed result:

```text
worker_iteration_failed attempt=1 max_consecutive_errors=5 error_type=ValueError
propagated=none (failure suppressed)
```

The aggregation code after pool join is structurally correct only for failures that reach
it. The minimum repair is to preserve an iteration failure even when a sibling has already
requested stop, and to test the real `run_worker` plus pool/controller composition rather
than replacing the function under test.

Acceptance oracle for this finding:

```text
dispatcher failure sets shared stop while ingestion is in flight
  + ingestion raises its own error
  + optional pool shutdown error
  -> main raises one error/group containing every causal leaf exactly once
  -> sibling loops stop and join within the configured deadline
```

### Medium 3: the implementation ledger does not bind the immutable candidate and its hygiene claim is false

The candidate is a clean local commit at
`f4a1d1d7451d707d90948612791d1bb2aac410f3`, but the committed implementation ledger at
`specs/v5/post-v5-optimization/reviews/r1-single-attempt-dispatcher-implementation-2026-08-24.md:12`
still says `Commit: none`. Its recorded A2a semantic/report identities were generated while
the implementation was an uncommitted worktree on start SHA `8674d4d`; they do not bind the
exact committed candidate.

The ledger also claims hygiene passed, while exact candidate hygiene fails:

```text
$ git show --check --oneline f4a1d1d7451d707d90948612791d1bb2aac410f3
f4a1d1d refactor(research): add R1 single-attempt dispatcher
specs/v5/post-v5-optimization/reviews/r1-single-attempt-dispatcher-implementation-2026-08-24.md:3: trailing whitespace.
+Date: 2026-08-24 [two trailing spaces]
```

`infra/scripts/run-r1-single-attempt-gate.sh` runs `git diff --check` without a range. On a
clean committed candidate that checks only uncommitted changes, so the gate reports pass
while `git diff --check 8674d4d..f4a1d1d` fails. This is an evidence-gate defect, not a
production runtime defect.

The minimum repair is documentation/gate-only: identify the exact production candidate and
current push state, bind fresh exact-head evidence, remove the whitespace, and make the
repeatable gate check the intended start-to-candidate range or the exact commit.

### Medium 4: canonical SSoT/spec status remains stale after the R1 implementation slice

The candidate adds an implementation ledger but does not update any canonical SSoT/spec
artifact. Existing current-state text still says R1 is unimplemented or only the next
future slice, including:

- `specs/v5/post-v5-optimization/research-boundary-runtime-design.md:59`
- `specs/v5/post-v5-optimization/spec.md:148`
- `specs/v5/post-v5-optimization/tasks.md:53`
- `docs/architecture/research-workflow-runtime.md:55`
- `docs/ssot/system-architecture.md:764`

Several of the same current-state sections also still describe already merged A2a/R0
commits as local and unpushed even though the immutable R1 start is merged
`origin/main@8674d4dc407048471f7b14b23b821e72529487bf` from PR #21. Historical sections may
retain their original facts, but current-state sections must not.

The minimum repair is to synchronize the existing canonical artifacts to
`R1 implementer-complete, Critical REWORK pending`, record the exact start/candidate/branch
and blocked R2/W1/admission state, and preserve the rule that no ACCEPT is claimed until a
follow-up independent review closes every finding.

## Critical Semantic Oracle

The R1 candidate is acceptable only if all statements below are independently verifiable:

1. One `process_one()` call performs at most one outer claim. A handled call creates exactly
   one new Attempt for exactly one Step and enters exactly one handler for that claimed kind.
2. No handler calls `claim_specific_research_step`, claims another Step, invokes a whole
   graph, or retains cross-step process state. DB/artifact-derived DTOs rebuilt for one
   handler call are allowed; retained `ResearchState` or SQLAlchemy identity state is not.
3. All nine persisted kinds have one explicit owner: planner plus seven Worker execution
   kinds, and the API/human-owned `plan_approval_gate`. The human gate is not Worker-claimable
   and a malformed queued gate causes zero Worker mutation.
4. Planner validation and publication semantics remain equal to the accepted fixed
   executor. Plan topology may remain in legacy/evaluation code, but production runtime
   import and call paths do not load LangGraph, `research_executor_engine`, or
   `BoundedResearchExecutor`.
5. Researcher, join, verifier, critic, conflict gate, synthesizer, and publisher rebuild
   their exact Attempt and handler inputs from persisted truth. They validate scope,
   Attempt number/status/token/expiry, unchanged `input_sha256` meaning, dependencies,
   snapshot and plan hashes, Claim/Evidence ownership and hashes, verification/critic
   provenance, and synthesis checkpoint bytes/provenance before effects.
6. Production uses a fixed bounded pool with default width at least two. Each loop owns a
   distinct processor, session-factory identity, and Worker ID. Two 200 ms handlers overlap,
   complete once each, and finish materially below the 400 ms serial sum.
7. Ingestion and Research make progress in independent loops. Fatal dispatcher, ingestion,
   sibling, and shutdown failures are not discarded; every causal leaf reaches the caller
   exactly once. Shutdown observes one deadline.
8. Invalid dispatcher widths fail before startup. Metrics describe actual active/handled
   work and do not invent claims or completions.
9. R1 adds no per-Run admission, cap-full exclusion, fairness, R2 multi-process proof, W1,
   schema, public API, save/replay/permission, Event, state-version, provider/tool, object
   publication, or other contract change.
10. Accepted R0 ordering and fencing remain `Run -> Step -> Attempt -> Call -> Ledger`, with
    no deadlock retry and no regression in the exact source-bound PostgreSQL evidence.

## Allowed Scheduling Delta

R1 intentionally changes scheduler granularity. The allowed delta is narrow:

- `process_one()` call count, call timing, and independent researcher scheduling
  interleaving may change.
- The frozen fixture baseline remains three handled calls followed by idle:
  `[true, true, true, false]`.
- The R1 candidate remains eight handled calls followed by idle:
  `[true, true, true, true, true, true, true, true, false]`.
- A real parallel schedule may reorder only independent researcher observations. Per-Run
  Event seq remains contiguous and unique; each Step retains
  `queued < started < terminal`; dependencies succeed before dependent queueing; Attempt and
  lease order is legal; Run terminal is last; duplicate terminal facts remain impossible.

Everything else is invariant. The deterministic differential fixture must retain exact
normalized terminal rows for all 29 relation groups, exact API bytes, exact immutable object
bytes, exact Event bytes, and equal lease/retry/cancel/reclaim/permission semantics. Call
count or interleaving is not permission to normalize away a terminal row, payload, object,
Event, partial-order, provider/tool, or publication difference.

## Review Matrix

| Area | Result | Independent judgment |
| --- | --- | --- |
| Goal alignment | blocked | Core one-Attempt dispatch is present, but the human authority boundary and error-preservation requirements are not complete. |
| One outer claim / one handler | pass | `process_one` passes only its outer lease to one explicit handler; no runtime handler calls another claim or whole graph. |
| Persisted kind mapping | blocked | All nine kinds are enumerated correctly, but the human kind is rejected only after the outer claim mutates it. |
| Planner semantics | pass | Direct agent call retains the former plan size, scope, duplicate, evidence, budget, and publication checks; A2a terminal semantics are exact. |
| Persisted input/provenance | pass | Read adapter and completion commands validate Attempt/dependency/snapshot/Claim/Evidence/checkpoint chains; exact happy-path DB/object evidence passes. Mutation coverage should be expanded with the required rework. |
| LangGraph/runtime boundary | pass | Production import smoke and source call scan show no LangGraph, executor engine, or `BoundedResearchExecutor` in the runtime closure. |
| Pool width/loop ownership | pass | Default is two; invalid values below two and non-integers fail; production factories, processors, session-factory identities, and Worker IDs are distinct. |
| Real overlap/no duplicate completion | pass | Two production-shaped processors overlap 200 ms handlers in less than 350 ms and use distinct Step/Attempt/session identities; R0 claim contention and exact terminal snapshots remain unique. |
| Ingestion independence | pass | Production main thread runs ingestion while dedicated threads run Research; neither holds the other's long-lived session. |
| Background error preservation | blocked | A real `run_worker` branch suppresses ingestion failure after a dispatcher sets shared stop. |
| Shutdown | pass | Pool join uses one 130-second deadline, detects live threads, stops siblings, and preserves join errors that reach the controller. |
| Metrics | pass | Existing active/error/claimed/handled observations remain bounded and no new high-cardinality labels were added. |
| Config fail-closed | pass | Width `1`, `0`, negative, and non-integer values reject; default and explicit `2` accept. |
| Per-Run admission/fairness | not applicable | No cap counting, slot admission, cap-full exclusion, or fairness implementation appears in the candidate. |
| R2/W1/SSE | not applicable | No multi-process proof or SSE/Web code is included. |
| Schema/API/save/replay/permission | pass | No model, migration, router, Web, public DTO, or permission path changed; exact A2a API/permission output is equal. |
| Provider/tool/object/Event/state_version | pass | Persistence command sources are unchanged; exact rows/payloads/objects/Events and R0 source hashes remain equal. |
| R0 locks/fencing | pass | Focused tests pass; stored PostgreSQL report is 7/7, deadlocks 0 to 0, no `40P01`/`55P03`, and all six production hashes match the candidate. |
| Python identifiers/imports | pass | Full Worker import execution, `compileall`, AST parsing, and exact runtime import smoke found no unresolved runtime name/import. No static checker is installed. |
| Source shape/evolution | pass | New 415-line handler module is cohesive by step dispatch responsibility; the 564-line test module is cohesive. R2 must not be added to either file mechanically. |
| Test honesty | blocked | The human-gate test bypasses claim and the multi-error test mocks `run_worker`; both miss the production failures above. |
| Delivery ledger/hygiene | blocked | Ledger says no commit and the exact commit has trailing whitespace despite a green HEAD-only gate. |
| SSoT/spec synchronization | blocked | Canonical current-state documents still call R1 unimplemented and contain stale A2a/R0 delivery state. |

## Production Call-Path Review

`ResearchWorkProcessor.process_one()` creates a new `SqlResearchLedgerAdapter` per claimed
Attempt. Planner remains a dedicated one-Step path. Every other Worker-owned kind enters
`SingleAttemptStepDispatcher`, calls `load_step_handler_input`, executes one function from
the explicit map, and calls one existing fenced completion command. The handler module has
no call to `claim_step`, `claim_specific_research_step`, graph invocation, or another
handler. Processor instances retain only session/service/provider/Worker identity, not a
Run graph or cross-step DTO.

The runtime import closure includes `research_runtime`, agents, core, handlers, ports,
processor, schemas, and executor tools. It does not include `langgraph`,
`research_executor_engine`, or `research_executor`. Legacy topology and evaluation tests can
still import those modules outside the production closure.

Result: **pass except for the human-owned kind's pre-dispatch claim mutation described in
Medium 1**.

## A2a Differential

Independent command:

```bash
uv run --project apps/api --frozen python infra/scripts/run-a2a-differential.py \
  --root /home/cc/code/citeframe \
  --baseline-ref d1b5945e977445e4db6bf56ef54cf61607ead2e2 \
  --output /tmp/citeframe-r1-critical-review-f4a1d1d-a2a.json
```

Result: **pass**, `equal=true`, exact candidate head `f4a1d1d7451d707d90948612791d1bb2aac410f3`,
clean semantic/repair worktree, coverage `7/7`, candidate neutral UoW entries `43`, baseline
handled count `3`, candidate handled count `8`, 29 transition relation groups, 29 process
relation groups, 20 transition Event byte records, 40 process Event byte records, three API
response payloads, and five immutable object payloads. Report SHA-256:
`fa9e7dcbee1e8c63087182aa85a3f18461e0eb44740aa22f98273773f03ef739`.

Canonical SHA-256 equality was independently checked for all seven areas:

| Area | Equal | Candidate canonical SHA-256 |
| --- | --- | --- |
| normalized DB rows | yes | `e2b9985ee263f0ec00869236cbc8884582cdd5c67e3d2b3dcdb387db3b898ef` |
| exact payload bytes | yes | `8ef726cb2ed78952067c8f330d81644aaaa0f0c9f571265f4217f6d1fd0ebca8` |
| exact Event bytes | yes | `366cb515009c7f141618cce08d4d83154a6b152ae1ee26761f7591b0cddb0f04` |
| lease fencing | yes | `eddf85241b87bf481bcf11c661b27a013f8e014ebfb94dfee60f325550088c32` |
| retry/cancel/reclaim/recovery | yes | `0b76c32cfbcdfe8269fd8273600c4960541fd86420ba4c3dd8bfe0f3fa6824d8` |
| permission | yes | `1972ac4b909f52ebe7d6c8e6a12fbb5fb4567d26be4f8fcf7bf4a456857c327e` |
| terminal process semantics | yes | `120bf314490a621b645b85e172fde373c8532c14a9e840aac001fed8cf890ec2` |

The frozen environment/pollution and candidate-API-facade mutation gates also passed as
part of the R1 gate. The differential therefore honestly isolates scheduler call count and
retains exact terminal semantics. It does not cover an invalid queued human gate or the
shared-stop error race, so it does not close Medium 1 or Medium 2.

## R0 Lock Evidence Validation

Focused independent command:

```bash
uv run --project apps/api --frozen pytest -q \
  apps/api/tests/test_r0_lock_normalization.py
```

Result: `6 passed`, with one pre-existing Starlette deprecation warning.

The accepted real PostgreSQL report was independently reread from
`/tmp/citeframe-r1-r0-contention-20260824.json` and rebound to the immutable R1 candidate.
Candidate R1 changes no `citeframe_research_persistence` source. All six report source
hashes match current bytes exactly.

- Report SHA-256: `e17183d9521d44ebf8a287386507cc19df04fb8814ad2e532545c6e467e31218`.
- PostgreSQL `17.11`; pgvector `0.8.6`.
- Seven of seven scenarios pass.
- Deadlocks remain `0 -> 0`; no `40P01` or `55P03` appears.
- Cleanup is `pass`; no `citeframe-r0-postgres-*` container remains.
- Claim/cancel, claim/complete, same-Run claim, different-Run claim, locator drift,
  reclaim/provider, and reclaim/tool scenarios remain represented.

Result: **pass**. No accepted R0 lock/fencing regression or hidden deadlock retry was found.

## Verification Evidence

| Verification | Result |
| --- | --- |
| Exact candidate/start identity | `f4a1d1d7451d707d90948612791d1bb2aac410f3` from `8674d4dc407048471f7b14b23b821e72529487bf` |
| Repeatable R1 gate | Worker `62 passed`; API `39 passed`, one existing warning; import/locks/compile pass |
| Full Worker suite | `347 passed in 223.42s` |
| A2a exact-head differential | pass, `equal=true`, coverage `7/7`, report SHA `fa9e7dcb...` |
| R0 focused | `6 passed`, one existing warning |
| R0 PostgreSQL report validation | `7/7`, deadlocks `0 -> 0`, six source hashes exact |
| API and Worker lock check | pass |
| Production runtime import smoke | pass; LangGraph and executor engine absent |
| Dispatcher config probes | `1`, `0`, negative, and non-integer reject; `2` accepts |
| Worker/API Research compileall | pass |
| Runtime AST/import-name scan | pass; no static checker installed |
| Gate shell execution | pass |
| `git diff --check 8674d4d..f4a1d1d` | **fail: implementation ledger line 3 trailing whitespace** |
| Branch/push state | local branch, no upstream, remote branch absent, push none |
| Worktree before review artifact | clean |

## Reverse Review

Assume an R1 regression reached production:

- A whole-graph or second-claim regression should be caught by the exact outer-lease test,
  the explicit handler call scan, candidate call count `8`, and terminal Attempt rows.
- LangGraph runtime re-entry should be caught by exact import smoke and the runtime module
  closure scan.
- Duplicate claim/completion should be caught by the production-shaped pool identities,
  R0 same-Run contention, exact terminal rows, exact Events, and idle-after-terminal probe.
- Lease/input/dependency/snapshot/Claim/Evidence/checkpoint drift should be caught by the
  read adapter plus final fenced persistence commands and exact differential; follow-up
  rework should add negative mutation coverage around these new composite reads.
- Provider/tool/object/Event/permission drift should be caught by exact A2a area hashes and
  unchanged persistence source hashes.
- A human-gate mutation was not caught because the test starts after claim. The required
  outer-command zero-mutation oracle closes that hole.
- A simultaneous ingestion failure was not caught because the test replaces `run_worker`.
  The required real-loop concurrency test closes that hole.
- A stale committed ledger was not caught because the gate checks only worktree diff. An
  explicit start-to-candidate hygiene range closes that hole.

The existing evidence is strong for normal one-Attempt terminal semantics, production
overlap, import ownership, A2a contracts, and R0 fencing. It is not strong enough for human
gate authority, shared-stop failure preservation, or durable delivery traceability.

## Required Rework

1. Prevent the production Worker claim path from claiming `plan_approval_gate`; add a real
   persistence/process-one zero-mutation regression covering Attempt, Event, Run, Step,
   state-version, and HumanDecision facts.
2. Preserve a real ingestion iteration error even when a dispatcher has set shared stop;
   replace the mocked aggregation proof with a deterministic real `run_worker`/pool/main
   test that preserves ingestion, every dispatcher, and optional shutdown failures.
3. Repair the implementation ledger and repeatable hygiene gate so they bind the exact new
   immutable candidate and check the intended commit range. Keep historical precommit
   evidence labeled historical rather than presenting it as exact-head evidence.
4. Synchronize canonical SSoT/spec current-state sections to implementation-complete,
   Critical REWORK pending, while keeping R2/W1/per-Run admission blocked and making no
   acceptance claim.
5. Rerun focused R1, full Worker, exact-head A2a, R0 focused/source-bound PG validation,
   imports/locks/compile, and exact-range hygiene. Return the same implementation agent's
   repaired immutable SHA for independent follow-up review.

## Initial Final Decision (Historical)

**REWORK (High=0, Medium=4, Low=0).** Candidate
`f4a1d1d7451d707d90948612791d1bb2aac410f3` successfully removes LangGraph from the
production runtime closure, dispatches one normal claimed Attempt to one explicit handler,
runs a genuine two-loop production-shaped pool, preserves exact A2a terminal semantics,
and leaves accepted R0 locking and all public contracts unchanged. It cannot receive
Critical ACCEPT because a malformed queued human gate is mutated before rejection, a
shared dispatcher stop can suppress an in-flight ingestion failure, the durable delivery
ledger/hygiene gate does not bind the immutable candidate truthfully, and canonical
SSoT/spec status is stale. R2, W1, per-Run admission, and downstream development remain
blocked.
