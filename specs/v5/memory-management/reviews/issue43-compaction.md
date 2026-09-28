# Issue43 compaction — independent Critical review

Date: 2026-09-28 (Asia/Shanghai)
Disposition: **APPROVE — selected Option A exact schema/design delta for implementation and real-PG proof**
Phase: exact bounded contract review, before implementation.

Latest separate implementation audit: **pure five-file algorithm slice — REWORK REQUIRED**, see “Pure policy/units/packing implementation audit” below. Selected Option A schema/design approval remains unchanged.

## Selected Option A — final targeted design decision

**APPROVE the selected Option A exact schema/design delta for implementation and full shipped-schema PostgreSQL proof. F43-1 and F43-2 are closed at design scope. No residual blocking finding is identified in this selected delta.** This is not implementation, migration, integrated runtime, semantic-quality or UI acceptance.

Exact reviewed identity:

- Contract `lanes/issue43-compaction.md`, operative §§1–9, final rechecked candidate: SHA-256 **`ED10B657B3DE9862D3601A8917B798AADE08B21E18CB48D66448BC5D2EEEE1E9`**. The probe-phase candidate was `712E0EADAD93B745F69A64A702AF0A206964332FB7CB1971FA5CDC90F0FA108A`. Before delivery the developer synchronized §3 source native_version with §4 compactionRevision, updated pure-algorithm progress wording and appended its deterministic evidence. Reversing exactly those changes reproduced the prior SHA-256 byte-for-byte. These changes were inspected; the selected-A approval applies to the final hash. The appended algorithm test claim is not independently accepted by this design review.
- Controlling selection/grant `lanes/issue43-controller-ownership.md`: SHA-256 **`44CB34BA3E8D10A4CAD8A2784670EC3974A9B0FEC1723E36A02BBF0D9D42F7C1`**.
- Source baseline remains `cae6379e1f3743b944b745797cf6f157b1915654`; integrated provider prerequisite is not an Issue43 acceptance result.
- The contract still contains historical “choice pending”, “pending transfer”, and Option B text. The controller's explicit selection and latest instruction govern: **only A is approved; B/global relation locking is not an authorized fallback.** The five narrowly scoped existing mapping/export files are granted; no router/service/shared-ABI ownership is added. Editorial synchronization of the stale selection labels does not require a new architecture review.

### F43-1 — closed, precise native accounting allowance

§5 now explicitly acknowledges the actual native ORM loads: `_provider_call_chain` reads the exact native aggregate chain, and `reconcile_provider_call` loads its exact planning/execution pricing row, including semantic attributes physically selected by the mappings. It makes no zero-body-read claim. The server-held receipt permits only metadata use, forbids inspection/copy/output/logging/generation/new persistence of semantic fields, prohibits source/object/history/private-memory access, and uses a fresh accounting Session whose ORM objects never escape.

The unchanged native functions substantiate the arithmetic protocol: Run → Step → Attempt → ProviderCall → Ledger is shared with reclaim; `mark_provider_call_sent` already counts the provider send; native `reconcile_provider_call` accepts only `sent` and settles the reserved usage once. A reclaim winner's cancelled/terminal/unknown state is mirrored into the sidecar without a second native reconcile, refund or late unknown refinement. Native and sidecar writes remain one transaction. The allowance repairs the earlier exact-contract mismatch without duplicating the ledger or granting model/content authority. Marker/query/output tests under actual implementation remain mandatory.

### F43-2 — closed for selected A; lock proof and boundaries

1. **No new cross-row trigger edge.** BEFORE INSERT/UPDATE assigns only `NEW.compaction_revision`, using OLD/NEW native-field comparisons and one noncycling sequence. It never locks another native root, mutates an execution, or updates another table. Consequently the rejected message → thread → execution trigger edge is absent, including native SET NULL updates. Native DELETE itself needs no stamp: disappearance is detected by the complete set; same-ID insertion always receives a fresh stamp.
2. **Insertion/reparent-in fence.** Inspected native migration `f4d9c0e7a2b1` creates `chat_messages.thread_id → chat_threads.id` without deferral, matching the current ORM. Its key-share FK check conflicts with the selected **FOR UPDATE**, not a weaker NO KEY UPDATE guard. A completed writer's committed row is visible to the fresh READ COMMITTED manifest query; an uncommitted writer already holding parent key-share makes root NOWAIT fail; a later FK check waits until the guarded transaction ends. The latter write serializes after adoption and must be observed by the next independently guarded dispatch.
3. **Complete current membership.** After the root fence, read and NOWAIT-lock the entire bounded thread's message ID/revision set, including siblings as metadata only. Lock or recheck anomalies under READ COMMITTED cause full rollback or manifest mismatch. No SKIP LOCKED, prefix-only fence, pagination that releases guards, or accepted truncated manifest. All current message rows are required to prevent deletion/reparent-out/status/body changes while adopting. Only eligible current-branch bodies may feed summaries.
4. **ABA/recreation.** Every changed native mapped field allocates a new stamp. Caller-supplied stamps are ignored, unchanged native values retain OLD, and INSERT always allocates. Thread leaf/content A→B→A and same-ID deletion/recreation cannot match the captured token. The sequence is not owned by a native identity column and is not reset by ordinary TRUNCATE RESTART IDENTITY; unsupported administrative sequence reset/trigger disablement is excluded explicitly. The tokens do not claim commit ordering or a full event history. A transient insert/delete leaving no surviving context change between captures is outside the claimed event history.
5. **Explicit and implicit lock closure.** Selected A retains Workspace → Membership → Thread → execution root/current → complete message/source set → checkpoint/calls, with NOWAIT acquisition and whole-transaction rollback before at most one retry. Before staged snapshot/coverage/use/call/pointer writes, existing FK targets must already be guarded; consistency checks take no new root locks in reverse order. The retained last-good snapshot may precede current owner/native state; exact new adoption CAS is independently checked. These restrictions are implementable; their new SQL/FKs/triggers do not yet exist and have **not** passed implementation review. New FK targets, unique conflicts, deferred checks and actual callback/autoflush behavior require the shipped-schema tests below.

Actual native `parent_message_id` and `active_message_id` retain ON DELETE SET NULL (`c2e4f8a1b7d9`; current models). Native message child CASCADE cleanup is preserved. Row-local stamps add no thread/execution lock to those actions. Existing native deadlocks or legitimate retention failures are not claimed repaired or converted into successful writes.

### Actual bounded PostgreSQL evidence executed by this reviewer

**Scope:** a newly initialized, isolated disposable PostgreSQL **17.11** cluster, synthetic native-FK subset (`chat_threads`, `chat_messages`, one CASCADE child), probe-only row-local stamp function/sequence, and separate psycopg connections. No product migration/schema/test file was authored. This is a mechanism probe, not a substitute for the complete real migration and native service fixture suite.

The synthetic subset reproduced the native thread FK and both SET NULL links. `pg_constraint` returned `(condeferrable=false, condeferred=false, convalidated=true)` for message thread/parent FKs. The probe compared metadata tuples only in full-thread scans. The stamp function was restricted to OLD/NEW comparison excluding `compaction_revision`, nextval assignment and RETURN NEW.

| Probe | Actual result |
| --- | --- |
| Raw INSERT holds thread FK lock; other Session requests thread FOR UPDATE NOWAIT | **PASS**, SQLSTATE `55P03` |
| Reparent-in holds new thread FK lock; root NOWAIT | **PASS**, `55P03` |
| Root acquired first; raw INSERT runs on another connection | **PASS**, writer observed with `wait_event_type=Lock` and root backend in `pg_blocking_pids`; old manifest stable before release, persistent new row visible after commit |
| Reparent-out in progress; compactor root then all message rows NOWAIT | **PASS**, `55P03`; full transaction rolled back |
| Native message-first row holder; compactor root then complete message metadata NOWAIT | **PASS**, `55P03`; root released by rollback |
| Two native writers, parent DELETE waiting on locked child; child UPDATE commits | **PASS**, both committed with row-local stamps; parent and active-leaf SET NULL received new stamps; CASCADE child removed |
| Message content ABA; leaf ABA; same message/thread ID recreation; supplied revision spoof | **PASS**, changed/recreated revisions distinct; metadata-only spoof did not replace OLD |
| Sequence + TRUNCATE RESTART IDENTITY | **PASS**, next inserted stamp did not recycle |

Reproduction shape: initialize a fresh cluster with `initdb.exe -D <new-temp>/data -U reviewer --auth=trust --encoding=UTF8 --no-locale`; run loopback-only `postgres.exe -D <data> -h 127.0.0.1 -p <unused-port>` with no visible window; execute the synthetic schema and two-connection SQL barriers using `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -`. Decisive guard SQL was `SELECT id FROM chat_threads WHERE id='t' FOR UPDATE NOWAIT` followed by `SELECT id,compaction_revision FROM chat_messages WHERE thread_id='t' ORDER BY id FOR UPDATE NOWAIT`. Writer statements were raw INSERT, thread_id UPDATE, parent DELETE and child content UPDATE; each transaction explicitly committed/rolled back. Probe connection timeouts: lock 2000 ms, statement 5000 ms; these are **probe settings**, not approved production defaults.

Execution log: first `pg_ctl start` failed before server launch with restricted-token error 87. Direct hidden `postgres.exe` startup on the same **new test cluster** succeeded; final probe exit code **0**. Probe used default `postgres` database in that fresh isolated cluster (no pre-existing/shared database), loopback port `63957`, scratch root `C:/Users/baiao/AppData/Local/Temp/issue43-review-optiona-ivlfi95i`. The reviewer server was stopped successfully with `pg_ctl ... -m fast -w stop`; other servers were untouched. No live model/network-provider call occurred.

### Long-thread limit: measured scope, no silent metadata loss

One synthetic metadata-lock/fetch sample per size, on short text IDs and narrow rows:

| Complete rows | Root guard + ordered full message metadata query/fetch | Compact tuple JSON bytes |
| --- | --- | --- |
| 1,000 | **1.56 ms** | **20,838** |
| 10,000 | **10.17 ms** | **239,918** |

These results establish that the proposed complete scan was actually exercised; they are not production latency, throughput or supported-history claims. UUID-sized IDs, full source manifests, concurrent writers, cold caches and the full transaction were not measured. In particular, the 10,000-row tuple encoding already exceeds 128 KiB; the accepted per-call manifest bound cannot be presumed to accommodate an arbitrarily large complete concurrency manifest.

**Implementation acceptance must freeze and report the actual row/serialized-byte caps and local transaction/lock timeouts, then measure representative long-thread fixtures and cap−1/cap/cap+1 cases under the shipped schema.** If the chosen bound is exceeded, return explicit `context_too_large` without coverage/CAS/reservation/model side effects; never omit IDs, summarize sibling bodies, or claim successful general long-history compaction. If the complete concurrency manifest uses a separate bounded encoding from the accepted input manifest, make that distinction auditable before accepting runtime behavior. No particular production cap/default is approved by this probe.

### Required shipped-schema implementation oracles (not yet executed)

- Run M43/A43 using the actual `u5c6d7e8f9a0` migration and canonical ORM, with populated P1a/native before/after parity and metadata comparison/downgrade fences. Freeze comparison coverage for every current native mapped column; prove raw values/public DTOs do not change.
- Verify real FK catalog/validation/deferral, exact isolation and FOR UPDATE modes. Exercise INSERT/FK-check-before-root and root-before-check, commit/rollback variants, reparent-in/out, update/delete/cascade/ABA/recreation, actual prepare/finalize/fail/archive/bulk paths and all current-message metadata. Add source deletion, membership revocation, workspace archive and lease/cancel races. Two attempts total; no regenerated summary or budget reset on retry.
- In a second Session lock each existing target subsequently touched by the new snapshot/coverage/use/call/pointer FK or consistency path. Prove pre-acquisition/whole rollback prevents implicit waits or reverse-root cycles; test uniqueness/deferred-constraint failures too. No relaxed test-only DDL or B fallback.
- Fail after each staged atomic write and before/after actual commit acknowledgement; fresh reads select all-old/all-new by the stable operation key. Retained historical snapshots must not obstruct valid native append/update, while stale candidates/dispatches are rejected.
- Execute server-receipt accounting after revoke/delete/cancel/expiry in both native pricing branches: allowed aggregate loads only, no semantic/private/source/object use or ORM escape, settle-first/reclaim-first/repeats/conflicts, and native-flush/sidecar-CAS failure. Native totals/unknown disposition remain authoritative with one charge.
- Measure/report the complete metadata cap behavior and guard hold time with representative long-thread data. Then continue all previously required compaction mechanics, semantic-negative, same-Attempt/native-state and integration evidence; this probe does not accept every-dispatch chat/Research wiring or model quality/UI.

**Controller disposition:** the developer may now implement the exact selected-A successor schema, neutral atomic repository and dedicated proof tests within the five granted existing files and new-file lane. Stop and surface any failed locking/schema oracle; no global-lock fallback, native raw-data rewrite or ownership expansion is authorized. Subsequent independent implementation review remains mandatory. Whole #43/#41 remains open.

Write-back check: only this review is a durable reviewer repository edit. The authorized disposable mechanism probe created synthetic scratch database files only and stopped its server. No product/test/shared-contract/Git/global-memory/model writes; concurrent pure algorithm work was left untouched. Ownership hash remained stable. The final concurrent contract update was inspected and exactly reconciled as recorded above; selected schema/locking/accounting scope did not change.

## Historical targeted re-review — superseded by selected-A approval


**Disposition: REWORK REQUIRED — NOT APPROVED.** Reviewed exact contract SHA-256 `B3A4C56B7DF17F764E883BA31D96F4B5B7A3C100833B2BC7D9BAD93540FC470D` at HEAD `cae6379e1f3743b944b745797cf6f157b1915654`. The controller's three-file ownership grant is unchanged. This section supersedes the earlier finding dispositions; the earlier review below is retained as history. No broad R1–R16 redesign was performed.

### F43-1 — original settlement-eligibility defect repaired; P1 content-free implementation contract still needs one clarification

The revised state/arithmetic protocol is credible against the actual native functions:

- `provider.py::_provider_call_chain` locks Run → Step → Attempt → ProviderCall → Ledger and refreshes/validates the identities without requiring a running Attempt, live membership or eligible sources.
- `reconcile_provider_call` accepts only native `sent`, transfers token/cost reservations into actual/conservative usage and updates Attempt totals; it flushes without committing. `mark_provider_call_sent` already moved the provider-call count from reserved to actual. The sidecar must not repeat either operation.
- `state.py::reclaim_expired_research_steps` first locks the same native root chain, then calls and ledgers. It cancels reserved calls; sent calls become `outcome_unknown` with conservative accounting. The shared Run lock serializes it against settlement. Mirroring an existing native terminal result without invoking native reconcile again correctly preserves the winner, including uncertainty. Identical-repeat/conflicting-repeat handling and rollback of native-plus-sidecar writes are now explicitly required.
- The separate server-held receipt authority correctly keeps content admission/adoption forbidden after revoke/delete/cancel/expiry while allowing bookkeeping. The original requirement for live membership during every settlement is removed by the operative §§4/11 exception; the last generic “after workspace/member guards” phrase in §9 must be read as content-path only.

**Residual:** the stronger statement “no body reads” in §4 is not met simply by invoking the unmodified native reconcile helper. `provider.py::reconcile_provider_call` uses `db.get(ResearchPlanRevision, ...)` or `db.get(ResearchExecutionSnapshot, ...)` to obtain pricing metadata. Both ORM mappings include `question_text` (`models/research_run.py:121,223`), and ordinary `Session.get` loads the full mapped row. In a fresh accounting Session this reads the task question after revocation, although only pricing is needed. The new public receipt DTO being content-free does not remove that database read. The native lock helpers also load whole aggregate rows, including free-text error fields.

**Narrow correction:** make the intended authority and implementation explicit. If the contract retains zero body reads, specify a metadata-only projection/preload path for the reused native helpers (with no lazy body loading) and its exact ownership; do not duplicate reservation/reconcile arithmetic. Alternatively, explicitly define the existing native aggregate-row loads as a narrowly scoped internal accounting allowance, while prohibiting content use, return, copying, source/object reads and new private-memory access. Such an allowance must be auditable in the contract rather than reported as zero body reads. This finding does not require new private/native product scope or another ledger.

**PG oracle:** use a fresh Session with question/error markers, exercise both planning and execution pricing branches after membership removal, and observe emitted SQL/attribute loads and persisted outputs against the chosen contract. Also cover settle-first and reclaim-first barriers, repeated/conflicting receipts, reserved cancellation, genuine unknown usage, and a failure injected between native flush and sidecar CAS. Assert one durable native charge, matching sidecar disposition, no adopted checkpoint/new send and no returned or newly persisted content. These tests have not been run by this reviewer.

### F43-2 — direct compactor cycle repaired; P1 native-to-native trigger cycle remains

