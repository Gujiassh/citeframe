# Issue #44 — actual chat tool-loop integration contract

**Runtime integration DESIGN CANDIDATE. Independent approval required. The separately authorized nonpublishing terminal-turn helper is the sole implementation slice in this handoff.**

Baseline: `fb78f83590cbe8a4944a01591922cc6162d27f5c`, `work/issue44-memory-provider`. [PR49](https://github.com/Gujiassh/citeframe/pull/49) is accepted provider foundation, still unmerged. This document contains source-inspection evidence and proposed integration contracts; it claims no runtime/product acceptance. The controller separately authorized only new chat_loop/turns.py, a minimal local __init__.py if needed and dedicated test_chat_loop_turns.py. Existing product/provider files, migrations, shared ABI, model spend and Git writes remain outside scope. Current rework inspection HEAD: `bc73fcb5bfca30e9aaa311c77dd694f3c123c894` (accepted provider/admission dependency integration preserved).

## 1. Authority and scope

Governing documents: local `spec.md` §§12–14 and approved `design.md` §§6–9, especially §7.2. Original proposal is identified in `design.md` at `C:/Users/baiao/Documents/Codex/2026-09-21/ai-ensemble-fork/outputs/Citeframe-记忆管理改造方案.md`; historical inferred-candidate wording creates no admission permission.

Read-only dependency: `D:/Code/citeframe-lanes/issue43-compaction/specs/v5/memory-management/lanes/issue43-compaction.md`. Its selected Option A design/schema baseline SHA-256 is `ED10B657B3DE9862D3601A8917B798AADE08B21E18CB48D66448BC5D2EEEE1E9`. Option A design approval remains valid; implementation acceptance is pending. Its `reviews/issue43-compaction.md` P43-A1/A2/A3 are mandatory integration gates, not waived by its 68 passing pure tests.

Outcome: one accepted chat submission executes bounded tool rounds, crosses context thresholds repeatedly, adopts lawful checkpoints and finishes without another question or manual continuation. Durable effects, authorization, cumulative budget and cancellation survive compaction/recovery. Research integration/evidence authority stays #45; actual UI delivery stays #46.

**A1 final choice 2 is resolved.** All outputs here use existing shared workspace readership. Exclude ALL private data, including the requester's own, before shared prompts, tools, history/source hydration, summaries/checkpoints, planning, streams, logs or final answers. Private storage/management remains separate. No native audience column, private thread/run/mode, guessed author or inferred long-term candidate is introduced.

| Item | Existing accepted versus proposed |
|---|---|
| PR49 typed GenerationPort events, counters, injected transport | Accepted foundation; not called by chat; provider ABI stays unchanged |
| #42 private persistence/shared declarations | Present at baseline; private management access does not grant shared recall |
| Approved design mode2/recovery/history/root-budget contracts | Design intent; absent from current chat implementation |
| #43 owner/journal/snapshot/coverage/atomic adoption | Accepted design dependency; implementation/PG proof outstanding |
| This document's orchestration DTOs, interval placements, result-source activation and SSE detail | New refinements requiring owner and independent approval |
| Actual loop/configuration/index/runner/frontend | Not delivered by PR49 |

## 2. Grounding in actual code

Paths below are relative to inspected baseline; function names remain authoritative if line numbers move.

| Source | Observed behavior / required seam |
|---|---|
| `apps/api/src/ai_pdf_api/services/chat.py::prepare_chat` (69–299) | Discards user_id; validates assets/parent, resolves evidence, embeds/retrieves, builds text/images, creates completed user/streaming assistant plus citations/evidence, commits. No execution/budget identity. Do not infer author from creator. |
| `PreparedChat` (59–66) | Legacy messages/provider and ORM rows only. Introduce separate execution preparation receipt. |
| `complete_chat` (343–382), line 375 | One legacy `.generate(...)`; must gate as well as HTTP streaming. |
| `apps/api/src/ai_pdf_api/routers/chat.py::stream_chat` (229–296), line 267 | One legacy `.stream(...)`; meta precedes try block. No tool continuation exists. #40 still owns router/dependencies. |
| `finalize_chat` (302–318), `fail_chat` (321–340) | Unconditional commits/head writes; fail deletes citation locators. Post-finalize serialization exceptions can enter failure path. New terminal CAS must prevent success downgrade. |
| `_get_message_lineage` (385–404), `active_message_path` (407–430), router `_resolve_parent_message_id` (303–333) | Parent graph authoritative; completed messages enter prompts, failed assistants remain navigable but error prose excluded. Edit branches from edited user's parent. Preserve these semantics. |
| `schemas/chat.py` (342–357,387–394) | Only all_ready/selected; selected-empty invalid. No request/version/history envelope. Existing permissive request model must not silently swallow mode2 fields. |
| `_build_generation_user_message` (450–471) | Real image arrays supported today; neutral GenerationMessage is text-only. Images cannot be silently dropped. |
| `services/workspace_models.py`, `model_config_types.py`, `capabilities.py::connection_profile` | Existing connection lacks physical capacity/tool/counter binding; timeout/output max are insufficient. |
| `services/model_transport.py::model_client` | Origin/DNS, byte/deadline bounds, trust_env=False, follow_redirects=False must survive composition. |
| `apps/web/src/lib/chat/sse.ts` (303–403) | Unknown events ignored; done/error independently tracked, no execution ordering/reconnect contract; citations validate detailed modality envelope. |
| `lib/chat/client.ts`, `lib/use-chat.ts` (330–499) | Immediate delta append, optimistic timestamp IDs, no durable cancel/poll. Active-history reload cannot recover pending execution. |
| `app/api/workspaces/[workspaceId]/chat/stream/route.ts` | Raw body proxy/trusted actor headers; no Idempotency-Key forwarding or explicit recovery contract. |
| `components/chat-panel.tsx` | Ready-asset predicate blocks no-assets Quick chat; history-only needs real UI readiness change. |

Native asset citations/input-evidence remain authoritative. History references do not become asset citations or Research evidence. Avoid adding runner/storage/retrieval/provider responsibilities to one growing `chat.py`.

## 3. Entry and recovery API

Retain approved `design.md` §7.2; prefix `/v1/workspaces/{workspaceId}`, corresponding BFF `/api/workspaces/{workspaceId}`.

- **Mode1:** absent version or protocolVersion=1 preserves existing schema/error precedence, selected-empty/no-ready/no-match, citations and disconnect interruption. Internal execution/context owner uses server identity; no client replay guarantee. Every actual main send, including nonstream helper, still gates.
- **Mode2 strict body:** `{protocolVersion:2,requestId:UUID,memoryMode:'enabled',threadId:UUID,question:string(1..12000),assetScope:{mode:'none'|'all_ready'}|{mode:'selected',assetIds:nonempty_unique_UUID[]},historyScope:'current_branch'|'workspace_history',parentMessageId?:UUID|null,editMessageId?:UUID,selectionText?:string,evidenceTargets?:EvidenceTarget[]}`. Unknown fields reject. None forbids selection/evidenceTargets and skips asset embedding. Other scopes preserve native validation; no retrieval hits may continue with history. Preserve native edit/parent precedence. Model cannot widen history envelope.
- `POST /chat/stream` mode2 requires Idempotency-Key ASCII 8..128. Hash canonical validated body/route/actor/workspace. Same identity with different hash:409. Register execution/request, user, pending assistant, branch binding and frozen policy atomically before meta. Same accepted POST subscribes, never dispatches again. Expensive preflight IO runs outside locks and is revalidated before admission. Native citations/evidence and their source manifests commit consistently before use.
- `GET /chat/requests/{requestId}` actor-bound/current-authorized: `{requestId,accepted:true,executionId,userMessageId,assistantMessageId,version,contextVersion,state,checkpointId,phase,canResume,error}`;404 unknown. Lost meta polls or exact-replays the same POST; never automatically creates fresh request ID.
- `GET /chat/executions/{id}/events`: current authorized snapshot then live events; no missing-token replay promise. Refresh loads messages + execution state.
- `POST .../cancel {requestId,expectedVersion}`: idempotent lifecycle CAS; already succeeded returns succeeded. Cancels future send/adopt/finalize.
- `POST .../resume {requestId,expectedVersion}`: only waiting_context with actionable changed condition and original allowance; same execution/messages, no unresolved-effect replay.
- `POST .../retry {requestId,expectedVersion}`: explicit failed/outcome_unknown retry creates child execution/new assistant sibling under original user; unique retry_of and operation key. Root deadline/policy/budgets retained, ancestry max16. Warn possible duplicate provider cost; unknown side effects still require reconciliation.

Execution lifecycle and diagnostic phase are owner-controlled, not defined by this document or the pure helper. In-progress #43 observations include prepared and cancel_requested; no reduced accepted/running enum is authorized. Pin the exact accepted owner commit and enums before any durable orchestration. Durable runner claims bounded renewable leases; takeover fences old content adoption. An untracked request background task is insufficient. Runner bootstrap/deployment needs composition owner assignment.

Mode2 HTTP errors retain approved structured code/message/retryability/request identity:404 inaccessible/unknown,409 conflict,410 authorized exact-source unavailable,422 request/capability,429 budget,503 transient/index unavailable. No inaccessible-source existence or provider-secret leak. After SSE starts, send safe terminal subscription error; durable execution state remains authoritative.

## 4. Every-main-dispatch gate

Only `prepare_main_dispatch(owner,proposed_input,expected_context_version)` (#43-owned) may authorize initial streaming/nonstream, every full tool continuation, resume, retry and lease-recovery main send. No other direct purpose=main generation call. Summary chunk/merge uses separate bounded tools-empty path without recursion.

1. Resolve trusted actor/workspace output scope, execution/root/branch/lease/cancel/deadline/policy. Refuse unresolved sent calls or pending/unknown groups. Reuse eligible committed results by identity, never prose inference.
2. Capture under #43 guard order: Workspace → Membership → ChatThread → root/current execution → full bounded native message revision manifest → sources/checkpoint/calls. Body inputs follow exact ancestry; sibling metadata only fences mutations. Guard misses abort/release under bounded retry.
3. Assemble ordered originals, valid checkpoint placements, protected anchors, full groups, bounded retrieval, exact tool definitions. Carry direct snapshot/tool dependencies AND original leaves. Whole-output-audience authorization precedes body load.
4. Bind current physical profile/counter/output reserve; count exact final serialized request. H=min(per-call input ceiling,physical context−output reserve−safety margin). Tool/protocol framing is counted, not subtracted twice. Unknown capability or stale/impossible capacity rejects.
5. Apply corrected §5 intervals and #43 hysteresis. At soft threshold with sufficient new eligible units, bounded compaction; adopt only nonempty valid candidate meeting gain and target. Persist no-progress. Original may continue only freshly lawful and <=H; otherwise waiting_context. No necessary-input truncation or repeated unchanged failed boundary.
6. After compaction, recheck native revisions/complete membership, context/parent checkpoint, source/direct uses, output permissions, lease/cancel. Persist exact FINAL main request manifest/hash + reservation atomically. Use the owner-supplied permit and separate authorization/send transition, bound to call/hash/context/lease; obtaining a preparation permit alone is not authorization to send.
7. Durably transition reserved→sent at dispatch boundary; invoke once with no DB guards across IO. Crash in ambiguous send window yields outcome_unknown unless no-send is proven. Authorization linearizes before send; revocation cannot retract transmitted bytes, but prevents subsequent sends/adoption.
8. Provider deltas are provisional. Whole valid TurnComplete required before accepting answer or executing any call. Incomplete/failed terminals, malformed IDs/args/pairing, cancellation or missing terminal cannot execute/finalize. Usage settlement is separate from content adoption.
9. Valid tool turn commits ordered group/members, executes bounded tools, persists full results, then returns to step1. Final answer rechecks native/source/cancel guards and atomically commits assistant/result/references/leaf/execution success. Later subscriber/serialization failures cannot downgrade success.

#44 invokes #43's single snapshot + coverage + uses + native-pointer/context-CAS transaction. It cannot implement a second summary head or advance coverage separately.

## 5. Corrected packing seam — P43-A1/A2/A3

Proposed `OrderedContext=[Anchor|CompleteUnit|SnapshotPlacement]` uses stable native-version/journal-group keys. Protected anchors retain exact position/content. A plan declares disjoint ordered intervals `{firstKey,lastKey,orderedUnitKeys,sourceManifest,parentSnapshotId}` containing only eligible complete units, no anchors. Replacement occupies the original interval position.

Example: `[oldA,oldB,currentQuestion,G1,G2,G3,recentG4]` may become `[summaryAB,currentQuestion,summaryG1toG3,recentG4]`. Later G5/G6 can trigger a second episode without a new user question. A protected constraint inside history splits intervals. Coverage records each original key once in order, while assembly explicitly represents retained anchors/units. No hidden interval hole, sibling body or incomplete batch. Existing snapshot composition must flatten to original coverage/support for validation.

**P43-A1:** current prefix-only planner stops at current question and cannot compact subsequent in-flight groups. Block integration until #43 approves/implements equivalent interval/anchor representation. Proposed `compaction-input-v2` adds ordered placement/interval identities; candidate maps interval IDs to structured summary atoms. If existing single summary body cannot encode placements, #43 owns the ABI/schema amendment. Persist strict versioned placement manifest if accepted; #44 creates no competing coverage schema.

**P43-A2:** compact requests use deterministic non-executable text projection of full groups: group ID, ordered IDs/names/arguments, terminal statuses, result/source refs. Project as attributed data, with tools empty and no executable historical tool_calls. Count the exact final projection with real neutral serialization for all three protocols. Preserve original units for coverage. Escape/delimit source text so it cannot become a trusted system instruction.

**P43-A3:** derive/validate capacity at planning against the current request/profile/output reserve/policy. Stale capacity must reject even if a fingerprint string is unchanged. Recount candidate with same bound capacity and stricter configured ceilings. Character estimation remains estimated; plumbing tests do not establish tokenizer accuracy.

Required #43 regression: one protected question followed by many multi-call groups, crossing soft then hard, two successful eligible interval replacements with exact chronology; constraints splitting intervals; no missing/double coverage. Actual counter/serializer must accept summary projections for Responses/Chat Completions/Anthropic with tools empty and failed/cancelled members. Lower context or raise output reserve after capacity construction must fail before safe-continuation classification.

## 6. Tool journal, full groups and stable effects

Initially allow read-only `search_memory`, `search_history`, `read_source`; execute returned batches sequentially in declared order. Multiple calls in a provider turn remain a complete group. Max calls/args/results derive from frozen policy. No prose tools, implicit aliases or silent text fallback.

Reuse #43 `memory_calls`: purpose=tool_group row, member parent_call_id, exact provider ID/name/validated canonical argument hash. Stable logical identity = server execution + accepted main-call ID + group/member ordinal. Provider IDs pair protocol messages; they are not global idempotency keys. CAS/uniqueness prevents accepting a main result twice; changed args under same logical key conflicts.

Proposed strict `chat-tool-result-v1` manifest:
`{groupId,memberCallId,providerCallId,toolName,argumentsSha256,status,contentRef?,contentSha256?,byteLength,sourceRefs,dependencyRefs,truncated,continuation?,safeError?}`.
States reuse reserved/sent/succeeded/failed/cancelled/outcome_unknown, separately from result availability. Exact membership/order persists before group completion. Each member has one paired terminal result, including known failed/cancelled. Pending/unknown prevents main continuation and group compaction. Never fabricate unknown as failed. Never-started members can become known-cancelled on interruption; possibly sent members stay unknown.

Approved design §9.3 additionally requires repeated normalized query plus identical result IDs/versions twice to return no_new_information. Changed results may permit another bounded call without resetting budget. This progress rule belongs to later owner-bound orchestration, not the terminal collector; call caps alone do not satisfy it.

No-repeat is based on journal/effect identity. Compaction preserves keys. A fresh intentional read may obtain new revisions and spend budget; same-key recovery reuses only the original currently eligible committed result. Explicit retry descendants may reference proven completed results after permission checks without copying billing.

No mutating tool is activated here. A future effect entry requires effectKind, stable business key/version precondition, durable receipt and reconcile(key). Local effect+receipt commit atomically; external effect needs native idempotency/query support. Unknown non-idempotent send stops for reconciliation; model-requested repetition cannot override it. Use a synthetic effect fixture to prove no-repeat through crash/compaction, without claiming a production mutation tool.

Oversized results: persist complete original/hash/length/call/dependency manifest before success; paired result carries bounded excerpt + exact source ref + explicit truncated/continuation. Approved design defaults:16 MiB/result,64 MiB/root including pending uploads, reserved under root guard. Upload/cap failure yields failed result, never successful truncated original. Server-owned object paths never enter tool arguments. Keep originals while live checkpoints/results depend on them; cleanup follows terminal reconciliation, including unknown uploads. Native evidence excerpt semantics remain unchanged.

## 7. History/source retrieval and output-audience authority

`search_memory` uses approved query1..4000, optional kinds/scopeKinds/includeHistory, limit1..20 default6. Shared eligible result currently empty because #42 records are private. Do not enumerate actor-private records and filter after hydration; no shared candidate store is implied.

`search_history` uses query1..4000, scope current_branch/workspace_history/explicit thread+optional leaf, validated from/to, limit1..20 default6 and signed cursor. Effective envelope = frozen server scope intersect current permission. Current branch uses accepted ancestry plus execution full groups. Workspace history may discover lawful shared threads, labels other_branch/other_task, and never changes active-branch membership. Assistant observations are not confirmed user decisions. Strict allowed source-kind enumeration remains the approved design's chat_message/note/content_unit/research_artifact set; only implemented/resolved kinds may activate.

`read_source {sourceRef,before:0..2000,after:0..2000,cursor?}` returns <=2000 tokens by default, exact version/range and bounded continuation. Result: `{sourceRef,content,contentKind,occurredAt,sourceState,provenance,branchRelation,truncated,nextCursor}`. Legacy chat provenance uses actorUserId:null/actorAttribution:unknown where no authenticated author exists. Do not substitute latest revision or infer author from creator. Internal checkpoints/Research evidence use native internal ports, not public tool exposure. Tool-result extension resolves group/member and manifest, never raw object URL.

For search/hydration/read/adoption/checkpoint/send/final output/source opening:

1. Authenticate actor/current membership and execution access; derive existing output readership independently of tool/client parameters.
2. Prove source ACL/visibility covers **every entitled output reader**, including native downstream publication rights. Actor-only authority is insufficient; unknown relationship denies. No private resolver registered in shared path.
3. Validate envelope/kind/branch, exact source version/status/hash, deletion/erasure and transitive summary/tool/raw dependencies.
4. Only then load bodies/snippets. Recheck at adoption and next send. Counts/ranking/cursors must not leak denied sources. Cursor binds actor/scope/query/filter/profile/generation and expires after15 minutes; every use reauthorizes.

Deletion/revocation/revision change invalidates dependent result/snapshot eligibility via direct and raw-leaf memory_uses. Content boundaries synchronously revalidate even if async invalidation/index cleanup lags. Retire stale generation/cursors; embedding cache never grants access. Rebuild only from lawful originals within original budgets, else waiting_context/source_context_conflict. Removing a source label does not make a private-derived summary lawful.

Revocation during generation prevents response adoption/publication; reconcile permitted accounting metadata only. Already disclosed bytes cannot be recalled. Mode2 presentation follows the approved provisional-delta and mixed-turn contract (§9); this nonpublishing helper makes no public presentation decision. Reject late content adoption after revocation and invalidate provisional UI state through the terminal error/reload flow. Provisional bytes already disclosed cannot be recalled. Existing published native messages retain native retention/access policy; this lane does not silently rewrite history or promise retroactive erasure.

### Missing source/index activation

#43 currently activates shared chat_message/research_evidence only. Actual chat also uses asset retrieval/input-evidence and journal originals. Production integration needs reviewed exact native asset/evidence version/hash/locator resolvers and journal tool_result reads, with existing ACL and dependency leaves. Tool result resolves memory_calls; no invented memory_instruction row. Notes/research_artifact kinds fail explicitly until resolver/index generation exists; unsupported kind cannot silently search another corpus.

Approved hybrid history index requires versioned manifests/fingerprints/eligible-source joins. Truthful retrieval metadata is `{mode,indexGeneration,policyVersion}`; a SQL-only prototype must not be labeled hybrid. No fake ContentUnit/Asset. Source/index owner allocation is a blocker, not permission to add schema in #44.

## 8. Continuous budgets and capability configuration

One immutable root execution policy/absolute deadline; lock root then current for admission/settlement, fold descendants. Main/summary/tool calls and admitted embedding/search resource use are bounded. Reserved/sent/unknown retain conservative reservations; settled usage is reported or separately labeled estimated. No refund/reset on timeout/cancel/retry/checkpoint/refresh. Idempotent call settlement cannot double bill. Report unknown usage; character counts are not exact billing.

Freeze main/tool counts, episodes/chunk/merge caps, total summary/input/output/result storage and deadline. Reserve next-answer headroom before compaction. Check per-call and cumulative limits before every remote send. No-progress key covers owner/context, ordered intervals, direct/raw source manifests, parent snapshot, policy/profile. Unchanged failed frontier cannot generate another automatic episode; new complete groups may qualify within remaining budget.

Proposed API-layer `ChatCapabilityBinding`:
`{connection:ModelConnectionSnapshot,toolsSupported,textSupported,multimodalSupported,counter:TokenCounter,counterId,counterVersion,countMode,profileFingerprint,policyFingerprint,physicalContextTokens,outputReserve,perCallInputCeiling,safetyMargin}`.
Runtime credentials stay injected, never durable/logged. Explicitly map existing anthropic_messages→neutral anthropic and construct protocol endpoint. Preserve secure origin/DNS/no-redirect/no-environment-proxy/byte/deadline transport by API composition; neutral package imports no app settings/credential loaders.

Deployment-approved versioned registry/config supplies capacity and counter; no name guess or paid capability probe. Unknown tools/capacity/counting rejects before send (`capability_unsupported`, `context_capacity_unknown`, `memory_counting_failed`). Changed workspace connection revokes old dispatch binding; explicit safe rebinding/new fingerprint/recount under original remaining policy required, no budget expansion.

Text-only orchestration may be the first explicitly limited implementation slice. Current image support blocks full mode1 gate parity and visual mode2 activation until separately reviewed multimodal ABI/serialization/counting. Unactivated legacy visual route can remain unchanged; it cannot count as satisfying this every-dispatch contract. Text extraction cannot silently replace image input.

## 9. Normative SSE compatibility and UI hooks

Approved `design.md` §9.4 remains the wire/presentation authority. This table preserves its required envelopes verbatim. No event replacement, renamed phase, mandatory sequence field or new terminal presentation delay is introduced. Owner IDs in context_compacted are the same explicit executionId/runId/stepId/attemptId nullable owner tuple used by context_status; chat supplies executionId and null Research IDs.

| Event / surface | Normative required envelope / behavior | Compatibility disposition |
|---|---|---|
| Mode1 meta/delta/citations/done/error | Existing payloads, timing and semantics unchanged | Unchanged; strict mode2 validation cannot alter legacy parsing |
| Mode2 meta | Existing threadId/userMessageId/assistantMessageId plus `{protocolVersion:2,requestId,executionId,version,contextVersion}` | Approved additive mode2 fields |
| memory_status | `{executionId,phase:'searching_memory'|'searching_history'|'reading_source',callId}` | Unchanged approved mode2 event |
| context_status | `{executionId:null|ID,runId:null|ID,stepId:null|ID,attemptId:null|ID,contextVersion,phase:'compacting'|'resumed'|'waiting_context',operationKey,checkpointId:null|ID,reason}` | Unchanged; phase is resumed |
| context_compacted | `{...owner IDs,checkpointId,coveredThroughUnitKey,unitCount,beforeTokens,afterTokens,countSource,counterVersion,policyVersion,durationMs}` | Unchanged; emit only after atomic checkpoint commit |
| history_sources | `{executionId,items:[{sourceRef,contentKind,excerpt,provenance,occurredAt,branchRelation}],truncated}` | Unchanged; separate from native citations |
| memory_saved | `{operationId,memoryId,version,indexState}` | Unchanged; only after an actual authorized durable explicit save. This helper performs no saves and no inferred admission |
| Mode2 delta | `{executionId,text,provisional:true}` | Unchanged provisional presentation; not proof of terminal answer acceptance |
| Mode2 done | `{threadId,assistantMessageId,executionId,version}` | Unchanged; only after accepted final answer |
| Mode2 error | `{executionId,code,message,state,retryable}` | Unchanged; no subsequent done |
| Native citations | Existing citation envelope | Unchanged; history refs never substituted |
| execution_state / tool_status / sequence | Not introduced by this contract | No silent replacement of approved status events; future additive proposal needs explicit owner review |

Buffer mixed text/tool turns until their type is known. Do not expose reasoning/tool arguments as completed answer. Preserve approved provisional answer streaming; waiting for every answer to complete and commit before emitting any text is not authorized. Whole-turn validation gates tool execution and durable answer adoption independently of public provisional presentation. The helper in §11 is nonpublishing and cannot impose a buffering policy on SSE. API/#46 must implement type-known presentation with the actual provider stream and prove first-text/progress/cancel/reload behavior; pure collector fixtures do not establish it.

Version discriminator and strict mode2 validation retain the exact required envelopes above. Validate execution/message identity and one terminal outcome; no done after error. Parser bounds and malformed-frame handling for mode2 are implementation requirements, not new wire fields. Existing legacy unknown-event tolerance is not execution recovery. A resumed subscriber receives current authorized status plus future events reconstructed from persisted call/checkpoint metadata; no model replay and no promise to replay missing text deltas. Use existing approved status envelopes, not an invented execution_state replacement. Refresh loads committed messages plus execution status; unfinished text remains provisional.

Mode2 subscription loss does not cancel accepted business execution. Explicit cancel commits durable flag/version, signals cooperative provider/tool cancellation and fences late content adoption; sent unknown calls keep reservations. Lost acceptance must be polled before cancel can target execution. Mode1 preserves interruption failure, including meta closure. Transport deadlines bound blocking IO; runner shutdown/lease expiry preserves durable work.

#46 hooks: persist request ID/key for acceptance recovery; history scope/none asset scope and no-assets readiness; organizing status returning automatically to same task; cancel/resume/retry driven by durable state; separate full-provenance history refs; source-unavailable and provisional-error/reload state. Bind callbacks to submission/account/workspace. BFF forwards Idempotency-Key/control endpoints with trusted identity; browser abort closes subscription only. Successful compaction needs no continue button or new message. No UI/SSE files are changed by the authorized helper slice.

## 10. Exact proposed contracts/schema deltas

These are owner handoffs before code, not existing declarations. Reuse accepted ports and tables; no duplicate owners.

| Surface | Necessary delta / owner |
|---|---|
| `citeframe_contracts/memory.py`, root exports | Provider ABI unchanged. #42 exclusive edits; no #44 port clone. |
| Shared orchestration DTOs | Deferred to exact accepted owner API/controller assignment. No new chat_loop.py ABI, lifecycle enum, receipt wrapper or root export. Module-local turn results reuse GenerationEvent/ToolCall/Usage/ProtocolError. |
| #43 `compaction.py`/manifest versions | Corrected interval/anchor placements, physical binding, typed single-use dispatch receipt; #43 owns final signatures and storage changes. |
| #43 chat_memory_executions | Reuse owner/request hash/uniqueness/retry ancestry/branch/state/version/context pointer/policy/lease/cancel. Require durable validated history/asset envelope and request schema version. If absent from final accepted schema, propose strict `request_manifest JSONB NOT NULL` with canonical hash and scoped request/key uniqueness. No second execution table. |
| #43 memory_calls | Reuse journal/group/member/input/result/reservation/usage. Strict §6 JSON result manifests; missing composite membership FK/uniqueness assigned to #43 before freeze. |
| #43 snapshots/coverage/uses | One adoption transaction; §5 placement amendment reviewed by #43. Ordered original source/group/version identities stay authoritative. |
| Shared sources/index | Exact asset/evidence/tool-result resolution and audience/dependency checks; any enum/check/table changes explicitly #42/#43-owned; controller assigns index lane. |
| Native ChatMessage/ChatThread | No audience/guessed-author column; reuse content/status/leaf/citations. Option A revisions remain #43-owned. Terminal execution/native CAS is #44 service command after handoff. |
| API request/control/status | Strict discriminator and §3 endpoints; #40-controlled paths await transfer/integration. Preserve v1 shapes/errors. |
| Web types/parser/BFF/hooks | §9 mode2 state machine, #46 with controller route coordination. |

### Mandatory owner handoff before durable orchestration

No start/load/accept_turn/complete_tool/finish wrapper or six-DTO shared layer is implemented now. Required record before the next production slice:

| Record | Current status |
|---|---|
| Exact contract commit and callable/module ownership | Pending accepted owner handoff; working files are observations only |
| Preparation versus send authorization | Observed `DispatchGate.prepare_main_dispatch(owner,template,coverage,runtime_policy,*,expected_context_version,logical_key,mode,recent_units,protected_keys)` returns local DispatchPermit; observed `authorize_send(permit,runtime_policy)` performs archive/check/send transition. Signatures are not frozen here; permit alone never authorizes transport |
| Lifecycle enum | Owner exact enum required, including prepared/cancel_requested if retained; no parallel authority |
| Start/replay/finish/group APIs | Exact atomic signatures, unique keys, error/replay rules and expected-version/lease guards required |
| Accounting | Exact AccountingReceipt call/workspace/owner/request/native-ledger identity and UsageSettlement nullable/unknown mapping required; provider Usage is not automatically a persistence settlement |
| Source and budget | Actual owner guards/fold/reservations/late settlement required; no dummy authorizer/journal or second counter |

The operations below state required atomic outcomes only. Python interfaces/schema refinements need named-owner approval and remain outside helper scope.

Atomic boundaries:

1. Start registers execution + native pending pair + request replay identity together; before meta.
2. Accept-turn CAS commits provider result + complete declared member list once; no tool executes before acceptance.
3. Complete-tool commits verified original reference + dependency edges + terminal member; group complete only when all paired members known terminal.
4. Finish commits lawful final result/references + assistant/leaf + terminal execution once, under native/context/source/cancel guard.
5. Unknown DB ACK reconciles unique operation/call on fresh Session; object existence/missing SSE proves neither commit nor rollback.

Accounting after revocation/cancel uses #43 metadata-only settlement receipt and fresh short-lived Session; no content/source hydration or adoption. Preserve reserved unknown costs. Accounting permission never grants content permission.

## 11. Authorized immediate slice and later ownership

**Controller-authorized now:** one cohesive nonpublishing terminal-turn collector/transition helper in `packages/memory-service/src/citeframe_memory/chat_loop/turns.py`, minimal local `__init__.py` if needed, and `packages/memory-service/tests/test_chat_loop_turns.py`. No state/engine module, shared ABI/root export, fake journal/authorizer/compactor or budget counter.

Responsibilities:

1. Consume parsed GenerationEvent values. Preserve completed ToolCall IDs/names/arguments/order and Usage values/source including None; no provider parsing duplication.
2. Keep provisional text/calls locally; accept only after valid matching TurnComplete and stream completion. Bound events/text/calls/arguments; reject missing/contradictory/duplicate terminal, invalid completed call set and cancellation before acceptance. No publication or tool execution.
3. Return local accepted-answer/declared-group or error/cancel/unknown stop. Pair result sets by original IDs/order; failed/cancelled explicit, pending/unknown block continuation.
4. Complete result transition returns only gate_required with supplied execution/root/call identity unchanged. No permit, transport, effect journal or source authorization. Durable no-repeat/budgets remain owner's responsibility.
5. Actual accepted neutral DTO/counter/serializer compatibility is tested deterministically with synthetic provider fixtures. No fake compactor or scripted gate counts as #43 conformance.

Later owners:

- #43: corrected packing, accepted signatures/authorization-send/accounting, shipped PG/native/atomic proof. Integrate exact controller-approved commit.
- #42/controller: exports/dependencies/config/locks/deploy; assign source/index and runner composition.
- #44 after relevant #40 handoff: focused API service/composition/native preparation and terminal integration; overlapping router/deps/schema explicitly transferred. Neutral helper does not wait for #40.
- #46: approved SSE/parser/BFF/client/UI presentation and recovery. #45: Research evidence/native publication and ledger consumers.

Production loop requires accepted owner interfaces and runtime prerequisites. This helper is independently useful protocol-to-loop preparation and does not establish loop delivery.

## 12. Acceptance oracles and genuine blockers

Independent review starts with actual same-submission outcome/A1 and scope. Foundation test counts/hashes do not establish loop delivery.

| Oracle | Required evidence |
|---|---|
| Gate completeness | Actual streaming/nonstream/continuation/resume/retry/recovery instrumented: transport only receives current single-use receipts and exact counted payload hash. |
| Same-task compaction | One question, multi-call rounds, two threshold crossings without new message, exact chronological anchors/intervals/recent groups and final answer. Protected middle constraints, no omissions/double coverage. |
| Real provider compatibility | All three neutral serializers/counters accept tools-empty summary projection; failed/cancelled members preserved; stale capacity/output reserve rejects. Independent P43 findings closure. |
| Recovery/no-repeat | Before send/ambiguous send/result-before-commit/lost ACK/after checkpoint crashes; one terminal effect receipt, original unknown reservations, stable result identities. Synthetic effect fixtures labeled. |
| Groups/originals | Fragmented IDs/args, duplicate/orphan/missing members, incomplete final message, full-original upload failure and continuation; no premature execution/partial group send. |
| Audience/revocation | Owner + second member; private sentinels absent from prompt/tool/index/summary/stream/log/output. Cross-workspace/branch, source edit/delete/ACL revoke at capture/generate/adopt/send, stale index and transitive dependencies. |
| Durability/native behavior | Shipped PostgreSQL schema, concurrent native writers, atomic coverage/uses/pointer, replay/lease takeover/root budget contention; successful terminal never downgraded. No test-only schema unlock/fake PG pass. |
| Compatibility | Existing branch/edit/failed-parent/citation fixtures, mode2 no-assets success, selected-empty rejection. Visual preservation pending multimodal solution. |
| SSE/UI | Split CRLF/UTF-8, bad/missing frames/terminal, wrong IDs/late data, disconnect after meta/final commit. Real browser organizing→automatic resume→answer, reload/cancel/unknown/source-unavailable; #46 acceptance. |
| Semantic quality | Fixed supported-source comparison of constraints/quantities/negation/conflict/unresolved work; semantic-loss negatives detected. Synthetic summaries prove plumbing only; model-quality spend separately authorized. |

Genuine blockers:

- Production candidate and exact owner-supplied interfaces need independent approval. Narrow helper implementation is authorized for original-review recheck.
- #43 P43-A1/A2/A3 and full storage/runtime acceptance remain unresolved in inspected evidence. Prefix-only planning cannot be frozen.
- #40 route/dependency handoff and controller integration baseline required; PR49 still unmerged.
- No current physical capacity/counter/tool binding; neutral DTO does not support existing images. Full activation requires reviewed solutions.
- Shared asset/tool-result resolvers, truthful history index and durable runner/deployment are not supplied by provider foundation; owner allocation/contract alignment required.
- Full PG and visible-product acceptance remain future gates. Deterministic helper tests do not establish durable/runtime/UI acceptance; no model spend is authorized.

Write-back: this document records the scoped handoff and helper verification below. No private memory, external workbench, historical evidence, existing provider/product files or Git state are written by this slice. SHA-256 is returned externally. Historical provider/admission acceptance remains unchanged.

## 13. Bounded helper candidate and verification

Candidate baseline: `bc73fcb5bfca30e9aaa311c77dd694f3c123c894`. Original independent reviewer recheck is pending. The original review artifact is retained unchanged; this report does not mark its findings independently closed.

Implemented only:

- `chat_loop/turns.py`: collect_turn consumes existing typed events and returns CollectedTurn after terminal validation/exhaustion/cleanup cancellation check. ProtocolError fails closed; stream/cleanup exceptions become bounded safe codes. No arguments-JSON reparse or native protocol parser. Completion ToolCall objects remain exact. Missing usage becomes Usage(None,None,'unknown').
- continuation_decision pairs ToolOutcome values in accepted member order, locally deduplicates identical deliveries and rejects conflicting same-ID outcomes. Known failed/cancelled outcomes remain explicit serialized result slots; absent/pending/unknown stops with no request. A complete group returns gate_required plus an unapproved GenerationRequest candidate and unchanged supplied identity. It creates no dispatch authority or durable guarantee. Module-local ToolOutcome status 'completed' is not a persistence lifecycle mapping.
- Minimal local package marker and dedicated test_chat_loop_turns.py. No root exports, shared ABI, state/engine module, journal/authorizer/compactor/budget implementation, provider edits or public presentation changes.

Independent controller execution: **181 passed in 0.66s**, comprising **64 helper + 117 existing provider/counting/wire**. Network socket connect/connect_ex/create_connection denied; ai_pdf_api/ai_pdf_worker imports denied; exact local contract path asserted; skip/deselection/zero-collection guard active; plugin autoload, bytecode and pytest cache disabled. All four test files explicitly selected. No live provider, PostgreSQL or UI executed.

Actual Responses/ChatCompletions/Anthropic adapters supplied typed events from labeled synthetic transports. Real PayloadTokenCounter serialized proposed paired continuation DTOs; synthetic callback captures were labeled estimated. Real CharacterEstimateCounter ran twice per fixture with deterministic positive estimated values, including failed/cancelled outcomes on all three protocols. This proves serializer/counter compatibility, not tokenizer accuracy or safe physical dispatch capacity.

Other deterministic negatives: fragmented typed identities, duplicate/mismatched completions, undeclared calls, missing/contradictory/duplicate terminal, late events/errors after terminal, cancellation before/during/after terminal and during close, UTF-8/event/argument/call/result bounds, invalid usage, unknown/pending results, duplicate outcome flood and encoded result expansion. These are local protocol-to-transition checks, not real source authorization, durable no-repeat, cumulative budget or loop runtime evidence.

### Reproduction

Use system Python with read-only cached dependencies; no install or external write:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$names=@('xIlLX82QEusHhXca','RHvkbWyG_J6xPpug','2ITaIXdneZF10lum','L-k_dNEQiegHAoRr','9WszWcRZL3SpM_A6','owHdhenMp3yGpVwQ','IXhh9yEdY9JaYctE','KCmD3SQamalmBs5q','YdsFZR1HrxsPKnB9','Zq2bI9VcljzvcYsS','_RYxQYdcVRNLZyX8','ZDAbANqgonyGTG3i','_9JbTHVRpvVtYE4F','FDG66F5kllj7cINU','K0LZfPUmyexRg91C','sBbxgXf9XB47bNJW')
$env:PYTHONPATH='packages/memory-service/src;packages/backend-contracts/src;' + (($names | ForEach-Object {'C:/Users/baiao/AppData/Local/uv/cache/archive-v0/' + $_}) -join ';')
```

Pipe this Python into that environment (the guards below were used for the reported run):

```python
import importlib.abc, pathlib, socket, sys
class NoApplications(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'ai_pdf_api', 'ai_pdf_worker'}:
            raise AssertionError('application import forbidden: ' + fullname)
def deny_network(*args, **kwargs):
    raise AssertionError('network forbidden')
sys.meta_path.insert(0, NoApplications())
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
import pytest
import citeframe_contracts.memory as contract
assert pathlib.Path(contract.__file__).resolve() == pathlib.Path('packages/backend-contracts/src/citeframe_contracts/memory.py').resolve()
class RequireExecuted:
    bad = False
    def pytest_collectreport(self, report): self.bad |= report.skipped
    def pytest_runtest_logreport(self, report): self.bad |= report.skipped
    def pytest_deselected(self, items): self.bad |= bool(items)
    def pytest_sessionfinish(self, session, exitstatus):
        if self.bad or session.testscollected == 0: session.exitstatus = 1
status = pytest.main([
    '--noconftest', '--strict-markers', '-o', 'pythonpath=',
    '-o', 'xfail_strict=true', '-p', 'no:cacheprovider', '-q',
    'packages/memory-service/tests/test_chat_loop_turns.py',
    'packages/memory-service/tests/test_native_provider.py',
    'packages/memory-service/tests/test_token_counting.py',
    'packages/memory-service/tests/test_wire_provider.py',
], plugins=[RequireExecuted()])
assert not any(n.split('.')[0] in {'ai_pdf_api','ai_pdf_worker'} for n in sys.modules)
raise SystemExit(status)
```

### Stable code candidate SHA-256

| File | SHA-256 |
|---|---|
| packages/memory-service/src/citeframe_memory/chat_loop/turns.py | `ebfe72ac945a854866494db0ac52b1f09eed23bae84815463260a9a7639a664b` |
| packages/memory-service/src/citeframe_memory/chat_loop/__init__.py | `10a788b1aeb20eef96f03330329d973e4a4166a814733e251b8db50aa62b3e37` |
| packages/memory-service/tests/test_chat_loop_turns.py | `c7581f8940686f44e99b7e0695bf4b0e4a77f2fe8e02cbfd9dca03a830bd38bc` |

Full production integration still requires the exact accepted #43 callable/receipt/send/lifecycle/accounting handoff and remaining source/schema/capability/multimodal/runtime/UI acceptance. No code in this candidate supplies those authorities.
