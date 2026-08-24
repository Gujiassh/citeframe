# A2a Research Persistence Critical Audit

Date: 2026-08-24
Reviewed snapshot: `20d411ebf60b755c4ef3308e269591b19209e4eb`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
Verdict: **REWORK (High=1, Medium=5, Low=1)**

## Semantic Oracle

A2a is an extraction slice, not a behavior-change slice. Acceptance requires all of the
following statements to be true and executable:

- schema, public API, save, replay, permission, Step/Attempt/Claim, lease/fencing,
  retry/cancel/reclaim/recovery, provider/tool accounting, payload, and Event row/byte
  meanings are equal to `d1b5945`;
- one Worker `process_one` still drives the existing fixed multi-step LangGraph, including
  planner publication, researcher work, conflict waiting, join, and final publication;
- current mixed lock acquisition is preserved; A2a does not implement R0 normalization or
  R1 single-attempt dispatch;
- `citeframe_research_persistence` is the neutral owner of the approved Research
  repositories/UoW/commands/locks boundary and imports no API/Worker implementation;
- legacy compatibility facades preserve required symbol identity, call signatures, and
  monkeypatch/adapter behavior;
- manifests, locks, hash-pinned exports, Docker source-copy/PYTHONPATH, image import smoke,
  CI, SSoT, specs, and workbench describe and test the same delivered state.

## Findings

### High

