# D-G4 Production-start Mixed Web Report

Date: 2026-08-11  
Lane: D-WEB + live stack verification  
Worktree: `/home/cc/code/citeframe`  
Source SHA baseline: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`

## Verdict

**pass-focused** for production-start mixed PDF+Image+Markdown primary browser
evidence. Not a full D-G7 matrix closeout.

## What ran

1. Local infra already up: Postgres `5432`, MinIO `9010`, Redis shared.
2. Provider stub: `apps/api/scripts/provider_m403b_stub.py` on `18081`.
3. API: `uvicorn` on `127.0.0.1:8000`.
4. Worker: `python -m ai_pdf_worker.main`.
5. Mixed seed: `apps/worker/scripts/v5d_mixed_deployment_seed.py` → three ready
   assets + historical citations in one workspace.
6. Standalone Web: `apps/web/.next/standalone/apps/web/server.js` on `3100`
   (`HOSTNAME=0.0.0.0`, `PLAYWRIGHT_STANDALONE_SERVER=1`).
7. Playwright:
   `e2e/v5d-mixed-production-start.spec.ts` → **2 passed**
   (desktop `1440x1000`, mobile `390x844`).

## Artifacts

| File | Meaning |
|---|---|
| `v5d-mixed-production-desktop.json` | `productionStart=true`, `mockedBff=false` |
| `v5d-mixed-production-mobile.json` | same for mobile |
| `v5d-mixed-production-desktop.png` | screenshot |
| `v5d-mixed-production-mobile.png` | screenshot |
| `mixed-browser-state.redacted.json` | seeded state (password redacted) |

## Oracle covered

- Three ready assets with exact kind labels `pdf` / `image` / `document`.
- Selected scope count 3.
- Historical citations open PDF viewer canvas, Image viewer, Document viewer
  with generation/block highlight when metadata present.
- Dual viewport + no horizontal overflow.
- Explicitly **not** `PLAYWRIGHT_START_WEB=1` mocked BFF.

## Residual

- Full Research live plan/approve over mixed scope not required for this D-G4
  focused close; mocked path remains in `v5d-mixed-workspace-primary.spec.ts`.
- Isolated Compose backup/empty-target restore still optional for full D-G6
  empty-deployment identity (seed+snapshot self-verify already green).

No commit/push.
