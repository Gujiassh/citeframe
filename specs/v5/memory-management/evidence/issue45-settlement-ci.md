# Issue45 settlement — dedicated PostgreSQL CI developer evidence

Date: 2026-09-29. Scope: new workflow and this new evidence only. Status: directed rework candidate for the original independent reviewer after F45-CI-1/F45-CI-2; closure review and hosted execution remain pending. Product review does not approve this workflow by inheritance.

## Files and frozen boundary

New files:

- `.github/workflows/research-memory-settlement.yml`
- `specs/v5/memory-management/evidence/issue45-settlement-ci.md`

No shared workflow, product, test, product evidence, manifest, lock file or Git state was changed in this CI slice. Existing uncommitted settlement files remain the frozen review candidate. Before/after checks retain:

| Protected artifact | SHA-256 |
| --- | --- |
| packages/research-persistence/src/citeframe_research_persistence/tools.py | F8E02EB6C9F93DED10BF59C9B136168130591FC49B4DED0041E6115530230A51 |
| packages/research-persistence/tests/test_memory_tool_settlement.py | 787ED87A226F26D928C2F7505A444235F4EB658E9C252719956FFAB5F9DC27E8 |
| specs/v5/memory-management/evidence/issue45-settlement.md | F3021C394463BB9FCC0F8255F37EADA1EEFBF899C135EE633ED92561F939E1B6 |
| .github/workflows/ci.yml | 363F81520750D14E74091D97CF63DC37194E9281A69DCBEE168F171C2CE8A2FD |
| apps/api/pyproject.toml | 17A546289BAD50C1C07BBF315CEA01292140DE70A36BF453E2F21FC5DE9FB115 |
| apps/api/uv.lock | F68143541ABFFDE4AF5F61F63EA2293E7EE5AC7E5150BF61A5DF58B3745C6CF0 |

The controller retains the settlement Critical review with `agt_26025b40` and will separately assign this workflow to the original reviewer. No unreceived product finding was anticipated or patched.

## Workflow behavior

- Normal `pull_request` and main-branch push triggers; `contents: read`; no path filter, conditional test bypass or continue-on-error.
- Fresh Ubuntu job, Python **3.12**, dedicated **postgres:17.11** service and health check.
- Service creates exactly `citeframe_issue45_settlement_test` with an ephemeral CI-only account. Required URL is supplied as `CITEFRAME_ISSUE45_POSTGRES_URL`; preflight rejects missing URL, wrong driver/host/port/database, failed connection or wrong server version. No external/production database is consulted.
- Default `actions/checkout@v4` shallow behavior is retained. There is no full-fetch requirement or Git-history lookup.
- Frozen API dependency setup is explicit, before test execution:

```sh
uv lock --project apps/api --check --python 3.12
uv sync --project apps/api --frozen --extra dev --python 3.12
```

- Subsequent execution uses `uv run --project apps/api --frozen --no-sync python`; a fresh job-local environment under runner.temp prevents host/sibling virtualenv reuse. No dependency downgrade, unlocked reinstall, package-index substitution or lock edit is used.
- PYTHONPATH contains only source/test paths under github.workspace. Imports of API, Worker, contracts, persistence, research persistence and memory-service are checked against their corresponding checkout roots before and after tests. Tools/projection modules and the fixture plugin receive exact-file checks. PEP 420 namespaces are checked through all their search paths; a missing file attribute does not exempt a module from origin checking.
- Pytest plugin autoload is disabled. `--noconftest` plus the existing explicit `research_worker_test_support` plugin supplies the native fixtures without unrelated router conftests. `addopts`/pythonpath overrides are cleared; strict markers and strict xfail are enabled.

The explicit final collection is:

| File | Required cases |
| --- | ---: |
| packages/research-persistence/tests/test_memory_tool_settlement.py | 56 |
| apps/api/tests/test_research_worker_budget_recovery.py | 22 |
| apps/api/tests/test_research_persistence_boundary.py | 6 |
| apps/worker/tests/test_research_memory_context.py | 36 |
| Total | 120 |

`RequireFullExecution` checks per-file counts, unique collected node IDs, call-phase passing IDs equal to the collected set, collection-only mode, collection/runtime failures, skipped/xfail/xpass reports and deselection. A successful collection or total count alone cannot satisfy the job. Ordinary pytest failure exit status is retained; guard violations force failure.

## Baseline independence

Inspection of the frozen settlement test confirms that `OLD_SOURCE` contains the verbatim pre-extraction function and `OLD_SOURCE_SHA256` pins it. `old_public()` compiles that local string with the unchanged native dependencies. `e7b3e86` appears as provenance/compiler filename, not a runtime Git read. There is no subprocess/Git-history requirement in this test. No additional oracle file or test authorization was needed.

