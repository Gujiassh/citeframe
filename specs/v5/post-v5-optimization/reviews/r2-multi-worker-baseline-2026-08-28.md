# R2 Real PostgreSQL Multi-Worker Baseline And WIP Handoff - 2026-08-28

## Current Stop Snapshot

**WIP ONLY. R2 is not accepted or closed.** The owner authorized the existing-design per-Run admission slice after the 9 PASS / 3 FAIL negative baseline. Admission code, focused tests, a split multi-worker harness, and an unfinished production dispatcher-overlap proof are present in the worktree. Work stopped on owner request for a computer migration.

The exact WIP commit and push state are maintained in the external dev-workbench and remote branch rather than self-referenced here. Do not merge this branch or claim R2 acceptance without completing the remaining evidence and one module-level review.

## Historical Baseline Verdict

**PARTIAL NEGATIVE BASELINE. This is not R2 `ACCEPT` and not module closure.**

The immutable production snapshot passes the focused multi-process claim, lease recovery,
join, provider/tool, conflict resume, publication success, Step tie-order, and R0 lock
non-regression probes. It deterministically fails all three admission-dependent probes.
Production admission is both absent and explicitly unauthorized by the canonical design,
so no production repair was attempted.

## Delivery Ledger

- Source branch: `work/research-r2-multi-worker-20260828`
- Immutable source/start SHA: `a616eea1350b095c6f229890d2c47e5010902330`
- Source of start: merged `main` after PR #22
- Commit state: no commit created
- Push state: not pushed
- Production/API/schema/contract/lock/manifest changes: none
- Added scope:
  - `infra/scripts/run-r2-multi-worker.sh`
  - `infra/scripts/run-r2-multi-worker.py`
  - `specs/v5/post-v5-optimization/reviews/r2-multi-worker-baseline-2026-08-28.md`
- External report: `/tmp/citeframe-r2-baseline-2026-08-28.json`
- External report SHA-256: `70e65afba02ddee2bfb5b7db5a4809ddbbf61da3b5f3502a7e619e31232b6b82`
- Harness SHA-256:
  - Python: `832a5fc194d17c2e7572690e58e82dac95ee848f4d2d23114df0b50235fe5cd4`
  - Shell: `d4673d0d47bd7fdfa8b0e8e1c570d12f9b6696fc6e462abb26605dae20938acd`

## Environment

- PostgreSQL: `17.10`
- pgvector: `0.8.4`
- Required digest: `sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0`
- Official Docker Hub result: registry header timeout before the container started
- Same-digest mirror used:
  `docker.m.daocloud.io/pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0`
- Docker image id: `sha256:83d2fe2f7efc2a3b52bc1edeaf845eefc8044be447564c062b12b8a55aceb9fc`
- Database isolation: generated schema inside an ephemeral tmpfs-backed container
- Cleanup: passed; schema and container removed
- Deadlocks: `0 -> 0`; no accepted `40P01` or `55P03`
- Secret scan: passed; database credentials and lease tokens are absent from the report

The harness compares 25 production/runtime/persistence/model/API/R0 source files against
the Git objects at the immutable SHA. Every OS worker repeats the comparison and must
match the controller result. Dirty tracked production source therefore fails closed even
when the checked-out HEAD string is unchanged.

## Baseline Matrix

| Scenario | Result | Evidence |
| --- | --- | --- |
| Two OS Workers on one Run | PASS | Distinct PIDs `2858919`/`2858920`, PostgreSQL PIDs `85`/`86`, distinct Worker IDs, unique Step/Attempt claims, handler-shaped interval overlap, wall time `2.089s` |
| Lease expiry, late completion, reclaim, retry recovery | PASS | Attempt 1 abandoned exactly once, late completion fenced with `research_state_conflict`, Attempt 2 succeeded |
| Join dependency readiness | PASS | Parent terminal Event precedes dependent `step_queued`; dependent then claimed and completed |
| Cancel/provider outcome-unknown exactly once | PASS | Concurrent OS commands end with one outcome-unknown provider fact and one ledger charge; duplicate reconcile fails closed |
| Tool reclaim exactly once | PASS | Real PostgreSQL R0 lock race abandons one Tool Call and applies the ledger once |
| Conflict wait/resume | PASS | Worker persists wait/decision facts; API decision resumes Run and resolves Claim as unresolved |
| Final publication success | PASS | One final Artifact; Step/Attempt succeed; `run_completed` is unique and last |
| `cap=1` | **FAIL** | Two effective unexpired researcher Attempts are admitted (`2 > 1`) |
| `cap=N` with `N=2` | **FAIL** | Three effective unexpired researcher Attempts are admitted (`3 > 2`) |
| `cap=1` expired slot/reclaim | PASS | Expired Attempt is abandoned and one replacement is active; no revived Attempt |
| Cap-full Run plus eligible Run, repeated claims | **FAIL** | Cap-full Run gains an illegal Step/Attempt/Event mutation before the eligible Run is selected |
| Equal queued/created time Step-ID parity | PASS | Production claim selects the lexicographically first Step ID |