NOWAIT acquisition of **all** explicit compactor row guards, followed by full rollback and at most two attempts total, removes the previously identified cycle where the compactor held Thread T while waiting for native-writer-owned Message M. A source-row miss must roll back the entire transaction before retry, not only a savepoint. Native callbacks may use their existing blocking selects only after the same rows have already been successfully guarded. This closes the original direct compactor/message case at design level.

The migration still introduces blocking thread/execution acquisition from message BEFORE triggers. A compactor is not required for the resulting cycle:

1. In a thread with an enabled nonterminal execution E, native writer B holds child Message C for UPDATE and has not yet acquired Thread T in the proposed message trigger.
2. Native writer A deletes parent Message P, acquiring P, then T and E through that trigger.
3. B requests T and waits for A.
4. A's native foreign-key action now updates `C.parent_message_id = NULL` and waits for C. `ChatMessage.parent_message_id` has **ON DELETE SET NULL**, verified in `models/chat_message.py:20–25` and migration `c2e4f8a1b7d9_add_chat_message_branches.py:27–32`.
5. A waits for B; B waits for A. No compactor NOWAIT statement exists in this execution. PostgreSQL must abort a native writer, contradicting the revised promise that no native-writer retry is needed and native save succeeds.

The same audit must include the indirect thread UPDATE from `ChatThread.active_message_id ON DELETE SET NULL` (`chat_thread.py:18–25`), trigger-driven execution version updates, and new snapshot/owner consistency predicates. Explicit NOWAIT source selects do not automatically apply to FK actions or trigger DML. The contract has not yet defined the latter predicates' lock behavior, so their safety cannot be inferred from the capture table. None of these observations claims an executed PostgreSQL failure; this is a concrete source-backed lock schedule allowed by the proposed protocol.

**Narrow correction:** define an enforceable compatible-writer boundary for enabled threads, including parent deletion/FK side effects and ordinary finalize/update paths, before the first message-row lock. If this is supplied by later #44 writer integration, explicitly fence creation/activation of enabled executions until **all** relevant writers follow the protocol, retain legacy no-enabled behavior, and limit this core's concurrency claim accordingly. Any existing-writer code changes require the named handoff already required by the controller. A core-local alternative must cover the native-to-native schedule above; changing only the compactor's SELECT or labeling a native abort `context_changed` does not do so. Do not solve it by changing native deletion/save semantics or adding unbounded retries.

For the snapshot/trigger portion, specify that consistency checks do not reacquire native roots after taking snapshot/call/consumer locks in reverse order; pre-acquire any row locks required by FK/trigger writes, or define the checks as nonlocking validation under already-held owner guards. Context-version bumps from native writes must not fail solely because the retained last-good snapshot represents an older context version.

**PG oracles required before implementation acceptance:**

- Compactor/native UPDATE and DELETE, in both barrier orders: native operation succeeds under the chosen writer protocol; compactor rolls back or commits a currently valid candidate in at most two attempts, with no regenerated summary/extra charge.
- **Two native writers, no active compactor:** parent DELETE with child UPDATE held before its trigger; include active-leaf SET NULL and execution-version trigger effects. Both intended operations complete under the explicitly enabled writer protocol without relying on victim selection.
- Actual `finalize_chat`/failure mutation pattern against source capture; active-leaf ABA, append with unchanged leaf, multiple enabled executions and no-enabled legacy rows.
- Lock each indirect snapshot/call/coverage/owner-reference target in a second connection, including the new consistency-trigger paths; prove bounded contention handling, full rollback and no reversed root acquisition. Distinguish an intended retention/FK rejection from a deadlock or an incorrect context-consistency rejection.
- After a successful checkpoint, append/modify authorized native context and commit: the native save succeeds, old checkpoint remains last-good historical state, and a stale candidate cannot adopt. Force failure after each staged snapshot/coverage/use/pointer write and at deferred-constraint/commit time; fresh-session reads remain all-old or all-new.

### Targeted disposition

| Item | Result |
| --- | --- |
| F43-1 original live-membership settlement blocker | **Closed at design level**; native transition/lock/arithmetic comparison performed |
| F43-1 exact content-free claim versus reused ORM loads | **Residual P1**, narrow authority/projection clarification required |
| F43-2 compactor → native-message direct wait cycle | **Closed at design level** by full NOWAIT guard/rollback protocol |
| F43-2 native/FK/trigger lock closure | **Residual P1**, compatible writer/activation and indirect-check protocol required |
| Exact revised delta approval | **NOT APPROVED** |
| Controller ownership / provider prerequisite | Unchanged; no additional grant or provider acceptance inferred |
| PG/runtime/semantic/UI evidence | **Unrun by this reviewer; required oracles above are specifications, not passes** |

Controller may relay these two narrowly scoped residuals to the same developer. Product/schema implementation remains behind the design gate. The accepted architecture and original full-outcome boundaries remain unchanged.

Evidence: focused source reads of `provider.py`, `state.py`, `locks.py`, native chat/Research models, actual chat service commit paths and branch migration; exact §§4/8/9/11 read, candidate hash verified twice. No private memory, product/test/Git/service/model writes or calls. Write-back is confined to this review; no duplicate global/workbench memory entry is appropriate.

## Earlier exact-candidate review (superseded dispositions)


### F43-1 — P1: content authorization is also required for accounting-only settlement

**Contract:** `lanes/issue43-compaction.md` §4 lines 46/52 and §9 accounting-callback paragraph. §4 combines reserve/send/settle under the same current owner/source guards. §9 requires refreshed creator membership before invoking the native accounting callback and rejects missing membership before any call write. No accounting-only exception is defined.

**Failure:** a summary call is validly sent, then its actor is removed, its source deleted, the task cancelled or its lease expires before the response arrives. Content adoption must fail. Under the proposed unified guard the known call usage cannot be settled either. This strands the sidecar/native reconciliation or forces recovery to keep an avoidable unknown charge. Native `packages/research-persistence/src/citeframe_research_persistence/provider.py::_provider_call_chain/reconcile_provider_call` deliberately validates the existing chain without requiring live membership/source eligibility or a running Attempt. The existing reclaimer separately accounts sent calls as unknown. Imposing content guards on every reconciliation changes those native semantics.

**Bounded correction:** split admission/send/content adoption from accounting-only settlement in the contract. Define a server-held authority tied to the already-recorded call/owner/native ledger, accepting only bounded status/usage/hash metadata and permitting settlement after revoke/delete/cancel/expiry. It must neither read/return source/result bodies, generate, adopt a checkpoint, revive an Attempt nor authorize another send. Use the existing native call transition plus sidecar CAS in one transaction; explicitly handle a race with native reclaim so already-accounted calls cannot be billed/refunded twice. Preserve unknown outcomes when the result really is unknown. Keep current membership/source guards on every content use and admission. This requires a narrow command/predicate clarification, not a new budget owner or general maintenance framework.

**Required later evidence:** real-PG sent-call fixtures with each invalidation between send and settlement; observed known usage reconciles once, no late snapshot/pointer/dispatch, no private/result-body persistence through this path. Race accounting with native reclaim and assert native plus sidecar final states/totals. No static safety claim is made from this finding.

### F43-2 — P1: trigger lock inversion has no guaranteed bounded recovery for the native writer

**Contract:** §8 lines 79–82. The message trigger takes the thread lock after PostgreSQL has locked an UPDATE/DELETE message row; capture/adoption takes thread → message. The addendum recognizes deadlock and labels the abort a retryable `context_changed`. §2 expressly excludes the existing chat service/writers from this lane.

**Counterexample:** transaction A captures/locks Thread T and waits for Message M; existing transaction B updates M and its new BEFORE trigger waits for T. PostgreSQL can choose **B**, not A, as deadlock victim. A compaction exception handler cannot convert or retry B's failure. `apps/api/src/ai_pdf_api/services/chat.py::finalize_chat` changes the assistant row and active leaf and calls `db.commit()` without the proposed bounded `context_changed` retry. Thus the contract's stated recovery does not cover both possible victims, and may fail a native answer save while the compactor survives. This is a reviewed migration/writer interaction, even though actual new dispatch activation is deferred.

**Bounded correction:** specify a concrete protocol that prevents the compactor from leaving this wait cycle, or explicitly assign and gate compatible native-writer recovery before these interactions can run. A possible core-local approach is nonblocking acquisition of potentially message-first-held source rows, aborting and releasing the compaction transaction on lock contention before bounded retry; the complete chosen lock order still needs validation. Do not rely on PostgreSQL choosing the compactor as victim. If compatible writer changes are deferred, state the actual enforceable activation fence and keep mixed-writer concurrency unaccepted; prose labeling an external transaction's error is insufficient. No expansion of reviewer file ownership is authorized.

**Required later evidence:** controlled separate PostgreSQL connections running the actual native writer pattern against capture/adoption, including update/delete, active-leaf ABA and an appended child. Assert native save success or its explicitly integrated bounded retry, compactor bounded result, and no stale coverage/pointer. Include the no-enabled-execution/legacy path. Test absence of silent corruption and preservation of the user operation separately.

**Open findings:** P0: none identified; P1: two. These are bounded contract corrections, not a reopening of accepted R1–R16. No Issue43 schema/implementation approval is granted yet.

## Exact candidate, ownership and accepted scope

- Worktree: `D:/Code/citeframe-lanes/issue43-compaction`; branch `work/issue43-inloop-compaction`.
- Fixed baseline inspected: `2e9287638fee9567c6474b8356c3b3ba93fec16a`. Controller changed HEAD during review to `cae6379e1f3743b944b745797cf6f157b1915654` by integrating the neutral provider prerequisite. This reviewer made no Git writes.
- Exact candidate inspected: `specs/v5/memory-management/lanes/issue43-compaction.md`, **§§1–10**, SHA-256 `88DF13CDC54FD0D9E732774A3AF0C8A605C3C08FE8DC6EA12BF91D67089E3F27`. It arrived after the initial missing-artifact preflight; this disposition supersedes that pending-only report.
- `lanes/issue43-controller-ownership.md`, SHA-256 `27D80D7E57E7A3AED6DE85D63F7C2561BAD51E334DF82C9C7E8206AFC81CF9E5`, grants the new files and narrowly scoped existing `models/memory.py`, `models/research_execution.py`, `models/__init__.py` changes. This satisfies the file-handoff prerequisite. It grants no schema approval; every other shared ABI/route/test/CI/lock file remains excluded.
- Reuse accepted design R1–R16 and effective spec **v4 §§12–14 / A1 choice2**. Historical A1/#40 holds in old review entries are superseded by the current authority. No private native task/audience product; owner-private memory is excluded from every shared path, including the owner's own records. No inferred long-term candidates or Research evidence expansion.
- Governing result remains automatic compaction before every main dispatch and same-task continuation without another user message. This phase may accept the neutral core and atomic persistence contract. #44 chat wiring, #45 native frozen-release/role/recovery integration, #46 UI, semantic quality and whole #43/#41 acceptance remain separate. #40 merge is not required for this neutral phase.

The following aspects are satisfactory **at contract scope**, subject to correcting F43-1/F43-2 and later implementation evidence:

1. One transaction owns snapshot, exact ordered coverage, direct/raw-leaf dependencies and the actual chat/Attempt pointer/context CAS. Business checkpoint fields remain native. The common neutral module is cohesive; there is no independent summary-head authority.
2. §9 defines the internal capture/adopt/reconcile/read/prepare boundary and stable errors; public API is unchanged. It prohibits implicit helper commits and explicitly avoids `ensure_creator_membership` during adoption. Transaction-neutral native accounting callbacks preserve native ledger arithmetic; they need the settlement-authority correction above.
3. Scoped successor migration `u5c6d7e8f9a0` after `t4b5c6d7e8f9`, staged circular FKs, populated P1a parity and guarded downgrade are appropriate. §9 explicitly fixes NULL-sensitive revision-support checks after making native source owner fields nullable. Implementation must also preserve the non-NULL instruction branch despite table-wide nullability; direct SQL must test that discriminator and all cross-workspace/private-consumer negatives.
4. Inherited bounded chunk/merge, nonrecursive summary purposes, no-progress suppression, target/hard-limit failure rules, original rebuilds, whole groups and durable oversized originals remain operative. Their exact numeric policy values and all inherited summary/manifest bounds must appear in immutable typed policy/validation, not disappear during implementation.
5. Research policy pinned in deterministic fixtures is explicitly limited to neutral-core evidence. Production frozen release/binding and dispatch integration are deferred without enabling legacy runs. Two real native context adoptions can establish storage behavior, while same-run role/continuation behavior still requires the actual later runtime.
6. Existing GenerationPort/TokenCounter/connection/object-store ports are reused; no adapter clone or shared ABI edit is approved. Controller-reported and developer-recorded 117 provider tests are supporting prerequisite evidence only; this reviewer did not rerun them.

## Actual native owners and constraints inspected

Paths below are repository-relative. These are source observations, not runtime passes.

| Area | Concrete baseline evidence | Consequence for the exact delta |
| --- | --- | --- |
| Chat owner | `packages/backend-persistence/src/citeframe_persistence/models/chat_thread.py:10` has `active_message_id`, archive state and timestamps; `chat_message.py:10` has parent ancestry, content/status and no actor or monotonic context version. `apps/api/src/ai_pdf_api/services/chat.py:69,302,321` prepares messages and changes the active leaf on completion/failure. | Current rows do not provide the proposed durable chat execution/context CAS. Name the real execution owner and pointer, branch/leaf guard, version advancement rules and later writer integration. No attribution inferred from thread creator; no summary-head-only substitute. In inspected chat service paths, leaf updates do not take an explicit thread row lock; core locking alone cannot establish integrated append/branch race safety. |
| Research owner | `packages/backend-persistence/src/citeframe_persistence/models/research_execution.py:89–128`: Attempt owns status, lease hash/expiry, counters and business checkpoint artifact pointer. It has no memory context version/pointer or general Attempt state-version column. Run/Step own state versions; Step has current attempt number and native branch identity. | Additions to the actual Attempt mapping/table need explicit ownership and exact migration impact. A guard must use existing native fields accurately, including current Attempt relationship and lease credentials/expiry; do not invent an existing lease-generation field. Separate context CAS from business checkpoint identity. |
| Research locking/lease | `packages/research-persistence/src/citeframe_research_persistence/locks.py::lock_attempt_chain` locks and refreshes Run → Step → Attempt, validating workspace/parent relationships. `lease.py:402–442` validates the lease token, active state, cancellation and frozen plan/execution chain. `_active_attempt_chain` is a distinct path without a supplied worker token. | Capture/adoption must retain the native lock order and independently establish the correct worker authority. UUID existence or a caller-supplied version is insufficient. Heartbeats change expiry without creating a new Attempt; distinguish renewal from stale-worker/replacement identity. |
| Membership transaction hazard | `packages/research-persistence/src/citeframe_research_persistence/membership.py::ensure_creator_membership` reads membership without its own row lock; on loss it changes cancellation state, **commits the Session**, then raises. | This helper cannot be treated as a transaction-neutral authorizer after staging snapshot/coverage/pointer writes. The exact command must specify transaction ownership, guarded membership ordering and failure rollback. Reuse native cancellation semantics without permitting an internal commit of staged compaction writes. Revocation/archive writers and dispatch authorization still require integration evidence. |
| Native checkpoint | `packages/research-persistence/src/citeframe_research_persistence/completion.py:38–86` creates internal schema-v1 object-backed execution checkpoints and requires `ResearchExecutionSnapshot`. Branch/synthesis completion sets Attempt/Run business pointers. | Planner compaction cannot call this helper as its storage owner. Preserve business checkpoint/publication fields; atomically change only the reviewed live memory-context reference with snapshot/coverage/dependencies. Future native checkpoint payload additions must be explicitly versioned. |
| Provider dispatch | `apps/worker/src/ai_pdf_worker/research/adapters/generation.py:175–300` resolves frozen IO/context policy, packs input, hashes it, reserves, marks sent and invokes generation under heartbeat. | Every-dispatch integration belongs before final request fingerprint/reservation and must preserve frozen release behavior. This core phase does not establish planner/researcher/verifier/critic/synthesizer/continuation/resume coverage. Summary dispatch must use the bounded nonrecursive path and existing neutral ports. |
| Native budgets and unknown outcome | `packages/research-persistence/src/citeframe_research_persistence/provider.py:39–156` reserves the native plan/execution ledger and requires a capability matcher; native token limits here are per-call. `state.py:293–329` cancels reserved calls, accounts sent calls as estimated `outcome_unknown`, and preserves uncertainty. Its reclaim path excludes publication-owned Attempts. | Exact sidecar/native accounting linkage must avoid duplicate charges, refund/reset or blind resend. New cumulative policy cannot be inferred from per-call limits. Native reclaim/publication ownership must survive compaction. No external exactly-once claim. |
| #42 sources and uses | `packages/backend-persistence/src/citeframe_persistence/models/memory.py` and `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py:33–58,114–129`: sources are instruction-only/private; uses require a memory revision consumer and source support. `citeframe_memory/access.py` authorizes private management only. | These are not an already-enabled shared native-source registry or task-checkpoint dependency relation. Using them for lawful task provenance needs the exact reviewed extension and explicit #42 ownership transfer. Do not bypass their constraints, treat private management access as shared-output authority, or invent parallel adapters/registries merely to avoid ownership. |
| Migration/import | Current inspected migration is `t4b5c6d7e8f9`, down `s3a4b5c6d7e8`. `apps/api/alembic/env.py` imports neutral `citeframe_persistence.models` and compares types/defaults. Its initializer currently exports #42 models; no context models are registered. | Specify successor revision, creation/FK/constraint order, native-column defaults, model registration and guarded downgrade. Imports/exports and native mappings are shared-owned files, not implicitly writable because a new `memory_context.py` exists. |
| Neutral ports | `packages/backend-contracts/src/citeframe_contracts/memory.py:92–187` already defines GenerationRequest/GenerationPort, TokenCounter/count provenance, connection, clock and object-store ports. Summary purposes forbid tools. Provider adapters were absent at the fixed baseline; the controller subsequently integrated them at cae6379. Their runtime behavior is not independently accepted in this review. | Reuse these ports. New compaction DTOs may refer to them; any ABI extension requires owner handoff. Actual provider-backed summary execution remains dependent on the separately reviewed neutral adapter lane. Deterministic core tests do not prove adapter integration. |

