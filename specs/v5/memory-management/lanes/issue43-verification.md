# Issue43 developer-side verification handoff

Disposition: **I3/I4 corrected 45-file candidate frozen for targeted independent re-review; core acceptance pending**. Native lifecycle, B34 interval/profile/provenance and 69A execution-scope designs are approved. C1/C2/B34/69A corrections were independently exercised on the prior 44-file candidate; I3/I4 corrections identify the current 45-file candidate. Genuine nonzero intervals and fresh-process repeated resume are implemented; temporary interval refusal is no longer the normal runtime path. The historical sections below identify earlier candidates only.

## Executor provenance

This artifact is authored by `/root` inside the **development lane**. Its runs and all subworker runs are developer-side verification. They are not executions by the external controlling task or its appointed independent reviewer. Earlier controller/independent labels for these runs are superseded by the explicit attribution here and in the JSON evidence.

Separately reported external results:

| Actual executor | Result | Source and boundary |
|---|---|---|
| External controlling task | 214 passed in1.16s | `issue43-controller-next.md`, Current actual controller verification; pure algorithms/native packing/provider/count/wire only. No DB/native-lifecycle execution by that controller turn. |
| Appointed original independent reviewer | 214 passed in1.09s | `../reviews/issue43-compaction.md`, Interval rendering targeted review; pure suite plus separately described source-reference counterexample probes. No full DB/core acceptance. |

## Historical developer-side frozen lifecycle candidate results

| Executor | Scope | Actual result |
|---|---|---|
| Development lane `/root` | Native races + repository + schema + constraints | 102 passed in313.78s |
| Development lane `/root` | Actual native lifecycle + guard limits + long branch | 21 passed in108.08s |
| Development lane `/root` | Pure algorithms/native packing/provider/count/wire | 214 passed in1.20s |
| `/root/core_implementation` and its named test delegates | Gate + Research gate + request archive | 29 passed in65.87s |
| `/root/core_implementation` and its named test delegates | Research accounting + successor P1a compatibility | 74 passed in263.80s |

Worker subruns and historical results retain their separate scopes in `issue43-core-evidence.json`. Overlapping run counts are not a unique aggregate. Native service `chat.py` remained unchanged at SHA-256 `DD6D28F8629C1655ACA238B817ACE9BE81C4DFB33C4198027B8FE9F966973C91`.

### Reproducible developer commands

All used `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, no bytecode/cache writes, no live model calls, and the lane-local PostgreSQL17.11 full shipped migration chain.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-ChildItem packages -Directory | ForEach-Object {
    Join-Path $_.FullName 'src'
} | Where-Object { Test-Path $_ }) -join ';'
$env:CITEFRAME_MEMORY43_POSTGRES_URL='postgresql+psycopg://memory43@127.0.0.1:56493/citeframe_memory43_test'

python -m pytest packages/memory-service/tests/test_compaction_native_races.py packages/memory-service/tests/test_compaction_repository.py packages/memory-service/tests/test_compaction_schema.py packages/memory-service/tests/test_compaction_constraints.py -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/pytest-lifecycle-independent-core

python -m pytest packages/memory-service/tests/test_compaction_native_lifecycle.py packages/memory-service/tests/test_compaction_guard_limits.py packages/memory-service/tests/test_compaction_long_branch.py -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/pytest-lifecycle-independent-native

python -m pytest packages/memory-service/tests/test_compaction_algorithms.py packages/memory-service/tests/test_compaction_native_packing.py packages/memory-service/tests/test_native_provider.py packages/memory-service/tests/test_token_counting.py packages/memory-service/tests/test_wire_provider.py -q -p no:cacheprovider --tb=short
```

The literal temporary directory names above contain `independent`; they do not confer independent-review status. `/root` executed these commands in the development lane.

Native oracles exercise unchanged prepare_chat first/later/older-sibling/root-edit/failed-parent paths, initial/continuation exact question inclusion, streaming/unselected-branch exclusion, actual finalize/fail, and thread/message/citation/locator/detail parity. NULL-anchor snapshot, ordered coverage, uses and pointer commit/rollback are covered. This remains developer-side evidence for review.

## Historical evidence

