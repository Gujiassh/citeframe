# Issue42 index storage: fresh independent Critical review

Date: 2026-10-03. Verdict: **APPROVE for the bounded index-storage / IS01 repair slice.**

This is a fresh independent review, not a continuation or approval by the original DevSpace reviewer. The controller reports that original reviewer resumption failed with `PROVIDER_UNAVAILABLE: Codex executable was not found`. The historical `issue42-index-storage.md` REQUEST CHANGES verdict remains intact as evidence of the original defect.

## Exact candidate

Checkout base: `7f41584aaa87554c5158d93129e25e8aecf7eca7`. Reviewed files were untracked candidate additions at review time. SHA-256 values were checked before and after execution:

| File | SHA-256 |
| --- | --- |
| `packages/backend-persistence/src/citeframe_persistence/models/memory_index.py` | `c3fd3b31eeaab589a2c1b60941a8e9e1fb5a4061d751da44afd04368552cdc28` |
| `packages/memory-service/tests/test_history_index_postgres.py` | `fbed151fec82299009d57973252e58b0d8b80d51430f71d59fba6dd6b1441cdc` |
| `.github/workflows/memory-index-storage.yml` | `ba2aea3b3e0501c2bc261841f910312f39f73159e207280aa78da53bc78ff22a` |

## Findings and scope

No blocking finding in this candidate. The prior IS01 stale-snapshot admission path is closed at the database write boundary: manifest INSERT/UPDATE/DELETE and entry INSERT/UPDATE/DELETE require READ COMMITTED. Both lock triggers reject unsupported isolation before snapshot-dependent queries with SQLSTATE `0A000`. Manifest DELETE acquires the workspace lock using OLD.workspace_id. Manifest lock precedes shape validation by trigger name order; shape itself also checks admission. Read-only transactions remain unaffected.

The tests cover READ COMMITTED rejection of missing/pending chunks, unsupported REPEATABLE READ and SERIALIZABLE admission, rollback and fresh-connection observation. Existing tests still cover canonical/profile shapes, active uniqueness, workspace composite FKs, immutable identities, metadata exclusion of private sources, entry readiness, codepoint/hash/range checks, real SQL indexes and competing activation barriers. READ COMMITTED NOWAIT conflicts fail closed; there is no claim that row locks refresh a stronger-isolation snapshot.

The new workflow installs the frozen API environment, checks checkout-local persistence imports before and after execution, requires exactly 156 unique collected cases, forbids skip/skipif/xfail, verifies passed setup/call/teardown for every case, and rejects PYTEST_ADDOPTS overrides. Its PostgreSQL17 pgvector service is dedicated to the exact test database. This local review executes the exact Python body; it does not establish hosted image pull, dependency installation or hosted CI success.

## Independently executed evidence

Candidate cwd: `C:/Users/baiao/Documents/Codex/2026-10-03/task/citeframe-next`. Interpreter: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B`. Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, candidate package source paths, `CITEFRAME_HISTORY42_INDEX_POSTGRES_URL=postgresql+psycopg://index42_test@127.0.0.1:56493/citeframe_history42_index_test`.

1. Complete test file, `-q -p no:cacheprovider`: **156 passed in 8.66s**, exit 0.
2. Exact Python body extracted from the workflow, without changing its import/collection/report guards: **156 passed in 8.14s**, exit 0; printed `index-storage-executed=156; skipped=0; xfailed=0`.
3. Additional in-memory reviewer probes using the real fixture and independent connections: held a workspace lock in a separate transaction, then attempted raw SQL entry UPDATE and manifest DELETE at each unsupported isolation level. All four rejected with `0A000`, rather than reaching workspace locking and returning `55P03`.
4. Additional manifest DELETE barrier probe: delete an empty building manifest without committing, then insert generation 2 in another transaction in the same workspace. Insert rejected with `55P03`. Rollback restored the building manifest, verified through a fresh connection.

All fixture runs created and dropped only their own randomly named test schemas. The controller-owned server was not stopped. No product/source/test/workflow files were edited by this reviewer; only this new review record was written.

## Remaining gates and nonblocking test improvements

Acceptance is limited to explicitly imported ORM storage and declared-set integrity. Native issuer/authorization, exhaustive original enumeration, original slice equality, migration upgrade/rollback, lifecycle retirement/erasure, runtime search/hybrid quality and UI remain unaccepted downstream work. This review does not grant production activation or merge readiness. The controller records dependency on unmerged PR56/54/49/48; those dependencies and hosted checks require separate resolution within authorized scope.

Nonblocking regression improvements: preserve the extra manifest-DELETE barrier and guard-before-lock probes as permanent cases; strengthen malformed-shape cases with matching canonical hashes so they distinguish shape rejection from digest mismatch. These are coverage improvements, not observed correctness failures. The exact-count CI guard must be updated deliberately if new cases are added.

## Follow-up: locale-aware lexical test oracle

Date: 2026-10-03. **APPROVE the narrow test-oracle repair**, preserving the preceding storage/IS01 verdict and its original hashes. The controller reports the first hosted PR58 storage run (`37104290402`, job `111149693995`, commit prefix `b415e15`) passed 155 cases and failed this lexical case because en_US.utf8 classified CJK as a word and produced two RRF channel contributions. This reviewer did not independently fetch that hosted log; the local evidence below is independently executed.

Reviewed diff changes only `test_real_simple_fts_trigram_unicode_rrf_sql`. Updated test-file SHA-256: `a66d35f30a574fd7d072fcfc029a57a16f939d87015b69d77a2c0f4a83f0185f`. Model and workflow retain the preceding exact hashes unchanged.

The old oracle fixed CJK score to `1/61` and assumed empty trigrams, which is specific to the original C-locale fixture. The repair independently classifies the literal query using the database POSIX alnum predicate, then requires exactly five trigrams or zero, exact FTS chunk ordinals `[0,1,2]`, exact trigram ordinals `[0,1,2]` or `[]`, and the corresponding exact `2/61` or `1/61` RRF score. It does not derive the expected score from the score under test. ASCII exact-word and trigram-only assertions, retired exclusion, winner identity, thresholds, SQL ranking and the 156-case count remain unchanged. No product, locale configuration, workflow or acceptance scope was changed.

Independently reran the complete 156-case storage suite with the same interpreter, environment and disposable fixture: **156 passed in 8.69s**, exit 0. A read-only catalog probe confirmed database locale `(datlocprovider, datcollate, datctype) = ('c', 'C', 'C')`; the CJK POSIX classification/trigram cardinality was `(False, 0)`. An initial `SHOW lc_ctype` metadata probe was unsupported on this server; the successful `pg_database` query supplied the locale evidence. This local run verifies the C-locale branch. Actual hosted Linux execution of the other branch remains required and is not claimed here. No new test-case skip, xfail or weakened numeric tolerance was introduced.
