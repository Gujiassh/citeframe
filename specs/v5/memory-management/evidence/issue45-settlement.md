# Issue45 transaction-neutral tool settlement — developer evidence

Date: 2026-09-29. Disposition: bounded extraction implemented and tested; frozen candidate for original independent reviewer `agt_26025b40`. No independent-review approval, shared ABI handoff, activation or release acceptance is claimed here.

## Authority and changed scope

- Worktree: `D:/Code/citeframe-lanes/issue45-research`; branch `work/issue45-research-memory`.
- Starting/final HEAD: `e7b3e86ae4de70764c4d17bcbe272686c1c8063a` (PR51 pure projection).
- Controller grant: `lanes/issue45-settlement-ownership.md`, SHA-256 `B9FB26CD86419AC515931223CB7E899FB5CFA2D576077AFF6E20D39E42E4FF96`; read in full.
- Approved governing contract: `lanes/issue45-research.md`, SHA-256 `249C97FD1705AFCA6481566FD49F1511A6D0E2F82E2C5933BEAD80212FBB89F4`, section 8.3; spec v4 and final A1 choice 2 remain governing.
- Hegel/#40 nonoverlap and developer/reviewer ownership follow the controller grant. No other lane was delegated or modified.

Authored only:

1. `packages/research-persistence/src/citeframe_research_persistence/tools.py`
2. New `packages/research-persistence/tests/test_memory_tool_settlement.py`
3. New `specs/v5/memory-management/evidence/issue45-settlement.md` (this file)

The pre-existing untracked ownership grant was preserved. No model, schema definition, migration, export, dependency/lock file, Worker, source resolver, shared #43 file, state/reclaimer, API/UI, shared CI or old-tree product file changed. No Git write, staging, commit, push or PR operation occurred.

## Implementation and native compatibility

`tools.py:161::_complete_tool_call_in_transaction` has the same argument signature as the existing public completion function. It accepts a Session and native tool-call ID; it does not accept a caller-supplied call/ledger/Attempt chain. It locates, locks, refreshes and validates through the existing `_tool_call_chain` before settlement. It never calls commit or rollback. A supplied callback must also respect the outer owner's transaction.

Public `complete_tool_call` keeps the existing signature and exception boundary:

1. Validate terminal status.
2. Acquire/validate native Run -> Step -> Attempt -> ToolCall -> Ledger chain.
3. Reject an already-terminal call.
4. Only then enter the existing rollback-on-settlement-error boundary.
5. Execute callback, write identical fields/arithmetic, flush once; callback/settlement exceptions cause one explicit public Session rollback and are re-raised.

`_tool_call_for_settlement` is shared preparation. `_settle_tool_call` is the local arithmetic helper used only after that preparation by the two entry functions. It is not the entry for a future transaction owner, does not obtain authority, and is not exported. No capability object, alternate ledger, retry behavior or shared settlement ABI was added.

The settlement statements remain AST-identical to the original public try body: callback result or zero; terminal status/result count/error fields/finished timestamp; one reserved tool slot released; one actual tool call added; ledger version increment and timestamp; one Attempt tool count increment; original flush. No clamping, new result-count validation or clock evaluation moved ahead of the callback.

An AST comparison against the fixed Git object found only `complete_tool_call` changed among existing functions. `_tool_call_chain`, `begin_tool_call` and `restore_evidence_handles` are unchanged. Native imports and public exports are unchanged. The runtime import probe resolved `citeframe_research_persistence.tools` from this authorized worktree.

## Old/new oracle provenance

The test file contains the verbatim pre-extraction public function from the fixed Git object, compiled only as a local test oracle with the existing unchanged native dependencies. It does not require an old tree, modify a tree, or invoke Git at test runtime.

| Frozen source | SHA-256 |
| --- | --- |
| `e7b3e86:packages/research-persistence/src/citeframe_research_persistence/tools.py` bytes from Git | `4150B842B6FEC30057E9B0A7E332AD1C45E9A165652B29AEB5021E83E525BA02` |
| Exact extracted original `complete_tool_call` source string | `F49A52E33FAC8EFA83A37DB45B9C037F4A8549B8947B9BE15C3E8FC45D4E12F7` |

The baseline digest, unchanged chain AST digest, old/new signatures and extracted arithmetic AST are checked in `test_frozen_baseline_and_entry_signature`. Real PostgreSQL tests execute the frozen public function, new public function and new inner entry against the same committed synthetic seed, with caller rollback between runs. This is developer differential evidence; the baseline assertions do not substitute for the separate reviewer.

## Real PostgreSQL transaction evidence

An owned disposable PostgreSQL **17.11** instance ran on loopback port **56545**, database **`citeframe_issue45_settlement_test`**, initialized under `$env:TEMP/citeframe-issue45-settlement-pg`. The pre-existing PostgreSQL executables were read-only tooling. No other cluster, user database, application service, model/provider or browser was used.

