# A1 Contracts Critical Audit

- Date: 2026-08-20
- Auditor: independent reviewer
- Baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
- Reviewed state: current unstaged tracked diff and untracked files at review time
- **Current verdict: ACCEPT (High=0, Medium=0, Low=0)**

## Current Findings

No High, Medium, or Low findings remain.

## Rework History

The first review returned **REJECT (High=0, Medium=1, Low=0)** because
[database-design.md](../../../../docs/architecture/database-design.md) said the boundary
must not be described as A1 complete while the canonical records described A1 as
implementer-complete with independent review pending.

The rework corrected the SSoT at
[database-design.md](../../../../docs/architecture/database-design.md): it now distinguishes
the implementer-complete A1 contracts extraction from the still-unaccepted independent A1
review and explicitly keeps ORM/mutation/session migration in blocked A1b/A2a/R0-and-later
slices. The full current-state scan found no equivalent stale A1-incomplete statement.

## Review Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | Pass | Changes are limited to the A1 contracts package, identity-preserving Worker re-exports, API/Worker local-path sources and locks, deployment exports, Docker/CI smoke, focused tests, and status documentation. No persistence or Research-persistence package exists. |
| User-visible flow and timing | Not applicable | No route, UI, scheduler, or runtime dispatch behavior changed. |
| Architecture and package boundary | Pass | `citeframe_contracts` imports only stdlib modules, has `dependencies = []`, and contains DTOs, TypedDicts, exceptions, and Protocols only. API/Worker production imports resolve from the package; no import cycle was observed. |
| Contract compatibility | Pass | AST comparison against the baseline found no removed existing contract symbol and only the approved `EvidenceToolRegistryProtocol` addition plus the `Researcher` annotation substitution. Legacy and public executor contract objects are identity-equal. Concrete `search`/`load` parameters match the structural Protocol; concrete tuple returns are covariant with the Protocol's `Sequence` returns. A legacy-qualified pickle round trip passed. |
| Data, save, replay, permission, schema, API | Not applicable | The reviewed diff contains no model, migration, route, payload, persistence, or authorization change. |
| Build and deployment topology | Pass | API and Worker manifests add only `citeframe-backend-contracts`; frozen requirement bodies match regenerated exports and contain only pinned third-party requirements. Docker copies only the contracts source and uses the documented A1 `PYTHONPATH`; Worker still copies API source. CI uses the A1 omit sets and import smoke. |
| Tests and verification | Pass | Worker focused tests: 5 passed. API focused tests: 6 passed. Isolated source-only import, contract identity/pickle test, export-body comparisons, compileall, and `git diff --check` passed. |
| SSoT/spec and delivery state | Pass | The corrected database SSoT agrees with README, spec, plan, tasks, implementation progress, architecture records, and workbench: A1 is implementer-complete and this review is its final acceptance gate; A1b and later slices remain blocked pending canonical status synchronization. |

## Commands And Results

```text
git diff --check
pass

uv run --project apps/worker pytest -q \
  apps/worker/tests/test_research_contracts_package.py \
  apps/worker/tests/test_deploy_dependencies.py
5 passed

uv run --project apps/api pytest -q apps/api/tests/test_deploy_dependencies.py
6 passed (one existing FastAPI/Starlette deprecation warning)

uv export ... --no-emit-package citeframe-backend-contracts
API and Worker generated dependency bodies match their committed requirements.deploy.txt files.

AST baseline comparison
no removed existing contract symbols; only EvidenceToolRegistryProtocol added and Researcher changed as approved

python -I source-only import
pass

legacy/executor identity, structural Protocol conformance, legacy pickle round trip
pass

compileall for API, Worker, and contracts sources
pass
```

## Residual Risk

- The implementer evidence records successful clean-image Docker builds and container runtime
  smokes; this reviewer did not rerun those expensive image checks during the re-audit.
- Runtime-checkable Protocol conformance verifies the callable surface at runtime, not static
  return/parameter variance. The reviewed concrete signatures are compatible, but a future
  static type-check gate would make this boundary stronger.
- This acceptance does not implement or authorize persistence mappings, Research persistence,
  R0/R1/R2/W1, schema/API/save/replay/permission changes, or API-source-free Worker work.
  Before A1b starts, the main controller must synchronize the canonical status and delivery
  ledger with this audit result.
