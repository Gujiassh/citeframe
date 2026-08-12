# D-OPS Lane Report

Date: 2026-08-11
Lane: D-OPS (D003 deployment/restart/backup/restore evidence harness)
Source SHA baseline: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`
Worktree: `/home/cc/code/citeframe`
Contract impact: **none** (infra harness + report schema only; no API/Worker/Web/business contract change)
Commit/push: **not performed**

## Goal alignment

Audit existing deployment/restart/backup/restore harnesses for V5-D D003 readiness
and determine whether a mixed PDF/Image/Document acceptance runner already exists
or can be drafted as a thin wrapper reusing v5b/r800 without changing contracts.

## 1. Gap analysis

### Inventory (existing, reusable)

| Asset | Path | Role for D003 |
|---|---|---|
| Shared compose helpers | `infra/scripts/compose-common.sh` | env/project validation, health wait, minio client, compose file stack |
| Production backup | `infra/scripts/backup-deployment.sh` | stop writers → pg_dump + MinIO mirror → FORMAT_VERSION=2 + `BACKUP_CONTRACT=document-modality-v1` + closed SHA256SUMS |
| Empty-target restore | `infra/scripts/restore-deployment.sh` | preflight (manifest/contract/checksum/empty DB/Redis/bucket) → restore → migration → start apps |
| Backup/restore unit | `infra/scripts/test-backup-restore.sh` | offline preflight/unit oracle (no live docker required for most cases) |
| Document live gate | `infra/scripts/run-v5b-document-acceptance.sh` + `infra/docker/compose.v5b.yml` | isolated build, Document seed, browser before/after, backup/restore, dual-asset semantic verify, zero-residue |
| Research live gate | `infra/scripts/run-r800-acceptance.sh` + `infra/docker/compose.r800.yml` | isolated Research scenarios + backup/restore + semantic identity; scripted provider only |
| Historical PDF/Image | `infra/scripts/run-m403-acceptance.sh` + `compose.m403.yml` | PDF/Image restore oracle (pre-Document); still useful as modality precedent |
| Deploy base | `infra/docker/compose.deploy.yml` | production profile (images, health, Caddy, migration) |
| Mixed fixture shape | `docs/fixtures/document-modality/mixed-workspace.manifest.json` | PDF+Image+Document shape only; not a live seed CLI |

### What already passes D003-adjacent needs

- **Backup/restore contract** is strict and shared: FORMAT_VERSION=2, document-modality-v1 typed table keys, closed checksum set, empty-target restore only, no symlink/special files.
- **Full `pg_dump` + MinIO mirror** already covers PDF/Image core tables and Document typed tables when present; no contract change required for mixed content.
- **Worker `health=null` is accepted** in V5-B runner report logic (must not be treated as failure).
- **Zero-residue teardown** patterns exist in v5b and r800 runners (containers/volumes/networks/env/images).
- **No `compose.v5d.yml` is required**: v5b/r800 provider-stub overlays on `compose.deploy.yml` are sufficient.

### Gaps (blockers / partials)

| ID | Severity | Summary | Status |
|---|---|---|---|
| G-MIXED-LIVE-SEED | high | No live seed/snapshot/verify CLI for one Workspace with PDF+Image+Document together | open — blocks full D-G6 mixed identity |
| G-MIXED-BROWSER | medium | No infra-wired production-start Playwright that replays mixed three-modality after restore | open — D-WEB e2e + D-OPS wire |
| G-RESTART-LIVE | medium | No dedicated live Compose API/Worker/Web restart harness; D-G5 relies on API/Worker tests + backup window stop/start | open if unit evidence insufficient |
| G-COMPOSE-V5D | low | No compose.v5d.yml | accepted-reuse of v5b/r800 |
| G-BACKUP-CONTRACT | info | Contract stays document-modality-v1 | pass-no-change |

### Can a mixed runner be a thin wrapper?

**Yes, for orchestration/static readiness.**  
**Not yet for true mixed live identity.**

Safe approach taken:

1. Static wrapper reuses existing scripts, fixtures, and contract guards.
2. Optional live modes only call `run-v5b-document-acceptance.sh` and/or `run-r800-acceptance.sh`.
3. Report explicitly marks `mixedPdfImageDocumentLive=blocked` and `modelQualityGate=not_evaluable`.
4. No new backup keys, no relaxed health/restore preflight, no business seed invented in infra.

When D-API-WORKER provides a mixed seed/snapshot/verify CLI, D-OPS can add a thin live mode that seeds once and reuses the same backup/restore scripts.

## 2. Deliverables created (infra only)

| Path | Purpose |
|---|---|
| `infra/scripts/run-v5d-mixed-acceptance.sh` | Mixed acceptance entrypoint skeleton (`static-only` default; `document`/`research`/`both`/`skeleton`) |
| `infra/scripts/v5d-mixed-acceptance.report.schema.json` | Artifact report schema (`v5d-mixed-deployment-acceptance-v1`) |
| `infra/README.md` | Documents V5-D mixed entrypoint and reuse map |
| `docs/evals/artifacts/v5d-20260811-01/d-ops-lane-report.md` | This report |
| `docs/evals/artifacts/v5d-20260811-01/d-ops-gap-analysis.json` | Machine-readable gap + reuse map |

## 3. Explicit non-goals

- No live full Compose run in this slice (expensive; not already configured as a cheap one-shot for mixed).
- No changes to `backup-deployment.sh` / `restore-deployment.sh` contract keys.
- No new worker seed CLI, no apps/api|worker|web contract edits.
- No claim of D-G6 mixed live pass, R803 model quality, or M404 user value.
- No commit/push.

## 4. Verification (static)

Intended commands (repo root):

```bash
chmod +x infra/scripts/run-v5d-mixed-acceptance.sh
for s in \
  infra/scripts/run-v5d-mixed-acceptance.sh \
  infra/scripts/backup-deployment.sh \
  infra/scripts/restore-deployment.sh \
  infra/scripts/run-v5b-document-acceptance.sh \
  infra/scripts/run-r800-acceptance.sh \
  infra/scripts/compose-common.sh \
  infra/scripts/test-backup-restore.sh; do
  bash -n "$s" || exit 1
