# Spec: Post-V5 Optimization

## 1. Objective

Raise Citeframe's structural and delivery quality without reopening completed V5
scope or disguising engineering coverage as model quality or user value.

The target is not a microservice rewrite or uniform feature depth. The target is:

- enforceable dependency direction;
- smaller, single-responsibility modules with unchanged behavior;
- evidence-led depth decisions across the nine enabled modalities;
- a protected `main` branch whose green checks are actual merge gates.

## 2. Current A1 Implementation Status

A1 was implemented and independently accepted on 2026-08-20: the pure
`citeframe_contracts` package, legacy identity-preserving re-exports, API/Worker
path-source integration, contracts-only Docker/CI smoke, and focused tests are present.
The design re-audit is accepted (`High=0`, `Medium=0`, `Low=0`). A1b/A2-foundation was
independently accepted on `2026-08-21` by the follow-up Critical review
(`High=0`, `Medium=0`, `Low=0`). A2a is implementer-complete; independent Critical review is pending; R0/R1/R2/W1
and downstream slices remain unstarted and blocked. No schema/API/save/replay/permission changes are authorized;
persistence and Research runtime semantics were not changed. A1 evidence: [`reviews/a1-contracts-implementation-2026-08-20.md`](reviews/a1-contracts-implementation-2026-08-20.md). A1b implementation evidence: [`reviews/a1b-persistence-implementation-2026-08-20.md`](reviews/a1b-persistence-implementation-2026-08-20.md); reviewer result: [`reviews/a1b-persistence-critical-audit-2026-08-20.md`](reviews/a1b-persistence-critical-audit-2026-08-20.md).

## 3. Verified Baseline

### 2.1 Architecture boundary

- `apps/worker/src` contains **41** Python source modules. **28 affected modules** contain
  **96** direct import statements referencing `ai_pdf_api`; **12** Worker modules directly
  import SQLAlchemy.
- API and Worker are separate processes but remain one versioned product with shared
  source, ORM, database, and transaction boundaries.
- API owns schema/migration and mutation-logic definitions. Research Worker `_ApiPort`
  currently creates sessions and commits/rolls back. Ingestion shares a Session/ORM
  boundary with modality adapters.

### 2.2 Maintainability

Current line-count baseline:

| File | Lines | Risk |
| --- | ---: | --- |
| `modalities/evidence.py` | 1587 | contracts, codecs, registry, and operations converge |
| `routers/assets.py` | 1526 | lifecycle, representation, and media endpoints converge |
| `test_r803_campaign_v5.py` | 2461 | campaign, integrity, retry, and scoring cases converge |
| `v5b_document_restore_acceptance.py` | 2006 | backup, restore, verify, and CLI converge |
| `services/multimodal_execution.py` | 1027 | schemas, provenance, validation, and report rendering converge |
| `test_multimodal_execution.py` | 1036 | baseline, tamper, provenance, and report tests converge |

Line count is a signal, not the acceptance criterion. A split is useful only when each
resulting module has one responsibility and the before/after behavior oracle is equal.

### 2.3 Product completeness

- Enabled kinds: `pdf`, `image`, `document`, `html`, `docx`, `xlsx`, `pptx`, `audio`, `video`.
- PDF/Image are `Deep`; the remaining seven are `Evidence-complete`.
- Model quality remains `not_evaluable` without an authorized R803 successor campaign.
- User value remains `not_evaluable` without an approved M404 protocol and qualified users.
- Known depth candidates include Office fidelity, Audio diarization/time-range UX, and
  richer Video shot/keyframe analysis with cost/latency limits.

### 2.4 Delivery governance

- GitHub `main` branch protection: absent.
- GitHub repository rulesets: empty.
- CI currently exposes six passing jobs: `api`, `worker-fast`, `worker-acceptance`,
  `worker-evaluation`, `web`, and `web-e2e`.
- Because the branch is unprotected, those jobs are evidence but not mandatory merge gates.

## 3. Goals

| ID | Goal |
| --- | --- |
| A | Remove Worker dependence on API internals through an approved ownership/transport target and measurable migration gates |
| M | Split the highest-risk mixed-responsibility files without changing runtime, HTTP, persistence, or evaluation semantics |
| P | Make modality depth investment depend on user tasks, quality evidence, latency, and cost rather than format count |
| G | Make reviewed PRs and the six CI jobs enforceable on `main` |

