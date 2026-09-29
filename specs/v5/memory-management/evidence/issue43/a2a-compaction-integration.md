# F43-CI1 — A2a compaction historical comparison integration

Date: 2026-09-29. Base/branch: `acefd922d235798bbf1b29212dc6e6c04304d6e1`, `work/issue43-inloop-compaction`. Status: **implemented bounded candidate; original-review acceptance and original frozen-exact/plugin test reruns pending**. No commit/push.

## Cause and exact change

Original F43-CI1 independently attributes the API differential failure to approved additive ResearchStepAttempt fields absent at frozen baseline `d1b5945e977445e4db6bf56ef54cf61607ead2e2`. Current probe intentionally captures every column. Existing schema and immutable retry-history oracles therefore reject defaults `memory_context_version=0`, `memory_checkpoint_id=NULL`. Publication diffs in raw stdout are not independently suppressed or reclassified by this correction.

One separate adapter, `infra/scripts/a2a_compaction_history_oracle.py`, validates before projection:
- Candidate Attempt schema equals the historical schema plus exactly those two unique columns.
- Every Attempt in raw/normalized transitions/processOne, maintenance before/after and all five lifecycle snapshots has both fields, `type(memory_context_version) is int` and value0, checkpoint explicitly None; exact row fields required.
- Existing raw/normalized validator runs on original evidence before removal.
- Only a deep copy loses the two fields and their Attempt schema entries. All other content passes unchanged to existing F2/F1/R2/retry comparators. Missing/extra/nondefault/bool/float/string values and inconsistent captures fail closed.

Runner change is one comparison-import substitution. Test change routes original negative controls through a separately validated copy and executes 176 compaction mutations against actual A/AStored reports first. Captured source reports and top-level raw-report hashes remain original. No capture-time hiding, prefix filter, baseline regeneration or publication-oracle edit.

## Exact candidate inventory

| File | SHA-256 |
|---|---|
| NEW `infra/scripts/a2a_compaction_history_oracle.py` | `77A9962CD96797839E24AA1A83FAC06B4C90F834C01DE8632146A94CE9DB1636` |
| `infra/scripts/run-a2a-differential.py` | `127809EBCB562F85A99A6A302006019EE65E7E4A99F1248209BD1D9F1AE1786C` |
| NEW `apps/api/tests/test_a2a_compaction_history_oracle.py` | `DE6735E33DED0D938C9AC1D6C8DBE1BA32F0FCCC62D487F93505BFAB3DA26905` |
| `apps/api/tests/test_a2a_differential.py` | `5A45E565ABA030E04CF39536DBC7DBCA45207050CB406085C5F5CD8D069D70E9` |

This report is the only new owned durable evidence file for the CI correction. Existing native handoff/delta are separate frozen proposals; reviewer-owned review changes are untouched.

## Executor-scoped verification

Single implementation agent: `/root/core_implementation`, completed. Developer root `/root` inspected changes and ran separate acceptance commands. Neither is the controlling user task or appointed independent reviewer.

| Executor | Execution | Result |
|---|---|---|
| Developer agent | Dedicated new test module, existing API interpreter, lane PYTHONPATH, no sync | **136 passed /0.17s** |
| Developer root | Dedicated module + complete persistence and Research persistence boundary modules | **156 passed /2.50s**, one existing Starlette/httpx warning, no skips |
| Developer root | Actual unchanged probe against exact Git-archived baseline | **1 passed /14.39s** |
| Developer root | Actual unchanged probe A historical restore / AStored / B current / C v3 restore | **1 passed each /2.15s,1.27s,2.24s,1.79s** |
| Developer root | Actual unchanged probe with candidate-api-facade mutation | Expected rejection at existing assertion `candidate production composition must not use API research_worker facade`; **1 failed /0.69s** is negative-control success, not a runner test pass |
| Developer agent and separately developer root | Old comparator on actual A reports | **RED:** `schema.unknown table/field` and `retryStepErrorDelta.immutable attempt history`; AStored also rejected |
| Developer agent and separately developer root | New comparator on same unchanged A/AStored reports | **GREEN**, both accepted |
| Developer agent and separately developer root | Actual-report mutation controls | **176 compaction mutations**, **33 original R2 controls**, nested **8 retry controls**, original **F1 controls**, **10 full F2 controls** pass; source bytes unchanged |

