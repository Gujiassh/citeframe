# Issue #25 candidate evidence

Base: #29 `5bfee6a0f9a7d8466d72b11a961cc5446fa7bca1`. Feature branch: `work/issue25-conflict-investigation`. Tests run against source paths in `D:/Code/citeframe-conflict-investigation`, not the canonical checkout. The interpreter is reused read-only; explicit PYTHONPATH selects this lane.

| Requirement | Implementation | Direct deterministic evidence | Remaining gate |
| --- | --- | --- | --- |
| Inspect original version/environment/conditions | conflict_contract.py, Worker conflict orchestration | Worker literal-quote/invented-condition rejection; actual journal/source integration | Real contradictory-source investigation |
| Targeted authorized supplemental search | frozen evidence service gate scope, stable investigation tool keys | New gate service search/load replay test: actual ledger writes with local injected retrieval; no repeated logical call | Real retrieval quality and service authorization race |
| Corrected claim history and rechecks | conflict_turn journal, conflict_provenance.py | Separate Sessions replay; original text unchanged; verifier and critic required; terminal fake-resolution rejected | Independent review of original-claim vs correction projection |
| Stop/recovery/budget | bounded Worker loop and reservation journal | Three-inspection/two-query policy, duplicate/no-new/budget/unknown-outcome cases, checkpoint cancellation/revocation guards | Full service restart and concurrent PostgreSQL leases |
| Frozen versions and migrations | p0 frozen v3 JSON, r2 v4 JSON/table | p0→q1→r2 same-process versus new-process staged upgrade; exact release rows/schema comparison; old-version suites | Empty/old production PostgreSQL databases through full Alembic chain |
| Final publication provenance | shared renderer and final adoption validation | Resolved/unresolved v4 publication through service saga with SQLite/object-store fixture; post-upload journal tamper compensates | Real object store and independent review |
| User-visible sources and gaps | Run detail DTO and investigation component | Four installed-Chrome mocked-API tests, screenshots inspected, reload and historical absence | Visible real API/Worker/Web walkthrough |
| Old report editing | No report-edit model/save changes | Existing Web/unit/build suites | Real historical/user-edited report smoke |

## Results

- API `test_research*.py` plus persistence boundary: **275 passed, 1 skipped** (`.local-issue25/api-final2.log`).
- Worker `test_research*.py`: **107 passed** (`.local-issue25/worker-delivery.log`).
- Web tests: **140 passed** (`.local-issue25/web-tests.log`).
- `tsc --noEmit`, ESLint and Next production build: exit 0 (`tsc-delivery.log`, `lint-delivery.log`, `build.log`).
- Playwright investigation scenarios: **4 passed**, installed Chrome / isolated profile / lane-local port 3305 (`browser-delivery.log`). Browser route mocks exercise UI projection, not the production backend. Fixture avatar warnings are unrelated to investigation state.
- No paid provider invoked and no credential files accessed. Migration tests use SQLite with a subprocess; no production database migration or backend restart acceptance is claimed.

## Review and deployment hold

Keep draft until remote CI, independent Critical review, full PostgreSQL migration/restart and real service-backed user walkthrough pass. Future prerequisite fixes must enter this branch by normal merge from an explicitly named #29 SHA, followed by affected regression. #28/#29/#25 merge ordering remains controlled by the main owner.

Reproduction commands and exact migration limitations are in the linked feature spec. Local pre-change and final-delta manifests are retained under `.local-issue25/`; no prerequisite overlay or unrelated canonical dirty state is in the feature commits.


## Hubble P1 follow-up: nullable live-gate input

Independent review found that lease creation permits a null Step input and stores SHA256(step.id) on its Attempt, while the investigation live-gate source validator compared against raw null. The correction uses the exact lease hash rule and retains wrong-hash rejection. Source validation also checks tool workspace and evidence run/workspace/capture ownership explicitly.

