# #42 shared history, exact sources and index — independent Critical design review

**Current verdict: ACCEPT the exact pure-history implementation files pinned in section 10, under the explicit real-policy dependency/test boundary. Design 2befea01 and SS03 remain closed. Native source/DB/archive/dispatch/API/UI integration and CI collection are not accepted by this verdict; #43 core remains outside it.**
Date: 2026-09-28.
Reviewer: original replacement #42 Critical reviewer.
Candidate: specs/v5/memory-management/lanes/issue42-shared-sources.md.
Candidate SHA-256: deec2cf73e2b65b9048f996c2fea283fdba2178affabf1f59f5a3817c86507d2.
#42 HEAD inspected: 893de951672f1a374d552425dfb2b3e7c3e6a223.

The initial reviews below are retained as history. Section 9 records approved design; section 10 records the current bounded pure-implementation disposition.

## 1. Governing goal and evidence scope

Deliver authorized discovery and exact version/range reads of real shared native history, with no private-memory injection, no inferred attribution/confirmation, no stale source revival, and no bypass of direct summary/checkpoint/result dependencies. Spec v4/A1 choice2 and full design remain authoritative. Existing P1a/admission acceptance is unchanged.

This is a design review grounded in source inspection, not runtime/PG/API/model acceptance. Read #43's active worktree without modifying it. Its code is an integration baseline observation, not accepted functionality. No blanket dependency on #40 is introduced.

Authority hashes:
- spec.md: a15b1b55e2542b01455b47b67508cffd673dd532dab2932702ad771b08a1fe85.
- design.md: 828effb02b5fbf9818604e35ea13662814e12ccc605b704dd895fd7bbafe6236.

## 2. Native grounding and decisions retained

Verified the named native models and their actual read paths:

- ChatMessage has content, role/status, parent/thread/workspace IDs and no author column. ChatThread creator is not message authorship. Chat/notes routers authorize workspace reads; creator-only thread archive permission does not establish private read ownership.
- Note.body_md is the original body; updated_at is application-maintained DateTime, with no native monotonic note revision. NoteSource separately retains locator/asset/citation and excerpt provenance; it must not be silently treated as proof of the author's proposition.
- ContentUnit.text_content is normalized unit text. char_start/end locate it within its representation. Asset readiness/generation/index and AssetRepresentation.generator_version exist as described.
- ResearchArtifact has producing run/step/attempt, visibility, retention, hash/size/object identity. research_views.artifact_detail validates native producing/prompt/workflow chains; verified_artifact_bytes downloads and verifies actual bytes. These helpers do not themselves provide the proposed body-free dependency proof.
- Existing services.chat.active_message_path selects whole ChatMessage rows. services.notes.get_note and related DTO construction load whole Note/body and provenance rows. Those helpers cannot be reused as pre-hydration metadata inspection.
- #43 owns register_source/read_registered, ContextOwner/CapturedContext and source-bearing journal/coverage uses. Its source eligibility is task-specific, not a public history authorizer.

**Sound decisions retained:** exact whole-text UTF-8 hashes, code-point ranges, BOM/newline/Unicode preservation; current-version-only reads when old native bytes do not exist; no invented author; no fake asset/unit; no artifact-to-evidence promotion; all-output-reader proof including future workspace members; no body/title/snippet/vector/count output on denial; no object fetch before proof; no copied private-owner authority.

Shared search_memory's explicit excluded/empty union is truthful under A1 and acceptable in principle. It must still validate caller/task scope and perform zero private revision reads. No owner exception.

## 3. Required bounded corrections

### SS01 — pin a real owner/snapshot-to-history seam before adding generic ports

**Priority P1. Target: candidate §§3–4, 10 (lines 43–65, 158–171).**

HistoryAccess is currently a set of proposed fields plus opaque proof/metadata parameters spread across four new port families. There is no concrete constructor from an existing owner/snapshot, finite supported reader-policy representation, proof lifetime/transaction binding, or precise frozen-history scope representation.

The inspected #43 ContextOwner is workspace/actor/kind/owner_id/lease; CapturedContext binds native context/checkpoint versions, policy fingerprint and native manifest. NativeGuard._chat binds ancestry and branch stamps; _research binds run/step/attempt/execution/plan and lease. None currently issues the proposed HistoryAccess/proof. A caller-created server dataclass is not itself evidence that these facts were checked.

There is also a concrete downstream incompatibility: #43 sources.native_source/read_registered accepts only ancestry chat_message or frozen research_evidence. u5 compaction_source_scope permits chat sources only for the consumer's same thread, and Research sources only for its frozen attempt. compaction_use_scope applies that predicate to journal uses. A note ref, a chat ref discovered in another thread, or ordinary workspace history for a Research task is rejected by these consumers. Extracting the registry allocator alone does not make the promised history/tool path coherent.

**Correction:**
1. Define one narrow owner-issued history capture using actual #43 identities/versions and a concrete standalone management variant. Enumerate supported reader policies and exact comparisons; unknown policy remains denied. Do not duplicate lease/journal/checkpoint ownership or use private management AccessPort as shared authority.
2. Specify metadata projections, dependency metadata, transaction/lock ownership and the non-transferable validity of the proof through hydrate/search return. State the actual SQL authorization barrier/authorized-ID materialization before indexed text scoring; a prose JOIN/filter requirement alone does not define evaluation order or prevent late filtering.
3. Have the existing #43 owner define the common registry extraction and explicit tool-result/direct-use adoption seam. Preserve internal failed-message and frozen-evidence behavior; do not widen compaction_source_scope to every workspace source merely to make inserts pass.
4. Defer the proposed generic HistoryAudiencePort/DependencyPort/etc. until this real consumer contract is pinned. Pure range/DTO experiments may be isolated, but a repository driven only by new permissive test ports is not a completed usable history slice.

**Closure oracle:** pinned owner factory/contract and call sequence from native owner through metadata proof, body hydration, source registration, journal dependency and dispatch/adoption; requester-readable but destination-denied source performs no body/object/index-text load or protected metadata output. Test note and cross-thread-history consumption without broadening Research evidence authority.

### SS02 — specify the native-version and derived-consumer invalidation transaction

**Priority P1. Target: candidate §§5, 8, 10–11 (lines 82, 130–142).**

The draft requires native/source changes to commit together and says #43 owns reverse fanout. It does not yet define the executable handoff for a note/chat mutation to invalidate journal results, summaries/checkpoints and in-flight adoption, nor its replayable cleanup disposition. Clearing index rows alone is not that handoff.

Actual note updated_at/bodySha256 can return to the same tuple under direct SQL; it is not an ABA clock. #43 chat stamps cover more mutations than the draft's first-slice trigger list, including role and workspace/thread identity. Current registry replay rejects a known non-current version; it does not specify the proposed note-version allocator. Retained stale/deleted source identities and their graph references must prevent revival rather than allow a restored tuple to reactivate an old ref.

