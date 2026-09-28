# Issue44 chat-loop — independent bounded design review

Date: 2026-09-28
Disposition: **REQUEST CHANGES for the complete proposed runtime/SSE contract. ELIGIBLE for a smaller, controller-assigned pure terminal-turn/transition slice described below.** No schema, shared ABI, route, runner or public-stream implementation is approved by this review.

## 1. Governing outcome and exact candidate

Reviewed all sections of `lanes/issue44-chat-loop.md`, SHA-256 **6E1EFAEAEBC5FC8BEBA476308BE933D9E720DC1384D27E84BE5CA7BEF69F0E24**, without modifying it. Its recorded source baseline is fb78f83590cbe8a4944a01591922cc6162d27f5c; actual integrated inspection HEAD is **a139336e70086be72a49893c418ecd9730c5f56e**, incorporating accepted admission 893de951672f1a374d552425dfb2b3e7c3e6a223. That merge does not change the inspected legacy chat/SSE behavior or provider ABI.

Acceptance target remains Issue41 v4: one accepted question, successive complete tool rounds, automatic post-question compaction and continuation without another user message; preserved source meaning, whole-output readership, native identities, cumulative budgets, cancellation and publication/effect state. A1 Choice 2 is final: no private thread/run or native audience schema; all private content, including the requester's own, is excluded from shared consuming boundaries. Existing private management/admission acceptance grants no shared recall authority.

Authority inspected:
- Effective local/canonical spec v4, SHA-256 `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85`.
- Local complete design, SHA-256 `828EFFB02B5FBF9818604E35EA13662814E12CCC605B704DD895FD7BBAFE6236`; canonical design `068F9112279B55C6B9E1AB63730EF053F9E0B8A570C0EC4929677CE92502B1BB`. Independently diffed them: canonical adds §16, the Option A checkpoint refinement and admission follow-up; earlier operative contracts are unchanged.
- Approved design/review/oracle history, interpreted under current v4/A1 rather than historical unapproved-A1/global-wait wording.
- #43 approved Option A design baseline ED10B657B3DE9862D3601A8917B798AADE08B21E18CB48D66448BC5D2EEEE1E9, current independent review SHA-256 `1A46554A52902CBCCFBB59F32220F17A4FA161C756AC28EF373B167978783219`, and read-only in-progress contract/gate/journal interfaces. These working files are unfinished dependency observations, not accepted integration inputs.

## 2. Actionable findings

### F44-L1 — P1 before activation: whole-answer buffering changes the approved presentation contract

**Candidate:** §9, lines 165–167, also §7 line 132.
**Authority/runtime:** design §9.4 lines 492–494; API `routers/chat.py:267–278`; web `lib/use-chat.ts:435–439`.

Approved mode2 defines a provisional delta envelope `{executionId,text,provisional:true}`; it already buffers mixed text/tool turns until their type is known. The candidate goes further: every final answer waits for the complete turn, fresh authorization and successful finalization before any text is emitted, then describes provisional text as requiring separate approval. Legacy code emits each provider delta immediately and the web hook immediately appends it, so the proposed change has a real first-text/progress/cancellation effect.

Whole-turn acceptance before tool execution/final adoption is necessary. It does not itself decide public presentation timing. The terminal reducer can remain nonpublishing while that decision is resolved.

**Rework:** retain the approved provisional contract, or obtain an explicit product/API/#46 amendment specifying the all-buffered behavior, bounds, cancellation/source-revocation behavior and first-text/progress/reload acceptance. Preserve the existing mixed-turn safeguard. Do not infer acceptance of this latency change from pure fixtures or unknown-event tolerance. No mode1 timing change is approved.

### F44-L2 — P1 contract gate: proposed mode2 event list silently diverges from approved envelopes

**Candidate:** §9 table/sequence contract, lines 159–167.
**Authority/runtime:** design §9.4 lines 487–494; `lib/chat/sse.ts:303–351,368–401`.

The proposal introduces execution_state/tool_status while omitting an explicit disposition for approved memory_status/context_compacted; changes context_status phase `resumed` to `resuming` and does not carry its operationKey/checkpointId/owner identity fields; abbreviates history_sources without the approved contentKind/excerpt/occurredAt/truncated contract. These may be intentional additions or replacements, but a parser author cannot determine one exact versioned wire contract from the current text. Compaction-commit observability and source provenance must not disappear incidentally.

**Rework:** provide one normative compatibility table: unchanged required envelopes, additive events/fields, and any explicitly approved replacement/version change. Keep committed context_compacted semantics and full source provenance or name their reviewed equivalent. Reconcile delta/terminal semantics with F44-L1. Version discriminator and strict mode2 validation must protect legacy v1 behavior; tolerant legacy parsing is not a recovery implementation.

### F44-L3 — P2 implementation-start gate: the advertised reducer/engine scope depends on interfaces that are not settled

**Candidate:** §3 execution enum; §10 lines 180–199; §11 line 215.

The document acknowledges that final Python signatures need owner approval, yet its proposed immediate state/turns/engine slice would prove dispatch, journal, retrieval and continuous-budget orchestration through those interfaces. The inspected #43 working API is concrete and different:

- `DispatchGate.prepare_main_dispatch(owner, template, coverage, runtime_policy, *, expected_context_version, logical_key, mode, recent_units, protected_keys)` returns implementation-local DispatchPermit.
- `authorize_send(permit, runtime_policy)` archives/checks/marks the call sent; obtaining a permit alone is not dispatch authorization.
- Shared AccountingReceipt binds call/workspace/owner/request/native ledger; UsageSettlement is distinct from provider Usage, including unknown-value representation.
- Existing #43 execution lifecycle uses prepared and cancel_requested; the candidate proposes accepted and a reduced enum. Its receiptId and start/accept_turn/complete_tool/finish operations are proposed, not an owner-approved adapter interface.

These are observations of unfinished work, not demands to freeze its present shapes. Implementing six shared DTOs plus engine/port wrappers now risks a parallel lifecycle/budget authority and compatibility translations that conceal unresolved semantics.

**Rework:** split the immediate pure turn/transition work from durable orchestration. Before the latter, record the exact owner-supplied contract commit, callable/receipt ownership, authorization/send transition, lifecycle enums, replay/error rules and accounting mapping. Assign shared files explicitly through the controller. Do not create a cloned port, dummy journal/authorizer, public wrapper layer or second budget counter to make tests green. File count alone is not a defect; add state/engine/shared DTO modules only when an actual agreed consumer requires them.

## 3. What may begin independently now

**Eligible after controller assignment:** one cohesive neutral terminal-turn collector/transition helper, preferably beginning in the proposed `chat_loop/turns.py` with its dedicated `test_chat_loop_turns.py`. Reuse existing GenerationEvent, ToolCall, Usage, GenerationRequest/Message and ProtocolError. Internal return/state data may stay module-local; no new shared chat_loop.py ABI or package-root export is needed for this first consumer.

Its responsibility:
1. Consume already parsed typed events; preserve exact ToolCall IDs/arguments/order. Do not reimplement Responses/Chat/Anthropic fragment parsing.
2. Keep text/tool completions provisional internally until a valid matching TurnComplete; reject missing/contradictory/duplicate terminal, invalid complete call set, bounded overflow and cancellation before acceptance. Retain reported/estimated/unknown usage without inventing zero.
3. Produce a pure next-action decision: accepted answer, complete declared tool group, or bounded error/cancel/unknown stop. Partial/pending/unknown member results never authorize continuation; known failed/cancelled members remain explicit paired outcomes.
4. Synthetic transition tests may show each requested continuation returns a “gate required” decision with unchanged supplied execution/root/call identity. They may not mint a dispatch permit, call transport, journal effects, claim fresh source authorization or publish an answer.
5. Check duplicate delivery/stable member order and terminal monotonicity in the local reducer. A same-ID mismatch fails. Durable no-repeat, exactly-once adoption and continuous budget enforcement remain the real owner's later responsibility.

This is useful protocol-to-loop preparation and does not require #40, a finished index, PostgreSQL or completed #43 implementation. A test-only scripted gate outcome may document transition expectations; it must be labeled synthetic and cannot stand in for #43 conformance. Do not implement a fake compactor or reproduce its flawed prefix algorithm.

**Not yet eligible:** production engine dispatch/recovery, start/load/cancel/resume/retry storage commands, source/index activation, lifecycle exports, SSE/BFF/parser changes, multimodal bridge, bootstrap/background runner or schema authoring. The candidate is a proposal and supplies no ownership/migration grant.

## 4. Exact dependency boundaries for the next orchestration slice

| Boundary | Owner / required handoff | Current judgment |
|---|---|---|
| Provider ABI and shared package exports | #42 exclusive memory.py/root exports; accepted #44 adapters | PASS unchanged. No duplicate GenerationPort or new Worker→API import. |
| Dispatch and compaction | #43 corrected interval/anchor representation, exact counted request, one-use authorize/send receipt, protected source/current context and unknown-call behavior | BLOCKED for binding to production. P43-A1/A2/A3 remain unresolved; current in-progress interfaces cannot be assumed accepted. |
| Start/replay/finish/tool journal | Controller-assigned persistence owner with #43 execution/call schema and native chat owner | BLOCKED pending exact atomic API/ownership. Start must commit execution + user/pending assistant + request identity together; finish must CAS assistant/references/leaf/execution together. No separately committed status or summary head. |
| Budgets and settlement | #43 root fold/journal; API supplies frozen policy/capability; #45 retains native Research ledger | BLOCKED for runtime proof. Pin nullable/unknown usage mapping, reservations, root retry ancestry/deadline and late accounting after revocation. No in-memory counter accepted as durable authority. |
| Source/archive/index | #42/#43 existing source-use ownership; controller assigns activated asset/evidence/tool-result resolver and index implementation | BLOCKED for production history tools. Existing AccessPort.authorize is a private-owner management contract; it does not prove whole-output-audience access. |
| Mode1/mode2 request and runtime | #40 handoff only for overlapping route/dependency/schema work; #44 API service/composition and assigned runner owner | Local integration gate only. Neutral helper work continues independently. No blanket “wait for #40.” |
| Public stream and actual UI | API/#46 with explicit wire/presentation decision | F44-L1/L2 unresolved. Real browser acceptance required. |
| Images/capacity/secure transport | #42 shared ABI changes if needed; API composition/capability owner | Full parity blocked until actual image serialization/counting/gating is reviewed; text-only pure helper remains eligible. |

The candidate's suggested request_manifest field, source enums, group membership constraints and placement schema are **not approved DDL**. #43 owns its granted Option A fields/atomic adoption; other amendments need named owner + exact reviewed delta before implementation. Research/native publication state remains #45-owned.

## 5. Semantic review and retained negative oracles

