# A1 Contracts Implementation Evidence

- Date: 2026-08-20
- Source branch: `work/docs-stale-honesty-20260817`
- Starting ref: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
- Delivery state: implementation complete by implementer; no commit and no push
- Review state: **design re-audit ACCEPT (High=0, Medium=0, Low=0); independent A1 implementation Critical review ACCEPT (2026-08-20); A1 accepted**

## Scope

A1 creates only `citeframe-backend-contracts` / `citeframe_contracts`. The package
contains the extracted pure Research DTOs, exceptions, TypedDicts, and Protocols from
`ai_pdf_worker.research_executor_contracts`, plus a neutral structural
`EvidenceToolRegistryProtocol`. The legacy worker module re-exports the same class objects.
API/Worker manifests, locks, third-party-only deployment exports, Docker source-copy and
CI/import smoke were updated for this package only. No persistence package was created.

The existing concrete `ai_pdf_worker.research_executor_tools.EvidenceToolRegistry` remains
the implementation and remains publicly exported by `ai_pdf_worker.research_executor`; only
the contract annotation is neutralized. Schema, API payloads, save/replay, permissions,
SSE, provider behavior, storage, retrieval, ORM ownership, and Research runtime dispatch
semantics were not changed.

## Contract Oracle

- New and legacy symbols are identity-equal for every exported contract symbol.
- Representative frozen dataclasses preserve equality, field order, defaults, and
  `dataclasses.asdict` output. Exception inheritance and Protocol signatures retain their
  prior meaning; the registry surface is structural (`search` and `load`).
- Contracts source AST imports only standard-library modules; its manifest has no runtime
  dependencies; isolated `python -I` import succeeds with only `packages/backend-contracts/src`
  on `sys.path`.
- API and Worker each declare only the contracts local path source. No persistence or
  research-persistence package appears in manifests, locks, Docker, or smoke paths.
- Deploy requirements omit local distributions and contain no editable/file-path entries.

## Verification

- `uv lock --project apps/api && uv lock --project apps/worker`: passed
- A1 frozen exports using `--format requirements.txt`: passed for API and Worker
- `uv sync --project apps/api --frozen --extra dev`: passed
- `uv sync --project apps/worker --frozen --dev`: passed
- API deploy/purity/Docker/CI assertions: 6 passed
- Worker deploy/identity/protocol assertions: 5 passed
- `uv run --project apps/worker pytest -q apps/worker/tests/test_research_executor.py`: 12 passed
- `uv run --project apps/worker pytest -q apps/worker/tests/test_research_runtime.py apps/worker/tests/test_research_runtime_integration.py apps/worker/tests/test_research_v5c_agent_io.py`: 35 passed
- `uv run --project apps/api pytest -q apps/api/tests/test_research_router_recovery.py apps/api/tests/test_document_api_contract.py`: 44 passed
- `python3 -m compileall -q packages/backend-contracts/src apps/worker/src apps/worker/tests apps/api/tests`: passed
- `git diff --check`: passed
- `docker build --target api -f infra/docker/Dockerfile.python -t citeframe-a1-api:local .`: passed; final-stage smoke passed
- `docker build --target worker -f infra/docker/Dockerfile.python -t citeframe-a1-worker:local .`: passed; final-stage smoke passed
- API container smoke: `api-runtime-contracts-smoke=pass`
- Worker container smoke: `worker-runtime-contracts-smoke=pass`

## Rework Verification (2026-08-20)

- API deployment/purity/Docker/CI assertions after per-stage/per-job test tightening: 6 passed
- Worker deployment/identity/structural-protocol assertions after concrete-registry coverage: 5 passed
- Worker executor regression: 12 passed; Worker Research runtime selections: 35 passed; API Research selections: 44 passed.
- Contracts purity now has a positive standard-library import-root allowlist, manifest `dependencies=[]`, and isolated `python -I` source-only import proof.
- Docker and CI tests assert named API/Worker stage or job boundaries, exact local-package omit sets, stage-specific `PYTHONPATH`, contracts import smoke, and no later package paths without global text counts.
- CI API/Worker export commands now match canonical generated header order (`--format requirements.txt`, then `--no-emit-project`, then local omit flags, then output path); exact commands reran against both requirement files and `git diff --exit-code` passed.
- Frozen API and Worker exports, compileall, Markdown links/fences, and `git diff --check` passed; both Docker targets built and final runtime smokes passed.
- Current-state docs and workbench records report design re-audit `ACCEPT (High=0, Medium=0, Low=0)`, A1 independently accepted on `2026-08-20`, and A1b/A2-foundation implementer-complete with independent Critical review pending. Historical rejected rounds remain historical only.

## Documentation Rework (2026-08-20)

- Corrected `docs/architecture/database-design.md` to distinguish implementer-complete A1 contracts from the independent A1 implementation ACCEPT recorded on 2026-08-20.
- Recorded that A1b/A2-foundation is implementer-complete with independent Critical review pending; A2a/R0/R1/R2/W1 and downstream slices remain unimplemented and blocked.
- Reviewer-owned Critical audit artifacts remain unchanged; no schema/API/save/replay/permission changes are authorized.

## Remaining Gate

Independent review accepted A1 on `2026-08-20` after re-checking goal alignment, package
purity, old/new identity, manifest/export omission, Docker stage boundaries, tests, SSoT
synchronization, and the no-data-contract-change oracle. A1b/A2-foundation is implementer-complete with independent Critical review pending. A2a, R0,
R1, R2, W1, A3-A6, G/M/P, paid evaluation, and
user research remain unstarted or blocked as defined by the parent specification; no
schema/API/save/replay/permission changes are authorized.
