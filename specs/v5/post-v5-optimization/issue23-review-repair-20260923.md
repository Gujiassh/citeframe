# Research autonomy review repair — 2026-09-23

## Delivery state

The three confirmed code defects have implementation repairs and bounded regression evidence. Independent Hubble re-review is requested against a new frozen repair delta. Shared-service migrations, real PostgreSQL concurrency/restart/revocation, and visible product acceptance remain blocked. No commit, push, PR creation, merge, paid provider call, or architecture patch application is included.

Canonical checkout: `D:/Code/citeframe`, branch `work/research-autonomy-conflicts-20260923`, HEAD `50af19dc3b79fbb677d9ac66c005b77cbe76f3d9`. Franklin holds repair write ownership; Averroes's #25 design remains untouched. No child implementation agent was started for this repair.

## Repaired contracts

### Decision events

New `decision_submitted` events persist schema version 2 and closed fields `decisionOrigin` and `policyId`. Human decisions require a nonempty actor and null policy ID. The two policy actions use null actors and `research-autonomy-v1`; their decision type/action pair is validated. Other events keep version 1. The API serializer emits the persisted version. The Web parser accepts historical version-1 human decisions and rejects unspecified null actors, forged policy actors, unknown origins, and null required artifact fields. Matched Web/API deployment is required for the new wire version.

The cross-layer test creates actual persisted automatic-plan and conflict-gate events, calls `serialize_sse_event`, then invokes Web `parseResearchSse` and `consumeResearchStream`. It checks emitted transition sequences; it does not exercise an HTTP SSE connection or a real final-report browser flow.

### Adaptive recovery

Migration `q1e2f3a4b5c6` adds `research_adaptive_turns` after `p0d1e2f3a4b5`. The composite key `(step_id, turn_number)` and database range check allow three logical turns per step across attempts. Each write-once row binds the frozen execution, creating attempt, exact query, request hash, result hash, and validated model result. The previous checkpoint's next query must equal the resumed query. Reads and saves validate the current lease, membership, and run state under the existing run/step/attempt lock ordering.

On retry, a fresh evidence registry replays initial search/load calls and saved model results in the same order, so the existing step-scoped tool keys retain exactly the same request hashes. The tool replay guard is unchanged. Successful search/load results remain in their existing ledger/evidence tables. Model output is checkpointed before issuing its next query. A crash after provider completion but before checkpoint commit can cause another budgeted provider call; no downstream query has used that uncommitted result. This is not an exactly-once provider guarantee. Claims have deterministic IDs across attempt recovery; prior validated claims and evidence are reconstructed without duplicates.

Regression cases use actual search/load services, `EvidenceToolRegistry`, real tool/provider ledger commands, actual fail/reclaim transitions, and new registries. Retrieval/model outputs are injected. Cases cover search commit then failure, model result before checkpoint, checkpoint commit then failure, provider timeout, failed tool retry, different A/B model proposals, repeated complete-loop replay, tool/provider budgets, cancellation, membership removal, hash mismatch, and out-of-bound turn. A separate test instantiates the production `LedgeredGeneration` checkpoint adapter and composition root across sessions/attempts. No external provider or recall-quality claim is made.

### Editor original binding

Every PUT includes the displayed `originalArtifactId` and `originalSha256`, plus `expectedVersion` and Markdown. The service refreshes/share-locks the artifact and checks the client base before creating or updating an edition. A first-save mismatch returns 409 with no row created; missing fields return 422. Existing version CAS, permission checks, original-byte integrity, and unverified user text are preserved. The editor retains the draft on a base conflict and does not offer a silent rebase.

## Reproducible PR prerequisite extraction

The original 49-file candidate remains a delta against inherited dirty. A source-only validation tree was assembled outside Git from fixed HEAD, the explicit prerequisites below, and the updated feature delta. The canonical Git/index was not changed. Full W1 hook/client/SSE rewrites, A3 document ingestion, media APIs/playback/hash, W2 workspace navigation, and historical evaluation dirty were excluded. Architecture PR #26 was not applied.

The prerequisite-only assembly contains 38 R2 source/test files and two W1 panel/caller files. Four exact locale lines are also required: `research.loading` and `workspace.retryLoad` in English and Chinese. These keys were identified by an initial isolated TypeScript failure and added to the extraction recipe. The backend boundary tests and migration-head assertion must use their R2 baseline versions in the predecessor commit. Shared i18n and SSoT files are hunk-merged rather than copied wholesale. The SSoT merge appends only the feature section to HEAD.