**Correction:** supply a small native event/state matrix, not another generic lifecycle framework:
- Each relevant chat/note body, eligibility, scope/identity, archive/restore and deletion event: which source versions become stale/unavailable/deleted, which manifests retire, which direct/transitive consumers are suppressed, and the exact #43-owned transaction/handoff responsible.
- Note version allocation, replay, A→B→A, delete/reinsert and source-tombstone retention/purge rules. Old references stay unavailable even if bytes and timestamp are restored; a fresh current registration has a new identity/version as defined. Never mutate a stale source back to current.
- Before granting index activation, identify the exact native mutation entry points receiving root guards and how direct SQL is handled without reversing workspace/native/source lock order. The existing statement that row triggers alone cannot establish the order is correct.
- On erase, delete every indexed text/vector generation, retain reference-safe identities, suppress affected summaries/checkpoints/tool results, and enumerate remaining content-bearing derived JSON/objects under design §5.5. Separate immediate suppression from cleanup completion. Preserve direct edges even when raw leaves survive.
- Clarify required dependencies for first-slice notes/chat, including how NoteSource or message evidence links are treated. Artifact per-kind mapping can remain a separate activation gate. Private memory conditions/revisions remain excluded entirely from these shared sources; future direct-revision consumption must not be implied by #43's currently narrower graph.

The draft correctly recognizes the tombstone CHECK conflict and the need for a joint #43 schema review; retain that requirement rather than issuing incompatible hash-null updates.

**Closure oracle:** direct-SQL and service mutation tests, same-timestamp A→B→A, archive/restore/delete/reinsert, register/build/adoption races, all-generation erase, and source change with a surviving independently readable raw leaf. Observe old consumer suppression and no later resurrection/cleanup loss. No native archive deletion is authorized.

### SS03 — reconcile manifest corpus identity with its uniqueness and completeness claims

**Priority P1. Target: candidate §§7–8 (lines 105–128), §9.**

The manifest has one active generation per workspace/audience/source_kind and no task/branch/history-policy scope key. The build instead selects the complete eligible set for “the declared scope,” while queries may have different branch/frozen envelopes. Those are different corpus identities.

For example, a current-branch chat build can legally contain only branch A under the prose, yet occupy the only active workspace chat generation. A workspace_history caller cannot treat that as complete, and a branch B build replaces A under the proposed unique key. Returning index_not_ready on mismatch avoids stale output but does not provide a coherent independently usable repository.

**Correction:** choose and state one corpus identity. The smallest fit with the proposed key is a workspace/kind shared-native corpus, built under an explicit workspace-wide indexing authority, with task/branch authorization applied independently before scoring. If builds are genuinely policy/task-scoped, the manifest key, immutable policy identity and activation rules must encode that distinction. Do not silently let requester permissions define a workspace-wide manifest.

Define completeness/freshness validation against that same corpus, and the authorized projection exposed in items/counts/truncated/generation/cursors. Specify how denied/out-of-envelope sources affect readiness and generation metadata; do not claim no denied-data signal merely because excerpts were filtered.

**Closure oracle:** concurrent branch A, branch B and workspace-history queries/builds; unknown-thread discovery; complete empty corpus; source insertion; different frozen Research allowances; inaccessible-source/count controls. One scope's activation cannot masquerade as another's complete history.

### SS04 — bind the exact range/page budget to the real counting contract

**Priority P2, required before implementing public range/cursor contract. Target: candidate §5 line 75 and §9.**

The accepted TokenCounter is count(GenerationRequest, ModelConnectionSnapshot) -> TokenCount, including exact/estimated mode and counter/config fingerprints. It is not a text-only callable. The draft requires <=2000 tokens through that accepted port but supplies no concrete request framing, connection/model snapshot owner or treatment of estimated counts. Requiring an unavailable counter to fail is sound; it does not resolve this mismatch.

The page window also needs one explicit definition: how before/after expands an explicit span once, what span=null means, the terminal range for continuation, and behavior for an empty original or inability to fit a nonempty unit. “All pages reproduce the full original” is true for a whole-source selection; an explicit bounded span should reproduce its selected/expanded window.

**Correction:** pin a narrow adapter to the real counting owner/snapshot and framing, budget mode, bounded local/no-network policy, and cursor binding to counter/profile/window/end. Do not add a generic counting port or fake provider credentials. No silent estimates, prefix truncation or repeated context expansion on later pages. Define a progress-or-explicit-error rule.

**Closure oracle:** long original, astral characters, combining marks, BOM/CRLF, exact whole-byte hash, clipped before/after, one-unit-over-budget, counter/config change between pages and empty original. Concatenation equals the requested exact window, with no gaps/duplicates or cross-version expansion. Deterministic test counters remain explicitly test evidence.

## 4. Schema/API deltas and staged scope disposition

| Proposed change | Disposition |
|---|---|
| SourceReference reuse, SourceSelection wrapper, returnedRange, code-point offsets | Sound direction; public range/count contract needs SS04. Do not duplicate the existing triple or serializer. |
| New note/content_unit/research_artifact source kinds and tombstone CHECK branch | Requires the named source-owner/persistence integration and SS01–SS02; not approved merely by listing enums. No edits to shipped t4 or active u5 from this lane. |
| Source-only first index, lexical_ready, nullable vector tuple in lexical mode | Acceptable staged design in principle. Original revision-target/memory_text design is deferred, not deleted. No schema implementation grant until SS03 is resolved. |
| Manifest FK, source FK, exact chunk hash/offsets, non-null-safe partial uniqueness | Appropriate constraints; migration must use existing ID types/composite keys, legal state transitions and service-verified exact slices. Populated upgrade/guarded down/direct-SQL evidence still required. |
| Lexical mode, generation map, searched sourceKinds, excluded search_memory union | Truthful additive response deltas in principle; serialize with actual API/contract owner and frozen scope. No hard-coded hybrid claim or silent fallback. |
| FTS + trigram + RRF first, hybrid later | Coherent no-spend staging. Hybrid embeddings, compatibility, budget/cancellation, real ranking and relevance remain explicit unfulfilled full-scope gates. Synthetic vectors do not close them; paid work needs later authorization. |
| Unit/artifact adapters gated separately | Acceptable staging if sourceKinds/mode/error outputs disclose what was searched. Per-kind producing/frozen/dependency proof precedes enablement; native API helper availability is not acceptance. |

Do not remove the original full #41 v4 source kinds/hybrid/direct-dependency/management retrieval obligations from delivery tracking when the lexical subset lands. No exact source read, lexical SQL pass or no-paid fixture is a model-quality/hybrid acceptance substitute.

## 5. Minimal coherent implementation sequence after correction/grants

