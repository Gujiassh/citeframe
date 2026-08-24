# A2a Research Persistence Rework Implementation Evidence

Status: **implementer-complete; new independent Critical re-audit pending; not accepted**
Date: 2026-08-24

## Delivery Ledger

| Field | Value |
| --- | --- |
| Repository / merged prerequisite | `Gujiassh/citeframe`; PR #20 merged as `origin/main@9f40241edcd10f98ec3e97db880354bb177cc505` |
| Behavioral baseline | `d1b5945e977445e4db6bf56ef54cf61607ead2e2` |
| Initial A2a snapshot | `20d411ebf60b755c4ef3308e269591b19209e4eb` |
| Initial Critical review | [`a2a-persistence-critical-audit-2026-08-24.md`](a2a-persistence-critical-audit-2026-08-24.md), `REWORK (High=1, Medium=5, Low=1)` |
| Review record commit | `5a6ee389ded25052bf11314fd63856bb1b444b67` (local review commit; not pushed) |
| Repair branch | `work/research-boundary-runtime-20260824` |
| Current tracked branch head | `a494b8a098cb77cbc22792883d2f27881a650ffb`, merging the review lineage with `origin/main@9f40241` |
| Repair delivery state | Dirty worktree; implementation and docs are uncommitted and unpushed |
| Downstream gates | R0/R1/R2/W1 and downstream remain blocked until a new independent A2a Critical `ACCEPT` |

PR #20 merged the prerequisite branch into `main`; it did not accept this repair delta.
The initial review record and the dirty repair must not be described as an immutable accepted
snapshot.

## Symptom And Root Cause

The initial snapshot was rejected because four evidence and ownership failures combined:

1. `_locked_attempt` accidentally made `db` keyword-only. Real planner and publication
   callers still passed `db` positionally, so normal multi-step Research execution failed
   with `TypeError` before the intended lease/fencing mutation.
2. The neutral package owned only part of the approved Research transition boundary.
   Planning, completion, publication, retry/cancel, and state transitions remained split or
   duplicated in API modules; the introduced repository/UoW had no production consumer.
3. The golden oracle was a hand-authored static JSON/hash test. It did not execute the
   baseline and candidate or compare DB rows, payload/Event bytes, lease fencing,
   retry/cancel/reclaim/recovery, permission, or real `process_one` output.
4. Deployment enforcement was weak: comment-sensitive substring tests could pass with no
   effective Docker `COPY`, CI did not build final images, and non-frozen sync could repair
   a stale lock before verification. SSoT, test counts, branch/artifact state, and range
   hygiene then overstated the reviewed evidence.

## Changed Scope

The bounded repair changes only the already-approved A2a extraction and its supply-chain
proof:

- restores `_locked_attempt(db, *, ...)`, the missing legacy facade symbols, direct
  positional/keyword calls, and monkeypatch identity chains;
- moves DB-only planning, completion, publication, retry, cancellation, control/reclaim,
  provider, and tool transitions behind `citeframe_research_persistence` as the neutral
  owner, removes the duplicated API cancellation transition, and makes the Worker default
  composition use `ResearchUnitOfWork` / `ResearchRepository` through
  `research_persistence_service.py`;
- retains specialized idempotency, membership-removal, and final commit-outcome-unknown
  semantics; storage, provider clients, retrieval, observability, and agent registry remain
  composition adapters outside the neutral package;
- deletes the static A2a golden and adds an executable baseline/candidate differential
  runner plus API tests;
- adds a named executable deploy gate and strengthens CI with lock checks, frozen sync,
  canonical export/diff, effective Docker instruction validation, Docker target builds,
  and final-image path/non-root smoke commands;
- synchronizes specs and SSoT to the real branch, artifacts, evidence, and blocked state.

The repair does not authorize or intentionally change schema, public API, save/replay,
permission, Step/Attempt/Claim/Event meanings, fixed multi-step LangGraph execution, or the
known mixed lock order. It does not implement R0 or R1.

## Verification Evidence

Core implementer evidence:

```text
Initial-audit exact API matrix: 71 passed
Complete API Research suites: 122 passed, 1 warning
Complete Worker Research suites: 58 passed
Worker fixed graph/UoW matrix: 39 passed
Persistence boundary matrix: 12 passed
Cancel/retry router matrix: 23 passed
compileall and API/Worker import smoke: passed
```

Executable differential evidence:

```text
baseline=d1b5945e977445e4db6bf56ef54cf61607ead2e2
equal=true
candidateWorktreeSha256=1e3c23856db39281ab4d4ba913ff9d1f8f40ee494856edd2f9377560e2406287
dirty=true
coverage=7
focused pytest: 1 passed, 1 warning
```

The seven scenarios cover normalized Research table rows, exact Event/payload bytes, lease
fencing, auto/manual retry, cancel/reclaim/recovery, permission, conflict wait/resume, and
final publication through real multi-step `process_one`. The oracle uses SQLite and
controlled external adapters; real PostgreSQL lock contention remains R0/R2 scope and is
not inferred from this evidence.

Supply-chain implementer evidence:

```text
API deploy gate tests: 6 passed
Worker deploy gate tests: 2 passed
API and Worker uv lock --check: passed
Frozen sync, canonical export, and combined lock/export diff: passed
CI YAML structure, shell syntax, and commented-COPY mutation checks: passed
Dirty tracked git diff --check: passed
Untracked-file trailing-whitespace scan: passed
```

The initial committed range `d1b5945..20d411e` was not whitespace-clean. The current dirty
repair delta is clean under the checks above; this distinction replaces the initial report's
incorrect range claim.

## Blocked Evidence

Docker clean-image evidence is **blocked, not passed**. Docker Hub header requests timed out,
so neither final API nor Worker image has current build/runtime proof. The named CI deploy
gate contains both Docker target builds and final-image import/path/non-root smokes, but
those commands still require a successful network-backed run before acceptance.

## Independent Re-Audit And Integration Steps

1. Form one immutable repair snapshot after code, tests, CI, docs, and workbench evidence are
   reconciled; record its exact SHA and rerun the full Critical acceptance matrix.
2. Retry both Docker target builds and final-image smokes when Docker Hub is reachable. Do
   not substitute the textual/YAML checks for clean-image runtime evidence.
3. Run a new independent Critical re-audit against that exact snapshot. The initial audit,
   implementer tests, and differential subreview are evidence inputs, not A2a acceptance.
4. Only an independent `ACCEPT` may unblock a separate R0 branch. R1/R2 remain after R0;
   W1 stays an independent slice. None may be folded into this repair.
5. After controller acceptance, commit and push one coherent repair slice, update the final
   commit/push state and workbench delivery ledger, then integrate that accepted commit into
   `main` through the repository's review flow.

Current verdict remains **pending new independent Critical re-audit**. No A2a `ACCEPT` is
claimed.