Each test creates a unique `settlement45_<uuid>` schema, creates the actual native ORM table dependency closure (15 tables), seeds real FK-linked rows and leaves all native ORM FK/check constraints enabled. No fake Session stands in for PostgreSQL. Both native public and inner commands execute actual SQL against these tables. Schemas are dropped in finally blocks; the final remaining-owned-schema count was **0**. The owned server was stopped successfully after verification.

This fixture uses ORM-created native tables, not an Alembic upgrade. It proves the stated settlement/transaction/constraint/locking behavior; it does not establish migration parity or future shared-memory SQL triggers.

The dedicated suite has **56 tests: 55 real-PG cases and 1 frozen-source/signature/AST case**, with no skips:

| Oracle | Actual observation |
| --- | --- |
| Both requested/running initial states × all four native terminal statuses × absent callback / result count 0 / result count 3 | Frozen public, new public and inner produce equal complete call/ledger/Attempt/result snapshots and identical lock/callback/flush traces. |
| Exact field arithmetic | Call/error/result fields checked completely; ledger begins with nonzero counters and unrelated token/provider/cost values; only the original fields change. Settlement time is 17 seconds after seed time, so ledger timestamp preservation is independently observable. |
| Public transaction compatibility | Success performs no explicit commit/rollback. Callback precedes the one settlement flush; other sessions still see the seed until the owner commits. |
| Outer rollback after inner success | Call, ledger, Attempt and callback-created native artifact writes all disappear; the exact committed baseline is restored. |
| Callback failure after a real result flush | Public old/new explicitly roll back once, including a prior outer write. Inner makes no rollback/commit call; the result and outer write remain visible only within that transaction until caller rollback restores everything. |
| Settlement flush failure | Native nonnegative reserved-slot CHECK rejects the update; old/new public explicitly roll back once. Inner makes no explicit transaction-control call; SQLAlchemy marks the failed flush transaction inactive and the caller performs rollback. No partial write is committed. |
| Callback flush failure | Native tool-name CHECK rejects a callback-side write; the same public/inner ownership distinction holds. |
| Invalid status / missing chain / foreign workspace / already-terminal combinations | Error type/message and precedence preserved, including invalid-status-over-terminal and foreign-chain-over-terminal. Callback never runs; precondition failures do not roll back unrelated outer writes. |
| Real lock failure before settlement | A second connection holds Run FOR UPDATE; native lock timeout (SQLSTATE 55P03) is outside the public rollback boundary for old/new and inner. Caller rollback is required. |
| Real autoflush failure during chain acquisition | NOT NULL violation (23502) occurs before settlement; no expanded public rollback. |
| Lock order and lock lifetime | SQL trace is exactly Run -> Step -> Attempt -> ToolCall -> Ledger. Separate connections using FOR UPDATE NOWAIT encounter 55P03 on all five rows until the owner rolls back. |
| No-double-settlement | After caller commits the first inner completion, another completion rejects before callback; row snapshots and counters are unchanged. |
| Cached-row manipulation | A supplied Session's unflushed forged workspace/terminal attributes are refreshed from locked native rows, rather than accepted as authority. Persisted foreign chain is rejected separately. |
| Default time/null errors | The existing datetime.now(UTC) branch and null error fields match the frozen public oracle. |

This extraction retains the native public authority scope. It does not newly enforce leases, membership, memory policy, evidence access or callback purity; those belong to the existing/future transaction owner contract. No read/evidence authority is issued by this change.

## Exact test commands and results

All commands ran from the authorized worktree root. Final environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH=((@(
  'apps/worker/src','apps/api/src','apps/api/tests',
  'packages/backend-contracts/src','packages/backend-persistence/src',
  'packages/research-persistence/src','packages/memory-service/src',
  'packages/prompt-contracts/src'
) | ForEach-Object { Join-Path $PWD $_ }) -join ';')
$env:CITEFRAME_ISSUE45_POSTGRES_URL='postgresql+psycopg://issue45_test@127.0.0.1:56545/citeframe_issue45_settlement_test'
$base=Join-Path $env:TEMP 'citeframe45-settlement-frozen-regression'
if (Test-Path -LiteralPath $base) { throw 'Refusing existing pytest basetemp' }
```

Final frozen-file verification:

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider --basetemp "$base" packages/research-persistence/tests/test_memory_tool_settlement.py apps/api/tests/test_research_worker_budget_recovery.py apps/api/tests/test_research_persistence_boundary.py apps/worker/tests/test_research_memory_context.py -q --tb=short
```