A 14-case null/explicit-input matrix covers valid current attempts and wrong attempt hash, changed Step hash, tool workspace/snapshot, handle run and evidence run. Before the fix, the nullable positive and two scope-negative cases failed; after the fix all pass. The frozen search/load service integration now covers both null and explicit Step input and invokes source validation on the newly retrieved handles. Targeted investigation/publication/adoption tests: 41 passed. Broad API Research plus boundary: 290 passed, 1 skipped. These results use local deterministic/SQLite fixtures.

The dependency base remains #29 `5bfee6a`; nullable **finished-attempt replay** still depends on Franklin's pending #29 integration of #28's adoption fix. This local live-gate repair does not establish that pending combined path.

CI at prior HEAD `d619d719` passed all Worker jobs and both Web jobs. API reported 837 passed, 2 skipped, 3 failures: two existing A2 pending-human-plan assumptions are handed back to Franklin; the third was the asset migration test expecting q1's downgrade error while r2 now rejects first. The latter test now expects r2's forward-only message. That PostgreSQL assertion needs a new CI run; no local PostgreSQL run is claimed. PR remains draft and the real-service acceptance gates stay open.


## Explicit v4 feature oracle and upstream integration

Normally merged #29 `b1f7423e5595d81d408d89de4ca565825e5c4e3b` in `ab704253d63c89ef95af287239a71eeffd79a850`. Both appended browser-test groups and SSoT sections were retained when resolving the two append conflicts. The R2 difference whitelist and F1 historical comparator remain unchanged.

Issue #25 adds `a2a_conflict_feature_oracle.py` as an explicit F2 projection before F1/R2: historical investigation table schema must be exact and its rows empty in all snapshots; only a null investigation field on a recognized historical run DTO may be removed; the current default must be v4/Agent IO v3 before projecting the default-version observation for the v3-era comparator. Existing historical responses and events retain their original handling. R2 still rejects unapproved changes.

The current-default B scenario now executes actual POST creation, production scheduling, investigator, real frozen evidence service with scripted retrieval, durable no-new-evidence termination and final publication. Its separate feature assertions check v4 prompt identities, journal hashes/phases/snapshot/attempt lineage, source linkage, original claims and unresolved report gaps. A and AStored continue to restore historical v2 state and idempotency records. C restores an original persisted v3 creation state exported by the fixed #29 b1f7423 runner, installs v4 beside it, and completes with the original v3 manifest/prompts/IO and no investigation journal. This C evidence starts before approval; it does not claim recovery of a pre-existing approved v3 snapshot.

The exploratory dirty-worktree runner passed A/AStored/B/C and five real serialized-SSE→Web-parser checks. Its report is `.local-issue25/v4-feature-integration.json`; it is not same-HEAD acceptance. On that raw report, all 33 R2, 6 F1 and 10 F2 negative controls reject; nullable running/completed-attempt source plus publication/migration targeted suite: 64 passed. A clean committed-head rerun is required for delivery. PostgreSQL/object-store/process/UI production acceptance remains open.

Frozen v3 creation fixture SHA256: `b5eb5b44a4f11db609a4a007dc2e7f55d0589fe84ba5c84798846880a97b84c7`. Source: `repair1/issue29-fixed-head.json`, candidateHead `b1f7423e5595d81d408d89de4ca565825e5c4e3b`; historical artifacts were read only.


## Dependency cfc0e728 integration and bounded local regression

Verified the public #29 HEAD `cfc0e728fb3dca82a097088a0dc5038cd833b926` with `gh pr view 29`; normal merge commit `f185aa521fd051f25edb3805198a8eedb89d013c` retains the #25 delta. The prerequisite is #28 `ae3fd6fbccb260c9e5851cbb4a57e2c549f6702f`. The cfc increment only strengthens replay request-body rejection and the unchanged Research/human-decision database projection. No R2 whitelist, R2 publication oracle or F1 historical comparator changes were introduced by #25. V4 changes remain in the explicit F2 oracle. Historical artifacts were not rewritten.

At f185aa5, with lane-owned environments and no paid provider:

