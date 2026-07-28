# R800 Critical Review

## Status

R800 deterministic engineering acceptance passed on 2026-07-28. The canonical
evidence is [`artifacts/r800-v1/deployment-20260728-v4/`](artifacts/r800-v1/deployment-20260728-v4/).

- Engineering gate: `pass`
- Scripted engineering release gate: `releaseGatePassed=true`
- Model-quality gate: `not_evaluable`
- User-value gate: `not_evaluable`
- Product stage: `internal_preview`
- Frozen R000 hashes: unchanged

The release flag applies only to the deterministic engineering artifact. It does
not claim that a real model meets a quality threshold or that target users receive
validated value.

## Semantic Oracle

| Review area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | pass | Explicit Research mode implemented; Quick Chat remains unchanged |
| User-visible flow and timing | pass | Plan approval, parallel branches, conflict wait/resume, final Artifact and Evidence links exercised |
| Architecture boundaries | pass | API owns business ledger; Worker uses typed ports; PostgreSQL remains truth source |
| Data/save contracts | pass | R000 hashes unchanged; no Asset/Citation/NoteSource/Chat save-semantic change |
| Permissions/isolation | pass | owner/creator/member and cross-Workspace API/Worker tests plus membership-removal runtime |
| Failure/recovery | pass | retry, lease reclaim, SSE replay, restart, cancellation race, unique final Artifact |
| Persistence/restore | pass | PostgreSQL/MinIO empty-deployment restore with equal semantic SHA and object hashes |
| Real-model quality | blocked | Scripted provider cannot evaluate model quality; R803 remains open |
| Target-user value | blocked | M404 does not yet contain qualified user evidence |

## Findings And Resolution

| ID | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| R8-F01 | Critical | Runtime prompts diverged from frozen PromptVersion provenance | Append-only Workflow/Prompt v2 migration and complete execution prompt bindings |
| R8-F02 | Critical | Verifier received IDs without immutable Evidence text | Bounded excerpts and provenance are passed; unsupported claims fail closed |
| R8-F03 | Critical | Artifact detail did not validate every Run/Workspace hop | Full Artifact/Claim/Evidence chain validation and corruption tests |
| R8-F04 | Critical | Final Markdown was accepted separately from selected Claims | API-owned canonical report, exact markers, bytes/hash and atomic Claim mappings |
| R8-F05 | High | Idle cancellation could remain `cancel_requested` | Idle Runs terminate; active cancellation follows persisted CAS semantics |
| R8-F06 | High | Creator membership removal did not stop Worker work | Claim/heartbeat gates enforce membership and persist cancellation |
| R8-F07 | High | Provider failures bypassed frozen retry policy | Failure taxonomy and branch-only bounded retry use the frozen policy |
| R8-F08 | High | Cost reservation did not use frozen pricing | Versioned pricing reserves and reconciles provider usage |
| R8-F09 | Medium | First idempotent failure and replay returned different envelopes | Error envelopes are stored and replayed consistently |
| R8-F10 | Standard | Evaluation importer first-write race and insert order failed on PostgreSQL | Transactional importer ordering and concurrent first-write tests |
| R8-F11 | Standard | Conflict-wait telemetry was overwritten as success | Explicit waiting outcome wins and telemetry failures remain isolated |
| R8-F12 | Critical | Parallel provider/tool completion locked call/ledger before Attempt/Step/Run and deadlocked on PostgreSQL | Unified `Attempt -> Step -> Run -> call -> ledger` order with identity-map refresh and cancellation reconciliation tests |
| R8-F13 | Standard | R800 stub classified every Claim as unsupported when the question contained that word | Verifier uses explicit synthetic Claim markers; Critic consumes only supported Claim status |

All implementation findings above are closed. R8-F12 was observed in v2;
R8-F13 became visible after the deadlock was removed in v3.

## Runtime Evidence History

