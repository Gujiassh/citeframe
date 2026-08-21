# A1b/A2-Foundation Persistence Critical Audit

- Date: 2026-08-21
- Auditor: independent reviewer
- Baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
- Reviewed state: current shared unstaged tracked diff and untracked files
- Risk class: **Critical** (`P0` persistence/deployment contract)
- Initial verdict: **REJECT (High=0, Medium=1, Low=0)**
- Follow-up verdict: **ACCEPT (High=0, Medium=0, Low=0)**

## Findings

### High

None.

### Medium

None. The initial Worker clean-image runtime proof gap is closed by the current final
Worker image build and independent final-runtime smoke recorded below.

### Low

None.

## Initial Finding And Rework History

The initial review rejected A1b because two current-worktree Worker builds stopped during
`pip install --require-hashes` while downloading from PyPI. Those failures were external
network failures, not evidence of a dependency hash, code, or Dockerfile defect, but they
left the final Worker filesystem and import path unproved. Static tests could not replace
a final-image smoke.

The required rework did not change code, tests, configuration, migrations, canonical SSoT,
or workbench records. It rebuilt the same current Worker target using an ephemeral
build-time network proxy. The final image contains no proxy environment variables.

## Semantic Oracle Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Goal and phase alignment | Pass | `citeframe-backend-persistence` is the sole new A1b distribution. No `citeframe_research_persistence` package exists. A2a/R0/R1/R2/W1 remain blocked pending main-controller canonical-state synchronization. |
| User-visible and Research flow | Not applicable | No route, save/API/replay/permission behavior, session/transaction owner, Research transition, lock order, or dispatcher change appears in the A1b scope. |
| Architecture and identity | Pass | The neutral package owns one `DeclarativeBase` and all 32 model modules. Normalized baseline-to-neutral source comparison found zero mismatches. Legacy Base, all model exports, and all legacy model submodules resolve to the same neutral objects/modules. |
| Data contract and Alembic | Pass | The checked-in PostgreSQL DDL fixture SHA is `678ad54b9977cc6258639b92fa65e5976d032ac323428c98ed89215cf02167af`; it equals current neutral metadata with 80 tables and 93 indexes. A fresh local `pgvector:pg17` database upgraded to `m7a8b9c0d1e2`; `alembic check` reported no new operations and the database/metadata table count was 80. Alembic directly imports `citeframe_persistence.Base` and its models. |
| Implementation quality and imports | Pass | Persistence runtime imports are limited to stdlib, SQLAlchemy, pgvector, and itself. An API-venv `python -I` source-only import passed. Focused API persistence/M403A tests, Worker package/deployment/R803 tests, and compileall passed. |
| API clean-image deployment | Pass | Current API image final runtime smoke imported `ai_pdf_api.main` and neutral persistence from `/app/packages/backend-persistence/src`, with 80 metadata tables. |
| Worker clean-image deployment | Pass | Current Worker image `sha256:3e0bfa04d2af6650f500387a74c556f7304fcfe8625fa34b488610593bbe128d` built successfully. Independent final-runtime smoke imported `ai_pdf_worker.main`, contracts, and persistence; verified the neutral path, legacy Base/model/submodule identity, 80 tables, UID `10001`, final user/workdir/CMD/PYTHONPATH, and absence of persisted proxy variables. |
| M403A/R803 provenance retargeting | Pass | The five changed files only move source paths/AST closure roots to actual neutral implementation modules. Scorer version, cases, thresholds, acceptance gates, and historical artifacts are unchanged. |
| SSoT and delivery status | Pass | This audit accepts only A1b/A2-foundation persistence. It does not accept or unblock A2a Research persistence, lock normalization, single-attempt dispatch, SSE, or data/API contract work. |

## Verification

```text
uv run --project apps/api pytest -q \
  apps/api/tests/test_persistence_boundary.py \
  apps/api/tests/test_m403a_capacity_acceptance.py \
  apps/api/tests/test_deploy_dependencies.py
25 passed, 1 existing deprecation warning

uv run --project apps/worker pytest -q \
  apps/worker/tests/test_deploy_dependencies.py \
  apps/worker/tests/test_research_contracts_package.py \
  apps/worker/tests/test_r803_campaign_v5.py
60 passed

normalized baseline model source -> neutral source
32 modules, zero mismatches

legacy Base/models/submodule runtime identity
pass

DDL fixture compile comparison
80 tables, 93 indexes, SHA matches

fresh pgvector PostgreSQL gate
upgrade to m7a8b9c0d1e2: pass
alembic check: No new upgrade operations detected
actual public table count == neutral metadata count == 80

A1b API/Worker frozen export dependency bodies
match

API final image runtime import smoke
api_final_runtime_persistence_smoke=pass
path=/app/packages/backend-persistence/src/citeframe_persistence/__init__.py

initial Worker builds
standard and host-network builds exited 2 during external PyPI downloads; no code/config change made

follow-up Worker clean-image build
docker build --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7890 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7890 \
  --build-arg NO_PROXY=localhost,127.0.0.1 \
  --target worker -f infra/docker/Dockerfile.python \
  -t citeframe-a1b-worker-audit:20260821 .
exit 0
backend-contracts-persistence-import-smoke=pass
image=sha256:3e0bfa04d2af6650f500387a74c556f7304fcfe8625fa34b488610593bbe128d

independent final Worker runtime smoke
docker run --rm citeframe-a1b-worker-audit:20260821 python -c '<A1b import/identity oracle>'
warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.
worker_final_runtime_persistence_smoke=pass path=/app/packages/backend-persistence/src/citeframe_persistence/__init__.py tables=80 uid=10001

final Worker image inspect
user=app
workdir=/app/apps/worker
cmd=python -m ai_pdf_worker.main
PYTHONPATH=/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/apps/api/src:/app/apps/worker/src
HTTP_PROXY/HTTPS_PROXY/NO_PROXY absent from final Config.Env

R803 frozen evidence comparison
non-provenance JSON equal to HEAD; cases, threshold, scorer unchanged
closure: 95 modules, 4 source roots, neutral contracts/persistence modules included

git diff --check
pass
```

## Residual Risk

- `apps/worker/tests/test_r803_campaign_v5.py` is 2,470 lines. A1b only retargets its
  provenance assertions, so this is not an A1b blocker; the existing M4 task should split
  campaign/oracle, closure-resolver, and artifact-validation responsibilities before it
  grows further.
- A2a Research persistence, lock normalization, single-attempt dispatch, SSE, and data/API
  contract work remain outside this acceptance and blocked pending main-controller state
  synchronization.
