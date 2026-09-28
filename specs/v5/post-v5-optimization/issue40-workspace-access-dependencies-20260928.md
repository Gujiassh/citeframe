# Issue 40 — workspace access dependencies

## Delivery identity

- Issue: https://github.com/Gujiassh/citeframe/issues/40
- Start/base: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Branch: `refactor/workspace-access-dependencies`; canonical repo: `D:/Code/citeframe`.
- Initial checkout clean; GitHub remote and matching local/global Git identity verified.
- Implemented and tested; comprehensive results recorded below. Independent Critical review,
  visible-browser acceptance, CI, and controller integration remain open.
- Controller candidate committed/pushed: `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`.
- Draft PR: https://github.com/Gujiassh/citeframe/pull/47.
- Earlier lane staging failed on `.git/index.lock` permissions; controller subsequently
  completed the scope commit/push. This lane has not committed or pushed follow-up evidence.
- No push, PR, merge, workbench state changes, private memory access, shared environment
  upgrades, or historical-worktree changes by this lane.

## Implementation

All 56 workspace-path operations across jobs, model settings, workspaces, assets, chat,
notes, research, and evaluation consume typed access dependencies. `WorkspaceAccess`
contains user ID, workspace ID, role, and the already-loaded Workspace ORM object.
Shared member/owner policy retains each route's owner message.

Validated body/query routes return `WorkspaceRequest[T]` from thin explicit dependencies:
FastAPI validates inputs once, the dependency authorizes access, and the existing handler
consumes the same typed input. Simple routes use shared dependencies directly. No eager
member mount precedes validation-first wrappers. Default FastAPI request caching remains
enabled; real router+parameter+nested-owner execution proves one query and shared context.

Existing-user checks remain on their original routes. Unknown-user workspace detail
returns 401; jobs returns 404. Public auth and auth-only workspace creation/listing remain
distinct. User headers require the internal token. SSE preserves Accept/cursor precedence,
uses a short membership session and a separate short initial-event session, and retains
fresh-session membership revalidation while tailing.

Resource scoping, report-edit state/creator/version/artifact/hash/transaction checks,
research-persistence membership checks, and Worker revocation code are unchanged.
Ownership does not grant report creator privileges. Worker archive behavior is unchanged.
No schema, role, public payload, RLS, policy engine, billing, cross-request cache, or
paid-provider change is included. Current architecture: `docs/ssot/workspace-access.md`.

## Error and schema oracles

`evidence/issue40/precedence-baseline.json` records the original error-order conflict.
The implemented composition preserves validation-first precedence. Its probe reconstructs
the original router from the starting Git object after removal of the old local helper.

`http-baseline.json` and `http-after.json` contain 378 actual HTTP cases: owners, members,
outsiders, unknown users, missing auth/user headers, invalid bodies, and invalid queries.
Every HTTP case gets a fresh database so successful archive/create requests cannot affect
later cases. Workspace timestamps are fixed fixture inputs. Only generated thread IDs/
timestamps and research request IDs are normalized during capture; status and all other
body/detail fields compare exactly.

`openapi-comparison.json`: all 64 OpenAPI operations match exactly after sorting parameter
presentation order; `/metrics` remains outside OpenAPI. Raw schemas and Git-object source
overlay are local under `.local-runtime/artifacts/issue40-dev/openapi-final/`. Historical
worktrees were not used or modified.

## Verification

Tests use existing API/Worker Python executables, `-c pytest.ini`, `-p no:cacheprovider`,
and new disposable basetemp paths below `.local-runtime/artifacts/issue40-dev/`.
Installed `uv.exe` is Windows execution-denied; environments were not upgraded.

| Scope | Result |
| --- | --- |
| Baseline model-settings + workspace tests | 29 passed |
| Pilot model-settings + precedence | 21 passed |
| Focused workspace/model-settings/notes/report/evaluation/precedence | 67 passed |
| New workspace access suite | 8 passed |
| Fresh-database HTTP oracle + access/precedence suites | 10 passed in 21.45 s |
| Access + precedence + model-settings final focused run | 29 passed |
| Embedding-current/index + image-ingestion adapted direct-call tests | 37 passed |
| Image-evidence + access + precedence after final direct-call repair | 40 passed |
| Research worker budget recovery + router recovery + report edit | 47 passed |
| Worker runtime + runtime integration, Worker venv | 35 passed in 110.26 s |
| First completed comprehensive API run | 981 passed, 11 skipped, 6 failed in 596.81 s; one direct-call test repaired/rerun, five environmental failures reproduced with baseline sources |
| Final comprehensive API rerun | 983 passed, 11 skipped, 5 environment failures in 708.74 s; exactly the five baseline-reproduced failures |
| `git diff --check` | Passed |