For Event-bearing PASS scenarios, the report proves per-Run `seq` starts at 1 and is
contiguous/unique, dedupe keys are unique, initial `step_queued` precedes `step_started`,
terminal Events follow starts, every Attempt starts once and has at most one terminal
fact, payload keys match the immutable contract, dependencies precede readiness, and a
Run terminal Event is unique and last when present.

## Root Cause And Authorization Blocker

`claim_next_research_step()` does not read
`ResearchExecutionSnapshot.max_parallel_researchers`, does not count effective unexpired
researcher Attempts using database time, and has no `excluded_run_ids` loop that rolls
back a cap-full candidate before scanning another Run. Consequently:

- `cap=1` admits 2 effective Attempts;
- `cap=2` admits 3 effective Attempts;
- a cap-full Run is mutated instead of producing zero Step/Attempt/Event mutation;
- the eligible Run is only reached after the earlier cap-full Run's queued work was
  illegally claimed.

The canonical design simultaneously states that per-Run admission is unimplemented and
unauthorized:

- `research-boundary-runtime-design.md`, section 4.2: per-Run admission remains
  unauthorized;
- section 6: no slot table, schema change, or per-Run admission implementation is
  authorized; admission requires its own later gate.

**Decision required:** explicitly authorize the already-designed per-Run admission slice,
or narrow R2 so admission-dependent scenarios are not acceptance requirements. Until that
decision, R2 cannot close and no production change is permitted.

## Known Evidence Gaps

The current PASS evidence is deliberately described as focused baseline evidence, not a
complete Critical gate:

- Multi-process claim and persistence-handler overlap is proven, but concurrent execution
  inside `SingleAttemptStepDispatcher` with a real production provider/tool handler is not.
- Final publication success is proven; commit-outcome-unknown compensation/reconciliation
  is not.
- Provider outcome-unknown exactly-once is proven; budget exhaustion/reconcile is not.
- Current cap failures are conclusive because admission is absent. The cap probes are not
  yet sufficient to validate a future admission implementation under simultaneous
  contention.
- The Tool reclaim lock race reuses the accepted real-PostgreSQL R0 threaded fixture; the
  R2 OS-process requirement is proven in the Worker/provider scenarios, not this Tool
  sub-scenario.

## Verification

Primary command (expected exit `1` because the report contains truthful scenario FAILs):

```bash
R2_POSTGRES_IMAGE='docker.m.daocloud.io/pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0' \
  infra/scripts/run-r2-multi-worker.sh \
  --output /tmp/citeframe-r2-baseline-2026-08-28.json
```

Result: `9 PASS / 3 FAIL`, aggregate `FAIL`, cleanup PASS, secret scan PASS,
admission decision required. `--report-only` is available for evidence collection while
preserving the same truthful JSON status.

Non-regression and hygiene:

- R0 real PostgreSQL contention: `7/7 PASS`, deadlocks `0 -> 0`, report
  `/tmp/citeframe-r2-r0-nonregression.json`, SHA-256
  `d58dcc8a94b38ed4c51cb7f8c961f5c1cce32e698ed67100c1c6207c901d6531`.
- R1 Worker focused tests: `64 passed`.
- R1 API/A2a/R0/lease focused tests: `40 passed`, one existing Starlette deprecation
  warning.
- `uv lock --project apps/api --check`: passed.
- `uv lock --project apps/worker --check`: passed.
- Python compile: passed.
- Bash syntax: passed.
- `git diff --check`: passed.
- `shellcheck`: unavailable in the environment.

