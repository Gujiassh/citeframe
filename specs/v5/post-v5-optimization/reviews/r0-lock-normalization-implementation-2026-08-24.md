# R0 Research Lock Normalization Implementation

Date: 2026-08-24
Status: **IMPLEMENTATION AND LEDGER CLOSURE COMMITTED LOCALLY; independent Critical re-audit pending**

This record does not claim `ACCEPT`. The independent Critical review is
[`REWORK (High=0, Medium=1, Low=0)`](r0-lock-normalization-critical-review-2026-08-24.md)
with no production finding and one durable-ledger/hygiene finding. The latest docs-only
ledger closure is committed locally atop `9500bd4`; production `39766c3` is unchanged. The
exact latest documentation SHA is maintained externally by the reviewer and dev-workbench.
Independent Critical re-audit is pending. R1, R2, W1, per-Run admission, and downstream
work remain blocked.

## Delivery Ledger

- Repository: `https://github.com/Gujiassh/citeframe.git`
- Source branch/ref: `work/research-boundary-runtime-20260824`
- Starting SHA: `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`
- Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
- Repair branch: `work/research-boundary-runtime-20260824`
- Production parent/start SHA: `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`
- Production commit: `39766c374bd584b0cb834ef103de025d233c87c1`
- Production commit state: local commit on `work/research-boundary-runtime-20260824`; the
  branch has no upstream, `origin` has no branch with this name, and the commit is not pushed
- Latest docs-only ledger closure: committed locally atop `9500bd4`; it is not pushed,
  production `39766c3` remains unchanged, and the exact latest documentation SHA is
  maintained externally by the independent reviewer and dev-workbench
- Integration state: no merge, cherry-pick, or downstream branch update performed
- Downstream targets: R1, R2, W1, and per-Run admission remain blocked behind the R0
  Critical gate; no downstream sync is authorized from this production candidate

## Symptom And Root Cause

The accepted A2a snapshot intentionally retained conflicting row-lock acquisition. Worker
Attempt paths acquired `Attempt -> Step -> Run`, claim acquired `Step -> Run`, while API
cancel, retry, and decision paths acquired `Run -> Step`. Claim-versus-cancel could form a
reverse-order deadlock ring. Provider/tool and reclaim paths also alternated Call and Ledger
locks after the reversed Attempt chain.

R0 removes that ring by making `ResearchRun` the aggregate lock root for every multi-row
Research mutation. Attempt and Call identifiers are first read without locks as location
hints. Mutable rows are then locked with `populate_existing` in this order:

```text
ResearchRun -> ResearchStep(s) -> ResearchStepAttempt -> provider/tool Call(s) -> ResearchBudgetLedger(s)
```

Changed locators, scope, status, lease token, or lease expiry fail closed after the ordered
refresh. Locator reads and core lock helpers suppress autoflush so pending mutations cannot
acquire a lower-level row before the Run lock.

## Implemented Scope

- Claim-next locks a candidate Run first. Candidate Runs are ordered by the minimum eligible
  Step tuple `(queued_at, created_at, step_id)`, then Run ID. The selected Run is refreshed,
  then its winning queued Step is locked using the same Step tuple.
- Claim-specific locates the Step without a lock, then locks and revalidates Run and Step.
- Heartbeat, completion, failure, plan/publication, provider reserve, and tool begin use the
  shared Run-first Attempt chain.
- Completion pre-locates and locks the owning Step plus direct dependents in stable Step-ID
  order before the Attempt; join readiness mutates only those prelocked Steps.
- Provider/tool existing-call paths use unlocked parent hints, constrain the refreshed Call
  to those hints, then lock its Ledger. Sent provider calls retain post-cancellation billable
  reconciliation; reserved unsent calls still cannot be sent after cancellation.
- Reclaim scans expired candidates in the existing global `(lease_expires_at, attempt_id)`
  order, skips locked Runs, and continues until the requested limit. It locks all provider
  and tool Calls before all unique Ledgers, then preserves existing abandon, retry,
  cancellation, outcome-unknown, Event, and accounting transitions.
- Retry now locks Run, Step, failed Attempt, and Ledger before mutation.
- Cancellation locks Run first, then all affected Steps and pending Decisions in stable ID
  order.
- API plan/conflict decision composition locates the gate/dependent Step set, then locks Run,
  affected Steps, Decision, and mutable Claims before applying the unchanged decision flow.
- Legacy `citeframe_research_persistence.locks` exports remain identity-compatible through
  lazy re-exports.

No schema, Alembic revision, public HTTP/API shape, save payload, replay, permission,
transition, Event payload, state-version meaning, provider/tool accounting meaning, or
fixed multi-step `process_one` behavior changed. No deadlock retry, R1 dispatcher, admission
cap, compatibility fallback, or alternate lock order was added.

## Executable Unit Evidence

The R0 tests use SQLAlchemy `do_orm_execute` and inspect actual executed ORM lock statements;
they do not parse source text or SQL with regular expressions. They cover:

- claim `Run -> Step`;
- heartbeat `Run -> Step -> Attempt`;
- completion/join `Run -> all affected Steps -> Attempt`;
- cancellation `Run -> stable Steps -> Decisions`;
- retry `Run -> Step -> Attempt -> Ledger`;
- reclaim `Run -> Step -> Attempt -> all Calls -> Ledger`;
- provider/tool Call paths `Run -> Step -> Attempt -> Call -> Ledger`.

