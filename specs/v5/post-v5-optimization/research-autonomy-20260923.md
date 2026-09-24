# Research autonomy and Markdown editions — 2026-09-23

## Current delivery state

The working-tree candidate implements automatic bounded research and separately persisted user report editions. API/Worker/unit and fixture-browser verification has passed within the scopes below. Real PostgreSQL multi-session verification and a visible end-to-end UI walkthrough against the migrated API, object store, worker, and approved provider configuration remain pending. No shared database migration, paid provider run, deployment, commit, or push was performed.

Source and repair branch: `main`, starting HEAD `50af19dc3b79fbb677d9ac66c005b77cbe76f3d9`. Canonical implementation checkout: `D:/Code/citeframe`. Before editing, HEAD and local `origin/main` were 0/0. Inherited R2 publication, W1 SSE, A3 and media/W2 changes remain in place. The historical media task remains unclosed.

## Behavior and contracts

- New runs bind immutable workflow v3 (`30000000-0000-4000-8000-000000000001`) and Agent I/O v2. Existing v2 workflow and v1/legacy I/O readers are retained. Historical v2 plans can still be approved against their own frozen release.
- Planner publication injects the existing API-owned `_approve_plan` materializer through the current persistence composition root. Successful auto-start creates the same execution snapshot, frozen assets, prompt bindings, DAG, and budget ledger. Artifact byte/hash, plan hash, current asset generation/index, provider fingerprint, policy availability, creator membership, lease, and cancel guards remain active. Automatic runs do not emit a pending approval request.
- Automatic decisions have `decision_origin=policy`, no human actor, and an explicit policy comment. Existing rows default to `human`. The DTO exposes `decisionOrigin`. A policy decision does not claim a human approved the plan.
- Workflow v3 conflict gates persist the conflict artifact and `leave_unresolved` dispositions, mark the gate complete, and queue synthesis atomically through the existing locked completion path. Conflict claims retain `resolved_unresolved`; synthesis only accepts supported, non-conflicted facts and includes every unresolved conflict in the final unresolved section. There is no new final publication approval.
- The researcher may propose a `nextQuery` string of 1–1000 characters or null. Program bounds: initial search plus at most two logical supplemental searches per branch step across attempts, at most three persisted model turns, fixed `evidence.search.v1`/`evidence.load.v1`, frozen branch asset IDs, and frozen top-k. Every production provider/tool call retains the existing reservation, cancellation, membership, lease, timeout, and aggregate budget checks. A retry remains subject to persisted run limits. Committed model turns replay; a response lost before checkpoint commit can require a new provider call, still charged to the run budget.
- Query dedup normalizes whitespace/case. Evidence dedup compares exact asset/representation/generation/index/parser/excerpt content because search clones locators and produces new snapshot fingerprints. A supplemental search with no new evidence stops before another model call. Prior validated claims survive a later empty response; exact text plus sorted handle IDs deduplicates claims across turns. No new data source, browser tool, or paid execution was introduced.
- Report editing uses a separate `research_report_edits` row per run. The original artifact bytes, claim verification, and evidence links remain immutable. User text is always unverified. Workspace members may read; the current run creator may write only a completed report. Saves lock and refresh the run, recheck membership, refresh the edition version, and reject stale versions with 409. Generated artifact integrity is checked on read/save. The UI separates original/user editions and preserves a conflicting draft. See `report-edit-20260923.md` for the API/UI contract.

## Additive migrations and deployment gate

1. Inherited R2 head: `n8b9c0d1e2f3`.
2. Report edition table: `o9c0d1e2f3a4`.
3. Decision-origin field/checks and immutable v3 release installation: `p0d1e2f3a4b5`.

The Alembic graph has one head. Apply the full approved chain before starting the new application version; new code expects the edition table, decision-origin column, and v3 release. The autonomy migration refuses a lossy downgrade. SQLite migration execution and PostgreSQL DDL compilation were tested; live PostgreSQL upgrade/locking remains unverified. The old metadata fixture is untouched. A separate two-table schema delta fixture freezes the authorized additions.

## Ownership and architecture integration

- Feature implementation lane: automatic plan, conflicts, bounded retrieval, API/Worker tests, integration fixes, and this delivery record.
- Report-editor child lane (`gpt-6-sol/high`, session `01a0cc9f-4be2-75f1-943b-94348042a12d`): edition model/API/UI and tests; completed. Ownership returned to the feature lane before the lock-refresh/membership integration fixes.
- Read-only review child: completed; identified historical approval, cumulative claims, and cross-release prompt binding defects. All three have targeted regression tests and repairs. Its scope was static autonomy review; it did not accept the full product or review the editor.
- Main controller owns architecture/navigation and final acceptance. The separately authorized architecture checkout `D:/Code/citeframe-architecture` is not written by this lane. Architecture integration must map paths and merge serially after candidate freeze, preserving both inherited dirty and feature changes. No staging or integration commit is authorized here.