- **PASS at design intent — same-submission compaction.** §5's old-history/current-question/in-flight-group example correctly addresses P43-A1. Preserve anchors in place and permit complete older groups after the protected question to compact twice without another question. The proposed compaction-input-v2/placements still need #43 agreement; pure plan success cannot establish committed coverage/pointer behavior.
- **PASS at design intent — actual serialization and capacity.** P43-A2 needs non-executable group projection with tools empty and actual native counters for all three protocols. P43-A3 requires recomputing/binding physical capacity against the current request/output reserve; unchanged fingerprint cannot legitimize stale capacity. No model-name guess, paid probe or estimate presented as exact count.
- **PASS at design intent; runtime unproved — entire readership.** Current thread reads are workspace-scoped, not creator-only (`routers/chat.py:121–130,189–198`); prepare_chat discards user_id. Candidate §7 correctly requires source ACL to cover every entitled output reader before hydration, with direct and original-leaf dependencies and current rechecks. Test both owner-private and second-member-private sentinels before snippets/ranking/cursors, prompts, tools, summaries/checkpoints, streams, logs and final outputs. Deleting a label or preserving actor membership is insufficient. No private resolver in shared path.
- **PASS at design intent — originals/provenance.** Exact source version/range/hash, Unicode ranges, unavailable-old-version failure, unknown legacy author and separate history references retain native meaning. A Research excerpt stays an excerpt, not a full original or new report evidence. Full oversized tool originals must be durable before success; missing tail/archive failure cannot become a successful truncated original. Source activation is still absent.
- **PASS at design intent; runtime unproved — budgets/unknown/no-repeat.** Frozen root policy/deadline, conservative sent/unknown reservations, no reset on retry/compaction and metadata-only late settlement are appropriate. Crash/replay tests must use real unique identities/CAS/reconciliation before claiming no repeated effect/final publication. Preserve design §9.3's repeated normalized-query + identical source/result versions twice → no_new_information rule in the next agreed orchestration tests; caps alone do not implement this progress rule.
- **PASS for explicitly limited boundary — multimodal.** Actual `services/chat.py:153–168,450–471` emits image arrays from native retrieval/explicit targets; GenerationMessage.content is text. Leaving that route unchanged is acceptable during an unactivated pure slice, and remains an unfulfilled every-main-dispatch gate. Never drop images or substitute OCR/text silently.
- **PASS for identified compatibility obligations.** Preserve mode1 selected-empty/no-ready/no-match errors, native edit-parent precedence, failed-ancestor prose exclusion and detailed citations. Both stream and complete_chat need the eventual gate. Current BFF lacks Idempotency-Key forwarding; optimistic client IDs/history reload are not durable mode2 recovery. Current ready-asset UI predicate blocks history-only chat. These require real integrations, not extra pure wrappers.
- **BLOCKED/unrun — user/runtime acceptance.** New bounded HTTP/SSE/recovery, security race/PG, two-compaction trajectory, semantic quality and visible organizing→automatic continuation/reload/cancel paths are not executed by this design review.

## 6. Evidence and handoff

Provider/admission integration is independently accepted and recorded only in the existing provider review: 117 dedicated provider, 6 API deploy, 2 Worker deploy and 13 boundary tests passed at a139336. Those results do not test the proposed loop. This review used source/contract inspection, exact hashes, specification comparison and a separate read-only legacy runtime/SSE audit. No new loop code exists to execute; no fake loop runtime result is reported.

Return F44-L1/L2 and the F44-L3 scope/interface correction to the original developer through the controller. The controller may assign the restricted pure helper now while owners resolve the affected contract boundaries. Full proposed engine/stream activation remains unapproved. #43 findings, full storage proof, source/capability/runner integration, semantic quality and UI acceptance retain their independent gates. Existing external service/delivery gates are not waived.

Write-back check: this new review and the integration-only append in issue44-provider.md are the sole reviewer writes. Candidate, product/tests/contracts/schema/workflows, Git state, canonical/shared-workbench and private memory were not modified. No database/service change, live provider or paid model call occurred. All prior provider evidence remains intact.


## Revised contract and pure-helper recheck — 2026-09-28

**ACCEPT — revised F44-L1/L2/L3 corrections and the bounded nonpublishing helper at the exact manifest below. No helper-code defect identified in this recheck. F44-L4 remains an actionable CI-delivery gap: the new 64 cases are not collected by the current hosted workflow.** This local acceptance does not approve production orchestration or public SSE/UI implementation.

### Exact reviewed snapshot

HEAD: **bc73fcb5bfca30e9aaa311c77dd694f3c123c894**. The revised lane document and three helper files are uncommitted candidate content. All hashes were checked before/after execution; the existing 14-entry provider/shared-contract manifest is unchanged. No tracked shared ABI, adapter or workflow delta is present.

| Repository-relative candidate | SHA-256 |
|---|---|
| `specs/v5/memory-management/lanes/issue44-chat-loop.md` | `EBFBDACE4ECF6FB28AB23079120E8738070E40A2ACD1042A6E80DC3C2F13D7E4` |
| `packages/memory-service/src/citeframe_memory/chat_loop/turns.py` | `EBFE72AC945A854866494DB0AC52B1F09EED23BAE84815463260A9A7639A664B` |
| `packages/memory-service/src/citeframe_memory/chat_loop/__init__.py` | `10A788B1AEB20EEF96F03330329D973E4A4166A814733E251B8DB50AA62B3E37` |
| `packages/memory-service/tests/test_chat_loop_turns.py` | `C7581F8940686F44E99B7E0695BF4B0E4A77F2FE8E02CBFD9DCA03A830BD38BC` |

Review SHA-256 before this append: `6C00E25F67CC3C0BEDCAE31D0DD9A1D8A923B21ABA537EEAF2BDF1E21482AF18`. Historical findings/evidence above remain intact.

### Prior findings disposition

| Finding | Recheck | Disposition |
|---|---|---|
| F44-L1 | Revised §9 retains provisional:true, preserves mode1 timing and mixed/type-unknown buffering, and expressly withdraws mandatory whole-answer/post-commit presentation delay. Terminal acceptance remains separate from public provisional presentation. | **Closed at contract scope.** The collector's internal buffering has no publisher and does not establish client timing. |
| F44-L2 | §9 restores memory_status, resumed, committed context_compacted, full history_sources provenance/truncated envelope and exact done/error forms. execution_state/tool_status/mandatory sequence replacements are expressly not introduced. | **Closed at contract scope.** Actual API/#46 wire/parser/browser implementation remains unaccepted. |
| F44-L3 | §3 defers lifecycle to the owner; §10 records required exact callable/receipt/send/accounting handoff. Actual code is one cohesive turns.py plus inert package init and one test file; no state/engine scaffold, shared ABI, root exports, owner service, fake authorizer/journal, budget ledger, dispatch or publication. | **Closed for this restricted implementation.** Future owner interfaces remain genuine integration gates. |

The v4/A1 shared-output exclusion, actual multimodal preservation, unresolved #43 findings and schema-ownership limits are unchanged. No new schema authority follows from this correction.

### Independent suite evidence

The developer's reported 181-case execution, including its “independent controller execution” label, is treated here solely as developer-supplied evidence. This reviewer performed a new execution.

**181 passed in 0.45s**, with actual collection observed as:

- `test_chat_loop_turns.py`: **64**;
- `test_native_provider.py`: **86**;
- `test_token_counting.py`: **14**;
- `test_wire_provider.py`: **17**.

