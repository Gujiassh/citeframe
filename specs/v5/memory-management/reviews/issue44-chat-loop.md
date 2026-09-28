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
