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