- Development-lane `/root`: pre-pure-rework aggregate364 passed in571.91s, excluding then-failing lifecycle cases. Migration identity was `5CA29D7517C65710133AE5A1EAAD4A6F59BF10A35126656B01C2D631EB043468`; it is not the current migration identity.
- Development-lane `/root`: gate/Research/request archive29 passed in122.60s before lifecycle correction.
- Development-lane `/root`: native SQLite boundary/recovery28 passed in133.03s, one existing Starlette warning; not PostgreSQL accounting proof.
- Historical native-shaped lifecycle failure: `/root/core_implementation`2 failed in10.00s; development-lane `/root`2 failed in6.44s. Both are superseded by the actual-native lifecycle candidate results above.
- Historical pure combined185 passed in0.63s belongs to development-lane `/root`; the focused68 belonged to the implementation worker. Neither is the appointed reviewer's separately recorded185 run.

## Historical pre-B34 freeze and integration

External controller integrated accepted admission893de95 as HEAD `2d6c5b2fd8ab0ec7f2092f2be9e34162e61dfea3`. The above developer runs predate this integration; **no post-integration test execution is claimed**. All35 owned product/test hashes remain unchanged against the frozen manifest. Current migration SHA-256: `21FE3E52A3984628F02B37918B2EBFB3C103297C13038204714CD70F99883469`.

Registration stores the captured leaf ID. NULL/ID changes before first capture reject; A→B→A entirely before first capture is outside the supported guarantee. Revision-based ABA checks begin at capture.

Production complete-source-manifest cap is131072bytes. Measured127-source/128-native-row adoption succeeds; the1023-source/1024-native-row case is explicitly refused for its259650-byte manifest. This refusal preserves originals and is not successful long-thread compaction or full-goal acceptance.

The protected-interval refusal is temporary. Full same-execution repeated-resume rendering, exact per-call provenance, recovery/adoption profile binding and original independent implementation/security/migration review remain required. Actual API/Worker/UI integration remains #44/#45/#46. Semantic omission fixtures do not establish live-model fidelity.

Lane-local PostgreSQL shutdown completed2026-09-28 22:12:53 CST. No new DB/test execution for this documentation correction. No product/test/Git/model/private-memory/global/workbench/canonical writes. Write-back is confined to lane-owned artifacts.

## Historical delegate roster and exact contract revision

- `/root/core_implementation`: single product owner; completed contract-only P43-I1/P43-I2 revision.
- `/root/core_implementation/schema_proof`: completed developer-side native lifecycle/strict fixture proof, as reported by product owner.
- `/root/schema_proof`: completed developer-side read-only static audit; no DB runs or implementation authority.

No active delegate remains. Revised interval contract SHA-256: `B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736`. Product/test hashes remain frozen; no new tests executed for this documentation-only revision.

## Approval and rework chronology

The appointed reviewer approved interval contract `B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736` at design scope and reported F43-C1/C2/C3 against the pre-interval implementation. Earlier developer passes above do not close those semantic findings. The single product owner is implementing C1/C2 and B34 plus the newly authorized standalone `.github/workflows/memory-compaction.yml`; shared ci.yml remains outside its edits.

C3 exact predicate proposal: `issue43-scope-predicate-delta.md`, SHA-256 `69A7115EA197C780345285E0611F5E2488C2AD86C96D788292B9393B6974FC92`. The original reviewer subsequently approved this exact hash in its final C3 design-gate section; the product owner is now implementing the predicates. Current code changes are in progress, so the earlier frozen35-file manifest is a historical pre-rework identity, not the new implementation candidate. New results must identify their developer executor and candidate before handoff.

## Current B34/C1/C2/C3 frozen candidate — 2026-09-29

Current HEAD is `2d6c5b2fd8ab0ec7f2092f2be9e34162e61dfea3`; source start remains `2e9287638fee9567c6474b8356c3b3ba93fec16a`. The authoritative delivery inventory is the 44-entry `files` array in `issue43-core-evidence.json`. Developer-root disk comparison found 44 entries and zero SHA-256 mismatches after the final aggregate; no product/test edits occurred during those runs. The five existing model files remain the only existing product files changed. New CI is `.github/workflows/memory-compaction.yml`; shared `ci.yml` remains `363F81520750D14E74091D97CF63DC37194E9281A69DCBEE168F171C2CE8A2FD`.

Design identities remain byte-for-byte unchanged: interval B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736; exact execution-scope 69A7115EA197C780345285E0611F5E2488C2AD86C96D788292B9393B6974FC92. Both are approved designs; implementation acceptance belongs to the appointed reviewer.

### Current implementation oracles

