# A2a Research Persistence Rework Implementation Evidence

Status: **immutable local production candidate; final independent Critical re-audit pending documentation closure; not accepted**
Date: 2026-08-24

## Delivery Ledger

| Field | Value |
| --- | --- |
| Repository / merged prerequisite | `Gujiassh/citeframe`; PR #20 merged as `origin/main@9f40241edcd10f98ec3e97db880354bb177cc505` |
| Behavioral baseline | `d1b5945e977445e4db6bf56ef54cf61607ead2e2` |
| Initial A2a snapshot | `20d411ebf60b755c4ef3308e269591b19209e4eb` |
| Initial Critical review | [`a2a-persistence-critical-audit-2026-08-24.md`](a2a-persistence-critical-audit-2026-08-24.md), `REWORK (High=1, Medium=5, Low=1)` |
| Initial review record commit | `5a6ee389ded25052bf11314fd63856bb1b444b67` |
| Repair branch | `work/research-boundary-runtime-20260824` |
| Repair starting SHA | `a494b8a098cb77cbc22792883d2f27881a650ffb` (merge of review lineage with `origin/main@9f40241`) |
| Immutable production candidate | `215cd52565089138704c6b637350e18bc8705c8b` (`refactor(research): complete A2a persistence extraction`) |
| Push state | Local only; not pushed |
| Final reviewer artifact | [`a2a-persistence-critical-reaudit-2026-08-24.md`](a2a-persistence-critical-reaudit-2026-08-24.md); verdict pending documentation closure |
| Downstream gates | R0/R1/R2/W1 and downstream remain blocked until final independent A2a Critical `ACCEPT` |

PR #20 merged the prerequisite branch into `main`; it did not accept the A2a repair. The
production candidate is now immutable by commit SHA. Documentation closure must not rewrite
that production snapshot or turn passing implementation evidence into an acceptance claim.

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
- replaces the static A2a golden with an executable baseline/candidate differential that
  verifies baseline API-facade composition against candidate neutral production
  composition;
- adds a named executable deploy gate and strengthens CI with lock checks, frozen sync,
  canonical export/diff, effective Docker instruction validation, Docker target builds,
  and final-image path/non-root smoke commands;
- synchronizes specs and SSoT to the immutable candidate, evidence, and blocked state.

The repair does not authorize or intentionally change schema, public API, save/replay,
permission, Step/Attempt/Claim/Event meanings, fixed multi-step LangGraph execution, or the
known mixed lock order. It does not implement R0 or R1.

## Differential And Composition Evidence

```text
candidateCommit=215cd52565089138704c6b637350e18bc8705c8b
baseline=d1b5945e977445e4db6bf56ef54cf61607ead2e2
equal=true
semanticFingerprint=b155d2fa7783b70e57ed60015eecfd6dd2f2d28bfe9cd5ebea68166c9a33855a
candidateComposition=candidate-neutral-research-uow
uowEnterCount=38
focused differential=2 passed, 1 warning
```

Baseline `process_one` uses its original API facade composition. Candidate `process_one`
uses the production neutral command/UoW composition; an API-facade fallback mutation fails
closed. The comparison covers normalized Research rows, exact Event/payload bytes, lease
fencing, auto/manual retry, cancel/reclaim/recovery, permission, conflict wait/resume, and
final publication.

The pre-commit full-repair worktree fingerprint
`d185e78e75894be45c0fe625c51856b36531d74d496ea395adc51424b474f037`
is historical provenance only. The immutable production identity is commit
`215cd52565089138704c6b637350e18bc8705c8b`; the worktree fingerprint must not replace it.

The differential uses SQLite and controlled external adapters. Real PostgreSQL lock
contention remains R0/R2 scope and is not inferred from this evidence.

## Controller Full Verification

```text
API: 650 passed, 6 skipped, 1 warning
Worker fast: 174 passed, 153 deselected
Worker acceptance: 61 passed, 266 deselected
Worker evaluation: 92 passed, 235 deselected
API deploy gate: 6 passed
Worker deploy gate: 2 passed
API and Worker lock checks: passed
Frozen sync, canonical exports, combined lock/export diff: passed
CI YAML structure, shell syntax, effective-COPY mutation gate: passed
git diff --check for immutable production commit: passed
```

## Image Runtime Evidence

Official Docker Hub header requests timed out. This is retained as a transport caveat, not
as a failed clean-image claim: the exact same pinned base digest was fetched through a
mirror, then used to build both targets.

```text
Controller pre-final API image ID: b1b165f75d14
Final immutable-SHA reviewer API image ID:
sha256:2437e95e909b2b6d941e58b58b28551f5a09c87d93594ac9e4c80ae9ba7fe70c
Final Worker image ID: 17e8f6645b4b
API final non-root/path/import smoke: passed
Worker final non-root/path/import smoke: passed
```

The smokes verify final-image imports, package paths outside `/app/apps/api`, and the Worker
non-root UID. The mirror did not substitute a different base digest.

## Final Re-Audit And Integration Steps

1. Commit the documentation closure separately after controller inspection; do not amend or
   rewrite production candidate `215cd52565089138704c6b637350e18bc8705c8b`.
2. Let the independent reviewer finalize
   [`a2a-persistence-critical-reaudit-2026-08-24.md`](a2a-persistence-critical-reaudit-2026-08-24.md)
   against production commit `215cd52` plus the documentation closure.
3. Only a final independent `ACCEPT` may unblock a separate R0 branch. R1/R2 remain after
   R0; W1 stays an independent slice. None may be folded into this repair.
4. After controller acceptance, push the immutable repair and documentation commits, record
   their remote SHAs in the workbench delivery ledger, then integrate through the repository
   review flow. Do not push directly to `main` outside that flow.

Current verdict remains **pending final independent Critical re-audit after documentation
closure**. No A2a `ACCEPT` is claimed.
