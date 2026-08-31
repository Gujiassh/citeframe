# Plan: Post-V5 Optimization
> **Current gated sequence (2026-09-01):** R1.5 admission received independent Critical
> `ACCEPT` with findings=0. Its PostgreSQL artifact is
> `docs/evals/r15-postgres-admission-2026-08-31.json` at SHA-256
> `eab095bd68a78972c5b80713d2746a816551eaf1d21bb24ee48016615104d9be`.
> R2 PostgreSQL proof-only is the next stage.

## 1. Sequencing Principle

The owner-authorized architecture freeze and design re-audit are complete: the design audit
accepted with `High=0`, `Medium=0`, `Low=0`. A1 implementation was independently accepted
on `2026-08-20`. A1b/A2-foundation was independently accepted on `2026-08-21` by the
follow-up Critical review (`High=0`, `Medium=0`, `Low=0`); PR #20 is merged at `origin/main@9f40241`; PR #21 head `1d81470` is merged at `origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI, delivering A2a/R0. R1 was independently `ACCEPTED` on 2026-08-25 (`High=0`, `Medium=0`, `Low=0`) across start `8674d4dc407048471f7b14b23b821e72529487bf`, historical initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`REWORK`), runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`, ledger `652cfd47f8bc462038e1bd623afc2b33a4ce511a`, canonical docs `559997d073cc2d26fb346c30e2ab9f20550b673f`, delivery truth `80d395d4fd19c0146b22befc2929bc556cfe62fa`, and review `5a55489fef8380f78854f10666a2fdd2983beeff`. The complete R1 chain was delivered by PR #22 at `origin/main@a616eea1350b095c6f229890d2c47e5010902330` with `6/6` CI. R1.5 admission is independently Critical ACCEPTED (findings=0); R2 proof-only is next; W1 SSE and downstream remain blocked. No schema/API/save/replay/permission change is authorized. Product
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
follow-up Critical review (`High=0`, `Medium=0`, `Low=0`). PR #20 is merged at `origin/main@9f40241`; PR #21 head `1d81470` is merged at `origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI, delivering A2a/R0. R1 was independently `ACCEPTED` on 2026-08-25 (`High=0`, `Medium=0`, `Low=0`) across start `8674d4dc407048471f7b14b23b821e72529487bf`, historical initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`REWORK`), runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`, ledger `652cfd47f8bc462038e1bd623afc2b33a4ce511a`, canonical docs `559997d073cc2d26fb346c30e2ab9f20550b673f`, delivery truth `80d395d4fd19c0146b22befc2929bc556cfe62fa`, and review `5a55489fef8380f78854f10666a2fdd2983beeff`. The complete R1 chain was delivered by PR #22 at `origin/main@a616eea1350b095c6f229890d2c47e5010902330` with `6/6` CI. R1.5 admission is independently Critical ACCEPTED (findings=0); R2 proof-only is next; W1 SSE and downstream remain blocked. No schema/API/save/replay/permission change is authorized. No schema/API/save/
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
`2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`). A2a/R0 are delivered at `origin/main@8674d4d`. R1 is independently `ACCEPTED (High=0, Medium=0, Low=0)` at review `5a55489` and delivered by PR #22 at `origin/main@a616eea` with `6/6` CI. R1.5 admission is independently Critical ACCEPTED (findings=0); R2 proof-only is next; W1 SSE/downstream remain blocked; no schema/API/save/replay/permission change is authorized.

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

Delivered boundary history: PR #20 merged `origin/main@9f40241`. PR #21 head
`1d81470b816c3f8c107aa3023f828840c9a1c8da` merged as
`origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI. It includes
A2a Worker-environment isolation fix `4b24181a3b2a5fbca3cbf6ee0cf0a3ac0d72ca96`
and ledger `1d81470`, which records the exact Worker environment. A2a and R0 are delivered.

Current R1 acceptance ledger: start `8674d4dc407048471f7b14b23b821e72529487bf`;
historical initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`REWORK`);
runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`; implementation ledger
`652cfd47f8bc462038e1bd623afc2b33a4ce511a`; canonical docs
`559997d073cc2d26fb346c30e2ab9f20550b673f`; delivery truth
`80d395d4fd19c0146b22befc2929bc556cfe62fa`; final Critical
[`ACCEPT (High=0, Medium=0, Low=0)`](reviews/r1-single-attempt-dispatcher-critical-review-2026-08-24.md)
at review `5a55489fef8380f78854f10666a2fdd2983beeff` and delivered by PR #22 at
`origin/main@a616eea1350b095c6f229890d2c47e5010902330` with `6/6` CI. Evidence: Worker `349`, named gate `64+40`, API `132`,
A2a `equal=true` handled `3 -> 8` / UoW `43`, PostgreSQL `7/7` deadlocks `0`, human gate
zero-mutation, causal errors preserved, and LangGraph absent from runtime imports. R2 is the
only next separately gated module; W1/admission/downstream remain blocked.

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
