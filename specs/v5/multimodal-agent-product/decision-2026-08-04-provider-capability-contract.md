# V5-A Capability Registry/Profile Contract

## Status

`approved-for-v5a-implementation`

This document freezes the smallest V5-A contract for a server-side capability registry and provider profile resolver. It does not authorize implementation of persistence, API, or save-contract changes.

## Current Facts

- Generation currently has two adapters: OpenAI Responses and DeepSeek Anthropic Messages.
- Embedding currently has OpenAI and Ollama adapters with provider/model/dimensions/version checks.
- Image caption is an OpenAI-only adapter with an ingestion-job configuration snapshot.
- ASR has no production adapter and must remain unavailable until a separate modality/provider slice is approved.
- Quick Chat resolves providers from server settings. It does not accept a user-supplied provider.
- Research currently freezes one generation provider/model and one embedding provider/model per plan revision and execution snapshot. Provider reservations must match the frozen provider, model, and fingerprint.
- Existing persisted fields and saved Citation, NoteSource, Chat, and Research artifact semantics are historical contracts.

## Proposed Contract

### 1. Registry Scope

The registry is a server-side catalogue of capability adapters. It is not a user plugin system and it does not load arbitrary Python modules, URLs, or model names at runtime.

The first registry contains these capability families:

| Capability | Current profiles | Availability |
| --- | --- | --- |
| `generation` | `openai` Responses, `deepseek` Anthropic Messages | enabled when the selected server profile has its required secret |
| `embedding` | `openai`, `ollama` | enabled when the selected server profile is configured and its dimensions/version match the current index contract |
| `vision` | existing image-caption OpenAI adapter | enabled only for the existing image-caption ingestion path |
| `asr` | none | unavailable; no silent fallback |

`vision` is the capability name for the existing image-caption operation. It does not claim general image/video understanding beyond that adapter.

There is exactly one active server-selected profile per capability in this slice. A server administrator selects it through environment/configuration. Workspace members cannot select providers, endpoints, keys, or arbitrary models yet.

### 2. Profile Identity

A resolved profile has the following internal fields:

- `capability`: `generation | embedding | vision | asr`
- `provider`: registered adapter key
- `model`: provider model identifier
- `adapterVersion`: versioned adapter/protocol contract, for example `generation-openai-responses-v1`
- `modelVersion`: optional provider-declared or deployment-configured version; absent when the provider exposes no stable version separate from the model identifier
- capability-specific limits and format parameters, such as timeout, output token limit, embedding dimensions/version, image detail, or supported input parts
- `pricingVersion`: the bounded local pricing-book version when cost accounting applies
- `dataBoundaryPolicyVersion`: the policy version used to decide where data may be sent
- `configured`: whether the selected profile has the required server-side secret and valid local configuration
- `configFingerprint`: SHA-256 over the canonical non-secret profile configuration

The durable profile identity for the first implementation remains the existing `provider + model` fields. `adapterVersion`, `modelVersion`, and non-secret parameters are included in the fingerprint and are not added as new database columns in this slice. This preserves the existing R000 storage shape while making the fingerprint meaningful for adapter/config drift.

### 3. Fingerprint Boundary

The canonical fingerprint input is an allowlisted object containing:

- capability, provider, model, adapterVersion, and modelVersion
- normalized API base identifier, without credentials or request headers
- capability-specific non-secret limits and format parameters
- embedding dimensions, embedding version, and a hash of the query instruction when applicable
- pricingVersion and dataBoundaryPolicyVersion

The fingerprint must not contain:

- API keys, bearer tokens, authorization headers, cookies, or secret values
- request bodies, source content, retrieved text, Evidence, user prompts, or hidden reasoning
- raw provider responses or arbitrary environment variables

The API and Web surfaces expose provider/model and bounded capability metadata only. They never expose the endpoint identifier or fingerprint preimage. Logs use flat provider/capability/outcome fields and may expose the final SHA-256 only where an existing audit contract already requires it.

The current `provider_config_fingerprint` field continues to mean the execution-profile fingerprint: a canonical hash of the selected generation and embedding capability profiles plus retrieval strategy, retrieval top-k, and data-boundary policy. The implementation may introduce internal per-capability fingerprints, but it must not rename or reinterpret the existing persisted field without a separate migration decision.

### 4. Resolution and Freeze Timing

- Quick Chat resolves the active embedding and generation profiles before retrieval or generation. It fails before a provider request when a required capability is unavailable or misconfigured. It never falls back to another profile.
- An ingestion job snapshots the selected embedding and modality profiles when the job is created. Worker execution must compare its actual resolved profile to that snapshot before producing representations or vectors.
- Research planning resolves the active generation and embedding profiles when a plan revision is created. The existing revision fields and `proposed_provider_config_fingerprint` remain the planning snapshot.
- Research approval revalidates that the selected profiles and current execution policy still match the revision. The approved execution snapshot is immutable.
- Research workers execute only from the approved snapshot. They must compare the worker-resolved profile's actual fingerprint with the frozen fingerprint before reserving or sending a provider call. The worker must not overwrite the frozen fingerprint with the current environment value.
- A provider/model change never mutates an existing plan, execution snapshot, Citation, NoteSource, Chat message, Research artifact, or ingestion result.