1. Pin the narrow existing-owner history capture, supported reader predicates and canonical reference serialization; #43 owner specifies/extracts its single registration implementation and compatible result-use seam.
2. Implement chat/note metadata projections and exact reads with real transaction-bound authorization, version/invalidation behavior and source-state/schema delta. Test this against native rows, including denied-body spies and ABA controls.
3. Add the two shared index tables and lexical activation/search for the precisely defined corpus, with native mutation guards/triggers and #43 suppression/adoption integration. Keep all activation paths disabled until these dependencies are coherent.
4. API/tool owner mounts the accepted contracts only after exact integration. Other-kind adapters and hybrid remain separately owned mandatory later gates.

Pure range/hash/Unicode functions and synthetic design fixtures can be prepared without unrelated #40 changes. This does not authorize four generic ports or a parallel source allocator ahead of steps 1–2. No tasks/checkpoint/journal redesign is requested.

## 6. Read-only #43 evidence identity

The candidate's §13 pins became stale in three files while #43 continued working. This is an observation, not a defect in #43. The later inspected identities below ground this review; re-pin the seam with that owner before implementation.

| Relative path in issue43-compaction | Observed SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/compaction.py | d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b |
| packages/memory-service/src/citeframe_memory/compaction/sources.py | d783d49f377459fd5a1b9ddd544562ea1dc5741947df24642ae882a35af5a66e |
| packages/memory-service/src/citeframe_memory/compaction/guards.py | 969c91cbd30429d5ff89f850b1cfb5d35986c4aedc35e14192094323a8aee7d2 |
| packages/memory-service/src/citeframe_memory/compaction/repository.py | 38ec20ba9d0d0707218dad8849de37300cee5025897c64bf47e0240f6235ecd6 |
| apps/api/alembic/versions/u5c6d7e8f9a0_inloop_compaction.py | 21fe3e52a3984628f02b37918b2ebfb3c103297c13038204714cd70f99883469 |

Concrete inspection anchors: repository.register_source line 108, _validate_units 146, _capture 188; sources.native_source line 10/read_registered 50; NativeGuard line 48, chat/research guards 74/141; migration compaction_source_scope line 262/compaction_use_scope 340. Existing use-scope predicates must not be assumed to accept new public history references.

## 7. Handoff and evidence limits

Return SS01–SS04 to the original design owner for bounded correction and explicit owner/persistence grants. Pre-hydration authorization and no-private-data principles are retained; exact implementation contract is not yet approved. Existing #42 P1a/admission acceptance stands. This review does not accept or block unrelated #43 work.

No product/test/schema/API/CI file changed; no database/runtime/model/provider execution or Git write. Only this new review was written. Durable write-back is confined here, with no private/global memory or canonical #40 workbench change.


## 8. Targeted SS01–SS04 recheck — 2026-09-28

**Reviewed exact revised SHA-256: 98fb0e0823b81aac0bda2f26e03de1ff6d702fe1ec59043911fc841ba87860b5.**
**Verdict: REQUEST_CHANGES for the residual items below.** This judges the revised artifact itself; no closure is inferred from a handoff summary. The new concrete issuer, source-use seam, workspace corpus and event matrix materially address the original findings. No request to repeat the architecture review or wait on unrelated #40 work.

### 8.1 Disposition of the original findings

| Finding | Current disposition |
|---|---|
| SS01 native issuer/consumer seam | **Substantially resolved at design level.** Transaction-local HistorySession, existing ContextOwner/NativeGuard, frozen owner policy and explicit archive/capture/journal/use-predicate responsibilities replace the speculative generic proof ports. #43 approval remains a real pending owner grant. Pin the strict policy-version/zero-result compatibility details in SS01-R below. |
| SS02 versions/invalidation | **Substantially resolved at design level.** Global noncycling note stamps, same-timestamp ABA, archive/restore fresh stamps, all-version tombstones and transaction-wide reverse closure are explicit. Correct the actual SQL baseline and absent-column assumptions in SS02-R before authorizing the successor migration. |
| SS03 corpus identity | **Design CLOSED.** The manifest now represents a workspace/kind corpus; maintenance enumeration is distinct from task query projection. Branches cannot replace the workspace corpus. Runtime authorization-before-scoring, completeness and denied-output tests remain mandatory. |
| SS04 range/counting | **Partially resolved; still blocking usable task continuation.** The fixed expanded window, code-point boundaries, exact framing, CounterIdentity, reported estimates and progress/error rule are useful. Binding the cursor to the complete current base request and restarting on any change prevents ordinary multi-turn tool pagination; see SS04-R. |

The lexical-only response, source-only first schema and policy-excluded search_memory union remain acceptable staged deltas in principle. Full workspace discovery, notes/units/artifacts, original exact reads, hybrid retrieval and required dependency/erasure behavior remain outstanding full-scope obligations. No new native audience or private task mode is authorized.

### 8.2 SS01-R — declare strict policy-version compatibility and legitimate empty tool results

**P1 for task-tool activation; target §§4.1–4.2, 10.**

The concrete task owner is now specified. Two existing interfaces still require explicit finite changes:

1. Current repository.validate_runtime_policy requires exactly schemaVersion/maxCalls/maxInputTokens/maxOutputTokens/maxSummaryCalls/maxEpisodes/deadlineAt with schemaVersion=compaction-policy-v1. It rejects any extra key. The proposed nested history object needs a named key, versioned strict parent-policy shape and owner-authored validation/hash changes. State how old v1 tasks continue compaction while history tools stay disabled, and how retries inherit the new immutable history policy. Do not weaken validation to arbitrary JSON or default missing history to a grant.
2. Current ToolArchive.persist rejects not sources. A legitimate empty history search, or policy-excluded shared search_memory, has no source refs. Explicitly permit that authorized complete result without inventing a source/evidence edge. Retain native owner/policy/capture validation, full assistant-call/result pairing and direct tool-group dependencies. Specify the durable empty/excluded disposition so absence of refs cannot be interpreted as bypassing authorization.

**Closure:** strict old/new policy fixtures (unknown keys and malformed history denied), retry/hash parity, and a zero-hit/excluded complete tool result that can be archived/replayed/adopted under its native owner with zero private-body reads. These are narrow changes in the named #43-owned files, not a new port or registry.

Independent read-only probe executed the actual extracted validate_runtime_policy AST: existing v1 passed; adding a historyPolicy member failed invalid_runtime_policy. The current archive guard was inspected directly. These are interface checks, not runtime acceptance of the proposed design.

### 8.3 SS02-R — correct the SQL baseline and restrict closure to actual graph targets

**P2, required before the SQL implementation grant; target §8.3.**

The draft states compaction_snapshot_complete currently runs even on a snapshot status update. In the pinned u5 file it is installed AFTER INSERT ON task_memory_snapshots, and separately AFTER INSERT OR UPDATE OR DELETE ON task_memory_coverage. A status-only snapshot UPDATE with untouched coverage does not invoke it. compaction_snapshot_immutable already permits the narrowly shaped invalidated/erased transition and prevents revival.

