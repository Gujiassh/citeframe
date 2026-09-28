# Controller settlement verification

Controller independently ran the frozen two-file settlement candidate from e7b3e86 against its own freshly initialized PostgreSQL17.11 cluster (loopback56945, citeframe_issue45_settlement_test), separate from developer/reviewer clusters. Product SHA256 F8E02EB6C9F93DED10BF59C9B136168130591FC49B4DED0041E6115530230A51; test SHA256 787ED87A226F26D928C2F7505A444235F4EB658E9C252719956FFAB5F9DC27E8. Both unchanged before/after.

Command: existing API Python -B -m pytest packages/research-persistence/tests/test_memory_tool_settlement.py --strict-markers -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/controller45-settlement/pytest, lane-local packages/*/src imports, PYTHONDONTWRITEBYTECODE=1, plugin autoload disabled, explicit CITEFRAME_ISSUE45_POSTGRES_URL.

56 passed in23.59s, exit0;55 real-PG cases plus1 frozen-source/AST case, zero skips. The fixture uses actual ORM table dependency closure and constraints, not Alembic. This proves the shipped old/new settlement/lock/outer-transaction oracles at this identity, not migration or full Research memory integration. Controller inspected actual helper/wrapper diff and verbatim baseline oracle; source locks/validation retained and only the mutation helper moved within the unchanged public rollback boundary.

Post-run remaining settlement45 fixture schemas:0. Controller PostgreSQL stopped normally. No paid model, actual browser, #46 denied operation or native activation was attempted. Original independent review and dedicated hosted collection remain separate gates. Raw output: controller45-settlement-tests.txt. Local database files retained ignored; no recursive cleanup.