Read-only interpreter: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B`. Local neutral source PYTHONPATH, PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Used the existing workflow's extracted Python denial/skip guards, adding only the helper path and a collection observer in memory. **The workflow file itself was not changed.**

Exact pytest argument scope:

```text
--noconftest --strict-markers -p no:cacheprovider
-o pythonpath= -o xfail_strict=true -q
packages/memory-service/tests/test_chat_loop_turns.py
packages/memory-service/tests/test_native_provider.py
packages/memory-service/tests/test_token_counting.py
packages/memory-service/tests/test_wire_provider.py
```

The meta-path finder denied ai_pdf_api/ai_pdf_worker; socket connect/connect_ex/create_connection were denied; the imported shared contract's exact local file path was asserted. Existing guards reject skipped/deselected/zero collections; no such weakening occurred. No PostgreSQL/application suite was selected.

### Independent adversarial and conformance probes

Executed separately through inline Python without importing developer test helpers. All were synthetic, under the same application/network denial.

- **14 typed/result rejection probes passed:** missing terminal, contradictory answer/tool terminal, duplicate terminal, same completed call ID with changed arguments, delta/completed ID mismatch, reversed completed-call order against declared indices, cancellation before processing and after terminal, UTF-8 byte overflow, call limit, argument limit, orphan result, changed duplicate result content and changed duplicate result status.
- **Positive/stop controls passed:** two Chinese characters exactly fit six UTF-8 bytes and fail at five; unknown Usage(None,None,'unknown') stays unknown; missing/pending results stop without a continuation request; unknown results stop as unknown rather than failed; execution cancellation stops even with complete results; reversed result arrival and identical duplicate delivery produce exactly one result per original call in original order and preserve the supplied TurnIdentity object.
- **Actual adapter → collector conformance passed for all three protocols:** used httpx.MockTransport and the accepted ResponsesAdapter, ChatCompletionsAdapter and AnthropicAdapter with two interleaved calls observed index 1 before index 0. Pretty/Unicode argument text was parsed/canonicalized by the real adapters; collected call IDs/order and completed argument bytes matched their output. This covers fragmented ChatCompletions names/IDs as well as Responses/Anthropic native event framing.
- **Nine actual counter/serializer continuations passed:** for each protocol, paired the two-call group with completed, failed and cancelled second-member outcomes, using the real PayloadTokenCounter/native serializer. Each candidate remained gate_required, preserved identity, and was structurally acceptable to that protocol. The injected count of 77 is a synthetic observer result, not tokenizer-accuracy evidence.
- **10 native-wire rejection probes passed:** missing terminal, duplicate IDs and schema-invalid arguments for each protocol; additionally Responses arguments.done differing from the streamed arguments. Every case raised generation_protocol_invalid before collector acceptance.

**Argument trust boundary:** completed ToolCall objects come from the parsed, schema-validating provider port. The helper retains them; it does not parse native JSON/tool schema again or compare raw fragment spelling with canonical completed JSON. Such raw equality would reject valid whitespace/Unicode normalization. Delta IDs/order/byte bounds are checked locally, while argument syntax/schema and native final-argument reconciliation remain adapter-owned. Directly forging an arbitrary ToolCallComplete is outside this parsed-input guarantee; this helper is not an untrusted DTO/schema security boundary.

The local transition's identical-result deduplication is not durable exactly-once execution. Unknown stream failure remains a safe collector failure; only the eventual journal owner can determine sent/outcome_unknown disposition. No source authorization, lease, accounting settlement, recovery, dispatch or publication was exercised.

### F44-L4 — P2 delivery gap: the new helper suite is absent from hosted collection

Actual `.github/workflows/memory-provider.yml` SHA-256 remains **0147FB741DB6ED737942A258F189B0D561CEC77BD1B688FFA247D82A86FA5412**. Independently parsed its embedded runner's AST: its explicit test list contains only the three accepted provider/counting/wire paths. Consequently this job continues to select the old **117**, not the new 64 helper cases. The new lane's four-file local command does not change hosted collection.

**Minimal original-developer/controller change:** add exactly

```python
"packages/memory-service/tests/test_chat_loop_turns.py",
```

to that dedicated workflow's existing pytest.main argument list. Preserve frozen API uv setup, local contract assertion, network/application-import denial, no-conftest/plugin/cache settings and skip/deselection/zero/xfail guards. Do not broaden to the whole memory-service directory or modify #42-owned ci.yml; no PostgreSQL collection is needed. Expected current collection is four named files / 181 items, with no skip, deselection or xfail escape. Record the revised workflow hash and execute its exact body, then attach hosted evidence at the delivered commit. No separate framework or new job is necessary.

This CI omission does not invalidate the independently passing local helper implementation; it remains open before claiming hosted enforcement of the new slice. Return the minimal workflow rework through the controller to the original developer.

### Final scoped handoff

The revised document and helper are accepted only for parsed-turn collection and pure continuation preparation. Production owner contracts, actual gate/send binding, entire-audience source enforcement, shipped storage/recovery, same-run compaction, frozen budgets, native effect/publication preservation, multimodal parity and real SSE/UI behavior remain unaccepted. Synthetic fixtures provide no live-provider/model-quality evidence. Existing provider/admission acceptance is retained.

Only this original chat-loop reviewer artifact was appended. No product/test/workflow/schema/contract/Git/profile/private-memory/shared-workbench write, service/DB change or paid/live model call occurred. Controller retains delivery ownership. F44-L4 is the sole new actionable delivery item from this bounded recheck.


## F44-L4 exact workflow closure — 2026-09-28

**ACCEPT — bounded CI correction. F44-L4 CLOSED.** No new finding. Prior F44-L1/L2/L3 closures and restricted helper acceptance remain unchanged; earlier evidence is preserved.

Reviewed HEAD `bc73fcb5bfca30e9aaa311c77dd694f3c123c894` plus the uncommitted workflow candidate SHA-256 **BBEF4AED401E013E1E09A0206D2BD8FC01635DE1B54B5C7FC3F52974873EC091**. Removing the sole added explicit `packages/memory-service/tests/test_chat_loop_turns.py` line restores exact prior candidate SHA-256 `0147FB741DB6ED737942A258F189B0D561CEC77BD1B688FFA247D82A86FA5412`. Therefore frozen uv setup, local-contract assertion, application/network denial, explicit provider selection and skip/deselection/zero/xfail guards are unchanged. No #42 CI or PostgreSQL collection was added.

Independently parsed the actual YAML and extracted Python AST: exactly the three provider paths plus the helper path are selected. Heredoc/Python syntax and Git Bash `bash -n` pass. Executed the **exact revised embedded Python body**, using the same read-only interpreter and local environment documented above: **181 passed in 0.44s**, exit 0. This is new reviewer execution, separate from the developer's report.

Independent negative control changed only the selected helper path in an in-memory copy of the runner to a verified nonexistent path. Pytest returned **exit 4**, with file-not-found and no tests run. No file was removed or renamed. The actual workflow remained byte-identical throughout.

The three previously accepted helper hashes are stable:

| File | SHA-256 |
|---|---|
| `chat_loop/turns.py` | `EBFE72AC945A854866494DB0AC52B1F09EED23BAE84815463260A9A7639A664B` |
| `chat_loop/__init__.py` | `10A788B1AEB20EEF96F03330329D973E4A4166A814733E251B8DB50AA62B3E37` |
| `tests/test_chat_loop_turns.py` | `C7581F8940686F44E99B7E0695BF4B0E4A77F2FE8E02CBFD9DCA03A830BD38BC` |

Paths are under the same memory-service source/test roots as the full manifest above. Hosted Ubuntu execution after controller commit/push remains separate pending evidence; neither hosted execution nor frozen dependency installation was run locally. No wider runtime, source/security, storage, compaction, UI or model-quality acceptance follows.

Write-back: only this reviewer artifact appended; no product/test/workflow/Git/model/service/DB/private-memory/shared-workbench writes. Controller owns commit/push and hosted delivery verification. No remaining F44-L1/L2/L3/L4 rework for this exact scoped candidate.


## Runtime 合同 §§14–19 独立评审 — 2026-09-28

**结论：整体 runtime 合同 REQUEST CHANGES；不批准 start/finish、source/tool、multimodal、router 或 runner 激活。最小 R3 profile 解析/校验代码可以按下述明确边界独立开始，不等待 #43 全部返工，也不整体等待 #40。** 原 F44-L1/L2/L3/L4、provider/helper/CI 的既有范围结论保留。

### 1. 总体目标、权限范围与精确身份

先核对有效 spec v4 §§12–14 与 A1 选项 2：目标仍是同一问题提交中的完整工具轮次、问题之后的历史自动压缩、多次阈值跨越与自动续跑；保持原始来源含义、任务身份、冻结预算、取消、工具效果和发布状态。当前输出沿用整个工作区的现有读取语义；请求者自己的私有数据也不得进入 shared prompt/tool/history/summary/checkpoint/planning/SSE/log/final output。无新 audience/private thread/private run，也无推断长期候选授权。

- 当前分支：`work/issue44-chat-runtime`；HEAD **b0e30fb24d3c119573ea7a5d1a7b1607da2fc602**。
- 只读验证两个 merge parents：**812ebb1ed9bdddf8ef3dc44f9aeb8387036607cd** 与 **1b9e1168c2c2b1548febc1fcb5997d4310bfe511**。这是精确集成候选，不是 main/已合并 lineage 的替代证明。
- 被审新合同：`lanes/issue44-chat-loop.md`，SHA-256 **B8510A1C79D3154C939F326AFDD65C696749D28473151116E68C8C78AFF4023B**，读取完整新增 §§14–19，检查与前文已批准范围的衔接；未修改。
- ownership 文档 SHA-256：`6D6119E236DB62038A8A34599F1FE65E66BFF49ECCC157246B69C165CD61CF82`。Hegel 的 router 窄租约及 services/chat.py 可用性不构成新合同/DDL批准；没有创建新的实施 owner。
- #43 interval **B34DEAC14AF9A7438E6453EBD46649B07F18B5EF8904BB43AB2BA63B092BD736** 已获设计批准；本次读取的原 reviewer 仍要求 F43-C1/C2/C3 core 返工及 CI gate。该设计批准不覆盖当前实现或 C1/C2/C3。
- sources 的 **98fb0e0823b81aac0bda2f26e03de1ff6d702fe1ec59043911fc841ba87860b5** 原 recheck 仍有 strict-policy/empty-result/cursor 残留。只读期间原 source owner 已有更新文稿 A0B3029C…，未发现原 reviewer 对其新的 closure；不将并发文稿视作已接受接口。

### 2. F44-R1 — P1：重放身份混入可变的解析结果，精确 POST 可能在完成后变成冲突

**位置：新合同 457、465–467 行；原生 `routers/chat.py::_resolve_parent_message_id`。**

§15同时规定同 request/key 直接返回原 IDs，又把 resolved parent、profile/control 值放入 canonical request hash，并在 start 描述中先重验当前 parent/edit。实际 parent 未显式传入时取 thread.active_message_id。

合同级反例：首次同一 POST 未指定 parent，解析为 P 并接受；完成后 native leaf 变为 A。原 POST 精确重放若重新解析，parent 变成 A，profile 或模型配置也可能已变化，产生不同 request hash，于是409。这里没有客户端修改请求；它是恢复丢失 meta/ACK 的合法重放。当前文稿未区分稳定的客户端意图与首次接受时冻结的执行解析结果。

**精确修正：** #43原 owner 与 #44原 developer 约定一个稳定的请求意图 hash，覆盖客户端验证后的 body/route/actor/workspace，保留“省略 parent”和“显式 parent”的含义；首次接受的 resolvedParent/profile/control/source snapshot 另存已有 request_manifest 及其绑定。当前授权通过后，先按 requestId/key定位并验证原请求意图，再返回已接受身份，不重新执行预检/parent解析/写入 callback。新的请求才解析当前环境并冻结；显式 retry/rebind走各自授权命令。无需为此发明第二 execution 表或新幂等框架。

**必要 oracle：** 成功后、leaf变化后、凭据/配置变化后重放同一个 POST，仍返回同一执行/消息且零 callback/模型调用；客户端改 body/显式 parent则409；被撤权者仍不能借 replay 读取内容。并发双身份碰撞和 lost-ACK 用真实 owner transaction 验证。本次仅是明确的合同反例，未声称执行了不存在的 start_chat。

### 3. F44-R2 — P1：profile 的实际连接绑定与有效模型上限尚不闭合

**位置：§16 496–526 行；`services/capabilities.py:339–380,469–481`；`model_config_types.py::ModelConnection`。**

文稿称 config revision change 必须重新绑定，但现有 connection_profile 的 hash preimage不包含 ModelConnection.revision/source。本 reviewer 从实际文件抽取原函数 AST，在完全合成 settings/constants/secret 下独立执行：**revision 1→2，fingerprint不变**；合成 secret轮换控制组 fingerprint变化。未导入真实应用 settings/凭据，未联网。检查对象 capabilities.py SHA-256 `FFE48D99BCA411B98A77FBFEA7336E25D1F53F5686B9FB4612D76D453C40BD08`。这证明现有函数无法单独兑现“任意配置 revision 变化必重绑”。

此外 proposed resolve接收可单独提供的 connection_fingerprint，build又接收另一个 connection；没有规定如何拒绝“旧 fingerprint/profile + 新 connection”。注册条目的 maxOutputTokens也未明确与现有 connection.max_output_tokens取更严格值；“不超过物理窗口”不足以保护已有应用输出上限。

**精确修正：**
- API可信 composition计算现有连接指纹，并额外绑定实际 source/revision及明确的原协议→中立协议/adapterVersion映射。不要修改现有全局 capability fingerprint算法来影响旧 Research release。
- build只消费该确切已解析连接，或重验连接与 profile完全匹配；不得只信任独立传入的字符串。端点、模型、协议、凭据身份、timeout、revision漂移应拒绝且零 transport send。凭据只在短生命周期 connection中，不进入 registry/hash明文/repr/日志/持久化。
- physical context/output、应用 connection.max_output_tokens、请求 output reserve与更严格 inputCeiling分别校验；有效 output不得超过任一已配置上限，不能因部署条目更大而抬高原限制。counter/Capabilities/snapshot使用同一最终绑定指纹。
- 所有能力开关严格bool，数值严格类型/有限/合法关系；未知或歧义 profile、未知实现ID、无真实counter、缺失容量或参数全部 fail closed。传入 cancelled callback还要与实际 supportsCancellation一致，不能构造后到首次 send才发现不支持。

本条影响安全 profile composition；不要求等待数据库、sources或interval完成。

### 4. F44-R3 — P1 source/tool 激活门：两个来源权限合同尚未形成单一可消费接口

**位置：§14 strict v1；§15 request_manifest；§17 561–586 行；source reviewer SS01-R/SS04-R。**

候选将 history envelope放在 request_manifest，明确不扩展 strict compaction-policy-v1；已有 #42 source方案则要求 #43从冻结 owner policy签发 transaction-local HistorySession，并提出新 policy版本。两者目前没有确定的唯一 authority/交集/hash/retry规则。§17还把 search/read实现整体指定给 repo方法，未与已有 #42 shared-source/query/range owner、#43 issuer/registry/consumer职责形成精确调用链。不能通过另造 API authorizer、重复查询实现或继续传scope dict解决。

原 sources98fb的分页问题也不能被本合同“cursor15分钟”覆盖：把cursor绑定上一次完整请求hash，会在下一轮工具调用及历史增长后拒绝正常下一页。empty/excluded结果放宽方向正确，但仍需原owner实现、严格code-owned disposition及完整group/use验证。

**精确修正：** 回原 #42/#43 owner，确定同一冻结history policy来源和request scope交集；保留旧v1意义、history默认禁用、严格版本/未知字段拒绝，不隐式重写旧任务hash。#43保有原生issuer、registration、journal/archive、use predicates；#42原source/query/range实现通过其受控transaction接口工作；#44只做工具DTO映射和编排。最终Python签名与确定提交由两个原owner交付，不授权另起实施者。

cursor保持source/version/window/owner/权限策略/counter能力身份等稳定绑定；每个后续调用重新授权并按当次完整请求及剩余容量计数。当前请求hash写该call journal，不要求等于上一页请求。至少两轮不同call ID/增长历史的范围拼接必须精确还原固定窗口。零命中/合法excluded/已知失败结果可无source叶，但不能借此授权任意非空正文。SS02-R graph/SQL残留也保留，未获DDL豁免。

这阻塞真正source/tool激活，**不阻塞纯profile解析**。A1全部读者覆盖、包括后来合法工作区成员的原生读取语义、失败祖先零模型正文、显式图像locator不能假冒ContentUnit等方向正确；目前均为未执行的consumer约束。

### 5. F44-R4 — P2：创建 HTTP client 的 build 签名缺少明确关闭责任

**位置：§16 build_chat_generation，524行；实际 `model_transport.py:129–131` 与 neutral adapter 构造函数。**

model_client返回持有连接池的httpx.Client；neutral adapter只保有注入的transport，无统一close/context-manager协议。候选build内部创建client却只返回GenerationPort/TokenCounter，未规定正常、构造失败、cancel/unknown、runner关闭时由谁释放。依赖调用方访问实现私有属性关闭不是已批准的接口。

**最小建议：** 由API composition在明确的 `with model_client(...)` 生命周期内拥有client，build显式接收已有HTTPTransport并仅构造现有adapter/counter，不新增包装service。最终签名可为原tuple返回加关键字transport；真实composition只能注入既有secure model_client，测试注入MockTransport包装client。原developer先明确签名/关闭责任；不需要shared port/adapter改动。该修正只影响build部分，无需等待#43。

### 6. F44-R5 — P1 multimodal 激活门：“现有 bounded image loader”与实际代码不符

**位置：§16 544行。**

独立只读实际路径：
- `services/storage.py:324–332` 使用无显式长度上限的response.read()。
- `modalities/image_evidence_targets.py:269–282,307–337` 先下载完整对象并image.load()，随后才进行几何检查/crop。
- `modalities/pdf_evidence_targets.py:122–145,404–411` 先读取PDF，再以150dpi生成完整pixmap，之后才据1280边长重渲染。
- visual_enrichment的图片数量限制只约束可选输出，不限制源下载/中间解码分配，也不是显式target加retrieval的总量上限。

因此在最终GenerationImage上检查字节/尺寸，不能追溯保护已发生的下载/解码/渲染资源消耗。

**精确修正：** 指定既有native loader/render原owner的有限输入/分配边界，source bytes、decode前像素和render前分配分别限额；改正“已存在”的声明。获支持的实际输入保持crop bytes/order/detail，不能悄悄缩图、丢图或OCR替代显式证据。本项仅阻塞R4/R5多模态激活，文本R3可继续。

### 7. start/finish、unknown usage 与其 owner delta 判断

**方向 PASS，精确实现/DDL未批准。** 把commit集中到#43一个Session事务，#44仅提供无commit/rollback/IO/授权的native writer callback，是合理的最小边界。实际prepare_chat在270行commit，finalize_chat在311行commit，直接串接现有create_chat会产生已提交消息但无execution窗口；文稿正确识别了此问题。

原owner需要交付的具体delta与oracle：
1. **#43 start/replay**：事务内factoring，原生workspace/member/thread/FK目标预锁与验证、原生消息/citation/input-evidence+execution一并提交、唯一键输家全回滚、R1稳定重放。保留nullable anchor及用户指定branch；不能省略F43-C1实际anchor FK NOWAIT修正。
2. **#43 finish/terminal**：先按现有成功receipt进行当前授权的幂等reconcile，再走仍streaming的live guard；校验同一main receipt/结果hash/context/lease/source后callback更新native状态和execution成功，同事务提交。结束后serialization异常不得调用legacy fail_chat降级。失败/取消命令的精确接口和重放存储仍待该owner确认。
3. **#43 current question + interval**：F43-C2必须在真正的mandatory gate保证指定当前原文恰好一次、protected且顺序正确；不能让#44“每次记得传”代替。B34 interval实现、fresh-process重建、F43-C3同thread sibling/source/group DB约束修复仍是runtime依赖。
4. **#43结果journal/usage**：声明完整成员再执行；complete_group/archive可复用但不能倒过来宣称已journal。settle_generation在原journal同一metadata-only事务读取reserved值，保留nullable原Usage，复用原settle算术；不在#44增加预算副本或嵌套commit。
5. **usage映射要求**：有可信reported组件则保留真实0；缺组件使用对应reservation，标注estimated/unknown且保存原source；全部known但source=estimated不能改报reported。sent/outcome_unknown至少保留原reservation，无终态/取消不自动退款；proven-unsent通过独立幂等取消命令释放。重复结算、late usage、revocation、部分None、两项None、显式0和estimated完整值需要表格化测试。metadata-only更新不应为了拼result JSON重新hydrate内容/source。
6. **#42/#43 schema**：request_manifest/idempotency_key/唯一性、旧行legacy-disabled与control操作幂等归属仍需exact migration/compatibility批准。此评审没有批准NOT NULL回填、字段、迁移文件或改private memory_operations。只在其真实consumer下新增必要字段。

### 8. 最小 chat_runtime_profile.py / test 的独立实施边界

**允许原developer在controller登记这两个新文件后，先做R3-A；无需等整体runtime。**
- `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py`
- `apps/api/tests/test_chat_runtime_profile.py`

**R3-A可立即开始：** 无IO的严格registry形状/类型/唯一性校验、确切协议映射、合成text-only条目的纯resolve及负例；只复用既有ModelConnectionSnapshot/CountingProfile/Capabilities，module-local不可变结果，不创建port/framework/新全局registry服务。对R2的可信连接身份/revision及上限规定先同步到这两个文件的实施合同；不允许按原文漏洞构造一个已“安全绑定”的对象。可以先完成与这些差异无关的schema/参数/未知项拒绝测试。

**R3-B建造器仅在R2/R4的小范围签名/绑定修正后开始**，不等待#43：显式transport生命周期；实际existing adapter类；没有send、DNS、remote discovery、DB、route/runner、source/journal/gate或shared settings修改。无模型调用构造与synthetic MockTransport序列化可以测试，但不视为生产profile可用。

计数/配置限制：
- 当前锁定依赖中未发现tiktoken/tokenizers/transformers/sentencepiece，也未提供一个经过provider/model/protocol计量验证的真实精确实现；**本轮不批准任何生产exact counter或真实capacity profile**。
- 现有CharacterEstimateCounter可用于明确estimated的合成fixtures；真实部署使用仍需对应模型参数/安全余量的来源和审查。字符除数、constant callback或tokenizer对JSON的简单计数均不能据此称provider精确token。
- 只允许closed implementation ID；未知ID不动态import、不从网络下载、不猜provider/model alias。exact分支若无已注册验证实现必须拒绝。profile/CountingProfile/TokenCount的mode与fingerprint必须一致。
- 真实registry条目、加载路径/部署配置仍归#42/controller另行审查；测试不写任何可被生产自动加载的假容量。images条目在R4/R5批准前明确拒绝。
- 测试覆盖重复/未知entry、严格bool/有限数值、物理与配置上限取严格值、raw protocol mapping、adapterVersion区别、revision/secret/endpoint漂移、坏counter结果及mode、构造零网络与正确关闭；实际生成质量/计数准确度不在此scope。
- 所有成功结果只是“未激活的真实组合代码/负向边界通过”，不构成可用chat runtime。测试进入现有CI的精确目标由controller登记，不能以宽目录收集引入PG，也不擅改#42 ci.yml。

**现在不允许写：** router/chat、services/chat的native callback、shared memory.py/exports、adapters image字段/serializer、#43 source/DB、settings/locks/registry加载器、SSE/client或runner。已有router租约保留，等其实际消费合同批准后使用；无新增实施owner。

### 9. 多模态与SSE兼容的其余结论

- **GenerationImage方向可行但ABI未批准**：当前chat.py:450–471是单text在前，显式targets按target/region顺序，再追加retrieval crops，原PNG bytes编码data URL并detail=high。追加ordered images tuple足够，四个旧位置参数可保持；无需通用content-part框架。
- **#42精确ABI交付**：GenerationImage与GenerationMessage末尾images，user-only、严格PNG/base64/dimensions/bytes约束和text回归；#44待批准后改现有serializer/Capabilities/counting，#43改请求archive/restore/hash/limits和protected current image重建。Anthropic协议本来没有detail字段，按既有native语义映射，不虚构字段。
- 图片fixtures须包含多个显式target的多region及其后的retrieval crops；no-image、错误MIME/尺寸、历史图片restart、当前private/revoked source等负例仍必需。图像token上界来源须真实可验证；计数投影不改变实际发出的图片/请求hash，估算仍标estimated。
- **§18 presentation方向PASS**：text-only mode1即时delta、mode2 provisional、mixed/type-unknown直到真实类型已知再释放，done在owner finish后；与已关闭L1/L2一致。当前typed事件没有early-answer类型，不能从首个文字token猜测。
- bounded tee需要对mixed-turn buffer和subscriber queue分别设限；mode2慢/断subscriber只detach，不能停已接受执行；mode1保留中断语义；terminal成功不被callback失败降级。这些是后续真实SSE/#46浏览器oracle，本次未执行/未批准UI。

### 10. Evidence 边界与交付

本次Critical证据是：实际merge parents/branch/hash、完整新增合同与source/core reviewer结论的对照、真实native/provider/counter/transport/image代码检查，以及**实际connection_profile函数AST的合成revision漂移反例**。没有把接口文稿当成已存在产品。未运行PG/native交易/HTTP模型/UI；没有重复无关181 fixtures并借其泛化runtime安全。#43 C1/C2/C3和sources98fb残留只作为原独审依赖证据，本review不冒称复现或关闭。

本次原#43 reviewer hash `502613A76C612EB9278040F483A6A2E92855513833472D6A2E35DD9F391D7E26`；原sources reviewer hash `AA64E61FFAF258E3732DCEB2341273643F122BB7FA35E5A341538BA602808E65`。并发source新文稿hash `A0B3029CD9321B6D8EF45C425322FE39BBFE6E940557042D5838AF2AC0B54572`仅记录观察，不给closure。

请controller将R1/R2/R3/R4/R5分别交回原#44 developer及上述#42/#43 owner。R3-A可以先推进；R3-B只等自身小合同修正；原生runtime需真实owner APIs、修复后的core/source、完整multimodal和SSE/UI证据。任何一项局部批准都不豁免外部service/merge gates或完成#41。

Write-back检查：仅追加此已有review artifact，之前所有provider/helper/CI证据完整保留；未改候选/产品/测试/工作流/共享合同/schema/Git/数据库/服务/私有memory/共享workbench，无paid/live模型。追加前review SHA-256为 `B783EF58044DFEF8B63B1AB396B4258B871CE46EAC92DF77620B306064822F1F`。


## R2/R4 profile-binding 小合同独立复审 — 2026-09-28

**结论：ACCEPT — R3-A 纯解析/校验的实施合同。F44-R2 在此精确 text-only 合同范围设计关闭，实际实现验证待后续同一 reviewer。F44-R4 的 transport 注入和生命周期责任在设计层关闭；R3-B endpoint 规则仍未定齐，暂不实施 builder。该局部门槛不限制 R3-A，也不等待 #43/full runtime。**

### 精确对象与目标

- 被审文件：`lanes/issue44-profile-binding.md`，完整71行；审查前后 SHA-256 均为 **26186416599BC39E3732F2842F77E84F4D6F6B347D461578EDA2D16E83976338**，未改动。
- 分支 `work/issue44-chat-runtime`，HEAD **b0e30fb24d3c119573ea7a5d1a7b1607da2fc602**，没有 Git 写入。
- 原 review 追加前 SHA-256 **E06BD82578182A2944DEE2F0658558F620E60984318264274EB00FBE7A4E9468**；以二进制前缀比对保证历史证据未改。
- 主合同 `lanes/issue44-chat-loop.md` 当前观察 SHA-256 **5D032056A20E89D394A781303F37F698AB09EE63EA9BAC4D030486E0E9DE7A0F**，已经不同于上轮 B8510A…；本次只复核其关联 §16，不给并发修改的其他条款新批准。小合同 hash 没有漂移。
- 已出现两个新 API 产品/测试文件及开发证据；本轮仅记录存在，不将开发测试报告视为独审，也不对这些并发代码给 ACCEPT。

重新核对 spec v4 §§12–14/A1选2：完整目标仍为问题之后、同一任务内的多次自动压缩/工具续跑，预算与来源不变、不重复效果或发布；共享消费边界排除所有私有内容，不新增 audience/private thread/run。当前 profile 是未激活的配置前置条件，不承担权限、账本、native transaction 或压缩完整性证明。总体 runtime 的未关闭项及 #42/#43 原 owner 边界不变。

### R3-A — PASS，可在既有两个授权文件继续实现

小合同16–24、28–42行已足够消除本 slice 的 R2 接口漏洞：

1. resolve 自己把同一冻结 `ModelConnection` 传给可信 composition callback；不接受单独 fingerprint 字符串。source/revision/native protocol 加入严格 selector，保留既有 Research fingerprint 语义。配置变化须拒绝旧条目或生成新绑定，不能沿用旧执行授权。
2. 最终 hash 绑定 raw base 的 hash、timeout、应用/有效 output、全部已验证 entry；结果持有原始连接的私有短生命周期字段，深度复制冻结外部 registry。错误/repr 不泄露 endpoint/key。无第二 connection 的 builder 方向可接受。
3. 应用和物理输出上限取 min；requested reserve 只校验不静默夹小，H 另扣 reserve/safety，并受 inputCeiling 限制；严格整数排除 bool、有限数值和水位关系均有明确 oracle。profile identity 不代替将来 owner 冻结本次 request reserve/预算；后续 request admission 仍须检查该 reserve。
4. 三种 raw→neutral protocol/实际 adapter 映射是封闭集合；不从模型名推断能力。完整 registry 包括非命中 entry 均校验，重复/歧义/未知拒绝；无动态导入或下载。
5. 仅 `character-estimate-v1` + `estimated` + 现有 `CharacterEstimateCounter`；images/exact/未知实现拒绝。实际 Capabilities 无 fingerprint 字段，合同“where DTO supports it”允许保持既有 ABI，不能为此擅加共享字段。

**可写范围仍只有** `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` 与 `apps/api/tests/test_chat_runtime_profile.py`：严格 schema/selector、可信 callback 绑定、不可变 API-local 解析结果、上限/水位、既有 CountingProfile/Capabilities/estimated counter 与合成正负例。暂不构造 endpoint/snapshot，不创建 HTTP client/build 占位，不加载配置/settings/secrets；不增加全局 registry 服务、共享 port 或框架。

后续同 owner 实际代码独审需验证 callback 收到原对象、source/revision 同旧 hash 拒绝、所有绑定漂移、app/physical/reserve 三种边界、嵌套 mutation、safe errors/repr、严格未知/重复 entry 与三协议；使用真实 counter/serializer 并保持 network/settings-import denial。不能用开发者自己的测试命名替代 independent verification。CI 精确收集这两个新文件对应测试的方案仍须单独登记；本轮无 workflow 修改授权。

### R3-B — 生命周期方向 PASS；最小剩余 endpoint 信息

47–65行的接口和职责足以关闭原 F44-R4 的“谁关闭 client”问题：composition 持有 `with model_client`，先关闭活跃 iterator、再退出 client；正常/构造异常/cancel/unknown/runner退出均覆盖。build 接收既有 transport，不自建/关闭第二个连接池，不接收另一个 connection；cancel callback 与 capability 构造前检查。此为合同判断，尚无实际 builder/client-close 测试通过声明。

**仅待原 #44 developer 补齐下面的 source/provider/protocol→endpoint 小表及校验位置，再审 R3-B；无需 #42/#43 新接口或新实施 owner：**

- 实际 `workspace_providers._BoundProvider.adapter` 对 workspace 使用 `exact_base=True`；server OpenAI 使用 `_normalize_openai_base` 再追加 `/responses`，ChatCompletions 追加 `/chat/completions`。同一 raw `https://fixture.invalid/custom`，workspace 的 `/custom/responses` 与 server 的 `/custom/v1/responses` 有真实差异。不能统一无条件补 `/v1`。
- 实际 DeepSeek 路径通过 `_normalize_deepseek_base` 把 `/v1` 转成 `/anthropic/v1`，随后 `/messages`。raw protocol `anthropic_messages` 本身不能说明任意 provider/workspace 也该使用 DeepSeek 路径；需逐项规定支持的 source/provider 组合及不支持时的明确拒绝，不新增猜测路由。表中至少列 root、custom prefix、`/v1`、`/anthropic`、`/anthropic/v1` 和尾斜线。
- 指定 raw base 与最终 endpoint 在哪里调用既有 URL/origin validation，什么时候构建 snapshot，以及 composition 如何取到 profile 绑定的原连接来创建 client。现有 `model_endpoint.py` 顶层依赖 settings；原 provider normalizer 也会导入 capabilities。不要为复用几行路径规则让 R3-A import-time 加载这些模块。现有 `model_client` 在构造时验证 base、真正连接时做 DNS/IP/origin 检查；合同需明确这两种时点，不把纯 resolve 当成 URL/SSRF admission。
- endpoint 只能从已绑定连接按该表确定，不能增加 caller 任意 endpoint/第二 connection；保留 raw base hash。无须增加 transport-close ABI、生命周期包装类或新的 registry/endpoint 服务。实际测试再证明三类 adapter、零 construction send、同源拒绝与 iterator/client 各退出路径关闭。

