# V5-C Critical Review (2026-08-10)

## Verdict

**ACCEPT for the V5-C engineering/release gate, with explicit Medium residuals.** The terr implementation lane is complete, the production-start Research replay is green, and the independent R800 v6 artifact passes engineering and release gates. This acceptance does not establish model quality or user value. Do not commit or push the worktree from this lane.

## Scope And Baseline

- Repository: `citeframe`
- Review class: `Critical` (persistence, recovery, provider caps, versioned Agent I/O, context packing)
- Starting HEAD: `4f2129c`
- Comparison reference: `origin/main@80d73e3`
- Required product contract: `specs/v5/multimodal-agent-product/decision-2026-08-10-v5c-product-contract.md`
- Existing dirty implementation is owner work and must be preserved.

## Findings

### F1, Medium residual: registry metadata must bind executable implementations

The terr lane corrected current/legacy role binding, dispatches role-specific validators, validates prompt-node mapping, and checks runtime-adapter mapping against the frozen registry. Focused registry tests and the R800 v6 replay pass. The implementation still exposes schema/projection identifiers as registry metadata rather than a separate generated registry object, so future role-specific versions require an explicit mapping test before enablement. This is a follow-up risk, not a blocker for the current frozen v1 registry.

**Required oracle:** for every role and registry version, resolving the role returns the exact schema, validator, prompt binding, adapter, and projection used at runtime; mutating any binding fails closed before provider send.

### F2, High: streaming provider completion (resolved)

The terr lane now requires explicit OpenAI `response.completed` and DeepSeek `message_stop` terminal metadata, and rejects missing/incomplete terminal events. Focused provider tests and the R800 v6 provider timeline cover the fail-closed cases.

**Required oracle:** a stream with missing terminal metadata, `length`/`max_tokens`, or an error raises `research_provider_output_incomplete`/provider error; only an explicit completed terminal event succeeds.

### F3, Standard: compact decoder contract (resolved)

`research_context_policy.py` now adds `research-typed-batches-v1`, nested `fieldPath` batching, a decoder, and non-expansion behavior. Focused tests cover nested round-trip, malformed rows, mutated batch metadata, missing batches, physical reordering, duplicate/missing metadata, and the fitting-context non-expansion invariant.

**Result:** the decoder oracle and mutation/reorder/overflow cases pass; a compact candidate that is larger is discarded and the original payload is sent.

### F4, Standard: frozen top-k exactness (resolved)

`search_frozen_evidence` now rejects `top_k != snapshot.retrieval_top_k` with `research_retrieval_top_k_mismatch`. The shared fixture/callers and a direct mismatch-before-provider/reservation reverse test were aligned during rework. Worker researcher tests record the frozen value, the R800 v6 provider timeline exercises it, and the full API suite is `561 passed`.

**Result:** every Worker researcher call passes the frozen value; API rejects mismatch before provider lookup/reservation; request hash/replay uses that same frozen value; retrieval now receives `limit=snapshot.retrieval_top_k` directly, with no `min(top_k, frozen)` compatibility path. Focused reverse, exact-limit assertion, R800 v6, and full API evidence satisfy this gate.

### F5, Medium residual: legacy reader and legacy role path need a historical-row artifact

The current worktree adds `LegacyResearchPlanArtifactPayload` and a legacy researcher schema that allows empty claims. Focused API/Worker tests load the legacy registry, accept the historical empty-claims shape, reject it for a new current run, and keep current/legacy role bindings separate. The remaining gap is a live historical database-row fixture that records finished artifact bytes/hashes through recovery; it does not block the current release gate because the migration and R800 v6 restore identity checks pass.

**Residual oracle:** add a live pre-V5-C row fixture and record unchanged artifact bytes/hashes through retry/recovery before introducing another registry version.

## Evidence Collected

