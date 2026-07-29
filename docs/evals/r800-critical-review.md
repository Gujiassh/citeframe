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
| Real-model quality | blocked | R803 strict v4 completed Quick 6/6 and Research 5/6; one sample has no release threshold and one Researcher schema failure remains |
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

## R803 First Provider-Backed Baseline

The first approved real-model package ran on 2026-07-29 with `openai / gpt-5.5`,
all six R100 cases, the three frozen PDF/Image assets, and scorer `r100-v1`.
Canonical evidence is in [`artifacts/r803-v1/`](artifacts/r803-v1/), with the
frozen package in [`r803-evaluation-package-v1.json`](r803-evaluation-package-v1.json)
and the detailed run record in
[`r803-real-model-first-run.md`](r803-real-model-first-run.md).

| Area | Result | Evidence |
| --- | --- | --- |
| Comparison keys | pass | Fixture, Asset scope, provider/model, provider profile, and scorer hashes match |
| Quick engineering | pass | 6/6 cases completed; 6 provider calls; USD 0.084350 |
| Research engineering | fail | 4/6 cases completed; 36 provider calls; USD 0.578043 |
| Strict output handling | pass | Both concatenated pseudo tool-call/result payloads failed closed as `researcher_invalid_output` |
| Model-quality release | blocked | One execution per case/mode and no approved release threshold; `not_evaluable` |
| User value | blocked | M404 evidence remains absent; `not_evaluable` |
| Product stage | pass | Remains `internal_preview` |

The two failed Research cases were `r100-refuse-energy` and
`r100-refuse-customer`. The model prefixed the required Claims object with a
second JSON object resembling a tool call. The evaluator intentionally does not
extract a later JSON fragment or coerce the payload. R803 therefore remains open.

The complete Agent result schemas used by this evaluation are frozen separately
as `research-agent-results-v1` and included in the Research prompt-binding hash.
They are injected only by the R803 evaluator. Production Research continues to
send the existing V2 runtime schema values, so this evidence does not silently
change an append-only PromptVersion or historical replay contract.

## R803 Strict Structured-Output Follow-Up

The evaluator-only follow-up freezes Responses strict JSON Schema without changing
the production provider or Research V2 prompt/persistence contracts. Complete local
schemas remain authoritative; provider schema limitations do not enable coercion or
fragment extraction. The raw evaluator adapter now retains failed-response usage and
retries only frozen transport-level failures.

The immutable history is:

| Run | Result | Review judgment |
| --- | --- | --- |
| [`artifacts/r803-v2/`](artifacts/r803-v2/) | Quick 5/6; Research 0/6 | Diagnostic only; first wrapper undercounted failed no-text response usage, so cost is not canonical |
| [`artifacts/r803-v3/`](artifacts/r803-v3/) | Quick 1/6; Research 1/6 | Valid SourcesData outage evidence dominated by connection/no-text failures |
| [`artifacts/r803-v4/`](artifacts/r803-v4/) | Quick 6/6; Research 5/6 | Current canonical strict run; one transport retry recovered and `r100-refuse-customer` failed the complete local Researcher schema |

V4 keeps all six v1 comparison keys. Quick used 6 calls and USD 0.086065;
Research used 36 calls and USD 0.568163. The v1 concatenated-object failure no longer
occurred and `r100-refuse-energy` completed. The remaining failure was not normalized
or rerun until green. Model quality, M404, and product stage remain respectively
`not_evaluable`, `not_evaluable`, and `internal_preview`. Full evidence and hashes are
in [`r803-strict-structured-output-follow-up.md`](r803-strict-structured-output-follow-up.md).

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

## Hosted CI Repair

The first hosted run for the delivered R800 baseline, GitHub Actions run
`30351908864` at `main@9e4064e7fa39809c06a6d1d87dca3fa4e885e481`, exposed three CI-environment
defects after the local release gates had passed:

- router tests sent the development default internal token instead of the token
  configured by the CI environment, causing 75 authentication failures;
- the Worker deploy export omitted CI's `--no-emit-package ai-pdf-api` option,
  so the retained requirements file did not match the deterministic CI export;
- the hosted Ubuntu image supplied PostgreSQL 16 client tools while the service
  and deployment baseline use PostgreSQL 17, so the Asset `pg_dump`/`pg_restore`
  migration oracle rejected the client/server major-version mismatch.

The first repair commit fixed those failures, but hosted run `30353632850`
exposed two remaining assertions that encoded the local `.env` Ollama provider
and model instead of the effective application settings. Worker, Web, and Web
E2E passed in that run; API completed `405` tests and failed only those two
configuration-dependent assertions.

The configuration-aware assertion repair then passed all `407` API tests in
hosted run `30354094055`. That run exposed a final workflow error after the test
suite: Alembic was launched from the repository root without an explicit
`apps/api/alembic.ini`, so it stopped before migration with
`No 'script_location' key found in configuration`. The workflow now supplies the
configuration path for both `upgrade head` and `check`.

The repair reads the configured API internal token in router tests, regenerates
the Worker deploy requirements with the exact CI command, and installs/selects
the official PostgreSQL 17 client before the API test step. Configuration
metadata assertions now compare against the effective `Settings` values and
pass under both the local Ollama configuration and clean-CI OpenAI defaults. The
repair does not change an API contract, persisted payload, save semantic,
migration, or product runtime behavior.

Local repair evidence:

- API full suite with the CI token and PostgreSQL 17: `407 passed, 1 warning`;
- the two configuration-sensitive route tests passed under both local and
  clean-CI provider/model settings: `2 passed` in each environment;
- PostgreSQL Asset dump/restore migration oracle: `1 passed, 1 warning`;
- Worker full suite: `143 passed`;
- API deploy export gate: clean;
- Worker deploy export regenerated twice with identical SHA-256
  `f149735bac2a7057200e403435d820db7950cd40ad730df8b6ed58362667ec5f`;
- changed API tests passed Ruff `F821/F822/F823` and `compileall`;
- workflow passed `actionlint` v1.7.7 and YAML parsing;
- repository diff passed `git diff --check`.

Repair delivery ledger:

- Source branch/ref: `main@9e4064e7fa39809c06a6d1d87dca3fa4e885e481`.
- Repair branch/target: `main` -> `origin/main`; no downstream merge or
  cherry-pick is required.
- Changed scope: hosted workflow setup, test authentication fixtures, generated
  Worker deploy requirements, and this review record.
- Commit/push state: the linked dev-workbench checkpoint records the exact
  repair commit and final hosted run because this commit cannot self-reference
  its own SHA.

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

R803 has an approved strict paired follow-up, but remains open because Research
completed only five of six cases and no sample/release threshold exists. The next
R803 slice must first freeze that threshold and decide whether the remaining complete
schema failure is a measured model failure or requires a new explicit contract; it
must not rerun the same package until green. M404 must separately collect qualified
target-user task evidence. Neither gate can be inferred from R800 or these R803 samples.