Correct this baseline and name only changes actually needed for history-edge validation and suppression. Do not broaden triggers or weaken committed adoption checks to resolve a nonexistent status-update invocation. Preserve the deferred case: a newly inserted snapshot and source invalidation in the same transaction may still have a queued completeness check, which requires a deliberate tested disposition.

The inspected graph also adds used_snapshot_id and used_tool_call_id, not used_revision_id or observed_head_version. The proposed closure currently names used_revision_id while later explicitly excluding private revision dependencies. Define closure over the actual activated source/snapshot/tool-result graph. Keep future direct-revision/head-mode support in the full-scope ledger; do not add an unused column/framework merely to make pseudocode executable.

**Closure:** corrected trigger/event description; exact activated closure targets; status-only invalidation and erasure succeed while source tombstones persist; queued same-transaction insert/invalidation is deterministic; invalid new coverage still fails; no revival or direct-edge loss. The note/chat stamp and source-retention design otherwise addresses the original ABA concern.

### 8.4 SS04-R — current-request hash binding makes normal next-page tool calls restart

**P1, usable exact-source pagination blocker; target §5 paragraphs on countingProfileSha256/change handling.**

The revised cursor binds the actual base request hash/framing. Any changed framing returns source_context_conflict and requires a new first-page read. Normal task pagination necessarily changes that request:

1. Tool call C1 reads page one under request R1.
2. The assistant receives its result, then issues tool call C2 with nextCursor.
3. R2 includes C1's result and the new tool-call identity/framing; it differs from R1 even if source, policy, model and counter are unchanged.
4. The specified equality gate rejects the continuation and sends the caller back to page one.

Idempotent replay of the unchanged first call or a fixed management template does not demonstrate model-tool continuation beyond the first page. This is a consequence of the pinned contract, not an inferred implementation defect.

**Correction:** separate stable cursor authority/window from per-dispatch budgeting. Keep actor/workspace/native owner, frozen policy, exact source/hash/range, terminal window, offsets, expiry and chosen model/counter capability identity pinned. Reissue authorization and recount each continuation against its actual current complete request and remaining capacity. Record the current request hash in that call's capture/journal, rather than requiring equality with the previous page's base request. If the owner requires a different logical-pagination mechanism, specify how ordinary C1→C2 advancement works without resetting the selected window or suppressing current-request capacity checks.

**Closure:** two or more sequential read_source tool calls with different legitimate call IDs and growing history return strictly advancing ranges whose concatenation exactly equals the fixed window. Test mutation, owner/policy/profile drift and tampering separately. On smaller current capacity, return a fitting nonempty next page or explicit capacity error without reauthorizing a broader window. No paid provider needed; use complete request fixtures and the declared deterministic counter.

### 8.5 Smallest usable native-chat-only slice — full registry extraction not required

A bounded **current-branch, completed-chat exact-source slice** can precede cross-thread/note adoption. It does not need the proposed common registry extraction, note stamp, Research history-policy fields or widened source-kind/use predicates:

- Use existing ContextOwner, NativeGuard, SourceReference and the existing chat registration/read implementation owned by #43. Prefer refs already registered for the captured branch; any trusted native-ID registration still goes through existing register_source.
- Add only an owner-authored current-branch/public-completed eligibility projection in the same guarded transaction before body load. An after-read completed-status filter is insufficient because internal native_source deliberately also permits failed messages.
- Wrap exact native text with the approved provenance, fixed window/continuation and corrected SS04-R counting behavior. Retain unknown actor and null confirmation.
- Feed source-bearing complete tool-group results through the existing same-ancestry archive/use path and its direct dependency chain. The empty-result correction is needed if search/excluded tools are enabled. No new history-v1 cross-scope authority is needed solely to read already permitted ancestry.
- Keep source mutation/dispatch/replay guards and required suppression/erasure acceptance in the slice's activation gate. Reusing an unfinished owner module is not acceptance of its runtime behavior.

The smallest demonstrable deliverable is an actual long completed ancestor read across multiple pages under a real native execution, with denied/sibling/private cases excluded before hydration and existing archive/checkpoint/CAS regressions retained. If current-branch lexical discovery is included, label its ancestry-only corpus explicitly and use real guarded native predicates; do not claim workspace manifest/index or unknown-thread discovery completion.

This is an explicit staged alternative, not a silent replacement of the proposed workspace-history/index outcome. Cross-thread chat and notes still need the newly described consumer seam and corpus integration. The original unit/artifact/hybrid and full #41 v4 obligations remain. Controller must choose/grant this bounded stage; this review does not independently authorize product writes or change the final target.

### 8.6 Evidence, owner gate and write-back

All eight #43 hashes in the revised §13 matched the read-only files at recheck, including policy.py, archive.py, journal.py and the u5 migration. The earlier observed source/registry constraints therefore remain the actual baseline for these residual findings. No #43 file was changed.

The candidate hash was verified before writing this addendum. #43 owner approval is still pending; an accepted design would not itself grant those shared-file changes. No database, API/UI, model/provider or integration acceptance is claimed. Only this existing review artifact was updated; no product/test/schema/Git or global/private-memory writes.


## 9. SS01-R / SS02-R / SS04-R 实物重审 — 2026-09-28

**结论：APPROVE，本轮三项修订在设计范围关闭；没有剩余的设计阻断项。**

候选：`specs/v5/memory-management/lanes/issue42-shared-sources.md`  
SHA-256：`2befea01c88ff5fc7d3f8f54c23c9f22b9bb850dd5619dbf819d1091dcf3c042`。

### 9.1 判定目标与边界

判定对象为可实施的严格策略兼容、合法空结果归档、先校验后失效以及正常多轮原文分页。接受标准仍为实际原文、原始版本/范围/来源、全输出读者授权与 A1 choice2；private memory 对 shared 路径保持零读取/零注入。SS03 保持 design CLOSED；P1a 和 admission 既有接受结论不变。未重新审计或接受完整 #42、#43、API、UI 或 #41。

已重新核对本树原 review、候选全文的相关段落、#43 实际 policy/source/archive/SQL 接口和当前所有权/interval/C3 文档。原始 spec/design 哈希仍与 §1 一致。结论依据实际候选，不推断开发者是否读过原 review 全文。

### 9.2 各项结论