- `uv run --project apps/api python -m pytest apps/api/tests -q --tb=short`: **561 passed, 1 warning** (final rerun after terr cleanup).
- V5-C API contract/provider/recovery/evidence focused suites: **84 passed, 1 warning**.
- Frozen retrieval evidence/V5-A/capability focused rerun after exact-limit repair: **27 passed, 1 warning**.
- Worker Agent I/O/runtime focused suites: **34 passed**.
- R803 campaign regression focused suite: **55 passed**.
- `uv run --project apps/worker python -m pytest apps/worker/tests -q --tb=short`: **295 passed** (final rerun).
- `uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests` and Worker equivalent: passed.
- `pnpm --dir apps/web test`: **130 passed**.
- `pnpm --dir apps/web exec tsc --noEmit`: passed.
- `git diff --check`: passed.
- Production-start Research Playwright: **5 passed**.
- `docs/evals/artifacts/v5c-migration-roundtrip-20260810/report.json`: online PostgreSQL round-trip passed; final head `h2b3c4d5e6f7`, six Agent I/O columns present.
- `docs/evals/artifacts/v5c-r800-20260810-v6/report.json`: `engineeringGate=pass`, `releaseGatePassed=true`, ten scenarios passed, before/after restore SHA equal, provider timeline and zero-residue cleanup passed.

## Review Matrix

| Area | Status | Evidence / gate |
| --- | --- | --- |
| Goal alignment and non-goals | pass | Scope follows C1/C2/C8; no dynamic DAG/provider selector added |
| User-visible flow/timing | pass | production-start Research `5 passed`; R800 v6 replay and artifact projection pass |
| Architecture boundaries | pass with F1 residual | current/legacy role-specific validator, prompt-node, and runtime-adapter dispatch are wired; future version mapping remains a non-blocking residual |
| Runtime vs persisted state | pass | version fields are persisted in snapshots; no UI money field in current DTO |
| Data contracts/save semantics | pass with F5 residual | strict/legacy focused recovery tests, online migration, and R800 restore identity pass; live historical-row bytes/hash artifact remains follow-up |
| Provider/profile/fingerprint | pass | frozen provider fingerprint/cap and sync/stream completion proof pass in focused tests and R800 v6 |
| Permissions/scope/idempotency | pass | R800 v6 covers workspace membership, cancel, retry, lease reclaim, conflict and unique-final invariants |
| Error/retry/recovery | pass | stable codes plus R800 v6 transient retry, lease reclaim, cancel and recovery pass |
| Context/compact provenance | pass | nested lossless decode, malformed/mutated metadata, reorder/missing batch and non-expansion tests pass |
| Frozen retrieval | pass | direct mismatch-before-provider test, focused evidence/V5-A/capability coverage within the `84 passed` API focused suites, and API `561 passed` |
| Unit/integration/browser evidence | pass | API `561 passed`; Worker `295 passed`; Web `130 passed` and TypeScript/build passed; production-start Research `5 passed` |
| Backup/restore | pass | R800 v6 PostgreSQL/MinIO restore identity and zero-residue evidence pass |
| Production registry enablement | pass for frozen v1 | current registry is enabled; legacy registry is explicit and not approved for new runs |

## Phased Acceptance Plan

1. **Implementation closeout (terr):** complete. Registry/provider/compact/legacy/top-k changes and focused regressions remain in the dirty worktree; no commit or push was made.
2. **Focused semantic gates:** complete; the role, provider, compact, legacy and frozen-top-k oracles pass.
3. **Full regression:** complete; API, Worker, Web unit/type/build, production-start Research Playwright, R800 v6, online migration, compileall and `git diff --check` pass.
4. **Acceptance writeback:** complete in this review, the V5-C acceptance record, verification matrix, implementation progress and Workbench checkpoint. V5-D is the next implementation slice; no commit/push is implied.

## Residual Risks

- Registry string-key metadata can drift from concrete implementations when a future role/version is added; require an executable mapping test before enabling that version (F1, Medium).
- No live pre-V5-C database row artifact currently proves unchanged finished-artifact bytes/hashes through legacy retry/recovery; add this before introducing another registry version (F5, Medium).
- Scripted R800 provider proves engineering plumbing only. R803 model quality and M404 user value remain `not_evaluable`, and the product remains `internal_preview`.
- `alembic upgrade head --sql` remains blocked by the existing offline-incompatible migration `e6a7b8c9d0f1`; online migration is green and this is not a V5-C release blocker.


## F5 residual closeout (2026-08-13)

Status: **closed for current frozen registry (no new registry version)**.

- Test: `test_f5_historical_final_artifact_bytes_survive_retry_and_recovery`
- Artifact: `docs/evals/artifacts/v5c-f5-historical-artifact-20260813/`
- Paid provider calls: 0
- Proves finished final_report bytes/sha/byte_size and content etag are unchanged
  across manual retry requeue under legacy agent I/O snapshot versions.

F1 remains Medium residual only for **future** registry versions (current v1 has
Worker executable binding coverage from V5-D).