The new suite executes all 56 operations with valid inputs as an outsider: each returns
its expected 404 envelope, performs exactly one membership query, and leaves every DB
table unchanged. Other tests cover graph wiring, request caching, revoked/archived access,
dual-workspace resource access, executed SQL workspace predicates, evaluation/research
scoping, noncreator rejection, SSE headers, and DB/object invariants.
Four existing direct-handler test modules pass typed dependency results while retaining
their original lock, deletion-race, index, and image-evidence assertions. Independent
HTTP tests execute actual FastAPI dependencies.

### Environment-limited gates

Baseline-source replay reproduces all five remaining environment failures:
- Three `test_a2a_differential.py` tests: Windows `WinError 5` launching historical
  differential/exact-sync tools, including denied `uv.exe` execution.
- Two `test_research_policy_sse.py` tests: Node/tsx aborts before the consumer runs with
  `uv_os_get_passwd` / `ENOMEM` in `os.userInfo()`.

Baseline replay puts `openapi-final/baseline-source` first in pytest's `pythonpath`,
followed by normal source roots. Log: `baseline-environment-01.log` under the local
artifact root (5 failed). These gates remain open; no product workaround was applied.
The API venv lacks Worker-only packages; the existing Worker venv resolves that separate
collection limitation. Earlier long default-DB attempts were interrupted; final runs
set `PGCONNECT_TIMEOUT=2` without changing database configuration.

### Reproducible commands

