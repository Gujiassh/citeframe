# Issue 40 — workspace access dependencies

## Delivery identity

- Issue: https://github.com/Gujiassh/citeframe/issues/40
- Start/base: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Branch: `refactor/workspace-access-dependencies`; canonical repo: `D:/Code/citeframe`.
- Initial checkout clean; GitHub remote and matching local/global Git identity verified.
- Implemented and tested; comprehensive results recorded below. Independent Critical review,
  visible-browser acceptance, CI, and controller integration remain open.
- Git staging was attempted after identity verification and failed creating
  `.git/index.lock` with `Permission denied`. No commit was created; controller Git
  metadata write access is required. No permission bypass was attempted.
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

Independent Critical review, five environment-limited gates, controller-visible browser
acceptance, CI, push/PR/merge, and total-delivery acceptance remain open. Scope commits
will be recorded below. This lane remains available for original-developer rework.
Durable write-back is confined to repo SSoT/spec/evidence; controller-owned workbench
records and private memory remain untouched.


## Final lane state

- Commit IDs: none. Staging failed on `.git/index.lock` permissions; all issue40 changes
  remain unstaged. No push/PR/merge was attempted.
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
repair. Controller can resume visible report save/reload/conflict/draft checks.

F2 (initial SSE session boundary): implementation decision is to retain two short initial
sessions. It keeps the access dependency limited to authentication/header validation and
membership, without retaining a session across streaming or adding an event-data loading
responsibility to the permission dependency. Independent measurement found 4 SQL queries
and 1 membership query in both baseline and candidate, with initial sessions changing
from 1 to 2. The extra pool checkout/transaction boundary is explicit; this is not a claim
of identical session lifecycle. No permission lock or write transaction was moved, and
fresh polling checks remain. Final controller disposition remains part of acceptance.

The nine-file product digest still matches the review checkpoint:
`4dd71da985aa47bb8ea6f3be8ae0ade44978e4efcd1b16bbeb28f3ede02e3349`.
Subsequent changes concern the strengthened fresh-database oracle, evidence/docs, and
ignored synthetic fixture repair. A completed candidate SHA is still blocked by Git
metadata permissions. Independent final approval, visible report editing, real-PG race
scope disposition, and environment/CI gates remain open.
