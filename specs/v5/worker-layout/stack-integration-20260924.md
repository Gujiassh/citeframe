# Architecture integration: prerequisite and feature stack

## Fixed prerequisite inputs

- Accepted architecture main: `5ed02c8b7b5f357f58d1c3fd270ead0718e7afbf`.
- Reviewed prerequisite plus deadline fix: `e1f080f4c9dca954da11fcd58aa5559220b23ab1` (contains `e2946c7`).
- Integration uses a normal merge in a separate checkout. Frozen local e8/e607/7d6 browser sources remain untouched.

## Conflict and runtime mappings

1. The deleted `research_runtime_ports.py` is not restored. Its R2 `SqlResearchLedgerAdapter.publish_final` method moves into `research/adapters/ledger.py`, including `_call_saga`, `PublicationResult` validation and committed/reconcile-pending identity checks. All three adapter class AST bodies match the reviewed prerequisite classes.
2. `research/executor.py` retains architecture exports and adds shared-contract `PublicationResult`. No `research_executor_contracts.py` compatibility shim is recreated.
3. `test_research_runtime.py` retains the prerequisite V2 prompt provenance imports and imports the relocated production executor.
4. Service fixtures import `citeframe_evaluation.acceptance` and `ai_pdf_worker.research`; their child-process PYTHONPATH includes the explicit offline tool source. Production dependency declarations do not acquire evaluation.
5. Dynamic script-import tests prepend only the script directory under test, matching normal CLI resolution. Assertions and frozen historical fixture bytes remain unchanged.

The checked file mapping remains `file-mapping.json`. Prerequisite mapped runtime body comparison permits only import relocation, the accepted module docstrings and the two explicit logger namespace moves. Adapter class bodies are compared without these normalizations. Extra behavioral changes are not admitted by that comparison.

## Deployment harness contract increment

The historical `c263` product diff and pinned `50af` historical scenarios remain recorded. The old evaluation-only allowlist cannot admit this feature stack. Current candidates additionally use fixed architecture main5ed as their reviewed baseline and `integrated-product-delta.json` as a checked-in, exact path-to-Git-blob contract.

- The manifest is frozen during owner preparation and reviewed as source. CI never regenerates it from the candidate.
- Git ancestry is required for the accepted architecture and explicitly reviewed source heads, but is not sufficient: every reviewed source path/blob and every integrated path/blob is verified.
- Actual product diff must exactly equal the manifest, including missing paths. Unknown files, changed admitted bytes, duplicate paths and changed baseline fail.
- The prerequisite manifest contains55 product/test paths. Layout-independent files retain reviewed bytes; mapped files and two script-import test adaptations have explicit source provenance.
- `r800_product_delta.py` is the validator; `test_r800_product_delta.py` supplies positive and five rejection controls. Existing deployment controls remain intact.
- The original three Hubble false-positive controls, historical raw output, real fresh-project forced-serial negative control, original scenario engineering gate, backup/restore, ordinary Worker task completion and default pinned MinIO-client check remain mandatory.
- A pre-smoke functional check explicitly runs R2 adoption/revocation, recovered-Step error and deadline-admission regressions. It supplements the existing scenario and real-service gates; it does not replace them.

## Verification scope

Development checks: architecture/runtime/dispatcher/storage84passed; layout parity/CLI-output/import-probe/adoption/recovery24passed; deployment harness13passed; three console entry points, evaluation wheel/sdist build and API/Worker lock checks passed. A broad combined Worker/evaluation run was interrupted and is not a pass. Final publication records exact integration-SHA checks independently.

Local Windows has no Docker runtime. The existing exact-HEAD GitHub runner exercises image packaging and deployment. No paid provider, shared database migration or frozen-source mutation is authorized by this integration.

## Snapshot-proof integration repair

The first architecture candidate `bec8864c320fb3fec1132ddd35e6298c86eb8747` reproduced 10 failed / 6 passed frozen proof tests. The evaluation CI job reported the same ten ImportErrors (119 other tests passed). R2 had moved the canonical snapshot constructor from the API facade to `citeframe_research_persistence.snapshot_integrity`; the offline proof now imports that actual production constructor. Its invocation, payload keys, canonical hash operation, frozen fixtures and mutation controls remain unchanged. No ImportError is converted to an accepted rejection.

The shared-contract manifest provenance now references `packages/backend-contracts/src/citeframe_contracts/__init__.py` at the reviewed e1 source, whose bytes exactly equal the integrated definition. The former re-export shim is not a definition source and is not restored. The snapshot-proof file adds one explicitly pinned product-delta entry sourced from accepted architecture main.

## Feature stack mapping

The feature source is fixed `b691406fdc7d38e3f93578b36aaddafe7dbf992f`. The feature manifest replaces the prerequisite manifest with its own exact product delta and provenance. Adaptive retrieval moves to `research/adaptive_retrieval.py`; `LedgeredGeneration.adaptive_turn` moves into the generation adapter with its durable call contract intact. The evaluation provider retains historical `V1_REGISTRY` after the schema-module move. Historical A2 probe import translation and the feature historical-state helper are both retained. No historical fixture bytes change.

