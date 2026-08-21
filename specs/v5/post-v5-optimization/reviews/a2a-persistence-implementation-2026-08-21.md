# A2a Research Persistence Implementation Evidence

Status: **implementer-complete; independent Critical review pending**
Date: 2026-08-21
Scope: `citeframe-research-persistence` / `citeframe_research_persistence` only.
No commit or push was made.

## Boundary

- Added the neutral Research persistence distribution under `packages/research-persistence`.
- Its runtime imports are limited to stdlib, SQLAlchemy, `citeframe_contracts`, and `citeframe_persistence`; it does not import `ai_pdf_api`, `ai_pdf_worker`, storage, providers, retrieval, observability, or agent registry implementations.
- Extracted DB-only error/idempotency, event append, failure and accounting policy, Research persistence DTOs, evidence fingerprints, membership cancellation audit, lease/attempt/fencing helpers, provider/tool ledger commands, repositories, UoW, and current lock primitives.
- Kept API-only planning/execution reads, artifact publication, provider capability resolution, retrieval, storage, and observability in the API composition layer.
- API compatibility facades preserve legacy import paths and object identity for the neutral primitives. Public lease claim/heartbeat/complete commands use the neutral implementation while API-only reads and private compatibility helpers remain in the API facade.
- Worker continues to use the existing service protocol and fixed LangGraph multi-step runtime. No R0 lock normalization, R1 dispatcher, schema, migration, public API, save/replay, permission, or `ResearchState` contract change was made.

## Golden Oracle

The deterministic pre/post fixture is `apps/api/tests/fixtures/citeframe-a2a-research-golden.json`. It covers a multi-step `process_one` shape and retry/cancel/reclaim/recovery rows, payloads, and event sequences. The fixture is hash-pinned by `apps/api/tests/test_research_persistence_boundary.py`; an independent reviewer must run the old/new behavioral comparison against the immutable fixture before acceptance.

## Verification

- `uv run --project apps/api pytest -q apps/api/tests/test_research_persistence_boundary.py`: 4 passed.
- `uv run --project apps/api pytest -q apps/api/tests/test_persistence_boundary.py`: 6 passed.
- `uv run --project apps/api pytest -q apps/api/tests/test_deploy_dependencies.py`: 6 passed.
- `uv run --project apps/worker pytest -q apps/worker/tests/test_deploy_dependencies.py`: 2 passed.
- Research lease/budget/recovery regression: 30 passed before compatibility facade wiring; targeted private-helper compatibility regression: 2 passed after wiring.
- Neutral package AST compile and import smoke: pass; 80 neutral metadata tables load, and no API/Worker modules enter `sys.modules` in isolated import smoke.
- `git diff --check`: pass.

## Pending Critical Review

The independent reviewer must verify exact old/new DB rows, payloads, event bytes, retry/cancel/reclaim/recovery behavior, API/Worker command identity, and the provider/tool composition-port boundary. This artifact deliberately does not claim `ACCEPT`.