这是候选65行自己保留的 endpoint approval gate；无需将其扩成整个 runtime 的新阻塞。最终 builder 实施仍待该小表/校验位置确认。

### 实际依赖证据及限制

只读核对现有 ModelConnection、connection_profile、native endpoint paths、model_client、shared snapshot、counter 和 adapter 构造签名。关键 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/services/model_config_types.py` | `FD9CBA258790C867683F11FB7C930BC92DD0F541A352537139767F3348CB452A` |
| `apps/api/src/ai_pdf_api/services/capabilities.py` | `FFE48D99BCA411B98A77FBFEA7336E25D1F53F5686B9FB4612D76D453C40BD08` |
| `apps/api/src/ai_pdf_api/services/model_transport.py` | `A9E79ACC79C6FB90959DE0A7892BBDE466B58B4884367F534DE027BA5CE001A2` |
| `apps/api/src/ai_pdf_api/services/model_endpoint.py` | `6E647925B708AF4FF933EE9CE7CA49B44E65D08BBF88F82A0DC9669B069609E1` |
| `apps/api/src/ai_pdf_api/services/providers.py` | `8338579B25493C2AE1D837FCCCD675F8F80B169C7EC22CF04FC9082AA755501E` |
| `apps/api/src/ai_pdf_api/services/workspace_providers.py` | `6C96C82A10BC0695965A4EAC6BFDEBD6DC3180F10100CDFACACA55B15F53566A` |
| `apps/api/src/ai_pdf_api/services/chat_completions.py` | `1DE65A326E5F0B7555E0F5251524ACB04B92F82D0D1EDEB01AED5D66E9258DEE` |
| `packages/memory-service/src/citeframe_memory/adapters/counting.py` | `5852ABE7D7A0D2951E4FB31F29CDD5B4DA38AC20AD2DDC977E5813B3FEC8FCA1` |
| `packages/backend-contracts/src/citeframe_contracts/memory.py` | `B1A0D53B5D21BAC31AC12609A5A798CCEDA5F9AAB43EEFAA4E178A3D9D5AAE45` |

独立 inline Python（`D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`）禁止 socket connect/connect_ex/create_connection/getaddrinfo，MetaPathFinder 禁止 ai_pdf_api/ai_pdf_worker 导入：

- 从真实 capabilities.py AST 提取 `normalize_provider_endpoint` 原函数，仅注入 stdlib urlsplit/urlunsplit，3项断言通过：OpenAI custom→custom/v1；DeepSeek /v1、/anthropic 均→/anthropic/v1。workspace exact_base 分歧另由真实调用代码确认，没有执行 HTTP。
- 实际本地共享合同 + CharacterEstimateCounter + native serialized：合成 message=`合成 text`、model=`synthetic-model`、reserve=25、characters_per_token=4、overhead=7；三协议分别得到 **35 / 44 / 34，全部 estimated**，逐项等于 `ceil(len(serialized)/4)+7` 且绑定 fingerprint 一致。初次探针误写 TokenCount.value 而中止，按实际 ABI 改为 tokens 后独立重跑三项全通过；没有产品修复或把失败记为 PASS。
- 上述只证明现有实际依赖适合这个估算接口、endpoint 存在需保留的差异。没有验证任何真实模型容量、token准确性、生成质量、生产部署、安全 source consumer 或新 profile 实现。

**保留边界：** 不批准 production capacity/profile、exact counter、配置加载器、endpoint实际激活、router/native callbacks、source/DB/schema、多模态、SSE/UI。F44-R1/R3/R5及相应原owner依赖保持未关闭；本轮没有复审其并发返工。provider/helper/CI 早前范围 closures 保持，不重跑全套代替本次合同判断。

Write-back：仅追加本原 review，前缀原字节不变；候选合同只读，未写产品/测试/工作流/共享合同/Git/DB/服务/私有memory/共享workbench，未调用模型。后续实际 code/tests 仍由原开发与原 reviewer 交付；controller 负责登记、集成及提交。


## R3-A 冻结代码独立验收；§§20–21 限定合同复核 — 2026-09-28

**代码结论：ACCEPT — 仅 R3-A pure text-only profile resolve/schema/estimated counter slice。未发现本精确代码候选需要返工的缺陷。F44-R2 在该实际实现范围验证通过。** 独立执行 **364 passed in 0.87s**（183新profile + 64helper +117provider），并另行执行48项独立定向检查、192项JSON形状变异。该结论不包括生产配置、R3-B builder、原生循环/来源/事务/图像/SSE/UI；CI托管收集仍待下述明确动作。开发者此前364通过保持 developer/controller evidence，本节是新的 reviewer execution。

### 1. 固定候选与审查边界

分支/HEAD保持 `work/issue44-chat-runtime` / **b0e30fb24d3c119573ea7a5d1a7b1607da2fc602**。完整读取两个实际新文件及开发证据，对照已接受261864小合同；`git diff --exit-code -- apps packages .github` 为0，已有跟踪产品/adapter/shared ABI/CI没有静默修改。两个新文件仍是未跟踪候选；reviewer没有stage或Git写入。

| 文件 | 审前/审后相同 SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` | `C3F5DF0BBC9FF52259AFCEE07A2C5DC4DA53CEE6472788B67536F7CED073CDF8` |
| `apps/api/tests/test_chat_runtime_profile.py` | `E0EC4B923A191E65068ECF4DB4CD327A7C79D54DD47EDCB0C3E2B71E719BA823` |
| `evidence/issue44-provider/chat-runtime-profile.md` | `F21B9D9FF6B2B85518C06A975D13426E634C26E767C621207381079F499A17D6` |
| `lanes/issue44-profile-binding.md` | `26186416599BC39E3732F2842F77E84F4D6F6B347D461578EDA2D16E83976338` |
| `lanes/issue44-chat-loop.md` | `5D032056A20E89D394A781303F37F698AB09EE63EA9BAC4D030486E0E9DE7A0F` |

