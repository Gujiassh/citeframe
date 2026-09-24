# Issue 36 — Workspace third-party model configuration

- Issue: https://github.com/Gujiassh/citeframe/issues/36
- Feature branch: `work/issue36-model-config`
- Implementation base: upload branch head `ffa94b0994b5e99eab7fb37ca2e4ae6f658b0a83`; upload PR #37 subsequently merged as `7bfc044e6933272b9ad4a7c8d347f869ba91daf4`.
- Risk: Critical (encrypted persistence, permissions, network destination control, job/run snapshot semantics).
- Web implementation: `bb0a2c7f08f0bddf86ecc6455fa8937b0fff5687`; [Web delivery ledger](issue36-web-settings.md).
- Stable operational contract: [workspace model configuration](../../../docs/ssot/workspace-model-configuration.md).

## Accepted outcome and boundaries

Owner-managed webpage configuration of third-party URL, key and model for each workspace. Generation supports both OpenAI Responses and Chat Completions for Quick Answer and Research; embedding is independent and fixed to the database's 1024 dimensions. Keys are encrypted server-side and write-only. Existing Vision/ASR remains unchanged. The controller owns the GitHub issue, real UI acceptance and merge; implementation is submitted as one combined PR. Upload multi-select queue was delivered in PR #37.

## Semantic acceptance oracles

1. Two workspaces use their own base, key and model in actual provider requests; server keys never accompany a workspace URL.
2. Reload/restart preserves configuration and encrypted-key usability without exposing credentials in responses, validation errors or logs.
3. Unauthorized readers/writers fail; atomic saves, revision conflicts and reset tombstones prevent lost writes or stale-form ABA.
4. Public/private destination policy applies at the connected socket, with original TLS identity and no redirect/proxy escape.
5. Both generation protocols produce usable Quick Answer and Research output with the chosen embedding configuration.
6. An already-authorized captured Research call may complete after a settings edit; later reservations fail drift. No network lock or snapshot rewriting.
7. Embedding mismatch is visible and recoverable with per-asset reindex. Failed reindex preserves complete old vectors and a ready asset while retrieval still enforces the selected contract.
8. Setup UI is reachable without global provider credentials; full provider readiness diagnostics keep their prior meaning.

## Implemented backend scope

Additive shared persistence model/migration, owner settings GET/PATCH and sanitized validation; AES-GCM with persistent operator key; immutable one-query connection pair resolution; socket-pinned transport; Chat Completions adapter and exact-base provider constructors; explicit Chat/Research/Worker/ingestion/retrieval propagation; profile/index contract checks and legacy-default-only compatibility; workspace row locking at Research authorization; per-ready-asset reindex projection; application readiness and deployment environment/dependencies.

## Verification recorded before runtime-candidate freeze

- Narrow API health, index contract, transport, settings and protocol suite: **88 passed** (before one additional Settings repr regression was added).
- Dedicated PostgreSQL concurrency suite: **4 passed**, using only `citeframe_issue36_test`; full migration applied to that disposable DB. Tests prove one-snapshot pair read, conflicting writer locks, save-before-reserve drift, and reserve-before-save captured-call semantics with observed PostgreSQL lock waits.
- Earlier broad API excluding historical differential and persistence gates: **918 passed, 3 skipped**, with the sole outdated migration-head expectation subsequently corrected. Must rerun stable source gates after commit.
- Earlier Worker suite: **462 passed**; dirty-source proof gates and an orphan historical bytecode artifact still require a frozen rerun.
- Web: **175 tests**, typecheck, lint and build passed (see Web ledger).
- Real socket transport tests include local redirects/proxy rejection, DNS rebinding numeric dial, valid TLS hostname/SNI, wrong certificate rejection, deadlines, byte limits and compressed-body rejection.
- Historical schema snapshots remain unchanged; the additive metadata delta is explicit in `workspace-model-config-metadata-delta-20260924.json`.
- Docker/Compose is unavailable on this machine. Reviewer checked Compose structure and authoritative compose-go interpolation behavior; actual `docker compose config` is **not executed**.

## Outstanding acceptance at candidate freeze

Controller-owned real visible UI walkthrough: owner save/reload/restart; two-workspace routing; both protocols in Quick Answer/Research; upload/reindex and clear failure/recovery. Synthetic fixture output proves protocol/business-flow plumbing only. Real provider/model quality remains outside this fixture evidence. Independent Critical review and frozen broad/source-bound tests remain required before PR approval/merge.

## Runtime-found planner correction

The visible UI walkthrough reached ingestion and Responses Quick Answer, then Research failed before its first HTTP request. The planning DTO included `retrievalTopK`, but Worker planning conversion omitted it and `ApprovedResearchExecution` defaulted to 0. The new immutable provider-fingerprint check correctly rejected this incomplete runtime snapshot. Worker now carries the frozen value through both conversion steps. Two integration regressions create workspace overrides, run actual planner/ledger/provider adapters with frozen topK 9 for Responses and Chat Completions, and verify the selected URL/key/model, succeeded provider ledger and queued approved run. Only network and object storage are fixtures. Focused Worker runtime suite: **33 passed**. Existing user data and failed run snapshots were not changed.