The aggregate R1 shell gate was initially bounded by `timeout 300`; its Worker portion
completed `64 passed` before the outer timeout. The exact remaining API command was then
run separately to completion with `40 passed`. No release qualification or R2 `ACCEPT`
claim is made.

## Independent Harness Review

The first independent review judged report
`b0d552eed973c872916bbe78c8932c7054671b42078ded93b30e5cbd5762ac4c`
credible only as a partial negative baseline. It found two High evidence weaknesses:
immutable-source verification used only the HEAD string, and the Event oracle could pass
illegal histories. Both were repaired before the final report by Git-object hash
comparison in controller and child processes, explicit initial queued Events, stronger
Attempt/Step/Run/payload oracles, fail-closed child cleanup, aggregate-state corrections,
and removal of the database URL from the process argument list.

The residual coverage gaps above remain open and are why this ledger does not claim R2
acceptance.


## WIP Stop Handoff - 2026-08-28

### Implemented After The Negative Baseline

The owner explicitly authorized per-Run admission on 2026-08-28. The stopped worktree adds:

- neutral `admission.py` using the accepted Run-first lock root, PostgreSQL database time,
  existing `ResearchStepAttempt` rows, and the frozen execution-snapshot
  `max_parallel_researchers` value;
- `claim_next_research_step` cap-full rollback/exclusion scanning and
  `claim_specific_research_step` admission fencing without a schema or public API change;
- focused admission tests in `apps/api/tests/test_r2_research_admission.py`;
- a split harness under `infra/scripts/r2_multi_worker/` for admission, runtime,
  accounting, publication, and real OS-process actors;
- an R800-backed dispatcher-overlap proof under `infra/scripts/r2_dispatcher_overlap/`
  plus its shell/Compose entry points.

Reported evidence before the stop:

- admission affected suite: `55 passed`;
- quick controller handoff check: admission plus lease/plan `13 passed`;
- split real-PostgreSQL matrix after admission: `12 PASS / 0 FAIL`;
- expanded aggregate matrix before final interruption: `16 PASS / 0 FAIL`, report
  `/tmp/citeframe-r2-expanded-aggregate-2026-08-28.json`, SHA-256
  `f968da70cdb27449061468b405a1405571ea4eca06675493d6a664c77afe682c`;
- deadlocks remained `0 -> 0`; cleanup, secret scan, compile, Shell syntax, and diff hygiene
  passed in the completed lanes.

These results are intermediate evidence only. The final candidate tree changed while the
last dispatcher/publication lanes were still active, so none of the report hashes above is
a final immutable R2 qualification report.

### Interrupted Or Incomplete Work

- The R800-backed real `SingleAttemptStepDispatcher` two-process overlap lane was
  interrupted before its final Compose/runtime proof completed.
- The final-publication outcome lane was interrupted while extending committed, absent,
  unknown/committed, and unknown/absent evidence.
- The aggregate harness has not been rerun against the final stopped source tree.
- `scenarios_publication.py` and `r2_dispatcher_overlap/controller.py` exceed 600 lines;
  split their scenario/setup/reporting responsibilities before materially expanding them.
- Publication has no durable public unknown-outcome reconciliation command; the current
  harness can prove inline classification/manual later inspection only.
- Existing tool-completion-after-cancel semantics still need an explicit frozen oracle.
- Canonical SSoT/spec authorization and final R2 status were not synchronized.
- Full module tests, one independent module-level review, final immutable report, and direct
  delivery were not performed.

### Resume Checklist

1. Fetch and switch to `work/research-r2-multi-worker-20260828`; read this ledger and the
   latest dev-workbench checkpoint before editing.
2. Confirm `git status`, remote SHA parity, and that no R2 containers/processes remain.
3. Run focused admission tests and compile/Shell/diff gates.
4. Finish and validate dispatcher overlap plus publication outcomes; freeze the
   tool-after-cancel oracle.
5. Rerun the complete real-PostgreSQL matrix against one immutable candidate and require all
   canonical scenarios to pass.
6. Run relevant API/Worker module gates, perform one R2 module-level independent review,
   then synchronize SSoT/spec and deliver. Do not start W1 or downstream work first.
