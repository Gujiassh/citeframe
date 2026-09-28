# #42 admission implementation evidence

Date: 2026-09-28. Developer candidate ready for original Critical implementation review.
Branch: work/issue42-memory-persistence.
Starting HEAD: 492624c1f36e17f94f7e5010bf9e374edc40ec2c.
No commit, staging, push or merge performed.

## Authority and bounded implementation

Original reviewer closed R001 and approved the exact policy and pre-write placement in reviews/issue42-admission.md section 6. Approved files remain unchanged:

- lanes/issue42-admission.md: 6fd16d80c32e7c4205d1d97c408347232070c2ccb218a3a91ab044400597f60c
- evidence/issue42-admission-rules.md: 35b19edf1889cb4ce37cad912154e50085f860e3141e87c348676cb1e2abf8fc

The historical proposal status in those pinned artifacts is superseded by the independent section 6 approval. This evidence records implementation; it does not modify that policy.

One new admission module uses stdlib matching plus existing neutral contract types. It scans content, conditions.subject and conditions.applicability independently, preserves original strings, and raises only MemoryError("sensitive_content_unsupported"). It performs no logging, normalization, decoding, classification or network activity. Its supported syntax and false-positive limits are exactly the finite approved inventory.

commands.py adds one import and one shared two-line call immediately after fresh target/CAS/terminal checks and before MemoryInstruction construction. Structural validation, authorization, operation lookup/conflict, committed replay, reconcile and delete/deactivate retain their paths. No schema, migration, shared DTO, provider, compaction, API, dependency or lock file changed.

## Executed final verification

Own disposable PostgreSQL 17.11 only: port 56492, database citeframe_memory42_test. The existing guarded fixture creates/drops a UUID schema for each test and applies the real instruction-memory migration. No reviewer cluster or external database was used.

PowerShell from D:/Code/citeframe-lanes/issue42-persistence:

    $env:PYTHONDONTWRITEBYTECODE='1'
    $env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://memory42_test@127.0.0.1:56492/citeframe_memory42_test'
    & D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_admission_postgres.py packages/memory-service/tests/test_instruction_memory.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py -q --disable-warnings --tb=short

Final result: **1682 passed, zero skipped, 1 warning, 19.59 seconds**.

| Suite | Passed |
|---|---:|
| New finite-policy unit fixtures | 1603 |
| New real PostgreSQL admission oracles | 22 |
| Existing P1a suite, including migration/model oracle and races | 44 |
| Existing native persistence boundaries | 13 |

### Direct acceptance evidence

- Every approved type/alias/header/scheme/provider shape has positive and nearest-negative fixtures; each base positive and negative is placed independently in all three fields. Additional fixtures check ASCII casing, Unicode non-equivalence, quotes/newlines/whitespace, terminal delimiters, provider upper bounds and the approved optional-prefix overlap.
- Public-key/certificate, English/Chinese credential discussion, token budgets/counts and ordinary preferences remain admitted. Concrete supported patterns remain rejected inside negation/examples. No universal secret/PII/obfuscation-detection claim is made.
- Exact MemoryError type, args, str and repr are asserted, with no chained exception. Captured logs exclude the synthetic matched value, content digest and canonical request digest.
- Six real-PG remember/correct rejection cases (both commands × all three fields) compare every row of all six memory tables before/after. An engine event listener observes no INSERT/UPDATE/DELETE attempts. A constructor sentinel separately proves no MemoryInstruction is constructed. Reconcile returns no operation; a clean edit reuses the same request/key successfully, then replays/reconciles exactly.
- Twelve PG precedence cases prove admission is not called before invalid UUID/key/version, shared audience/purpose, non-owner, missing membership, archive, stale version, deleted/superseded target or changed-body idempotency errors. Six-table snapshots and no-DML observations also hold.
- Source/revision content, conditions, actor attribution and hashes retain exact whitespace, Unicode, literal backslash and timestamps on remember/correct. Correction replay and reconciliation preserve the receipt and single successor.
- Historical remember and correct replay are each seeded with pre-admission content under a test-only bypass. With a fail-on-call admission sentinel restored, exact replay/reconcile/deactivate/delete still work without retroactive scanning. No production bypass was added.
- A rejected/clean correction race permits the existing stale-CAS result if the clean correction wins; only the clean successor is persisted, rejected operation reconciliation is absent and the marker is absent from all six tables.
- Existing same-key races, correction/deactivation CAS race and actual commit-ack-loss reconciliation pass unchanged in the 44-test P1a suite.
- Neutral import works while API/Worker imports are denied. Repeated maximum-size adversarial inputs meet a generous 10-second catastrophic-backtracking watchdog; this is not a latency SLA.
- Python AST parsing and explicit trailing-whitespace checks pass for all four code/test files, including untracked files. git diff --check passes. Both approved policy hashes were reverified.

The first PG run exposed an incorrect new test expectation for non-owner access: the existing error is memory_unavailable. The assertion was corrected to preserve that exact existing behavior; production authorization was unchanged.

## Candidate identities

| File | SHA-256 |
|---|---|
| packages/memory-service/src/citeframe_memory/admission.py | 95956d8d28bc00ec59964ff6f6512d92f0db2668a930ed56ebc291bb6259ff81 |
| packages/memory-service/src/citeframe_memory/commands.py | 119d45a326e6f247847f927187b19baad11e4fc0b1bf32dce8d40c7f6e59a0d9 |
| packages/memory-service/tests/test_admission.py | 2a8530c4dcd816ff778ae4a2c5d5c5a823f282cc7c6490bb32bc6667b50e5563 |
| packages/memory-service/tests/test_admission_postgres.py | 1d65b7fedd3b889f2b2cdd22a2dacc8a358f86a1e001e073bc25097766a65be8 |

## Handoff and remaining gate

Original Critical reviewer must verify this actual implementation and real-PG evidence. Controller owns commit/push and exact-delta integration into #43 and Management API lane 32bb676. API must use these commands and the neutral error without a duplicate predicate. Mutation activation and merge remain gated on independent implementation acceptance, exact integration and CI. No API HTTP/log/UI acceptance is claimed by these core tests. Existing A1 choice2 private-management-only scope is unchanged.

Durable write-back is this owned evidence and the appended lane report. No private/global memory or canonical workbench state was accessed or changed.