The existing persistence-boundary test starts a Python subprocess for neutral imports, using paths computed from its own repository root. It does not invoke Git or reference a host sibling tree.

A temporary source package was assembled without `.git`, using copies of the API source/tests, Worker source/projection test, and relevant packages from this worktree. The interpreter was existing read-only local tooling; all own source imports were required to resolve inside the copied package. A Python audit hook rejected attempted Git subprocesses. In that package:

```text
packages/research-persistence/tests/test_memory_tool_settlement.py::test_frozen_baseline_and_entry_signature
apps/api/tests/test_research_worker_budget_recovery.py
apps/api/tests/test_research_persistence_boundary.py
apps/worker/tests/test_research_memory_context.py
```

ran with:

```text
python -B -m pytest --noconftest -p research_worker_test_support --strict-markers
-p no:cacheprovider -o addopts= -o pythonpath= -o xfail_strict=true
--basetemp <fresh-source-package>/pytest-final-temp -q --tb=short <the four selections above>
```

The probe used pytest.main with those exact arguments, bracketed by the workflow's extracted own-import checks and the no-Git audit hook. Result: **65 passed in 2.57s, exit 0**, including the baseline oracle and all 64 non-PG regressions. No warning remained in this final source-package run. This proves the selected source/oracle path works without repository history; it does not claim the 55 PG cases ran during this CI-only slice.

## Guard and selection verification

Verification extracted the inline Python/class directly from the new workflow. Inline Python compilation passed.

1. Real pytest probes of the unmodified guard class, against small synthetic temporary test files:

| Probe | Actual / expected exit |
| --- | --- |
| Full successful execution | 0 / 0 |
| Runtime skip | 1 / 1 |
| Collection skip | 1 / 1 |
| xfail | 1 / 1 |
| xpass | 1 / 1 |
| Test failure | 1 / 1 |
| Teardown failure | 1 / 1 |
| collect-only | 1 / 1 |
| Deselection | 1 / 1 |
| Omitted selected file | 1 / 1 |
| Zero tests | 1 / 1 |

**11/11 initial guard probes matched.** This initial matrix omitted empty/omitted-reason XPASS; the directed rework matrix below supersedes its coverage. These are guard behavior tests, not product/PG acceptance.

2. All four real files were collected in the `.git`-free source package, with an additional assertion comparing the actual per-file counter to the workflow's expected counter. Actual counts were **56/22/6/36**, **120 tests collected in 0.23s**. The extracted guard rejected collect-only with **exit 1**, as required.
3. Running the workflow's actual preflight with the required URL removed produced **exit 1** and `CITEFRAME_ISSUE45_POSTGRES_URL is required; no PostgreSQL skip is permitted`. No database service was started or contacted by that missing-URL probe.
4. Own-import negative probes rejected a foreign module file, a foreign namespace search path and an empty namespace search path. Legitimate in-package namespace imports passed.
5. A separate direct non-PG run under the workflow's explicit fixture-plugin/pytest flags passed **64 tests in 2.47s**.

Two CI-authoring checks exposed and corrected workflow-only issues before freezing: the first origin check incorrectly rejected the legitimate namespace `ai_pdf_api.db`; the first per-file expectation used 21/7 instead of actual 22/6 for the two existing native files. Namespace-path validation and measured per-file expectations corrected those issues. Frozen product/test/evidence files were not touched.

## Execution limits and installation evidence

No service was started/restarted, no real PG tests were rerun, and no paid/model call, browser, application service or previously denied #46 operation was performed in this slice. Earlier real-PG product evidence remains frozen and separately scoped.

Local attempts to run `uv --version` and `uv sync --help` failed before execution because the installed Windows `uv.exe` was denied access by the current sandbox. No alternative launch, privilege escalation, dependency downgrade or permission change was attempted. Consequently, a clean local frozen install was **not** verified here. The workflow includes the normal setup-uv + lock check + frozen API/dev install sequence and fails if installation is unavailable; actual Linux dependency download/installation and the postgres:17.11 container startup require hosted execution after controller delivery.

The workflow's embedded Python, actual test collection, origin checks, source-package path and execution guard were locally tested. The initial pass had no actionlint result; directed rework below adds actionlint verification. No hosted GitHub Actions result is claimed. Full hosted job execution and independent workflow approval remain outstanding; neither the earlier 120 product pass nor local collect-only is presented as a successful CI job.

## Directed rework: F45-CI-1 / F45-CI-2

Governing independent review: `D:/Code/citeframe/specs/v5/memory-management/reviews/issue45-settlement-ci.md`, SHA-256 `8D91F27B68ED6FDE1A40961E06013FC315B04613E94559A0CAE2F5A52C5B7B41`. Its disposition was REWORK REQUIRED with exactly these two findings. This section records developer verification, pending closure by the same reviewer `agt_26025b40`.

