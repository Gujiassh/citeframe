# Instruction/admission fixture integration

Scope: one authorized test file, `packages/memory-service/tests/test_instruction_memory.py`. Approved compaction45, the prior two head-compatibility tests, migrations, native snapshots, workflows and prior reports remain unchanged. No product or contract change; original command/admission error, permission-precedence, no-DML, replay and CAS assertions remain intact.

## Reproduction and fixture separation

User reported hosted59failed/1610passed. Root's hosted-log request was network-blocked; that hosted result is reported evidence, not locally fetched or independently reproduced as a whole.

Developer authentic local RED on original fixture: **2 failed,42deselected in1.21s**. `remember` attempted an actual memory_uses INSERT through current ORM and PostgreSQL rejected missing `consumer_snapshot_id`; the frozen t4 DDL/current ORM equality also failed. Original fixture created three native ORM tables and invoked t4 directly, omitting the successor schema used by current runtime models.

Approved local separation:
- `pg`: genuine complete Alembic chain to literal `u5c6d7e8f9a0`; current command/admission tests inherit this fixture unchanged.
- `pg_t4`: genuine complete chain to literal `t4b5c6d7e8f9`; historical catalog and downgrade tests remain isolated from current memory commands.
- Shared local helper first refuses any database except `citeframe_memory42_test`, provisions vector/pg_trgm in public, verifies location, and uses a UUID test schema with finally cleanup. No create_all or hand-built native-table substitute.
- Historical empty downgrade/re-upgrade asserts t4 -> s3 -> t4 and exact retained workspace rows. Populated downgrade refusal uses a historical raw instruction INSERT, without current memory ORM/commands on t4.
- Historical catalog checks independently hardcoded canonical t4 DDL SHA-256, exact six-table set, explicit original columns/nullability, check names and index names.
- Current six-table parity uses real u5 catalog and Alembic compare_metadata with type and server-default comparison, plus explicit u5 consumer columns and version.

The bare-database prerequisite was exercised on the developer-owned56493 cluster:0 user tables and no vector/pg_trgm before the first full-chain fixture. The helper installed both extensions in public. The separate43 database was retained.

## Execution evidence

- Initial focused bootstrap:3passed/1failed6.25s; new historical column literal omitted nullable http_status. Corrected the fixture literal.
- Initial full instruction/admission/admission_postgres/frozen-p1a run:1708passed/1failed146.45s; new historical index literal omitted uq_memory_source_current. Corrected the literal without relaxing checks.
- Final historical catalog/current ORM defaults/downgrade focused run: **3passed,42deselected5.19s**.
- Final four-module run: **1709 passed in175.66s**, exit0, zero skips. Frozen test identity remained unchanged during execution.

All local executions above are `/root/core_implementation` developer-side evidence. No skipped tests establish acceptance. Developer-root owns the separate follow-up run; it does not confer appointed independent-review authority. The existing CI missing-PG failure check and test-only database refusal remain unchanged; optional local missing-PG behavior was not weakened.

Command environment: PYTHONDONTWRITEBYTECODE=1, package src roots and apps/api/src on PYTHONPATH, CITEFRAME_MEMORY42_POSTGRES_URL=postgresql+psycopg://memory43@127.0.0.1:56493/citeframe_memory42_test, CITEFRAME_MEMORY43_POSTGRES_URL with the same cluster and citeframe_memory43_test. Existing API Python runs:

```text
-m pytest packages/memory-service/tests/test_instruction_memory.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_admission_postgres.py packages/memory-service/tests/test_compaction_p1a_compatibility.py -q --tb=short -p no:cacheprovider --basetemp=.local-runtime/fixture-final-all
```

## Identity and remaining boundary

Changed test SHA-256: `E6A33A6461785F3AFB371B647C0DCF28776DEA46310A76C7FB06C975ED5D2AED`.

AST comparison to HEAD confirms existing function changes limited to pg and the historical downgrade test; the obsolete frozen-DDL/current-model test was replaced by separate historical/current catalog oracles. Every other original command/admission function body is unchanged. Approved45-file readback:zero mismatches. Scoped diff-check clean.

The original85-table/97-index oracle is located in `apps/api/tests/test_persistence_boundary.py` and `apps/api/tests/fixtures/citeframe-a1b-before-metadata.json`, retained byte-identical:
- boundary SHA-256 `234B7325892351ADEE64E34203373C1FE2ED3D35123B3AFE6044F00D758AE24F`
- snapshot SHA-256 `100C42F7BDCDB3E816FF780E25260EBEA66E889917293E2154CD9FF12585B55E`

Root separately reports read-only boundary2failed/5deselected0.19s:four extra compaction exports and95 versus91 table expectation. This requires separate ownership; no boundary file was edited or accepted here. No hosted green or whole-CI completion is claimed. No Git/private/global/canonical writes. Root coordinates final local PostgreSQL shutdown.

Entry HEAD: `b4e773a8fed882cd8cd8c6164c2b8814299eab56`. Controller committed the prior head-test correction during this work; final observed HEAD: `0315a735bc6206b87a2e9e49d3ecd72a56f9205b`. Both prior head-test hashes stayed unchanged. No Git writes by this lane.

## Final developer-root follow-up

Developer-root executed the frozen test identity serially against the developer-owned56493 cluster: **98 passed in139.97s**, exit0, zero skips. Modules: instruction_memory, admission_postgres, compaction_schema. This includes the explicit historical t4/current u5 catalogs, server defaults, downgrade barriers and full-chain native schema oracles. It is a separate developer-root execution, not appointed independent review or hosted CI evidence.

```text
-m pytest packages/memory-service/tests/test_instruction_memory.py packages/memory-service/tests/test_admission_postgres.py packages/memory-service/tests/test_compaction_schema.py -q --strict-markers --tb=short -p no:cacheprovider --basetemp=.local-runtime/pytest-fixture-integration-root
```

Both42/43 test database environment variables point to their separate named databases on56493. Final admission_postgres matches HEAD (git diff exit0), SHA-256 `0D430E60BA5138E351A61443425D78CB966EEEF6F82CCB038CFE6A9508F976C4`. Previous head-test hashes remain `52F83664473A9644829C4B50AC718E171197D8C0A6668F43AEB79DD2418CCD05` and `B5F85E71FBF92AEE4144D7B48CEBD5B65220546C2F703909595D77D30DBFC6E6`. Approved45 and original85-table/97-index artifacts remain byte-identical.

All lane and developer-root tests are complete. This fixture correction is ready for targeted review. The separate boundary2 failures remain unresolved outside this grant; no whole-CI acceptance is asserted. No active child task or Git write. Root coordinates shutdown of the developer-owned PostgreSQL; no other cluster was operated.

Final developer-root closeout: all required agents and verification sessions completed. Own PostgreSQL stopped normally; log confirmed `database system is shut down` at2026-09-29 02:01:09 CST. Final core45 raw-hash reconciliation remains zero differences. Original-reviewer acceptance of this fixture correction is pending; the two out-of-scope persistence-boundary failures remain explicitly open. Durable write-back is this new report only.