后三路径相对 `specs/v5/memory-management/`。本次结束前 profile-binding 仍为原71行，没有出现新的 builder endpoint 小表；不等待并发文档。R3-B 保持上节明确的endpoint小表/校验位置门槛，不阻塞此次代码判定。

总体 oracle 仍是有效v4/A1选2：同一任务内的工具续轮/问题后多次自动压缩、冻结预算、原始来源和不重复副作用/发布；共享消费路径全部排除私有内容。R3-A没有内容消费、来源授权或任务执行，不能借本次绿灯推导全目标完成。

### 2. 实际代码判断

| 检查 | 判断与精确代码证据 |
|---|---|
| strict selector / revision | PASS。142–186行先验证实际ModelConnection，在同一对象上调用可信fingerprint；全registry严格验证后按fingerprint/source/revision/nativeProtocol匹配并核对model/provider。原协议映射和adapterVersion在entry校验中封闭；重复ID/selector拒绝，不选第一个。 |
| secret-safe / drift | PASS。callback异常与编码错误转换为固定ProtocolError且抑制原exception显示；结果的connection/profile/counting字段不进repr。201–214行hash含raw-base哈希、timeout、app/effective输出及完整entry，不明文存凭据。真实指纹函数的合成执行下，secret轮换使旧条目拒绝；相同旧fingerprint的raw尾斜线变化仍产生不同runtime绑定。 |
| 不可变配置 | PASS。_entry复制所有允许的嵌套mapping，_freeze递归转MappingProxyType；其余允许叶子均为不可变标量，images固定None。外部registry/counter参数/watermark变化不改变已有profile/counter含义。原ModelConnection为冻结dataclass。 |
| min caps / request reserve | PASS。188–198行对应用/物理输出取min，超额reserve拒绝而非夹小；H受inputCeiling与context-reserve-safety双限制，水位floor严格有序。正整数拒绝bool，有限数值/溢出/编码失败安全处理。 |
| estimated / 实际serializer | PASS。137–139行只实例化现有CharacterEstimateCounter，215–218行复用现有CountingProfile/Capabilities。无exact实现、常量counter或通用port副本；实际完整工具消息序列经三协议serializer计数并保留estimated标签与同一runtime identity。 |
| scope / structure | PASS。220行模块承担纯校验与绑定；没有build/NotImplemented占位、snapshot端点推测、settings/secret loader、DB/HTTP client、router或循环状态。小函数拆分与局部不可变数据足够，没有新增服务/框架。 |
| production/transaction/source/UI | NOT APPLICABLE于本代码验收，后续activation仍BLOCKED于相应原owner交付与实际证据。 |