Source/repair branch: `work/issue45-research-memory`, HEAD `e7b3e86ae4de70764c4d17bcbe272686c1c8063a`. No commit, staging or push was performed. Controller owns downstream stacked PR delivery and hosted validation.

### Exact corrections

- F45-CI-1: removed the invalid job-level `runner.temp` expression. A shell step before dependency installation writes `UV_PROJECT_ENVIRONMENT=$RUNNER_TEMP/research-memory-settlement-venv` to `$GITHUB_ENV`. Both later installation and execution inherit this single job-owned environment path. The lock check, frozen API/dev sync and frozen/no-sync run commands are unchanged.
- F45-CI-2: changed the report guard from `bool(getattr(report, "wasxfail", False))` to `hasattr(report, "wasxfail")`. Empty reason strings now retain their XPASS marker meaning and force nonzero completion.

Reversing only these two substitutions reproduced the original workflow text exactly. Original workflow SHA-256: `F77E6FF9ED5C41D4995092FEFC8B442BCB96D01C829178E6B72A96BC0FBCB6DB`; original CI evidence SHA-256: `2FD7FDB89A7E72E7A3F3FFD0BFE149E3BDF7EA2924EE0441BBA8F8A235D8851B`.

### Actionlint

Used the existing executable without downloading a replacement:

```powershell
& D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe -version
& D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe `
  -no-color -shellcheck= -pyflakes= `
  .github/workflows/research-memory-settlement.yml
```

Version **1.7.12**; workflow validation **exit 0, no diagnostics**. Shellcheck and pyflakes integrations were disabled explicitly; this result validates actionlint's workflow/expression checks.

### Actual pytest guard verification

Extracted the current unmodified `RequireFullExecution` class via AST from the workflow's inline Python. The inline body compiles. Real pytest ran in separate subprocesses against synthetic fixtures in `C:/Users/baiao/AppData/Local/Temp/citeframe45-ci-directed-n48rfa_2`, using existing read-only interpreter `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`. Only probe `root` and `expected_counts` were bound to synthetic files (`test_a.py:2`, `test_b.py:1`); the actual workflow selection and frozen tests remain unchanged.

Reproduction uses that directory as cwd and runs `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B driver.py` for each `PROBE_MODE` below. Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTEST_ADDOPTS=""`. Driver invokes real pytest with:

```text
--noconftest --strict-markers -p no:cacheprovider
-o addopts= -o pythonpath= -o xfail_strict=true -q test_a.py test_b.py
```

`collectonly` adds `--collect-only`; `deselect` adds `-k test_good`; `omission` selects only `test_a.py`; `zero` selects empty `empty.py`.

| PROBE_MODE | Actual / expected exit |
| --- | --- |
| success | 0 / 0 |
| skip | 1 / 1 |
| collection_skip | 1 / 1 |
| xfail | 1 / 1 |
| xpass_reason | 1 / 1 |
| xpass_empty | 1 / 1 |
| xpass_omitted | 1 / 1 |
| failure | 1 / 1 |
| teardown_failure | 1 / 1 |
| collectonly | 1 / 1 |
| deselect | 1 / 1 |
| omission | 1 / 1 |
| zero | 1 / 1 |

**13/13 matched.** The two added fixtures apply `pytest.mark.xfail(reason="", strict=False)` and `pytest.mark.xfail(strict=False)` to a passing test. An observing plugin confirmed for each `wasxfail_present=True reason='' passed=True`; pytest reported `2 passed, 1 xpassed`, and the current guard forced **exit 1**. The probes exercise real reports rather than fabricated report objects.

### Attribution and limits

The pinned original independent review records **120 passed in 26.63s, exit 0**, running the previous frozen inline candidate against real PostgreSQL 17.11, including preflight and own-import checks. That result belongs to the reviewer and the previous candidate. No PG service or full 120-case run was repeated for this directed correction; no service operation, dependency installation, denied-uv invocation/replacement, model call or product/test edit occurred. Hosted Linux frozen installation, service-container startup and current-commit job execution remain controller delivery evidence. The corrected candidate still requires original-reviewer closure; this developer report grants no independent approval.

## Handoff and write-back

Only the dedicated workflow and this evidence are new in this CI slice. Controller owns commit/push, required-check configuration, hosted results and the separate original-reviewer workflow audit. There is no change to the frozen settlement candidate or its pending review.

Applicable session instructions and shared memory policy remain in force. Write-back check: bounded durable verification is recorded here only. No private MEMORY/daily memory or external workbench/profile write was used. New file hashes are reported in the handoff; this file does not contain a self-referential hash.
