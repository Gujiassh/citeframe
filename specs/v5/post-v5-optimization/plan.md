# Plan: Post-V5 Optimization

## 1. Sequencing Principle

Run governance and architecture decisions first, then install guards, then move code.
Product depth follows a capability/quality matrix rather than preceding it.

```text
Wave 0: G0 governance decision + A0 ownership decision + M0/P0 baselines
    -> Wave 1: required merge gates + contracts + first pure file splits + quality protocols
        -> Wave 2: Research/ingestion boundary pilots + authorized evidence runs
            -> Wave 3: all-modality migration + one evidence-selected depth investment
                -> Wave 4: API-source-free Worker candidate and release review
```

Wave numbers express dependencies, not authorization. Independent lanes may run in
parallel only when their file ownership and contracts do not overlap.

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

## 3. Lane A: API / Worker Boundary (6.0 -> target 7.5)

| Slice | Scope | Estimate | Exit gate |
| --- | --- | ---: | --- |
| A0 | Freeze the four ownership decisions and transport; sync architecture/database/V5 SSoT | 0.5-1 day | Owner-approved decision; zero production change |
| A1 | Add Python-only versioned DTO/Protocol package with no ORM/settings/provider client | 2-3 days | Dependency test proves contracts are pure; legacy runtime retained |
| A2 | Migrate Research port payloads to contracts and implement approved transaction adapter | 3-5 days | Old/new state, events, retry, cancel, recovery, and payload oracle equal |
| A3 | Freeze ingestion result/object/hash/compensation contract; pilot PDF or Image | 4-7 days | Same Representation/ContentUnit/Locator/object and failure semantics |
| A4 | Migrate the other eight adapters plus composition root | 10-20 days | Import baseline trends 28/96/12 to target/approved allowlist; all modality gates pass |
| A5 | Add Worker candidate build without API source/editable dependency/PYTHONPATH | 2-3 days | import/compile/start/ingest/Research/recovery/version-mismatch smoke passes |
| A6 | Replace legacy Worker target only after A5 | 1 day | Deploy/restore regression passes; old dependency removed last |

Required semantic oracle for A2-A6:

- same job state transitions, retry/lease behavior, error codes, and transaction outcome;
- same Asset generation, Representation, ContentUnit, locator, Citation/NoteSource, and
  Research save/replay meaning;
- before/after payload and database snapshots on real fixtures;
- candidate version mismatch fails closed.

Never use the single-modality A3 pilot as permission to enter A5. All nine adapters,
Research runtime, startup composition, and recovery must satisfy the boundary gate first.

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
| O1 Control plane | G0-G3, A0, M0, P0 | 4-6 days |
| O2 Safer codebase | A1-A2, M1-M3 | 10-16 days |
| O3 Boundary proof | A3-A4, M4-M6 | 15-30 days |
| O4 Product evidence/depth | P1 plus one of P2/P3/P4 | 7-15 engineering days plus M404 calendar time |
| O5 API-source-free Worker build | A5-A6 | 3-4 days after all prior gates |

These are planning ranges, not delivery commitments. A0/P0 evidence can stop or reorder
later work. Do not schedule all milestones as one release.

An API-source-free Worker build remains part of the same versioned Citeframe product. It
does not authorize independent API/Worker release versions or a microservice split.
