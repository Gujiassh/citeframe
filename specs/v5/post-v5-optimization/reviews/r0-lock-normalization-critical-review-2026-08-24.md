# R0 Lock Normalization Independent Critical Review

Date: 2026-08-24
Reviewer scope: immutable candidate `39766c374bd584b0cb834ef103de025d233c87c1`
Starting SHA: `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
Documentation follow-up re-reviewed: `9500bd4f83a0548e4fb161545bd67dc07910a63c`
Second documentation follow-up re-reviewed: `ea3fd53af899076b02b0eb76100db3b15cbe2b5e`
Final documentation closure accepted: `6b8ab475c14a7bbfe90f59a635255ca3768edcf9`
Verdict: **ACCEPT (High=0, Medium=0, Low=0)**

## Historical Findings

### Medium 1 at `39766c3`: the durable delivery ledger did not identify the immutable candidate and its hygiene claim was false

At the initial production review, the R0 implementation record and linked dev-workbench
checkpoint said that the
implementation is uncommitted (`Commit SHA: none`, `implementation remains uncommitted`,
and `delivery=commit none`). The reviewed branch is instead clean at local commit
`39766c374bd584b0cb834ef103de025d233c87c1`, with no upstream and no remote branch. This
breaks the required source/start/repair/commit/push/downstream trace from the implementation
record to the immutable snapshot under review.

The same initial record and checkpoint said `git diff --check` passed, but the exact immutable diff
fails at
`specs/v5/post-v5-optimization/reviews/r0-lock-normalization-implementation-2026-08-24.md:3`
because `Date: 2026-08-24` has trailing whitespace. The production implementation and its
runtime evidence are not invalidated, but the candidate cannot receive Critical `ACCEPT`
while its mandatory delivery/evidence ledger is factually wrong.

The initial required rework was documentation-only:

1. Update the implementation delivery ledger and linked dev-workbench record to identify
   source/start `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`, production commit
   `39766c374bd584b0cb834ef103de025d233c87c1`, local/no-push state, the actual repair branch,
   and blocked downstream targets.
2. Remove the trailing whitespace and rerun `git diff --check` against the new immutable
   review head.
3. Preserve `39766c3` as the production-code commit. Do not change production code to close
   this finding.

No production-code, lock-order, transition, contract, or runtime finding was found.

### Follow-up re-review of `9500bd4`

The documentation-only follow-up closes most of Medium 1:

- `39766c3..9500bd4` changes only the R0 implementation ledger;
- the historical production whitespace is now described truthfully and
  `git diff --check 7ee97471..9500bd4` passes;
- production commit `39766c3`, source/start `7ee97471`, local branch, no upstream, absent
  remote branch, no push, and blocked downstream targets are recorded in the ledger and the
  latest workbench state/checkpoint;
- focused tests remain `8 passed, 1 warning`, no production path differs from `39766c3`, and
  all six production hashes still match PostgreSQL report `95f2608e`.

The Medium is nevertheless still open because the immutable ledger at `9500bd4` describes
the documentation follow-up itself as "an uncommitted worktree change" that "requires a
separate documentation commit" and marks the documentation-only closure pending. At
`9500bd4`, that change is already a committed docs-only child of `39766c3`. Embedding the
docs commit's own SHA is neither required nor possible without another commit, but the
committed/uncommitted state must not be false. A second docs-only closure must replace those
current-state claims with truthful wording, preserve the historical whitespace fact, and
leave production `39766c3` unchanged. Exact docs SHA can continue to be bound by the
workbench and reviewer artifact.

### Second follow-up re-review of `ea3fd53`

The second docs-only commit again preserves production and closes the first follow-up's
specific stale sentence:

- `9500bd4..ea3fd53` changes only the implementation ledger;
- `git diff --check 7ee97471..ea3fd53` passes;
- focused tests remain `8 passed, 1 warning`;
- no production path differs from `39766c3`, and all six production hashes still match
  PostgreSQL report `95f2608e`;
- branch, remote, and latest workbench/checkpoint state correctly bind `39766c3`, `9500bd4`,
  and `ea3fd53` as local/no-upstream/no-remote/no-push artifacts.

The Medium remains open because `ea3fd53` moves rather than removes the recursive stale
state. Its immutable implementation ledger now says the "second documentation-only closure"
is "pending its own local commit" and the status says that second closure is pending. The
second closure is already committed as `ea3fd53`. The next docs-only correction must use a
non-recursive current-state statement: the latest docs-only ledger closure is committed
locally, production is unchanged, exact docs SHA is external in workbench/reviewer, and only
independent re-audit is pending. It must not introduce another pending-commit layer.

### Final closure re-review of `6b8ab475`

The non-recursive final closure closes Medium 1:

- `ea3fd53..6b8ab475` changes only the R0 implementation ledger;
- `git diff --check 7ee97471..6b8ab475` passes;
- all forbidden current-state patterns for uncommitted/pending docs commits or closures are
  absent;
- the ledger states that the latest docs-only closure is committed locally atop `9500bd4`,
  production `39766c3` is unchanged, exact docs SHA is maintained externally, and only
  independent re-audit is pending;
- branch and workbench bind exact docs `6b8ab475`, production `39766c3`, source/start
  `7ee97471`, no upstream, absent remote branch, no push, and unchanged downstream state;
- focused tests pass `8 passed, 1 warning`, production diff is empty, and all six production
  hashes still match PostgreSQL report `95f2608e`.

Current findings: **none (High=0, Medium=0, Low=0)**.

## Critical Semantic Oracle

The candidate is acceptable only if every statement below is independently verifiable:

1. Every multi-row Research mutation acquires locks in the partial order
   `Run -> Step(s) -> Attempt -> Call(s) -> Ledger(s)`. Multiple Steps, Calls, and Ledgers
   use stable ordering. No production path locks a Step and then waits for its Run.
2. Attempt- and Call-ID paths read locators without locks and with autoflush suppressed,
   then lock and refresh the complete aggregate and reject locator, scope, status, token,
   or expiry drift before mutation.
3. `claim_next_research_step` locks a Run first. Candidate Runs are ordered by their minimum
   eligible `(queued_at, created_at, step_id)` tuple and Run ID; the selected Step uses the
   same Step tuple. A locked Run is skipped without head-blocking another eligible Run.
4. Cancellation locks Run first and affected Steps/Decisions in stable ID order. Completion
   prelocks direct dependents before the Attempt, revalidates the dependency set, and queues
   only committed-ready dependents. Join and conflict paths retain their existing meaning.
5. Claim creates a new Attempt; heartbeat extends only the same live Attempt; fail, complete,
   retry, reclaim, and late-result fencing retain their previous transitions. Reclaim never
   revives an expired Attempt and applies every Call/Ledger terminal fact once.
6. Provider reserve/send/reconcile/cancel, tool begin/complete, publication compensation and
   commit-unknown handling, permission gates, Event rows/payloads/order, state versions, and
   budget accounting remain semantically equal to `d1b5945`.
7. Schema, Alembic, public API, save/replay payloads, dependencies, frozen lockfiles, and the
   fixed multi-step `process_one` runtime do not change.
8. R0 does not contain R1 dispatcher work, per-Run admission, deadlock retry, W1, or R2
   expansion.
9. Real PostgreSQL evidence must exercise production commands, show actual `pg_locks` and
   `pg_blocking_pids`, run all seven R0 scenarios, report no `40P01`/`55P03`, preserve the
   database deadlock counter, bind evidence to production source hashes, clean up, and avoid
   secrets. Harness-only synchronization must not substitute for a production wait edge.

## Lock-Path Review

| Path | Result | Independent judgment |
| --- | --- | --- |
| Claim-next Run ordering | pass | `lease.py` selects and locks `ResearchRun` with `SKIP LOCKED`, ordered by three correlated minimum-Step scalar subqueries plus Run ID. |
| Claim-next Step ordering | pass | After Run ownership, it locks one queued Step by `(queued_at, created_at, id)` and only then inserts the Attempt. Existing oldest-Step assertion remains in `test_research_worker_lease_plan.py`. |
| Claim-specific | pass | Step ID is a no-lock hint; production then locks Run and refreshes/revalidates Step before leasing. |
| Attempt locator | pass | `locate_attempt` uses `no_autoflush`; `lock_attempt_chain` performs Run, Step, Attempt locks with `populate_existing` and fails closed on parent/scope drift. |
| Heartbeat | pass | Reuses the ordered Attempt chain and validates live status, token, and expiry before extending the same lease. Real reparent contention preserves the old expiry and source Step. |
| Failure | pass | `failure.py` delegates to `_locked_attempt`, so fail transitions run only after the ordered, refreshed, fenced chain. |
| Completion | pass | Direct dependent IDs are located first, all known Steps are locked in sorted ID order before Attempt, and the dependency set is reread and compared before callbacks/mutation. |
| Join/dependents | pass | `_queue_ready_dependents` mutates only the prelocked dependent set and requires all dependencies succeeded in the same Run/workspace. |
| Cancellation | pass | API cancellation locks Run, then all Run Steps by ID and pending Decisions by ID; no Attempt lock is required because cancellation does not mutate active Attempts. |
| Creator-membership cancellation | pass | Run is already the aggregate root; idle finalization locks Steps then Decisions, while an active Attempt causes the idle check to return without acquiring later Step locks. Existing permission and cancellation transitions remain equal. |
| Retry | pass | Locks Run, Step, named failed Attempt, then execution Ledger; state-version, retryability, and budget checks remain before mutation. |
| Reclaim candidate order | pass | Keyset scan preserves `(lease_expires_at, attempt_id)` globally, skips locked Runs, refreshes Run/Step/Attempt, and continues until the requested limit. |
| Reclaim Calls/Ledgers | pass | Provider Calls are locked by ID, then Tool Calls by ID, then all unique Ledgers by ID. Locator counts and Call/Ledger relationships are revalidated before accounting. |
| Provider | pass | Existing Call paths locate all parent/ledger IDs without locks, acquire Run/Step/Attempt/Call/Ledger, refresh each mutable row, and reject drift. Sent-after-cancel reconciliation and reserved-send rejection tests remain green. |
| Tool | pass | Existing Call paths use the same locator and Run/Step/Attempt/Call/Ledger order; terminal Call/Ledger/Attempt accounting remains atomic. |
| Publication | pass | Final publication begins through `_locked_attempt`; claim selection refresh was added without changing object write, compensation, commit verification, Event, or terminal semantics. |
| Plan/conflict decision | pass | Decision paths locate gate/dependent Step IDs, lock Run and sorted Steps, then Decision and mutable Claims, and revalidate the gate/dependent set. |
| Stable cancellation/decision rows | pass | Steps, pending Decisions, and conflict Claims have explicit stable ordering where locked as sets. |
| Step-to-Run acquisition | pass | Repository-wide `with_for_update` scan found no remaining Research mutation that locks a Step and subsequently waits for Run. |

## Contract And Scope Review

| Area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | pass | Candidate diff is R0 lock normalization, tests, PostgreSQL harness, and its implementation ledger only. |
| Architecture boundaries | pass | Lock primitives remain in `citeframe_research_persistence`; API composition only delegates Run locking and composes decision-specific Step sets. |
| Schema/Alembic | pass | No model or migration path changed from `7ee97471`. |
| Public API/save/replay | pass | No schema/router/public DTO path changed; A2a differential is exact equal. |
| Permission | pass | Creator/owner/membership behavior is included in the differential and affected API tests. |
| Transitions/Event/state_version | pass | Differential compares exact Event bytes, normalized DB rows, retry/cancel/reclaim/recovery, lease fencing, and payload bytes. |
| Provider/tool accounting | pass | Differential is equal; focused accounting/recovery tests and real reclaim races pass. |
| Fixed `process_one` | pass | Worker runtime processor bytes equal `7ee97471`; differential includes fixed multi-step `processOne`. |
| Dependency/lockfiles | pass | No manifest or lockfile changed in R0; both API and Worker `uv lock --check` pass. |
| Python identifiers/imports | pass | `compileall` passed and 12 changed production modules imported from the frozen API environment. No unresolved runtime identifier/import was found. |
| R1 dispatcher | not applicable | No Worker runtime source changed from the R0 start. |
| Per-Run admission | not applicable | No cap/admission implementation was added; `max_parallel_researchers` appears only in the harness fixture. |
| Deadlock retry | not applicable | No retry for `40P01`, lock timeout, or transaction deadlock was added. |
| W1/SSE | not applicable | No SSE code changed. |
| R2 multi-Worker expansion | not applicable | Outside R0; remains governed by its named downstream gate. |
| Delivery ledger | pass | Final docs closure `6b8ab475` is non-recursive, committed locally, externally SHA-bound, and preserves historical hygiene truth. |

## Query-Order Test Audit

The query-order tests are not source-shape theater. `_executed_lock_entities` registers a
SQLAlchemy `do_orm_execute` listener on the real test Session, observes statements passed to
ORM execution, and invokes each statement through `execute_state.invoke_statement()`. The
provider/tool regression additionally wraps both `Session.scalar` and `Session.execute`, so
the unlocked locator query and locked refresh query are both observed.

The assertions cover executed lock entity order for claim, heartbeat, completion with direct
dependent Steps, cancellation, retry, reclaim with both Call types, provider, and tool. SQLite
does not prove PostgreSQL locking behavior, so these tests were treated only as query-order
evidence and were paired with the independent PostgreSQL run below. Existing scheduler tests
also assert that the oldest queued Step, not merely some Step, wins.

Result: **pass**. Residual limitation: entity-name traces do not identify individual row IDs,
so stable row-set order is also verified from explicit `order_by(id)` production queries and
the PostgreSQL contention evidence, not from the trace alone.

## A2a Differential

Independent command:

```bash
uv run --project apps/api --frozen python infra/scripts/run-a2a-differential.py \
  --root /home/cc/code/citeframe \
  --baseline-ref d1b5945e977445e4db6bf56ef54cf61607ead2e2 \
  --output /tmp/citeframe-r0-review-a2a-39766c3-1787553088.json
