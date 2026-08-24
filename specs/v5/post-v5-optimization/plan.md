# Plan: Post-V5 Optimization

## 1. Sequencing Principle

The owner-authorized architecture freeze and design re-audit are complete: the design audit
accepted with `High=0`, `Medium=0`, `Low=0`. A1 implementation was independently accepted
on `2026-08-20`. A1b/A2-foundation was independently accepted on `2026-08-21` by the
follow-up Critical review (`High=0`, `Medium=0`, `Low=0`); A2a was independently `ACCEPTED` on 2026-08-24 (`High=0`, `Medium=0`, `Low=0`) at production commit `215cd52565089138704c6b637350e18bc8705c8b`, documentation closure `95981a499521a28bfd9eb24480d54ef42f485528`, and review record `eb97adfa75660867eb31d46a4e7d7712909c348e`. All three commits are local and not pushed. R0 was independently `ACCEPTED` on 2026-08-24 (`High=0`, `Medium=0`, `Low=0`) across start `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`, production `39766c374bd584b0cb834ef103de025d233c87c1`, final ledger closure `6b8ab475c14a7bbfe90f59a635255ca3768edcf9`, and review record `9d4297f89451fe79b6d1c141613722f7749b11c0`. All four commits are local and not pushed; the branch has no upstream and no remote branch. R1 is the only next separately gated implementation slice; R2/W1 and downstream remain blocked. R0 acceptance authorizes no schema/API/save/replay/permission/admission change and does not claim R1 implementation. Product
depth follows a capability/quality matrix rather than preceding it.

```text
Wave 0: A0/R/W target freeze + design re-audit `ACCEPT` (`High=0`, `Medium=0`, `Low=0`) + M0/P0 baselines
    -> Wave 1: A1 contracts -> A1b/A2-foundation neutral mappings -> A2a Research behavior extraction
        -> Wave 2: R0 lock normalization -> R1 one-claimed-attempt dispatcher + R2 real PostgreSQL proof + W1 SSE
            -> Wave 3: A3/A4 nine-modality migration and composition-root boundary proof
                -> Wave 4: A5/A6 API-source-free Worker candidate and release review
```

Wave numbers express dependencies, not authorization. A1 was independently accepted
on `2026-08-20`; A1b/A2-foundation was independently accepted on `2026-08-21` by the
follow-up Critical review (`High=0`, `Medium=0`, `Low=0`). A2a was independently `ACCEPTED` on 2026-08-24 (`High=0`, `Medium=0`, `Low=0`) at production commit `215cd52565089138704c6b637350e18bc8705c8b`, documentation closure `95981a499521a28bfd9eb24480d54ef42f485528`, and review record `eb97adfa75660867eb31d46a4e7d7712909c348e`. All three commits are local and not pushed. R0 was independently `ACCEPTED` on 2026-08-24 (`High=0`, `Medium=0`, `Low=0`) across start `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`, production `39766c374bd584b0cb834ef103de025d233c87c1`, final ledger closure `6b8ab475c14a7bbfe90f59a635255ca3768edcf9`, and review record `9d4297f89451fe79b6d1c141613722f7749b11c0`. All four commits are local and not pushed; the branch has no upstream and no remote branch. R1 is the only next separately gated implementation slice; R2/W1 and downstream remain blocked. R0 acceptance authorizes no schema/API/save/replay/permission/admission change and does not claim R1 implementation. No schema/API/save/
replay/permission changes are authorized. G/M/P and GitHub settings remain separate
unauthorized lanes.

## 2. Lane G: Delivery Governance (5.5 -> target 8.0)

| Slice | Scope | Estimate | Acceptance |
| --- | --- | ---: | --- |
| G0 | Owner approves `main` ruleset, reviewer availability, and break-glass policy | 0.5 day | Decision records exact settings; no mutation before approval |
| G1 | Require PRs, resolved conversations, and six named CI checks; block force-push/delete | 0.5 day | Failing probe PR blocked; green PR mergeable under the approved review policy; API evidence archived |
| G2 | Add workflow concurrency cancellation and explicit timeouts where absent | 0.5 day | Superseded runs cancel; genuine failures remain visible |
| G3 | Upgrade actions that emit Node 20 deprecation warnings | 0.5 day | Same six jobs pass with warning removed; no dependency/output drift |

Recommended required checks:

`api`, `worker-fast`, `worker-acceptance`, `worker-evaluation`, `web`, `web-e2e`.

