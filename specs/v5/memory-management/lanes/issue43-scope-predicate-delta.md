# Issue43 exact persisted execution-scope predicate amendment

Status: proposed F43-C3 correction; affected SQL authoring remains stopped pending exact original-reviewer approval. No new table/column, provider ABI, native source kind, native writer or Research upstream scope. This changes the new u5 successor's predicates and matching neutral adoption validation only; predecessor remains t4b5c6d7e8f9. Selected Option A locks/revisions and approved interval contract B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736 remain governing.

## 1. Durable chat snapshot owner, including old checkpoints

Use the existing immutable `task_memory_snapshots.generation_call_id -> memory_calls.id -> chat_execution_id` chain as the durable chat execution identity. For every newly inserted chat snapshot, require non-NULL generation_call_id referencing a succeeded, valid compact_chunk/compact_merge call of exactly that execution, workspace and actor; immutable call identity and snapshot generation FK preserve this owner after native pointer advancement. No current-pointer search, matching thread/actor fallback, ancestry-based owner inference or operation-key decoding is permitted. A missing or ambiguous binding rejects.

This is an explicit tightened predicate on existing fields: columns and ORM nullability remain unchanged. Research snapshot ownership remains exact existing attempt_id; no new Research generation requirement. Existing direct low-level chat `adopt(...,generation_call_id=None)` fixtures must create a real persisted, valid, correctly owned journal summary call and pass it; the neutral chat adoption path rejects an absent generation binding before writes. Those fixtures may still capture/adopt a lawful prefix that omits the current question; C2 main-dispatch authority is separate. Under B34, an adopted call must additionally have authenticated complete interval input and final eligibility. Tests may not substitute an in-memory checkpoint or disable the new predicate.

No historical deployed-data backfill is proposed: this is the unshipped u5 candidate. Tests that create nullable-generation chat snapshots through raw SQL must now expect rejection. Existing historical chat snapshots created under the corrected schema always retain the immutable call owner, including after checkpoint pointer movement, native finalize/fail, source revocation or summary invalidation/erasure. Owner identity lookup itself does not require that the call/result/source remain currently valid; live admission validates those states separately.

## 2. Exact predicate signatures and live source/group semantics

Change the meaning/signature of `compaction_source_scope(x memory_sources, eid varchar, aid varchar)` so its second argument is an exact chat execution ID, never a thread ID. Exactly one owner argument must be non-NULL. For chat:

- Resolve execution by eid; require x.workspace_id=execution.workspace_id, shared current chat_message source with non-NULL hash, and exact native message identity.
- Resolve designated user/assistant metadata in the execution's workspace/thread; require completed user, streaming assistant, assistant.parent_message_id=user.id, valid current execution state and no cancel request. Current thread active leaf must be NULL-safe equal to execution.anchor_leaf_id. No source body reads are needed by these SQL predicates.
- Traverse the user's actual parent chain using a bounded recursive CTE with explicit visited IDs and depth bound 1024. Require all visited rows in the same workspace/thread, eligible user/assistant role and completed/failed status, termination at NULL, and no cycle/missing parent/bound overflow. Admit only source native_id in that selected chain. Never union active-leaf or sibling history. The streaming assistant is excluded.
- Source-version/hash/parent and coverage canonical-hash checks remain separately mandatory at existing consumer checks; this predicate does not authenticate bytes or grant source access outside the application guard.

Keep the Research source branch's exact current same-attempt/same-step frozen evidence predicate; no prior/upstream role sources, sibling attempts, or run-wide widening.

`compaction_tool_scope(c memory_calls, eid varchar, aid varchar, actor varchar)` likewise accepts exact execution ID. Require exact workspace/actor consistency with the resolved owner, succeeded valid tool_group, and c.chat_execution_id=eid (or existing c.research_attempt_id=aid). Same actor/thread, retry root, descendant execution or sibling request is insufficient. No tool-result prose or sourceRefs can manufacture ownership; raw source dependencies must independently satisfy the same exact consumer owner.

## 3. Consumer resolution and trigger scope

A cohesive read-only helper `compaction_snapshot_chat_owner(snapshot_id varchar)` returns only the immutable generation-call chat owner above. It checks snapshot/call workspace/actor/thread identity and rejects absent/inconsistent bindings; it does not require live execution/message/source status. No table writes or locks occur in this helper.