Exact production-candidate results:

```text
uv run --project apps/api pytest -q <R0 + A2a focused files>
8 passed, 1 warning

uv run --project apps/api pytest -q <10 affected Research/API files>
112 passed, 1 warning

uv run --project apps/worker pytest -q \
  apps/worker/tests/test_research_contracts_package.py \
  apps/worker/tests/test_research_executor.py \
  apps/worker/tests/test_research_runtime.py \
  apps/worker/tests/test_research_runtime_integration.py
43 passed
```

## A2a Differential Oracle

The executable old/new differential against `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
remains equal. The candidate production composition remains
`citeframe_research_persistence.lease` with `38` real Research UoW entries; the baseline
remains the original API facade with `0` UoW entries. The fixed multi-step process-one flow,
29 transition/process tables, exact Event rows, payloads, retry/cancel/reclaim/recovery,
permissions, publication, and terminal outcomes remain byte/row equal. Only lock acquisition
evidence differs. Production-candidate semantic fingerprint:

- semantic SHA-256 `f5057a39be0b2b4c823e31e2022358702df21273433198391bd572cdc6fd8d69`

The dirty repair snapshot fingerprint recorded before the production commit is not the
immutable commit identity. The canonical production identity is `39766c3`; the latest
docs-only ledger closure is committed locally atop `9500bd4`, with its exact SHA maintained
externally by the reviewer and dev-workbench.

## Real PostgreSQL Critical Evidence

Exact command:

```bash
R0_POSTGRES_IMAGE='docker.m.daocloud.io/pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0' \
R0_OUTPUT_PATH=/tmp/citeframe-r0-final-run-4.json \
infra/scripts/run-r0-postgres-contention.sh
```

Environment and report:

- PostgreSQL `17.10`; pgvector `0.8.4`
- pinned image digest `sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0`
- report SHA-256 `95f2608e3455a7c0a1272fddc727c0339cdc65d28384c13d6d29318d5dbdf91d`
- session `lock_timeout=8000ms` and bounded statement/task timeouts
- PostgreSQL deadlock counter `0 -> 0`
- no task returned SQLSTATE `40P01` or `55P03`
- isolated schema, extensions created only when absent, and container were cleaned up
- report lease tokens are redacted and the report contains no database URL/password

| Scenario | `pg_locks` / activity rows | Result |
| --- | ---: | --- |
| claim vs cancel | 46 | claim unique; cancel waits on Run then fails stale-version closed; no deadlock |
| claim vs complete | 58 | completion waits on Run; exactly one completion Event; no deadlock |
| two claims on same Run | 37 | second claimant skips the locked Run; exactly one Attempt |
| claims on different Runs | 37 | second Run remains claimable without head blocking |
| changed Attempt locator | 27 | heartbeat rejects the changed parent chain; expiry and source Step remain unchanged |
| reclaim vs provider | 68 | one abandon; reservation/ledger applied once; late cancel rejects |
| reclaim vs tool | 74 | one abandon; tool/ledger applied once; late completion rejects |

The report embeds SHA-256 values for the exact production modules exercised. They match
production commit `39766c3` for cancellation, lease, locks, provider, state, and tools.
Official `registry-1.docker.io` access remained blocked by a header timeout; the mirror ran
the exact same immutable digest.

## Verification Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | pass | R0 lock order only; no R1/admission work |
| Save/API/data contracts | pass | executable A2a differential equal |
| Fixed multi-step runtime | pass | process-one differential remains equal |
| Query-order unit oracle | pass | real executed ORM lock query tracing |
| PostgreSQL contention | pass | seven scenarios, `pg_locks`, blocking PIDs, no deadlock/timeout |
| Duplicate terminal facts | pass | unique Attempt/completion/abandon/ledger assertions |
| Locator refresh/fail-closed | pass | real concurrent Attempt reparent race |
| Schema/dependencies | pass | no model/migration/lockfile/dependency change; API/Worker `uv lock --check` pass |
| Production commit/push | pass | local production `39766c3`; no upstream; no remote branch; not pushed |
| Latest docs-only ledger closure | pass | committed locally atop `9500bd4`; exact SHA recorded by reviewer/workbench; not pushed |
| Independent Critical review | blocked | `REWORK (High=0, Medium=1, Low=0)`; no production finding; no `ACCEPT` claimed |

## Residual Risks And Next Gate

- Official Docker Hub transport was unavailable; exact-digest mirror PostgreSQL evidence is
  complete, but it is not proof of official-registry availability.
- The real PostgreSQL harness covers the required contention matrix. Unit/differential tests
  cover retry, join, conflict, publication, provider/tool, payload, Event, and permission
  semantics; the independent reviewer found no production issue in `39766c3`.
- `run-r0-postgres-contention.py` is a cohesive but 1,007-line Critical evidence harness.
  Keep it stable for R0 review and split scenario fixtures, observation, and reporting before
  materially expanding it for R2 rather than growing the file further.
- Production commit `39766c3` historically contains the trailing whitespace that caused
  `git diff --check 7ee97471..39766c3` to fail. The committed docs-only ledger closure
  removes it and the start-to-documentation range passes hygiene. Do not describe the
  original immutable production range as having passed hygiene.
- R1, R2, W1, per-Run admission, deadlock retry, schema/API changes, and downstream
  integration remain blocked. The next action is independent Critical re-audit; this
  implementer record must not be treated as an acceptance verdict.
