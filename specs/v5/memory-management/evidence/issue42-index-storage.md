# Issue42 index storage — partial implementation evidence

2026-09-29 historical first slice: PARTIAL. Current post-IC01 candidate and verification are recorded in the appended section below; implementation acceptance remains with the original reviewer. Only granted new model/test files and this evidence were written. No commit/push.

## Actual files

- packages/backend-persistence/src/citeframe_persistence/models/memory_index.py
  SHA-256 c629fecd3c06416591eece14e22a9158fc760334556e4c56c6fb5cf46037e227
- packages/memory-service/tests/test_history_index_postgres.py
  SHA-256 1f7ecf64d0af591d9bd3e1bafd3ea1c564b6e535912fc890afb2a37a8694ad23

The model adds memory_index_manifests and memory_index_entries only on explicit import. Actual scope/mode/state/digest/range checks, composite workspace FKs, active uniqueness, FTS/trigram/HNSW indexes and narrow table-local immutability triggers are present. No export, source registry, native trigger, successor migration or service is added.

## Storage meaning requiring controller clarification

Reported before implementing the affected constraints:
1. Proposed source_set encoding: ordered unique source_id array of exact {source_id,version,sha256,chunk_count}; canonical compact sorted-key UTF-8 hash. The approved section names strict ordered refs/count and byte bound, but does not fix this JSON wire/canonical encoding. Await exact approval before SQL validation/canonical hashing.
2. Does entry.config_fingerprint equal manifest.profile_fingerprint, or does it identify provider config while manifest fingerprints the full index policy? Await exact meaning before cross-profile checks.

Remaining implementation gates: strict source_set shape/hash/count/size, relational manifest/entry mode and generation coherence, source-only/current kind/version/hash checks and corresponding illegal-SQL tests, plus any resulting bounded concurrency tests. Current simple local CHECKs do NOT establish those relational properties. Do not merge this partial model as complete or activate it.

## Actual PostgreSQL evidence

Own previously stopped memory42 cluster, explicitly started for this work and stopped afterward with its exact data directory:
D:/Code/citeframe-lanes/issue42-persistence/.local-runtime/memory42-pg
PostgreSQL17.11, loopback port56492, role memory42_test.
Created a NEW database citeframe_history42_index_test. Tests require this exact database name and loopback URL and fail (never skip) when missing. Each run creates a UUID schema, installs required public vector/pg_trgm extensions in this own DB and drops only that schema in finally. No other lane database or denied workflow was used.

Command:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_HISTORY42_INDEX_POSTGRES_URL='postgresql+psycopg://memory42_test@127.0.0.1:56492/citeframe_history42_index_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_history_index_postgres.py -q -p no:cacheprovider
~~~

Final partial run: 39 passed in2.35s, exit0, no skips. Own server subsequently stopped, exit0.
Tests cover actual index DDL, cross-workspace FK rejection, private/branch manifest rejection, active uniqueness, codepoint/hash and local profile coherence, immutable activated metadata (including after retirement), entry identity, invalid zero/short/NaN/infinite ready vectors, synthetic valid vector SQL readiness, and actual FTS/trigram/RRF query. The separate-process metadata oracle proves explicit import adds exactly two tables and leaves existing table/index DDL unchanged, without model export.

Fixtures create actual native metadata tables via Base.metadata.create_all, with synthetic public chat source rows satisfying their checks. They do NOT invoke a native issuer or claim authoritative registry admission; native source bodies/permissions and exact original-slice adoption remain out of this ORM/schema fixture. No query into private revisions. No model/provider embedding call. Synthetic vector positive proves pgvector SQL plumbing only.

An initial ranking expectation of two CJK candidate lists failed (37 passed/1 failed). Direct PostgreSQL inspection showed the disposable C-locale database produces the simple FTS CJK token but no CJK trigrams. The final oracle explicitly records CJK exact FTS score1/61, English exact FTS+trigram score2/61, English substring trigram score1/61 and inactive-manifest exclusion. This is actual locale-bound lexical evidence, not universal CJK substring support or semantic recall. No production search endpoint/profile was changed to hide that limitation.