- **Snapshot insertion / coverage completion:** derive exact chat owner from generation_call_id. Validate coverage sources and tool groups with that owner; enforce current call validity, selected ancestry and NULL-safe captured anchor at new adoption. Generation call's immutable captured owner/context and snapshot context progression must agree. Research uses exact attempt_id. Existing complete ordered manifest, parent-prefix and native-pointer-required checks remain.
- **Parent snapshot:** immutable parent and child chat owners must be equal, in addition to existing workspace/actor/thread/version checks. Sharing a thread does not permit adopting another execution's parent checkpoint.
- **memory_uses INSERT/UPDATE:** resolve consumer_call_id directly to its immutable exact call owner or consumer_snapshot_id through the helper; require NEW.workspace_id match consumer and every dependency. Validate new source/group dependencies against that exact owner. For used_snapshot_id require identical immutable execution/attempt owner and workspace, and validate its complete bounded source/group dependency coverage for current lawful reuse. A retained historical snapshot is not automatically eligible for a new dependency. Private instruction revision consumers retain the existing separate #42 branch unchanged.
- **Owner pointer insertion/change:** chat snapshot owner must equal NEW.id, with workspace/actor/thread and context checks retained. On a changed checkpoint pointer, validate new snapshot's current selected-ancestry/source/group scope and generation binding; reject sibling execution checkpoints even if their actor/thread match. For an unchanged pointer, check only immutable owner/structural identity and nonregressing version, without reevaluating live ancestry, call result validity or source state.
- **Historical lifecycle:** native finalize/fail/source deletion/revocation does not fire new cross-row validation on retained snapshots, uses or coverage. Snapshot invalidation/erasure retains its immutable generation identity; lifecycle-only snapshot UPDATE does not invoke live admission predicates. Ordinary owner state/lease/accounting UPDATE with the same checkpoint must preserve last-good history, including when snapshot.context_version < owner.context_version. Historical identity lookup remains usable after finalization; fresh capture/read/send/new dependency still requires current application authority.

The existing immutable coverage rule remains; direct INSERT attempts into an old snapshot still undergo full exact-owner scope plus immutable canonical-manifest validation and cannot append hidden dependencies. No xmin/transaction-age exception, UPDATE no-op bypass or disabling trigger is introduced.

## 4. Transaction and lock boundary

All helpers and deferred checks use read-only SELECT/recursive CTEs without FOR UPDATE/SHARE, advisory locks, implicit writes or native-root reacquisition. They execute within the existing single snapshot+coverage+uses+native-pointer CAS transaction after application NOWAIT guards. No new native writer hook, reverse-root lock edge, independent summary head or trigger revision write. C1 registration FK prelocks are a separate application correction; this amendment does not authorize trigger-based root locking.

## 5. Exclusive affected files and required proof

Upon exact approval only: new u5 migration consistency functions/downgrade signatures, neutral repository/journal/rendering validation as already owned, dedicated compaction constraint/schema/repository tests and lane evidence. No old migration, #42 memory.py contract, router, native service or shared CI edit.

Required real migrated PostgreSQL cases, with valid independently recomputed coverage hashes so digest errors cannot mask scope failures:

1. Same-thread sibling source registered under sibling execution: service read rejection and direct SQL snapshot+coverage+uses+matching pointer rejection. Exact selected older-sibling/root-edit lawful ancestry remains positive.
2. Same-actor/same-thread foreign-execution complete tool group rejection in coverage and direct use; same-execution group positive. Raw group dependencies cannot add sibling sources.
3. Foreign-execution parent snapshot, used_snapshot_id, call consumer source/use and pointer target all reject. Null or wrong generation binding rejects; exact persisted call owner survives two pointer advances.
4. Native finalize/fail, source revoke/delete and snapshot invalidation/erasure preserve historical identity and last-good pointer semantics; fresh dependency/adoption/read/send fails when authority is lost. Unchanged-pointer native/accounting updates do not revalidate stale ancestry.
5. Raw source/group/direct-use mutations, cycle/missing/foreign ancestry and depth overflow fail closed. Existing private-input exclusions, Research same-step frozen scope, canonical manifest, populated migration/catalog/downgrade and transaction rollback tests remain green. Observe no reverse-root acquisitions or native writer cycle from deferred checks.

No implementation or full-core acceptance is claimed by this proposed amendment. F43-C1/C2 and approved B34 implementation may proceed independently while these SQL predicates remain frozen.
