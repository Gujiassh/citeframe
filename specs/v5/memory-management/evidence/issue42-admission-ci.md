# #42 admission CI collection delta

Date: 2026-09-28. Ready for the original Critical reviewer's CI-delta check.
Base HEAD: 492624c1f36e17f94f7e5010bf9e374edc40ec2c.
No Git writes. Admission product/tests and reviewer artifact were not edited.

## Exact workflow change

Only the existing pytest command in .github/workflows/ci.yml, step Run instruction-memory PostgreSQL regressions, changes:

    uv run --project apps/api pytest packages/memory-service/tests/test_instruction_memory.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_admission_postgres.py

The original explicit instruction suite is retained. Both admission files are explicit arguments; there is no directory-wide collection. Database creation, PostgreSQL service, environment, frozen dependency setup and all other jobs/steps/gates are unchanged. There is no added condition, marker exclusion, skip, continue-on-error, shell bypass or success override.

Workflow SHA-256: 363f81520750d14e74091d97cf63dc37194e9281a69dcbee168f171c2ce8a2fd

## Independent local verification

A stdlib verifier extracted the actual two-line run block, parsed its command with shlex, and compared its exact pytest path list with the three expected files. It also asserted the complete workflow text equals git show HEAD:.github/workflows/ci.yml with only the single expected command replacement. All assertions passed.

Using D:/Code/citeframe/apps/api/.venv/Scripts/python.exe, PYTHONDONTWRITEBYTECODE=1 and CI=true, the extracted paths were passed to:

    python -m pytest <the three exact extracted paths> --collect-only -q

Exit 0; collected node IDs were independently counted by file:

| File | Collected |
|---|---:|
| test_instruction_memory.py | 44 |
| test_admission.py | 1603 |
| test_admission_postgres.py | 22 |
| Total | 1669 |

The verifier then selected an actual collected admission PG rejection node and ran it with CI=true and CITEFRAME_MEMORY42_POSTGRES_URL absent. It asserted exit 1, exactly one setup error containing the existing CI-required-database message, and no skipped result. This intentionally failing probe passed its verifier: absent database configuration cannot silently skip the new PostgreSQL tests.

The earlier real PostgreSQL run in issue42-admission-runtime.md passed all these tests with zero skips, plus 13 native boundary tests. This CI-only delta did not start a database or rerun the full PG suite. Local verification used the installed API interpreter; hosted uv/GitHub Actions execution remains pending controller push. No YAML parser claim is made: the new command is within the unchanged literal run block.

All four implementation candidate hashes were verified unchanged after this delta:

| File | SHA-256 |
|---|---|
| packages/memory-service/src/citeframe_memory/admission.py | 95956d8d28bc00ec59964ff6f6512d92f0db2668a930ed56ebc291bb6259ff81 |
| packages/memory-service/src/citeframe_memory/commands.py | 119d45a326e6f247847f927187b19baad11e4fc0b1bf32dce8d40c7f6e59a0d9 |
| packages/memory-service/tests/test_admission.py | 2a8530c4dcd816ff778ae4a2c5d5c5a823f282cc7c6490bb32bc6667b50e5563 |
| packages/memory-service/tests/test_admission_postgres.py | 1d65b7fedd3b889f2b2cdd22a2dacc8a358f86a1e001e073bc25097766a65be8 |

No provider/compaction suite was added to this step. The original reviewer retains implementation acceptance and this CI-delta check; controller owns commit/push and downstream integration.
