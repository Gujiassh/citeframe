# #42 admission implementation — independent Critical review

Date: 2026-09-28.
Reviewer: original replacement #42 Critical reviewer.
Reviewed base HEAD: 492624c1f36e17f94f7e5010bf9e374edc40ec2c.

**Verdict: ACCEPT the exact four-file admission implementation and narrow CI collection delta identified below. No open implementation finding. AI001, discovered during review, is closed by the subsequently supplied workflow correction. Hosted execution and downstream activation remain separate gates.**

## Goal and authority

Verify that the approved finite lexical predicate rejects fresh manual content/conditions before any memory write, without changing source text or authorization/CAS/idempotency behavior. No broader core, API/UI, provider, shared-private or full #41 acceptance is in scope.

Historical policy approval/R001 closure remains in specs/v5/memory-management/reviews/issue42-admission.md. This implementation report uses the latest requested root reviews path. Both approved policy artifacts remain byte-identical:

| Policy artifact | SHA-256 |
|---|---|
| specs/v5/memory-management/lanes/issue42-admission.md | 6fd16d80c32e7c4205d1d97c408347232070c2ccb218a3a91ab044400597f60c |
| specs/v5/memory-management/evidence/issue42-admission-rules.md | 35b19edf1889cb4ce37cad912154e50085f860e3141e87c348676cb1e2abf8fc |

## Exact accepted candidate

All implementation hashes matched the developer handoff and were rechecked immediately before this report. The workflow hash reflects the narrow correction received during review.

| File | SHA-256 |
|---|---|
| packages/memory-service/src/citeframe_memory/admission.py | 95956d8d28bc00ec59964ff6f6512d92f0db2668a930ed56ebc291bb6259ff81 |
| packages/memory-service/src/citeframe_memory/commands.py | 119d45a326e6f247847f927187b19baad11e4fc0b1bf32dce8d40c7f6e59a0d9 |
| packages/memory-service/tests/test_admission.py | 2a8530c4dcd816ff778ae4a2c5d5c5a823f282cc7c6490bb32bc6667b50e5563 |
| packages/memory-service/tests/test_admission_postgres.py | 1d65b7fedd3b889f2b2cdd22a2dacc8a358f86a1e001e073bc25097766a65be8 |
| .github/workflows/ci.yml | 363f81520750d14e74091d97cf63dc37194e9281a69dcbee168f171c2ce8a2fd |

## Actual implementation assessment

| Invariant | Result and direct evidence |
|---|---|
| Approved finite matching | **Pass.** R1–R5 inspected against the pinned inventory: six same-type PEM markers/non-whitespace body; explicit header/assignment grammars; exhaustive labels/schemes; exact provider shapes/full-token boundaries. ASCII-insensitive groups are scoped to labels/schemes/headers; Unicode whitespace elsewhere retains the approved behavior. Optional OpenAI-prefix overlap is preserved. |
| Honest lexical limits | **Pass.** No negation/example/placeholder exemption; supported values remain rejected in surrounding discussion. Unsupported/truncated/obfuscated and nearest-negative cases are retained. No classifier/authenticity/PII guarantee follows. |
| Original text and independent fields | **Pass.** No normalization, decoding or concatenation. PostgreSQL tests verify exact source content, Unicode/combining marks, whitespace, literal backslashes, conditions, attribution and hashes. |
| Pre-write integration | **Pass.** One import and the guarded two-line call occur on the fresh-operation branch after existing authorization/idempotency/ownership/CAS/terminal checks and before instruction construction. AST comparison after removing precisely that addition equals HEAD. |
| Content-free errors/logging | **Pass for neutral core.** Only MemoryError("sensitive_content_unsupported"), with exact type/args/str/repr and no cause/context. No logging/network code. Captured logs, including SQLAlchemy engine diagnostics during rejection, exclude the synthetic value, content digest and canonical request digest. HTTP serialization/telemetry requires separate API evidence. |
| No write on rejection | **Pass, real PG.** Both commands × all three fields: constructor sentinel never reached; before_cursor_execute observes no INSERT/UPDATE/DELETE attempt; every row of all six memory tables remains equal. Reconcile absent, predecessor unchanged, clean edited retry reuses the identities and subsequently replays. |
| Error priority and recovery | **Pass.** Twelve structural/auth/owner/archive/stale/terminal/idempotency cases retain their error before admission. Historical committed replay/reconcile/deactivate/delete do not rescan. Exact correction receipts/successor, new rejected-versus-clean race and original lost-ack/idempotency/CAS races pass. |
| Regex bounds and imports | **Pass within current 4000/256/2000 limits.** No nested unbounded regex repetition found; PEM scanning advances its cursor. Repeated maximum-size near-matches pass the generous catastrophic-backtracking watchdog, with no latency SLA inferred. Neutral import smoke denies both application packages. |
| Schema/native/shared boundary | **Unchanged by this delta.** No schema/migration/DTO/request/provider/API/compaction change. Prior P1a acceptance remains; no architecture re-review. |