From `D:/Code/citeframe`:

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest -c pytest.ini apps/api/tests/test_workspace_access_dependencies.py -q -p no:cacheprovider --basetemp=.local-runtime/artifacts/issue40-dev/graph-execution-01
& apps/api/.venv/Scripts/python.exe -m pytest -c pytest.ini apps/api/tests/test_research_worker_budget_recovery.py apps/api/tests/test_research_router_recovery.py apps/api/tests/test_research_report_edit.py -q -p no:cacheprovider --basetemp=.local-runtime/artifacts/issue40-dev/revocation-final-01
& apps/worker/.venv/Scripts/python.exe -m pytest -c pytest.ini apps/worker/tests/test_research_runtime.py apps/worker/tests/test_research_runtime_integration.py -q -p no:cacheprovider --basetemp=.local-runtime/artifacts/issue40-dev/worker-03
$env:PGCONNECT_TIMEOUT='2'
& apps/api/.venv/Scripts/python.exe -u -m pytest -c pytest.ini apps/api/tests -q -p no:cacheprovider --basetemp=.local-runtime/artifacts/issue40-dev/api-final-02
& apps/api/.venv/Scripts/python.exe specs/v5/post-v5-optimization/evidence/issue40/http_oracle.py specs/v5/post-v5-optimization/evidence/issue40/http-after.json
& apps/api/.venv/Scripts/python.exe specs/v5/post-v5-optimization/evidence/issue40/openapi_oracle.py .local-runtime/artifacts/issue40-dev/openapi-final
```

## Isolated live runtime

- Web: http://127.0.0.1:18430
- API: http://127.0.0.1:18400
- PostgreSQL: loopback 18432, newly initialized directory, `issue40_accept` DB.
- MinIO: loopback 18410/18411, new storage directory, `issue40-synthetic` bucket.
- Runtime root: `.local-runtime/artifacts/issue40-dev/runtime/` (gitignored).
- Background services started hidden. Existing user environment files, data, services,
  and historical worktrees untouched. Credentials remain only in the ignored local file.
- Providers have no real keys and point to loopback. No paid calls or Worker model
  execution. Completed research/ingestion states are deterministic synthetic fixtures,
  with no claim of model-quality or real-user evidence.

Fixture scenario: A/B workspaces, an A-only member, an owner with both memberships, and
B's separate owner. Both workspaces have notes, threads, actual PDF objects/page metadata,
and ingestion-job records. A has a completed synthetic report created by the A-only
member. The workspace owner can view the report and receives 403 when editing it.

`live-api.json` records 35 actual localhost API checks: valid reads and persisted note,
model-setting/report saves; auth/user failures; membership/resource/owner isolation;
invalid-input precedence; noncreator report rejection; stale version; SSE headers/event
delivery; next-request revocation; archived-workspace rejection. The rejected-request
block compares all rows in all tables and every object's name/etag/size before/after,
with no changes. Membership/archive fixtures are restored afterward.

`asset-runtime.json` adds actual PDF detail/file reads for A/B with byte hashes matching
storage. `web-bff.json` verifies Web login, session-cookie creation, and BFF-authorized
workspace listing, excluding credential/cookie values.

Local scripts/logs: `runtime/run.py`, `seed.py`, `verify.py`, `complete_pdf_fixture.py`,
`initdb.log`, `migrate-02.log`, and API/Web/MinIO/Postgres logs. The isolated database is
migrated through `s3a4b5c6d7e8`. The controller owns the visible browser walkthrough; HTTP
BFF checks do not substitute for that acceptance.

## Modified scope and remaining risks

Product: nine router modules (`deps`, `jobs`, `model_settings`, `workspaces`, `assets`,
`chat`, `notes`, `research`, `evaluation`). Tests: two new permission suites and four
existing direct-call adaptations. Docs: SSoT access document, README/architecture links,
this ledger, and bounded synthetic evidence files.

`assets.py` remains a large existing router. This change adds request-boundary composition
without moving business/storage logic; a broader split is outside this refactor. Future
validated inputs must be added to the thin dependency to retain error order. SSE uses
two short initial sessions; polling and service transaction checks are unchanged.

Independent final Critical approval, five environment-limited gates, remaining browser
acceptance, CI, merge, and total-delivery acceptance remain open. Controller candidate
and draft PR are recorded above. This lane remains available for original-developer rework.
Durable write-back is confined to repo SSoT/spec/evidence; controller-owned workbench
records and private memory remain untouched.


## Final lane state

- Controller candidate: `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`, pushed with draft PR47.
  This follow-up changes evidence/docs only, without another lane commit or push.
- Final comprehensive results and exact skipped/failed node IDs:
  `evidence/issue40/verification-summary.json`. The 11 skips cover PostgreSQL migration/retrieval/configuration-concurrency and
  historical differential prerequisites; live issue40 PostgreSQL
  checks use the separate isolated runtime described above.
- Concurrent unrelated untracked files appeared during verification:
  `docs/ssot/memory-management.md`, `specs/v5/memory-management/spec.md`, and
  `specs/v5/memory-management/delivery.md`. They were not edited or included in this lane.
- Original-developer rework lane remains available. Controller acceptance and integration
  remain open.

- Final isolated API was restarted from the final source only; Web sessions and fixture
  data remained in place. All 35 live API checks passed again with complete rejected-write
  DB/object snapshot equality. Final server logs: `runtime/api-final.out.log` and
  `runtime/api-final.err.log` under the local artifact root.


## Independent review follow-up

The independently authored review remains controller/reviewer-owned at
`reviews/issue40-critical-review-20260928.md`; this lane did not edit that file.

F1 (synthetic report provenance): repaired only the designated generating attempt's
output hash to match the existing artifact and actual stored bytes. The seed script now
sets that link when installing synthetic content. The unchanged complete artifact-detail
domain validator passes, and artifact detail/content/report-edit reads return 200 for
both owner and creator (six live requests). Evidence: `evidence/issue40/provenance-repair.json`.
No note, saved report edit, artifact bytes, or production validator was changed by this
repair. Controller subsequently reported that the visible report page renders and the
creator save succeeds. Controller subsequently confirmed two-tab conflict/draft recovery and new-tab persistence
passed; see the CI follow-up below.

F2 (initial SSE session boundary): implementation decision is to retain two short initial
sessions. It keeps the access dependency limited to authentication/header validation and
membership, without retaining a session across streaming or adding an event-data loading
responsibility to the permission dependency. Independent measurement found 4 SQL queries
and 1 membership query in both baseline and candidate, with initial sessions changing
from 1 to 2. The extra pool checkout/transaction boundary is explicit; this is not a claim
of identical session lifecycle. No permission lock or write transaction was moved, and
fresh polling checks remain. Controller explicitly accepted this bounded F2 tradeoff on
2026-09-28; identical session lifecycle is not asserted.

The nine-file product digest still matches the review checkpoint:
`4dd71da985aa47bb8ea6f3be8ae0ade44978e4efcd1b16bbeb28f3ede02e3349`.
Subsequent changes concern the strengthened fresh-database oracle, evidence/docs, and
ignored synthetic fixture repair. Controller has since committed/pushed the candidate
identified above. Independent final approval, remaining browser checks, PostgreSQL
evidence-scope acceptance, and environment/CI gates remain open.

## Bounded PostgreSQL and model-setting follow-up

Product code remains identical to candidate `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`.
No controller A/B note/report was reset or edited in this follow-up. Issue41 documents,
reviewer artifact, private memory, and workbench state were not edited.

### Browser model-setting fixture

Only A generation was changed from inherited/unconfigured revision 2 to an override at
revision 3. It uses `http://127.0.0.1:18481/v1`, `openai_chat_completions`, and model
`issue40-synthetic-generation-no-calls`. A had no existing configured key; an explicitly
fake local key was established in an ignored local file. Once stored, a same-base model
name save can omit the key. Live PATCH/GET returned 200 and `apiKeyConfigured=true`.
Embedding was not changed; no provider request was made.

