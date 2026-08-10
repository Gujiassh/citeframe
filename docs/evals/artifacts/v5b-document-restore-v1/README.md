# V5-B Document restore evidence

## Purpose

Capture Document-aware backup/restore evidence for Markdown-only `document` modality:

- scoped oracle rows for one `workspaceId` + `assetId`
- typed tables: `document_normalized_contents`, `document_blocks`, `document_locator_details`
- catalog rows: document asset/representation/content-unit/locator types
- ContentUnit + embedding identity/sha metadata (no raw vectors)
- EvidenceLocator + DocumentLocatorDetail, Citation, NoteSource linked to the scoped asset
- object SHA only under `workspaces/{workspace_id}/assets/{asset_id}/`
- historical Citation/NoteSource `sourceAvailable=false` after delete (covered by lifecycle/recovery unit and mixed-workspace evidence)

## Live result (2026-08-07)

The dev service is now managed by the tracked `infra/docker/compose.yml`: PostgreSQL uses named volume `docker_postgres_data`, MinIO uses the repository bind path `infra/docker/data/minio`, and both containers report `restart=unless-stopped`. A restart-persistence snapshot pair is recorded in `live-compose-before.json` / `live-compose-after.json`; `live-verify-after-compose.json` passes with no mismatches and the same semantic SHA `02e6eeb15e539989295d123f154602976bc4faaa1c4f1a46bd6f7502155f321b`.

The live scoped fixture was materialized through the production Document adapter and contained one Document Asset, two Representations, one normalized content row, seven blocks, seven ContentUnits and embeddings, nine locators/details, one Citation, one NoteSource and two scoped objects. `live-table-check.json` reports `passed=true`.

A PostgreSQL custom dump and MinIO byte backup were restored into fresh temporary PostgreSQL 17 and MinIO targets. `live-before.json` and `live-after.json` both have semantic SHA-256 `4913e985d71652490c5fb879f289f8ea99bf139e768b06615b6c815686404367`; `live-verify.json` reports `passed=true`, `skipped=false`, no mismatches and real PostgreSQL/MinIO evidence. Temporary target containers and volumes were removed after verification. `live-restore-run.json` records database/object backup SHA values and source/target image identities.

The online migration oracle also ran against live PostgreSQL. `live-migration-roundtrip.json` and its SHA-bound log prove fresh upgrade to `e8f1a2b3c4d5`, upgrade/downgrade/re-upgrade through `f9a1b2c3d4e5`, populated Document downgrade refusal, single head/current `f9a1b2c3d4e5`, and exit code 0.

This closes the scoped restore semantic and online migration blockers. It does not satisfy the stricter B008 isolated deployment gate by itself because this restore used direct `pg_dump`/`pg_restore` plus byte-for-byte MinIO replay. The formal isolated gate is now recorded separately in `../v5b-document-deployment-v1/`, with built API/Worker/Web image IDs, dual-asset restore/API/DOM replay and full deployment teardown evidence.

## Helper

```bash
# Offline deterministic shape (not live evidence)
python3 apps/worker/scripts/v5b_document_restore_acceptance.py snapshot \
  --mode fixture \
  --output docs/evals/artifacts/v5b-document-restore-v1/fixture-snapshot.json

# Live PostgreSQL/MinIO scoped oracle (requires explicit ids; skips only when unavailable)
V5B_WORKSPACE_ID=... \
V5B_ASSET_ID=... \
DATABASE_URL=postgresql+psycopg://... \
V5B_MINIO_ENDPOINT=127.0.0.1:9000 \
V5B_MINIO_ACCESS_KEY=... \
V5B_MINIO_SECRET_KEY=... \
V5B_MINIO_BUCKET=ai-pdf-workspace \
python3 apps/worker/scripts/v5b_document_restore_acceptance.py snapshot \
  --mode live \
  --output docs/evals/artifacts/v5b-document-restore-v1/live-snapshot.json

python3 apps/worker/scripts/v5b_document_restore_acceptance.py verify \
  --before docs/evals/artifacts/v5b-document-restore-v1/live-before.json \
  --after docs/evals/artifacts/v5b-document-restore-v1/live-after.json \
  --output docs/evals/artifacts/v5b-document-restore-v1/verify.json
```

