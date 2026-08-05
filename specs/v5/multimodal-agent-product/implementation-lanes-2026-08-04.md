# V5-A Implementation Lanes: A004-A007

## Status

`v5a-a007-accepted`

A002-A006 and A007 cross-layer regression have passed independent review and are integrated in the current dirty worktree. V5-A is complete for this slice; no commit or push has been performed.

## Wave 1

### A004: Embedding Index Contract

Status: `accepted`

Goal: make the active embedding provider/model/dimensions/version/profile fingerprint a single fail-closed index contract and expose an explicit reindex-required signal without automatic rebuilding.

Ownership:

- `apps/api/src/ai_pdf_api/services/embedding_index.py` (new)
- `apps/api/src/ai_pdf_api/services/retrieval.py`
- `apps/api/src/ai_pdf_api/routers/assets.py` (only reindex/error projection)
- `apps/api/tests/test_embedding_index_contract.py` (new)
- focused extensions to existing embedding/reindex tests only when necessary

Invariants:

- current vectors must match the active embedding contract before retrieval;
- a provider/model/version/dimension/profile mismatch fails closed with a stable code;
- reindex remains an explicit operator action;
- no automatic provider fallback, index-version rewrite, migration, or save-contract change.

Delivery notes:

- Stable internal code: `embedding_index_mismatch` via existing `ModelProviderError` path (Chat maps provider errors; no new HTTP resource).
- Research maps the same code to non-retryable `ResearchError(409)` with preserved reindex message; policy does not rewrite it to `tool_temporarily_unavailable`.
- Empty ready-scope / no current vectors remains ordinary empty retrieval, not mismatch.
- Job/reindex snapshots continue to freeze provider/model/dimensions/version/profile fingerprint fields; present job ownership must match Asset before trusting fingerprint.
- Settings changes do not auto-reindex or rewrite vectors.
- Residual: Chat public HTTP detail still uses the existing provider/ChatError mapping shape (not a dedicated machine-readable code field); A007 may tighten if product requires it.

Audit: Critical review with old/new embedding contract evidence and reverse review for silent empty retrieval.

### A005: Vision and ASR Capability Errors

Goal: make image-caption configuration errors and ASR unavailability explicit at every production entry point.

Ownership:

- `apps/api/src/ai_pdf_api/modalities/image_caption.py`
- `apps/api/src/ai_pdf_api/services/capability_errors.py` (new, if needed)
- `apps/api/src/ai_pdf_api/main.py` (readiness/status only)
- `apps/api/tests/test_vision_asr_capability_errors.py` (new)
- worker image error-code assertions only when required by the same invariant

Invariants:

- missing vision configuration fails before provider HTTP;
- ASR remains unavailable and never falls back;
- existing image-caption snapshot mismatch code remains stable;
- no endpoint, key, or fingerprint preimage is exposed.

Delivery notes:

- production image-caption factory uses `require_configured_vision_profile()` before adapter construction;
- ASR entry helper always raises `capability_unavailable`;
- readiness keeps historical `checks` body; `capability_status()` is the explicit vision/ASR surface;
- OpenAI/DeepSeek generation and embedding provider preflight plus readiness treat `None`, empty, and whitespace-only keys as missing before HTTP;
- worker keeps `image_caption_configuration_mismatch` and asserts required-caption not-configured code.

Audit: Standard/Critical review with no-fallback and secret-boundary checks; independently accepted after focused API/Worker tests, compileall, and diff-check.

## Wave 2

### A006: Web Research Profile Display

Status: `accepted`

Goal: show live server-selected profiles in Settings and frozen provider/model snapshots in Research run detail without adding a selector.

Ownership:

- `apps/web/src/lib/research/types.ts`
- `apps/web/src/lib/research/presentation.ts` and focused tests
- `apps/web/src/components/research-run-panel.tsx`
- research i18n keys only when required
- Settings copy-only changes only if they do not overlap A004

Default path consumes existing API provider snapshot fields. Do not add API or persistence fields unless a separate additive decision is made.

Delivery notes:

- approved runs read only `researchExecution.execution.provider`;
- proposed revisions read only `plan.inputSnapshot.proposedResearchExecution.provider` when no execution snapshot exists;
- incomplete selected snapshots fail closed to unavailable and never fall through to another source or current Workspace values;
- Settings labels current server-selected values separately from frozen Research snapshots;
- residual: Playwright was blocked before page bootstrap by the local OS file-watch limit; unit, TypeScript, lint, and production build gates passed.

Audit: Standard UI/data-flow review accepted after source-precedence rework; frozen run/revision values are not replaced by current environment values.

## Wave 3

### A007: Cross-Layer Regression

Status: `accepted`

Goal: verify Quick Chat, Citation, NoteSource, Research, ingestion/reindex and Web profile display remain within existing contracts.

Ownership:

- focused regression tests, preferably `apps/api/tests/test_v5a_a007_regression.py`
- Web presentation/type tests where required
- `specs/v5/multimodal-agent-product/tasks.md`
- one incremental implementation-progress/SSoT record

A007 starts only after A004-A006 merge and independent review. It verifies existing save semantics; it does not introduce feature behavior.

Delivery notes:

- real Research provider-drift path is covered through `search_frozen_evidence`, including no provider factory call and no erroneous tool reservation;
- Chat embedding mismatch remains the old `502` detail-only HTTP shape, with no half-saved messages;
- newest successful index-producing job, finalize snapshot contract, worker image caption mismatch and Web frozen profile fixtures are covered;
- production-start Web Research E2E passes the five-case spec; dev Turbopack file-watch failure remains a non-blocking environment residual;
- full canonical validation: API `480 passed, 4 skipped`, Worker `238 passed`, Web `113 passed`, TypeScript/lint/build/compileall/diff-check passed; Ruff `not-run` because executable is unavailable.

Audit: independent API/Worker and Web reviews accepted; no API, DB, save-contract, or production behavior changes in A007.

## Merge and Worktree Rules

1. Keep the current worktree as the canonical integration worktree.
2. Create separate worktrees for Wave 1 implementation lanes from the accepted current baseline. The user explicitly approved multiple worktrees for this development wave.
3. A004 and A005 may run in parallel because their production file ownership is disjoint.
4. Each lane has one writer, focused tests, a delivery note, and an independent reviewer.
5. Rework returns to the original lane worker whenever possible.
6. The main controller inspects every diff, resolves conflicts, runs the acceptance matrix, and is the only integrator.
7. No lane may commit or push without explicit user approval.

## Explicit Out of Scope

- user/workspace provider selectors
- provider/profile database tables or migrations
- Citation, NoteSource, Chat, or Research save-contract changes
- ASR adapter implementation
- automatic reindex or silent provider fallback
- R803/M404 quality or user-value claims