1. **The `_locked_attempt` facade breaks the baseline calling contract and terminates real multi-step Research execution.**

   [`research_worker_lease.py`](../../../../apps/api/src/ai_pdf_api/services/research/research_worker_lease.py#L201)
   changes the baseline signature from `_locked_attempt(db, *, ...)` to
   `_locked_attempt(*, db, ...)`. Existing production callers still pass `db` positionally:
   [`research_worker_plan.py`](../../../../apps/api/src/ai_pdf_api/services/research/research_worker_plan.py#L45)
   and
   [`research_worker_publication.py`](../../../../apps/api/src/ai_pdf_api/services/research/research_worker_publication.py#L46).
   The later conflict-publication path has the same call at line 371.

   Current snapshot evidence is `9 failed, 62 passed`; all nine failures raise
   `TypeError: _locked_attempt() takes 0 positional arguments but 1 positional argument ...`.
   The same three baseline test files at `d1b5945` pass `44/44`. The Worker fixed-graph
   suite passes `37/37`, but those tests use fake/adapter paths and do not exercise the real
   LangGraph-to-API publication facade. A normal planner/final publication therefore fails
   before its lease validation and DB mutation, and `process_one` converts the error into a
   non-retryable `research_execution_failed` step outcome.

### Medium

1. **The canonical neutral command/UoW ownership is incomplete and duplicated.**

   The accepted design requires the neutral package to own claim, lease refresh/reclaim,
   handler completion, cancellation, provider/tool reserve/send/reconcile, conflict/join
   readiness, and artifact publication commands
   ([`research-boundary-runtime-design.md`](../research-boundary-runtime-design.md#L115)).
   [`commands.py`](../../../../packages/research-persistence/src/citeframe_research_persistence/commands.py#L10)
   exposes only a subset. Planning publication, handler completion/state, artifact
   publication, retry/cancel, and related DB transitions remain in API modules.
   `finalize_cancel_if_idle` is independently implemented in both
   [`research_runs.py`](../../../../apps/api/src/ai_pdf_api/services/research/research_runs.py#L481)
   and
   [`membership.py`](../../../../packages/research-persistence/src/citeframe_research_persistence/membership.py#L11).
   `ResearchUnitOfWork` and `ResearchRepository` have no production consumer, while neutral
   commands continue to commit internally and Worker `_ApiPort` still owns the Session
   lifecycle. This is not the single transition/UoW owner described by the design and leaves
   two implementations free to drift.

2. **The A2a golden is a hand-authored static file, not the required old/new behavior oracle.**

   [`test_research_persistence_boundary.py`](../../../../apps/api/tests/test_research_persistence_boundary.py#L68)
   only hashes JSON, checks two case names, and asserts that `dbRows`, `payloads`, and
   `events` are non-empty. It never runs baseline or snapshot commands, `process_one`, or a
   database; it does not generate or compare DB rows, payload bytes, Event bytes,
   retry/cancel/reclaim/recovery, save/replay, or permission results. It remains green while
   finding H1 breaks the real flow. This does not satisfy the A2a exit gate at
   [`research-boundary-runtime-design.md`](../research-boundary-runtime-design.md#L465).

3. **Docker/CI evidence is textual and can pass when the production image is invalid.**

   [`ci.yml`](../../../../.github/workflows/ci.yml#L49) syncs, imports packages from the
   repository environment, and runs tests/exports, but never builds the API or Worker Docker
   target. The Docker test at
   [`test_deploy_dependencies.py`](../../../../apps/api/tests/test_deploy_dependencies.py#L101)
   uses substring membership and accepts commented-out `COPY` lines. A mutation that
   comments all twelve backend-package `COPY` instructions leaves zero effective copies yet
   still passes that test. Because CI discovers the whole test directory rather than naming
   a non-removable deploy gate, deleting the test also removes the protection. No current
   clean-image A2a runtime proof was obtained: local Docker build attempts were blocked by a
   Docker Hub timeout.

4. **CI can repair a stale lock before checking the frozen export.**

   API and Worker jobs use non-frozen `uv sync` at
   [`ci.yml`](../../../../.github/workflows/ci.yml#L49) and line 70, then diff only
   `requirements.deploy.txt`. A mutation that changes a manifest constraint without its lock
   makes `uv lock --check` fail, but the CI-equivalent `uv sync` updates the lock and the
   canonical export/test sequence passes without any lock diff. Current locks themselves do
   pass `uv lock --check`; the defect is that CI does not prove committed lock freshness.

5. **Durable status and implementation evidence disagree with the reviewed snapshot.**

   [`plan.md`](../plan.md#L51) and
   [`research-boundary-runtime-design.md`](../research-boundary-runtime-design.md#L520)
   still call A2a the next implementation step even though their nearby current status and
   `tasks.md` say it is implementer-complete pending review. Workbench state still records the
   old branch, omits several A2a delivery artifacts, and retains verification values saying
   no A2a code exists. The implementation report records four boundary tests while the
   current suite has five, and claims `git diff --check: pass`; the actual reviewed range
   reports trailing blank lines in `test_persistence_boundary.py` and
   `citeframe_persistence/models/evidence_locator.py`. These contradictions make the
   delivery ledger unsuitable as Critical acceptance evidence.

### Low

1. **The compatibility facade does not preserve the complete baseline symbol surface.**

   Baseline names missing from their legacy modules include
   `research_idempotency._persisted_error_payload`,
   `research_idempotency._frozen_error`, `research_worker_lease._lease_step`,
   `research_worker_lease._queue_ready_dependents`, and
   `research_worker_tools.ToolResultCallback`. No in-repository consumer was found, so this
   is not independently production-blocking, but it contradicts the implementation report's
   claim that private compatibility helpers remain. The rework should either preserve each
   real compatibility seam with an identity/signature test or explicitly prove and document
   why it is not part of the supported facade.

## Review Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | **blocked** | Extraction changes runtime behavior and does not complete the approved neutral owner boundary. |
| User-visible flow/timing | **fail** | Planner and final publication terminate with `TypeError`. |
| Schema/DDL identity | **pass** | Persistence boundary suite passes; the accepted 80-table/93-index fixture remains unchanged. |
| API/save/replay/permission semantics | **blocked** | No executable old/new oracle exists, and the real flow fails before completion. No authorization exists to reinterpret these semantics. |
| Fixed LangGraph multi-step shape | **pass statically; fail end-to-end** | Worker graph suite is `37/37`, but real publication facade fails. No R1 topology was introduced. |
| Mixed lock behavior | **pass statically** | No R0 normalization was found; the known mixed order remains. Runtime lock-path equivalence is blocked by H1 and the missing oracle. |
| Neutral package ownership/UoW | **fail** | Commands and cancellation remain split/duplicated; UoW/repository are unused. |
| Compatibility facade | **fail** | `_locked_attempt` ABI regression; additional legacy symbols are absent. |
| Dependencies/lock/export | **current files pass; CI gate fails** | Current locks/exports and focused package tests pass, but non-frozen sync can conceal stale locks. |
| Docker/runtime packaging | **blocked** | Source-copy file is present, but no current clean-image build/runtime proof; textual test can false-pass. |
| Test honesty | **fail** | Static golden cannot observe the production regression. |
| SSoT/spec/workbench | **fail** | Current-state, branch, artifacts, counts, and range hygiene evidence conflict. |
| Reverse review | **fail** | Assuming a facade regression, the named golden/Worker tests did not detect it; H1 is the concrete counterexample. |

## Verification Evidence

Current snapshot:

```text
uv run --project apps/api pytest -q \
  apps/api/tests/test_research_worker_lease_plan.py \
  apps/api/tests/test_research_worker_budget_recovery.py \
  apps/api/tests/test_research_router_basic.py \
  apps/api/tests/test_research_router_recovery.py \
  apps/api/tests/test_research_worker_evidence_publication.py \
  apps/api/tests/test_research_router_artifacts.py

9 failed, 62 passed
```

Baseline, extracted with `git archive d1b5945` and run with the same Python environment:

```text
pytest -q \
  apps/api/tests/test_research_worker_lease_plan.py \
  apps/api/tests/test_research_worker_budget_recovery.py \
  apps/api/tests/test_research_worker_evidence_publication.py

44 passed
```

Other current gates:

```text
uv run --project apps/api pytest -q \
  apps/api/tests/test_research_persistence_boundary.py \
  apps/api/tests/test_persistence_boundary.py \
  apps/api/tests/test_deploy_dependencies.py

17 passed, 1 warning

uv run --project apps/worker pytest -q \
  apps/worker/tests/test_deploy_dependencies.py \
  apps/worker/tests/test_research_contracts_package.py

6 passed

uv run --project apps/worker pytest -q \
  apps/worker/tests/test_research_executor.py \
  apps/worker/tests/test_research_runtime.py \
  apps/worker/tests/test_research_runtime_integration.py

37 passed
```

`compileall` passed for API, Worker, and Research persistence sources. Current API and
Worker locks pass `uv lock --check`. All three local distributions can be built as wheels,
installed into a clean Python 3.12 environment, imported from `site-packages`, and pass
dependency checking. These passing results do not override H1 or the missing behavioral and
image gates.

## Minimum Rework Boundary

1. Restore every required compatibility facade's baseline identity and callable signature,
   starting with `_locked_attempt(db, *, attempt_id, lease_token, now)`, and add direct
   positional/keyword/monkeypatch tests.
2. Complete the already-approved A2a neutral command/UoW ownership: move the remaining
   DB-only transition commands behind one neutral implementation, remove duplicate API
   transitions, and make the actual Worker/API composition use the intended UoW/session
   owner. Keep storage/provider/retrieval/observability adapters outside the neutral package.
3. Replace the static golden with an executable differential oracle that runs the same real
   fixtures against `d1b5945` and the reworked snapshot and compares normalized DB rows,
   exact payload/Event bytes, lease/fencing, retry/cancel/reclaim/recovery, permission, and
   multi-step `process_one` outputs.
4. Make deployment gates executable: use frozen lock validation before sync, diff both lock
   and export artifacts, build both Docker targets in CI, and run final-image import/path/
   non-root smoke. Do not rely on comment-sensitive substring tests.
5. Reconcile specs, SSoT, implementation evidence, workbench branch/artifacts/verification,
   and range hygiene to the actual rework snapshot. Do not mark A2a accepted before the
   independent re-audit.

Do not change schema, public API, save/replay/permission meaning, mixed lock order, or fixed
multi-step execution. Do not implement R0 or R1 while fixing A2a.

## Acceptance Commands

At minimum, the next independent review must run and retain results for:

```bash
uv lock --project apps/api --check
uv lock --project apps/worker --check
uv sync --project apps/api --frozen --extra dev
uv sync --project apps/worker --frozen --dev

uv run --project apps/api pytest -q apps/api/tests
uv run --project apps/worker pytest --strict-markers -q \
  -m "not acceptance and not evaluation" apps/worker/tests
uv run --project apps/worker pytest --strict-markers -q -m acceptance apps/worker/tests
uv run --project apps/worker pytest --strict-markers -q -m evaluation apps/worker/tests

uv export --project apps/api --frozen --no-dev --format requirements.txt \
  --no-emit-project --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --output-file apps/api/requirements.deploy.txt
uv export --project apps/worker --frozen --no-dev --format requirements.txt \
  --no-emit-project --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --no-emit-package ai-pdf-api \
  --output-file apps/worker/requirements.deploy.txt
git diff --exit-code -- apps/api/uv.lock apps/worker/uv.lock \
  apps/api/requirements.deploy.txt apps/worker/requirements.deploy.txt

docker build --target api -f infra/docker/Dockerfile.python -t citeframe-a2a-api-audit .
docker build --target worker -f infra/docker/Dockerfile.python -t citeframe-a2a-worker-audit .
docker run --rm --entrypoint python citeframe-a2a-api-audit -c \
  'from pathlib import Path; import citeframe_contracts, citeframe_persistence, citeframe_research_persistence; assert "/app/apps/api" not in str(Path(citeframe_research_persistence.__file__).resolve())'
docker run --rm --entrypoint python citeframe-a2a-worker-audit -c \
  'from pathlib import Path; import os, citeframe_contracts, citeframe_persistence, citeframe_research_persistence; assert os.getuid() == 10001; assert "/app/apps/api" not in str(Path(citeframe_research_persistence.__file__).resolve())'

# The reworked test must execute both baseline and candidate behavior, not hash static JSON.
uv run --project apps/api pytest -q apps/api/tests/test_research_persistence_boundary.py
git diff --check <rework-starting-sha>..HEAD
```

## Next Gate

A2a remains **implementer-complete but not accepted**. R0/R1/R2/W1 and downstream slices
remain blocked. After the bounded rework and durable evidence update, run a new independent
Critical audit against one immutable snapshot; only an `ACCEPT` with executable old/new and
clean-image evidence may unlock R0.
