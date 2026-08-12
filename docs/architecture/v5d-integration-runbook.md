# V5-D Integration Runbook

Status: draft for V5-D engineering integration (internal preview)
Artifact root: [`../evals/artifacts/v5d-20260811-01/`](../evals/artifacts/v5d-20260811-01/)

This runbook covers mixed PDF / Image / Markdown Document workspaces with Quick
Chat and Research. It does not claim model quality (R803) or user value (M404).

## 1. Gate separation

| Gate | Meaning | V5-D may claim |
|---|---|---|
| Engineering / internal-preview | Contracts, restore, primary flows | yes |
| Model quality (R803) | Real model paired evaluation | no |
| User value (M404) | Target-user evidence | no |

## 2. Local development start

From repository root:

```bash
docker compose -f infra/docker/compose.yml up -d
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
pnpm dev:web
pnpm dev:api
pnpm dev:worker
```

Open `http://localhost:3000`. Dev watcher is for development only and is not
acceptance evidence.

## 3. Production-start Web (acceptance)

```bash
pnpm --dir apps/web build
HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
  pnpm --dir apps/web exec playwright test e2e/<focused>.spec.ts
```

Desktop viewport target: `1440x1000`. Mobile viewport target: `390x844`.

Focused suites:

- Document: `e2e/v5b-document-production-start.spec.ts`
- Research: `e2e/research-run.spec.ts`
- PDF/Image multimodal: `e2e/multimodal-fullstack.spec.ts`
- Image region: `e2e/image-region-evidence.spec.ts`

## 4. Mixed workspace verification (API/Worker)

```bash
uv run --project apps/api python -m pytest \
  apps/api/tests/test_multimodal_retrieval.py \
  apps/api/tests/test_document_api_contract.py \
  apps/api/tests/test_research_v5c_contract.py -q
uv run --project apps/worker python -m pytest \
  apps/worker/tests/test_v5b_mixed_workspace.py \
  apps/worker/tests/test_v5b_recovery.py -q
```

Invariants:

- Scope is exact; no foreign Workspace leakage.
- Retrieval candidates keep typed locators: `pdf_page` / `pdf_region`,
  `image_region`, `document_anchor`.
- Citation / NoteSource snapshots remain immutable after reprocess/delete.
- Research provider/model/limits/retrievalTopK come only from frozen execution
  snapshots.

## 5. Isolated live restore

Prefer existing accepted runners; do not invent a second backup format.

- Document deployment/restore: `infra/scripts/run-v5b-document-acceptance.sh`
- Research R800: `infra/scripts/run-r800-acceptance.sh`
- Generic backup/restore scripts: `infra/scripts/backup-deployment.sh`,
  `infra/scripts/restore-deployment.sh`, `infra/scripts/test-backup-restore.sh`

Required live evidence when claiming D-G6:

- API/Worker/Web image or runtime version
- Alembic head
- PostgreSQL semantic hash / row checksums
- MinIO object SHA-256
- API or DOM replay after restore
- zero-residue cleanup

## 6. Diagnostic map

Prefer flat grep-friendly logs: `tag key=value key=value`.

| Symptom | Likely service | Grep / signal | Retryable | Operator action |
|---|---|---|---|---|
| Upload rejected kind/MIME | API registry | asset kind inspect / fail-closed | no | Use enabled kind only |
| Ingest stuck queued | Worker lease | ingestion job status, lease reclaim | yes after reclaim | Restart worker; check Redis/MinIO |
| Embedding index mismatch | API retrieval / Worker embed | `embedding_index_mismatch` | no until reindex | Explicit reindex job; do not change current Settings as fallback |
| Document integrity fail | API evidence | `document content_sha256` / block hash | no | Fail closed; re-ingest source |
| Research provider drift | API Research ports | `research_provider_config_drift` / 409 | no | Frozen snapshot is truth; do not fall back to live profile |
| Source unavailable after delete | API citation/note | `sourceAvailable=false` | n/a | Expected; historical snapshot remains |
| Worker health null | Worker metrics | accepted runner rules | n/a | Do not treat as hard fail without other evidence |

## 7. Stop and escalate

Stop implementation and escalate when any of these appear:

- Database / API / save / replay / permission / cost / locator contract change
- Need for provider selector, fallback chain, new registry version, new modality
- Unowned dirty worktree overlap
- Missing live PostgreSQL/MinIO, auth, or production-start environment for a required gate

Use `specs/v5/multimodal-agent-product/save-contract-checklist.md` for contract
changes.

## 8. Related authority

- Scope decision: `specs/v5/multimodal-agent-product/decision-2026-08-11-v5d-scope.md`
- Detailed spec: `specs/v5/multimodal-agent-product/v5d-detailed-spec.md`
- Lanes: `specs/v5/multimodal-agent-product/implementation-lanes-v5d.md`
- Matrix: `specs/v5/multimodal-agent-product/verification-matrix-v5d.md`
- Research runtime: `docs/architecture/research-workflow-runtime.md`
- Modality extension: `docs/architecture/modality-extension-contract.md`