The isolated `runtime/run.py` now allowlists only origin `http://127.0.0.1:18481` for
`127.0.0.1/32`. Only the identified isolated API was restarted, hidden; Web, PostgreSQL,
MinIO, sessions, and A/B notes/reports remained in place. API logs:
`runtime/api-model.out.log` and `runtime/api-model.err.log`. Evidence:
`evidence/issue40/model-browser-ready.json`. Reproduction helper:
`apps/api/.venv/Scripts/python.exe specs/v5/post-v5-optimization/evidence/issue40/model_browser_setup.py`.
Do not rerun preparation during the controller's model-settings edit. The helper retains
an existing same-base key; its first-run key file is ignored. Browser save/reload
acceptance is controller-owned, independent of this API readiness check.

Web URL: `http://127.0.0.1:18430`. Local credential paths only:
`.local-runtime/artifacts/issue40-dev/runtime/credentials.json` (login/runtime) and
`.local-runtime/artifacts/issue40-dev/runtime/synthetic-provider.json` (fake local key).

### PostgreSQL safety evidence

Command, from repository root:

```powershell
apps/api/.venv/Scripts/python.exe specs/v5/post-v5-optimization/evidence/issue40/postgres_safety.py > .local-runtime/artifacts/issue40-dev/runtime/postgres-safety-final.log 2>&1
```

Exit 0; six bounded checks passed on PostgreSQL **17.11**, migrated through
`s3a4b5c6d7e8`, database `issue40_safety_1ab12e684a6c`. Evidence:
`evidence/issue40/postgres-safety.json`. Each invocation creates a new explicitly
synthetic DB in the isolated cluster and new workspace-based MinIO prefixes. The
acceptance database and browser fixture IDs are not used. No schema constraint was
removed or relaxed, no product code was patched, and no external provider was called.

- Actual Worker-facing claim after revocation: 403 `research_permission_denied`, idle
  run cancelled with `creator_membership_removed`, zero work attempts created.
- Actual heartbeat after revocation: 403, run becomes `cancel_requested`, existing active
  attempt remains running for the established cancellation protocol.
- Actual persistence adoption finalizer with a synthetic uploaded publisher intent:
  revocation changes intent to `compensating`, run to `cancel_requested`; zero final
  artifacts and zero completion events. The existing uploaded object is unchanged.
  Its compensation is pending; this check does not claim a cleanup sweep ran.
- Two independent PostgreSQL sessions saving expectedVersion 0 concurrently: exactly
  one success/version 1 and one 409 `report_edit_version_conflict`.
- Repeated at expectedVersion 1: exactly one success/version 2 and one 409.
- Revocation after a successful preliminary membership read, while the report save is
  demonstrably waiting on the PostgreSQL run lock (`pg_stat_activity` reports `Lock`):
  after lock release, service recheck returns 403. The complete edit row remains equal
  and the real MinIO original-report byte hash is unchanged.

Fixture preparation uses actual request dependencies for run creation/plan approval,
existing deterministic plan builders, and migrated PostgreSQL constraints. Worker
claim/heartbeat and report-write services execute unchanged. The adoption case is a
narrow **finalizer boundary** fixture with an uploaded intent and publisher attempt;
it does not validate end-to-end publication preparation or successful report provenance.
Report edit checks validate actual original object bytes/hash, with synthetic
completed-report state. Full view provenance was separately validated in the F1 repair.