## Semantic oracles and later implementation review

- **Atomicity:** force faults after each staged write and before/after commit acknowledgement; fresh-session reads show all-old or all-new snapshot/coverage/dependencies/live pointer. Two compactors from one version have one winner. Stale leaf, new complete group, changed source, cancellation, revoked membership or expired/replaced lease cannot adopt or dispatch.
- **Continuation and native preservation:** two committed compactions within one live Research Attempt preserve run/step/Attempt IDs, completed tool/result identities, business checkpoint/publication state and monotonic ledger totals. After crash, committed completed work is not rerun. Later integrated chat/Research traces must include every actual main send, including no-compaction sends.
- **Protocol and bounded failure:** delayed/unknown parallel member prevents partial-group continuation; failed terminal members retain matching call IDs. Oversized-result tail remains exactly retrievable. Archive failure produces no successful dangling ref. No-gain, overfull mandatory input, overfull chunk/merge and exhausted limits terminate boundedly without advancing coverage or losing mandatory content.
- **Privacy and meaning:** inject unique private markers for caller, second member and owner; none may enter shared inputs, tool results, summaries/checkpoints, plans, logs or outputs. A structurally valid summary omitting a critical qualifier/negation/conflict side must fail semantic evaluation. Source identifiers alone cannot certify meaning or authorize Research evidence.
- **Recovery/accounting:** known-unsent, sent-unknown, durable-result/pre-adoption, committed/pre-send and genuine native lease recovery are distinguished. No automatic unknown resend, reset/refund, duplicate side effect or publication. Last-good checkpoint stays intact on every rejection.

Implementation review requires real PostgreSQL populated upgrade/schema parity, constraints, separate-session races and crash/reconciliation evidence, plus runtime use of the real owners. Deterministic tests establish mechanics only. No model call is authorized here; local semantic-quality evidence remains a separate future gate, and paid evaluation is excluded. Real UI acceptance belongs to later integrated product work.

## Evidence-scoped disposition and handoff

| Review area | Status |
| --- | --- |
| Governing outcome/A1 and native baseline alignment | **pass — static review scope** |
| Exact artifact and scoped file ownership available | **pass — §§1–10 and controller handoff inspected** |
| Schema/API/transaction contract approval | **blocked — F43-1/F43-2; NOT APPROVED** |
| Implementation, real PG migration/races, runtime recovery | **blocked / unrun by this reviewer** |
| Real-model semantic quality / real visible UI | **blocked / unrun; independent gates** |
| Private native product, evidence expansion, inferred long-term candidates | **not applicable / excluded** |

Commands used: `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, remote/local/global identity reads; `python D:/Code/dev-workbench/scripts/prepare_session.py --repo-path D:/Code/citeframe-lanes/issue43-compaction`; targeted `Get-Content`/`rg` reads of the paths above; `Test-Path`; `Get-FileHash`. Initial worktree was clean. Referenced workbench project/state/task were read only. No migration, test, service or model evaluation was run by this reviewer. Some broad reads were truncated; findings rely on the subsequent focused source/contract reads quoted above.

Governing document SHA-256:

- `spec.md`: `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85`
- `design.md`: `828EFFB02B5FBF9818604E35EA13662814E12CCC605B704DD895FD7BBAFE6236`
- `controller-brief.md`: `5FCB90CD11F87319DC8A1CC9BCA9C4013F7824BD8C119F6B2B64CE6D529A350A`

**Controller handoff:** relay F43-1/F43-2 to the original developer for bounded contract rework, then return the exact revised candidate to this reviewer. Ownership need not be re-requested for the already-granted three files; additional native-writer changes require a separate named handoff if that remedy is chosen. Do not begin affected schema implementation on the strength of the initial preflight or this non-approval. Reuse this reviewer for the revised contract and later independent implementation pass. Whole Issue43/Issue41 remains open.

Write-back check: verified inspection, exact candidate identity and disposition are durable only in this review. No private MEMORY/daily memory read; no global/profile/shared-workbench write; no product/test/shared-file edit; no Git writes. Concurrent developer/controller edits to lane/delivery artifacts were observed and left untouched. Only this review artifact is authored.


## Pure policy/units/packing implementation audit

**Disposition: REWORK REQUIRED for this bounded five-file pure slice.** Option A schema/design APPROVE above is unchanged. This review neither inspects nor accepts the concurrent unfinished database implementation, dispatch integration, semantic quality or UI.

### P43-A1 — P1: protected current request prevents same-task tool-history compaction

**Location:** `packages/memory-service/src/citeframe_memory/compaction/packing.py:66–79`, with the chronology contract in `assemble_request` and replacement at lines 92–102.

The planner ends the compressible prefix at the first protected unit and retains everything afterward. The documented current user question is a chronological protected unit. During the first ongoing response, that question precedes all completed tool rounds. Therefore none of those growing rounds can ever enter the compressible prefix. Even when earlier conversational history existed, exhausting its prefix leaves subsequent tool growth subject to the same obstruction.

**Executed reproduction using the existing deterministic fixture Counter:** units = protected `current` (15 characters) followed by six complete two-call tool groups with unique IDs; `recent_units=1`, all group keys new, `Capacity(900,720,540)`, policy min-new=1. Actual input **807** crosses soft 720, with five old complete groups available, but result is **`no_compressible_units`**, compressible length zero. With seven groups, actual input **934** produces **`mandatory_context_limit_exceeded`** because the entire post-current history is treated as mandatory.

**Correction:** represent the current request/other protected anchors separately from the compressible chronological interval, so an old complete prefix of the *in-flight tool history after the current request* can be replaced while that request stays before the retained rounds. Keep explicit ordered covered-unit identity and preserve every protected unit; do not move the question ahead of older conversation, mark it unprotected, delete it or silently create coverage holes. The chosen pure plan/replacement representation must make this same-submission case expressible. This is necessary for the accepted in-loop outcome and does not require new persistence design.

**Required regression:** one protected current request, no subsequent user message, successive complete groups crossing soft and then hard; an eligible older group interval is selected and replaced, current request and recent whole groups retain exact chronological order, and a second episode can compact newly eligible rounds. Include protected constraints within history and verify no omitted or double-covered units.

### P43-A2 — P1: tool-group chunks are incompatible with the actual neutral counter/serializer

**Location:** `packing.py:115–137,144–146`; dependency behavior in `adapters/counting.py::PayloadTokenCounter.count` and `adapters/_requests.py::prepare`.

`partition_summary_chunks` requires `purpose=compact_chunk` and empty tools, then copies a tool group's original assistant tool_calls and tool-result messages directly into the generated request. The existing native serializer requires each historical tool call's name to exist in `request.tools`. The summary purpose forbids supplying those tools. Thus a valid complete group cannot be counted or dispatched by the existing neutral implementation. The test fixture Counter skips native serialization, so `test_chunk_boundaries_keep_complete_groups_and_exact_originals` passes while masking this incompatibility.

**Executed reproduction:** a valid two-call `read_source` batch passes native full-request counting as a main request with its bounded tool definition. Passing the same group to `partition_summary_chunks` with `CharacterEstimateCounter`/`CountingProfile`, empty-tools compact template and input_limit=500 fails with **`ProtocolError('memory_counting_failed')`** for **all three protocols**:

| Protocol | Valid main request count | Chunk result |
| --- | --- | --- |
| openai_responses | 169 | memory_counting_failed |
| openai_chat_completions | 190 | memory_counting_failed |
| anthropic | 162 | memory_counting_failed |

**Correction:** construct a non-executable source-data representation for summary inputs and count that exact final native request. Preserve group identity, ordered calls/arguments/results and explicit succeeded/failed/cancelled states as attributed data, plus the original units for coverage. Do not enable tools on summary calls, recursively invoke the main gate, clone an adapter, or count a different request from the one later sent. A provider-ABI change would require a separate handoff; a pure deterministic transcript projection can remain within this slice.

**Required regression:** use the actual neutral payload counter/serializer for each supported protocol to partition a valid parallel batch, including failed/cancelled outcomes. All returned chunk requests must serialize with tools empty, preserve the full source-data group and fit the counted physical cap. No provider/network/model call is needed.

### P43-A3 — P2: supplied Capacity is not checked against the current physical request

**Location:** `packing.py:48–89`; `capacity_for` in `policy.py` computes a valid capacity separately, but the planner does not bind or revalidate it.

A structurally valid Capacity can be retained from an earlier model/output configuration or constructed independently. `plan_compaction` uses only its supplied hard/soft limits. It never verifies that hard fits `connection.context_window_tokens - template.max_output_tokens`, nor that output reserve fits the current connection. Counter-identity checks do not establish that relationship.

**Executed reproduction with the actual `CharacterEstimateCounter`, not only the fixture counter:** current connection context=**200**, output max=100; request reserves **100** output; one protected current unit counts **160** input. Passing `Capacity(900,720,540)` returns **`below_soft`**, although the physical input ceiling is at most **100** even before any safety margin. No dispatch occurred; this demonstrates an unsafe planner classification when a caller supplies stale capacity, not an observed production send.

**Correction:** derive the capacity from the exact current request/profile/policy at the planning boundary, or validate a bound capacity object there and reject stale/impossible values. Preserve configured stricter input ceilings and safety margins; do not silently expand them. Ensure the candidate gain/recount path uses the same bound capacity. This is a pure invariant check, not a source/permission grant.

**Required regression:** lower the model capacity or raise output reserve between capacity construction and planning; reject before returning a safe-continuation classification, with a stable error. Include current-output-over-profile and same-profile-fingerprint/stale-capacity cases using the real counter.

### Independent execution and candidate identity

Executed without bytecode/pytest-cache writes:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH="$pwd/packages/backend-contracts/src;$pwd/packages/backend-persistence/src;$pwd/packages/memory-service/src"
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_compaction_algorithms.py packages/memory-service/tests/test_native_provider.py packages/memory-service/tests/test_token_counting.py packages/memory-service/tests/test_wire_provider.py -q -p no:cacheprovider --tb=short
```

**Actual result: 185 passed in 0.60 s** (68 focused + 117 provider/count tests). Additional adversarial probes above were executed as inline Python with the same local package roots, importing the existing fixture helper where stated and actual neutral counting implementations where stated. They made no model/network request. No product tests were added or changed.

The five hashes matched `lanes/issue43-algorithms-evidence.json` before review and remained identical after the suite and both adversarial-probe calls:

| File | SHA-256 |
| --- | --- |
| compaction/__init__.py | `456c29be0a4f60166669a94a432bcc4c89a536740b5ee821a94aa5d762cc7208` |
| compaction/policy.py | `1ec0899b93cd0b828f8f11977958ddd9fd2aba8c6bbd3e4083744767d6281f98` |
| compaction/units.py | `5ebb23a85ee51818845926bb8c7f4b7347c706a0ed9e3e76a2683a3c5d34be76` |
| compaction/packing.py | `1db1e16baa026af38e993d2ea309b3abab785364bf7b7bf40dc7fba5677f7010` |
| tests/test_compaction_algorithms.py | `6b9f9a04ecfc754829c59865469e3eec4c2d4b8b1f22c4fcd612128e094ec4a8` |

First four paths are under `packages/memory-service/src/citeframe_memory/`; test path is under `packages/memory-service/`. Concurrent database/contract work is outside this identity and was not attributed to or audited as part of this pure slice.

### Bounded disposition

- **Two P1 and one P2 actionable findings; pure slice not accepted.** Original developer can absorb them while database implementation continues.
- Complete ordered batch membership, duplicate/orphan rejection, protected-prefix preservation for the tested pre-current history cases, request counter metadata checks and chunk-call caps passed the existing deterministic tests. Those local passes do not resolve the failing same-task/tool-summary boundaries.
- Pure module imports remain neutral. Code/docstrings correctly leave source authorization, durable no-progress/journal state, adoption and dispatch authority outside these functions. No fake persistence or source-permission acceptance is inferred.
- Existing Option A design approval remains in force. Full shipped-schema PG, Research/native runtime, semantic quality and visible UI review remain later gates.
- Write-back is this appended reviewer section only. No product/test/shared-ABI/Git/model/profile-memory writes; no private memory read. No reviewer background work remains active for this bounded audit.

## Native prepared-chat lifecycle amendment — exact design decision

**APPROVE the bounded nullability/ancestry amendment for implementation and subsequent full shipped-schema PostgreSQL proof.** No residual design blocker is identified in this amendment. This decision does not accept the current unfinished core or its tests.

Exact candidate: `lanes/issue43-native-lifecycle-delta.md`, SHA-256 **`2F8B0A52DD07A47758DBAD85441859CEBDCDB282380508D071A9BB4E90A9F005`**, unchanged on repeated reads during this review. The selected Option A baseline approval remains in force. Only the already-owned new model, new u5 successor migration, compaction guards/sources/repository and dedicated tests are covered; no native writer, raw-record mutation, output-scope or shared provider change is authorized.

### Independently checked native facts

- `apps/api/src/ai_pdf_api/services/chat.py:103–118,171–188,264–274`: preparation resolves the selected parent, persists a **completed user** and **streaming assistant child**, and updates thread title/timestamps without advancing the active leaf. Consequently NULL is the correct first-turn captured native leaf. On a subsequent prepared turn the designated current user lies beyond the older active leaf.
- `chat.py:302–311,321–340`: completion/failure updates the assistant and assigns its ID to the active leaf. These native operations remain untouched.
- `chat.py:103` and `routers/chat.py:303–336`: an explicit parent or edited-root request can select a parent different from the current active leaf, including NULL with existing history. Thus **selected ancestry and captured active leaf are distinct facts**. The current user's parent must not be required to equal the captured active leaf.
- Native `ChatThread.active_message_id` is nullable; the message parent and active-leaf FKs use SET NULL. Message/thread/workspace FKs reference individual IDs and do not themselves prove that a designated pair and all of its ancestors share the execution's workspace/thread. Those predicates remain the guarded resolver's responsibility.
- The unfinished `memory_context.py:29,84` and u5 DDL still impose the two restrictive predicates identified by the amendment. `repository.py:98` copies the native active leaf; `guards.py:106–110` starts ancestry at that leaf; `sources.py:10–24` checks ancestry before admitting completed/failed user/assistant sources. This corroborates both described gaps directly. It is not a review of the rest of the unfinished implementation.

### Precise authorized amendment and its required semantics

1. **Nullability only at the specified schema points.** Make execution `anchor_leaf_id` nullable. The snapshot column is already nullable: remove only `anchor_leaf_id IS NOT NULL` from the chat arm of `ck_task_snapshot_owner`. Preserve required chat thread, Research exclusion, the Research arm including its NULL chat anchor, all native FKs and other constraints. Match the new u5 migration to ORM, retaining predecessor `t4b5c6d7e8f9`. NULL must mean the actually observed absence of an active native leaf; do not substitute the user/assistant ID, a sentinel, or an inferred branch head.
2. **Resolve the designated pair before admitting source bodies.** Under existing complete metadata guards, validate execution workspace/thread, designated user/assistant roles and the assistant's exact parent link to the designated user. The current user is completed. Walk from that pair through the user's actual selected parent, rejecting missing, foreign-thread/workspace and cyclic ancestry. Admit the current user plus eligible ancestors; never union in unrelated active-leaf/sibling history merely because it belongs to the thread. A streaming assistant is an identity/parentage guard, not summary/source content. These checks apply again at capture, adoption and pre-send source authorization, not only during execution registration.
3. **Retain independent, NULL-safe mutation guards.** Capture the actual active leaf, thread revision and complete bounded message ID/revision set, including pair metadata, and compare them on revalidation. NULL→ID and ID→NULL are changes; in SQL use NULL-safe equality/distinctness rather than a comparison that evaluates to UNKNOWN. An unrelated branch switch must reject stale work, including a switch between owner registration and its first content authorization; starting a fresh capture must not silently rebind that execution to a new branch. Existing metadata caps/NOWAIT/retry/rollback and implicit-FK pre-acquisition obligations remain unchanged.
4. **Historical retention is separate from active dispatch authority.** Native finalize/fail must remain able to advance its leaf without rewriting the execution anchor, stored summary, coverage or original messages. Its revision/status transition invalidates outstanding capture/dispatch authority. Retained historical checkpoints may be inspected/reused only through the already-approved ancestry/dependency checks; neither a NULL anchor nor the designated assistant becoming completed grants automatic reuse or a new live dispatch. No new root-locking native trigger or native-writer hook is needed or authorized.