**120 passed, 1 warning in 24.30s; exit 0.** Breakdown: 56 settlement cases, 28 existing native budget/recovery/boundary cases, 36 frozen projection cases. The warning is the existing Starlette/httpx TestClient deprecation; it is unrelated to settlement. The API native fixture tests are SQLite regressions; the separate 55 PG cases provide the actual PostgreSQL evidence.

Dedicated suite during development:

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider packages/research-persistence/tests/test_memory_tool_settlement.py -q --tb=short
```

**56 passed in 21.34s; exit 0**, before the final additional distinct seed/settlement timestamp oracle. Final 120-case run above includes that oracle and the frozen hashes below.

Original native tests separately (fresh owned `$env:TEMP/citeframe45-native-settlement-regression` basetemp):

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider --basetemp "$base" apps/api/tests/test_research_worker_budget_recovery.py apps/api/tests/test_research_persistence_boundary.py -q --tb=short
```

**28 passed, 1 warning in 2.52s; exit 0.** This includes the original public tool accounting test and native chain lock-order test.

`git --no-optional-locks diff --check` passed. Cached diff remained empty. Branch/HEAD and Git identity were read without modification; origin remains GitHub Gujiassh/citeframe and effective/global identity is `gujishh <baiaoshh@163.com>`, with no repo-local user override.

## Retained environment and intentional failure evidence

1. Initial `pg_ctl ... start` failed with `could not create restricted token: error code 87` / `could not start server: error code 3`. `initdb` reported successful cluster initialization. Starting the same server executable directly via `Start-Process -WindowStyle Hidden`, with data/stdout/stderr confined to the owned temporary directory, succeeded under the same session. No escalation or sandbox-policy change was used. PostgreSQL startup reported 17.11, loopback 56545 and ready to accept connections. Final `pg_ctl -D <owned-temp>/data -m fast -w stop` succeeded.
2. Initial native regression command without an explicit basetemp returned **7 passed, 21 setup errors, 1 warning**, exit 1. Exact shared fixture failure: `research_worker_test_support.py:263 -> tmp_path_factory.mktemp("research-worker-schema")`, `PermissionError: [WinError 5]` at `C:/Users/baiao/AppData/Local/Temp/pytest-of-baiao`. No shared directory permission or fixture was changed. A fresh owned `--basetemp` produced the passing native/final runs above.
3. Intentional no-database negative probe:

```powershell
Remove-Item Env:CITEFRAME_ISSUE45_POSTGRES_URL -ErrorAction SilentlyContinue
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider packages/research-persistence/tests/test_memory_tool_settlement.py -k inner_commit -q --tb=short
```

Expected **exit 1**, **55 deselected, 1 setup error in 0.69s**: `CITEFRAME_ISSUE45_POSTGRES_URL is required; real PostgreSQL settlement tests cannot skip`. This was an intentional fail-closed probe, followed by the successful configured final run; it is not counted as a passing PG test.

## CI / integration / independent-review handoff

The authorized new package test directory works directly with the existing API Python/pytest/psycopg environment; no directory expansion, dependency change or conftest is needed. Existing shared CI does **not** automatically collect this new package test path. Controller owns explicit collection: it must arrange the dedicated disposable test database/`CITEFRAME_ISSUE45_POSTGRES_URL` and select this file in an authorized PG step. No CI job, condition or bypass was changed here. The suite fails instead of skipping when its required DB is absent.

Return these frozen artifacts to original reviewer `agt_26025b40`. Reviewer owns `reviews/issue45-settlement.md`; this developer did not author it or claim independent acceptance. Controller owns Git, PR grouping, CI wiring and integration.

Remaining mandatory gates are unchanged: #43's actual approved ABI and transaction owner, broader native lifecycle/reclaim/schema work, planner sidecar accounting, shared-output/private-memory exclusion, real same-Attempt twice-compaction and no-repeat execution, full native-ledger/runtime recovery, and real UI acceptance. No previously denied #46 service/browser operation was performed or represented as covered by these tests.

## Frozen artifacts and write-back

| Artifact | SHA-256 |
| --- | --- |
| packages/research-persistence/src/citeframe_research_persistence/tools.py | `F8E02EB6C9F93DED10BF59C9B136168130591FC49B4DED0041E6115530230A51` |
| packages/research-persistence/tests/test_memory_tool_settlement.py | `787ED87A226F26D928C2F7505A444235F4EB658E9C252719956FFAB5F9DC27E8` |

This evidence file's final SHA-256 is supplied in the response, avoiding a self-referential hash.

Applicable instructions and MEMORY-POLICY from the session remain in force. `prepare_session.py` ran with bytecode disabled; linked project/state/task and current grant/contract were read. Private MEMORY/daily memory were never read. Write-back check: durable verified results are recorded solely in this authorized evidence file; external workbench/profile records remain controller-owned and untouched. The owned PG server and test processes have stopped; no delegated implementation task remains.