```

Result: **pass**, `equal=true`, coverage `7/7`, candidate head exactly `39766c3`, clean
semantic worktree, candidate composition `candidate-neutral-research-uow`, and
`uowEnterCount=38`. The seven compared areas are exact Event bytes, exact payload bytes,
fixed multi-step `processOne`, lease fencing, normalized DB rows, permission, and
retry/cancel/reclaim/recovery. Report SHA-256:
`65e745bbaa3deb626a7f8705a75e61a774999655546d2d1fe4dd224cfc96d91e`.

The reported `e3b0c442...` semantic worktree fingerprint means the candidate has no semantic
diff relative to its own HEAD; it is not used as the production source identity. Candidate
identity is the exact Git SHA plus PostgreSQL report module hashes.

## Real PostgreSQL Review

Independent command used the same immutable image digest through the configured mirror:

```bash
R0_POSTGRES_IMAGE='docker.m.daocloud.io/pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0' \
R0_OUTPUT_PATH=/tmp/citeframe-r0-critical-review-39766c3-1787553119.json \
infra/scripts/run-r0-postgres-contention.sh
```

Result: **pass**.

- PostgreSQL `17.10`; pgvector `0.8.4`.
- Seven of seven scenarios passed: claim/cancel, claim/complete, same-Run claims,
  different-Run claims, changed locator, reclaim/provider, and reclaim/tool.
- Every required contention wait was verified through `wait_event_type='Lock'` plus the
  expected PID in `pg_blocking_pids`, not by sleep/timing alone.
- Captured samples contain 46, 58, 37, 37, 27, 68, and 74 `pg_locks`/activity rows.
- All tasks completed within bounds. No task returned `40P01` or `55P03`.
- PostgreSQL database deadlock counter remained `0 -> 0`.
- Claim/cancel failed stale-version closed after claim ownership; claim/complete emitted one
  terminal Event; same-Run claim created one Attempt; different-Run claim was not head
  blocked; locator drift preserved expiry/source Step; both reclaim races applied one
  terminal Call/Ledger fact and rejected the late competitor.
- Report production hashes exactly match current `cancellation.py`, `lease.py`, `locks.py`,
  `provider.py`, `state.py`, and `tools.py` bytes.
- Report secret scan found no database URL, password assignment, AWS key, or private key;
  five lease tokens are redacted.
- Isolated schema cleanup reports pass and no `citeframe-r0-postgres-*` container remains.
- Independent report SHA-256:
  `127271dc7621d9cfc5fa3dcaf92055d406f18feaf09c6e3ca158cc80ae3e7a2d`.

The implementer report at `/tmp/citeframe-r0-final-run-4.json` was also independently read:
its SHA-256 is the recorded `95f2608e3455a7c0a1272fddc727c0339cdc65d28384c13d6d29318d5dbdf91d`,
it has `status=pass`, `cleanup=pass`, seven scenarios, no database URL, and source hashes that
still match candidate bytes.

## Harness Independence And Source Shape

The 1,007-line harness imports production commands from
`citeframe_research_persistence.commands`; it does not reproduce the lock algorithm. Its
advisory trigger pauses a real production claim only at Attempt insertion. The observed
cancel/complete wait on that claimant's Run proves the production claim already owns Run;
the trigger does not manufacture that row-lock edge. Reclaim races similarly gate the real
Call row and prove the competing production Call command waits behind reclaim's Run-rooted
transaction. Actual blocking PID checks, terminal-fact assertions, SQLSTATE checks, deadlock
counters, and production hashes prevent the harness from passing on its own assertions alone.

Current R0 result: **pass**. Future R2 expansion risk: the file already combines schema
provisioning, fixtures, thread/task control, lock observation, seven scenarios, cleanup, and
reporting. It is cohesive enough to preserve as immutable R0 evidence, but materially adding
R2 Worker/cap/fairness/recovery matrices in this file would create a blob and make source-hash
and cleanup review harder. Before R2 expansion, split infrastructure/observation/reporting
from scenario modules while keeping one thin runner and immutable R0 scenario behavior.

## Verification Commands

| Verification | Result |
| --- | --- |
| Focused R0 + A2a pytest | `8 passed, 1 warning` |
| Affected Research/API pytest set | `90 passed, 1 warning` |
| Supplementary deploy/migration/V5-C/R100 API set | `49 passed, 1 warning` |
| Worker contracts/executor/runtime/integration | `43 passed` |
| A2a executable differential | `equal=true`, coverage `7/7` |
| Real PostgreSQL harness | `7/7`, deadlocks `0 -> 0`, no `40P01`/`55P03` |
| API and Worker `uv lock --check` | pass |
| Production/harness `compileall` | pass |
| Changed production import smoke | 12 modules pass |
| Harness `bash -n` | pass |
| `git diff --check 7ee97471..39766c3` | **fail: implementation record line 3 trailing whitespace** |
| `git diff --check 7ee97471..6b8ab475` | pass; historical production whitespace is repaired and documented |
| Final docs closure scope | `ea3fd53..6b8ab475` changes one implementation-ledger file only |
| Branch/remote state | head `6b8ab475`, production `39766c3`, upstream none, remote branch absent, `origin/main=9f40241`, not pushed |

The only warning in API pytest is the pre-existing Starlette `httpx` deprecation warning.

## Reverse Review

Assuming an R0 regression occurred:

- A Step-before-Run regression should be caught by the executed ORM lock trace and by
  claim/cancel or claim/complete blocking direction.
- A changed locator accepted after waiting should be caught by the concurrent reparent
  scenario and unchanged expiry/source-Step assertions.
- A duplicate claim/completion/reclaim should be caught by Attempt/Event counts and exact
  Call/Ledger terminal accounting.
- A semantic transition, permission, payload, Event, or `process_one` regression should be
  caught by the exact A2a differential and affected API/Worker tests.
- A harness/source mismatch should be caught by report module hashes compared to candidate
  bytes.
- A hidden deadlock retry should be caught by the source scan and unchanged task SQLSTATE
  handling.

Those oracles are strong enough for production `39766c3`. Documentation history
`9500bd4 -> ea3fd53 -> 6b8ab475` preserves those results, repairs hygiene, and ends in a
non-recursive committed-state ledger. The final docs SHA is bound externally without a
self-referential claim. No finding remains.

## Final Decision

**ACCEPT (High=0, Medium=0, Low=0).** Production `39766c3` satisfies the complete R0 lock,
contract, transition, differential, and real-PostgreSQL oracles. Final documentation closure
`6b8ab475` closes the only historical ledger/hygiene Medium without changing production,
truthfully records the local/no-upstream/no-remote/no-push state, and passes full
start-to-documentation hygiene. R1, R2, W1, per-Run admission, deadlock retry, and downstream
integration were not included in R0 and remain governed by their named gates.