These are the concrete meanings of the candidate's captured-leaf, designated-ancestry, streaming-content exclusion and late-branch rejection clauses. They do not expand source kinds or audience authority. Existing deferred scope/manifest checks still require full implementation proof; current SQL's thread-level source predicate alone is not evidence of current-task ancestry enforcement.

### Required evidence before implementation acceptance

The new lifecycle test currently constructs native-shaped rows through fixture SQL; its two cases cover first/later shape only. This review did **not** execute or accept that test, a migration, or PostgreSQL runtime behavior. Schema edits were intentionally pending this design gate. Required later oracles are:

- **Full real migration/ORM parity:** populated upgrade and catalog checks for exactly the nullable execution column and amended snapshot CHECK; actual transaction commits a first-turn NULL-anchor snapshot + ordered coverage/uses + owner pointer. Wrong owner shape, foreign non-NULL FK and incomplete atomic writes still reject. Preserve all previous crash/deferred-commit and last-good-pointer proof.
- **Actual native preparation:** use `prepare_chat` with deterministic local dependencies/no paid calls; capture raw rows immediately after prepare for first NULL and later old-leaf cases. Exact current-user readback, initial dispatch and same-execution continuation include the designated question once and in order. Streaming assistant content must never enter a registered source, generated summary input or source readback, even when a fixture puts a distinctive marker in that body. Compare native raw fields before/after compaction.
- **Explicit branch and malformed-pair negatives:** select an older sibling parent, and edit a root while another leaf is active. Only the selected ancestry is admitted; the old active branch remains metadata-only. Reject wrong roles/linkage, cross-thread/workspace IDs, missing/cyclic parents and another pending pair. Include completed/failed ancestor dispositions without treating failures as confirmed facts.
- **NULL/branch/status races:** separate-session leaf NULL→ID, ID→NULL and A→B→A; reparent/status/body changes to the pair; switch before first capture and between capture/adoption/pre-send. Each stale path fails closed within the existing bounds, with no new snapshot/pointer/dispatch. Exercise real finalize/fail, preserving immutable historical checkpoint data and excluding renewed live authority. Same-ID recreation and insertion fences remain covered by the prior Option A obligations.

### Unchanged gates and write-back

- **P43-A1/P43-A2/P43-A3 remain open in this independent review.** Concurrent fixes, test counts or this lifecycle approval do not close the pure-slice findings.
- **#45 F45-3 upstream roles remain outside current same-step scope.** Any expansion requires a separate owner-reviewed exact delta covering both the resolver and database predicates; this amendment grants neither.
- Full saved-schema PG, native/runtime dispatch, semantic-quality and real UI acceptance remain separate and pending. No whole Issue43/Issue41 completion is claimed.
- Evidence method: targeted `Get-Content`, `rg -n` and SHA-256 reads of the candidate, native prepare/finalize/fail/router/mappings and narrowly affected in-progress schema/guard/source/repository sections. Native `chat.py` identity: `DD6D28F8629C1655ACA238B817ACE9BE81C4DFB33C4198027B8FE9F966973C91`. No test, database, model or Git write was performed in this amendment review. Write-back is this appended review only; no private memory or global/shared-workbench write.

## Interval rendering / persisted dispatchProfile — targeted exact-delta review

**Disposition: REWORK REQUIRED for exact candidate `ADF9667B7C33821F84B89972436AF0BFB3CF34CB19CE5DB9861DB8576979C540`.** Two bounded contract corrections below are needed before adopting the new rendering/result JSON meanings. The interval representation and persisted dispatch-profile direction are appropriate; no additional table, native writer, provider ABI or independent head is requested. The native-lifecycle amendment remains **APPROVED** under its separately recorded hash. The candidate's final sentence calling that amendment pending is stale and does not reopen its gate. Unaffected implementation work can continue.

Candidate: `lanes/issue43-interval-rendering-delta.md`, hash checked before/after inspection and the focused pure run, unchanged. This is an exact JSON/persistence contract review plus a bounded pure-code recheck. It is not full database/core implementation acceptance.

### P43-I1 — P1: aggregate rendering interval does not define each summary call's actual input/support scope or final-result eligibility

**Target:** amendment lines 17–18,25–29; owned gate/journal/repository call sites.

The proposal gives every summary record a `compactionPlan` describing the replacement interval, requires its end beyond the previous covered frontier, and permits adoption via a valid `generation_call_id`. It does not distinguish the input subset of an intermediate chunk from the full replacement interval, or specify which results are eligible to become that interval's replacement. Cumulative dependency coverage `[0,end)` has a third, deliberately broader meaning: it includes protected/raw-before originals that the summary did not consume.

This distinction matters in the actual code. `gate.py:96,163` supplies the cumulative covered prefix to summary validation, `journal.py:215` validates against the entire capture, and `repository.py:216,233–243` validates the cumulative prefix and accepts either a valid `compact_chunk` or `compact_merge` generation record. None of these existing predicates establishes the proposed interval-specific input/support proof. Their implementation is unfinished; this finding concerns the missing exact replacement contract, not a claim that interval persistence has already shipped.

**Independent executable counterexample:** for originals `[protected_question, g1, g2]` and intended interval `[1,3)`, the actual `validate_summary` accepts a nonempty summary whose only sourceRef is the protected question when passed the cumulative prefix. Passing the actual interval rejects it with `invalid_summary_source`. Likewise, a chunk physically containing only `g1` accepts a summary citing only `g2` when validated against the full interval; exact chunk validation rejects it. The probe used no provider or database. These are provenance-scope failures independent of subjective summary quality.

There is also a repeated-episode ambiguity: with prior frontier 6 and a new aggregate interval `[1,9)`, a legitimate first chunk `[1,4)` cannot satisfy the proposed end-beyond-frontier rule if that rule applies to every chunk's own input interval. Copying aggregate `[1,9)` into all chunks avoids that conflict but would make a single partial chunk appear to represent the entire replacement unless final-result eligibility is separately checked.

**Required precise amendment:**

- Keep `compactionPlan` as the **episode's aggregate replacement plan**, with the beyond-prior-frontier requirement applying to adoption. Specify an additional bounded, code-owned per-call input descriptor: exact ordered original unit keys for a chunk; exact ordered child result call IDs/hashes for a merge. Define its exact JSON name/schema and validation before authoring that persisted meaning. Existing immutable request archives/hashes remain the physical-payload evidence.
- Validate each chunk's source/group refs against the originals actually supplied to that chunk. Validate merged support against those authenticated child results and the aggregate interval. Cumulative prefix dependencies remain authorized/readable but do not automatically become support for interval summary atoms.
- A chunk is adoptable directly only when its authenticated complete-unit input is the entire selected interval. A merge is adoptable only when its validated child-input union covers that interval exactly, without gaps, duplicate groups or out-of-interval support. Intermediate chunks cannot carry final rendering authority solely because they copied the aggregate plan.
- The same checks must hold on save, recovered-result use, final adoption and checkpoint reload; protect raw-before/current/interior anchors independently of coverage. Retained prior intervals must preserve their own result/input provenance. Summarizing a containing interval must retain the original-unit mapping and the existing bounded nonrecursive/rebuild rules; it cannot reinterpret prior summary prose as an original source.

This remains inside the proposed owned JSON/service boundary and the single snapshot+coverage+uses+live-pointer transaction. No new provider fields, native sources or shared schema extension are needed to state it. Exact support validation proves permitted provenance and complete input consumption; semantic omission/fidelity remains a separate oracle.

### P43-I2 — P2: recovered summary results bypass the stated reservation/send profile binding

**Target:** amendment lines 25,35; `gate.py:151–153`, `journal.py:261–277`.

The proposed profile equality applies to idempotent reservation, request archive adoption and `mark_sent`. Actual summary recovery runs **before** reservation: `recovered_summary` returns a succeeded valid result after request-hash/result-hash checks, and the gate returns it without calling those three boundaries. The candidate's adoption paragraph names plan/capture/summary-hash checks, but does not define the saved-result profile comparison. A changed counter identity or physical/configured ceiling can leave request bytes and the current recovery key unchanged (the current key includes only config fingerprint and counter version from the profile). The proposed checks alone therefore do not pin the recovery path's meaning.

**Required precise amendment:** extend the same strict input-manifest/profile/plan/input-descriptor equality to recovered **unadopted** summary results and their adoption. Reject mismatch before returning reusable content or performing archive/provider effects; do not relabel an old result with the current provider/counter provenance. This does not require resending a known result. Keep committed historical checkpoint rendering separate: retain its recorded generation provenance and revalidate/recount the newly rendered main request under the current physical profile. Record that distinction explicitly so recovery cannot become an implicit compatibility path. Unknown/sent results remain non-replayable.

### Persistence/ABI assessment of the remaining proposal

The following parts are **acceptable at design scope**, subject to the two corrections above and subsequent implementation evidence:

- `covered_count = intervalEnd` is a cumulative **dependency frontier**, not the count of hidden units. Keeping coverage `[0,end)` permits exact existing prefix extension while a protected question remains rendered. The durable plan must be the sole omission/rendering authority. No fallback to `units[covered_count:]` is valid after this amendment.
- Original-unit half-open indices must be strict integers with `0 <= start < end <= len(capture.units)`; protected keys must be unique known unit keys and carried forward. Apply intervals in parent/version order, retain disjoint intervals, replace only fully contained earlier intervals, and reject partial overlap or protected-anchor containment. Missing/deleted/invalidated result metadata, cycles, inconsistent parent captures or bound overflow fail closed without truncating the chain.
- Planner selection, gain calculation and final main count must all use the same current rendered request, preserving earlier summary intervals and raw chronology. Select only intervals that can extend the persisted frontier. The existing nonzero-start refusal is a safe interim guard and **cannot be final delivery** of P43-A1.
- Define `dispatchProfile.maxOutputTokens` as the connection's physical output ceiling; the exact request's reserved output is already bound by its immutable request hash and reserved-output count. `contextWindowTokens` is physical model capacity, `inputCeiling` is the configured input cap, and `safetyMargin` is the nonnegative explicit reserve. Compute hard input from all of these and actual request output. `watermarks` is the exact complete CompactionPolicy object, not just its ratios. Counter identity and config fingerprint must agree with the actual count metadata. Reject malformed/missing/version-mismatched profiles rather than filling defaults.
- Code-owned provider identity must match the identifier supplied to native reservation; protocol/model/config/counter/capacity fields must come from the actual frozen connection/policy/counter inputs. These internal JSON fields grant no source authority. GenerationRequest, native callback parameters, neutral ports and adapters remain unchanged; no endpoint, API key or secret is persisted.
- Reservation, archive adoption and mark-sent must compare the **whole** stored profile and bound request/capture identity, even if request hash and config fingerprint are unchanged. Recompute/count immediately against the current physical/configured cap before object/send effects. Non-dispatch accounting/tool records cannot acquire provider-send authority by omitting profile fields.
- Existing snapshots lacking explicit rendering metadata may fail runtime reload with the named error; no migration/inference from text/sourceRefs/ordinal count is approved. Snapshot insertion, cumulative coverage/uses and real pointer CAS remain one atomic transaction. Exact prior/current source versions, group completion, native membership/lease/cancel and Option A guards remain mandatory.

### Required independent oracles after revised exact contract and implementation

1. Same live native execution/current question, no next user turn: commit `[a,b)` after the protected question, append complete groups, commit a containing or disjoint later interval. Include earlier conversation and an interior protected constraint. Recreate repository/gate in a fresh process and compare **exact reconstructed GenerationRequest bytes/hash** with pre-restart rendering; every raw/protected unit stays in order and every replacement corresponds to the correct original interval.
2. Assert cumulative original coverage/source versions/group IDs and direct/raw dependency uses, plus effective rendered intervals, separately. Inject a protected-only/out-of-interval sourceRef, a sibling-chunk ref, a partial chunk used as final generation result, missing/duplicate child results, partial overlap, protected-key removal and corrupted/missing parent/result metadata. Reject without pointer/coverage changes or provider replay.
3. Change each profile/counter/capacity field while keeping GenerationRequest bytes and config fingerprint fixed where possible. Exercise reserve, archive adoption, send **and succeeded-result recovery/adoption**. Observe zero new object/provider effects on rejection and unchanged authoritative accounting. Recount historical checkpoint rendering under the current profile with original provenance retained.
4. Save actual count metadata for original/current-rendered/candidate requests, using all three existing serializers. Summary chunk input and merge fan-in must fit their independently counted caps; no partial tool groups, recursive main gate or manufactured source authority. Preserve no-progress/budget/unknown/crash bounds and the single-transaction all-old/all-new oracle. Full saved-schema PG evidence remains a later independent gate.

### This reviewer's actual bounded execution and provenance

