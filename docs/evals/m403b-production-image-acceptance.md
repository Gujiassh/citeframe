# M403B Production Image Acceptance

## Scope

This report covers the production plumbing path only. It does not evaluate model quality, caption quality, user value, or the M404 Beta gate.

The semantic oracle is:

- upload MIME is exactly `image/png`, `image/jpeg`, or `image/webp` (PDF remains unchanged);
- API upload-session, binary PUT, finalize, Worker Image adapter, retrieval, Evidence Viewer stream, and `evidenceTargets` Chat use the same Asset and processing generation;
- Citation/NoteSource/Chat/save contracts are unchanged;
- deleting the processed Asset removes both source and generated Image objects;
- all provider calls use a local deterministic stub and are labelled `modelQualityClaim=false`.

## Execution

The checked-in `apps/worker/scripts/m403b_production_acceptance.py` creates a unique temporary Workspace, uploads PNG/JPEG/WebP through the API HTTP boundary, processes queued jobs with the production Worker registry, performs scoped Hybrid retrieval and Image region Chat Evidence, checks the oriented PNG stream, exercises immutable-source failure/retry and terminal delete cleanup, and removes the temporary identity and objects.

`apps/worker/scripts/m403b_browser_acceptance.py` provisions a temporary login and empty Workspace. `apps/web/e2e/m403b-image-production.spec.ts` then uses the real session, BFF, API, MinIO and a long-running Worker without `page.route` or `context.route`. Desktop uploads PNG/JPEG/WebP and opens the PNG Viewer; `390x844` uploads PNG and verifies the Viewer, no overflow, nonblank pixels and six 44px Image controls.

The provider process is `apps/api/scripts/provider_m403b_stub.py`. It implements only deterministic Ollama embedding, Responses caption, and streaming generation responses for local synthetic acceptance. It is not a model-quality oracle.

## Result

Artifacts:

- `docs/evals/artifacts/m403b-v2/report.json` with `SHA256SUMS`
- `docs/evals/artifacts/m403b-browser-v1/` with desktop/mobile JSON, screenshots and `SHA256SUMS`
- `docs/evals/artifacts/m403b-restore-v2/` with before/after snapshots, replay screenshots, verification, cleanup and complete directory `SHA256SUMS`

- upload-session / PUT / finalize: `201 / 204 / 200`
- PNG/JPEG/WebP each reached `ready`; JPEG/WebP also completed terminal delete cleanup
- MIME mismatch PUT returned `422` before object persistence
- immutable-source failure/retry: attempt 1 `failed`, attempt 2 `succeeded`, `sourceIdentityPreserved=true`
- Worker: `ready`, 3 Representations, 9 ContentUnits
- retrieval: 6 scoped results, all `image_region` locators
- oriented Evidence stream: `200 image/png`, `1200x800`, `orientationApplied=true`
- Evidence Chat: `200`, completed assistant, `inputEvidence=1`, Citation rows `6`, terminal `citations` and `done`
- delete cleanup: Asset `deleted`, `deletedAtPresent=true`, latest job `succeeded`, ContentUnit/embedding/geometry rows zero, source and oriented objects absent
- browser: desktop and `390x844` both passed; PNG/JPEG/WebP UI uploads used fresh Asset IDs; pixels were nonblank; Viewer/panel/surface stayed within bounds; mobile controls were `44x44`; `routeInterceptions=0`
- restore: before/after semantic SHA `c4c8ab66e050bdbbaa33f3b3d0af3fd3f5fe21df3e6cca5988a3af113a86bd4d`, `imageProductionEnabled=true`, desktop/mobile PDF/Image replay passed, final containers/volumes/networks zero
- `releaseGatePassed=true`; `modelQualityClaim=false`

## Process And Corrections

