# D-API-WORKER Lane Report

Date: 2026-08-11T07:06:13.429997+00:00
Lane: D-API-WORKER
Source SHA baseline: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`
Worktree: `/home/cc/code/citeframe`
Contract impact: **none** (tests/fixture only; no schema/API/save/replay change)

## Goal alignment

Close D001 mixed PDF/Image/Document scope and retrieval regression gaps on the
existing Asset/Evidence/Chat contracts. Add a first F1 role-binding metadata
oracle without enabling a new registry version; the controller review must still
verify concrete runtime mappings before calling F1 closed.

## Changes

### `apps/api/tests/test_multimodal_retrieval.py`

- Extended mixed session fixture from PDF+Image to PDF+Image+Markdown Document
  with typed `document_anchor` / `document_text_chunk` / integrity hashes.
- Hybrid retrieval now asserts all three kinds, typed locators, selected-scope
  document-only results, and unique-location fusion including document.
- Quick Chat freeze test renamed and extended to all-ready mixed citations,
  document selected scope, and selected order including document.
- PostgreSQL mixed oracle asserts document presence with unique-location limits.
- Fixed asset ID collision with document fixture (`000...300`).

### `apps/api/tests/test_research_v5c_contract.py`

- Added `test_f1_executable_registry_role_mapping_oracle` freezing production v1
  and legacy-v0 role-binding metadata (schema/validator/adapter/projection/prompt).
  This is a baseline guard, not a complete concrete runtime mapping oracle;
  `docs/evals/v5d-critical-review-20260811.md` records the remaining F1 review
  finding.

## Verification

| Command | Result |
|---|---|
| `uv run --project apps/api python -m pytest apps/api/tests/test_multimodal_retrieval.py apps/api/tests/test_research_v5c_contract.py::test_f1_executable_registry_role_mapping_oracle -q` | **12 passed** |
| `uv run --project apps/worker python -m pytest apps/worker/tests/test_v5b_mixed_workspace.py -q` | **5 passed** |
| `uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests` | passed |
| `uv run --project apps/worker python -m compileall -q apps/worker/src apps/worker/tests` | passed |

## Explicit non-goals

- No new modality, locator, registry version, provider selector, or save semantics.
- No production code path changes in this lane.
- No commit/push.

## Residual risks

- Full API/Worker suite not re-run in this slice (focused suites only).
- F5 live pre-V5-C historical-row bytes/hash remains deferred (no new registry).
- Production-start Playwright mixed desktop/mobile is D-WEB ownership.
- Live PostgreSQL/MinIO restore mixed acceptance is D-OPS ownership.

## Next handoff

- D-WEB: mixed desktop/mobile production-start coverage
- D-OPS: mixed restore harness entry
- D-DOCS: runbook + progress writeback
- D-ACCEPT: full matrix after lanes land