Executed with bytecode/pytest cache disabled and lane-local package roots:

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_compaction_algorithms.py packages/memory-service/tests/test_compaction_native_packing.py packages/memory-service/tests/test_native_provider.py packages/memory-service/tests/test_token_counting.py packages/memory-service/tests/test_wire_provider.py -q -p no:cacheprovider --tb=short
```

**Actual original independent reviewer result: 214 passed in 1.09 s.** The separate inline sourceRef probes described in P43-I1 also ran in this reviewer turn. No DB, model/network or full-core suite was run here.

Bounded pure findings update: P43-A2's executable-tool summary serialization counterexample is addressed by the tool-less attributed projection, independently tested for all three protocols and succeeded/failed/cancelled parallel results. P43-A3's original physically impossible supplied-capacity counterexample is rejected by the new planning check and native-counter regressions; persisted profile/recovery admission remains pending as above. P43-A1's pure nonzero interval selection/chronology tests pass, but durable same-task repeated-episode acceptance remains blocked. These observations do not close the whole original pure/core acceptance gate or waive the new provenance findings.

Source identities pinned before reads/tests and stable through the final comparison:

| File under `packages/memory-service/` | SHA-256 |
| --- | --- |
| src/citeframe_memory/compaction/gate.py | `C371DEE7D1C3AE819E3A7A45AEF39DFD385179AD126007303E00A85715EE2113` |
| src/citeframe_memory/compaction/journal.py | `0643125D343A6A1E978B80804744077ED6BB640137DF40A6885DDC2D7CF5E8A3` |
| src/citeframe_memory/compaction/packing.py | `A9F32697DF3D3AAA2BF42C56396349782E77627D1C0A422CBCECD8D83D94120F` |
| src/citeframe_memory/compaction/policy.py | `F992B4D5E0D512A6CAE7756CAB3ED0E33DEF8F178A4948C05A919DC9B2796B44` |
| src/citeframe_memory/compaction/repository.py | `38EC20BA9D0D0707218DAD8849DE37300CEE5025897C64BF47E0240F6235ECD6` |
| src/citeframe_memory/compaction/requests.py | `3615F7374C06D7CB2CD946A77BDD3F42E207CC2ECA24DDF0B7AEFD495B6B77E5` |
| src/citeframe_memory/compaction/summary.py | `703FE529562EC677E6E3AD01756B3F38A47AD2A6097FA2F9F7F4E5EF1E6B91BD` |
| tests/test_compaction_algorithms.py | `9CB0A2FF185660F55EE751A5C0A4B3728624F12FADD8A7C0907E35D9CEC86D60` |
| tests/test_compaction_native_packing.py | `92C7CCA41324165380FFB1AA0E4C0A1DE5B7F01236FCD6B92BCAA0B971637FCC` |

Concurrent changes were detected in `test_compaction_constraints.py`, `test_compaction_guard_limits.py`, `test_compaction_long_branch.py`, `test_compaction_native_lifecycle.py` and `test_compaction_repository.py`. None was part of this executed suite or accepted by this review. Existing evidence's guards/repository hashes also differ from this turn's initial working files; prior evidence cannot attest those later native-lifecycle changes. No full-DB acceptance is inferred from the current in-progress tree.

`issue43-core-evidence.json` observed hash: `1440E6A10DB697E1BCABF08FB56F9D97B9C65A3886389CF4845EF1D7655A1019`. Its `controllerIndependentReproduction` and other controller-labeled results are **reported external runs recorded by the development lane**, not runs executed by this original independent reviewer. Their specific runner provenance has not been independently verified here; do not promote those labels to this reviewer/controller's evidence. Only the command/result and probes immediately above are newly attributable to this review. The developer/controller should correct or substantiate external attribution in its owned evidence artifact; this reviewer did not edit it.

Write-back: this review appendix only. No product/test/schema/shared-ABI/Git/model/private-memory/global-workbench writes. Selected Option A and native-lifecycle approvals are unchanged; #45 F45-3 still requires its separate resolver/database-predicate delta. Whole Issue43/Issue41, full PG/runtime, semantic quality and UI acceptance remain open.

## Revised interval/result/profile contract — design gate reopened and approved

**APPROVE the revised exact design delta** `lanes/issue43-interval-rendering-delta.md`, SHA-256 **`B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736`**, for implementation in its listed owned files. Reviewed all operative sections against P43-I1/P43-I2 and the existing gate/journal/repository/summary/request boundaries. **P43-I1 and P43-I2 are closed at design scope only.** No interval implementation, durable repeated-episode behavior or full-core acceptance is granted.

The revised contract now distinguishes aggregate plan, exact per-chunk original-unit inputs, merge child-result/input-manifest hashes, final eligibility and cumulative dependencies. It scopes atom support to actual input, requires complete ordered original coverage for final eligibility, permits intermediate chunks before the old frontier, and revalidates eligibility/provenance on save/recovery/adoption/reload. Containing replacement intervals rebuild from originals; retained summaries keep their original provenance. Missing/corrupt metadata fails closed; no source inference or recursive merge-of-merge path is introduced.

Whole-profile/capture/plan/descriptor/request equality now explicitly governs recovered unadopted results and adoption, closing the recovery bypass. Committed historical rendering has a distinct, explicit rule: authenticate historical provenance, revalidate current authority, and recount/reserve the new request under the current actual physical profile. The one atomic snapshot+coverage+uses+native-pointer transaction and neutral provider ABI remain unchanged. `summary.py` is expressly inside the existing owned module scope; no new shared-file transfer is implied.

Required implementation proof remains the revised contract's five oracle groups plus this review's exact-request/restart, source-ref/subset/final-eligibility, profile-change/recovery and atomicity negatives. Nonzero interval refusal remains an interim guard only. Prior Option A and native-lifecycle approvals remain valid. The concurrent independent core schema/source/accounting audit continues separately against the pinned pre-interval candidate; it cannot establish correctness of future interval edits.

Write-back for this narrow gate: this reviewer appendix only; no product/schema/Git/model writes. Candidate hash was rechecked at append time.

## Independent shipped-core audit — pre-interval candidate at 2d6c5b2

**Disposition: REWORK REQUIRED.** Two P1 implementation findings and one P2 persisted-integrity finding below remain, in addition to the CI collection gate. This audit excludes acceptance of the forthcoming interval implementation. Revised interval contract `B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736` is approved at design scope in the preceding section; its implementation still needs independent review.

### Exact candidate and evidence authority

- Actual worktree HEAD inspected: **`2d6c5b2fd8ab0ec7f2092f2be9e34162e61dfea3`**, containing the accepted admission dependency. The Issue43 candidate is the uncommitted 35-file product/test manifest initially recorded in developer evidence SHA-256 **`EAB89C5B1CA2B1EA6E8D36371C1B81F9F2FBFC4DE096F05369299E14AB36573B`**. All **35 file hashes matched at entry and remained unchanged through the last independent run/probe and final hash check**. These executions are post-admission-integration evidence; earlier developer runs at cae6379 are not substituted for them.
- During the audit, the developer changed contract/evidence documentation only. Evidence became **`FE0F9A6D9089B9F56345705CC070ACEC54F469EC6A8CC28D2819F0873155FB74`**; comparison confirmed unchanged product/test manifest plus revised interval reference, attribution corrections and additional developer-reported records. `controllerIndependentReproduction` was replaced with developer-root attribution. Those historical/root/subworker records remain **DEVELOPER evidence**. The executions below were performed by this original independent reviewer.
- No product, test, migration, provider or Git write was made by this reviewer. Scratch SQL mutations were confined to a newly initialized reviewer-owned disposable PostgreSQL **17.11** cluster on loopback port 56543, database `citeframe_memory43_test`, unique fixture schemas, full real Alembic chain and actual vector/pg_trgm extensions. No developer/canonical database was changed. All fixture schemas were removed by fixture teardown; the reviewer server was stopped before delivery.

### F43-C1 — P1: registration leaves the active-anchor FK target unguarded and can make a native DELETE the deadlock victim

**Location:** `compaction/repository.py:66–108` (`create_chat`), especially designated-pair locking at 83–90 and `anchor_leaf_id=thread.active_message_id` at 100.

Registration locks Workspace/Membership/Thread/User and the designated current user/assistant, then INSERTs the execution. On a later prepared turn, its non-NULL anchor is ordinarily an older message, distinct from both designated rows. That anchor is not pre-acquired NOWAIT. The execution INSERT's native FK therefore introduces a blocking key-share acquisition while the compactor holds the current pair/root locks.

**Own shipped-PG reproduction:** a separate ordinary native-message writer held the old anchor row FOR UPDATE, then attempted DELETE; a barrier paused actual `create_chat` immediately before its INSERT, after it had locked the designated pair. DELETE's native parent SET NULL action waited on the locked current-user child; INSERT's anchor FK waited on the writer's old-anchor row. The native writer's session used `deadlock_timeout=10ms` to deterministically detect the cycle before the compactor's 250ms lock timeout. Results:

```text
COMPACTOR_REGISTRATION committed
NATIVE_DELETE_RESULT 40P01
```

The PostgreSQL server log confirmed the two-transaction ShareLock cycle between `DELETE FROM chat_messages` and `INSERT INTO chat_memory_executions`, with the DELETE waiting inside native `UPDATE ... SET parent_message_id = NULL`. This is an observed new implicit-FK cycle and native-writer victim. The probe's shorter deadlock timeout is explicit; no claim is made that the default 1s detector always beats the configured 250ms lock timeout. Correctness must not depend on that timing race. This is distinct from a legitimate post-registration RESTRICT retention rejection.

**Required correction:** before registration writes, NOWAIT-lock and validate the actual non-NULL captured anchor as another native FK target under the established root guards. Audit every registration FK target with the same rule. Fully roll back/retry at most twice on conflict; do not change native DELETE/SET NULL semantics, add cross-row stamping, or rely on deadlock-victim selection. Add the actual writer/registration barrier oracle in both acquisition orders, including NULL anchor. This is within the owned repository/guard/test boundary; no new schema column is needed for this defect.

### F43-C2 — P1: the mandatory main gate admits a request with no designated current question

**Location:** `compaction/gate.py:60–118,121–129`, `repository.py:146–209`.

Native guards validate the designated pair, but the main gate never requires the designated completed user's source/unit to be present in the supplied coverage or rendered request. `protected_keys` is caller-supplied and defaults empty. The repository accepts an empty source set when there are no complete tool groups. Thus the actual mandatory gate can account/archive/mark-sent an input that entirely omits the current task question.

**Own shipped-PG reproduction with the actual CharacterEstimateCounter/neutral serializer:** create a valid streaming execution using the prepared fixture; call `prepare_main_dispatch` with empty coverage, `recent_units=0`, and a system-only template, then `authorize_send`. The output was:

```text
EMPTY_COVERAGE_ADMITTED [('system', 'trusted rules')] unchanged
CALL_STATE sent
DESIGNATED_CURRENT current request
OBJECTS 1 PROVIDER_CALLS 0
```

No external provider was invoked; the observed failure is real durable send admission and archived payload omission. The designated current user remained present in the native database. Existing native-lifecycle positive tests supply its coverage/protected key correctly and consequently do not test this negative.

**Required correction:** at the authoritative chat main-dispatch boundary, derive/validate the designated current-user original and require it exactly once, protected, in its lawful chronological position. Do not infer it from arbitrary template text or trust an omitted/forged protected-key set. Reject missing/history-only coverage or inconsistent current-user identity before reservation/object/send effects. Low-level prefix capture/adoption fixtures need not be converted into main-dispatch authority. Add empty/history-only/foreign-current/duplicate-current negatives plus initial/continuation/resume positives; retain the question through both interval episodes and fresh reload. Route wiring in #44 cannot establish a guarantee that this shared mandatory gate currently fails to enforce.

### F43-C3 — P2: database scope predicates admit sibling-branch snapshot dependencies for the wrong current execution

**Location:** new u5 migration `compaction_source_scope` at 262–266, `compaction_tool_scope` at 267–271, deferred snapshot/use checks at 288 onward.

The chat source predicate checks only native message workspace/thread. It has no designated execution/ancestry input. The tool predicate similarly checks actor/thread for chat groups rather than exact execution ownership. Application `native_source`/`_validate_units` are stricter; that does not establish the claimed deferred same-task integrity boundary.

**Own shipped-PG reproduction:** create a second valid pending pair on a sibling root of the same thread and register that sibling's source under its own execution. The first execution's service read correctly rejects it. Then, using ordinary SQL on the real schema, insert a snapshot with that sibling source, a correctly recomputed ordered coverage hash, a direct source use, and the first execution's matching context-version/pointer update; force `SET CONSTRAINTS ALL IMMEDIATE` and commit. Results:

```text
SERVICE_SIBLING_READ source_branch_mismatch
DB_SOURCE_SCOPE True
SIBLING_SNAPSHOT_POINTER_COMMITTED (2, True)
SERVICE_RELOAD_DENIED source_branch_mismatch
```

This proves an invalid current-task checkpoint can be persisted and made the live pointer through the deferred integrity checks. **It does not demonstrate a service read leak**: the current resolver rejects the sibling both before and after this crafted write. The demonstrated impact is incorrectly accepted persisted provenance/live state and subsequent fail-closed unavailability. The raw-SQL negative is the same integrity-testing boundary used by the shipped constraint suite, whose foreign-thread/workspace cases do not cover this same-thread sibling case.

**Required correction:** make the owned deferred source/group/consumer predicates identify the actual current context owner and enforce its task/branch scope at adoption and dependency insertion; thread membership alone is insufficient. Preserve historical checkpoint immutability and last-good semantics, and do not acquire reverse native root locks from triggers. Add sibling-source and same-actor/same-thread foreign-execution group negatives with valid hashes so a manifest error cannot mask a scope error. Any exact predicate/schema-contract adjustment must remain auditable before implementation. This grants no upstream Research-role expansion: #45 F45-3 still needs its separate resolver **and database predicate** delta.

### Independently executed evidence

All commands used existing `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, `PYTHONDONTWRITEBYTECODE=1`, lane-local `packages/*/src` PYTHONPATH, the reviewer database URL, `-q -p no:cacheprovider --tb=short`. The supplied developer server at port 56493 was unavailable; all successful PG results below used the reviewer-created server.

1. Ran these ten modules together: `test_compaction_schema.py`, `test_compaction_native_lifecycle.py`, `test_compaction_native_races.py`, `test_compaction_repository.py`, `test_compaction_constraints.py`, `test_compaction_guard_limits.py`, `test_compaction_long_branch.py`, `test_compaction_research.py`, `test_compaction_requests.py`, `test_compaction_p1a_compatibility.py`.
   - **190 passed, 15 setup errors in 332.54s.** All 15 errors were pytest attempting to enumerate inaccessible pre-existing `%TEMP%/pytest-of-baiao`, before those test bodies ran; no product assertion failed in that run.
2. Reran the entire native-lifecycle and request modules with a fresh explicitly named reviewer-owned `--basetemp`.
   - **21 passed in 46.15s**, resolving all 15 environment errors; six already-passing lifecycle cases were repeated. Thus **205 distinct targeted core cases passed across those two runs**, not a fabricated single green aggregate.
3. Ran gate and Research-gate modules with another fresh explicit `--basetemp`.
   - **21 passed in 35.29s**. These establish the tested pre-interval mechanics, not interval rendering or F43-C2's missing-anchor negative.
4. Reran guard-limit and long-branch modules with `-s` to retain actual measurements.
   - **8 passed in 13.70s**; values below. These repeat cases in item 1.
5. Executed four additional inline reviewer probes against fresh full-migration schemas: F43-C1 deadlock, F43-C2 omitted-question admission, F43-C3 sibling persisted scope, and registration-before-first-guard ABA described below. No probe source/test file or model call was created.

There are **226 distinct pre-interval core cases passing across the scoped runs**, alongside the independently reproduced defects. The earlier 214-case pure/provider run is separately recorded and is not counted again here. Counts do not supersede the semantic failures.

### Areas supported by those executions, with exact limits

| Area | Scoped assessment |
| --- | --- |
| Approved nullable lifecycle delta | **Pass in executed cases.** Real migrated ORM/catalog parity; actual `prepare_chat` first NULL/later old leaf/explicit older sibling/edited root/failed ancestor; streaming exclusion; native finalize/fail citation/locator/detail behavior and historical checkpoint preservation. Both anchor columns are nullable with the approved owner CHECK meaning. |
| Row-local Option A mechanism | **Pass in tested capture/adoption cases; registration has F43-C1.** Real nondeferrable validated thread FK, NOWAIT contention/phantom orders, row stamps, ordinary spoof/ABA/same-ID recreation/noncycling sequence, SET NULL/CASCADE, populated upgrade/downgrade checks. No global-lock fallback. |
| Atomic snapshot transaction | **Pass in tested repository paths, subject to F43-C3's deferred-scope gap.** Injected failures after snapshot/coverage/uses/pointer and before commit roll back together; committed/lost-ack reconciliation and competing compactor cases exercised. Tests use injected faults/fresh sessions, not an operating-system crash or production failover. |
| Current source/privacy boundary | **Application negatives pass.** Wrong actor/workspace/branch/malformed pair/cancel/lease/revocation rejected; other pending and streaming bodies excluded. No private instruction resolver in shared path. Same-step Research evidence/frozen execution-asset checks tested. DB branch integrity remains F43-C3. |
| Native Research accounting | **Pass in tested native callback cases.** Actual reserve/mark-sent/reconcile/reclaim functions, planning and execution pricing branches, query/marker audit after revoke/cancel/expiry/archive/source deletion, native+sidecar rollback, concurrent reclaim/settle, unknown/cancelled winner and forged/conflicting receipts. The server-held receipt returns authoritative metadata without a second native charge/refund/refinement. |
| Root-bound policy | **Pass in exercised chat service path.** Root policy/deadline lock and descendant-call aggregation prevent the tested retry budget reset; existing calls/checkpoints pin policy fingerprints. Research's neutral commands receive an explicit policy and native callbacks; production resolution/binding to the frozen Research policy/profile remains #45 composition work. Fixture capability matcher is deterministic, not live resolver acceptance. |
| Native originals/P1a compatibility | **Pass for the executed fixtures.** Native prepare/finalize/fail methods remain unchanged; frozen Research rows/business checkpoint/artifacts are compared before/after compaction. Thirty-nine unchanged P1a oracles passed on the successor schema at HEAD 2d6c5b2. No side-effect/publication replay acceptance or new output scope is inferred. |
| Full interval runtime / real model quality / UI | **Pending separate acceptance.** Design approval alone closes none of these implementation/product gates. |

### Registration ABA and supported size envelope

**Registration is not a revision capture.** The execution stores the active-leaf ID but no registration-time thread/message revision manifest. Own probe performed NULL→user-ID→NULL after registration and before the first guard: thread revision changed **7→9**, yet the first guard succeeded. Ordinary ID/NULL mismatches are rejected; post-capture ABA is rejected by captured revisions. This is an explicit temporal coverage limit, not proof of stale summary adoption: the first capture can still read the exact lawful current graph, and no summary/captured provider input existed in this probe. Do not claim registration-to-first-read ABA detection or cancellation intent. If registration must freeze that earlier graph/intent for #44, a reviewed persisted registration token is required; an ID comparison cannot supply that guarantee. This limitation is separate from the demonstrated native-writer deadlock in registration.

**Bounds fail safely but limit the goal's supported history size.** Actual independent measurements:

| Fixture | Observed result |
| --- | --- |
| 1,023 native message metadata rows | Complete manifest **45,967 bytes**, guard **9.771ms** |
| 1,024 native message metadata rows | Complete manifest **46,013 bytes**, guard **7.909ms** |
| 1,025 native rows / manifest-byte overflow | Explicit `context_too_large`, no accepted truncated set; root/message locks released and no compaction effects in the tests |
| 128-row branch | Native tuples **5,661 bytes**, original-unit manifest **32,015 bytes**; capture/adoption transactions **102.647/672.216ms**, coverage/pointer committed |
| 1,024-row branch | Native tuples **46,010 bytes**, original-unit manifest **259,650 bytes**; refused in **17.951ms** before accepting that oversized unit manifest; no snapshot/coverage/use/call/pointer effects |

