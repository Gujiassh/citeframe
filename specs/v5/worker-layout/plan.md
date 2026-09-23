# Worker layout delivery and integration ledger

## Scope and status

Issue: [#24](https://github.com/Gujiassh/citeframe/issues/24).
Implementation branch: `work/research-layout-20260923`, based on clean commit
`50af19dc3b79fbb677d9ac66c005b77cbe76f3d9`.

The implementation groups product ingestion and research responsibilities, extracts
offline evaluation into a separately buildable Python package, and removes product
imports of evaluation diagnostics. The [SSoT](../../../docs/ssot/worker-layout.md)
defines module ownership. [file-mapping.json](file-mapping.json) records relocations
and responsibility-based splits. Existing flat modules were removed without a full
compatibility-shim layer.

Local implementation and the checks below are complete. Draft PR publication is
authorized; independent review and final acceptance remain pending. The controller
owns review assignment and merge. No main checkout source files were changed by
this lane, and this record does not certify the main checkout or functional lane.

## Invariants

- Preserve business, permission, lease/state, save and evaluation semantics.
- Preserve historical report/fixture/schema IDs, campaign files and hash evidence.
- Keep frozen-evidence search frozen, including its intentional query-independent
  selection. No retrieval strategy or conflict-investigation feature is added.
- Product contracts own `AgentResultValidationError`; evaluation observes through
  existing validator/output-observer interfaces.
- Production API/Worker packages must not import `citeframe_evaluation`, including
  lazy/dynamic imports. Production images exclude it; tooling uses an opt-in target.
- New implementation hashes identify new source. Do not overwrite, re-sign or resume
  historical campaigns as if their implementation hash were unchanged.

## Verification on the isolated baseline

Commands run from the repository root. Windows validation used existing Python 3.12
Worker/API environments with this checkout's explicit source paths, not installed
editable main-checkout sources. `PYTHONUTF8=1` and `PYTHONDONTWRITEBYTECODE=1` were set.
Raw machine-local logs remain in ignored `.local-validation/`.

| Check | Result |
|---|---|
| Pre-move focused baseline | 85 passed |
| `python -m pytest -c pytest.ini apps/worker/tests tools/evaluation/tests -q --tb=short` | 545 passed, 1 skipped (Windows directory-symlink privilege) |
| API `test_research*.py`, `test_persistence_boundary.py`, `test_r800_acceptance_runner.py`, `test_deploy_dependencies.py`, `test_layout_probe_paths.py` with root pytest config | 146 passed; existing Starlette deprecation warning |
| `python -m pytest -c pytest.ini apps/api/tests/test_a2a_differential.py apps/api/tests/test_layout_probe_paths.py -q --tb=short` using API runtime | 4 passed, including historical differential, mutation and real plugin-pollution cleanup |
| `uv build --project <project> --offline --out-dir .local-validation/dist` for backend-contracts, Worker and evaluation | Wheel and sdist builds passed |
| Extracted-wheel import and module CLI smoke | Correct wheel sources; production import without evaluator/LangGraph; 3 CLI help checks; 6 frozen cases load |
| `uv lock --project <project> --offline --check` for API, Worker and evaluation | Passed |
| `uv tool run --offline ruff check --target-version py312 --select F821,F822,F823 apps/worker/src apps/worker/tests tools/evaluation apps/api/tests/test_a2a_differential_probe.py infra/scripts` | Passed |
| Compileall for Worker/evaluation/contracts; `git diff --check` | Passed |

The frozen output oracle in `tools/evaluation/tests/fixtures/layout-baseline.json`
was captured before relocation: v4/v5, six cases each, Quick and Research (24 outputs).
Parity excludes only measured elapsed-time fields (`duration_ms`, `wall_time_ms`,
`wallTimeMs`); outputs and scores are otherwise exact.

[product-parity.json](product-parity.json) records exact equality of `semantics`,
`composition`, `schedulerEvidence` and `schemaVersion` between the clean HEAD snapshot
and migrated A2a probe. This covers the probe's normalized DB rows, serialized
event/payload bytes, permissions, lease fencing, retry/cancel/reclaim and terminal
semantics. It is not a live PostgreSQL/MinIO deployment result.

The historical A2a runner translates five probe import paths when testing its frozen
baseline. A regression test verifies that the probe AST excluding imports is
unchanged. Product modules do not carry this historical compatibility mapping.

Existing JSON/JSONL/PDF/PNG and evaluation artifact files have no changes in this lane.
Current invocation documentation and the fixture generator's active import changed;
generated historical fixtures did not.

## Outstanding acceptance

- Actual Docker builds/runs: unavailable locally; CI now includes the opt-in
  evaluation image build and entry-point/fixture smoke. Remote results must be checked.
- Real PostgreSQL/MinIO multi-worker deployment/restore and browser/UI validation.
- Live paid-model campaigns were not run or authorized by this refactor.
- Independent reviewer must validate the intended directory ownership and dependency
  direction first, then old/new output evidence, packaging/CLI/CI and integration scope.
  Findings return to the implementation owner. Merge requires controller approval
  after review, regardless of branch-protection configuration.

## Functional lane integration handoff

[feature-integration-audit.json](feature-integration-audit.json) audits the supplied
49-file frozen candidate and its baseline-relative manifest without copying source
or applying its patch. Candidate hashes and available baseline hashes match the
manifest. Five destinations change, including the proposed new
`research/adaptive_retrieval.py`; that feature module is not implemented here.

Twelve touched files already differed from clean HEAD in the candidate's inherited
baseline, even ignoring CRLF. This audit covers the 49 touched files, not all inherited
R2/W1/A3 dirty changes. Additional inherited Worker core/ports/processor/contracts and
ingestion changes must also be preserved.

Authorized integration should:

1. Freeze and retain inherited baseline plus functional delta and identify all
   inherited changes, including files outside the 49-file manifest.
2. Translate paths using the mapping; integrate split runtime ports by owning class
   into ledger/evidence/generation adapters. Do not replace functional files with
   whole files from this clean-HEAD architecture branch.
3. Apply the functional delta against its supplied baseline. Translate adaptive
   retrieval's old schema import and update all affected tests/scripts.
4. Rerun boundary, parity, functional and service/UI checks on the actual combined
   candidate. Its original UI/DB acceptance remains incomplete.
5. Keep the separately authorized conflict-investigation loop in its own Issue/PR.

## Durable records

The independent worktree's dev-workbench task is `research-layout-20260923` under
`--Code--citeframe-architecture`. Publication commit/PR and review-pending status are
recorded there after publication. This repository ledger and SSoT are the durable
project records; no private user memory is needed for this handoff.

## PR #26 review corrections

At submitted HEAD `98f78cce4bbeb324f43b02a0f24ceb4212150a50`, CI run
`35824377439` passed API, Worker fast/acceptance, Web and Web E2E jobs. Evaluation
had 109 passing tests and one failing new layout oracle; its later wheel, CLI and
evaluation-image steps were skipped. These job results do not certify the dirty
functional checkout or full service/UI acceptance.

The oracle compared a derived timing value (`parallel_speedup`) captured as null
on Windows with 1.0 on Linux. It now controls the evaluation research module's
nanosecond clock and checks both zero-duration (null) and nonzero-duration (1.0)
paths. It independently asserts that timing value, adjusts only that field in the
in-memory expected record, and strictly compares all remaining output, evidence,
score and failure fields. The captured fixture bytes and runtime formula are
unchanged; measured elapsed fields remain the three previously documented exclusions.

Independent review also identified that the opt-in evaluation image's default help
command would be inherited by the R800 worker service. `compose.r800.yml` now
explicitly starts `python -m ai_pdf_worker.main`; explicit one-off acceptance CLI
commands continue to override it. A regression checks the image/Compose command
contract and the shared override used by backup/restore. This was a static finding,
not a locally reproduced Docker failure. Actual isolated restore followed by worker
task consumption remains an outstanding acceptance check.

Correction verification: `python -m pytest -c pytest.ini tools/evaluation/tests
apps/api/tests/test_r800_acceptance_runner.py
apps/worker/tests/test_architecture_boundaries.py -q --tb=short` passed with
**122 passed, 1 skipped** (Windows directory-symlink privilege); the existing
Starlette deprecation warning remains. The controlled-clock parity test covers all
24 outputs in each timing mode. Remote CI must rerun the previously skipped gates.