The 40 prerequisite files are:

- `apps/api/alembic/versions/n8b9c0d1e2f3_add_research_publication_intents.py`
- `packages/backend-persistence/src/citeframe_persistence/models/research_publication_intent.py`
- `packages/backend-contracts/src/citeframe_contracts/__init__.py`
- `apps/api/src/ai_pdf_api/services/storage.py`
- `apps/api/src/ai_pdf_api/services/research/__init__.py`
- `apps/api/src/ai_pdf_api/services/research/research_runs.py`
- `apps/api/src/ai_pdf_api/services/research/research_worker.py`
- `apps/api/src/ai_pdf_api/services/research/research_worker_publication.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_core.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_ports.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_processor.py`
- `apps/worker/src/ai_pdf_worker/research_executor_contracts.py`
- `apps/api/tests/research_worker_test_support.py`
- `apps/api/tests/test_persistence_boundary.py`
- `apps/api/tests/test_research_migration.py`
- `apps/api/tests/fixtures/citeframe-a1b-before-metadata.json`
- `apps/api/tests/test_research_publication_intent_migration.py`
- `apps/api/tests/test_research_worker_evidence_publication.py`
- `apps/api/tests/test_storage_metrics.py`
- `apps/worker/tests/test_research_runtime.py`
- `apps/worker/tests/test_research_single_attempt_dispatcher.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_render.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_saga.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_prepare.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_finalize.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_reconcile.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication_saga_support.py`
- `packages/research-persistence/src/citeframe_research_persistence/snapshot_integrity.py`
- `packages/research-persistence/src/citeframe_research_persistence/commands.py`
- `packages/research-persistence/src/citeframe_research_persistence/state.py`
- `packages/research-persistence/src/citeframe_research_persistence/policy.py`
- `apps/api/src/ai_pdf_api/models/__init__.py`
- `packages/backend-persistence/src/citeframe_persistence/models/__init__.py`
- `apps/api/src/ai_pdf_api/services/research/research_plan_approval.py`
- `apps/api/src/ai_pdf_api/services/research/research_prompt_provenance.py`
- `apps/worker/src/ai_pdf_worker/research_persistence_service.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_handlers.py`
- `packages/research-persistence/src/citeframe_research_persistence/publication.py`
- `apps/web/src/components/research-run-panel.tsx`
- `apps/web/src/components/chat-panel.tsx`

Proposed publication order: controller reviews the extracted R2/minimal-panel prerequisite delta, assigns its scoped predecessor commit/PR, then applies the feature/repair delta on that reviewed base. The current extraction has no remote dependency SHA or approved predecessor PR. No whole-dirty commit is authorized by this recipe. Independent review and real-service gates still apply before merging the feature.

## Evidence

Artifacts live under `C:/Users/baiao/Documents/Codex/2026-09-21/ai-ensemble-fork/citeframe-20260923/repair1`:

- `baseline.json` and `baseline.zip`: before-repair hashes/source snapshot, including the protected #25 spec.
- `assemble_pr_source.py`: repeatable source-only assembly. Run with a new directory name under `repair1`; it refuses to overwrite an existing tree. Add `--predecessor-only` for a prerequisite-only tree.
- `prerequisite-only-manifest.json`: explicit R2/panel source hashes and locale hunks.
- `pr-source-manifest.json`: assembled feature/prerequisite file hashes; original shared dirty is not implicitly included.
- `candidate.zip`, `delta.patch`, and `files.json`: repaired candidate relative to the repair baseline.

Verified dependency runtimes are `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe` and `D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe`; plain `python` is a Store stub. The venvs use editable imports, so isolated checks set `PYTHONPATH` to the assembled API/Worker/three shared package roots and assert all five package `__file__` paths are inside that assembled source tree. Third-party Python dependencies were reused; a fresh Python dependency installation was not tested. Web `pnpm install --offline --frozen-lockfile` reused 462 cached packages, downloading none.

Canonical checkout verification:

