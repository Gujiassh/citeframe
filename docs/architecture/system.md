# System architecture

Citeframe runs as a Next.js Web application, a FastAPI API service, and a Python Worker. PostgreSQL, pgvector, and object storage hold persistent state. Deployment Compose includes Redis; current job claims and Research correctness use PostgreSQL.

## Service responsibilities

| Component | Responsibility |
| --- | --- |
| Web / BFF | UI, signed session cookies, authentication context, and stream forwarding |
| API | Workspace and resource authorization, assets, chat, retrieval, notes, model settings, Research HTTP interfaces, and Alembic migrations |
| Worker | Modality ingestion, OCR/caption/transcription, embeddings, cleanup, and persisted Research step execution |
| PostgreSQL / pgvector | Business data, typed evidence, current index projections, job leases, Research state, and retrieval |
| MinIO | Original source files, generated representations, and immutable Research artifact bytes |
| Caddy | Public HTTP(S) entry point for single-host deployment |
| Redis | Deployed infrastructure reserved for caching/queue acceleration; no current business truth or job-claim authority |

The split separates browser interaction, synchronous requests, and long-running processing. Assets, retrieval, chat, and permissions share Workspace context and data relations; keeping API orchestration together reduces cross-service consistency and deployment costs.

## Request and processing paths

```text
Browser -> Caddy -> Next.js BFF -> FastAPI -> PostgreSQL / MinIO / model provider
                                      |
                                      +-> persisted jobs -> Worker
```

BFF resolves the signed session and supplies the internal token and user identity. API checks database membership and each resource's Workspace scope. Browser-supplied role headers grant no access. [Workspace access](workspace-access.md) describes validation order and stream revalidation.

Upload creates an Asset with immutable source identity. Finalization verifies object size/hash and creates an ingestion job. Worker adapters produce representations, typed content units, and locators. Shared ingestion orchestration manages transactions, index activation, failure state, and cleanup.

Retrieval filters by Workspace, explicit asset scope, ready/nondeleted assets, current generation/index, and embedding contract. Dense pgvector and PostgreSQL lexical candidates are fused using reciprocal rank fusion. PDF page candidates deduplicate by asset/page; typed region and temporal locations retain their identity.

Chat generates a streaming response from this evidence and persists immutable citation snapshots. Notes copy source snapshots independently. Research uses a bounded versioned workflow and separate event stream. See [Evidence](evidence.md) and [Research](research-workflow-runtime.md).

## Persistence ownership

`citeframe_contracts` contains neutral contracts. `citeframe_persistence` owns common ORM mappings and metadata. `citeframe_research_persistence` owns DB-only Research commands, repositories, locks, and UoW interfaces. API owns HTTP/authentication and migration execution; Worker composes Research orchestration with persistence and provider/tool adapters.

Ingestion shares an API orchestrator Session/ORM boundary with Worker adapters. API and Worker use the same database and deploy together. The production Research dispatcher claims one Attempt per handler; its default step-execution path does not load LangGraph.

## State and model boundaries

Workspace, assets, chat, notes, and settings are server state. Viewer focus, selection drafts, zoom, pan, and panels are UI runtime state. Theme and language may be stored as local preferences. Runtime viewer state never changes a saved locator.

Generation, embedding, vision/caption, and ASR are distinct capabilities. Server profiles are resolved before use and execution bindings recorded. Workspace owners can override generation/embedding; vision and ASR remain server configured. Missing capability or configuration drift returns an explicit failure. [Model configuration](../guides/model-configuration.md) documents protocols and network controls.

## Operational boundaries

`/health/live` indicates liveness. `/health/application-ready` checks database, enabled modality catalog, object storage, and model configuration schema; Compose uses it so settings can open without global model keys. `/health/ready` retains full global provider diagnostics and does not summarize every workspace override.

This is a single-host self-hosting design. Multi-region high availability, federated cross-workspace retrieval, and a general-purpose agent/plugin platform are outside current scope. Model quality and target-user validation remain pending. [Deployment](../deployment/README.md) covers secrets, backups, and public exposure.