- The historical M403 oracle assumed Image disabled. `M403_EXPECT_IMAGE_ENABLED` now makes the expected catalog state explicit; M403B restore runs use `true`, while the old M403 reproduction remains `false` by default.
- The first retry fixture repaired the source object out of band. Review rejected it because source identity is immutable. The accepted oracle injects one deterministic transient adapter failure and retries the same source bytes/key/hash unchanged.
- Delete evidence initially checked only MinIO absence. The accepted gate also requires Asset `deleted`, non-null `deleted_at`, latest delete job `succeeded`, and zero current derived content rows.
- Worker ingestion now verifies downloaded byte length and SHA-256 against persisted source identity before invoking an adapter when a hash baseline exists; both initial and retry mismatch paths fail closed.
- The first live browser fixture used the reserved `example.invalid` email and was rejected before product code. The setup now uses a valid `example.com` fixture address.
- The Asset delete control incorrectly reused the Workspace-delete label. It now uses `Delete asset` / `删除资产`.
- The first real Viewer layout run exposed a one-shot `ResizeObserver` effect that executed before the loading branch mounted the viewport. Rebinding when `viewerSource.status` changes fixed the 712px surface overflow; accepted desktop/mobile scroll widths now equal client widths.
- All final provider traffic is bound to `127.0.0.1:18081`; the deterministic stub proves plumbing only and does not support a model-quality claim.

## Reproduction

The backup/restore gate is fully isolated and starts its own deployment:

```bash
M403_EXPECT_IMAGE_ENABLED=true infra/scripts/run-m403-acceptance.sh \
  --output-dir /home/cc/tmp/citeframe-m403b-restore \
  --project citeframe-m403-m403b-release
```

The standalone production-plumbing runner expects the normal local PostgreSQL
and MinIO services, the head migration, and an API process on `127.0.0.1:8000`.
Start the deterministic provider first:

```bash
uv run --project apps/api python apps/api/scripts/provider_m403b_stub.py
```

Start or restart the API with the same provider configuration in a second
terminal. Existing database, storage and internal-token values continue to
come from the project's local `.env`:

```bash
AI_PDF_OPENAI_API_BASE=http://127.0.0.1:18081/v1 \
AI_PDF_OPENAI_API_KEY=m403b-local-only \
AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:18081 \
AI_PDF_EMBEDDING_PROVIDER=ollama \
  pnpm dev:api
```

Only after that API reports ready, run the acceptance process in a third
terminal with the identical provider variables:

```bash
curl --fail http://127.0.0.1:8000/health/ready

AI_PDF_OPENAI_API_BASE=http://127.0.0.1:18081/v1 \
AI_PDF_OPENAI_API_KEY=m403b-local-only \
AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:18081 \
AI_PDF_EMBEDDING_PROVIDER=ollama \
  uv run --project apps/worker python apps/worker/scripts/m403b_production_acceptance.py \
  --output /home/cc/tmp/m403b-report.json
```

For the browser gate, keep the same stub and API running, then start a
long-running production Worker with the same provider configuration:

```bash
AI_PDF_OPENAI_API_BASE=http://127.0.0.1:18081/v1 \
AI_PDF_OPENAI_API_KEY=m403b-local-only \
AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:18081 \
AI_PDF_EMBEDDING_PROVIDER=ollama \
  pnpm dev:worker
```

Start the Web app with `pnpm dev:web`. In another terminal, provision the
temporary identity, run both real-browser viewports without route
interception, and always clean the temporary Workspace:

```bash
STATE=/home/cc/tmp/m403b-browser-state.json
ARTIFACTS=/home/cc/tmp/m403b-browser-artifacts

uv run --project apps/worker python apps/worker/scripts/m403b_browser_acceptance.py \
  setup --output "$STATE"
trap 'uv run --project apps/worker python apps/worker/scripts/m403b_browser_acceptance.py cleanup --state "$STATE"' EXIT

PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
PLAYWRIGHT_M403B_BROWSER_STATE_PATH="$STATE" \
PLAYWRIGHT_M403B_BROWSER_ARTIFACT_DIR="$ARTIFACTS" \
  pnpm --dir apps/web exec playwright test e2e/m403b-image-production.spec.ts
```

M403B is complete as an engineering production-enablement gate. M404 real-user value remains `not_evaluable`; the product remains an internal preview until that separate gate has data.