### 5. Drift and Failure Semantics

- Missing secret, unsupported capability, invalid profile, or profile fingerprint mismatch is a fail-closed configuration failure.
- A pending Research plan whose server profile changed after creation cannot be approved; the user must create a new plan revision.
- An approved Research execution does not re-resolve to a different provider. If the exact frozen profile cannot be instantiated, the run enters the existing bounded provider/configuration failure path and does not send a request with a different profile.
- An ingestion job with a changed embedding/caption profile fails the job with an explicit configuration-mismatch error and preserves the existing generation/result rollback semantics.
- No automatic fallback, first-available selection, model-name inference, endpoint probing, or silent reindex is allowed.
- Historical terminal records remain readable. They are not rehashed or rewritten after a registry or adapter-version change.

### 6. API and Persistence Boundary

The first implementation is intentionally server-side:

- no new provider-selection field in Chat, Research creation, Workspace settings, Citation, NoteSource, or Asset APIs;
- no user-controlled model/provider routing;
- no new provider/profile database table;
- no migration for profile IDs or version columns;
- keep existing `generationProvider`, `generationModel`, embedding fields, and `providerConfigFingerprint` projections;
- add only internal typed registry/profile code, resolver tests, configuration-drift tests, and bounded health/status metadata if needed for existing response fields.

A later user-visible profile selector, explicit profile/version snapshot fields, workspace-scoped model policy, or multiple capabilities in one Run requires a new contract and explicit approval because it changes API, authorization, budget, snapshot, and migration semantics.

## Acceptance Invariants

1. The same server configuration resolves to deterministic profile metadata and the same fingerprint.
2. Changing a secret, endpoint, model, adapter version, embedding dimension/version, or relevant capability limit changes the fingerprint without exposing the changed value.
3. A changed profile cannot satisfy an old Research reservation or ingestion-job snapshot.
4. A missing capability never selects another provider implicitly.
5. Existing provider/model/fingerprint fields and historical Citation, NoteSource, Chat, Research, and deletion/recovery behavior remain unchanged.
6. OpenAI and DeepSeek generation can be selected by server configuration in separate runs, while each run still uses one frozen generation provider/model profile.
7. The registry reports ASR as unavailable rather than pretending it is configured.

## Approval Required

Approve or reject this contract before implementation, specifically:

1. one active server-selected profile per capability, with no user/workspace selector in V5-A;
2. reuse of current persistence/API fields and no migration in the first registry slice;
3. fingerprint inclusion of normalized non-secret endpoint/configuration and adapter version, with secrets excluded;
4. fail-closed drift and no fallback;
5. treating the existing image-caption operation as the initial `vision` capability and leaving ASR unavailable.

## Implementation Boundary After Approval

The first code slice may add a typed registry/profile module, adapter metadata, canonical fingerprinting, resolver integration at existing provider factories, and focused tests. It may not add user-selected routing, change Run schema/save payloads, create migrations, or alter Citation/NoteSource semantics without a separate approval.


## Implementation Record

- 2026-08-04: V5-A capability registry/profile slice implemented server-side only.
- Added `apps/api/src/ai_pdf_api/services/capabilities.py` and wired Research/ingestion/provider factories.
- No user/workspace provider selector, no DB migration, no Citation/NoteSource/Chat/Research save-payload meaning change.
- Focused verification: `apps/api/tests/test_capabilities.py` plus existing provider/ingestion/research fixture patches.


## Fingerprint Cutover

- New Research plan revisions write `citeframe-execution-profile-v2` fingerprints that include generation/embedding capability profile hashes and optional retrieval top-k.
- Historical pending revisions and approved execution snapshots keep their frozen `provider_config_fingerprint` values; they are never rewritten.
- Approval and reservation use bounded dual-read: a frozen fingerprint may match either the current v2 fingerprint or the legacy preimage when provider/model/embedding/retrieval/data-boundary fields still match. Endpoint/secret/adapter/limit drift still fails closed for pure v2 snapshots.
- Ingestion jobs created after this slice freeze `embeddingProfileFingerprint` / `imageCaptionProfileFingerprint`; when those fields are present the worker requires a non-empty actual fingerprint match. Legacy snapshots without those fields keep field-level compatibility only.
- Secret markers use `AI_PDF_CAPABILITY_FINGERPRINT_PEPPER`, not `AI_PDF_API_INTERNAL_TOKEN`.
- DeepSeek Anthropic generation maps Chat system messages to the top-level `system` field, maps supported text/image parts, and rejects unsupported parts before HTTP.
- The accepted slice has API `431 passed, 4 skipped`, Worker `236 passed`, compileall and diff check passing; Ruff was not run because the executable is unavailable in the project environment.
- Independent review verdict: `ACCEPT`. Residual test gap: the Research evidence drift test should call the real `search_frozen_evidence` path directly in A007 rather than reimplementing its gate inline.

## Next Lane Plan

The next implementation wave is recorded in [`implementation-lanes-2026-08-04.md`](implementation-lanes-2026-08-04.md). A004 and A005 are parallel-safe with exclusive API ownership; A006 consumes existing frozen Research provider snapshots in Web; A007 is serial regression closeout.