## 4. Non-goals

- No immediate microservice split, event-bus migration, database split, or package rename.
- No change to Asset/Representation/ContentUnit/EvidenceLocator, Citation, NoteSource,
  Research, API, SSE, save, replay, or permission semantics.
- No attempt to make all nine modalities equally deep in one release.
- No paid R803 run, M404 study, or public-release claim without separate authorization.
- No GitHub branch/ruleset mutation without explicit owner authorization.
- This plan does not authorize additional schema/API changes, G/M/P work, GitHub settings,
  provider spend, or user research. A1b/A2-foundation was independently accepted on 2026-08-21
  by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`); A2a is implementer-complete; independent Critical review is pending; R0/R1/R2/W1 and downstream remain blocked;
  no schema/API/save/replay/permission changes are authorized.

## 5. Owner Decision Gates

| Gate | Decision required before implementation |
| --- | --- |
| `G0` | Approve exact `main` protection/ruleset policy and permitted owner bypass |
| `A0` | Record owner-authorized same-DB ownership/transport target; the design re-audit is accepted and A1 was independently accepted on 2026-08-20; A1b/A2-foundation was independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0) |
| `A-DATA` | Approve any proposed persistence, payload, API, save, or replay contract change before code |
| `P0` | Approve priority user segment/tasks and modality scoring weights |
| `P-R803` | Approve provider/profile, budget ceiling, threshold, and new artifact directory |
| `P-M404` | Approve protocol, qualified users, task set, success criteria, and privacy boundary |

## 6. Architecture Recommendation And Owner Authorization

For `internal_preview`, owner has authorized a versioned pure contracts boundary plus a
same-PostgreSQL-database adapter. API owns HTTP/authentication, Alembic execution, and
schema governance; Worker owns Research orchestration and provider/tool execution; the
Worker-side UoW is the Research job runtime commit-process owner. Package staging is strict:
A1 creates only `citeframe-backend-contracts` / `citeframe_contracts` for pure DTO/Protocol;
A1b/A2-foundation then adds `citeframe-backend-persistence` / `citeframe_persistence` for
one DeclarativeBase/Base.metadata and all ORM mappings; A2a finally adds
`citeframe-research-persistence` / `citeframe_research_persistence` for Research
repositories/UoW/commands/locks. No behavior-free Research package scaffold may appear
before A2a. Each stage extends API/Worker manifests, source-copy paths, PYTHONPATH, and
pre-start smoke only with the package introduced by that stage. The current
`ai_pdf_api.models` surface may temporarily re-export the same classes. API Alembic
explicitly imports `citeframe_persistence.models` only after A1b. API and Worker use the
same persistence commands; models and transition logic are not copied.

This is an approved **target direction**, not a current implementation claim. The design
re-audit is accepted (`High=0`, `Medium=0`, `Low=0`); A1 was independently accepted
on `2026-08-20`. A1b/A2-foundation was independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0). A2a is implementer-complete; independent Critical review is pending; R0/R1/R2/W1 and downstream remain blocked.
Current Research `_ApiPort` and ingestion shared Session/ORM facts remain until their named
slices land. Same-DB adapter must not be described as API-process commit.

The implementation-ready contract is in
[`research-boundary-runtime-design.md`](research-boundary-runtime-design.md). A2a/R0/R1/R2/W1
and downstream implementation remains blocked. No schema/API/save/replay/permission changes
are authorized.
Internal HTTP/RPC, database split, Redis/Kafka scheduling, workspace/provider-wide capacity,
G/M/P, and GitHub settings are outside this authorization.

## 7. Research Runtime Invariants

The Research target preserves one planned subproblem = one `ResearchStep`, one
retry/lease = one `ResearchStepAttempt`, and one researcher attempt = zero-to-many
`ResearchClaim`. The R1 target dispatcher claim operation creates and leases one Attempt, then
one handler executes exactly that leased Attempt; this is distinct from the persisted
`ResearchClaim` entity and does not change A-DATA/schema/API/save/replay/permission semantics.
PostgreSQL remains the persistence and business authority for DAG dependencies, readiness,
joins, conflicts, cancellation, retry, reclaim, events, and budgets. During A2a, the current fixed LangGraph StateGraph remains the in-process executor and
may drive multiple steps in one `process_one`; it is not a persisted checkpoint authority.
After A2a is accepted, R0 must normalize lock acquisition before R1. R1 then removes
LangGraph from runtime step execution (it may remain only as a plan-approval topology
validator) and uses one claimed Attempt per handler in a bounded pool of independent
dispatcher loops. Research-enabled production uses at least two loops and acceptance
proves real branch overlap; the persisted per-Run cap remains the concurrency authority.
R1 handlers validate existing dependency/upstream persisted status, execution snapshot
identity/hash, and artifact/claim/evidence provenance/hash from the DB and do not carry
cross-step in-memory `ResearchState`. Existing `ResearchStep.input_sha256` keeps its
current meaning; a canonical handler-input hash requires separate A-DATA.

Normal claim creates a new Attempt for a queued Step; heartbeat only extends the same
currently running Attempt; expiry reclaim marks the old Attempt `abandoned`, synchronizes
the Step through its existing `failed`/`queued` or cancellation path, and a later retry
creates a new Attempt. An expired Attempt is never refreshed or revived.

**Current lock fact:** acquisition is mixed and conflicting: Worker attempt paths commonly
use `Attempt -> Step -> Run`, claim uses `Step -> Run`, and API cancel/retry/decision paths
use `Run -> Step`; claim-vs-cancel has a real deadlock ring. A2a retains current lock
behavior. **R0 target, not implemented:** normalize all multi-row paths to
`Run -> Step -> Attempt -> Call -> Ledger`. Attempt/Call id paths locate parent IDs without
locks, then acquire, refresh, and revalidate the complete chain; changed locators or
status/token/expiry fail closed. Claim orders candidate Runs by the minimum eligible Step tuple
`(queued_at, created_at, step_id)`, then Run ID; it locks the candidate Run first, rechecks status/cap,
then locks the eligible Step using the existing `queued_at`, `created_at`, then Step ID ordering, and creates Attempt. Cancel remains
Run-first. Heartbeat, complete, reclaim, retry, decision, join, provider/tool, and
publication use the same order. R0 changes lock acquisition only and requires real
PostgreSQL lock evidence before R1 or per-Run admission; no deadlock retry is allowed.

Per-Run `maxParallelResearchers` uses existing Attempt rows as durable slots after R0.
A cap-full candidate Run rolls back the whole claim transaction, releases the Run lock,
records local `excluded_run_ids`, and continues in a new transaction. It locks no Step
and mutates no Attempt/status/Event; only after the locked cap check passes may it lock an
eligible Step. Query prefiltering is optimization only. R2 covers the lock matrix, two
Workers, and cap-full plus other-Run fairness/no-starvation.

Research SSE is an independent W1 slice: single-flight plus dirty rerun/coalescing is
performance behavior; only explicit proven event fields apply, stale sequence responses
are discarded, Run switches abort/discard, artifact content is keyed by `(id, sha256)`,
terminal events flush immediately, history gaps/cursor conflicts trigger full reads, and
LISTEN/NOTIFY is only a post-commit wakeup beside persisted replay.

## 8. Success Measures

- No new Worker `ai_pdf_api` or SQLAlchemy import is added after baseline guards land.
- Final boundary target: Worker runtime imports `ai_pdf_api` = 0, or a small owner-approved
  allowlist with an expiry condition; modality/domain code imports SQLAlchemy = 0.
- Non-semantic splits preserve OpenAPI, JSON/payload, canonical report, error-code,
  permission, and frozen-artifact oracles.
- Every enabled modality has an explicit task/depth/quality/cost row; only evidence-backed
  depth work is promoted.
- A deliberately failing PR cannot merge to `main`; a fully green reviewed PR can.
- A2a preserves the current one-`process_one` multi-step LangGraph behavior and has only
  Research behavior/import-smoke scope; R1 one-step dispatch is a separate implementation
  PR; R2 proves two or more Workers against real PostgreSQL. A2a event rows/bytes are equal;
  R1/R2 use a per-Run contiguous/unique seq and partial-order event oracle with variable independent researcher interleaving.
- A5 is not claimable until A3/A4 complete the nine-modality migration and the Research
  runtime/composition/recovery import and behavior gates pass.
- W1 passes stale response, burst, reconnect, lost-notify, history-gap, terminal, and
  artifact hash/provenance scenarios without changing the SSE/API contract.
