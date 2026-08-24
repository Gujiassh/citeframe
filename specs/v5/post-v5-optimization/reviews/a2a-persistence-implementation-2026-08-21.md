# A2a Research Persistence Initial Implementation Evidence (Historical)

Status: **superseded initial snapshot; independent Critical review required REWORK**
Date: 2026-08-21
Reviewed snapshot: `20d411ebf60b755c4ef3308e269591b19209e4eb`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
Review result: [`a2a-persistence-critical-audit-2026-08-24.md`](a2a-persistence-critical-audit-2026-08-24.md), `REWORK (High=1, Medium=5, Low=1)`

This file records the initial implementation snapshot only. It is not current acceptance
or delivery evidence. The bounded repair is recorded in
[`a2a-persistence-rework-implementation-2026-08-24.md`](a2a-persistence-rework-implementation-2026-08-24.md).

## Initial Scope

- Added `packages/research-persistence` and API compatibility facades.
- Added the third local distribution to the API/Worker source and deployment topology.
- Kept the fixed multi-step LangGraph runtime and mixed lock order; no R0/R1, schema,
  public API, save/replay, or permission change was intended.

## Why This Snapshot Was Not Accepted

- `_locked_attempt` changed `db` from positional-or-keyword to keyword-only, while real
  planner and publication paths still passed it positionally. The reviewed API flow had
  `9 failed, 62 passed`; the equivalent baseline files had `44 passed`.
- Neutral command/UoW ownership was incomplete and duplicated; the production Worker did
  not consume the introduced repository/UoW.
- The checked-in JSON golden was static and did not execute or compare baseline/candidate
  DB rows, payload/Event bytes, or multi-step `process_one` behavior.
- Docker/CI checks were textual and removable; CI could repair a stale lock before checking
  exports. Docker Hub timeouts prevented current clean-image evidence.
- The implementation report said four boundary tests while the reviewed suite had five.
  It also said `git diff --check` passed, but the exact `d1b5945..20d411e` range reported
  new blank lines at EOF in `apps/api/tests/test_persistence_boundary.py` and
  `packages/backend-persistence/src/citeframe_persistence/models/evidence_locator.py`.

## Historical Passing Evidence

The initial audit independently retained the following bounded passing evidence, which did
not override the failures above:

- API persistence/deploy boundary: `17 passed, 1 warning`.
- Worker package/deploy boundary: `6 passed`.
- Worker fixed-graph suites: `37 passed` using paths that did not exercise the failing real
  publication facade.
- `compileall`, current lock checks, and clean wheel install/import: passed.
- Initial audit could not obtain image evidence from official Docker Hub. The later immutable repair candidate has same-pinned-digest mirror image/runtime evidence in the rework report; this does not retroactively accept the initial snapshot.

This historical snapshot remained rejected. The later repair was independently accepted on 2026-08-24 in [`a2a-persistence-critical-reaudit-2026-08-24.md`](a2a-persistence-critical-reaudit-2026-08-24.md).