The separate 128KiB unit-manifest cap can reject a branch whose native metadata count is within 1,024. Original coverage grows across episodes even when rendered tokens shrink, so compaction does not remove this limit. Full-thread metadata also includes sibling rows, which can exhaust the cap without entering source bodies. Current defaults further bound units to 2,048 and source-body aggregation to 1MiB; native body checks occur after loading the authorized body, and source registration has its own side effect, so these measurements must not be generalized to arbitrary large-body allocation or end-to-end registration performance. These are documented safe refusals and explicit support limits, not silent data loss or a successful long-history result. No general 1,024-source compaction or production performance acceptance is granted.

### CI collection remains a delivery gate

Own `pytest packages/memory-service/tests --collect-only` found **323 compaction cases across 14 test modules** in the current candidate. Current `.github/workflows/ci.yml:73` explicitly invokes only `test_instruction_memory.py`, `test_admission.py` and `test_admission_postgres.py` for this package; other inspected jobs target API/Worker/infra directories. No compaction test path or `CITEFRAME_MEMORY43_POSTGRES_URL` provisioning was found in the workflows. Consequently the existing CI commands do not collect these new cases.

**Required before acceptance:** controller-authorized CI ownership must provision the isolated #43 database/extensions and collect every new compaction test (including forthcoming interval tests), with missing PG configuration failing rather than silently skipping. This reviewer makes no shared-CI edit or ownership transfer. Local 323-case collection is supporting evidence only; it is not CI execution.

### Pinned file identities for findings and native grounding

| File | SHA-256 |
| --- | --- |
| compaction/repository.py | `38EC20BA9D0D0707218DAD8849DE37300CEE5025897C64BF47E0240F6235ECD6` |
| compaction/gate.py | `C371DEE7D1C3AE819E3A7A45AEF39DFD385179AD126007303E00A85715EE2113` |
| compaction/guards.py | `969C91CBD30429D5FF89F850B1CFB5D35986C4AEDC35E14192094323A8AEE7D2` |
| compaction/sources.py | `D783D49F377459FD5A1B9DDD544562EA1DC5741947DF24642AE882A35AF5A66E` |
| compaction/journal.py | `0643125D343A6A1E978B80804744077ED6BB640137DF40A6885DDC2D7CF5E8A3` |
| new u5 migration | `21FE3E52A3984628F02B37918B2EBFB3C103297C13038204714CD70F99883469` |
| models/memory_context.py | `26CB462272BA7765F6ED804AE56971FE105CCAAA96175CFDD8EB7CF4FACBC67A` |
| actual API services/chat.py | `DD6D28F8629C1655ACA238B817ACE9BE81C4DFB33C4198027B8FE9F966973C91` |
| native research provider.py | `2F84259235828113E506663912C0C7E253CD6E0D8FC75FD241D970F8D8FE7794` |
| native research lease.py | `FEBAF5803BDBDC4AE9CC6A02C96A7ABD25910DB05C524D2233B409BD2F9E1E86` |
| .github/workflows/ci.yml | `363F81520750D14E74091D97CF63DC37194E9281A69DCBEE168F171C2CE8A2FD` |

Compaction paths are under `packages/memory-service/src/citeframe_memory/`; model path is under `packages/backend-persistence/src/citeframe_persistence/`; native Research paths are under `packages/research-persistence/src/citeframe_research_persistence/`. Full unchanged 35-file test/product manifest remains in the identified developer evidence artifact; its hashes were independently compared, not accepted by assertion.

**Handoff:** original developer owns rework for F43-C1/C2 and the bounded persisted-scope correction for F43-C3; controller owns arranging any shared-CI handoff. No extra implementation owner is assigned. Reuse this reviewer for exact predicate amendments and final frozen interval/core implementation evidence. Whole Issue43/Issue41 remains unaccepted. Write-back is this review artifact only; no private MEMORY/daily/profile/workbench write. No reviewer test/server/background task remains running.

## Independent exact F43-C3 predicate amendment — design gate

**Disposition: APPROVE the exact bounded design for original-developer implementation.** Reviewed `lanes/issue43-scope-predicate-delta.md`, SHA-256 **`69A7115EA197C780345285E0611F5E2488C2AD86C96D788292B9393B6974FC92`**, with the approved B34 interval contract retained. No residual design-blocking finding in this amendment. **F43-C3 remains open at implementation/runtime scope** until the corrected shipped migration and consumer paths pass independent PostgreSQL review. This does not accept the moving core, F43-C1/C2 fixes, interval implementation, dispatch integration, semantic quality or UI.

### Independent grounding and reason for approval

- **Durable identity: pass at design scope.** Actual `memory_context.py` maps the existing composite workspace/generation-call FK and call/execution FK. Actual u5 `compaction_call_identity` freezes `chat_execution_id`, workspace, actor, purpose, captured context, checkpoint and input manifest; `compaction_snapshot_immutable` freezes generation-call identity. Snapshot/call erasure changes payload/lifecycle fields, not those owner IDs. The existing FKs retain referenced identities. Consequently the proposed helper can resolve an older checkpoint independently of the current pointer and without requiring its erased result body. Do not describe the entire execution row as immutable: its lifecycle/version fields are mutable, and no execution-wide immutability trigger is established by this review. The durable binding is the frozen call-to-execution ID. New admission separately validates that execution's actual current native scope.
- **Exact scope: pass at design scope.** The current u5 source/tool helpers use thread-wide matching, as independently reproduced in F43-C3. Replacing their second argument at every caller with exact execution identity, plus the selected-user ancestry predicate, removes that specific sibling checkpoint admission. Exact tool ownership also rejects another retry/descendant/sibling execution's group. Distinguishing the owner kinds explicitly and requiring exactly one non-NULL owner prevents an ID collision between chat and Research from becoming authority. The helper's SQL argument types remain unchanged; this is a semantic ABI change at all callers, not an overload that can coexist with thread-ID callers.
- **Native lifecycle: pass at design scope.** Actual `prepare_chat` inserts a completed user and its streaming assistant without moving the active leaf; `finalize_chat` completes the assistant and advances the leaf; `fail_chat` marks it failed and advances the leaf while performing its existing citation cleanup. Therefore live streaming/anchor checks belong to new adoption/dependency/pointer admission. Applying them to unchanged-pointer owner updates would reject legitimate historical state. The amendment explicitly separates these cases and exempts lifecycle-only snapshot updates from live admission. NULL-safe anchor equality also preserves the approved first-turn NULL case. Source/native deletion or revocation must invalidate fresh reuse without making a retained checkpoint's immutable owner unknowable. Existing FK retention restrictions remain; this approval introduces no additional native delete hook or changed delete semantics.
- **Older checkpoints and dependencies: pass at design scope.** Generation ownership remains usable after two pointer advances; parent and used-snapshot equality is by exact owner, not thread or pointer search. Current dependency validation is required for fresh reuse even when immutable ownership matches. Complete bounded coverage must include the tool groups' raw source dependencies, including dependencies outside direct source coverage. An old coverage INSERT still undergoes manifest and scope validation. There is no transaction-age or no-op exemption for dependency insertion.
- **Locks/transaction: pass at design scope.** Read-only helpers do not add the reverse native-root row-lock edge that caused C1. The application must still obtain the approved NOWAIT/native/source guards and commit snapshot, coverage, uses and pointer together. These SQL predicates supplement that transaction; read-only SELECT alone does not establish concurrent lease, membership, version or source authority. No trigger-side guard substitution or independent pointer write is approved. Ordinary SQL table-level read locks remain; “no locks” in the helper description means no new explicit row/advisory/native-root lock acquisition.
- **Scope: pass.** No new columns/tables, native writer changes, private-memory path or Research upstream expansion. Research ownership remains exact attempt/same-step frozen evidence. #45 F45-3 still requires its separate resolver and database-predicate amendment. Nullable ORM fields remain nullable; the new chat generation requirement is a predicate and application contract. Genuine persisted summary-call fixtures replace missing-generation fixtures without promoting low-level prefix adoption to C2 main-dispatch authority.

### Required implementation readings and independent PostgreSQL oracles

These make the approved semantics testable; they do not expand the amendment's scope.

1. **Reject absence/NULL, not only explicit FALSE.** Use qualified table aliases and unambiguous parameters in each helper/trigger. Prove missing owner, both owner arguments, neither owner argument, absent/wrong-kind generation binding, wrong workspace/actor and cross-kind equal IDs reject. A SQL NULL returned by a predicate must never escape through `IF NOT predicate` or `WHERE NOT predicate`. Exercise every coverage/use/pointer call site after changing the second argument's meaning; retained thread-ID callers are incompatible.
2. **Repeat the original F43-C3 raw-SQL probe with a valid recomputed manifest.** The sibling source snapshot+coverage+uses+matching pointer transaction must reject with no partial rows/pointer advance. Also reject foreign-execution groups, parent snapshots, direct call consumers and used snapshots. Positive cases must include NULL first-turn anchor, later old leaf, explicit older-sibling ancestry and edited-root selection; the active-leaf branch must not be unioned into the selected ancestry.
3. **Traverse the entire selected chain.** Finding the requested source before reaching a corrupt tail is insufficient. Missing/cross-workspace/cross-thread parent, cycle, invalid role/status and overflow must reject even when the requested source is the designated user. Test the exact depth boundary and NULL termination. No source body reads or hidden body reuse are needed. For dependency validation, use complete bounded original coverage/raw group references; reject malformed or cyclic dependency structures rather than recursively trusting a summary's prose/support claims. Preserve B34's nonrecursive summary/input provenance rules.
4. **Prove history/live separation with real native methods and real rows.** Create two successive checkpoints backed by persisted valid generation calls, then finalize/fail, invalidate/erase result and snapshot payloads, revoke sources and exercise supported native deletion. Older owner lookup and unchanged-pointer state/lease/accounting updates must remain usable when snapshot context version is smaller. Fresh use/adoption/read/send and changed-pointer adoption must reject lost authority, invalid/erased results or invalidated snapshots. Test nullable anchors with `IS [NOT] DISTINCT FROM` semantics. Do not clear a retained pointer or revive an invalid result to satisfy a test.
5. **Exercise trigger timing and transaction rollback.** Run direct mutations with ordinary deferred COMMIT and `SET CONSTRAINTS ALL IMMEDIATE`; old-coverage insertion, dependency UPDATE/no-op paths and changed-pointer paths must not bypass scope. Failed admission must leave snapshot/coverage/uses/pointer unchanged. Preserve lifecycle-only updates after lost authority. Inspect shipped function definitions and runtime lock observations for hidden writes/root row locks; C1's implicit-FK prelocks remain separately required.
6. **Ship and collect the tests.** Verify populated upgrade/catalog/downgrade and all new predicate/interval cases on the real successor schema. The user's dedicated independent PG CI-file grant belongs to the original developer; shared `ci.yml` remains untouched. Missing PG configuration must fail the dedicated gate, not silently skip its cases.

No amended-schema PostgreSQL execution is claimed in this design decision: the exact C3 SQL was still awaiting authorization. The earlier sibling-SQL reproduction is this reviewer's own evidence; developer root/subworker evidence remains attributed to the developer.

### Hash-pinned source reads and concurrent-change attribution

The following actual files grounded this narrow review. Migration, native chat, guards, sources and mappings retained their previously audited hashes. Repository and journal changed during the developer's parallel B34/C1/C2 work; the values below identify the versions re-read here, **not accepted implementations**. The contract hash was checked again immediately before this append.

| File | SHA-256 |
| --- | --- |
| new u5 migration | `21FE3E52A3984628F02B37918B2EBFB3C103297C13038204714CD70F99883469` |
| models/memory_context.py | `26CB462272BA7765F6ED804AE56971FE105CCAAA96175CFDD8EB7CF4FACBC67A` |
| compaction/repository.py | `7E6C6E94B4ED9450AD7AF52F542DC83132468DC4ADA21A0D442701770981E8A7` |
| compaction/journal.py | `F34EB52B22ABD56127A536E83B8DB00C7C4A60C01E2E67BC443E69AFB72A04E6` |
| compaction/guards.py | `969C91CBD30429D5FF89F850B1CFB5D35986C4AEDC35E14192094323A8AEE7D2` |
| compaction/sources.py | `D783D49F377459FD5A1B9DDD544562EA1DC5741947DF24642AE882A35AF5A66E` |
| apps/api/src/ai_pdf_api/services/chat.py | `DD6D28F8629C1655ACA238B817ACE9BE81C4DFB33C4198027B8FE9F966973C91` |

**Handoff:** original developer may implement this exact predicate amendment in the already-owned files. Existing Option A/native-lifecycle/B34 design approvals remain. Full-core acceptance stays withheld. This review append is the only write-back; no product/test/schema/Git/model/private-memory writes or new review owner.

## Independent frozen-candidate re-review — 2026-09-29 (in progress)

Initial evidence SHA-256: `03222573DEC5427C9D53DA4B80E2396A272B4FBCEE24E90EA15EF44C43A76622`. Independently compared all **44** manifest paths against actual file bytes: all matched at entry. Actual successor migration is `080BA0EF0CA227B7E367ED2BB97164A06479ED9CC77398DF611EC1A8729DFDEA`; historical migration hashes/pass counts in the evidence are not current-candidate acceptance. Evidence subsequently reported `fullAggregatePending=false` and developer-subtree 486 passes; these remain developer evidence. The independent scoped run below is separate, on the reviewer's own PostgreSQL 17 cluster at port 56543 with unique full-migration schemas, never the developer cluster.

### F43-I3 — P2: adoption commits an interval chain that its own reload rejects

**Disposition: REWORK REQUIRED before core acceptance.** Locations: `compaction/repository.py:238–330` (`adopt`), `compaction/rendering.py:108–118,132–162` (`append_interval`, `load_intervals`). Pinned repository SHA-256 `DDAB087A72977D6FD9B0D5AC96BF34C195A89BB5DBE4739C85155E5F00B13163`; rendering SHA-256 `AA65B267CFD074517FCD205DC06BDA103BE3700F451FA9B4E17E33E00139A2C1`.

`adopt` authenticates the new call's individual plan/result/profile and requires cumulative coverage extension, but does not validate that plan against the prior authenticated interval/protected-key chain before committing. Prior protected-key retention and interval compatibility are enforced only by later `load_intervals`. Thus a genuine persisted, archived, settled, valid final-eligible summary call can advance the live pointer to an unreloadable checkpoint.

**Own independent PostgreSQL reproduction, using public journal/repository methods and no raw mutation of product state:** create a native pending execution with three lawful source units; reserve/archive/mark-sent/settle/save each summary with exact original-input descriptor and hash, then adopt in the ordinary atomic transaction.

1. First plan `[0,1)` explicitly protects original unit 1. Second plan `[0,3)` omits that protected key. Both adoptions commit. Subsequent `checkpoint_intervals` rejects `checkpoint_plan_regression`.
2. First plan `[0,2)`, second plan `[1,3)`, both without protected keys. Both adoptions commit. Subsequent `checkpoint_intervals` rejects `checkpoint_partial_overlap`.

Observed output:

```text
protected_removed ADOPTED_POINTER (2, '25486aa4-16e2-435c-afb9-91ee1c03385e')
protected_removed RELOAD checkpoint_plan_regression
partial_overlap ADOPTED_POINTER (2, 'e0c76e96-e5eb-424d-8ad9-9130fc3af784')
partial_overlap RELOAD checkpoint_partial_overlap
```

The main planner currently avoids constructing these plans, so this probe does not demonstrate omission through a normal `prepare_main_dispatch` call. It demonstrates a durable neutral-adoption boundary failure and subsequent fail-closed unavailability, analogous in impact to the earlier persisted C3 gap. Low-level prefix adoption remains allowed by the contract; its independence from C2 does not waive B34's chain/protected-anchor semantics. The second checkpoint is already committed when reload discovers the defect, so the last-good pointer is not preserved.

**Required bounded correction:** inside the same adoption transaction, load/authenticate the prior interval chain under the existing guard and validate the proposed plan's protected-key superset, frontier extension and disjoint/full-containment compatibility before any snapshot/coverage/use/pointer write. Reuse the cohesive rendering validator; do not rely on the caller being the main planner or defer this check until the next dispatch. Reject protected-key removal, newly protected keys hidden by retained intervals, partial overlap and malformed prior provenance with all-old persisted state. Add public-repository real-PG negatives with genuine valid calls and exact descriptors; retain lawful containing/disjoint positives and fresh-process reload. No schema/new owner/native writer change is requested.

Independent six-module regression run is still active at this checkpoint. Full-core disposition remains withheld. Only this review artifact was edited; scratch request objects and disposable database schemas are runtime verification data.

### F43-I4 — P2: delayed summary save can revive invalidated or erased result authority

**Disposition: REWORK REQUIRED.** `compaction/journal.py:217–236`, `CallJournal.save_summary`; SHA-256 `8BD92A66B81A9E703791155E068513F2885C3F20F2C2545A3B1027EA3E005972`. The row guard requires `state='succeeded'` but accepts every `result_state`. Only the already-`valid` case gets immutable-result/idempotence validation. An `invalidated` or `erased` result follows the first-save path and is written back as `valid`.

