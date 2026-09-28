# Issue42 mounted management API candidate



Status: ready for original independent Critical implementation review after final local verification. Consumer-contract approval and admission ACCEPT are separate review artifacts; this report does not self-approve the mounted implementation.



## Candidate and delivered surface



- HEAD: `7d47607778a9212e9f3cb076442cd7c497c1f8ca`; controller-integrated admission source: `893de951672f1a374d552425dfb2b3e7c3e6a223`. Original integration: `32bb6764c785a0d3e424519d9a977df5182b4927`. Four source/integrated admission blobs match; reviewed raw-byte versus checkout line-ending reconciliation is in `admission-integration.json`.

- Mounted authenticated owner-private list/current/history/source, create/correct/deactivate/delete and request/operation recovery receipts. Strict DTOs and extracted live OpenAPI are available to #46.

- Manual workspace-private instruction management only. Unsupported scopes and arbitrary author/source grants are rejected. No shared recall, chat/Research/model input, native private task product, inferred user confirmation, search/index/job success, or raw source deletion is implemented.

- Unchanged #40 member dependency and original auth headers. Fresh Engine-bound command sessions avoid the dependency read transaction; shared commands lock and reauthorize actor/output purpose. Fresh guarded postcommit queries validate and render response bytes inside their transaction. Historical persisted validity is preserved; every support availability gate suppresses unavailable semantic bytes.

- Shared admission predicate and existing commands are reused without duplication. Six create/correct × content/subject/applicability cases verify422 `sensitive_content_unsupported`, no memory-table DML, six-table equality, and payload/digest log redaction.

- Signed expiring keyset cursors bind actor/workspace/endpoint/filter/record. Request identities support lost acknowledgement recovery, replay and changed-body conflict. Expected-version conflicts expose metadata only after fresh owner authorization.



## Changed file inventory



| File | Responsibility |

|---|---|

| `apps/api/src/ai_pdf_api/routers/memories.py` | Mounted routes and router-local safe errors |

| `apps/api/src/ai_pdf_api/schemas/memory.py` | Strict public request/response DTOs |

| `apps/api/src/ai_pdf_api/services/memory_management.py` | Fresh command/projection composition and signed paging |

| `packages/memory-service/src/citeframe_memory/management_queries.py` | Neutral PostgreSQL-only owner queries and gated projection; no mutation implementation |

| `apps/api/src/ai_pdf_api/main.py` | One import and one router registration |

| `apps/api/tests/test_memory_management.py` | Dedicated consumer tests |

| `apps/api/tests/fixtures/memory/management_contract_cases.json` | Frozen19-case error and readability fixtures |

| `.github/workflows/ci.yml` | New test file appended to dedicated PostgreSQL command only |

| `specs/v5/memory-management/lanes/issue42-management.md` | Mounted-candidate checkpoint |

| `specs/v5/memory-management/evidence/issue42-management/*` | Reproduction script, sanitized results, OpenAPI, exact hashes and handoff |



Existing core/deps/models/migrations/other routers and #43 extensions remain untouched. Controller-preserved admission contract and reviewer artifacts remain untouched. `candidate.json` records exact file SHA-256 values including unchanged dependencies.



## Real PostgreSQL verification



Disposable lane-owned PostgreSQL cluster, loopback56542, database `citeframe_memory42_test`, role `memory_management_test`. Full Alembic head `t4b5c6d7e8f9` is applied to the live-HTTP database. API/core fixture tests use isolated UUID schemas through the original guarded P1a fixture. No production database or credentials were used.



```powershell

$env:PYTHONDONTWRITEBYTECODE='1'

$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://memory_management_test@127.0.0.1:56542/citeframe_memory42_test'

& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest `

  packages/memory-service/tests/test_instruction_memory.py `

  packages/memory-service/tests/test_admission.py `

  packages/memory-service/tests/test_admission_postgres.py `

  apps/api/tests/test_memory_management.py `

  apps/api/tests/test_workspace_router.py `

  apps/api/tests/test_persistence_boundary.py `

  apps/api/tests/test_research_persistence_boundary.py `

  -p no:cacheprovider -q --tb=short

```



