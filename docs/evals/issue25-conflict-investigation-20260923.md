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