### 3. 独立执行，非转述开发输出

解释器：`D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`；环境 `PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，PYTHONPATH精确指向本worktree的 `apps/api/src`、`packages/memory-service/src`、`packages/backend-contracts/src`。

实际运行如下五个路径，公共args为 `--noconftest --strict-markers -p no:cacheprovider -o pythonpath= -o xfail_strict=true -q`：

```text
apps/api/tests/test_chat_runtime_profile.py
packages/memory-service/tests/test_chat_loop_turns.py
packages/memory-service/tests/test_native_provider.py
packages/memory-service/tests/test_token_counting.py
packages/memory-service/tests/test_wire_provider.py
```

注入MetaPathFinder，仅放行 `ai_pdf_api` / `ai_pdf_api.services` 包容器及两个实际纯模块 `chat_runtime_profile`、`model_config_types`；其余API模块和全部Worker导入拒绝。这不是“零application模块导入”的泛称。socket.connect/connect_ex/create_connection/getaddrinfo全部拒绝；开跑前断言profile和共享contract的__file__为本worktree。pytest plugin禁止collection/runtime skip、任何wasxfail、deselection，要求恰好364收集；退出后再次核对module边界。结果 **364 passed in 0.87s；total=364；guards_bad=False；exit0**。没有PG收集、conftest、pytest cache或bytecode写入。

另行inline反例脚本禁止HTTP/SQL依赖及上述非白名单应用导入，独立执行：

1. **真实fingerprint依赖与新resolver组合。** 从现有capabilities.py AST提取原CapabilityProfile、connection_profile及其实际normalization/hash/secret helper；仅注入虚构pepper、research常量与stdlib，不加载真实settings/凭据。revision1→2时原fingerprint相同，真实新resolver拒绝旧selector；secret/model/provider/protocol/source/timeout/output漂移拒绝。raw base仅增加尾斜线时原normalization hash相同，新runtime raw-base绑定不同。
2. **27组上限组合。** physical=(20,150,300)，app=(10,200,400)，reserve=(1,min,min+1)逐组验证精确effective/H/soft/target；越界均得到chat_output_limit，不静默clamp。
3. **192组形状变异。** 对24个entry字段逐一替换None、[]、{}、True、False、0、1、空字符串；只允许符合原字段类型的值形成冻结estimated结果，其余均安全ProtocolError，无未捕获类型异常。该实验只覆盖普通JSON形状，不声称任意恶意Python Mapping对象的沙箱安全。
4. **完整工具轮次三协议计数。** system+user+assistant文本/lookup(call1,{x:值})+匹配tool结果，携带真实ToolDefinition，经实际serialized→CharacterEstimateCounter；手算 `ceil(len(payload)/4)+8` 与结果一致，Responses/ChatCompletions/Anthropic分别 **142 / 156 / 139 estimated**。检查各协议call ID/result ID原生字段与系统/工具内容；非字符精确token断言。调用方随后修改嵌套参数/水位并清空registry，原counter结果不变。counter对不同fingerprint/model/context capacity的snapshot均拒绝。

定向脚本汇总 **48 checks PASS +192 JSON mutations**。没有调用provider、模型或远程服务；实际serializer计数证明接口/估算来源，不能证明真实模型计量准确度或容量足够。

### 4. CI交付门槛，最小后续动作

当前 `.github/workflows/memory-provider.yml` 仍只显式选择原181项；新183项尚无hosted收集，本轮没有把本地364当作hosted结果。原中立job的NoApplications禁止全部API，不能直接塞入新API测试并绕过guard。

**最小方案：** controller给原developer单独workflow租约后，在既有provider workflow增加独立的pure-profile job/runner，复用冻结API uv环境与本地共享contract断言，仅收集 `apps/api/tests/test_chat_runtime_profile.py`，使用本节精确API白名单、网络拒绝、无conftest/cache/plugin与skip/xfail/deselection/空收集门禁。原181 neutral job及其严格application denial原样保留，不改#42 ci.yml、不收集PG。无需新增测试框架或修改产品。该CI delta另行独审并看controller推送后的hosted证据；R3-A局部代码ACCEPT可先交付，CI/PR合并门槛不豁免。

### 5. 精确5D032056合同 §§20–21，保持原owner gates

已完整读取两节，以下是合同修正复核，不是其不存在实现的测试通过：

- **R1：先前重放反例在文稿层得到修正。** §20分开稳定client-intent和首次execution-binding，保留省略/显式parent含义；当前授权后先查两类幂等身份，再做新请求解析，合法重放不重新调用preflight/native writer。方向符合原发现。#43仍须交付精确存储/transaction接口并证明双键交叉冲突、并发唯一键输家全回滚、lost ACK、成功/叶子/配置变化后同IDs、撤权拒绝；未批准schema，未关闭runtime gate。
- **R3：单authority与owner链修正正确，精确接口对齐仍未关闭。** 文稿撤回#44自建repo search/read和request_manifest独立authority，保留strict v1、显式新v2、#43 issuer→#42 source/query/range。当前只读原#42 source文稿SHA **2BEFEA01C88FF5FC7D3F8F54C23C9F22B9BB850DD5619DBF819D1091DCF3C042** 已进一步规定read cursor不含connection/counter fingerprint、context_version或renewable lease；每页使用当前授权snapshot/counter重新计数。#44 §20仍写“stable paging/count-capability identity”，不能把它实施为固定模型/counter指纹。请原#44 developer与#42/#43 owner明确仅固定paging policy及来源/权限窗口身份，将counter/profile/当前request全部留在per-page budget记录和当前dispatch授权。原#42文稿为并发工作稿观察，不据此自授它的approval；最终签名/commit仍待原owners确认。这个小对齐不影响R3-A。
- **Usage：文稿保留reported零、原nullable/source和estimated，不把known estimated改报reported；sent uncertainty保留reservation。** #43 metadata-only结算实现与回放/late/revocation证明仍待其owner，#44不得复制算术。
- **R5：错误的“现有bounded loader”声明已撤回，§21覆盖source读前限额、decode/render前分配、aggregate和cleanup，是合理的原owner修正方向。** 实际canonical image路径确为PNG，在image.load后才检查format/geometry；本次只读再次确认这一旧边界。拟议资源预算、隔离硬内存/时间边界、预计算PDF最终transform都尚未实现或批准。原native owner须给出受限资源实现、旧PNG bytes/order/detail和PDF clip/rounding parity、并发aggregate/恶意输入实证；不能从本设计文字生成新worker/schema授权。R5多模态activation继续受限，文本profile不受影响。

原#43 interval B34设计hash仍一致；并发C1/C2/C3/predicate修正不在本次code验收。其设计批准与实际core acceptance分开；本review不关闭#43/source残留或豁免外部服务/合并门禁。provider/helper既有closures保持。

Write-back：只追加此原review。追加前SHA **142E1B324B79A6F09D0E0674BA2479286ADB5737367F25C0A825E62748C3DB0E**，原字节前缀完整保留。候选代码/测试/证据/合同hash均复核稳定；无产品/测试/CI/shared ABI/schema/Git/DB/service/private-memory/shared-workbench写入，无live/paid模型。返回原developer/controller继续各自已有职责，不创建第二实施owner。


## R3-A CI / R3-B endpoint 小合同分别复审 — 2026-09-29

**CI：ACCEPT，可由controller提交此冻结workflow。** 已关闭新183项未被独立CI收集的文档/选择门槛；hosted Ubuntu实际执行仍待push后的独立证据。原R3-A代码ACCEPT不变。

**R3-B：endpoint matrix、raw/final validation与transport lifetime设计接受；完整snapshot/builder还需下述 F44-B1 一项小修正。** 原developer可先实施已明确的endpoint选择/验证及其负例，凭据进入snapshot的部分须先补齐原生normalization语义。无需等待#43/full runtime，不增加实施owner或框架。

### 1. F44-B1 — P2，仅R3-B：snapshot凭据缺少旧原生trim语义

位置：`lanes/issue44-profile-binding.md:103`（§5步骤4：pinned model/credentials）；实际 `providers.py::_normalize_api_key`、OpenAIGenerationProvider/DeepSeekGenerationProvider构造函数与 `adapters/_generation.py` header构造。

旧原生provider在构造时对api_key执行strip；ChatCompletions继承相同构造路径。server_connection直接携带settings中的key；Settings字段没有全局str_strip_whitespace保证。已接受R3-A允许两端含空白、内部非空的key；可信capability fingerprint也使用规范化secret。中立adapter只用strip检查是否为空，随后原样将snapshot.api_key写入Bearer或x-api-key。

**独立实际反例：** 使用完全合成key `  synthetic-key  `，执行实际 `_normalize_api_key` 原函数AST得到 `synthetic-key`；将raw key按§5当前直接copy解释装入真实ModelConnectionSnapshot，分别执行三个实际adapter的stream_turn到内存transport（立即503，无网络）。捕获的Responses/ChatCompletions Authorization均含额外空白，Anthropic x-api-key也保留空白；三者均不同于原生normalize后的header。这是实际header构造差异，不声称测试了尚不存在的builder，也没有使用真实secret。

**最小返工：** 原developer在步骤4明确：仅从已绑定的原connection取key，按既有 `_normalize_api_key`/等价strip规则得到snapshot凭据；空白-only继续安全拒绝，不接收第二key、不修改原connection、不改全局fingerprint、不把secret加进hash/repr。build测试加入带首尾空白和空白-only的合成key，检查三类真实adapter的最终header、zero-send拒绝和safe errors。可复用原helper，不为此创建新credential服务或修改neutral adapter。此项不重开R3-A或原provider/helper closure；它只保护新API composition的原生行为。

### 2. 精确候选和原批准范围

HEAD仍为 **b0e30fb24d3c119573ea7a5d1a7b1607da2fc602**，分支 `work/issue44-chat-runtime`。审前/审后以下hash均稳定：

| 文件 | SHA-256 |
|---|---|
| `.github/workflows/chat-runtime-profile.yml` | `4A816968A145398CF6EEBF32BED98A24C5845A75A004CCE2184B4BAB84B24F06` |
| 原 `.github/workflows/memory-provider.yml` | `BBEF4AED401E013E1E09A0206D2BD8FC01635DE1B54B5C7FC3F52974873EC091` |
| `lanes/issue44-profile-binding.md` | `06C1837F709D2BA7E01ACC69A26D3F3F3474E653C89E01DD6A13760408455647` |
| `lanes/issue44-chat-loop.md` | `721738B24F85957985BB91E2AF632ED698DA664F47C79D4E4F34A02288594C9D` |
| `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` | `C3F5DF0BBC9FF52259AFCEE07A2C5DC4DA53CEE6472788B67536F7CED073CDF8` |
| `apps/api/tests/test_chat_runtime_profile.py` | `E0EC4B923A191E65068ECF4DB4CD327A7C79D54DD47EDCB0C3E2B71E719BA823` |

lane路径相对specs/v5/memory-management。更新后的开发evidence `evidence/issue44-provider/chat-runtime-profile.md` 观察hash为 **0D9D1FAF77BD7C62FB00144D43CB646EB81466F84DC608685CF319420EAC9ED4**。其中developer/controller执行、任何“本轮独立”标签均按其实际身份归类为开发/controller证据，不替代本appointed reviewer的下述执行。

有效v4/A1选2目标不变：同问题任务内压缩与续跑、共享上下文排除全部私有数据、原始来源/预算/效果不漂移。本CI只验证未激活的pure profile；无production registry、exactcounter、source/security consumer、native交易或loop/UI验收。

### 3. CI实际YAML、heredoc与正负控制

**静态 PASS：** 新独立pure-chat-profile job，ubuntu-latest、10分钟上限；仅contents:read，普通pull_request/main push，无pull_request_target、secret、付费模型或提权步骤。使用冻结API uv lock/env、明确三个local PYTHONPATH根、只选一个专属API测试文件；不改#42 ci.yml或原neutral工作流。原neutral hash保持已接受BBEF4AED…，原全application denial未放宽。

从实际文件用已缓存PyYAML BaseLoader读取，核对on/permissions/job以及run标量；Python AST解析原heredoc，Git Bash `--noprofile --norc -n` 对实际run标量通过。没有安装包或下载。以 `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -c <exact body>` 执行原始heredoc Python正文，未修改任何正文字符。环境为PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1与本worktree三路径；本地没有运行uv sync/联网，也未声称已在Linux runner实跑。

实际正文只允许API包容器+两个纯模块，其余API/全部Worker拒绝；socket构造/socketpair/create_connection与DNS入口拒绝。profile及shared contract均断言来自当前worktree。plugin要求恰好183 collected且183 passed call reports，同时拒绝skip/deselect/wasxfail；collect-only不能冒充执行。

| reviewer执行 | 结果 |
|---|---|
| **实际原始runner** | **183 passed in 0.59s，exit0** |
| selected test_path改为不存在路径，仅内存副本 | exit1，required chat profile test file is missing |
| 增加--collect-only，仅内存副本 | 183 collected，exit1 |
| -k排除exact_mapping，仅内存副本 | 180 passed /3 deselected，exit1 |
| collection hook给第一项mark.skip，仅内存副本 | 182 passed /1 skipped，exit1 |
| 第一项xfail(run=False)，仅内存副本 | 182 passed /1 xfailed，exit1 |
| 第一项xfail(strict=False)实际成功，仅内存副本 | 182 passed /1 xpassed，exit1 |
| 原guard prefix直接尝试4个禁止导入 | settings/workspace_models/routers.chat/Worker均AssertionError |
| 原guard prefix直接调用8个socket/DNS入口 | socket/create_connection/socketpair/getaddrinfo/gethostbyname/gethostbyname_ex/gethostbyaddr/getnameinfo均AssertionError |

所有negative runner副本只存在进程内，不改产品/测试/工作流，不删除或移动文件。禁止导入在真实模块执行前拦截；网络函数均已替换后才测试，无实际连接/DNS。以上是本reviewer新证据；开发侧183计数不参与代替本结论。

**CI scope ACCEPT，可冻结提交。** Hosted执行、uv frozen安装与PR required-check设置仍由controller后续确认，不豁免其他service/merge gates。未来增减测试需同步明确收集/执行计数，不能删除guard使未知选择变绿。

### 4. R3-B endpoint/lifecycle，已消除的门槛与实施边界

新增§5给出了精确source/provider/raw-protocol白名单：workspace/openai exact-base，server/openai规范化v1，server/deepseek/anthropic_messages才执行DeepSeek rewrite；其余组合拒绝。server ChatCompletions是明确新neutral映射，文稿没有虚称旧server factory已具备同一路由。该显式支持范围适合本text-only slice。

**独立helper执行 PASS：** 从实际capabilities/model_endpoint/providers AST提取原normalize/validate/origin函数（native normalizer内部import仅接到实际提取的normalize函数），注入空的合成private-origin策略，不导入真实settings/credentials；五类raw path×尾斜线两变体×五个路由组合，**50个最终endpoint/同源断言通过**。这覆盖文稿20个server normalizer组合，并加workspace exact及两类ChatCompletions suffix。另7个空白、HTTP未授权、metadata、userinfo、query、fragment、encoded-path样例均被实际validator安全拒绝。此为实际旧helpers的执行，不冒称新builder已测试。

raw/final校验、同源比较、保留raw-base hash、延迟settings依赖导入、snapshot构造时点现在明确；读取profile._connection仅限API-local trusted composition，不新增第二connection/endpoint override。现有model_client仍拥有真正origin/DNS/IP enforcement；无DNS的URL校验不替代dial admission。composition先关闭活跃iterator、再退出client上下文，正常/异常/cancel/unknown均覆盖，原F44-R4生命周期设计closure保留。

**可独立推进：** 原developer在已授权的同一API module/test内实现表驱动的endpoint选择/校验与合成失败测试；保持R3-A import/resolve路径不加载settings或HTTP client。F44-B1一行语义及对应测试约定补齐后，可完成snapshot+三类既有adapter+estimated counter的builder；无需新增owner或等待43。实际构造/取消能力/URL-origin负例/迭代关闭/客户端关闭证据仍须之后按精确代码候选独审。本轮不批准route activation、production条目/loader、真实capacity或exact counter。

新builder测试若需受控settings/transport依赖，应单独明确fixture和CI选择，不能把当前pure-profile job的API白名单整体放开；先保持冻结183 pure路径独立有效。

### 5. stable cursor文档修正

精确721738B…的§20（682行）现在明确cursor不含connection/counter fingerprint、context_version、renewable lease、前次request/tool-call ID；每页重新取得当前profile/counter/request授权和预算，容量不足不推进cursor。**先前#44文稿中stable count-capability identity歧义在设计文字层关闭。** 改动保持#43 issuer→#42 source单authority，无第二签名器或API授权副本。

该文字对齐不自动批准#42/#43当前工作稿、实际HistorySession/分页/SQL/重试消费接口，也不关闭其残留实现问题。R1原生幂等/事务、R3来源接口与原owner验收、R5真实读前/解码渲染资源边界仍维持原gate；原provider/helper/R3-A代码ACCEPT保留。

Write-back：仅追加本原review，追加前SHA **7EC60A4E923C158133868C85948BF1291F2FF63FCDEB445BD2596AC03292CB50**；原字节前缀未改。未写产品/测试/CI候选/合同/Git/DB/service/private-memory/shared-workbench，无网络/paid模型调用。controller负责stage/commit/push与hosted核验；F44-B1交回原developer。


## R3-B 冻结builder实现与双job CI独立验收 — 2026-09-29

**最终结论：ACCEPT — bounded text-only builder implementation + updated dedicated CI。F44-B1 CLOSED（实际代码与三协议header证据）。没有新返工finding。** R3-A及neutral provider/helper的既有范围ACCEPT保留；controller可以提交本精确候选，hosted新版builder job仍待push后验证。该结论不包含真实TLS/外网/provider质量、生产profile/capacity/exactcounter、native loop/事务/source/多模态/SSE/UI。

### 1. 目标、基线与精确manifest

先按有效v4/A1选2界定：最终目标仍是同一问题任务内的完整工具续轮、问题后多次自动压缩、冻结预算/来源/效果、共享输出排除所有私有内容。当前真实产品结果仅为未接入router的API-local纯profile与受控provider构造；它不会执行上述循环或授权任何来源。

实际分支 `work/issue44-chat-runtime`，HEAD **7e45cf97329a02cea20016a201b4cd08ed6f3e73**，本候选为其工作区增量。PR52 pure CI八checks全绿为controller提供的先前交付状态，本轮无网络访问核验，不把它用于新版builder验收。新builder仍未push。

| 精确文件 | 审前/审后相同 SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` | `07E901D14F9FD49B1C4DB89FE0A0C6408F7227009D719B365E8F680FA13FAC9E` |
| `apps/api/tests/test_chat_runtime_profile.py` | `CE5ADD454FEF14586F88F15C6D84D5CDBB70EA58CFB882E480EDCFE1C3301EE5` |
| `.github/workflows/chat-runtime-profile.yml` | `354B158CBAEDB1E98E865AC8A5B9C72FED6FF70582CD99567CF60ABD95D4ABA3` |
| 原 `.github/workflows/memory-provider.yml` | `BBEF4AED401E013E1E09A0206D2BD8FC01635DE1B54B5C7FC3F52974873EC091` |
| `lanes/issue44-profile-binding.md` | `287725302D4092490D46F63A5D35CEC7E73195B81774329A28AC6E880A8E4EA7` |
| `evidence/issue44-provider/chat-runtime-profile.md` | `7FB5FD4BAC64F6CE6E124FD724DAF5C8DF92E059F32C868AD80DCC5C1132FC75` |
| `lanes/issue44-chat-loop.md` | `39377E36F20476EBC10BD908A0596723A40534A7137FD45C0E78964487946B42` |