## Boundaries

No full migration/upgrade/rollback proof, source authority, all-reader authorization, native deletion/tombstone/transitive-use suppression, index build/activation or hybrid quality acceptance. Notes/units/artifacts and genuine budgeted hybrid remain required. Source-set/profile decisions above block only affected schema work; completed local constraints are retained as real partial progress. Await controller clarification, then complete/retest and submit exact candidate to original reviewer. This evidence is the only durable write-back.


## IC01 approved delta implementation — current frozen candidate

The controller resolved the two stored-meaning questions in the independently approved delta:
- lanes/issue42-index-canonical-delta.md SHA-256 3e8a8f2f98917545df3bafe19b83869db6dec32ee0b27a8c9f32f49b71974625.
- reviews/issue42-index-canonical-delta.md SHA-256 43731c925bd0f252a953674cb8a068549214fa5a03dc02fd2f1cbc8cc3ef0bd2.

Current status: complete two-file storage candidate ready for original actual-code review; NOT independently accepted, not production-integrated or activated. The initial39 result/hashes above are preserved as historical partial evidence; their missing-constraint list is superseded for this candidate by the work below.

### Exact current candidate

| File | SHA-256 |
|---|---|
| packages/backend-persistence/src/citeframe_persistence/models/memory_index.py | ec63758e965f39bffdd7e36ec08dbc9f32bfa895c88c396d04d8a4b1d23d723a |
| packages/memory-service/tests/test_history_index_postgres.py | eea4224239b8f799d4d6dcb3c965961fc1a56efdc6ae93a897cfc453c4d95a2d |

Changes remain inside the two NEW files. profile_snapshot is the only new stored field beyond the earlier two-table layout. No existing DTO/model/export/migration/registry/route/CI edits. HC02 test remains 1d17c3ada08dc31f58c1c875ce830f9099c92d47132de9eb7d29a1bf9b19532f.

### Implemented constraints and canonical boundaries

- Application TypeDecorator admission invokes strict Python source-set/profile validators. Booleans/floats fail the application integer gate. Ordered canonical UUID refs, exact member keys, BIGINT/INTEGER limits,4096 members and1MiB canonical cap are enforced without sorting/coercing input.
- Direct JSONB validation accepts mathematically integral numeric values within bounds, including decimal/exponent spellings; it does not claim original token fidelity. SQL canonical numeric output is base10 integer digits. Profile fixed numeric values follow the same two-layer rule.
- SQL canonical helper is private to the two validated finite domains; table triggers validate their shape before canonicalization/hash. Source-set and whole-profile SHA use compact key-sorted UTF-8 bytes. Python/PG exact golden bytes/hash agree, including quote/backslash/control/nonASCII/astral/combining provider model names. NUL/lone surrogate fail at Python admission and PostgreSQL JSONB input.
- Complete profile hash differs from lexical config hash; hybrid entries must exactly match manifest embedding provider/model/version/1024 dimensions/config. Lexical entries require the approved lexical subconfiguration hash and NULL embedding tuple. Nonzero finite vector readiness remains checked by vector type/local ready check; synthetic vectors do not establish relevance.
- Entry admission checks declared source membership/count/ordinal, workspace, public source kind/audience/owner, current source version/hash, index generation, profile,1200-codepoint chunk ceiling,1000-codepoint starts and advancing overlap coverage. Text SHA/codepoint length are SQL CHECKs. Native authorized original-slice equality remains outside these metadata checks.
- Activation revalidates every declared member, including zero-chunk members; exact expected count, contiguous ordinal coverage, range coherence, all entries' current source/profile and mode-specific ready states are required. Building profile/source-set/generation changes revalidate existing entries.
- Activated profile_snapshot/profile/source-set/generation/identity remain immutable after retirement. Entry identity/profile/text/ranges cannot be repointed. Active corpus entry INSERT/UPDATE/DELETE is rejected; retirement must precede cleanup.
- Workspace row serialization and manifest/source row locks protect table-local mutation/adoption. Explicit trigger lock acquisitions use NOWAIT; PostgreSQL's implicit UPDATE row lock may wait before a trigger runs. The real race fixture uses a1s lock_timeout to bound that wait and asserts SQLSTATE55P03. No successful unsafe overlap is counted as a pass.