| 项 | 结论 | 实物依据与保留条件 |
|---|---|---|
| SS01-R：strict v1/v2 | **Design CLOSED / pass** | 候选 53–62 行保留 v1 精确七键、五个严格正整数（拒绝 bool）、带时区 deadline、datetime 返回值以及原始 digest/capture/retry 身份；v1 多 history 键仍拒绝。v2 精确增加 history，enabled/disabled 为封闭形状，未知键/枚举/重复列表拒绝。旧任务只读推导 disabled，不改旧 policy/hash。Research 旧 snapshot 不因调用者提交 v2 而获得权限。原 #43 validator 当前仍只支持 v1，因此实现由其原 owner 负责。 |
| SS01-R：合法空结果 | **Design CLOSED / pass** | 87–100 行将 empty union 限定为可信 executor 验证的完整 zero_hits / policy_excluded 调用组，验证真实 call ID、顺序、canonical 结果、owner/lease/capture/policy。空原文 read 仍有真实 ref；混合组保留真实 refs 并集。不构造假 source 或 self-edge。零命中持有完整 corpus-generation 依赖，retirement 同事务失效组并传播真实 direct tool-group edges；excluded 不伪称查过 private corpus。空 refs 不免除 archive/capture/send/adopt 授权。 |
| SS02-R：真实触发时机和图 | **Design CLOSED / pass** | 214、219–225 行已准确区分 snapshot AFTER INSERT 与 coverage INSERT/UPDATE/DELETE；旧 snapshot status-only UPDATE 不触发 completeness。闭包仅使用实际 source / used_snapshot_id / used_tool_call_id，不新增不存在的 used_revision_id / observed_head_version。未批准未来 private-revision 图扩张。 |
| SS02-R：pending 校验屏障 | **Design CLOSED / pass，运行时范围见 §9.3** | 在原 native/source 状态尚存时触发 named SET CONSTRAINTS IMMEDIATE，先完成 queued adoption 检查再失效；无 invalidated/erased 跳过 completeness 分支，失败回滚全部原生变化。保持旧 identity/coverage/pointer 检查。此设计不能替代 #43 C3 的 exact execution owner / NULL-safe admission 修订。 |
| SS04-R：稳定 continuation | **Design CLOSED / pass** | 114–126、238 行将固定 source/window/nextStart/expiry/owner/frozen scope 与当前 dispatch 预算分开。每页真实 C2/R2 使用当前完整 GenerationRequest 和当前授权 connection/counter；不比较 page1 请求 hash。更小合法预算缩页或原 cursor 可重试，不能回到第一页、重复扩窗或返回非终止空页。每个实际请求单独计数、归档、journal hash 等值校验；sibling/framing 改变必须重新装配计数。 |

### 9.3 PostgreSQL 屏障：独立实测及精确适用范围

独立建立全新的 reviewer 专用临时 PostgreSQL **17.11** cluster，loopback 动态空闲端口；没有连接现有数据库，也没有使用开发者的 PG 结果作为本人证据。使用 API venv 的 Python `-B` + psycopg 3.3.4 运行机制级探针。仅测试 PostgreSQL 的 deferred-trigger 行为，**未安装或验收完整 P1a+#43 migration**。

最小复现结构：

```sql
CREATE TABLE native(id int PRIMARY KEY, live bool);
INSERT INTO native VALUES(1,true);
CREATE TABLE snap(id int PRIMARY KEY, good bool, status text DEFAULT 'valid');
CREATE TABLE checked(id int);
CREATE FUNCTION complete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF NOT NEW.good OR NOT (SELECT live FROM native WHERE id=1) THEN
    RAISE EXCEPTION 'invalid_snapshot';
  END IF;
  INSERT INTO checked VALUES(NEW.id);
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER snapshot_complete AFTER INSERT ON snap
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION complete();
CREATE FUNCTION barrier() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  SET CONSTRAINTS snapshot_complete IMMEDIATE;
  UPDATE snap SET status='invalidated';
  RETURN NEW;
END $$;
CREATE TRIGGER native_barrier BEFORE UPDATE ON native
  FOR EACH ROW EXECUTE FUNCTION barrier();
```

每例从空 snap/checked、live=true 开始。两个独立 statement 的事务：先 `INSERT INTO snap(id,good) VALUES(1,...)`，再 `UPDATE native SET live=false`。另用以下单 statement 对照：

```sql
WITH ins AS (
  INSERT INTO snap(id,good) VALUES(1,...) RETURNING id
)
UPDATE native SET live=false FROM ins WHERE native.id=ins.id;
```

实际输出：

| 探针 | 结果 |
|---|---|
| valid_prior_statement | COMMITTED；snap.status=invalidated，checked 恰有 id=1，证明 BEFORE trigger 可以执行 SET CONSTRAINTS 并先校验前序 statement 的 pending INSERT |
| invalid_prior_statement | REJECTED，SQLSTATE P0001 / invalid_snapshot；不能用后续 invalidation 洗掉坏 insert |
| valid_same_statement | REJECTED，P0001 / invalid_snapshot |
| invalid_same_statement | REJECTED，P0001 / invalid_snapshot |

**实现读法：**批准的成功路径为同一事务中的完整 adoption statement 序列（snapshot/coverage/uses/pointer 全部准备好），然后单独 mutation statement 的 pre-mutation barrier。当前 statement 自己产生的事件不能被宣传成已经由该屏障提前完整校验；上述 data-modifying CTE 不在成功承诺内，允许 fail closed。保留 end-of-statement/commit 检查，不能为使该 CTE 成功而增加 invalidated/erased 跳过条件。若 owner 后续要求支持同 statement adoption+mutation，须单独提出可验证事务方案。本轮未发现 malformed pending insert 可借此提交的证据；机制探针也不证明真实五类约束的全部安全性。

正式 migration/runtime gate 必须复现真实 snapshot+coverage+uses+native pointer 的 valid insert→invalidate、invalid insert→invalidate/erase、旧 snapshot suppression、SQL bypass、rollback 和 source/hash/owner/parent/coverage 全部负例；同时覆盖同 statement 拒绝。应用不得在屏障后重新开启 adoption。named constraints 与最终 owner 接受的 C3 定义一致，不能复用当前 thread-wide predicate 冒充 exact-owner 校验。

临时 cluster 已用其**自身** data directory 执行 `pg_ctl -m fast -w stop`，退出码 0；直接启动的 postgres process 退出码 0，无 reviewer server 留存。初次 pg_ctl start 因 restricted-token error 87 未启动；随后以隐藏窗口直接启动该同一专用 postgres 完成探针。没有停止其他 cluster。

### 9.4 模型/counter drift 与错误映射

本版不再把 model/counter fingerprint 放进稳定 cursor，本 reviewer 接受这一修订；§8.4 旧建议中的能力身份 pinning 由本节更新为**每次 dispatch 的可信策略验证**。这与 #43 interval amendment 的“旧 committed checkpoint 按原 provenance 验证，新的 main request 按当前 profile 计数”相容。

必须区分：

1. 下一页的合法 tool-call ID、request hash、prompt history 或已授权 profile/capacity 改变：继续同一 nextStart，按当前预算计数，不要求旧页 profile 相等。
2. 当前 TokenCount 返回的 counter identity 与当前可信 expected identity 不一致，或 connection config 不一致：当前页 fail closed，不产生新 archive/provider 效果；不能把模型提交的 identity 当成授权。
3. 同一个调用的 lost-ack/idempotent replay：保留它原来归档的完整页和 provenance，重新检查读权限。若之后放入新 dispatch，该新请求仍须按当前 profile 全量计数；replay 不提供新的预算通行证。
4. 同次待发送候选在计数后改变 sibling result/framing/profile：重新计数并保持 final request SHA 等值，不借稳定 cursor 绕过当前请求校验。