| Run | Result | Durable evidence |
| --- | --- | --- |
| `deployment-20260728-v1` | fail | Planner budget comparison and SSE timeout defects; cleanup evidence retained |
| `deployment-20260728-v2` | fail | Real PostgreSQL deadlock on `research_budget_ledgers`; restore and cleanup independently passed |
| `deployment-20260728-v3` | fail | Deadlock absent and `maxActive=2`; deterministic stub status parsing caused `critic_conflict_set_mismatch`; restore and cleanup passed |
| `deployment-20260728-v4` | pass | All scenarios, provider timeline, restore identity and cleanup passed |

Canonical v4 results:

- main Run completed;
- parallel provider maximum active count was `2`;
- one transient provider failure produced exactly one retry;
- three unsupported Claims produced zero final links;
- one conflict Decision was submitted and resumed;
- lease reclaim preserved attempt numbers `1,2` and abandoned the expired attempt;
- SSE replay returned all events after cursor `24` without gaps;
- cancellation produced no final Artifact;
- membership removal cancelled the Run;
- API and database each contained exactly one final Artifact;
- restore semantic SHA before/after was
  `a60fa5eaf70a86e47d3de1b17a7c49561a2c6cfbc369554fc1d94a9567bab6a8`;
- cleanup removed all project containers, volumes, networks, and the generated env file.

## Verification Evidence

- Focused lock/provider/tool tests: `40 passed`.
- API full regression after lock-order repair: `407 passed`.
- Worker full regression: `143 passed`.
- Provider stub and API R800 runner tests after fixture repair: `13 passed`.
- Worker R800 acceptance tests: `7 passed`.
- Earlier Web gate: `108 passed`, ESLint, TypeScript, and Next production build passed.
- Earlier production Playwright: `9 passed, 9 skipped`.
- Changed Python files passed focused Ruff and compileall checks.
- Changed TS/JS files were scanned for unresolved identifiers during the prior full gate.

## Reverse Review

- A lock-order regression is caught by the SQLAlchemy lock trace and the real
  PostgreSQL parallel scenario.
- A stale identity-map terminal state is caught by a second-Session refresh test.
- Unsupported Claims entering the final report are caught by final link counts and
  exact Artifact marker/Claim mappings.
- A missing conflict pause is caught by the submitted Decision count and persisted
  Run events.
- Duplicate completion is caught by API/database final Artifact counts.
- Restore drift is caught by semantic snapshots plus object byte/hash comparison.
- Resource leakage is caught after both failed and passing deployments.

## Delivery Ledger

- Source branch/ref: `main` at `cf70ffd77a6bb421be2348fe1f3da1e28afa00af`.
- Repair and delivery branch: `main`; no secondary worktree or integration branch was used.
- Symptoms and root causes: the R800 Critical findings in this review, including
  the v2 PostgreSQL reverse lock order and stale identity-map state, followed by
  the v3 scripted Claim-status parsing defect.
- Changed scope: Research/Evaluation migrations and API ledger, fixed typed Worker
  executor and runtime ports, Research/Evaluation Web surfaces, observability,
  deterministic R800 acceptance, tests, artifacts, and SSoT/spec updates.
- Implementation commit: `6de0927b8416dd4e237852881e678993cd62bbea`.
- Verification: API `407 passed`; Worker `143 passed`; Web `108 passed`; ESLint,
  TypeScript and Next production build passed; Playwright `9 passed, 9 skipped`;
  canonical R800 v4, restore SHA, backup hashes and cleanup checks passed.
- Delivery target: `origin/main`; no downstream merge or cherry-pick is required.
  The linked dev-workbench checkpoint records final pushed SHA parity because this
  repository document cannot contain the SHA of its own follow-up commit.

## Remaining Gates

R803 must run paired Quick/Research cases with an explicitly approved real provider
and matching fixture, Asset scope, provider/model, Workflow, and Prompt comparison
keys. M404 must separately collect qualified target-user task evidence. Neither gate
can be inferred from deterministic R800 success.