### Actual final execution

Same dedicated database/command as the historical section above; PostgreSQL17.11, vector and pg_trgm real extensions.
Final execution: **138 passed in9.94s, exit0, zero skips**. This is the complete storage suite including application/metadata tests and real PG oracles; it is not described as138 distinct native integration cases.

In addition to prior coverage:
- Cross-language fixed goldens: empty set2bytes, single ref158bytes, complete lexical profile282bytes and distinct lexical config fingerprint.
- Source numeric token matrix and boundaries, actual application bind rejection, direct SQL NULL/unknown/missing/malformed/order/duplicate rejection.
-4096 maximal legal members canonicalize identically in Python/PG;4097 rejects. The maximum legal4096-member encoding is753,665bytes under this fixed ASCII schema, so a valid exact1MiB boundary fixture cannot exist. The explicit1MiB guard remains; oversized malformed fields reject without claiming an independently reachable valid1MiB case.
- Whole profile shapes, Unicode escaping, fixed-number layering, hash whitespace drift, hybrid tuple mismatch, profile-versus-config confusion.
- Incomplete/extra/nonready/wrong-generation/wrong-kind/wrong-version/wrong-hash entry and activation rejection; zero-chunk declared member; genuine private instruction source cannot become an index entry or activate a declared shared corpus.
- Composite FKs tested independently with the user trigger disabled only within a rolled-back test transaction; actual named FK constraints reject mismatched workspace references.
-9 real concurrent two-connection cases: entry insert/delete/pending-state/profile/source change vs activation (5); atomic old/new corpus replacement with competing activation and rollback (1); activation-held deletion/pending/source change barriers (3). Events coordinate actual overlapping PG transactions, without fake authority or fake repositories.
- Replacement observer sees old committed active corpus until the transaction commits, then exactly the new one; failed replacement rolls back retirement too.
- Explicit import still adds exactly two tables and leaves pre-existing native table/index DDL unchanged.

During development a DDL CASE expression required SQL parentheses and an invalid-mode fixture initially failed before reaching SQL; these were corrected before the final full run. The first concurrent insertion attempt used only statement_timeout and waited for the test writer's10s release deadline, then saw incomplete coverage after writer rollback. The final race protocol adds explicit1s lock_timeout and verifies the lock conflict while the other transaction is still live, releases it and separately rechecks post-commit outcomes. No failed intermediate run is reported as acceptance.

The own server was stopped after final execution via its exact data directory, exit0. Per-run schemas were removed in fixture cleanup. No other lane server/database, model or paid provider was used.

### Exact remaining integration gates

This table-local candidate proves completeness of the DECLARED source set, not that an authorized builder enumerated every eligible original in the workspace. Empty-original truth, source/body slice equality, current output-reader authorization and corpus enumeration remain real native issuer/service gates.

Source/native mutation AFTER activation, including same-transaction mutation following activation, needs the owner43 successor's source retirement/tombstones/direct-transitive suppression and native hooks; this two-file grant does not install them. Source row locks serialize concurrent mutation across the local activation boundary, but do not themselves retire already committed indexes. SQL ranking fixtures join current public source metadata; no callable runtime search or issuer was added.

The full successor migration must reproduce functions/triggers/tables/indexes and prove populated upgrade/rollback and integration lock order. ORM create_all in isolated test schemas is not that migration evidence. Existing registry still limits currently supported native source kinds; no note/unit/artifact registration or private audience expansion was introduced. C-locale lexical limitations and synthetic-vector quality limits remain as recorded above. Genuine hybrid, complete workspace/native source service and API/runtime activation remain unimplemented obligations.

Only these two product/test files and this evidence changed. Approved delta/reviewer artifacts, HC02/history/image/workflow remain frozen. No commit/push; original reviewer must accept the exact code before controller integration. Durable write-back is this evidence.