Residual scope: no long-running Worker process, broad multi-Worker stress, crash/restart
schedule, compensation sweep, or exhaustive revocation interleaving. Controller decides
whether this bounded real-PG evidence closes the required race-safety gate. Earlier
harness attempts exposed fixture-only FK/required-field issues and failed before a final
result (runs 01-05); run 06 passed, followed by the strengthened final pass. Logs
`runtime/postgres-safety-01.log` through `-06.log` are retained. The final
script uses valid ordered seed data; no fixture constraint was bypassed. Disposable
`issue40_safety_*` databases/prefixes are retained in the isolated runtime; none were
removed and no existing user path was recursively deleted.

### Remaining gates

Controller-visible model save/reload and report conflict/draft acceptance have since
passed (recorded below). Final Critical review, CI/external service disposition,
controller merge, and total delivery remain open. Prior comprehensive API result remains
983 passed / 11 skipped / 5 environment-reproduced failures; this bounded follow-up does
not convert it to an all-green suite. Lane remains available for original-developer CI
or review rework. Durable write-back is this owned ledger/evidence; no private-memory or
controller-owned state update was made.


## PR47 CI rework — original developer lane

Exact candidate CI log: `.local-runtime/artifacts/issue40-ci-635bb2b.log`. Linux API
recorded 992 passed / 6 skipped / 1 failed; Worker acceptance recorded 57 passed /
411 deselected / 1 failed. The five previously recorded Windows environment failures
passed on Linux. This slice repairs only the two diagnosed test/oracle regressions.

1. SQLite stripped the fixed workspace fixture's timezone; the unchanged DTO interpreted
   the resulting naive timestamp in the machine's local timezone. The oracle fixture
   now restores UTC only for its exact known fixed timestamps on ORM load/refresh.
   No product conversion changed, and no response normalization was added. A regression
   checks actual SQLite load, refresh, and HTTP serialization in the native host timezone
   and, on POSIX, `UTC0` and `CST-8`.
2. The Worker mixed-workspace test now gets `WorkspaceAccess` from the actual
   `require_delete_asset_access` dependency before calling `delete_asset`. All deletion,
   cleanup, generation, and late-ingest non-resurrection assertions remain intact.
   Worker/tools/infra Python imports/calls were audited; no other stale handler caller
   was found. Remaining router imports use unchanged helpers or mount the router.

The baseline overlay was freshly extracted using `git show` from original
`8812fda4d69b7f0e654e749c357fa05b5e8da72f` for all nine router modules, with package-path
shims only. Local overlay: `.local-runtime/artifacts/issue40-dev/ci-baseline-source`.
Source hashes, exact commands/results/log paths: `evidence/issue40/ci-rework.json`.
Both oracle captures returned 378 cases and match exactly. Compared to the prior
baseline, only indices 18/19 changed: fixed fixture createdAt/updatedAt now serialize
as `2026-09-28T00:00:00+00:00`; all other payload/status/detail fields are unchanged.

Verification:
- API access + permission-precedence suites: **11 passed, 2 skipped**, 22.41s. The skips
  are only POSIX timezone switching on Windows; native UTC+8 load/refresh/HTTP passed.
- Full CI Worker acceptance selection (`--strict-markers -m acceptance apps/worker/tests`):
  **58 passed, 411 deselected**, 200.78s, using the existing Worker venv.
- `git diff --check`: pass. Nine product router modules remain unchanged from candidate.
- Full API suite was not rerun in this bounded slice; Linux CI rerun remains required.

Controller browser evidence at `.local-runtime/artifacts/issue40-controller-browser.md`
now confirms generation revision4 model-name save/reload with credential field untouched,
report creator save, new-tab persistence, two-tab conflict, and preserved-draft recovery.
No browser fixtures were modified during this CI slice.

The pinned quay MinIO image still returns unauthorized for conflict-services and
research-services. This external gate remains controller-coordinated; neither workflow
nor image source was edited or bypassed. Independent final review, CI rerun, controller
merge, and total delivery remain open. No commit/push, reviewer artifact, Issue41,
workbench, private-memory, schema, or product changes in this rework.