Final result: **1738 passed, zero skipped**,84.91s, one existing Starlette/httpx warning (`pytest.txt`). The dedicated API suite contains46 tests:37 PostgreSQL-backed consumer tests and9 pure DTO checks. The combined run includes1603 pure admission tests and existing static/SQLite regressions; its total is not described as entirely PostgreSQL-backed.



Coverage includes all19 frozen error cases; auth/syntax/schema precedence; unknown role, revoked membership and archived workspace; cross-owner/workspace record, revision, source, request and operation isolation; all-support/historical readability; exact source version and Unicode content; paging binding/expiry/tamper; no-write admission and clean retry; concurrent replay/CAS; fresh authorization for version metadata; after-commit database acknowledgement failure for remember/correct/deactivate; source preservation, correction successor and provenance; delete erasure and receipt replay. Frozen fixture planning labels remain design-time labels, superseded by this execution ledger.



## Separate real HTTP evidence



```powershell

$env:PYTHONDONTWRITEBYTECODE='1'

$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://memory_management_test@127.0.0.1:56542/citeframe_memory42_test'

& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B `

  specs/v5/memory-management/evidence/issue42-management/live_http.py

```



`live-http.json`:76 checks passed against actual `ai_pdf_api.main:app`, uvicorn on loopback56543, original auth headers and generated local-only token; no dependency/auth overrides. All memory creation uses HTTP. Full lifecycle, admission three-field no-write checks for both commands, logs, same-identity retry, concurrent create replay/correction CAS, source/history, cross-workspace and owner isolation, unsupported grants/scopes, deactivation/deletion and receipts are covered. Raw TCP response-drop tests for create/correct/deactivate independently verify durable recovery with the original request identity. Synthetic database acknowledgement-fault tests are separately labeled in the pytest suite.



`openapi.json` is extracted from the live mounted application and includes create/correct. API evidence does not establish #46 UI acceptance.



## CI and remaining gates



Dedicated CI command collection:1715 tests, including46 new API tests (`ci-collection.json`). Missing dedicated URL with `CI=true` demonstrably fails the existing fixture with zero skips (`ci-missing-url.txt`).



The regular `pytest apps/api/tests` step now receives the identical `CITEFRAME_MEMORY42_POSTGRES_URL` as a step-local environment entry, using the already-created disposable CI database. The dedicated selection remains explicit. No job-wide environment, service, other test command, skip/deselection or gate changed. The existing missing-URL fixture fails in CI; an unreachable configured database raises a connection error. Updated full-suite local verification is recorded in `ci-followup.md`.

Original reviewer must audit this exact mounted candidate and its evidence. Hosted/core CI, prerequisite #40/#48 merge status, release, controller commit/push and partial #42 PR attachment remain gated; neither PR is represented as merged. No parent closure or UI/shared-model acceptance is claimed. No paid calls or Git writes were made.



## Static checks and write-back



`git diff --check` and in-memory Python compilation are checked at handoff. Main registration remains exactly two lines. Neutral query import/SQLite-refusal probe passed with API/Worker imports blocked. Ruff is unavailable; no lint pass is claimed. The live HTTP script terminates its API process in `finally`; lane-owned PostgreSQL cleanup is recorded separately.



Durable write-back is confined to these lane artifacts. Private profile memory and shared workbench remain untouched. Controller can checkpoint `memory42-management-api` with mounted local evidence ready for original Critical review and the duplicate-suite CI environment wiring resolved.


Cleanup verified: fast shutdown timed out while rejecting connections; immediate shutdown of the exact lane-owned disposable cluster succeeded. Port56542 returns no response and postmaster.pid is absent. No other cluster was targeted.

## M42-I1 superseding checkpoint

See `i1-repair.md` and `i1-candidate.json`: owner-sensitive error rendering is now inside the fresh guarded transaction;1748 combined tests,56 dedicated tests including10 new reverse races, and76 separate live HTTP checks passed. CI collection is1725. Earlier counts above describe the pre-repair candidate. Original independent re-review remains required.