候选 242 行的简写 `source_context_conflict409 for changed framing/profile` 应按详细 §5 收窄：**不得用于合法跨页的当前 request/profile 更新**。可用于同次绑定不一致或稳定 authority/window 变化的相应冲突；当前 profile/counter 错误仍由真实 owner validator 判定。建议原文在下一次文档整理时注明这一限定，避免 API error mapping 恢复旧 SS04-R 行为。该简写不覆盖 118–126 行已经明确的正常 continuation 规则，不要求再次整体设计重审。

### 9.5 可并行实施的精确文件边界

下表为本轮接受的实施划分，供 controller 显式授予原开发。**review 的设计 APPROVE 不转移 #43 文件所有权。** 当前 #42 树尚无 #43 contracts/compaction.py 实物；controller 应先同步已批准的精确 contract 基线或安排只读测试依赖，不允许 #42 复制 SourceReference/TokenCounter 或补一个兼容占位类型。

#### A. #42 可先开的无重叠纯模块

- NEW `packages/memory-service/src/citeframe_memory/history/__init__.py`：最小 package 初始化，无自动激活。
- NEW `packages/memory-service/src/citeframe_memory/history/ranges.py`：只处理原文 code-point selection、一次扩窗、固定 terminal window、页进度与实际 request/counter 预算适配。不得实现 #43 的 checkpoint interval renderer；不得复制 policy.count_request/capacity_for 或 source allocator。
- NEW `packages/memory-service/src/citeframe_memory/history/search.py`：严格查询解析及 corpus→query projection 的纯逻辑；没有 issuer 前不添加真实 DB hydration、tool registration 或管理 API mount。
- NEW `packages/backend-contracts/src/citeframe_contracts/history.py`：SourceSelection、query/page、history-policy 的严格 shape，复用现有 canonical SourceReference 和 memory contract。这个新增文件可独立写，现有 `__init__.py` export 由 controller 单独串行授予。
- NEW `packages/memory-service/tests/test_history_sources.py`：对应 Unicode/精确范围、v1/v2 policy shape、正常 C1→C2 continuation、当前 counter/profile mismatch、缩页/无进展等 deterministic tests；模拟数据只证明纯行为，不声称 native issuer 或真实任务已可用。

`history/resolvers.py` 与 `history/index.py` 保留为候选中已命名的后续实现文件；issuer/common-registry 和 schema handoff 明确后再开启，避免先造可构造 authority DTO、通用 ports 或第二套 source 逻辑。`test_history_index_postgres.py` 随真实 index schema 再实施。无需等待 #40、完整 #43 或 paid model 工作才开始上述纯模块。

#### B. 最小可用 current-branch completed-chat 原文子集

controller 可单独选择此 milestone；不需要提前抽取整个 registry，不需要 note stamp、workspace index、Research policy 新字段或新的跨 scope SQL use predicate。

#43 必要 narrow grant 由其原 owner 承接，并串行接在正在进行的 interval/C1/C2 改动上：

- `packages/memory-service/src/citeframe_memory/compaction/repository.py`：strict v1/v2 validator、trusted task policy 与 history entry/capture 边界，使用既有 register_source，不复制其 lookup/stale/insert。
- `.../compaction/guards.py` 或 owner 选择的 NEW `.../compaction/history_guard.py`（二选一，避免双 issuer），及 `.../compaction/sources.py`：真实 native transaction 内先查 metadata 的 public completed-only/current-branch eligibility，再读取正文；内部 compaction 的 failed-message 规则不改。
- `.../compaction/archive.py`：真实 complete tool group/paging provenance；仅在启用 search/excluded 工具时加入上述 narrow empty-result union。archive 的 pre/post/read checks 不能以空 refs 跳过。
- `.../compaction/journal.py`：当前完整 dispatch request/count/hash 绑定与正常 replay；沿用 owner 的 B34/C1/C2 实现，#42 不另建 journal。具体 request composition 若需触及 `requests.py`，仍由 #43 原 owner 修改，不能转为 #42 的平行 writer。

#42 的新增 `history/resolvers.py` 只调用该 owner 给出的实际 seam 并构造原文 response，不拥有 registry/native-source 实现。NEW `packages/memory-service/tests/test_history_sources_postgres.py` 可作为这一最小 native milestone 的专有测试文件；不要改写 #43 现有 compaction tests 或 CI。正式启用须有 real native execution 的长 completed ancestor 连续分页、denied-before-body、siblings/private 拒绝、archive/replay/CAS 和 owner suppression 证据。当前 corpus/search 未启用时不需要先完成 zero-hit corpus retirement。

#### C. workspace history / notes / index 后续切片

- #42 NEW `history/resolvers.py`、`history/index.py`、`tests/test_history_index_postgres.py`，以及 NEW `packages/backend-persistence/src/citeframe_persistence/models/memory_index.py`，仅在相应 grant 与实际 issuer/schema contract 就绪后实施。
- #43 原 owner 负责 §4.2 的 `_register_exact` 提取、跨 scope source predicate、archive/capture/adopt/use/journal delta；这些全部在其已有 files 上串行，不能让 #42 用新 parallel module 接管 source registry。
- NEW `apps/api/alembic/versions/<controller分配的唯一successor>.py` 及现有 model/export 的修改必须由 controller 单独给 exact filename 和 predecessor。#42 不编辑 shipped t4，也不编辑 #43 正在施工的 u5。此刻不虚构 migration revision ID 或 second head。
- `models/memory.py`、`models/note.py`、model exports 和 native mutation hooks/stamp transition 为明确的后续联合 grant：#43 批准 scope/use/barrier/closure predicate 语义，native owners 批准写入/锁序/触发器；其前置仅阻挡这一集成部分。
- Research immutable history-policy fields/hash、新规划 issuer、asset/unit/artifact resolver、API/BFF/tool composition 分别归原生/API owner；不并入当前纯模块 grant。真实 hybrid、原始 unit/artifact 与全 v4 scope 继续保留，lexical/chat 子集不替代最终范围。

#43 保留当前 `compaction/{gate,packing,rendering,requests,summary,repository,journal}.py` 的 interval/C1/C2 单一所有权；C3 migration/predicate 仍由 #43 原开发与原 reviewer 负责。#42 不新增 generic ports、复制 interval renderer 或修改其测试来换取集成通过。

### 9.6 #43 当前证据身份与未接受范围

本轮读到了 #43 原 review 中 **C3 exact design APPROVE** 的新段落，指向 `69a7115ea197c780345285e0611f5e2488c2ad86c96d788292b9393b6974fc92`；该段同样明确 F43-C3 implementation/runtime 未关闭。本 reviewer 仅记录已存在的独立设计结论，**不接受其 SQL 实现**。interval contract 哈希为 `b34deac14af9a7438e6453ebd46649b07f18b5ef8904bb43ab2ba63b092bd736`。两者均不能据此推导 C1/C2、interval 实现或整个 #43 通过。