- `PGCONNECT_TIMEOUT=2; apps/api/.venv/Scripts/python.exe -u -m pytest apps/api/tests -q -ra`: **844 passed, 27 failed, 7 skipped** (`.local-issue25/cfc-api-bounded.log`). The three A2 executable/facade/plugin-pollution tests pass, including the 33 R2 / 6 F1 / 10 F2 rejection controls. Six skips require PostgreSQL; the seventh is the runner-only probe. The earlier unbounded-connection run was stopped and is not counted as complete.
- The 27 API failures comprise 22 historical M402 hash/provenance checks, two R100 taxonomy-hash checks and three storage subprocess timeout/lifecycle checks on Windows. `windows-hash-diagnostic.json` confirms CRLF worktree bytes for the sampled M402 harness/artifact and R100 taxonomy normalize exactly to unchanged cfc Git blobs; the artifact/taxonomy LF hashes match their recorded hashes. These files are outside the feature delta. Storage timeouts remain local failures; no portability fix or passing baseline is inferred. No frozen artifact, hash whitelist or unrelated production code was changed to suppress failures.
- `PGCONNECT_TIMEOUT=2; apps/worker/.venv/Scripts/python.exe -m pytest --strict-markers apps/worker/tests -q -ra`: **569 passed, 1 skipped** (`cfc-worker-all.log`), including fast, acceptance and evaluation markers. The skip is the unavailable Windows directory-symlink capability.
- Web unit **140 passed**; TypeScript, lint and production build passed. Installed Chrome on lane-local port 3305: **7 passed**, covering four investigation cases and three upstream initial-failure/retry cases (`cfc-browser.log`). These browser tests use API fixtures, not a service-backed acceptance environment.
- Investigation/source/publication/adoption/migration targeted regression on the merged b1 source: **64 passed** (`b1-affected2.log`). It covers nullable and explicit Step input on running and completed originating attempts.

The delivery also formats the three new F2 oracle/test modules; AST comparisons against f185aa5 are identical. This is a readability-only change. Final clean-commit evidence is generated after the delivery commit with:

```powershell
$env:PYTHONUTF8='1'
& ./apps/api/.venv/Scripts/python.exe infra/scripts/run-a2a-differential.py --root D:/Code/citeframe-conflict-investigation --output .local-issue25/delivery-fixed-head-a2.json
```

The report must identify the public delivery commit, `repairSnapshotDirty=false`, `candidateSemanticDirty=false`, accepted A/AStored/B/C scenarios and five production Web SSE parser results. Its exact SHA/results are recorded in draft PR #30 and the linked dev-workbench delivery checkpoint; exploratory dirty reports do not substitute for it. C remains a restored pre-approval v3 task, not recovery of an already approved v3 snapshot.

Local full-suite failures, the six unavailable PostgreSQL checks, actual object-store/service restart and visible real-service UI acceptance remain open. CI for #29 cfc passed all six jobs; that is prerequisite evidence only. #30 requires its own current-SHA CI and independent Hubble review. All stacked PRs remain draft and unmerged.


## Real-service rework (2026-09-24, based on e27f5813)

The service harness is `infra/testing/issue25_service_support.py` with a production Worker fixture in `issue25_runtime.py`. It creates isolated `pr25_` PostgreSQL databases and runs Alembic, Uvicorn and Workers as separate processes. Retrieval uses real pgvector SQL and S3; only generation and embedding capabilities are scripted and unpaid. Subprocesses run outside credential-file directories with explicit loopback configuration. No historical fixture bytes are rewritten.

