# Issue #36 — Web model settings and explicit reindex

Date: 2026-09-24
Issue: https://github.com/Gujiassh/citeframe/issues/36
Branch base: `ffa94b0994b5e99eab7fb37ca2e4ae6f658b0a83`.
Status: implementation and deterministic Web checks; controller browser acceptance and independent security review pending.

## UI and API boundary

- Owners receive separate Generation and Embedding forms inside existing workspace settings. Nonowners keep effective-model metadata and the existing-member reindex capability; they do not request owner model-settings.
- Authenticated Next BFF GET/PATCH `/api/workspaces/{id}/model-settings` forwards to the owner-only API with session/internal headers and no cache. No direct browser-to-provider request or key storage is introduced.
- Forms use the frozen backend DTO in `apps/api/src/ai_pdf_api/schemas/model_settings.py`. Generation explicitly selects OpenAI Responses or Chat Completions; embedding uses OpenAI Embeddings with the fixed 1024-dimensional contract. Inherited server protocols remain visible as metadata.
- Each save/reset uses the server-returned capability revision. The client does not increment or reset revisions itself. A conflict preserves the error and requires configuration reload before saving again.
- Password fields initialize empty. An omitted key preserves an existing workspace key only for the same base URL; initial override, missing key, and endpoint change require explicit input. Keys remain in component/request memory only; successful save or unmount releases the field value. Neither browser storage nor diagnostic logging is used.
- Reset is explicit, confirms removal of the saved key, and sends only action/revision. Missing encryption configuration disables writes and explains the required administrator setup. Secret/endpoint/key errors provide recovery guidance without exposing credentials.
- Existing prompt, retrievalTopK and chunkSize save semantics are unchanged. Successful model save refreshes the same workspace-summary API for effective provider/model metadata. An aborted component cannot apply a delayed summary refresh.

## Reindex lifecycle

- A dedicated per-asset section exposes explicit Reindex actions to existing accessible members. There is no automatic reindex on configuration save and no new owner restriction on the backend route.
- Authenticated POST BFF `/api/workspaces/{id}/assets/{assetId}/reindex` preserves the existing no-body API and `{asset, job}` response.
- The root workspace provider owns an independent job tracker. It records the returned `job.id` and polls `/api/workspaces/{id}/jobs/{jobId}` even when Asset.status is already ready. Workspace navigation or closing settings does not discard this tracker.
- Queued/running jobs suppress duplicate local submission. A polling failure offers Refresh job status using the same ID rather than resubmitting a job. Terminal failure displays the job error; explicit Reindex remains available afterward.
- Completed jobs trigger current-workspace Asset list and owner model-settings refresh, including the backend-derived reindex-required IDs. Workspace/asset/job identifiers are checked before accepting a polling response. Logout/auth-owner changes/provider unmount abort requests and release local state.
- Local job tracking does not survive a full page reload; persisted job execution remains server-owned. A lost submission response cannot be reconciled automatically through the existing API without its job ID. No resumption or rollback promise is made.
- Index-data replacement and mismatch checks remain backend-owned. Reindex failure must preserve stored data; this Web lane displays status and does not manipulate index contents.

## Module boundaries

- `lib/model-settings`: DTO, request/error handling, form-command rules and hook lifetime.
- `components/model-settings`: capability form, settings composition and per-asset reindex display.
- `lib/assets/reindex-tracker.ts`: explicit submission, returned-job polling and lifecycle isolation.
- `use-workspaces`: generic summary refresh only. `use-assets`: a refresh token reuses existing authoritative list hydration; upload response-order guards remain unchanged.
- No migrations, deployment keys, backend code, model HTTP transport or provider execution were changed by the Web lane.

## Verification

- `pnpm --filter @citeframe/web test`: 175 passing unit/render tests, including 14 added model-settings/reindex cases.
- `pnpm --filter @citeframe/web exec tsc --noEmit`: passed.
- `pnpm lint:web`: passed.
- `pnpm build:web`: passed after retrying a transient Google Fonts/Geist network-fetch failure; no font/source workaround added.
- Coverage: password initialization, key omission/replacement, endpoint key requirements, server revision reuse, protocol/dimension controls, request body/cache policy, conflict handling, late response abort, ready-asset job-ID polling, failed-poll recovery without duplicate POST, terminal job error, workspace mismatch rejection and logout cleanup.

## Controller acceptance still required

1. Owner save/reload for both generation protocols and separate embedding configuration; clear/write-only password behavior; same-endpoint key retention; endpoint change requiring a new key.
2. Nonowner access denial to GET/PATCH and visible existing-member reindex action.
3. Conflicting tabs, reset/override ABA revisions, unavailable encryption key, denied endpoint, and safe recovery.
4. Workspace switch or logout during reads/saves; no cross-workspace metadata or secret field carryover.
5. Explicit reindex of an already-ready Asset: queued/running/terminal job progress, status polling after settings closes, poll failure recovery without duplicate job, backend mismatch recovery after success, and stored-data preservation on failure.
6. Combined backend verification covers encryption at rest, API/Worker restart, actual Quick Answer/Research protocol paths, embedding query/ingestion and provider-security boundaries. Web unit/render evidence does not establish these runtime outcomes or real-provider quality.

## Prestream Quick Answer failure recovery

Controller browser acceptance at `5c2954a` reproduced: after an embedding profile change, Quick Answer was rejected before streaming with an index-mismatch error; successful thread hydration then removed optimistic rows, while the composer had already cleared the question.

The Web recovery keeps prestream rejection separately from persisted thread messages, scoped by authenticated user, workspace and thread. The composer clears only after request acceptance. A rejected normal question remains an in-memory retry draft across opening settings and returning to chat. The visible error includes a Model settings / Reindex action. Accepted-stream failure handling and the existing boolean send contract remain unchanged; rejected edits do not become new-question drafts. Logout clears stored failures, and identity/hydration lifetime changes reject delayed failure updates.

Focused regression covers the real `startChatStream` HTTP rejection parser, retained draft/error, accepted retry clearing, scope separation and rejected-edit semantics. This scoped fix still requires the controller's repeat of the embedding-change → rejected question → settings/reindex → retry browser flow.

Rework checks: `pnpm --filter @citeframe/web test` 179 passed; focused `src/lib/chat/submission.test.ts` 4 passed; TypeScript, ESLint, production build and scoped diff checks passed.