## Independent execution

Existing API Python environment, bytecode disabled, cache provider disabled, lane sources in PYTHONPATH. Ran the equivalent of:

    D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_admission_postgres.py packages/memory-service/tests/test_instruction_memory.py -p no:cacheprovider -q -rs --tb=short

Actual invocation used pytest.main with these arguments and an explicit reviewer-owned temporary basetemp. CITEFRAME_MEMORY42_POSTGRES_URL was set inside Python to postgresql+psycopg://reviewer@127.0.0.1:55442/citeframe_memory42_test; TEMP/TMP were confined to the reviewer temporary root.

**Observed: 1669 passed, zero skipped, 19.51 seconds.**
- 1603 finite-policy unit tests: exhaustive positive/nearest-negative expansions, all three fields, boundaries/casing, content-free errors, watchdog and neutral import.
- 22 real-PG admission tests: six no-write cases, twelve priority cases, fidelity, two historical replay cases and one race.
- 44 existing P1a tests including actual lost-ack recovery, same-key/CAS races and frozen migration/model checks. Not every original test uses a PG fixture; this is not a claim of 44 additional database cases.

Inspected the actual test assertions, SQL observer, six-table snapshots and constructor/admission sentinels before execution. All four code/test files parse and have no trailing ASCII whitespace, including untracked files.

The developer's separate 1682-pass report includes 13 native boundary tests. Those 13 were not repeated here or counted as independent execution.

## AI001 — CI collection gap, found and closed

Initial .github/workflows/ci.yml:73 selected only test_instruction_memory.py. Other workflow selections targeted API/Worker/evaluation/infra paths. Independent collection proved 44 original tests, zero new admission tests. Initial workflow SHA-256: 734eaebb1c579ab7cb2e0f967159c5a6044ab5ca82891add39f373c673b70f40.

A correction arrived during review. The reviewer did not edit it. Whole-file comparison against HEAD proves its sole change adds the two explicit admission paths to the existing dedicated-PostgreSQL step:

    uv run --project apps/api pytest packages/memory-service/tests/test_instruction_memory.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_admission_postgres.py

Independent --collect-only execution using targets parsed from that actual workflow line found exactly 44 original + 1603 admission unit + 22 admission PG = 1669 tests. These are the same three suites independently executed successfully above. A separate CI=true probe with CITEFRAME_MEMORY42_POSTGRES_URL removed failed fixture setup with the expected required-URL error: one error, zero skips. No database connection is attempted by that negative control.

The database creation, dedicated URL, missing-URL guard and other jobs remain unchanged. **AI001 closed for local wiring and collection.** No hosted workflow execution is claimed; controller push/hosted verification remains required.

## Runtime cleanup and bounded handoff

Only the reviewer-owned cluster at C:/Users/baiao/AppData/Local/Temp/citeframe-issue42-review-3174ea83c95f4539945ac26ed8ef7eb0/data was started, following exact-path/PID/port checks, on loopback 55442. Guarded fixtures owned UUID schemas in the dedicated test database. A finally block stopped this cluster; pg_isready returned no response and postmaster.pid was absent. Developer port 56492 and existing application runtime were untouched.

**Ready for controller commit/push and exact-delta integration, subject to hosted CI and downstream activation gates.** API must consume these commands/error without cloning the validator. This review grants no final-image, Management API route/HTTP/log, UI, model/provider, #44 adapter or full #41/#42 acceptance.

Reviewer wrote only this implementation report; no product/test/CI or Git writes and no paid calls. Durable write-back is confined here; approved policy artifacts and their historical review were preserved.