Frozen pre-correction full API suite: **977 passed, 7 skipped** (`uv run --project apps/api pytest apps/api/tests -q --disable-warnings`). Dedicated PostgreSQL rerun: **4 passed**. Worker pre-correction: **464 passed**, with only an orphan historical `r803*.pyc` namespace failure; verified orphan bytecode removed and architecture boundary rerun **4 passed**. Full Worker will be rerun on corrected committed source.

## Stable failure recovery

After the planner propagation fix, the frozen full Worker suite passed **467 tests**. A follow-up failure audit found that the newly added local drift guard's `ResearchPortError` lost its specific reason at failure normalization. The guard now raises the existing code-bearing `ModelProviderError`; Research's safe-code map preserves config drift, unavailable encryption/secret, and denied/invalid endpoint reasons as nonretryable failures. Unknown strings remain generic. Both protocol integration cases now additionally edit configuration after plan freeze and verify: zero provider HTTP calls, failed run with `research_provider_config_drift`, no provider ledger reservation. Focused integration: **8 passed**; settings/safe-error suite: **19 passed**. Controller reported a completed real Responses Research report after the planner fix; live Chat Research and combined UI acceptance remain controller-owned.

## Final controller-visible acceptance and frozen gates (2026-09-24)

This section supersedes the candidate-freeze pending runtime items above. The controller walked the owner UI in the actual local app and cross-checked persisted state and fixture traffic. Backend source was frozen at `2b9812c7abd8c15a6bcd1172df85ab5cc73c5957`; final Web recovery copy is `ef585e61d1443df878ff82d680eb5b383370b5b0`.

- **Configuration and isolation — passed:** owner saved generation and separate embedding, refreshed and saw persisted values with blank key fields. Two workspaces used distinct generation/embedding prefixes, models and fixture credentials. The database stored encrypted envelopes; API responses omitted plaintext and ciphertext. Runtime log scans found zero synthetic key-string matches.
- **Permissions and conflicts — passed:** owner stale-form save returned 409 and reload restored editing. Separate synthetic member GET/PATCH returned 403 without changing revision; an outsider workspace returned 404. Member checks were API-level; the owner flow was walked visibly.
- **Protocol/business flow — passed:** Responses and Chat Completions each produced Quick Answer with citations and completed Research reports. A report citation opened the source document with its cited block highlighted. Responses Research example run: `058a137b-d16f-4975-a065-fc6e154e9e88`.
- **Failure/recovery — passed:** unapproved private origin rejected; incorrect provider key produced visible HTTP 401 failure and correcting it recovered generation. Changing embedding marked both test assets for reindex. After prestream rejection, the question and a settings/reindex action stayed visible; following the action, reindexing both assets and resubmitting the preserved question produced a cited answer. Existing failed ingestion recovered through Retry Processing; no original data was deleted.
- **Restart and frozen-run boundary — passed:** API and Worker restarted from the persistent profile without key regeneration. A queued run frozen before an owner protocol edit failed with `research_provider_config_drift` and zero new fixture calls (hit count stayed 32). A fresh post-restart Research run completed a report using the saved encrypted keys. Application readiness returned 200; full provider readiness remained 503 for unavailable server-default models.
- **Backend full commands — passed:** `uv run --project apps/api pytest apps/api/tests -q --disable-warnings --tb=short`: **982 passed, 7 skipped**. `uv run --project apps/worker pytest apps/worker/tests -q --disable-warnings --tb=short`: **469 passed**. The four new opt-in PostgreSQL cases passed separately on the guarded disposable DB; the other three skips are existing optional tests.
- **Web gates — passed:** **181 tests**, including 12 focused Research presentation cases; TypeScript, ESLint and diff checks passed. Production build passed on the preceding recovery commit; the final localized-copy delta received tests/typecheck/lint (see Web ledger).
- **Independent review:** foundation, planner propagation, Web prestream recovery and safe failure-code deltas received separately scoped Critical reviews with independent focused reruns. Final localized-copy review and PR/CI status are tracked by the controller.

Reproduce the user path with two owner workspaces and the loopback fixture: configure independent capabilities; upload and cite a document; run Research once per generation protocol; change embedding, follow reindex recovery and retry; queue a run, change generation before Worker resumes, observe drift rejection and start a new run. The fixture confirms engineering behavior only. Third-party availability/model quality, backup restoration, and actual Docker Compose execution are not established by this evidence. Local pre-migration backup TOC was checked; restoration was not exercised.

## PR #39 CI dependency-lock repair

Original head `150d3d1` failed evaluation/API lock checks because the evaluation consumer lock had not received API cryptography and transport dependency metadata. The r800 deployment evidence for run `35978894818` independently showed exactly ` M tools/evaluation/uv.lock` in both candidate source-status artifacts: `uv run` updated the stale lock before the existing clean-source assertion. The guard remains unchanged.

Regenerated only `tools/evaluation/uv.lock`. Parsed comparison confirms no existing package version changes or removals; added cryptography `50.0.1`, matching API and Worker locks, propagated direct dependency metadata, and accepted uv's root-package/dev formatting normalization. All three tracked lock checks passed. `uv run --project tools/evaluation --frozen pytest tools/evaluation/tests -q --disable-warnings --tb=short`: **157 passed, 1 skipped** in a fresh evaluation virtualenv. Runtime source, migrations and other dependency versions were unchanged. New CI runs on the pushed repair remain the deployment acceptance gate; the prior failed jobs are not manually rerun.