后三路径相对specs/v5/memory-management。实际diff为原module追加一个builder函数及既有DTO类型导入；resolve实现未变。原183测试仅将“builder不存在”断言改为callable且settings/helpers仍未导入，并追加fixture/helper与80项builder class。主runtime文稿只更新小slice交付状态，不产生其他条款新批准。

### 2. 实际实现审查

| 边界/语义 | 结论与证据 |
|---|---|
| F44-B1 native credential parity | **PASS/CLOSED。** build直接调用现有providers._normalize_api_key，trim后构造snapshot；原不可变connection和runtime fingerprint不变。不接收第二connection/key。三个真实adapter最终wire header均使用规范化key；空白-only resolver及builder防线安全拒绝。 |
| pure与lazy import | **PASS。** build调用前不import settings/native providers/model_endpoint；原strict pure job仍能完成全部183。build只在类型/cancel/route检查之后延迟导入既有helper，不新增配置加载器或全局secret。 |
| exact route / raw-final URL | **PASS。** 仅五个source/provider/protocol组合；workspace exact-base与server规则区分。实际native normalizer、raw/final validate与最终同源比较执行，未知组合/非法URL/normalizer换源均zero-send拒绝。 |
| binding / counter / ABI | **PASS。** snapshot使用原model、归一key、同runtime fingerprint、profile物理context和effective output ceiling；counter仍为实际CharacterEstimateCounter/estimated。没有第二port、factory框架、parser复制、shared ABI或全局fingerprint修改。请求reserve仍由实际request admission检查，本builder不创建owner预算。 |
| HTTP ownership | **PASS，composition contract范围。** build只持有注入transport，不创建/关闭client。测试composition使用真正model_client with并finally关闭iterator；正常、构造异常、预取消、流中取消、早关、无完整终态、sent read error和KeyboardInterrupt退出均验证清理。没有实际router/runner消费代码，本结论不代替将来真实consumer必须遵守该生命周期。 |
| unknown / retry | **PASS，adapter边界范围。** 缺usage成功时保留Usage(None,None,unknown)；sent读失败只有安全transport error、无成功终态/自动请求重发。未执行#43 reservation/unknown账本结算，不授予自动重试权限。 |
| production/runtime/UI | **NOT APPLICABLE于本slice验收；原activation gates保留。** |

