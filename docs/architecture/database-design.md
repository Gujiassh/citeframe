# Data model and migrations

PostgreSQL is the shared transactional database. pgvector stores 1024-dimensional text embeddings; pg_trgm and full-text search support lexical retrieval. Current migration head is `s3a4b5c6d7e8`; check the installed database with Alembic.

```bash
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
uv run --project apps/api alembic -c apps/api/alembic.ini check
```

## Ownership and table groups

The neutral persistence package owns the single DeclarativeBase, metadata, and ORM mappings. API Alembic executes migrations against that metadata. Worker and API share the mappings.

| Group | Main tables |
| --- | --- |
| Identity/Workspace | `users`, `workspaces`, `workspace_memberships`, `workspace_model_configs` |
| Catalog | `asset_types`, `representation_types`, `content_unit_types`, `locator_types`, `embedding_spaces` |
| Assets/indexing | `assets`, `asset_representations`, `content_units`, `content_unit_embeddings`, `ingestion_jobs` |
| Parsed content | `pdf_pages`, `image_representation_geometry`, document/HTML/DOCX content/blocks, audio/video content/transcript segments |
| Evidence | `evidence_locators`, spatial regions and typed PDF/image/document/HTML/DOCX/XLSX/PPTX/audio/video detail tables |
| Chat/knowledge | threads/messages, input evidence/retrieval scopes/citations, notes/source snapshots, tags/bindings |
| Research | workflows/prompts, runs/plans/snapshots, steps/dependencies/attempts, events/decisions, calls/budget ledgers, claims/evidence/artifacts, publication intents, adaptive/conflict turns, report edits |
| Evaluation | suites, runs, case results, claim results |

[ORM mappings](../../packages/backend-persistence/src/citeframe_persistence/models/) define exact columns/constraints. [Migrations](../../apps/api/alembic/versions/) define deployment order. [API](api-contracts.md) and [Evidence](evidence.md) describe observable meaning.

## Assets and representations

Asset identity includes Workspace, source key/MIME/size/hash, lifecycle, current processing generation, and current index version. Generation and index version are distinct. Source bytes remain immutable after upload.

Representations are unique by `(asset_id, representation_kind, processing_generation)` and retain generator/content hash. Historical generations remain distinguishable. Canonical oriented images use PNG without EXIF; the source remains untouched.

Content units bind representation and source locator before retrieval. Page-text offsets apply only to a genuinely continuous span. Derived table/figure text and image OCR/caption units do not fabricate offsets. Citations bind typed locations rather than reconstructing them from filenames/page fields.

## Current embeddings

Embeddings retain Workspace/Asset/content-unit identity, generation/index, `is_current`, space, provider/model/version, dimensions, and vector. `is_current` denotes the active generation/index projection; Asset ready/deleted state is checked separately.

Ingestion writes inactive vectors, checks latest-job CAS, switches Asset generation/index, and activates the new projection in one transaction. Failed replacement preserves the prior complete index. Workspace overrides add a configuration fingerprint to the index contract.

Dense retrieval filters current embeddings by Workspace, asset scope, and provider metadata. Current-only cosine HNSW uses `ef_construction=512`; auxiliary binary-quantized Hamming HNSW uses `ef_construction=64`. Candidate identities deduplicate and rerank by original 1024-dimensional cosine distance. Binary distance only discovers candidates.

Outer queries validate full Asset/Representation/Locator current chain and type scope. Triggers enforce scope/generation/index consistency for active projections. Inactive historical rows retain their meaning. Lexical `search_vector` is generated/stored with `simple` configuration and FTS GIN; text also has trigram GiST.

## Research and model configuration

Research locks follow `Run -> Step -> Attempt -> Call -> Ledger`. Leases, dependencies, events, budgets, and publication intents provide recovery state. Versioned workflow/prompt bindings preserve historical runs. Report edits never alter original artifact bytes.

Workspace keys use AES-GCM with a persistent operator key. Save/reset revisions are monotonic and stale edits fail. See [model configuration](../guides/model-configuration.md).

## Operational constraints

Catalog rows match the closed deployment registry. They cannot enable absent modules.

Some migrations refuse downgrade when references exist. The Asset migration requires restoring a matching backup to recover the old schema. Index-rebuilding migrations require maintenance windows and do not promise zero downtime. Back up database and object storage together; preserve encryption secrets separately. See [deployment](../deployment/README.md).