Do not configure an impossible approval rule. If the repository has only one accountable
maintainer, start with zero required approvals while still requiring a PR, resolved
conversations, and all six checks. Raise the rule to one real approval only after a named
second maintainer exists. CODEOWNERS and multiple approvals remain unnecessary at the
current scale.

## 3. Lane A/R/W: API / Worker Boundary And Research Runtime

Owner-authorized direction: same-DB adapter, API HTTP/auth/Alembic/schema governance,
Worker orchestration, Worker-side Research UoW commit process, pure contracts, and one
shared `citeframe_research_persistence` behavior implementation over neutral mappings. The
design re-audit is accepted (`High=0`, `Medium=0`, `Low=0`). A1 implementation was
independently accepted on `2026-08-20`; A1b/A2-foundation was independently accepted on
`2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`). A2a was independently `ACCEPTED` on 2026-08-24 at production `215cd52`, documentation `95981a4`, and review record `eb97adf`; all remain local and not pushed. R0 was independently `ACCEPTED` on 2026-08-24 (`High=0`, `Medium=0`, `Low=0`) across start `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`, production `39766c374bd584b0cb834ef103de025d233c87c1`, final ledger closure `6b8ab475c14a7bbfe90f59a635255ca3768edcf9`, and review record `9d4297f89451fe79b6d1c141613722f7749b11c0`. All four commits are local and not pushed; the branch has no upstream and no remote branch. R1 is the only next separately gated implementation slice; R2/W1 and downstream remain blocked. R0 acceptance authorizes no schema/API/save/replay/permission/admission change and does not claim R1 implementation; no
schema/API/save/replay/permission changes are authorized.

| Slice | Scope | Estimate | Exit gate |
| --- | --- | ---: | --- |
| A0 | Freeze ownership, package boundaries, save semantics, lock/fencing contract, per-Run admission, and W1 boundary | 0.5-1 day | Owner authorization recorded; no production change; design re-audit `ACCEPT` |
| A1 | Add only `citeframe-backend-contracts` (`citeframe_contracts`) pure DTO/Protocol package and necessary legacy re-exports | 2-3 days | API/Worker add only contracts path; contracts-only export, source-copy, PYTHONPATH, and import smoke; no ORM/Research package |
| A1b / A2-foundation | On top of A1, add `citeframe-backend-persistence` (`citeframe_persistence`) as the unique Base/metadata and all-model mapping distribution | 1-2 days | Add only persistence to manifests/locks, source-copy, PYTHONPATH, and smoke; table/column/constraint/index zero drift; no Research package or schema/save change |
| A2a | On top of A1b, add `citeframe-research-persistence` (`citeframe_research_persistence`) Research behavior/ports | 3-5 days | Only now add the third manifest/path/COPY/PYTHONPATH; preserve current multi-step `process_one` and mixed locks; old/new DB/payload/Event/retry/cancel/recovery snapshots equal; final three-package smoke |
| R0 | Normalize all lock acquisition to `Run -> Step -> Attempt -> Call -> Ledger`; no save/API semantic change | 2-4 days | Real PostgreSQL `pg_locks`/timeout evidence for claim-vs-cancel/complete, reclaim-vs-provider, two claims; separate PR before R1/admission |
| R1 | Change `process_one` to dispatch exactly one newly claimed and leased Attempt to one step-kind handler through bounded concurrent dispatcher loops | 3-5 days | Starts only after R0; production-shaped two-loop overlap/wall-time oracle, one-step handler, fencing, readiness/join, no in-memory cross-step state; separate PR from A2a/R0 |
| R2 | Real PostgreSQL two-or-more Worker contention, per-Run cap, lease/reclaim/cancel/provider/join/recovery proof | 2-4 days | Immutable Critical report; SQLite-only evidence is insufficient |
| A3 | Freeze ingestion result/object/hash/compensation contract and pilot one modality | 4-7 days | Same Representation/ContentUnit/Locator/object/failure semantics; pilot is not A5 entry |
| A4 | Migrate the other eight adapters plus composition root | 10-20 days | Nine-modality import/behavior/recovery gates pass |
| A5 | Candidate Worker build without API source/editable dependency/PYTHONPATH | 2-3 days | import/compile/start/ingest/Research/recovery/version-mismatch smoke |
| A6 | Replace legacy Worker target only after A5 | 1 day | Deploy/restore regression passes; old dependency removed last |
| W1 | Independent Research SSE single-flight, sequence gate, event-directed artifact cache, replay fallback | 2-4 days | Burst/stale/reconnect/lost-notify/gap/terminal/hash evidence; no API/save contract change |