实际只读文件身份：

| #43 相对路径 | 本轮 SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/compaction.py | d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b |
| packages/memory-service/src/citeframe_memory/compaction/repository.py | 7e6c6e94b4ed9450ad7af52f542dc83132468dc4ada21a0d442701770981e8a7 |
| packages/memory-service/src/citeframe_memory/compaction/journal.py | f34eb52b22abd56127a536e83b8db00c7c4a60c01e2e67bc443e69afb72a04e6 |
| packages/memory-service/src/citeframe_memory/compaction/archive.py | 87bd63c47a8d3a9ebcd8b214f3004cc5ffe8ba4b040bcde2a957487e42d2d5e6 |
| packages/memory-service/src/citeframe_memory/compaction/sources.py | d783d49f377459fd5a1b9ddd544562ea1dc5741947df24642ae882a35af5a66e |
| packages/memory-service/src/citeframe_memory/compaction/guards.py | 969c91cbd30429d5ff89f850b1cfb5d35986c4aedc35e14192094323a8aee7d2 |
| packages/memory-service/src/citeframe_memory/compaction/policy.py | f992b4d5e0d512a6cae7756cab3ed0e33def8f178a4948c05a919dc9b2796b44 |
| apps/api/alembic/versions/u5c6d7e8f9a0_inloop_compaction.py | 21fe3e52a3984628f02b37918b2ebfb3c103297c13038204714cd70f99883469 |

repository/journal 已较候选 §13 的观察版本前进；这是并行开发身份记录，不是本轮对其改动的接受。集成前 owner 应固定实际 handoff 再运行各自 tests。

### 9.7 交付与 durable write-back

本轮只更新本 root review；未修改产品、测试、schema、CI、Git、候选 contract、private/global memory 或 canonical #40。临时 PG 仅为上述四例机制探针，已经停止。无付费/provider/model 调用。保存了原 review 历史；controller 可据本节原文向原开发授予非重叠纯文件并安排 #43 narrow handoff。后续只需审实际实现及对应 runtime gates，无需重复已关闭的设计架构审查。


## 10. Pure history 实现独立审查 — 2026-09-29

**结论：ACCEPT 下列精确 pure-slice 文件。未发现本轮实现范围内的阻断问题。**

批准设计 `2befea01c88ff5fc7d3f8f54c23c9f22b9bb850dd5619dbf819d1091dcf3c042` 保持不变；本轮没有重做设计。P1a/admission 既有接受结论保持。这里接受的是已供给正文上的范围/分页/计数候选，以及严格输入形状和纯查询投影；不接受 source hydration、授权、归档、数据库、真实 dispatch 或完整检索能力。

### 10.1 精确候选及实际依赖

| 本树文件 | SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/history.py | a771d0caf41ac0da307e1bb723da039aa2411f9cc35dd86e4c2ee460cf9d3c02 |
| packages/memory-service/src/citeframe_memory/history/__init__.py | 4c554257bcd2186adba89361614363bdc7ec92c969ccbb200e1ef6027a8dd3a0 |
| packages/memory-service/src/citeframe_memory/history/ranges.py | 65f068f1003692f0b30e4f7f0daa8c4ab3993b2f5fd44c6686163dca93669d08 |
| packages/memory-service/src/citeframe_memory/history/search.py | 1e399094f51ae3f4dcfd9c25474584ab85193ce745410fc836704a2433fa334f |
| packages/memory-service/tests/test_history_sources.py | 22ec11d67fe74a221b38dbed6a0a3d39fda538d5e1f7f09c66dd661f7883b944 |
| specs/v5/memory-management/evidence/issue42-history-pure-runtime.md | 0a834d7b597c485c002303fe078af26006a34fd8afa8a37b0d7e9952f80a71be |

本树 controller byte-copy 的 `packages/backend-contracts/src/citeframe_contracts/compaction.py` 实测仍为 `d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b`。SourceSelection 引用的 SourceReference 为该同一 class，无本地替身。

运行时只读依赖为：
`D:/Code/citeframe-lanes/issue43-compaction/packages/memory-service/src/citeframe_memory/compaction/policy.py`，SHA-256 `f992b4d5e0d512a6cae7756cab3ed0e33def8f178a4948c05a919dc9b2796b44`。

独立进程核对了实际 `policy.__file__`、文件 hash，以及 `ranges.count_request is policy.count_request`。加载相邻真实 `compaction/__init__.py`；没有安装 stub、复制 helper 或 fallback。当前本树缺少这些 owner43 policy/package 文件，因此这次证据是**显式提供真实 sibling 依赖的运行环境**，不证明当前 worktree 已可独立打包/import history.ranges。controller 后续必须通过真实 owner handoff 集成依赖。该 policy 函数的局部使用不接受正在返工的 #43 source/registry/journal/SQL 核心。

### 10.2 语义判定

| 检查 | 结果与依据 |
|---|---|
| Goal / scope | **pass**。所有 pure 模块明确没有 native authority、DB、hydration、registry、archive 或 activation。新增 SourcePage/HistoryQuery/HistoryPolicy 是数据形状；opaque binding、集合交集和 DTO 均不构成权限凭证。无 private-memory import/read 或 owner exception。 |
| 严格 parent/member shapes | **pass（shape scope）**。精确 v1/v2 key sets；v1 projection 为 disabled 且不改输入；v2 必须含严格 nested union。未知成员、重复/未知 scopes/kinds、错误 enabled 类型拒绝。`history_member_from_runtime_shape` 明确只投影 shape，不校验 parent budget/deadline scalar；实际 owner validator 仍必须运行。不能将该函数成功当作完整 runtime-policy 通过。 |
| Unicode / exact window | **pass**。完整 source UTF-8 SHA 核对，无 normalization；BOM、CRLF、astral、组合字符均按 Python code points 保留。一次 before/after 扩展，固定 end，续页 start 精确推进；空原文为单个空 terminal page，非空耗尽窗口拒绝。LocatorSpan 只接受 shape，未解析 locator 的 text-window 请求明确拒绝。 |
| Cursor | **pass（签名/数据范围）**。HMAC、canonical 编码、重复 JSON key 拒绝、版本/字段/expiry/binding/整数边界检查；cursor 不含请求/counter/profile 身份。保持原 expiry 和 selection/window，不重新扩窗。没有把 signer key 或 supplied binding 宣称为 native issuer。权限与请求 selection 冲突仍由未来真实入口验证。 |
| Complete-request counting | **pass（supplied request scope）**。检查目标 assistant/tool batch 的调用 ID、顺序、完整 sibling results；只替换目标 tool message。实际 count_request 分别计算完整 candidate 与同 envelope 的空内容 baseline。检查 full hard capacity、content delta≤2000、最大 16000 code points，当前 output reserve 与实际 physical capacity 使用 owner validate_capacity。调用方仍负责供给合法完整 request、可信 render、授权连接与配置 ceiling。 |
| 非单调 counter | **pass**。每次缩小候选均重新计算 candidate/baseline；不推断未计数前缀一定能装下。halving 为有界保守选择，不承诺最大可装前缀；发出的一定是已计数且满足两类预算的候选。原 6000→3000→1500→750 非单调 fixture 实际运行通过。 |
| 当前 profile / no progress | **pass**。C1→C2 可以改变 request/tool/profile，继续相同 nextStart；当前 identity 不一致拒绝。不能容纳一 code point 时抛稳定 capacity code，不修改输入 window/cursor，恢复预算后可重试。每页 request hash 独立，profile hash 不包含 api_key/endpoint。 |
| Query/projection | **pass（pure scope）**。query/limit/cursor/time/scope/kind 的有限严格解析，显式 disabled kind 拒绝，current_branch 只含 chat；只返回 supplied sets 的交集，不改变 corpus。没有 lexical SQL、rank、index completeness、ACL 或 denied-body 证明。 |
| 错误/副作用 | **pass（已实现边界）**。已测试的本模块 shape/range/cursor/capacity 和真实 policy identity 拒绝均为 payload-free codes；没有 logging、provider 或数据库副作用。任意外部 render/counter 抛错的清洗及最终 API mapping 不在此 slice 完成。 |

