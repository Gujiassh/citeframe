# V5-D D-WEB Lane Report

Date: 2026-08-11  
Lane: `D-WEB`  
Worktree: `/home/cc/code/citeframe`  
Source SHA baseline: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`  
Artifact root: `docs/evals/artifacts/v5d-20260811-01/`

## 1. Scope and constraints

- Allowed: `apps/web/src/**`, `apps/web/e2e/**`, web fixtures/tests, this artifact report.
- Forbidden: `apps/api/**`, `apps/worker/**`, `infra/**`, schema/migration, commit/push.
- Contract-preserving only; no registry/API/save/locator contract changes.
- V5-C dirty tree retained; D-WEB only added non-overlapping web test/report files.

## 2. Gap analysis (desktop/mobile mixed PDF+Image+Markdown)

### Existing coverage inventory

| Spec | Modalities | Viewports | Live/mocked | Primary mixed path? |
|---|---|---|---|---|
| `e2e/v5b-document-production-start.spec.ts` | Markdown document only | not dual-viewport primary | live production-start gated | No — document upload/content/historical citation only |
| `e2e/multimodal-fullstack.spec.ts` | PDF + Image (M402 evidence) | `1440x1000`, `390x844` | live state (`PLAYWRIGHT_M402_STATE_PATH`) | Partial — no Markdown document |
| `e2e/research-run.spec.ts` | PDF-only frozen scope | desktop `1440x900`, mobile `390x844` (not exact D002 desktop height) | mocked BFF | Partial — Research controls, not mixed assets/viewers |
| `e2e/image-region-evidence.spec.ts` | Image only | default desktop | mocked BFF | No |
| `e2e/authenticated-smoke.spec.ts` | PDF or Image env-gated | default | live secrets | No |
| `e2e/m403b-image-production.spec.ts` | Image only | `1440x1000`, `390x844` | live production | No |
| `e2e/m403-restore.spec.ts` | PDF + Image historical | both viewports | live restore state | No Markdown |
| Unit: `registry.test.ts`, `document-content*.test.ts`, `sse.test.ts`, `document-viewer*.test.ts` | document/pdf/image modules | n/a | unit | Module-level, not mixed primary UI flow |

### Missing before this lane

1. **No single Playwright path** that seeds/renders **PDF + Image + Markdown** in one Workspace and exercises:
   - asset list kind labels for all three;
   - selected-scope Quick Chat over the three;
   - Citation open for PDF page, Image region, and Document block/range;
   - Research start with selected mixed scope;
   - unavailable source disabled/fail-closed UI;
   - both target viewports **`1440x1000`** and **`390x844`**.
2. Planned V5-B file `apps/web/e2e/v5b-mixed-workspace.spec.ts` was never present in the worktree.
3. Live production-start mixed evidence still depends on external standalone server + auth/API/worker/state; no existing live state schema for three-modality mixed primary.

### Closable with tests/fixtures only (this lane)

- Mocked BFF e2e for mixed primary UI flows at both viewports.
- Unit assertion that selected scope preserves three mixed asset ids.

### Not closable without live stack (residual for D-ACCEPT / D-OPS)

- Production-start standalone Web + real API/Worker ingest of mixed fixtures.
- Live mixed retrieval candidate trace / generation / index contract.
- Live Research branch retry/cancel/lease reclaim over mixed Evidence.
- Live backup/restore DOM replay for mixed assets.

## 3. Implementation

### Added

| File | Purpose |
|---|---|
| `apps/web/e2e/v5d-mixed-workspace-primary.spec.ts` | Mocked desktop/mobile mixed primary flow e2e |
| `apps/web/src/lib/use-chat.test.ts` | Extra unit case for mixed three-id selected scope |
| `docs/evals/artifacts/v5d-20260811-01/d-web-lane-report.md` | This report |

### Intentionally not changed

- No production UI/src product logic (except unit test next to existing `buildAssetScope`).
- No dirty V5-C web files (`research-run.spec.ts`, `research-run-panel.tsx`, i18n, research types, etc.).
- No API/Worker/infra.

### Mocked e2e oracle (semantic)

1. Workspace lists three ready assets with exact `kind` labels: `pdf`, `image`, `document`.
2. Checking all three scope checkboxes shows selected count 3.
3. Quick Chat POST body uses  
   `assetScope: { mode: "selected", assetIds: [pdf, image, document] }`.
4. Assistant citations include PDF page, Image region, Document anchor, plus one unavailable citation.
5. Unavailable citation button is **disabled** and shows source-deleted copy.
6. PDF citation → `[data-pdf-viewer]` page 1 canvas.
7. Image citation → `[data-image-viewer]` + region overlay.
8. Document citation → `[data-document-viewer=true]` with `data-document-highlight-status=ready`, generation `1`, exact block highlight range.
9. Research start POST body uses the same selected three-id scope; frozen scope titles for all three appear.
10. No horizontal overflow at either viewport; screenshot + JSON artifacts written.

## 4. Commands (run / blocked)

### Unit — no production-start, no secrets

```bash
cd /home/cc/code/citeframe/apps/web
pnpm exec tsx --test src/lib/use-chat.test.ts
# optional full suite:
pnpm test
```

Expected new case: `mixed PDF+Image+Markdown selected scope stays exact without dedupe reordering`.

### Mocked dual-viewport mixed e2e — no live API secrets

Engineering evidence only. Uses route mocks + optional local dev server via `PLAYWRIGHT_START_WEB=1`.  
**Not** formal D-G4 production-start evidence.

```bash
cd /home/cc/code/citeframe/apps/web
PLAYWRIGHT_START_WEB=1 \
  pnpm exec playwright test e2e/v5d-mixed-workspace-primary.spec.ts --reporter=line
```

On pass writes:

- `docs/evals/artifacts/v5d-20260811-01/v5d-mixed-primary-desktop.{png,json}`
- `docs/evals/artifacts/v5d-20260811-01/v5d-mixed-primary-mobile.{png,json}`

Optional: `PLAYWRIGHT_V5D_MIXED_ARTIFACT_DIR` overrides artifact directory.

### Production-start mixed live — blocked in this lane

```bash
pnpm --dir apps/web build
HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
# + API/Worker/auth/mixed ready fixtures (D-API-WORKER / D-OPS)

PLAYWRIGHT_STANDALONE_SERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
PLAYWRIGHT_V5B_DOCUMENT_STATE_PATH=<document-or-mixed-state.json> \
  pnpm --dir apps/web exec playwright test e2e/v5b-document-production-start.spec.ts
```

Blockers:

1. No checked-in live mixed browser state for PDF+Image+Markdown primary.
2. Real API/Worker/auth/MinIO/ingest outside D-WEB ownership.
3. Formal evidence requires standalone + `PLAYWRIGHT_STANDALONE_SERVER=1` (never `PLAYWRIGHT_START_WEB=1`).
4. D-OPS mixed acceptance harness owns live orchestration.

## 5. Execution note

Lane prepared tests + report under dirty-tree constraints (no commit/push, no unowned overwrites).  
Controller/D-ACCEPT should re-run the unit + mocked e2e commands and attach exit codes to the acceptance record.  
Do **not** mark D-G4 `pass` on mocked evidence alone.

## 6. Residual risks

1. **Mocked vs live**: mocked e2e cannot prove real BFF/proxy/ingest/retrieval contracts or production-start hydration.
2. **PDF canvas timing**: real pdf.js render may flake under CI load; timeout is 30s per surface.
3. **Research desktop height**: existing Research e2e still uses `1440x900`; new mixed e2e uses exact D002 `1440x1000`.
4. **D002 incomplete without live**: approval/revise/conflict/retry/cancel/recovery full matrix still lives primarily in `research-run.spec.ts` (PDF-only mocks) + live R800; not fully re-proven on mixed three-modality live data.
5. **Unavailable source** only asserts disabled citation UI; does not open a historical unavailable document viewer path in this mocked suite.
6. Dirty V5-C web research files were not modified; if those change Research DTO shape mid-flight, this mocked Research section may need sync.

## 7. Handoff

### Done for D-WEB (engineering gap close)

- Gap analysis recorded.
- Mocked dual-viewport mixed primary Playwright added.
- Mixed selected-scope unit assertion added.
- Production-start live mixed commands/blockers documented.

### Next owners

| Owner | Next |
|---|---|
| D-API-WORKER | Live mixed fixture seed / scope-retrieval oracles if missing |
| D-OPS | Production-start + isolated stack for formal D-G4 evidence |
| D-ACCEPT | Mark D-G4 `pass` only after production-start dual-viewport evidence + screenshots/DOM/state |
| Main controller | Do not treat mocked e2e alone as D-G4 formal pass |

### Changed files (this lane)

- `apps/web/e2e/v5d-mixed-workspace-primary.spec.ts` (new)
- `apps/web/src/lib/use-chat.test.ts` (unit case)
- `docs/evals/artifacts/v5d-20260811-01/d-web-lane-report.md` (this file)
- runtime artifacts under `docs/evals/artifacts/v5d-20260811-01/v5d-mixed-primary-*` after test run


## Controller verification (2026-08-11)

| Command | Result |
|---|---|
| `pnpm exec tsx --test src/lib/use-chat.test.ts` | **6 passed** |
| `PLAYWRIGHT_START_WEB=1 pnpm exec playwright test e2e/v5d-mixed-workspace-primary.spec.ts` | **2 passed** (desktop 1440x1000 + mobile 390x844, mocked BFF) |

Notes:
- Mobile required closing the full-screen `关闭导航` overlay before chat send.
- Research frozen scope titles appear as one definition string, not three exact nodes.
- Still **not** formal D-G4 production-start evidence (`productionStart=false`, `mockedBff=true`).
