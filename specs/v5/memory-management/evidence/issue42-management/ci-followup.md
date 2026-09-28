# Narrow CI environment follow-up

The regular `uv run --project apps/api pytest apps/api/tests` step now has step-local `CITEFRAME_MEMORY42_POSTGRES_URL` set to the same already-created disposable `citeframe_memory42_test` database used by the dedicated PostgreSQL step. Exact workflow comparison against HEAD confirms only the previously authorized dedicated-test addition and this two-line environment addition. All other services, environment settings, commands and gates are preserved.

The six review-frozen files match the prior candidate byte-for-byte; see `ci-frozen-files.json`. No product, test, dependency, lane-contract or core file was edited in this follow-up. The earlier lane checkpoint's CI environment blocker is superseded by this evidence.

## Executed verification

Local full API run used Python from the existing API environment, `CI=true`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`, and:

- `CITEFRAME_MEMORY42_POSTGRES_URL=postgresql+psycopg://memory_management_test@127.0.0.1:56542/citeframe_memory42_test`
- `AI_PDF_DATABASE_URL` pointed to that same local disposable database, with a synthetic local test token.
- `TEMP` and `TMP` pointed to a newly created lane-local directory. A prior attempt hit the inaccessible default Windows pytest temporary directory; that attempt was superseded by the complete rerun.

Command: `python -B -m pytest apps/api/tests -p no:cacheprovider -q --tb=short`.

**Result: 1011 passed, 29 failed, 9 skipped, one warning, 986.97 seconds.** Full output: `pytest-full-api.txt`. No selectors, deselection, skip flags, test modifications, gate weakening or package installation were used. This is a completed local full-suite run, not a green-suite or hosted-CI claim.

Failure distribution:

| Tests | Count | Observed failure |
|---|---:|---|
| `test_a2a_differential.py` | 3 | Windows subprocess/access denial |
| `test_multimodal_execution.py` | 22 | M402 source/artifact hash drift assertions |
| `test_r100_research_eval.py` | 2 | Reference failure taxonomy hash mismatch |
| `test_research_policy_sse.py` | 2 | Web `tsx` package unavailable |

These failures are outside the management suite. No baseline repair or line-ending rewrite was attempted. The nine skips are from existing full-suite behavior; no skip logic was added. Dedicated management verification with `CI=true` is separately recorded in `pytest-ci-management.txt`.

Negative controls execute the actual management fixture shared by both collection paths:

- Missing URL with `CI=true`: explicit fixture failure, zero skips (`ci-missing-url.txt`).
- Configured unreachable disposable test database: connection timeout error, zero skips (`ci-unreachable-db.txt`).

Both commands collect the same unchanged management suite and fixture. The explicit dedicated command collection remains1715; normal API collection contains1049 test cases. Workflow wiring does not change fixture fail-closed behavior.

## Scope and remaining gates

Workflow environment blocker resolved. Frozen mounted candidate remains pending original independent Critical review; hosted CI and merge/release gates remain unclaimed. No commits or pushes. Durable write-back is limited to this evidence directory; no private profile memory or shared workbench writes.

Dedicated CI-mode management result: **46 passed, zero skipped**,13.47 seconds. Final `git diff --check` passed. Lane-owned disposable PostgreSQL stopped cleanly; port56542 has no response and postmaster.pid is absent.