- Hubble's journal-origin finding is covered by matching frozen Step/current/origin Attempt inputs, workspace and snapshot, rejecting future/foreign producers while allowing earlier terminal attempts. The complete combined critic input is checked against all persisted supported unaffected claims and verified corrections. API projection also validates the final outcome.
- New integrity suite: 14 pass; against archived e27 package code the same tests yield 8 failed/6 passed. Existing investigation/publication suite: 45 pass. Broad Research/persistence boundary suite: 325 pass/1 PostgreSQL skip. Logs: `.local-issue25/service-rework/{integrity-tests2,integrity-e27-red,journal-fix,research-regression}.log`.
- Real local services: portable PostgreSQL 17.11/pgvector 0.8.6 and lane-owned SeaweedFS S3. `live-all2.log` records 6 passed/13 failed. Passing cases include an **already-approved v3 snapshot** generated by archived cfc code, upgraded to current v4 default, resumed to original v3 report, edited and API-restarted with exact snapshot/prompt/asset bindings unchanged; resolved and unresolved API/report/editor paths; cancellation; actual shared tool-budget exhaustion; full-chain fresh versus cfc-staged migration.
- Twelve Worker exit86 boundaries test inspect/search reservation and result before/after, and verifier/critic result before/after. Diagnosis proves the conflict gate really reclaims and completes attempt 2, but publication compensates because the successful Step retains `lease_expired` from reclaim. The existing final-adoption oracle correctly rejects that Step. `diagnostic2/.../restart-state.json` records the succeeded gate with stale error and compensating publication intent. Franklin owns the prerequisite repair in R2 `lease.py`; #25 does not relax the publication oracle or edit his lane.
- The thirteenth failure was the permission fixture expecting 403 where the API intentionally conceals a removed workspace with 404 `workspace_not_found`. Durable cancellation and no new journal/provider/tool calls already passed; the HTTP assertion now checks the exact existing concealment contract.

Run the opt-in service matrix with a loopback `CITEFRAME_TEST_POSTGRES_URL`, explicit `AI_PDF_MINIO_*` fixture settings and `CITEFRAME_TEST_S3_BUCKET`, then `apps/worker/.venv/Scripts/python.exe -m pytest infra/testing/test_issue25_services.py infra/testing/test_issue25_service_limits.py -vv --tb=short --basetemp <evidence-directory>`. CI uses the same tests with PG17 and digest-pinned MinIO; its checkout is the PR head, not GitHub's merge ref. Service tests do not prove visible UI or paid-provider quality. Current candidate remains draft pending the upstream recovery repair, full matrix rerun, current-SHA CI, independent re-review and Descartes's visible UI walkthrough.


### Windows byte and timing attribution

Re-extracted cfc/e27 with `git -c core.autocrlf=false archive <SHA>`; ordinary `git archive` under this machine's autocrlf=true produced CRLF too. Selected extracted historical bytes were compared directly against official `git show SHA:path` output. No artifact or expected hash was normalized/rewritten. In the same 67-test selection (`test_multimodal_execution.py`, `test_r100_research_eval.py`, `test_storage_metrics.py`), both CRLF trees give 24 failures/43 passes; exact LF base gives 67 passes and candidate initially gives 66 passes/one storage timing failure. Eight alternating paired full-selection reruns give **67 passes each, 16/16 runs**, and four paired targeted reruns give **three storage tests passing each, 8/8 runs**.

The storage source and its test have identical official Git SHA256 across cfc/e27. Reproduction command from each LF archive, with its own apps/api/src, apps/worker/src and package src roots in PYTHONPATH: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_storage_metrics.py -k "hard_deadline_and_reaps_child or watchdog_enforces_its_own or self_terminates_when_supervisor" -q`. The full-selection command above reproduced one candidate failure (`publication_storage_child_self_terminates_when_supervisor_is_killed`); it was not reproduced in later paired runs. Raw logs and source hashes: `.local-issue25/service-rework/windows-byte-and-repeat-evidence.json` and `*-lf-repeat-*.log`.

Attribution: the 24 hash failures are checkout-byte configuration effects affecting both refs. The three original Windows storage lifecycle/timing failures belong to unchanged prerequisite storage/tests, but their intermittent environment cause is **not conclusively diagnosed**. No upstream defect is declared solely from identical source or Linux-green CI, and no storage timeout/oracle is weakened. This bounded investigation leaves Windows timing stability open for the controller; it does not block recording the separate genuine Step lifecycle bug reproduced by the service matrix.
