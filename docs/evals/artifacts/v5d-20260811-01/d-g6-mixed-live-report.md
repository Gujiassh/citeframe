# D-G6 Mixed Live Seed / Snapshot / Verify Report

Date: 2026-08-11  
Lane: D-API-WORKER + D-OPS wire  
Worktree: `/home/cc/code/citeframe`

## Verdict

**pass-focused** for mixed live seed + snapshot/verify CLI path and harness
`mixed-live` mode. Full isolated Compose empty-target backup/restore loop is
still optional residual (same contract as v5b/r800; no schema change).

## Deliverables

| Path | Role |
|---|---|
| `apps/worker/scripts/v5d_mixed_deployment_seed.py` | Upload PDF+Image+Markdown via real API/Worker; attach historical citations |
| `apps/worker/scripts/v5d_mixed_restore_acceptance.py` | Live snapshot + before/after semantic verify for three modalities |
| `apps/web/e2e/v5d-mixed-production-start.spec.ts` | Production-start browser replay |
| `infra/scripts/run-v5d-mixed-acceptance.sh` mode `mixed-live` | Records CLI + state + optional verification without inventing contracts |

## Live evidence (this slice)

- Seed result schema `v5d-mixed-deployment-seed-v1`, workspace with
  `pdf` + `image` + `document` ready assets and citation IDs for all three.
- Snapshot evidenceMode=`live`, semanticSha256 stable on self-verify.
- Harness: `engineeringGate=mixed-live-pass`.
- Static harness still `static-pass` with CLI presence checks.

## Artifacts

- `mixed-browser-state.redacted.json`
- `mixed-restore-snapshot-before.json`
- `mixed-restore-verification-self.json`
- `mixed-live-report.json` / `mixed-live-lane.json`

## Honesty limits

- Self-verify uses the same live snapshot before/after (identity freeze oracle).
  It does **not** claim a full empty-target Compose backup/restore cycle in this
  slice. That remains available by wiring the same CLIs into v5b-style
  backup-deployment/restore-deployment later without contract changes.
- Model quality remains `not_evaluable` (scripted/stub provider).

No commit/push.