- C1: registration NOWAIT-prelocks actual old active anchor and designated FK targets. Real native DELETE/SET NULL barriers cover both acquisition orders and NULL anchor; retention may return23503, with no reliance on native40P01 victim selection.
- C2: DB-designated current user is required exactly once and automatically protected in original chronology. Missing/history-only/foreign/duplicate coverage and forged send payloads reject before relevant reservation/archive/send effects.
- C3: deferred owner predicates bind immutable generation-call execution, complete selected ancestry, exact native revision/metadata and same-execution complete tool dependencies. Raw SQL with valid manifests rejects sibling scope and foreign owner dependencies. Historical owner lookup and unchanged pointers survive native lifecycle changes; fresh authority remains required.
- B34: real nonzero/disjoint/containing intervals, two growth adoptions under one execution, exact chunk input and ordered child provenance, final eligibility, full profile binding, committed-history current recount and subprocess reload are implemented. All three actual native serializers/counters are covered. Current questions and interior protected whole groups remain chronological originals.
- Persistence remains one real transaction for snapshot, complete ordered coverage, uses and native pointer CAS. No in-memory checkpoint substitute, shared-private inputs, new native audience mode or native writer transfer.

### Final developer execution records

| Executor | Scope | Result |
|---|---|---|
| `/root/core_implementation` | Dynamic full sorted `test_compaction*.py` inventory,22 matching modules, strict markers, real PostgreSQL17.11 shipped migration chain | **486 passed in1135.14s**, exit0 |
| Development-lane `/root` | Pure algorithms/native packing/provider/count/wire | **214 passed in1.19s** |
| Development-lane `/root` | Registration + main-question + intervals + provenance + scope | **101 passed,1 failed in385.19s** |
| Development-lane `/root` | Same dynamic inventory collection | **486 collected in1.20s**,22 matching files |
| Development-lane `/root` | CI=true with required PG URL absent | Explicit pytest Failed; no skip and no database created |

The root targeted failure was `test_gate_derives_protection_for_current_question_across_dispatch_modes[openai_chat_completions]`: `prepare_main_dispatch -> _materialize -> read_source -> transact` returned `context_busy`. PostgreSQL log at00:10:55.014 and00:10:55.542 recorded two lock timeouts on the bounded native chat-message metadata SELECT. Root and worker were then running disposable-schema suites concurrently on the same cluster. The blocking lock owner was not captured; shared database catalog/DDL contention is a possible explanation, not an established cause. The failed run remains recorded; a separate serial main-question rerun follows. No transaction/statement/lock caps or assertions were relaxed.

Full aggregate command (worker executor), with the environment above:

```powershell
$files = Get-ChildItem packages/memory-service/tests -Filter 'test_compaction*.py' | Sort-Object Name | ForEach-Object FullName
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest @files -q -p no:cacheprovider --strict-markers --tb=short
```

The root targeted command uses those five explicit module paths and `--basetemp=.local-runtime/pytest-final-c123-interval-devroot`. The serial rerun uses `test_compaction_main_question.py` and `--basetemp=.local-runtime/pytest-final-c2-serial-devroot`. These are developer-side runs, not external-controller or appointed-reviewer executions. Overlapping results are not summed into a unique total. GitHub-hosted workflow execution has not occurred.

### Current supported limits and remaining gates

Registration is not a revision capture: A→B→A before first capture is unsupported; captured ABA is guarded. Native thread cap1024 rows and metadata128KiB, original-unit manifest128KiB, source/request aggregate1MiB, tool archive16MiB and task archive64MiB remain explicit. Statement2s/lock250ms/transaction5s caps are unchanged. The measured127-source adoption succeeds;1023-source manifest259650bytes is explicitly refused, not a successful long-history compaction. The latest child isolated127-source adoption was1732.172ms; it is a bounded fixture measurement, not general throughput acceptance.

Crash tests cover injected boundaries, fresh sessions/process reconstruction and lost acknowledgments; no OS-crash or production-failover claim. Deterministic omission fixtures do not establish live-model semantic quality. API/Worker/UI dispatch integration remains #44/#45/#46. Final frozen implementation still needs original independent security/migration/runtime review.

Current product owner is `/root/core_implementation`; its child `/root/core_implementation/schema_proof` completed dedicated tests/CI and developer verification. Earlier `/root/schema_proof` was a completed developer-side read-only audit. `/root` only owns developer verification and this artifact. No commit/push, private MEMORY read or canonical/historical/global/workbench write. Durable write-back is confined to lane artifacts; controller-owned delivery.md and reviewer artifacts remain outside this lane's edits.

Serial follow-up: development-lane `/root` ran the entire main-question module alone against the same frozen candidate and PostgreSQL cluster: **17 passed in35.36s, exit0**. This includes the exact earlier failing OpenAI Chat Completions case. It establishes a successful serial rerun; the prior lock blocker remains unidentified and the original failed run is retained above. No product/test/cap edits preceded the rerun.