New stable modules are `autonomy.py` and `automatic_decisions.py` in research persistence, `research_auto_progress.py` and `research_report_edit.py` in API services, `research_adaptive_retrieval.py` in Worker, and independent report-editor/Markdown/client modules in Web. The existing `research_prompt_provenance.py` remains responsibility-dense; this feature adds explicit release selection without moving evaluation or ingestion code. Existing `r803*` diagnostic coupling is unchanged, and no evaluation files are renamed or deleted.

## Verification evidence

Commands run from `D:/Code/citeframe` unless a different cwd is shown:

- `apps/api/.venv/Scripts/python.exe -B -m pytest apps/api/tests/test_research_autonomy.py apps/api/tests/test_research_report_edit.py apps/api/tests/test_research_adaptive_service.py apps/api/tests/test_research_router_basic.py apps/api/tests/test_research_router_plan.py apps/api/tests/test_research_router_recovery.py apps/api/tests/test_research_router_artifacts.py apps/api/tests/test_research_worker_lease_plan.py apps/api/tests/test_research_worker_budget_recovery.py apps/api/tests/test_research_worker_evidence_publication.py apps/api/tests/test_research_v5c_contract.py -q -p no:cacheprovider`: **201 passed**.
- `apps/api/.venv/Scripts/python.exe -B -m pytest apps/api/tests/test_research_persistence_boundary.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_migration.py -q -p no:cacheprovider`: **25 passed**.
- `apps/worker/.venv/Scripts/python.exe -B -m pytest apps/worker/tests/test_research_adaptive_retrieval.py apps/worker/tests/test_research_v5c_agent_io.py apps/worker/tests/test_research_single_attempt_dispatcher.py apps/worker/tests/test_research_runtime.py apps/worker/tests/test_research_executor.py -q -p no:cacheprovider`: **83 passed**.
- `pnpm --dir apps/web test`: **217 passed**. `pnpm --dir apps/web exec tsc --noEmit`, `pnpm --dir apps/web lint`, and `pnpm --dir apps/web build`: passed in final integration rechecks.
- From `D:/Code/citeframe/apps/web`, with `PLAYWRIGHT_START_WEB=1` and `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3111`: `pnpm exec playwright test e2e/report-edit.spec.ts --workers=1`: **4 passed**, independently rerun after child delivery and effect-lifecycle integration repair. This is a temporary Next server with mocked API routes, covering save/refresh, conflict recovery, stale GET/save isolation, and load/retry. It is not full real-backend UI acceptance.
- `test_research_adaptive_service.py` calls the actual persisted `search_frozen_evidence` service with deterministic embedding/retrieval doubles. It verifies query forwarding, frozen scope, tool-ledger charging, budget exhaustion, and cancellation before further external work. It establishes no real retrieval quality improvement. No R803 frozen-evidence fixture is used as recall evidence.

## Acceptance still pending

- Visible user walkthrough: new ordinary run proceeds without confirmation, cancel remains usable, conflicts reach a separate final section, user edition saves and survives refresh while original evidence remains accessible.
- Real migrated PostgreSQL/API/object-store integration, concurrent editors and membership removal, and worker restart/recovery under v3. No relevant local service listener was found on 3000/8000/5432/9000 at the pre-walkthrough check. Shared service setup/migration was not attempted.
- Actual provider/search quality and cost behavior require an explicitly approved runtime and test budget. This candidate has no paid-model or recall-quality acceptance claim.
- Main controller review and architecture-lane path-mapped serial integration.

Baseline and delivery manifests are stored under `C:/Users/baiao/Documents/Codex/2026-09-21/ai-ensemble-fork/citeframe-20260923`. Use the before/after hashes and baseline-relative patch for this feature; a plain HEAD diff also includes substantial inherited work. Historical evaluation records are preserved.


## Durable recovery and wire contract update

The repaired candidate adds migration `q1e2f3a4b5c6` after `p0d1e2f3a4b5`. `research_adaptive_turns` stores bounded, write-once model results by `(step_id, turn_number)`, the frozen execution ID, producing attempt, query, and input/result hashes. Retried registries replay the same initial search/load sequence and committed model results before any further query is issued. Search/load keys and their strict request-hash checks are unchanged. Claim IDs are deterministic across recovery. Read and write checkpoints validate the current lease, creator membership, and run cancellation state; new provider/tool calls retain the existing aggregate ledger gates. No schema or scope is inferred from a model response.

New `decision_submitted` events use schema version 2 with `decisionOrigin` and `policyId`. A policy actor is null with policy ID `research-autonomy-v1`; a human actor is non-empty with null policy ID. Other event types remain version 1. The serializer emits the persisted version. Web accepts historical version-1 human decisions, rejects unspecified null actors, and validates closed version-2 provenance. Deploy the matched Web/API/Worker contract together; older Web parsers do not support version 2.

The original report ID/hash is now part of every editor PUT. Detailed repair, prerequisite extraction, independent source-tree validation, and acceptance limits are recorded in `issue23-review-repair-20260923.md`. The original frozen candidate remains available for comparison and is superseded by this repair candidate; its earlier test counts are historical evidence.