只读核对实际secure依赖未改：model_transport A9E79ACC…、model_endpoint 6E647925…、providers 8338579B…、capabilities FFE48D99…、shared memory.py B1A0D53B…；neutral _generation.py SHA **F7E2335BA034FB79573799916C80529FF540B186C9D97D21556788AC9D0CAD7A**。无通过更改安全helper来制造新测试PASS。

### 3. 原workflow正文的独立执行

本reviewer从当前两份YAML的实际run标量抽取Python heredoc，未修改正文；缓存PyYAML解析、Python AST解析及Git Bash `--noprofile --norc -n`语法检查通过。以 `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -c <exact body>` 在独立进程执行三个job正文。

PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1；PYTHONPATH指向本worktree的API/memory-service/backend-contracts，builder再使用backend-persistence。没有安装包/uv sync/网络；这些是本地同正文执行，不声称Ubuntu hosted或真实TLS执行。

| 实际runner | reviewer新结果 |
|---|---|
| pure-chat-profile | **183 passed in 0.56s，exit0** |
| secure-chat-builder | **80 passed in 1.77s，exit0** |
| 原neutral-provider | **181 passed in 0.40s，exit0** |

合计444只标识本次实际收集范围；安全判断来自具体边界、失败路径与下节反例。开发/controller的此前444与耗时保持开发侧证据，不代替本执行。

**CI partition验证：** 与HEAD已接受workflow的解析run正文逐字比较，将新增20个pure显式node selector恢复为原test_path一行后，pure run正文完全相等；其环境与job属性亦一致。AST验证当前测试文件恰有20个顶层pure test函数和一个TestChatGenerationBuilder class，所有实际组均被选择，无孤立未收集组。纯job的窄API白名单/socket/DNS/skip/xfail/deselection/count/pass-call门禁没有放宽。新增builder job是独立进程，只允许实际helper依赖闭包；providers→metrics→models需要ORM声明，不启动DB。原neutral workflow字节不变。

**双job各自6项负控制：** 对内存runner副本分别制造缺文件、collect-only、全deselection、单项skip、xfail(run=False)、非严格xpass；**12项均exit1**。原candidate/test从未改写或移除。collector与passed-call双计数保证收集数相同也不能用未执行/xfail冒充通过。未来新增test组应同步显式选择与数目，不能通过删门禁规避维护。

### 4. reviewer另行27项实际secure boundary反例

为避免只重放developer fixtures，另用原builder workflow的实际导入/网络guard前缀运行内存脚本。以fixture隔离真实Settings的env/dotenv/secret sources，实际module路径断言为本worktree。使用真实model_client、ModelTransport、PolicyNetworkBackend、httpcore HTTP解析与真实builder/三个adapter；替换**socket.getaddrinfo返回值**，保留真正 `_resolve` 的ThreadPool/Semaphore路径。只在最后SyncBackend numeric connect处注入独立内存wire peer；其start_tls只记录hostname，不握手。安全URL/IP/origin/peer helper未替换。

对Responses、ChatCompletions、Anthropic各执行下列9种情况，**27项全通过**：

1. **302 redirect到另一个origin**，并主动设置client.follow_redirects=True：adapter的每请求False仍有效；只有一次原host DNS、一次原IP dial/POST，无第二destination，无TurnComplete，响应/client关闭。
2. **307 redirect**同样拒绝，没有重放POST或泄露凭据到目标。
3. **DNS同时返回公网+127.0.0.1**：原policy先校验全部地址，零numeric dial/零request；没有先给公网地址发送后再发现私有地址。
4. **已连接peer与所选IP不一致**：原policy关闭peer，零request bytes，安全transport错误。
5. **已发请求+首text delta后的ReadError**：无TurnComplete；仅一次dial/POST，不自动重发。iterator、response、peer、client均清理。
6. **首delta后取消**：generation_cancelled，无成功终态，response/peer/client关闭。
7. **消费者首delta后主动iterator.close**：在client上下文退出前已关闭响应；退出后peer/client关闭。
8. **完整成功但provider未给usage**：三协议保留双None/unknown，正常终态；不把unknown虚构成0/reported。
9. **pre-cancel**：零DNS/零dial/零request，client退出仍关闭。

每次build都单独检查零DNS/dial、真实normalize helper被调用一次、合成key的tab/newline首尾空白被剥离、原connection和fingerprint不变、counter/snapshot绑定相同。所有实际请求wire均是一条POST；记录的TLS hostname为fixture.invalid。这里的“无重试”指sent/redirect请求不被再次发送，不否认原backend在未发送时按既有逻辑尝试多个允许的连接地址。

另外80项实际专属测试覆盖50个合法endpoint组合、三adapter正常headers、无效raw/final与不支持组合、cancellation capability构造前拒绝、构造异常及KeyboardInterrupt with清理。其synthetic DNS/wire替身范围已经逐项读代码核对；未把替身自身断言当成真实SSRF/peer检查。

### 5. 限制、交付和write-back

**R3-B与本精确双job CI可交controller提交；F44-B1实际闭环。** 新job hosted执行和frozen uv依赖安装仍待controller提交推送后的证据。原PR52八checks绿不代表这次尚未push的builder已hosted通过。

R1原生start/finish/replay事务、R3 #43 issuer→#42 source及cursor实际消费、R5 native图像资源边界仍归原owners；没有schema/native/router/source/loader授权变化。无production registry、容量背书、exact counter、外网模型质量、真实TLS/cert/代理环境集成或UI acceptance。没有凭此宣布#44/#41完成，也不豁免外部服务/合并门禁。

仅追加此原review；追加前SHA **2240D791041557801F5B65F01B842C9B4755956514A5809881552F9974216E56**，原字节前缀完整保留。候选所有hash复核稳定；`git diff --check`通过。无产品/测试/CI/合同/shared ABI/schema/Git写入，无DB/service/private-memory/shared-workbench写入，无paid/live模型或实际UI/network调用。controller负责stage/commit/push/PR；未创建重复实施owner。