Current A2a delivery ledger: PR #20 is merged at `origin/main@9f40241`; semantic baseline `d1b5945`; initial snapshot `20d411e`; initial review record `5a6ee38`; immutable production candidate `215cd52565089138704c6b637350e18bc8705c8b` on `work/research-boundary-runtime-20260824`, local and not pushed. Candidate production composition uses neutral commands/UoW with `uowEnterCount=38`; final differential/boundary is `8 passed`, `equal=true`, semantic SHA `119a36086bfb595ea0882deab719d530ebd0107296cf8033a4f348ef07e7d4c0`, report SHA `db1524a8a2604c60c98e1543eded1828cc8f9e23725287cb40d0056cace42bd7`. Controller evidence is API `650 passed, 6 skipped, 1 warning`; Worker fast `174 passed, 153 deselected`; acceptance `61 passed, 266 deselected`; evaluation `92 passed, 235 deselected`; deploy `6+2`; lock/export/YAML pass. Official Docker Hub timed out, but the same pinned base digest fetched through a mirror built controller pre-final API `b1b165f75d14`; the reviewer rebuilt immutable-SHA API `sha256:2437e95e909b2b6d941e58b58b28551f5a09c87d93594ac9e4c80ae9ba7fe70c`; final Worker remains `17e8f6645b4b`, and final non-root/path/import smokes passed. Final Critical review is `ACCEPT (High=0, Medium=0, Low=0)` at local review commit `eb97adf`; production, documentation, and review commits are not pushed, so remote push/PR/integration remains pending.

Current R0 delivery ledger: start `7ee97471ffb7d7d23e941d75795ab21d8cb3032b`; production `39766c374bd584b0cb834ef103de025d233c87c1`; final ledger closure `6b8ab475c14a7bbfe90f59a635255ca3768edcf9`; final Critical `ACCEPT (High=0, Medium=0, Low=0)` at review commit `9d4297f89451fe79b6d1c141613722f7749b11c0`. All four are local/not pushed; the branch has no upstream and no remote branch. PostgreSQL 17.10 contention is `7/7`, report SHA `95f2608e3455a7c0a1272fddc727c0339cdc65d28384c13d6d29318d5dbdf91d`, deadlocks `0 -> 0`, no `40P01`/`55P03`; official Docker Hub timed out before start, while the same immutable pgvector digest through the mirror completed all evidence; focused `8`, affected API `90`, supplementary API `49`, Worker `43`, A2a differential `equal=true` coverage `7/7`. R1 is the only next separately gated implementation slice; R2/W1/downstream remain blocked.

Required semantic oracle for A2a/R0/R1/R2/A3-A6/W1:

- same Step/Attempt/Claim/state-version transitions, retry/lease, cancel, reclaim, conflict,
  artifact hash/provenance, budget, permission, and API payload meaning; R0 changes lock
  acquisition order only; A2a Event rows/bytes
  are equal; R1/R2 use the event projection/partial-order oracle below;
- same provider/tool reserve/send/reconcile/cancel and object publication commit-unknown
  compensation behavior;
- before/after database and payload snapshots on real fixtures;
- two or more Workers against real PostgreSQL for contention and recovery;
- Research SSE stale-response, Run-switch, history-gap, terminal, lost-notify, and
  `(artifactId, sha256)` cache scenarios; per-Run contiguous/unique seq and partial-order event oracle passes.

Event oracle for R1/R2: within each Run, `seq` starts at 1, is contiguous and unique, and is allocated atomically across Workers; each Step has
`queued < started < terminal`; Attempt/lease events are legal; all dependencies succeed
before a dependent is queued; Run terminal is last; dedupe prevents duplicate terminal
facts; payload schema/error meaning stays equal. Independent Researcher event interleaving
may vary.

A2a is not R0 or R1. A2a preserves the fixed behavior where one `process_one` call can drive
multiple steps through LangGraph and retained the historical mixed lock behavior; accepted
R0 later normalized locks. R1/admission remain separate; R1 is the separate single-attempt dispatcher. A3/A4 cover all nine enabled
modalities before A5 can claim an API-source-free Worker.

## 4. Lane M: Maintainability (6.5 -> target 7.5)

All M slices are non-semantic. Keep a facade/re-export only when it preserves a real public
import surface; do not add compatibility layers for private internals.