- API repair/contract/persistence suite: 241 passed (`api-final.log`); command listed below.
- Worker scoped regression: 83 passed.
- Web unit: 217 passed; TypeScript, lint, and production build passed.
- Editor Playwright: 5 passed on a temporary Next server with mocked API routes. `editor-e2e-final.log` includes first-save base-conflict draft retention. An initial test locator matched the Next route announcer as well as the editor error; the locator was narrowed and the suite rerun.

Isolated source verification (no full W1/A3/media/W2 dirty):

- Prerequisite-only API/persistence/publication/storage: 135 passed (`prerequisite-api.log`).
- Combined API/repair/persistence/migration: 57 passed, 1 skipped (`pr-api-final.log`); the skipped check requires a real PostgreSQL database.
- Combined production SSE bridge + R2 publication/storage: 118 passed (`pr-cross-r2.log`).
- Combined Worker: 83 passed (`pr-worker.log`).
- Combined Web: 140 unit tests passed, TypeScript/lint/production build passed, five mocked-route browser tests passed (`pr-web-test.log`, `pr-tsc-final.log`, `pr-web-lint.log`, `pr-web-build.log`, `pr-editor-e2e.log`). Lower Web test count reflects exclusion of unrelated inherited test files.

Commands from the corresponding source root:

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest apps/api/tests/test_research_autonomy.py apps/api/tests/test_research_policy_sse.py apps/api/tests/test_research_report_edit.py apps/api/tests/test_research_adaptive_service.py apps/api/tests/test_research_adaptive_recovery.py apps/api/tests/test_research_router_basic.py apps/api/tests/test_research_router_plan.py apps/api/tests/test_research_router_recovery.py apps/api/tests/test_research_router_artifacts.py apps/api/tests/test_research_worker_lease_plan.py apps/api/tests/test_research_worker_budget_recovery.py apps/api/tests/test_research_worker_evidence_publication.py apps/api/tests/test_research_v5c_contract.py apps/api/tests/test_research_persistence_boundary.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_migration.py -q -p no:cacheprovider
& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -B -m pytest apps/worker/tests/test_research_adaptive_retrieval.py apps/worker/tests/test_research_v5c_agent_io.py apps/worker/tests/test_research_single_attempt_dispatcher.py apps/worker/tests/test_research_runtime.py apps/worker/tests/test_research_executor.py -q -p no:cacheprovider
pnpm --dir apps/web test
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

For editor browser tests, use cwd `apps/web`, set `PLAYWRIGHT_START_WEB=1` and `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3111` (isolated run: 3112), then run `pnpm exec playwright test e2e/report-edit.spec.ts --workers=1`.

## Remaining gates

- Hubble independent re-review of the repaired frozen candidate.
- Controller approval and publication of the scoped prerequisite PR/base SHA, followed by feature PR integration. A locally assembled source tree is not a published dependency.
- Real PostgreSQL full migration chain, multi-session save/lease/revocation races, process restart, and actual migrated API/object-store/Worker/Web user walkthrough. No listeners were found on local 3000/8000/5432/9000 during the repair check. No shared service was started or migrated.
- Paid provider/retrieval quality acceptance requires explicit runtime and budget approval. Fixture tests do not establish recall improvements.


## Published stack follow-up (2026-09-23)

PR #29 now integrates prerequisite adoption repair a02dbfbb by a normal merge. Final conflict publication accepts policy provenance only for frozen autonomous v3 with null human actor and the recorded policy identifier; historical human provenance remains valid. Four policy adoption tests cover success, forged actor, unknown policy and historical-workflow rejection.

The historical R803 evaluator incorrectly imported the moving production Agent IO version constant after production switched to v2. It now uses the immutable V1_REGISTRY version paired with its existing frozen workflow v2 prompts and schemas. Historical artifacts, fixture text and binding hashes are unchanged. Local isolated evaluation: 101 passed / 1 skipped; this is frozen-evidence evaluation, not real retrieval recall or paid provider evidence.

API CI now installs the actual Web parser dependency for production-serializer-to-parser tests. The two new metadata delta fixtures retain their pinned hashes; each hash check restores its original LF/CRLF serialization across Git checkout platforms. Image/document round-trip tests target their named migration revisions, while whole-chain downgrade still asserts the new adaptive forward-only safety gate. PostgreSQL execution remains a CI/runtime gate; no live local PG results are claimed.

Initial PR CI exposed additional A2 harness clock/storage/version compatibility work. That work is being repaired in the prerequisite branch and must be integrated into this stack before acceptance. No merge approval.