done
infra/scripts/test-backup-restore.sh
infra/scripts/run-v5d-mixed-acceptance.sh \
  --mode static-only \
  --output-dir docs/evals/artifacts/v5d-20260811-01/d-ops-static
```

### Execution note

This D-OPS worker completed static **authoring and audit** under a tool surface without a shell executor, so the commands above were not live-run inside the worker process. Main controller / local host should run the block once; expected outcomes:

| Check | Expected |
|---|---|
| `bash -n` on all listed scripts | exit 0 |
| `test-backup-restore.sh` | prints `backup_restore_unit_tests_passed` |
| `run-v5d-mixed-acceptance.sh --mode static-only` | exit 0, `engineeringGate=static-pass`, `lanes.mixedPdfImageDocumentLive.status=blocked` |
| report files | `gap-analysis.json`, `static-checks.json`, `report.json`, `state.json` under output dir |

No live Compose (`--mode document|research|both`) was run (by design for this slice).

## 5. Residual risks

1. **D-G6 mixed live** remains blocked until mixed seed/snapshot/verify exists.
2. Document-only or Research-only live green must not be re-labeled as mixed three-modality restore.
3. D-G5 live restart still depends on API/Worker suite evidence; infra only proves backup stop/start writers.
4. Live `document`/`research` modes are expensive (build + compose + restore) and should be scheduled by D-ACCEPT, not habitually by static D-OPS.
5. Dirty worktree contains V5-C + V5-D docs; D-OPS must not touch unowned paths (complied).

## 6. Next handoff

- **D-API-WORKER**: optional mixed deployment seed/snapshot/verify CLI if D-G6 requires single-workspace three-modality identity beyond existing unit tests.
- **D-WEB**: mixed production-start Playwright for restore replay (desktop/mobile).
- **D-ACCEPT**: may run `--mode document` and/or `--mode research` for engineering restore evidence; must keep mixed live gate blocked until gap closed.
- **D-DOCS**: link this report and entrypoint from runbook when finalizing D004.

## 7. Gate status (D-OPS view)

| Gate | D-OPS status | Note |
|---|---|---|
| D-G5 restart/delete/recovery | partial | harness/static ready; live restart oracle not added |
| D-G6 live deployment/restore | partial / blocked for mixed | document + research runners reusable; mixed identity blocked |
| Contract/save impact | none | backup contract unchanged |