Root pytest command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
# PYTHONPATH = lane packages/*/src; apps/api/src; apps/worker/src; infra/scripts; apps/api/tests
D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_a2a_compaction_history_oracle.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py -q -p no:cacheprovider --basetemp=.tmp/a2a-ci1/root-pytest
```

### Supplemental actual-probe method and limitations

No uv/network/environment install was invoked. Used existing `D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe` read-only, bytecode disabled, and explicit lane/snapshot source paths. The exact historical Git archive was extracted into disposable `.tmp/a2a-ci1/baseline`; the runner's existing `_historical_probe_source` transformation and unchanged historical helper prepared its probe. No historical repository or frozen fixture was edited. This method exercises real local source/probe behavior but **does not satisfy the original runner's distinct frozen-exact snapshot environment or Web-parser/plugin gate**.

Baseline invocation used `-c .tmp/a2a-ci1/baseline/apps/api/pyproject.toml` to prevent upward discovery of lane pytest.ini. The first attempt omitted this flag and failed importing old research_runtime because lane pythonpath overrode the temporary historical source. Both logs are retained; this was verification setup failure, not baseline/product failure. Corrected invocation passed. Candidate invocations use the unchanged lane probe and original scenario flags:
- A: A2A_HISTORICAL_STATE=baseline.json.
- AStored: same plus A2A_STORED_APPROVALS=1.
- B: A2A_CURRENT_SCENARIO=1.
- C: A2A_CURRENT_SCENARIO=1, A2A_V3_RESTORE=1, original `research-v3-created-b1f7423.json`.
- Facade negative: original candidate-api-facade mutation.

All basetemp/output files are under `.tmp/a2a-ci1`; no paid/live provider calls. Existing probe stub-provider behavior remains unchanged.

## Retained raw evidence identity

| Original report (all under `.tmp/a2a-ci1/`) | File SHA-256 after comparisons |
|---|---|
| baseline.json | `E035C6A8BDD040B645CCC88C0F3089018C261854301C31670BD3E4DAED86A8B2` |
| candidate.json | `BC8782EBD8A1A8CF431AE21648317B6569CE68354D1C51AE852138D096F3C038` |
| stored.json | `EC950AC03808FA080BBC8EE21E69AE50352224D6F2AC3A21242D181416C08618` |
| current.json | `3CA872C81CF26A2A415C8205BBC66FA2E6DC05774C34399CEF9D6E267958667D` |
| v3.json | `DBD9BAAAA412F35A2EEE4C5F7790297094B96563770C3B24F0520E111F6DC12D` |

Complete old/new comparison JSON including stored replay: `.tmp/a2a-ci1/developer-comparisons.json`, SHA `65F7E12D4747CDEA143D1A368C616B259D27DE974289A92BE926CC7C2FE3FF9B`. Logs: developer-controls.log, developer-f2-controls.log and each *-probe.log. This is supplemental developer evidence, not a fabricated frozen-exact full-run report. Controller-supplied hosted failure log identity and unavailable temporary candidate80cebef mapping retain the original review's provenance limitations.

## Frozen evidence and remaining acceptance

Final raw-hash check: all **45 core manifest entries match, 0 mismatches**. Accepted instruction fixture E6A33A64, boundary5FC30A4E and head-test identities remain unchanged. Probe F027E16B and original R2 delta CAF14C4B, publication E5A349D0, F1 E525E7A0, F2 903ECABA, retry8FEDF3B2 match original F43-CI1 inventory. No baseline or publication fixture changes. Scoped tracked diff-check passed.

The two original tests `test_a2a_historical_invariants_and_explicit_r2_delta` and `test_exact_worker_sync_removes_real_pytest_plugin_pollution`, plus original runner facade-negative test, have **not been rerun through the frozen-exact runner** in this lane. That path forcibly invokes uv; lane `apps/worker/.venv` is absent and the prior explicit restriction on repeated uv access remains unresolved. No bypass, mocked sync/plugin result or successful-removal claim is made. Root requested a narrow clarification: keep restriction and controller reruns, or authorize the original tests' uv synchronization. Original tests/environment/plugin assertions remain intact.

F43-CI1 closure requires original-reviewer acceptance and those exact runner/plugin reruns in an authorized environment, with complete report and hosted snapshot/tree identity. This correction does not claim whole API CI success, Chat Stage A acceptance, Research integration or Issue43 closure. Native-chat delta F57 remains frozen pending its separate precise approval; no affected core edits started. Durable write-back is this repository report only; no private/global memory, workbench, canonical/historical tree or Git-state write.
