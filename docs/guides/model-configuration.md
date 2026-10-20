# Workspace model configuration

## Configure models

### Operator preparation

1. Generate one encryption key as standard base64 of 32 cryptographically random bytes. Set the same persistent `AI_PDF_MODEL_CONFIG_ENCRYPTION_KEY` for API and Worker, keep it outside Git, and back it up separately from the database. In a [local preview profile](local-environment.md), set it in `infra/env/preview.local.env`; for [Compose deployment](../deployment/README.md), set it in `infra/docker/.env.deploy`, whose shared environment supplies both services. For host processes launched directly, supply it in both process environments. Restart/recreate the affected processes after changing their environment.
2. Use a public HTTPS model endpoint by default. Before an owner can use a private HTTP(S) endpoint, configure the matching `AI_PDF_MODEL_PRIVATE_ORIGINS` origin/CIDR mapping in both services. The exact-origin and network restrictions are described below. Missing or invalid encryption configuration disables the form's save controls.

### Workspace owner

1. Open the workspace as its owner, then select **Settings > Workspace > Model configuration**. In the Chinese interface these labels are **配置 > 工作区 > 模型配置**.
2. Configure **Generation** and **Embedding · 1024 dimensions** independently. For each capability, choose **Protocol** and enter **API Base URL**, **Model**, and **API Key**. Enter the exact API base, including `/v1` if required by the provider; Citeframe appends only the selected protocol's endpoint path. New or changed endpoint bases require an explicit key. A blank key retains an existing workspace key only for the same canonical base.
3. Select that capability's **Save**. Confirm **Saved**, or read the displayed error and correct it before retrying. Saving configuration does not test the provider connection or establish model output quality. After a revision conflict, select **Reload configuration**, reapply the intended edits to the current configuration, and save again.
4. After changing embedding configuration, use **Reindex assets** and select **Reindex** for each affected asset marked as requiring it. Follow the job status until **Index updated**, or resolve a displayed **Reindex failed** error. Changing settings does not automatically rebuild existing vectors; the previous complete index is retained until replacement succeeds, and retrieval requires an index matching the selected configuration.

## Effective configuration

Workspace owners manage generation and embedding separately at `GET/PATCH /v1/workspaces/{workspaceId}/model-settings`. Each capability inherits the complete server default or overrides the complete connection. Overrides never borrow a server API key. Generation overrides support `openai_responses` and `openai_chat_completions`; embedding overrides support `openai_embeddings` with exactly 1024 finite numeric dimensions. Server-inherited DeepSeek and Ollama behavior remains available. Vision and ASR remain server configured.

The entered API base is exact: `/responses`, `/chat/completions`, or `/embeddings` is appended without inserting `/v1`. Provider requests carry the selected model and workspace key. Generation and embedding are read in one database snapshot and passed explicitly as immutable connections to Chat, Research, ingestion, and retrieval; request handling does not mutate process-global settings.

## Save and secrets

PATCH accepts either or both capability objects. Save fields are `action: save`, `expectedRevision`, `protocol`, `baseUrl`, `model`, and optional `apiKey`. Omit a key only to retain the existing workspace key at the same canonical base. New or changed bases require an explicit nonblank key. Reset uses `action: reset` and `expectedRevision`.

Saving both capabilities is atomic. A stale revision returns `model_settings_conflict`; reset retains a durable monotonically increasing revision so an old form cannot overwrite a later reset. Owner authorization uses existing workspace membership boundaries. Responses expose only `apiKeyConfigured`, never key plaintext or ciphertext. Inherited server bases are not returned. Invalid request bodies and provider errors are sanitized.

The `workspace_model_configs` table stores AES-GCM ciphertext with a random nonce and workspace/capability authenticated context. Operators must provision the same persistent `AI_PDF_MODEL_CONFIG_ENCRYPTION_KEY` to API and Worker: standard base64 encoding of 32 cryptographically random bytes. There is no development fallback or generated-on-start key. Missing/invalid key disables saving overrides; unreadable stored keys fail closed. Back up this secret separately with the database, restrict access, and retain it across restarts. Changing it without re-encrypting stored rows makes their keys unreadable. Automated key rotation is not provided.

Migration `s3a4b5c6d7e8` is additive over `r2f3a4b5c6d7`. Its downgrade refuses silent destruction of saved configuration. Deployment exports include cryptography, httpcore/httpx, and certifi. When API dependencies change, update and check all three consumers: `apps/api/uv.lock`, `apps/worker/uv.lock`, and `tools/evaluation/uv.lock`. Run `uv lock --project <project> --check` for each before submitting.

## Network boundary

Workspace destinations default to public HTTPS. Private HTTP(S) requires operator-controlled `AI_PDF_MODEL_PRIVATE_ORIGINS`, a JSON mapping of exact canonical origins including ports to permitted CIDRs, for example `{"http://127.0.0.1:18136":["127.0.0.1/32"]}` for a local test server. This permission is independent of owner configuration. Metadata endpoints remain denied even when an allowlist is supplied.

URL userinfo, query, fragments, ambiguous numeric hosts and invalid forms are rejected. Every connection validates all DNS answers and dials a validated numeric IP; TLS retains the original hostname and certificate verification. Connection peer checks, bounded DNS workers/admission, no redirects, no environment proxies, and an explicit certifi trust store apply to overrides. Responses have a 16 MiB wire limit and read/deadline limits; only identity content encoding is accepted. These controls apply to workspace overrides; inherited deployment endpoints retain their established adapter behavior.

## Jobs, Research, and indexes

Ingestion jobs snapshot the selected embedding fingerprint. Worker resolution checks it before embedding, and stored index contracts include provider/model/version/dimensions and configuration fingerprint. Legacy jobs/indexes without fingerprint compatibility are accepted only under inherited defaults. Overrides require explicit reindexing. A model returning another dimension or nonfinite values fails before vectors are persisted.

Changing embedding settings never automatically deletes or rewrites vectors. Settings expose `reindexRequired` and ready asset IDs requiring reindex. The existing per-asset reindex endpoint returns `{asset, job}`; UI tracks the returned job because the preserved ready asset can remain ready during replacement. Failed replacement preserves a complete saved index; retrieval separately checks whether that index matches the currently selected connection. Reverting to the original matching configuration can restore access to the preserved index.

Research freezes configuration fingerprints. A short workspace row lock serializes configuration edits and call authorization; authorization becomes effective at reservation commit. A captured call authorized before a save may still send and finish with its old connection after that save. Later reservations fail on drift. Evidence retrieval takes the same configuration lock through its tool-call reservation. No network call holds the workspace lock, and frozen run snapshots are never rewritten to disguise drift.

## Startup checks

`/health/application-ready` checks database, enabled modality catalog, object storage, and model configuration schema. Compose uses it so deployments without global keys can open settings. `/health/ready` retains full global provider diagnostics and does not summarize every workspace override.