本轮没有将 fixture 的 `estimated` 或 `exact` mode 标签解释为真实 tokenizer 精度；这些都是明确声明的 deterministic counter 测试。

### 10.3 本 reviewer 独立执行

在本 worktree 执行以下命令；这是 reviewer 自行执行结果，区别于开发者 evidence 中的同名命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_HISTORY43_SOURCE_ROOT='D:/Code/citeframe-lanes/issue43-compaction/packages/memory-service/src/citeframe_memory'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest packages/memory-service/tests/test_history_sources.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_instruction_memory.py::test_validation_and_fail_closed packages/memory-service/tests/test_instruction_memory.py::test_neutral_import_without_application_packages -q -p no:cacheprovider
```

**实际结果：1647 passed in 3.36s，exit 0，零 skips。** 其中 42 个 history cases、1603 个既有 admission cases、2 个 P1a validation/import cases。没有重跑或重新接受 P1a PG/migration。

另在独立 `python -B -` 进程通过内存脚本做了 **42 项额外边界控制**，没有写入/修改测试文件。使用 `runpy.run_path('packages/memory-service/tests/test_history_sources.py')` 载入现有明确标注的 request/render/CharacterCounter fixtures，调用实际产品函数与上述真实 policy。输入/判定如下，可直接用这些参数重复：

- TokenCount 分别设 `tokens=-1/True/1.5`、错误 counter_id/version/mode/config_fingerprint：全部精确拒绝 `counter_changed_or_invalid`。
- page_token_limit 分别 `0/2001/True/1.5`；before 分别 `-1/2001/True/1.5`：全部 `invalid_history_range`。
- disabled history 多 sourceKinds、enabled=None、重复 scope、嵌套 list source kind：全部 `invalid_history_shape`。
- query 空/4001 chars，limit 0/21，cursor None/8193 chars，from 晚于 to：稳定 query/range 错误；4000-char query、limit=20 正例通过。
- 使用测试 HMAC key 重新签名 malformed payload：nextStart=-1/bodyEnd/True、bodyLength=-1、version=True、超 900 秒 expiry、反向 span、额外 payload 字段、duplicate version key：全部精确 `invalid_history_cursor`，错误不含注入的 sentinel 字符串。
- 独立长 Unicode fixture 为 `('\ufeff中😀e\u0301\r\n\t"\\\0' 的实际 Unicode 字符串)*950`；selection=[123,8000)，before=120，after=99。每页使用新的 tool ID、model、config_fingerprint、增长 prompt 与逐页减小的 context_window_tokens，page_token_limit=401；实际 **77 页**严格推进，拼接恰等于固定 [3,8099) 原文窗口。每页独立重算 canonical request hash、full count 与 delta，原 expiry 保持 900。
- `exact` 测试 counter mode 被原样保留，没有偷偷改成 estimated。
- 从实际 owner repository 只读提取当前 `validate_runtime_policy` AST 作函数探针：合法 v1 通过；maxCalls=True、maxInputTokens=0、无时区 deadline 分别被 owner 拒绝 `invalid_runtime_policy`。同三个输入的纯 history shape accessor 返回 disabled，验证了它明确声明的分工，不能当成完整 policy validator。这不评审或接受 owner repository 的其他实现，也不证明其 v2 尚未实施的行为。

额外进程实际输出：`INDEPENDENT_CONTROLS 42 PASS; changing-profile Unicode continuation pages 77`。77 为单个 continuation oracle 的页数，不是额外 pytest case 数。没有 native issuer、DB、archive、dispatch 或 provider 执行。

### 10.4 必须保留的交付门槛

1. **依赖与 CI 尚未闭合。** 本树 `.github/workflows/ci.yml:73` 的 memory-service 命令只列 instruction/admission/admission_postgres；`pytest.ini` 默认 testpaths 也不包含 memory-service history。当前 CI 不收集这 42 个新 history cases。controller 应在真实 owner43 policy/init 集成后，给原 CI owner 一个 narrow collection grant，明确加入 `packages/memory-service/tests/test_history_sources.py` 并在干净环境证明实际收集/运行；不能依赖某台机器的 sibling worktree 路径或以 skip/stub 消除缺失依赖。本 reviewer 不改 CI、不移交 #43 产品文件。
2. **真实 native 安全仍是 activation gate。** metadata authorization-before-BODY、全部输出读者、native frozen policy/current state、membership、source version、scope 和重新授权不在 pure 函数内实现。不能用这次 set-intersection 或 signed cursor 测试宣称通过。
3. **可信 composition / adoption 仍归 owner。** 实际 dispatcher 必须把该 candidate 的 exact rendered request、所有 sibling results、当前 counter/capacity 与 journal/request archive 对齐；最终 framing 变动要重新计数；lost-ack archive replay、CAS、invalidation/erasure 和 no-resurrection 需要真实 owner 路径证据。pure CountedPage 不授予 send 权限。
4. **完整检索未实现。** current-branch native resolver、workspace corpus/index、notes/units/artifacts、hybrid、真实 API/UI 与 full #41 继续保持未接受。C3/interval/C1/C2 当前实现返工不因本轮局部真实 policy 使用而关闭。SS03 的 design closure 与本次 pure projection acceptance 都不构成真实 index 验收。

本轮只更新原 `reviews/issue42-shared-sources.md`；候选、evidence、依赖 DTO、产品/tests/CI/Git 均未修改。未启动 PG，无数据库/provider/model/paid 调用。durable write-back 限于本 review，不写 private/global memory 或 canonical #40。