**Own real-PG probes:** reserve/archive/send/settle/save an authentic summary through the current journal, then perform the supported isolated-test result lifecycle transition. With native/source authority otherwise unchanged, invoke `save_summary` again using the same receipt/capture and previously saved value. In one schema set `result_state='invalidated'`; in another set `result_state='erased', result_manifest=NULL, result_sha256=NULL`. Both delayed saves succeed. The erased result is then returned by the actual `recovered_summary` path:

```text
RESAVE_INVALIDATED_RESULT valid
RESAVE_ERASED_RESULT ('valid', True)
ERASED_RESULT_RECOVERABLE True
```

This is not a source-revocation bypass: the source was deliberately left lawful to isolate result-state authority. It shows that explicit persisted invalidation/erasure of a completed result is reversible through an ordinary delayed/repeated service save, restoring reusable content without a new call. The caller need not forge the result or alter immutable call metadata. Existing reload rejection while `result_state` remains erased does not cover this transition.

**Required correction:** under the existing call lock, permit first summary save only from `absent`, and exact idempotent validation only from `valid`; reject `invalidated`/`erased` before payload writes. Preserve frozen identity and accounting settlement. Add independent real-PG delayed-save-after-invalidation and delayed-save-after-erasure cases, asserting unchanged result state/payload, no fresh reusable result, no snapshot/pointer effects and no resend. If direct SQL lifecycle monotonicity is also claimed, enforce/test it in the owned new u5 identity trigger; this finding's independently demonstrated minimum fix is the public service save path. No new table/column, native mutation or separate implementation owner is needed.


### Independent candidate identity inventory (2026-09-29 entry pin)

All 44 entries below matched the developer manifest at audit entry and the subsequent scoped-run checkpoint. This reviewer computed these hashes from the files; the manifest was not accepted by assertion. Historical evidence sections refer to other identities. This table pins the candidate with F43-I3/I4 still present.

| File | Actual SHA-256 |
| --- | --- |
| `.github/workflows/memory-compaction.yml` | `449DCE5287F862B4A1AB810D021D1E9E3BD0BFF2AC695E9DB2926901098D97AB` |
| `apps/api/alembic/versions/u5c6d7e8f9a0_inloop_compaction.py` | `080BA0EF0CA227B7E367ED2BB97164A06479ED9CC77398DF611EC1A8729DFDEA` |
| `packages/backend-contracts/src/citeframe_contracts/compaction.py` | `D77617A25ECF5CD9C0B808537F6C884B7EE67E2A2250BB0D955E99597DDB5E2B` |
| `packages/backend-persistence/src/citeframe_persistence/models/__init__.py` | `41B9E70E1F5F146F0D4C77E5EEE45CFBC0C503E4F8045DA2B80EDC6A20EBE452` |
| `packages/backend-persistence/src/citeframe_persistence/models/chat_message.py` | `4AC8D13A2F4C9322596C42A81A1EEE472C4499D9F0016B1CAAE533A1ABBFC303` |
| `packages/backend-persistence/src/citeframe_persistence/models/chat_thread.py` | `0687EF3FA9F2CE29FE9C4563A8C7BEE57D0349A1AFCE09A10F5AC630128288C9` |
| `packages/backend-persistence/src/citeframe_persistence/models/memory.py` | `FFCBF49EBB8EB3283220231E6E41DB4809D36A64790E638EE05E7477BF3E5C97` |
| `packages/backend-persistence/src/citeframe_persistence/models/memory_context.py` | `26CB462272BA7765F6ED804AE56971FE105CCAAA96175CFDD8EB7CF4FACBC67A` |
| `packages/backend-persistence/src/citeframe_persistence/models/research_execution.py` | `CF53DC4694FF7EA99D64E20E4E03455BD5960E21DB6DC66FC88EBFA92A29726D` |
| `packages/memory-service/src/citeframe_memory/compaction/__init__.py` | `2026CC0CD44D5F3475F58B0ABEE0A8F6531328D3E24FFB992150202CEC5BDD0A` |
| `packages/memory-service/src/citeframe_memory/compaction/archive.py` | `87BD63C47A8D3A9EBCD8B214F3004CC5FFE8BA4B040BCDE2A957487E42D2D5E6` |
| `packages/memory-service/src/citeframe_memory/compaction/gate.py` | `FAC0A06E9A2D74FB63C023B457CC3343A71254836A373D8628850A035D55FA59` |
| `packages/memory-service/src/citeframe_memory/compaction/guards.py` | `969C91CBD30429D5FF89F850B1CFB5D35986C4AEDC35E14192094323A8AEE7D2` |
| `packages/memory-service/src/citeframe_memory/compaction/journal.py` | `8BD92A66B81A9E703791155E068513F2885C3F20F2C2545A3B1027EA3E005972` |
| `packages/memory-service/src/citeframe_memory/compaction/packing.py` | `A9F32697DF3D3AAA2BF42C56396349782E77627D1C0A422CBCECD8D83D94120F` |
| `packages/memory-service/src/citeframe_memory/compaction/policy.py` | `F992B4D5E0D512A6CAE7756CAB3ED0E33DEF8F178A4948C05A919DC9B2796B44` |
| `packages/memory-service/src/citeframe_memory/compaction/rendering.py` | `AA65B267CFD074517FCD205DC06BDA103BE3700F451FA9B4E17E33E00139A2C1` |
| `packages/memory-service/src/citeframe_memory/compaction/repository.py` | `DDAB087A72977D6FD9B0D5AC96BF34C195A89BB5DBE4739C85155E5F00B13163` |
| `packages/memory-service/src/citeframe_memory/compaction/requests.py` | `7FB058C9B566FD025B2762012EDDC47772BB48E442835C3B65416659A2BA9477` |
| `packages/memory-service/src/citeframe_memory/compaction/sources.py` | `D783D49F377459FD5A1B9DDD544562EA1DC5741947DF24642AE882A35AF5A66E` |
| `packages/memory-service/src/citeframe_memory/compaction/summary.py` | `703FE529562EC677E6E3AD01756B3F38A47AD2A6097FA2F9F7F4E5EF1E6B91BD` |
| `packages/memory-service/src/citeframe_memory/compaction/units.py` | `5EBB23A85EE51818845926BB8C7F4B7347C706A0ED9E3E76A2683A3C5D34BE76` |
| `packages/memory-service/tests/test_compaction_algorithms.py` | `9CB0A2FF185660F55EE751A5C0A4B3728624F12FADD8A7C0907E35D9CEC86D60` |
| `packages/memory-service/tests/test_compaction_call_fixture.py` | `C4210B1FF26318C2809A6F9F908109CF80B6A962AAEC1E9549FCCBAC0844C67C` |
| `packages/memory-service/tests/test_compaction_constraints.py` | `DE2ABCC4A743A4B6A7C6B6B69A890BF0F8CA58263A4B60DB97A34CED46D48944` |
| `packages/memory-service/tests/test_compaction_fixture.py` | `645190AA83C40A2BD1F175C9C425E571CA011920A6C2E162B1AECE755E491040` |
| `packages/memory-service/tests/test_compaction_gate.py` | `73C48925030B2E1D4CF68B26046D8945527CC545F133CAF87884F16BF87EC2A3` |
| `packages/memory-service/tests/test_compaction_guard_limits.py` | `28F6E32260FE4866210D7CE1A39B6B08D3037BBF9B3C68AAF286169FDD14268A` |
| `packages/memory-service/tests/test_compaction_intervals.py` | `C961BA51642966C6FE6EE62AECF1F4DA8BF527210734C003EEC4BAC5AF0914A5` |
| `packages/memory-service/tests/test_compaction_long_branch.py` | `52D6B6665232466E7B9BF749437EE35F6C81DBCD59858EC99245516CF2897812` |
| `packages/memory-service/tests/test_compaction_main_question.py` | `F2C592340983D02ECA6973089D3CBA21FB26E9B8850EA420E6FBA685D121BC1C` |
| `packages/memory-service/tests/test_compaction_native_lifecycle.py` | `9F9DBDD7694CC2B7CDFA9F4E2ACFC070043A4BD5904C12C1790ED7389FF47FE8` |
| `packages/memory-service/tests/test_compaction_native_packing.py` | `92C7CCA41324165380FFB1AA0E4C0A1DE5B7F01236FCD6B92BCAA0B971637FCC` |
| `packages/memory-service/tests/test_compaction_native_races.py` | `C408876D0122AC2C66370CCCA3B9FE987CE98B69DD35D992142CB9B9AE8D4CFC` |
| `packages/memory-service/tests/test_compaction_p1a_compatibility.py` | `FEDFEEB0737462AAEE585E6C27986665F0186527805D03FFF64F8067E43E1ADA` |
| `packages/memory-service/tests/test_compaction_profiles.py` | `5BA0CF99B007AEE69C980A0EFFD23EEA566545123E75CE0FAA52A3A80CB931B1` |
| `packages/memory-service/tests/test_compaction_provenance.py` | `77497C3CC8314602321E75DFC96F87417F2F2EB16EAFF93E6AA8C3AF07D5A2D3` |
| `packages/memory-service/tests/test_compaction_registration.py` | `F6F4F0F1B3A99D5006EF0AF4323E71B845D23586A27B25B59828001B95E2B365` |
| `packages/memory-service/tests/test_compaction_repository.py` | `ED687DE3C7B694A35418A6322FF0AD47E2F3118879C4803657B267D17AC78F30` |
| `packages/memory-service/tests/test_compaction_requests.py` | `44B067D56B1E95A43FDBC33ABFAB1B8402A6CCB8EBCCD459E443AE19C163E0E2` |
| `packages/memory-service/tests/test_compaction_research.py` | `119895A603E898094C074F9B84513DDE02D747D75BADF255D76D4199D7D9B761` |
| `packages/memory-service/tests/test_compaction_research_gate.py` | `3AEA8EF3729862E7BABF227D7B133D9D2FEFD50DD8B8435D6F1319366D47A597` |
| `packages/memory-service/tests/test_compaction_schema.py` | `930F1B9D10851AD8C6CEE6C25186B0EF182C3708F9A3657C1A2C1B3833506450` |
| `packages/memory-service/tests/test_compaction_scope.py` | `C080D03F8F4D64A41EF934242012EC6FDF645E432558B0BFC5B3CE032BAAFF43` |


### Completed independent execution on that identity

**Disposition remains REWORK REQUIRED for F43-I3/I4.** The original F43-C1/C2/C3 reproductions are corrected in the exercised current-identity paths. No full-core PASS is granted from the green regression suite. Original developer retains implementation ownership for the two new findings.

**Identity stability:** all 44 product/test/workflow hashes in the independent inventory still matched at the end of all executions; no product/test delta was observed at the entry, intermediate or final comparisons. All 35 Python files in the owned compaction service and `test_compaction*.py` inventory were present in the manifest; no unmanifested Python file was found in those inventories. Evidence JSON changed from entry hash `03222573DEC5427C9D53DA4B80E2396A272B4FBCEE24E90EA15EF44C43A76622` to `77EEBDDAC51D62C9C3F698A54D93FBB8415B73E23FEE542A7883174F9EDFA07D`, adding/updating developer verification and aggregate status. That documentation change is not a product test run by this reviewer. Historical migration `21FE...`, earlier pure slices and prior pass counts were not used to waive current cases.

**Own commands/environment:** `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short`, `PYTHONDONTWRITEBYTECODE=1`, lane-local `packages/*/src` PYTHONPATH, reviewer-only `CITEFRAME_MEMORY43_POSTGRES_URL=postgresql+psycopg://memory43@127.0.0.1:56543/citeframe_memory43_test`. Each PG run used a separate explicit reviewer temporary `--basetemp`; each test/probe used the real full Alembic chain in its own disposable schema. All provider behavior was deterministic/local; no paid/live model or UI calls.

| Independently executed command file set | Result |
| --- | --- |
| `test_compaction_registration.py`, `test_compaction_main_question.py`, `test_compaction_scope.py`, `test_compaction_intervals.py`, `test_compaction_provenance.py`, `test_compaction_profiles.py` | **163 passed / 288.41s** |
| `test_compaction_gate.py`, `test_compaction_requests.py`, `test_compaction_research.py`, `test_compaction_research_gate.py`, `test_compaction_native_lifecycle.py`, `test_compaction_schema.py`, `test_compaction_repository.py` | **130 passed / 229.44s** |
| `test_compaction_algorithms.py`, `test_compaction_native_packing.py` | **97 passed / 0.87s** |
| `test_compaction_constraints.py`, `test_compaction_native_races.py`, `test_compaction_p1a_compatibility.py`, `test_compaction_guard_limits.py`, `test_compaction_long_branch.py` | **96 passed / 147.69s** |

These are **486 distinct collected compaction cases passing across four disjoint commands**, with no skipped cases in those runs. They are not described as a single aggregate invocation. Own dynamic-glob collection found **486 cases across 22 files** (20 test modules plus two helper/fixture modules), matching the dedicated CI inventory. The four commands cover that complete collected set. Additional independent adversarial probes below are separate from this count. None of these passing cases invalidates the two independently reproduced failures above.

### Semantic outcomes and limits

- **C1 / native DELETE: scoped pass.** Executed both actual native DELETE/SET NULL acquisition orders with NULL and non-NULL old anchors. Writer-first registration exhausts exactly two attempts, returns `context_busy`, releases locks and permits native deletion/SET NULL. Registration-first native DELETE waits for the fenced FK target and then receives the existing `23503` retention rejection after registration commits. The tests use the short 10ms native deadlock detector and actual lock-wait observation. The former `40P01` native-writer-victim result was not reproduced. Native schema/race/ABA/cascade cases and populated migration parity/downgrade cases also passed on current u5.
- **C2 / mandatory question: scoped pass.** In addition to the shipped tests, own inline probe ran **48** effect-free negatives: three real serializer protocols × four dispatch modes (`initial`, `continuation`, `resume`, `role`) × empty/history-only/foreign-current/duplicate-current coverage. Every case rejected with the expected identity-specific error, unchanged calls/pointer/snapshot/coverage/uses/request objects and zero summary-provider calls. Positive initial/continuation/resume cases, identical historical text, forged send permits and hidden-question low-level checkpoints were also exercised. Native prepared-chat NULL/old-leaf/explicit-parent cases still passed.
- **C3 / persisted scope: scoped pass.** Executed the same-thread sibling snapshot+coverage+use+pointer attack with valid recomputed manifest hashes in both deferred-COMMIT and forced-immediate modes; scope failure and complete rollback are asserted. Exact execution group/parent/used-snapshot/call-source predicates, NULL/ambiguous owners, full corrupt ancestry tail/depth boundary, two-pointer historical identity, native finalize/fail, result erasure and current-source revision checks passed. Historical identity is not made dependent on a currently valid result or active pointer. This grants no upstream Research-role scope.
- **B34 / tested planner path: scoped pass with I3/I4 exceptions.** Same-question post-question tool growth through two episodes, containing rebuilds from originals, disjoint intervals with an interior protected complete group, per-call partial/final eligibility, chunk/merge support and archive payload negatives passed. Fresh Python subprocess reload reconstructs the same canonical request and uses a forbidden provider implementation to detect summary resend. This proves durable reload through the neutral gate in those fixtures, not production Worker/API restart wiring or an external provider dispatch. Invalid plan composition remains F43-I3; invalidated/erased result resurrection remains F43-I4.
- **Loss of live authority after interval adoption: own scoped pass.** Five additional inline real-PG probes first adopted a post-question tool interval and obtained a reserved main permit, then separately applied cancel, membership removal, source invalidation, native body mutation or lease expiry. Actual `authorize_send` rejected respectively with `context_cancelled_or_terminal`, `context_access_denied`, `shared_source_unavailable`, `source_version_changed`, `context_lease_lost`. Main remained `(reserved, NULL request_object_key)`, request objects/provider-call count did not increase and the historical `(context_version=1, checkpoint_id)` remained unchanged.
- **Transactions/accounting: current regression pass within fixture scope.** Re-executed atomic adoption faults/reconciliation, request lost-ack/corruption/unknown paths, native Research receipt-only settlement/reclaim/accounting and source/member-loss cases, plus unchanged P1a regression cases. No new receipt arithmetic, native outputs or frozen Research originals were accepted by inference. These are injected-fault/concurrency tests, not operating-system crash/failover evidence.
- **Bounds remain support limits.** Current guard-limit/long-branch cases passed, including explicit metadata/unit-manifest refusal rather than truncation. They do not establish unlimited long-thread compaction or production performance. Registration-to-first-capture ABA limitation remains as previously recorded. No private source or inferred long-term candidate authority was introduced.

### Own actual serializer/count/archive/profile cross-check

An additional independent two-episode probe used the real `CharacterEstimateCounter`/native serializers for each protocol. For every physical summary/main request, compared its canonical archived bytes and request hash, complete persisted dispatchProfile, immutable output reserve, and reserved input count with a fresh count of that actual request. All comparisons passed. Each case produced six whole-unit chunk requests, two merges and two main permits; output reserve was 1,000 throughout. Current input ceiling was 5,500; physical context 8,000 and output ceiling 1,000. These are **estimated token counts from the actual serializer/counter**, not measured provider tokenizer usage:

