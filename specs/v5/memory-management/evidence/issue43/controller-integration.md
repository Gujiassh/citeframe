# Issue43 post-integration migration-test compatibility

Status: bounded two-test-file correction ready for original-reviewer targeted acceptance. The approved45-file neutral core is unchanged. This report is authored by development-lane `/root`; its verification and the implementation worker's verification are developer-side evidence, not the external controller or appointed reviewer.

## Integration identity and ownership

- Current inspected HEAD: `b4e773a8fed882cd8cd8c6164c2b8814299eab56`.
- External controller reports core commit `d4a0c12`, followed by accepted PR49 at `812ebb1` merged into the current HEAD; three documentation conflicts were resolved by that controller.
- Entry dirty state contained only generated `.tmp/`. No existing user changes were overwritten.
- Current core manifest:45paths; entry and final raw SHA-256 comparisons both found zero mismatches. No migration/core/workflow/previous evidence or approved contract was edited.
- Implementation remains `/root/core_implementation`; no new agent or delegate was spawned. `/root` inspected scope/diff, ran separate verification and owns this new report.

## Exact correction

`apps/api/tests/test_research_migration.py`: expect exactly one literal head `u5c6d7e8f9a0`, explicitly assert its parent `t4b5c6d7e8f9`, retain strict `t4b5c6d7e8f9 -> s3a4b5c6d7e8 -> r2f3a4b5c6d7` edges.

`apps/api/tests/test_asset_migration.py`: after upgrade to head, dump/restore and rejected destructive rollback, both source and restored databases must retain literal `u5c6d7e8f9a0`. All historical migration targets, legacy snapshots, payload comparisons, encrypted-configuration rollback refusal and corruption negatives remain unchanged. No expected value is derived dynamically from the observed head.

The full diff is two replaced assertions plus one added edge assertion. Existing migration DDL spacing/test EOF style exceptions were not touched.

## Verification and executor provenance

| Executor | Scope | Result |
| --- | --- | --- |
| External controller, user-reported | Pre-fix one_evolvable assertion |1failed13deselected0.30s; expectedt4/actualu5 |
| Original implementation worker | Same pre-fix red reproduction |1failed13deselected0.28s |
| Original implementation worker | Initial full research+asset modules |17passed1skipped19.20s; dump/restore CLI discovery missing in child PATH; not acceptance |
| Original implementation worker | Full research+asset modules with actual PG and resolved CLI |18passed22.36s, zero skips |
| Development-lane `/root` | research_migration + evaluation_migration + research_conflict_migration |19passed34.63s, zero skips |
| Development-lane `/root` | asset_migration + research_publication_intent_migration |7passed20.10s, zero skips |

Runs overlap and are not summed into a unique aggregate. Successful runs emitted one existing Starlette/httpx deprecation warning. No paid/live provider calls or hosted CI execution occurred.

Actual runtime: existing API Python `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, own isolated PostgreSQL17.11 on127.0.0.1:56493. Tests created disposable databases through their unchanged fixtures. Real `pg_dump` and `pg_restore`17.11 executed; root printed resolved executable paths and versions. In the Python launcher, PATH was explicitly prefixed with `D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin` to make CLI discovery reliable. This did not monkeypatch tests or bypass the dump/restore oracle.

Common options: `-q -p no:cacheprovider --tb=short`, `PYTHONDONTWRITEBYTECODE=1`, lane-local apps/api/src, apps/api/tests, apps/worker/src and packages/*/src PYTHONPATH. Root used explicit unique basetemp directories inside `.local-runtime`. Real PG runs set `AI_PDF_DATABASE_URL=postgresql+psycopg://memory43@127.0.0.1:56493/citeframe_memory43_test`; root also set `CITEFRAME_TEST_POSTGRES_URL` to that own URL for the publication-intent PG oracle.

Commands after environment setup:

```powershell
python -m pytest apps/api/tests/test_research_migration.py apps/api/tests/test_asset_migration.py -q -p no:cacheprovider --tb=short
python -m pytest apps/api/tests/test_research_migration.py apps/api/tests/test_evaluation_migration.py apps/api/tests/test_research_conflict_migration.py -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/pytest-ci-head-root
python -m pytest apps/api/tests/test_asset_migration.py apps/api/tests/test_research_publication_intent_migration.py -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/pytest-ci-head-pg-root
```

The real PG command used `pytest.main` from a Python launcher that set PATH before invocation. Its actual asset migration assertions verified populated legacy upgrade to current head, exact evidence payload round trip via dump/restore, rejected destructive downgrade, preserved head and encrypted configuration in both databases. Historical image/document migration round trips, embedding-scope corrupt backfill refusal and publication-intent SQLite/PG migration constraints passed without changed assertions.

## Frozen handoff

| File | SHA-256 |
| --- | --- |
| apps/api/tests/test_research_migration.py |52F83664473A9644829C4B50AC718E171197D8C0A6668F43AEB79DD2418CCD05 |
| apps/api/tests/test_asset_migration.py |B5F85E71FBF92AEE4144D7B48CEBD5B65220546C2F703909595D77D30DBFC6E6 |

Scoped `git diff --check` is clean. Git's LF/CRLF checkout warnings do not indicate content changes beyond the inspected assertions; approved45 raw hashes remain unchanged. Historical developer101+1 context_busy evidence and unproven cause remain untouched.

Original-reviewer targeted acceptance and controller commit/push/PR remain next delivery gates. No Git write was performed in this correction. API/Worker/UI integrations remain #44/#45/#46. No core reformat, schema modification, private-memory read, canonical/global write or expanded product acceptance is claimed.

All worker/root test sessions completed. Own PostgreSQL stopped normally; server log confirmed shutdown at2026-09-29 01:35:45 CST. Durable write-back is this newly authorized report only.
