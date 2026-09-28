# Issue #42 P1a implementation handoff

## Branch and artifact identity

- Workspace: `D:/Code/citeframe-lanes/issue42-persistence`.
- Branch: `work/issue42-memory-persistence`; starting SHA `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Shared contract/scaffold commit: `eac4de4` (`feat(memory): establish neutral provider contracts and package scaffold`), committed by controller after this lane's Git metadata write was refused.
- Sole shared ABI: `packages/backend-contracts/src/citeframe_contracts/memory.py`, re-exported from `citeframe_contracts`; package `packages/memory-service`. #44 imports these DTOs/ports and owns adapters/tests. No duplicate ports module exists.
- Storage is a working-tree candidate. Commit/push/draft PR remains controller work because this execution sandbox denies the worktree Git `index.lock`. No merge was attempted; no issue-closing language is intended.

## Implemented behavior

Six additive tables support attributable manual remember/correct/deactivate/delete, exact private source reads, current/history reads, immutable revisions, CAS head advancement, one successor per predecessor, operation-key replay and request-ID reconciliation. Normal access requires an injected authorizer, exact owner, recognized current membership, unarchived workspace and private management purpose. Source invalidation preserves user intent. Corrections produce fresh identities while retaining predecessor history.

Delete synchronously clears all revision conditions/content/hash bytes, including the new tombstone revision, and erases unshared instruction/source bytes while retaining provenance/support/operation IDs. History and old-create replay return content-free tombstone metadata. Shared instruction sources survive until their last legitimate dependent is erased. Transaction failure rolls the whole deletion back.

The migration installs composite FKs, strict conditions/live-erased checks, exact content hashes, immutable historical identity, mandatory same-owner confirmation support, deferred head integrity and terminal-intent validation. The head predicate evaluates transitions after both row orders are complete; advancing a head before inserting its revision cannot reactivate inactive/superseded/deleted identities. Empty downgrade retains native tables/extensions; populated memory downgrade refuses with an export/erasure guard.

No routes/UI, native hooks, provider dispatch, index/job/outbox or compaction schema is mounted. Existing chat/Research output visibility is unchanged. The later automatic shared-task compaction requirement remains outstanding; this slice does not complete #42 or parent #41.

## Developer evidence

Python 3.12.14 and installed dependencies were used read-only from `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, with `PYTHONDONTWRITEBYTECODE=1` and lane-local paths. No private profile memory or paid model was accessed.

Disposable PostgreSQL 17.11 was run on loopback port 56492 with a new cluster under this worktree's ignored `.local-runtime/memory42-pg` and database `citeframe_memory42_test`. Dedicated tests create/drop only generated schemas within that explicitly guarded database. No existing runtime database was used. The lane-owned server was cleanly stopped after verification; its ignored disposable data/log files remain for reproduction.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://memory42_test@127.0.0.1:56492/citeframe_memory42_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_instruction_memory.py -q --tb=short
```

Result: **44 passed**. Oracles include app-unavailable imports, private/shared-purpose exclusion, owner/member/archive/revocation denial, same-key races, CAS race, real after-commit acknowledgement loss, conditions-only marker erasure across all owned tables, rollback, shared-source retention, cross-owner/workspace support rejection, malformed conditions INSERTs, erased UPDATE and new-head resurrection rejection in both write orders, exact-hash checks, frozen model/migration DDL parity and empty/populated downgrade guards.

Full native Alembic chain upgraded successfully from empty through `s3a4b5c6d7e8`, then through P1a. `alembic check` reported no new upgrade operations. The final candidate also passed empty downgrade, re-upgrade and a repeated metadata check. Independent populated-native-row/schema evidence and exact final-candidate adjudication belong to `reviews/issue42-implementation.md`; developer unit counts do not substitute for that review.

The selected existing persistence/research boundary run produced 41 passes and 3 failures before the latest test additions. The failures are the legacy export equality and two 85-table count/snapshot assumptions after the approved six-table addition. This historical run preceded the authorized IR6 test update. The bounded recheck below supersedes those three failures and retains the original frozen native oracle.

## Dependency and delivery limitations

API/Worker package declarations, their locks, the transitive evaluation lock, Docker copy/import paths, deploy-export exclusions and CI neutral import/test wiring include `citeframe-memory-service`. No external package was introduced. `uv.exe` execution is denied in this sandbox, so lock/export regeneration and frozen lock checks require controller execution. Lock entries were updated narrowly and parsed, but are not claimed uv-verified. Final-image build was not run here. CI now creates the dedicated `citeframe_memory42_test` database and supplies the guarded URL; a missing URL in CI fails the fixture instead of skipping PostgreSQL checks.

SQLite native-fixture compatibility is preserved with JSON type variants and PostgreSQL-only emission of dialect-specific CHECKs. Memory commands explicitly reject non-PostgreSQL engines. The frozen PostgreSQL DDL oracle still matches every model constraint. Native regression commands passed: API `test_workspace_router.py` plus Worker `test_audio_ingestion.py` **13 passed** using the API environment; Worker `test_image_ingestion.py` **9 passed** using the existing Worker environment. Initial image-suite collection with the API-only environment lacked numpy; rerunning with the correct Worker environment passed. No SQLite result is presented as PostgreSQL integrity evidence.

Independent reviewer follow-up confirms corrections for IR1–IR5; IR6 now has the authorized boundary-test correction and passing developer evidence below, ready for independent targeted recheck. Final identity-bound acceptance and lock/image gates remain pending. Git staging was refused at `D:/Code/citeframe/.git/worktrees/issue42-persistence/index.lock`; no permission bypass was used. Controller must stage the coherent storage/dependency/doc slice, verify identity/remote, push and create a partial-foundation draft PR. Report its URL as the delivery artifact; merge remains controller-owned.

No canonical workbench/profile-memory writes were made from this lane. Durable state is this local report and the copied local memory SSoT/spec. Controller should checkpoint workbench task `memory42-p1a` after acceptance.

## Candidate file hashes

| File | SHA-256 |
|---|---|
| `packages/backend-persistence/src/citeframe_persistence/models/memory.py` | `a5dc08b1ee6e70dabc5ca9a1067741ce5f1b8ff6ec92ff1f7338d17fec3a9967` |
| `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py` | `261d30c99bb4000219264a6169b0a91ad9a267d6a774fdffc87f2f205e209155` |
| `packages/memory-service/src/citeframe_memory/access.py` | `286a3ffecdd83469c871351264283f078749ffea06622b60bd1c33dcbbbb972b` |
| `packages/memory-service/src/citeframe_memory/sources.py` | `805f7e5be3b807444615327b45bc51cba3e19ea04ba6baf24d25413e83df4ce3` |
| `packages/memory-service/src/citeframe_memory/commands.py` | `2f9285e6049ed52d4eb66e957647e1ce8a88bf0773c149b7785ca7090a07a2c7` |
| `packages/memory-service/src/citeframe_memory/lifecycle.py` | `7346ac060189247c58a6e337908c7e9bd331828d7ec596ac1121083987c611b8` |
| `packages/memory-service/tests/test_instruction_memory.py` | `6b906cd254a6b67fad6f33a3d152c58f30bd1d67078564194b014bd45e3cf5d1` |

## Bounded IR6 / F44-1 recheck — 2026-09-28

The sole shared transport port now requires keyword-only `follow_redirects: bool` with no default. Signature inspection confirmed the required keyword and boolean annotation. The #44 adapters must pass `False`; this lane changed no adapter files and makes no claim of cross-origin runtime acceptance before #44 integrates and independently tests this contract. `Usage.input_tokens` is documented as total uncached/cache-read/cache-creation input, with unknown totals remaining `None`; no fields or structures were added.

`apps/api/tests/test_persistence_boundary.py` now asserts the six explicit neutral-only model/table mappings separately. It retains the original snapshot bytes and hashes, every approved native delta, exact equality for all 85 native PostgreSQL table DDL definitions and all 97 indexes, legacy object identity/order, shared metadata identity and application-unavailable import checks. The complete table set must equal the frozen native set plus exactly the six memory tables.

Verification:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://memory42_test@127.0.0.1:56492/citeframe_memory42_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_instruction_memory.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py -q --tb=short
```