The feature stack normally merges prerequisite repair ed478a8. Its snapshot proof import and negative controls remain mandatory on the final feature candidate. The feature manifest contains 112 exact product/test paths including the explicit feature harness adaptation. The earlier mapping check passed 38 focused tests; final-SHA runtime gates are recorded separately.

## Feature deployment oracle increment (separate from R2 deltas)

The current deployment main and post-restore new task use the real POST default and require persisted v3 workflow/release/prompt bindings. The read-only `acceptance/workflow.py` loads the production release by the run's persisted revision, validates the actual frozen snapshot hash and prompt children, and observes the policy-created snapshot before independent consumers start. It rejects unknown releases, queued runs without snapshots, and v3 human gates. Reclaim selects its version contract from those persisted facts; only a proven historical v2 path may call the existing human approval helper.

The current v3 main and post-restore path do not POST plan/conflict decisions. Completion requires policy-origin/null-actor decisions and closed schema-v2 event payloads, plus the unresolved conflict partition. They record run/workflow/release/prompt/snapshot/decision/event facts. Historical50af execution and raw artifacts remain untouched. The separate A2 runner still requires historical-v2 creation/recovery/replay and real-current-default-v3 scenarios, including their candidate SHA; the v3 path is not an R2 equality exception.

The synthetic HTTP proof provider retains the original stub response byte-for-byte for the historical claims-only result schema. For the explicit adaptive claims+nextQuery wire schema it returns the same claims with null nextQuery, a bounded stop fixture. Unknown required fields fail. This does not claim supplemental-query quality; adaptive recovery/query/budget tests and the service gates remain independent requirements. No historical fixture/source stub bytes change.

Additional negatives cover an unknown workflow, policy waits for a human, queued-without-snapshot, spoofed decision actor, unknown wire fields, and moving/removing unresolved conflict text. The original serial, false-positive, snapshot, permission, backup/restore and Worker identity checks remain enforced. Product manifest changes list each integrated blob with source provenance; the provider/probe/workflow harness delta is separately reviewed and recorded in the existing harness hashes.

## Request-context binding repair

Independent review of fcafc1b found that a valid snapshot's internal hash graph could be observed through another run's pointer. The offline oracle now additionally binds snapshot run/workspace/approved revision to the requested run's current revision, and binds its approval decision ID/run/workspace/type/planning hash to that same context. Internal frozen-hash validation remains unchanged. This is an acceptance-proof defect; no production permission exploit is claimed.

Five new actual SQLite controls preserve the original valid snapshot bytes and database constraints: foreign run, foreign workspace, stale current revision, wrong approval type, and wrong approval planning hash. All five fail against the fcaf oracle (it incorrectly accepts); the repair rejects them and preserves valid production-auto-plan positive controls. The focused snapshot/feature set passes39 tests before publication. Historical fixtures and previous failed evidence remain intact.

## Issue25 v4 conflict investigation integration

PR30 normally merges architecture feature base `fcafc1b57325ef0815fe89f7e4d558343095f1d6` and snapshot outer-binding repair `ecc0102fc90a884eb4c6b5da6e78c6af995001c2`. Runtime investigation lives at `research/conflict_investigation.py`; journal and generation operations reside in the existing ledger/generation adapters. Deleted flat modules stay deleted. Historical v3 installation data, v2/v3 registries, persisted execution bindings and original report bytes remain unchanged by relocation.

The explicit v4 deployment-oracle increment supersedes the above v3-default requirement for PR30 only. New POST tasks must use v4; historical v2/v3 releases remain accepted by their persisted contracts. The six ecc request/approval binding assertions and five context-forgery controls are retained. The real-create positive now expects v4. The fixture's investigator inspects original source quotes, leaves unknown conditions null and returns no correction or follow-up query. The resulting unresolved conflict must have actual inspect/finish journal rows, canonical request/result hashes, same run/workspace/snapshot/attempt linkage and original claim/evidence relationships. Received investigator wire data must match its persisted inspect operation. No R2 equality whitelist is expanded.

The exact manifest contains142 product/test paths. Existing unchanged provenance is retained; merged feature paths reference a927's reviewed original paths; the six explicit v4 offline oracle paths reference the pinned local integration source. New integration/oracle changes require Hubble's independent review. The validator still requires exact blobs and ancestry and CI never regenerates the manifest. The new oracle does not claim evidence quality from the deterministic fixture.

Current service drivers import relocated production and offline modules. To execute the immutable archived cfc v3 source, only the test driver receives explicit reverse import translation in its isolated case directory. The archived product source and fixtures are not rewritten. The two layout tests guard both import modes and the actual production investigator registry.

Exploratory Windows evidence before the final integration commit: worker mapping73PASS; API feature/deadline95PASS; v4 oracle39PASS; mapped archived-v3 restore and two actual API report/edit paths plus layout tests5PASS. An earlier three-case run failed on a missed persistence import; that import was corrected and the failed log retained. Final-SHA evidence is separate. Frozen7d6 live UI/API source and its manual handoff remain untouched; no frontend process is launched by this integration.
