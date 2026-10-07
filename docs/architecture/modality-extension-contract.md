# Adding a modality

Deployments use a closed, versioned registry. Enabled types are PDF, image, Markdown document, HTML, DOCX, XLSX, PPTX, audio, and video. Additions ship with code and a matching catalog migration.

## Stable core

Assets retain source identity, Workspace ownership, lifecycle, and processing/index state. Representations, units, embeddings, locators, citations, and note sources retain their common responsibilities. Format behavior belongs in its module, adapter, codec, retrieval channel, target resolver, visual enricher, or renderer.

Shared Chat, retrieval fusion, and Viewer dispatch through registry interfaces. Unknown/unenabled types produce explicit errors. Catalog rows cannot enable absent modules.

## Module and ingestion contract

Modules declare Asset kind, accepted MIME/byte inspector, representation/unit/locator types, channel signatures, configuration snapshots, cleanup, and metrics.

Byte inspection resolves canonical MIME and checks declarations. Worker performs full format validation. A PNG declared as JPEG is rejected.

Adapters receive Asset/source identity, processing generation, and Workspace settings; return immutable representations, typed units/locators, embedding requests, and object manifest. Manifests bind keys within representation namespaces, bytes, content type, and SHA-256.

Shared orchestration owns transactions, job/generation activation, upload, failures, and cleanup. Adapters do not replace sources or commit shared transactions. Failed post-upload work removes generated keys; deletion removes source/derived objects idempotently.

## Locators and retrieval

Locators need typed detail storage, strict codecs, stable versions, and retrieval keys. Preserve ordered regions, normalized text ranges, or time/frame identity. Citation/NoteSource cloning copies full snapshots. See [Evidence](evidence.md).

Channels declare exact `(asset_kind, unit_kind, representation_kind, locator_kind)` signatures. Candidates apply Workspace/Asset/current generation/index/provider scope before ranking and full chain/type validation afterward. Batch locator validation rejects inconsistent/unknown details. RRF stays modality neutral.

## Web and API

Update upload MIME support, API unions, content/file endpoints, renderer bindings, summaries, and optional target/enrichment registrations. Clients render the representation matching validated locator versions. Unknown kinds are rejected.

Capabilities are explicit. Missing caption/ASR returns configuration failure. Video keyframes may be skipped without tooling; no synthetic frames enter product ingestion.

## Tests

Cover MIME/signatures, parsing, codec integrity, Workspace scope, current indices, citation/note cloning, history after reindex/delete, viewer positioning, and backup/restore. Type/version changes need matching migration, codec, schema, fixture, and renderer. Follow [onboarding](modality-onboarding-checklist.md).