| Protocol | Chunk inputs (each of six) | Merge inputs (episodes 1 / 2) | Main inputs (episodes 1 / 2) |
| --- | --- | --- | --- |
| openai_responses | 4,406 | 522 / 820 | 352 / 516 |
| openai_chat_completions | 4,415 | 531 / 829 | 364 / 529 |
| anthropic | 4,400 | 516 / 815 | 342 / 507 |

The exact per-call profile-drift matrix also passed at reserve/archive/send/unadopted recovery/adoption. Committed historical provenance was retained while new main requests were recounted under a changed current profile. Deterministic quantity/negation/condition fixtures remain semantic regression oracles only; no live-model semantic-quality acceptance follows.

### Dedicated CI gate

Inspected `.github/workflows/memory-compaction.yml` at hash `449DCE5287F862B4A1AB810D021D1E9E3BD0BFF2AC695E9DB2926901098D97AB`: dedicated PostgreSQL 17/pgvector service, explicit test database and extensions, dynamic sorted `test_compaction*.py` collection and execution, nonzero subprocess failures propagated. Own matching glob collected all 486 cases. Own negative execution with `CI=true` and PostgreSQL URL removed produced **two expected setup errors**, message `CI requires CITEFRAME_MEMORY43_POSTGRES_URL`, exit 1 and no skip. This verifies the missing-PG failure behavior. Hosted GitHub Actions execution was not performed or accepted; no shared `ci.yml` edit was made.

### Final handoff for this review slice

Return F43-I3/I4 to the original developer, with the exact repository/rendering/journal hashes above. Reuse this reviewer for the bounded corrections and final stable-identity reconciliation. Current C1/C2/C3 successes need not be recharacterized as design work; their current-identity runtime evidence is recorded here. Full-core acceptance remains blocked by the demonstrated implementation defects. Whole Issue43/Issue41, integrated every-dispatch routes, live semantic quality and UI remain unaccepted.

Reviewer PostgreSQL version was independently read as **17.11**. After all runs, remaining `memory43_%` fixture schemas were **0**; the reviewer server was stopped and its launcher session completed. No reviewer background verification task remains running. Durable write-back is this review artifact only; no product/test/Git/model/private-memory writes.

## Independent I3/I4 correction acceptance — frozen 45-file candidate

**Disposition: APPROVE the I3/I4 correction and the bounded neutral compaction core at the exact identity below. F43-I3 and F43-I4 are closed for the public neutral service paths. No new blocking finding was reproduced in this targeted re-review.** This supersedes the previous core REWORK disposition for those two defects; it does not rewrite their historical reproductions or claim that the old 44-file candidate was safe.

**Acceptance boundary:** reusable neutral in-loop compaction/gate, persisted interval/result provenance, owned persistence transaction, guarded current-task sources and neutral accounting mechanics, within the recorded caps and supported cases. This is **not** acceptance of actual Chat/Research every-dispatch integration, upstream Research-role resolution (#45 F45-3), hosted CI execution, live-model semantic quality, real UI, or whole Issue43/Issue41 completion. Those separate delivery gates remain explicit. No schema/native writer/provider ABI/scope expansion is authorized or implied.

### Exact candidate and scope reconciliation

Evidence file: `lanes/issue43-core-evidence.json`, SHA-256 **`A9C9385497F7092DC958ABFA218C3AEA13D089C97EBF621E92D46A24334375FB`**. Independently hashed all **45** manifest files: every actual hash matched. Compared against the **44 hashes in this review's own prior inventory**, rather than relying on the developer's historical-manifest claim. No previous path was removed. The only changed/new files were:

| File | Current SHA-256 |
| --- | --- |
| `packages/memory-service/src/citeframe_memory/compaction/repository.py` | `74D6EEEF9339F36369F474CE6D7EE4D41BC61EB32D504F2B6FB1543D964C8471` |
| `packages/memory-service/src/citeframe_memory/compaction/rendering.py` | `9D5D982D1C4B045C4F7F23E67EF2ADB265DD2AC8EC4BD42930C6C561C66049F5` |
| `packages/memory-service/src/citeframe_memory/compaction/journal.py` | `A338C0CCFAB594ADE8D704DB4002776FFEBD8BB38E992F4B8D0E8275B14CBF37` |
| new `packages/memory-service/tests/test_compaction_authority.py` | `DB494F3A5ACA5CE123952F371AE0F78C5BF4B6B5FE7C5683099769DB8F0CA5F0` |

The remaining 41 identities are unchanged from the independently pinned prior inventory. In particular, actual u5 migration remains `080BA0EF0CA227B7E367ED2BB97164A06479ED9CC77398DF611EC1A8729DFDEA`; dedicated CI workflow remains `449DCE5287F862B4A1AB810D021D1E9E3BD0BFF2AC695E9DB2926901098D97AB`. Entry, intermediate and final manifest comparisons found no mismatches/concurrent product delta; evidence hash also remained unchanged. The prior 44-file inventory plus this four-file delta reconstructs the accepted 45-file identity.

### I3 closure: validation is inside the actual adoption transaction, before writes

Read actual `repository.py:270–279` and `rendering.py:122–173`. After authenticating the new generation call's exact capture/profile/request, saved result and recomputed final eligibility, adoption now calls `load_intervals(..., proposed=(call.input_manifest,result))` and `advance_intervals(...)` using the **same database session/transaction**. This occurs before constructing/flushing the new snapshot. Prior snapshot/generation rows use the existing NOWAIT locks; those locks survive through all adoption writes and commit/rollback. No separate validation transaction or process-local summary head was added.

The shared `advance_intervals` checks the validated plan, protected-key superset, strict frontier extension, disjoint/full-containment relation and protected keys hidden by any resulting retained/replacement interval. Reload uses that same transition validator. `load_intervals` authenticates the actual historical generation chain and includes the proposed episode in both the existing maxEpisodes and combined 1MiB manifest/result budget, closing the proposed-state/readback-limit gap without changing those limits.

**Own reconstructed original probes, not merely developer-reported tests:** used public journal reserve/archive/mark-sent/settle/save methods with real source payloads, then invoked repository adoption directly. Before each invalid second adoption, independently asserted the call was `succeeded`, result `valid`, persisted `finalEligible=true`, and request archive present. Thus rejection was not an absent/invalid generation fixture masking the interval check. Observed:

```text
I3_OWN protected_removed checkpoint_plan_regression
LAST_GOOD_IDENTICAL_RELOAD_AND_ZERO_DML protected_removed
I3_OWN partial_overlap checkpoint_partial_overlap
LAST_GOOD_IDENTICAL_RELOAD_AND_ZERO_DML partial_overlap
I3_OWN newly_hidden checkpoint_protected_anchor_hidden
LAST_GOOD_IDENTICAL_RELOAD_AND_ZERO_DML newly_hidden
```

SQL event observation recorded zero INSERT/UPDATE/DELETE for the rejected adoption. Full execution/call/snapshot/coverage/use row images remained identical, and the last-good interval/protected/frontier tuple reloaded identically. An exact repeat of the first successful adoption returned the original receipt. Independently executed positive tests retained lawful containing/disjoint new episodes, post-question two-episode compaction and fresh-process reload.

### I4 closure: result state is checked under the existing call lock

Read actual `journal.py:218–236`. The locked row must now have result_state in `('absent','valid')`: absent takes the first-save validation/write path; valid takes exact saved-result/idempotence validation; invalidated/erased reject before payload DML. Accounting state/receipt identity and native source guards remain unchanged. This is public service transition enforcement; **no new claim of arbitrary-SQL lifecycle monotonicity** is made, and the migration was not changed.

**Own reconstructed original lifecycle probes:** after authentic archived success, invalidated or erased the result in separate isolated schemas, then called the same public delayed save. Both rejected `summary_call_unavailable`; full persisted row images remained unchanged and `recovered_summary` returned no reusable content:

```text
I4_OWN_DELAYED_SAVE_REJECTED_UNCHANGED invalidated
I4_OWN_DELAYED_SAVE_REJECTED_UNCHANGED erased
```

**Both real lock orders were exercised.** The authority suite tests lifecycle-writer-first contention: save exhausts bounded NOWAIT retries with `context_busy`, then rejects the committed terminal result state. In additional own save-first probes, paused an exact valid-repeat save immediately after its actual call `FOR UPDATE NOWAIT` acquired the row. A concurrent lifecycle UPDATE was independently observed in `pg_stat_activity` waiting on a lock; used 10ms deadlock_timeout and a bounded writer timeout. After save completed and released the lock, the writer committed invalidation/erasure; subsequent save rejected and recovery remained unavailable. Both states printed:

```text
SAVE_FIRST_REAL_WRITER_WAIT_THEN_COMMIT_RETRY_DENIED invalidated
SAVE_FIRST_REAL_WRITER_WAIT_THEN_COMMIT_RETRY_DENIED erased
```

These tests establish serialization of the public save with late lifecycle changes; they do not re-grant authority after a terminal result transition.

### Independent executions and provenance

All runs below are this reviewer's commands, on reviewer-owned **PostgreSQL 17.11 at port 56543**, full genuine Alembic migrations in disposable schemas. The developer cluster at 56493 was not used. Python: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`; `PYTHONDONTWRITEBYTECODE=1`; lane-local `packages/*/src` PYTHONPATH; `pytest -q -p no:cacheprovider --tb=short` with distinct explicit temporary `--basetemp` directories.

| Own execution | Result |
| --- | --- |
| `test_compaction_authority.py` | **22 passed / 41.89s** |
| `test_compaction_intervals.py`, `test_compaction_provenance.py`, `test_compaction_profiles.py`, `test_compaction_repository.py`, `test_compaction_gate.py`, `test_compaction_research.py`, `test_compaction_research_gate.py`, `test_compaction_native_lifecycle.py`, `test_compaction_long_branch.py` | **176 passed / 309.74s** |
| Matching dedicated-workflow sorted `test_compaction*.py` glob, `--collect-only` | **508 collected / 1.23s**, including the new authority module |
| Additional own inline original-counterexample and save-first-lock probes | Results recorded above; separate from pytest counts |

This is **198 distinct targeted passing cases on the current 45-file identity**, across two commands. It is not a 508-case aggregate run. The developer's red5/red2, green22, affected176, developer-root66 and pure214 entries remain developer evidence with their recorded executors. This reviewer did not relabel those executions. The earlier independently run 486-case suite remains evidence for the old pinned 44-file baseline; unchanged-file identity plus these affected-path regressions supports this bounded correction review, without pretending the old suite executed the new product.

The 22-case module was inspected as well as run. It proves zero-DML incompatible-plan and malformed/invalidated/erased-history rejection; lawful transitions; exact valid repeat/conflicting-repeat behavior; proposed episode/combined-byte caps; lifecycle contention in both adoption lock directions; and full last-good row-image preservation at **snapshot, coverage, uses, pointer and before_commit** injected rollback stages. Its adoption-first contention probe confirms a lifecycle writer is blocked by the prior generation lock through rollback, after which it can proceed. The affected regressions exercise actual interval rendering/reload, per-call final eligibility/provenance, complete profile equality, native lifecycle and accounting, plus the existing bounded long-branch behavior. No native side-effect or provider publication replay was introduced.

### Final scoped acceptance and remaining delivery boundaries

- **F43-I3 / F43-I4: CLOSED** for this exact public neutral-service implementation.
- Previously reproduced **F43-C1/C2/C3** corrections retain their prior current-baseline evidence; no schema/guard/main-gate scope change was made by this delta.
- **P43-A1/A2/A3 neutral-core concerns are resolved within the recorded evidence:** durable post-question repeated episodes preserve protected chronology; whole tool groups use the supported serializer projection; physical/current capacity and persisted dispatch profile are checked. This does not establish that every actual Chat/Research call site is wired through the gate.
- Dedicated workflow's dynamic collection includes the new 22 cases. Previously independently verified missing-PG fail-not-skip behavior remains applicable because workflow and fixture hashes are unchanged. Hosted CI execution is still an external delivery check; no hosted result is invented.
- Existing explicit metadata/source/manifest/episode limits, registration-before-first-capture ABA limitation, same-step Research scope and semantic-quality/UI separation remain in force. No private native task/audience product, upstream source grant or long-term candidate inference is accepted.

**Original developer may deliver this frozen neutral-core candidate within that boundary.** Controller may separately rerun the 22-case correction and related checks, then arrange downstream integration. Further product changes require identity reconciliation and affected-path verification; this approval does not float to later edits.

After all executions, independently confirmed **0** remaining `memory43_%` fixture schemas and stopped the reviewer PostgreSQL server. Only this review artifact was edited; no product/test/schema/Git/paid-model/private-memory writes. Runtime request objects and disposable database data were verification scratch only.

## Independent post-integration current-head test delta — APPROVE

**Disposition: APPROVE the exact three assertion-line changes in the two API test files below for controller commit. No defect found in this bounded delta.** Actual read-only `git rev-parse HEAD` returned `b4e773a8fed882cd8cd8c6164c2b8814299eab56`. Core commit/PR delivery history is controller-reported; no reviewer commit, push or merge was performed.

| Reviewed artifact | SHA-256 |
| --- | --- |
| `apps/api/tests/test_research_migration.py` | `52F83664473A9644829C4B50AC718E171197D8C0A6668F43AEB79DD2418CCD05` |
| `apps/api/tests/test_asset_migration.py` | `B5F85E71FBF92AEE4144D7B48CEBD5B65220546C2F703909595D77D30DBFC6E6` |
| Developer report `specs/v5/memory-management/evidence/issue43/controller-integration.md` | `675FC475D4806EDE46D87D6B7F6C30B20E96551DC8C344E1459C64E476D6BC6B` |

**Exact diff verified against current HEAD:** research test replaces the literal expected single head t4 with u5 and adds literal `u5.down_revision == t4`; asset test replaces one literal t4 post-head assertion with u5. Numstat is research +2/-1 and asset +1/-1. Scoped `git diff --check` passed; LF/CRLF checkout warnings do not change the inspected delta or raw hashes.

**Semantic assessment: pass.**

- `test_alembic_has_one_evolvable_head_after_autonomy` calls `ScriptDirectory.get_heads()`, so this assertion is the repository's current single head, not a historical checkpoint. The actual u5 migration declares `revision='u5c6d7e8f9a0'` and `down_revision='t4b5c6d7e8f9'`. The new literal edge strengthens the chain check. Existing t4→s3→r2 assertions remain unchanged; expectations are not derived from the observed head.
- The asset test explicitly upgrades to `head`, takes the populated evidence payload snapshot, performs real dump/restore, then verifies rollback refusal and both databases' retained head/configuration. u5 is therefore the correct expected value at that final assertion. Its separate explicit upgrade to r2 and r2 retention assertion after the earlier refused downgrade remain unchanged. Legacy/image/document migration anchors, evidence payload comparisons, encryption-related refusal and corruption negatives were not weakened.
- Independently compared all **45 previously approved core raw hashes** against both the current manifest and this review's own accepted hash inventory (prior inventory plus I3/I4 delta): **0 mismatches**. End-of-run manifest recheck also found 0. No product, schema or core workflow change is part of this test delta; the prior bounded neutral-core approval remains valid at its exact identity.

### Own bounded verification

Executed both complete affected modules on the reviewer's own isolated **PostgreSQL 17.11 at 127.0.0.1:56543**, not the developer cluster:

```text
apps/api/tests/test_research_migration.py
apps/api/tests/test_asset_migration.py
18 passed, 1 warning in 9.43s; zero skips
```

Used `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, `PYTHONDONTWRITEBYTECODE=1`, lane-local API/tests/Worker/packages PYTHONPATH, `AI_PDF_DATABASE_URL` pointing only to the reviewer test server, and `pytest -q -p no:cacheprovider --tb=short` with an explicit unique temporary basetemp. A Python launcher prefixed the actual PostgreSQL binary directory to PATH before pytest; no test monkeypatch or fixture bypass was used. Independently printed/discovered:

```text
D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/pg_dump.EXE — PostgreSQL 17.11
D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/pg_restore.EXE — PostgreSQL 17.11
```

The unmodified asset test executed its actual dump/restore oracle with zero skips, including the changed final source/restored-head assertion. The sole warning was the existing Starlette/httpx deprecation. This is this reviewer's own 18-case run. The report's initial 17+1skip, worker 18, developer-root adjacent 19 and 7 remain their original executor-scoped evidence and are not added to this result.

Both test hashes and the developer-report hash remained exactly as pinned after execution. The unchanged fixtures removed all their `ai_pdf_%` disposable databases (independently queried: empty list); the reviewer server was stopped. Only this review artifact was edited. No product/test/schema/Git write, paid provider or UI operation occurred. This approval is limited to the three-line current-head compatibility correction and identity preservation; it adds no actual Chat/Research/UI or whole-Issue acceptance.
