# Issue42 index storage: IS01 repair

The next serial delivery resumes the existing, uncommitted index storage candidate from the paused Issue42 worktree. The original worktree and its uncommitted files are preserved. This isolated branch starts at PR56 head `7f41584aaa87554c5158d93129e25e8aecf7eca7`; its parent PRs remain unmerged.

## Problem and resulting behavior

An established REPEATABLE READ snapshot could activate a manifest after another transaction committed entry deletion or a transition to pending. Workspace/manifest row locks alone do not refresh that snapshot. Both original candidate counterexamples were reproduced against real PostgreSQL17.11: the expected rejection did not occur.

All manifest and entry row writes now require READ COMMITTED inside their database triggers. REPEATABLE READ and SERIALIZABLE fail before snapshot-dependent validation with SQLSTATE `0A000` and `index_write_requires_read_committed`. Manifest DELETE also participates in the workspace lock and isolation admission. READ COMMITTED activation continues to reject missing/pending entries with `23514`; active immutability, canonical profiles, source metadata constraints and existing lock-conflict behavior remain covered.

This bounded contract explicitly supports READ COMMITTED index writers. Stronger isolation is rejected rather than represented as safe. Read-only transactions may still use their own isolation level.

## Controller execution

- Original model plus new delete/pending REPEATABLE READ tests: **2 failed**, both `DID NOT RAISE DBAPIError`, 154 deselected, 2.85s. This is recorded negative-control evidence.
- Repaired complete storage suite: **156 passed**, zero skips, 8.64s.
- Exact dedicated workflow Python body executed locally: **156 passed**, zero skips/xfails, 8.24s; checkout-local import checks passed.
- Added 18 cases: six two-connection stale-snapshot cases across READ COMMITTED / REPEATABLE READ / SERIALIZABLE, and twelve direct INSERT/UPDATE/DELETE admission cases across both unsupported levels and both tables. Fresh connections inspect committed state after rollback.
- Test database: a new controller-owned PostgreSQL17.11 cluster under the current task directory, loopback port56493, exact database `citeframe_history42_index_test`. No original lane database was resumed or modified.
- Dependencies come from the existing API Python environment; pytest's project pythonpath loads the candidate checkout. The dedicated hosted workflow separately verifies checkout-local model imports before and after all156 cases, freezes dependency installation and rejects skips/xfails/partial execution.

Command from the isolated checkout:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_HISTORY42_INDEX_POSTGRES_URL='postgresql+psycopg://index42_test@127.0.0.1:56493/citeframe_history42_index_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_history_index_postgres.py -q -p no:cacheprovider --tb=short
```

## Delivery and acceptance limits

Historical review/evidence and the approved IC01/storage/activation contracts are retained without rewriting their historical verdicts. Fresh independent product/CI review and hosted results must be recorded separately. The new workflow adds a storage gate; it does not weaken existing checks.

Original reviewer `agt_a74ed9c2` was queried through the official DevSpace CLI and a bounded continuation was requested. Execution failed with `PROVIDER_UNAVAILABLE: Codex executable was not found`; no successful original-reviewer approval is claimed. A fresh independent review is required and identified separately.

Only explicit model import creates these two tables. There is no production export, successor migration, source authority issuer, native lifecycle hook, index activation/search endpoint, embedding evaluation or UI change. ORM schema evidence is distinct from real migration and native runtime acceptance. No paid calls or deployment.

This PR depends on PR56, which depends on PR54, PR49 and PR48. PR56 still has two API differential failures at its current head; PR54 contains their reviewed repair. External service CI remains blocked by fixed MinIO artifact access. Do not merge the stack into a feature branch and claim main delivery; each prerequisite requires its own actual merge and dependent revalidation. The user authorized one PR only, so other PRs remain untouched.