Closeout: all required development delegates and test sessions completed. The lane-local PostgreSQL17.11 cluster was stopped with fast shutdown; its log confirmed `database system is shut down` at2026-09-29 00:33:07 CST. Product/test/CI44-file hashes remained unchanged. No external-review acceptance is asserted.

## I3/I4 bounded corrective slice

The appointed original reviewer independently passed486 distinct cases across four disjoint commands on the frozen44-file/080BA0EF candidate and closed C1/C2/C3 reproductions for that identity. Its latest full review separately reproduced I3 (invalid protected/overlap chain committed before reload refusal) and I4 (invalidated/erased summary revived through delayed save). Those findings block core acceptance despite the green regression evidence.

External controller evidence is available at `../evidence/issue43/controller-critical-verification.md`:102 passed in207.85s on its own new PostgreSQL17.11 cluster, frozen44-file identity unchanged. This evidence does not close I3/I4 or establish the cause of the developer101+1 failure.

The same product owner is implementing the authorized correction without schema/native/API expansion: authenticate and compose historical intervals before adoption DML in the guarded atomic transaction; permit summary first-save only from absent and exact idempotence only from valid under the existing call lock. Genuine archived/final-eligible reproducers run red before code changes, followed by no-DML, rollback, protected/overlap, lifecycle and late-concurrency positives/negatives. The prior44-file identity remains historical evidence; a separately frozen corrected manifest will identify the next candidate. Approved B34/lifecycle/69A contract bytes and production caps remain unchanged.

### Corrected candidate freeze and scope

Current manifest contains45 paths; its historicalFrozenManifests retains the prior44 entries. Developer-root comparison confirms exactly three changed existing candidate paths: compaction/repository.py, rendering.py and journal.py, plus new tests/test_compaction_authority.py. The successor migration remains080BA0EF0CA227B7E367ED2BB97164A06479ED9CC77398DF611EC1A8729DFDEA. No approved delta, native/schema/API/ABI file changes belong to this corrective slice.

Developer product owner recorded RED5failed8.72s on unchanged old44 product, then GREEN5passed8.49s. Proposed-chain count/combined-byte boundaries additionally ran RED2failed5.37s before candidate-cap enforcement. Final authority22passed38.70s covers no-DML rejection, exact idempotence, invalidated/erased delayed save, both lock orders, malformed prior provenance, disjoint/containing transitions and five exact second-adoption rollback stages. Affected nine-module regression passed176cases314.88s. All are developer-side runs; the old independent486 and external-controller102 results retain their original identity and executor.

Root static review checked that historical chain load/candidate-limit/transition validation executes before snapshot construction/flush in the same guarded adoption transaction; replay uses the same protected/frontier/overlap validator. Result-state rejection executes under the existing MemoryCall lock before validate/write. Forward lock tests refuse busy then refuse committed invalidation/erasure. Reverse lock test proves the historical generation call remains locked through rollback. Five fault stages compare full persisted JSON rows and successfully reload last-good history.

Developer-root current pure/native-provider suite:214passed1.15s. Dedicated workflow glob now collects508 tests from23matching files in1.21s. This is collection evidence, not a claimed full508-case execution. Disk comparison found45manifest entries and zero mismatches; old44 comparison identified only the three product changes listed above. No SQL lifecycle monotonicity guarantee is added; the corrected public save path enforces terminal result authority.

Root serial real-PG verification of the frozen45 candidate completed: **66 passed in120.61s, exit0**, running `test_compaction_authority.py`, `test_compaction_intervals.py`, `test_compaction_provenance.py`, `test_compaction_repository.py` together with `--strict-markers -q -p no:cacheprovider --tb=short --basetemp=.local-runtime/pytest-i3i4-devroot`. Existing API Python, lane-local package imports and own56493 PostgreSQL17.11 were used. No concurrent developer DB suite ran. This is developer-root evidence; original-reviewer targeted acceptance remains pending.

I3/I4 closeout: original product owner completed; no new delegate was spawned for this correction. All developer test sessions are complete. Own PostgreSQL fast shutdown completed2026-09-29 01:10:45 CST (`database system is shut down`). Durable write-back remains lane-local; no private/global/canonical write, Git change or model call. Current45-file manifest SHA-256: A9C9385497F7092DC958ABFA218C3AEA13D089C97EBF621E92D46A24334375FB. Targeted original independent re-review remains the next acceptance gate.