**57 passed** (44 P1a tests plus 13 persistence/research boundary tests), with the existing Starlette deprecation warning. Standalone boundary rerun: **13 passed**. On the lane-owned disposable PostgreSQL instance, empty downgrade to `s3a4b5c6d7e8`, re-upgrade to `t4b5c6d7e8f9` and `alembic check` all passed; no new upgrade operations were detected. The existing native computed-default warning remained. `git diff --check` passed.

Local `spec.md`, `design.md` and the pre-append `delivery.md` matched canonical bytes at recheck. Effective spec v4 §§13–14 and final A1 choice2 continue to govern. The ledger receives only this local delivery evidence; prior evidence is retained. No new lock edits, Git write attempt, canonical write or adapter change occurred in this bounded rework. Controller owns lock/export/image verification and separate contract commit/integration. Candidate is ready for independent targeted recheck; this record does not self-approve IR6 or F44-1.

Separate shared-contract handoff and boundary-test identity:

| File | SHA-256 |
|---|---|
| `packages/backend-contracts/src/citeframe_contracts/memory.py` | `b1a0d53b5d21bac31ac12609a5a798cceda5f9aab43eefaa4e178a3d9d5aae45` |
| `apps/api/tests/test_persistence_boundary.py` | `234b7325892351adee64e34203373c1fe2ed3d35123b3afe6044f00d758ae24f` |

## Migration whitespace-only recheck — 2026-09-28

Removed trailing spaces from 118 migration lines emitted by SQLAlchemy. The frozen DDL oracle normalizes only trailing ASCII spaces/tabs on each generated expected line, with a concise reason in the test; it still compares every complete DDL statement exactly afterward. No SQL tokens, constraints, functions, triggers or migration operations changed. A read-only comparison against the controller-staged migration confirmed the working file equals that file with only line-ending whitespace removed, and the normalized migration AST is identical.

The same combined P1a/PostgreSQL and persistence/research boundary command above passed **57 tests**. The suite includes the frozen six-table DDL parity oracle. Disposable PostgreSQL empty downgrade to `s3a4b5c6d7e8`, re-upgrade to `t4b5c6d7e8f9` and `alembic check` passed with no new upgrade operations. Existing Starlette/computed-default warnings remain unchanged. Scoped working-tree `git diff --check` passed; no Git stage/commit occurred, so the controller's existing index still contains the pre-cleanup files until refreshed.

Only the migration, its dedicated test and this evidence report were edited. Controller-owned authorization headers, controller brief, delivery ledger and Markdown line-break handling were left untouched. Prior acceptance remains scoped; targeted independent formatting/DDL confirmation is pending.

| Formatting-recheck file | SHA-256 |
|---|---|
| `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py` | `8c4b2f0e86dfb6de3f383e29247e7716a040e030179d4157717078d286836bd9` |
| `packages/memory-service/tests/test_instruction_memory.py` | `f4117dfbcb878cd26b799a8b0c5f9a0d9ec67964f1c6d882a09e3b97d774d3f1` |