Exit codes:

- `0` pass
- `1` mismatch / failed table checks
- `2` live evidence skipped/blocked (missing scope ids, PostgreSQL/MinIO unavailable)

## Backup manifest contract

Deployment backup/restore uses `FORMAT_VERSION=2` with stable document modality keys:

- `BACKUP_CONTRACT=document-modality-v1`
- `DOCUMENT_TYPED_TABLES=document_normalized_contents,document_blocks,document_locator_details`
- `DOCUMENT_CATALOG_TABLES=asset_types,representation_types,content_unit_types,locator_types`
- `DOCUMENT_OBJECT_LAYOUT=workspaces/{workspace_id}/assets/{asset_id}/`

Format 1 backups are rejected and require a new format-2 backup. Unknown versions are rejected.

## Hard rule

SQLite unit tests and fixture-shape snapshots are not live restore evidence. When live
PostgreSQL/MinIO is unavailable, record `evidenceMode=skipped|blocked` /
`livePostgresMinio=false` and the `skipReason`. Fixture verify through the live restore
path must return `skipped=true, passed=false`. Do not replace that gap with SQLite-only
claims or all-bucket object mirrors.

Live `verify` additionally requires:

- both snapshots `evidenceMode=live` and `livePostgresMinio=true`
- recomputed `semanticSha256` equality over the canonical body:
  `workspaceId`, `assetId`, `objectPrefix`, `scopedRows`, `objects`, `typedTables`,
  `catalog`, `historicalEvidence`
- strict live payload validation **before** equality/hash pass (forged empty or
  malformed scoped rows/objects with a recomputed digest must fail):
  - non-empty `workspaceId` / `assetId` and exact
    `objectPrefix=workspaces/{workspaceId}/assets/{assetId}/`
  - every required scoped collection present as a list with required field sets;
    no missing keys, no non-dict members, no soft-defaulting missing fields to
    `{}` / `[]` / projected `None`
  - exactly one scoped Asset with matching id/workspace and `asset_kind=document`
  - representations, normalized contents, blocks, content units, embeddings,
    locators, details, citations, and note sources only reference the scoped
    asset/workspace and existing parent IDs
  - live Document oracle requires at least one representation, normalized
    content, block, content unit, locator, citation, and note source
  - ContentUnit kinds only `document_text_chunk` (never `document_block`)
  - block/locator detail ranges and sha256 fields structurally valid when present
  - objects are dicts with `objectKey`, lowercase 64-hex `sha256`, nonnegative
    `byteSize`, and bool `expectedExists`; unique keys under the exact prefix;
    non-deleted assets require ≥1 object; empty object list only when the scoped
    Asset is deleted and historical rows remain
  - `historicalEvidence` required and must match derivation from scoped rows:
    `sourceAvailable` from `Asset.deleted_at`, retained locator/citation/
    note-source IDs, and Citation/NoteSource source-version tuples; after-delete
    evidence keeps `sourceAvailable=false` while locator/snapshot rows remain
- all Document typed tables, catalog tables, and required link tables
  (`message_citations`, `note_sources`) present with required columns
- full catalog metadata equality (order-independent, sorted canonical form):
  - `asset_types`: kind, enabled, contract_version
  - `representation_types` / `content_unit_types`: kind, asset_kind, contract_version
  - `locator_types`: kind, detail_family, contract_version
- `catalog.documentEnabled=true`, document asset enabled with contract_version=1,
  and `document_anchor` locator with `detail_family=record` and contract_version=1
- equality of `typedTables`, `catalog`, and `historicalEvidence` in addition to
  scoped rows/objects

Offline fixture shape uses checked-in Markdown fixture facts
(`docs/fixtures/document-modality/markdown-note.fixture.json`): `byteSize=114`,
source/normalized content SHA values, normalized text, and block/locator fields.
Fixture verify remains offline-only (`skipped=true`, `passed=false`).

`check-tables` validates those same catalog values, not only table presence. Fixture
shape may report `offlineCatalogShapeOk=true` / `fixtureShapeOk=true`, but live
acceptance `passed` is true only when PostgreSQL/MinIO live evidence is present.
Missing scope, PostgreSQL, MinIO, or required citation/note_source schema remains
blocked/skipped and never passes.