| Slice | File/split | Estimate | Mandatory oracle |
| --- | --- | ---: | --- |
| M0 | Add line/import/function baseline report and module ownership map | 0.5 day | Reproducible command output; no arbitrary line-limit CI failure |
| M1 | `evidence.py`: contracts + registry/dispatch + modality codecs + operations | 2-3 days | locator round-trip/clone/retrieval keys and all fixture hashes equal |
| M2 | `assets.py`: lifecycle + representation/content + media streaming routers | 2-3 days | OpenAPI, auth, status/error, headers, ranges, and streaming behavior equal |
| M3 | `multimodal_execution.py`: schemas + source/provenance + validators/report | 1-2 days | canonical M402 report byte-identical; tamper and single-read tests equal |
| M4 | Split `test_r803_campaign_v5.py` by runner/integrity/retry/scoring | 1-2 days | collected test IDs and frozen campaign semantics retained |
| M5 | Split restore acceptance into backup/restore/verify/CLI | 1-2 days | same CLI, exit codes, report JSON, cleanup, and restore oracle |
| M6 | Split M402 tests by baseline/provenance/tamper/report | 1 day | same tests and attack coverage; no shared mutable fixture leakage |

Execute one production-file split per PR. Do not combine M1/M2 with boundary transport or
product-depth behavior; review must be able to attribute any regression to one move.

## 5. Lane P: Product Completeness (7.0 -> target 8.0)

### P0: Capability and value matrix (2-3 days)

For each of the nine kinds, record:

- top user task and representative real fixture;
- upload/ingest/retrieve/cite/view/delete/restore status;
- locator fidelity and viewer inspectability;
- retrieval/answer quality evidence and known failure modes;
- p50/p95 processing latency, model calls, and estimated cost;
- user-value evidence or `not_evaluable`.

Use the matrix to rank depth work. Do not score a modality as complete merely because its
adapter and viewer exist.

### P1: Quality and user-value gates

| Slice | Scope | Estimate | Gate |
| --- | --- | ---: | --- |
| P1a | Approve new R803 campaign matrix across selected tasks/modalities | 1 day plan + 1-2 days run/analysis | Budget/profile/threshold/new directory approved; frozen v1 untouched |
| P1b | Approve and run M404 with qualified target users | 1-2 weeks calendar | Protocol, raw evidence, repeat use, and conclusion adoption recorded |
| P1c | Release review | 0.5 day | Engineering, model quality, and user value judged separately |

### P2-P4: Depth candidates (select one after P0/P1 evidence)

| Candidate | Bounded first slice | Estimate | Contract caution |
| --- | --- | ---: | --- |
| P2 Office | Fidelity fixture set; improve the highest-value DOCX/XLSX/PPTX inspection gap, not generic WYSIWYG | 4-8 days | Preserve Office locator and content/save meaning |
| P3 Audio | Speaker-aware transcript and stronger time-range review UX | 4-7 days | Diarization persistence/metadata requires `A-DATA` approval if meanings change |
| P4 Video | Shot boundaries, representative keyframes, and cost/latency gate | 5-8 days | New persisted shot/frame meaning requires `A-DATA` approval |

Selection rule: prioritize the candidate with the highest observed user-task failure impact
per engineering/model cost. At most one depth candidate enters active implementation at a
time until its quality and user-value delta is measured.

## 6. Cross-Lane Gates

| Gate | Required evidence |
| --- | --- |
| Light docs/settings | Diff review, exact API/settings evidence, rollback/break-glass note |
| Standard refactor | Unit/integration tests, before/after contract snapshot, import/dependency evidence |
| Critical boundary/data/depth | Real fixture, old/new payload or database comparison, runtime evidence, independent reverse review |

Every implementation slice must update its spec/tasks/SSoT and dev-workbench checkpoint.
Implementation defaults to a lower-cost worker model; Critical decisions, acceptance, and
integration remain owned by the main controller and an independent reviewer.

## 7. Aggregate Estimate and Milestones

| Milestone | Included | Engineering estimate |
| --- | --- | ---: |
| O1 Control plane | A0, M0, P0 | 1-3 days plus re-audit |
| O2 Safer codebase | A1-A1b-A2a, M1-M3 | 11-18 days |
| O3 Research runtime proof | R0-R2 and W1 | 9-17 days after A2a |
| O4 Boundary proof | A3-A4, M4-M6 | 15-30 days |
| O5 Product evidence/depth | P1 plus one of P2/P3/P4 | 7-15 engineering days plus M404 calendar time |
| O6 API-source-free Worker build | A5-A6 | 3-4 days after all prior gates |

These are planning ranges, not delivery commitments. A0/P0 evidence can stop or reorder
later work. Do not schedule all milestones as one release.

An API-source-free Worker build remains part of the same versioned Citeframe product. It
does not authorize independent API/Worker release versions or a microservice split.
