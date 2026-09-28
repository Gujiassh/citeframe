# Issue #44 — actual chat tool-loop integration contract

**Runtime integration DESIGN CANDIDATE. Sections 20–21 correct the §§14–19 proposal after F44-R1–R5; the linked R2/R4 small contract controls the authorized pure-profile slice. Remaining runtime changes require independent owner review. The earlier scoped contract/helper is accepted; no runtime product implementation or activation is authorized by this amendment.**

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
4. Only then load bodies/snippets. Recheck at adoption and next send. Counts/ranking/cursors must not leak denied sources. Cursor binds actor/scope/query/filter/source generation and paging policy and expires after15 minutes; every use reauthorizes. Current profile/counter/request belong to per-page admission, not stable cursor identity (see §20).

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

## 14. Fixed runtime baseline and exact owner handoff (current design amendment)

This amendment governs remaining runtime seams; §§1–13 retain the accepted requirements, helper evidence and historical dependency observations. It supersedes earlier deferred-signature/status statements, not approved mode1/mode2 presentation or the full same-question compaction outcome.

Controller-fixed baseline: `b0e30fb24d3c119573ea7a5d1a7b1607da2fc602`, branch `work/issue44-chat-runtime`, same authorized workspace. It combines accepted provider delivery `812ebb1` and exact PR47 candidate `1b9e1168`. Original PR49 ref stays unchanged. Six core/provider hosted checks passed per controller; external service gates failed. This candidate is not main or a substitute for eventual PR47/48/49 lineage/revalidation. No Git command was used in this amendment.

`issue44-runtime-ownership.md` grants only an in-principle narrow chat-router lease, conditional on exact registration. Actual merged router now uses `WorkspaceRequest[ChatStreamRequest]` and `require_stream_chat_access`, which validates body then calls `require_workspace_member`. Preserve dependency/validation priority, thread/workspace checks, authentication errors and native v1 response behavior. No `routers/deps.py` or other #40 files are writable. `services/chat.py` is available only after exact implementation approval; no source/schema/native code is edited now.

Workbench bootstrap returned task memory44-chat-runtime and the next step to settle native composition/multimodal/capacity/#43 interfaces. Linked project/state/task were read. This document is the scoped write-back; no external workbench or private memory write.

### Actual #43 status, not a guessed accepted commit

Read-only #43 core/native-lifecycle is a completed developer candidate; its original full-core/PG audit is separate. The latest reviewer appendix **approves the revised interval/result/profile design**, SHA-256 `b34deac14af9a7438e6453ebd46649b07f18b5ef8904bb43ab2ba63b092bd736`, closing P43-I1/I2 at design scope. The amendment file's pending-review header is stale relative to that appendix. No interval implementation/repeated-episode/full-core acceptance is inferred.

Inspected gate still uses `units[old_count:]`, refuses nonzero intervals with `checkpoint_interval_metadata_required`, and journal persists input-v1/result-v1. Therefore current code cannot deliver repeated post-question compaction. P43-A2/A3 original pure counterexamples have independently passed bounded corrections; P43-A1 durable interval rendering still needs implementation/proof. The exact accepted integration commit remains an owner/controller handoff, not a value invented here.

Read-only source identity:

| #43 relative path | SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/compaction.py | `d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b` |
| packages/memory-service/src/citeframe_memory/compaction/gate.py | `c371dee7d1c3ae819e3a7a45aef39dfd385179ad126007303e00a85715ee2113` |
| packages/memory-service/src/citeframe_memory/compaction/journal.py | `0643125d343a6a1e978b80804744077ed6bb640137df40a6885ddc2d7cf5e8a3` |
| packages/memory-service/src/citeframe_memory/compaction/repository.py | `38ec20ba9d0d0707218dad8849de37300cee5025897c64bf47e0240f6235ecd6` |
| packages/memory-service/src/citeframe_memory/compaction/archive.py | `87bd63c47a8d3a9ebcd8b214f3004cc5ffe8ba4b040bcde2a957487e42d2d5e6` |
| packages/memory-service/src/citeframe_memory/compaction/sources.py | `d783d49f377459fd5a1b9ddd544562ea1dc5741947df24642ae882a35af5a66e` |

### Existing callable signatures to consume directly

These are implementation-local #43 APIs, not new #44 ports. Pin them to its accepted commit before production binding:

```python
ContextOwner(workspace_id, actor_user_id, kind, owner_id, lease_token_hash)
SourceReference(source_id, version, sha256)
CoverageUnit(key, source=None, tool_group_id=None, parent_message_id=None)
# Exactly one source/tool_group target.

CompactionRepository(session_factory, *, clock=None, limits=GuardLimits(), fault=None)
repo.capture(owner, units, policy) -> CapturedContext
repo.register_source(owner, kind, native_id) -> SourceReference
repo.read_source(owner, reference, *, start=0, end=None) -> str
repo.reconcile(owner, operation_key)  # checkpoint reconciliation only

CallJournal(repository, *, native_accounting=None, object_store=None,
            max_request_bytes=1048576)
journal.reserve(captured, policy, *, logical_key, purpose, request_sha256,
                input_tokens, output_tokens, provider, model, profile_fingerprint,
                next_main_input=0, next_main_output=0, parent_call_id=None)
journal.archive_request(captured, policy, receipt, request)
journal.mark_sent(captured, policy, receipt, *, require_archive=False)
journal.settle(receipt: AccountingReceipt, usage: UsageSettlement)

DispatchGate(repository, journal, generation, counter, connection, counter_identity,
             *, policy=CompactionPolicy(), input_ceiling, safety_margin=0,
             archive=None, max_summary_wall_seconds=60, max_merge_calls=2,
             cancelled=lambda: False, provider_identity=None)
gate.prepare_main_dispatch(owner, template, coverage, runtime_policy,
    *, expected_context_version, logical_key, mode='initial', recent_units=1,
    protected_keys=frozenset()) -> DispatchPermit
gate.authorize_send(permit, runtime_policy) -> GenerationRequest

ToolArchive(repository, object_store, *, max_result_bytes=16777216,
            max_task_bytes=67108864)
archive.persist(captured, policy, unit: ContextUnit, sources: tuple[SourceReference, ...])
archive.read(owner, group_id) -> ContextUnit
archive.read_range(owner, group_id, call_id, *, start, end)
```

`DispatchPermit` fields are request,captured,receipt,checkpoint_id,disposition,mode. `CapturedContext` fields are owner,context_version,checkpoint_id,checkpoint_version,native_fingerprint,units,policy_fingerprint,native_manifest_json. `AccountingReceipt` fields are call_id,workspace_id,owner_id,request_sha256,native_provider_call_id,native_ledger_id. Do not wrap these in a second receipt or export duplicate shared declarations.

Existing runtime policy v1 has **exactly** schemaVersion='compaction-policy-v1',maxCalls,maxInputTokens,maxOutputTokens,maxSummaryCalls,maxEpisodes,deadlineAt; all numeric limits positive integers and deadline timezone-aware. Do not add optional fields to v1. History activation uses the single original #42/#43 strict versioned policy/HistorySession delta in §20; request_manifest records client intent, not a competing history authorization. CompactionPolicy has soft_ratio,target_ratio,min_new_tokens,min_gain_tokens,max_chunk_calls,max_units; CounterIdentity has counter_id,counter_version,mode,config_fingerprint. These independent meanings must not be collapsed into a generic budget map.

### Exact dispatch/accounting sequence

For initial, complete tool continuation and resume/retry: restore real owner/coverage/expected context → `prepare_main_dispatch` → `authorize_send` → invoke the existing GenerationPort once with **exact returned request**. Allowed gate modes are initial/continuation/role/resume; explicit retry uses resume with the new owner identity and original root policy. Do not add a retry mode silently. Main logical key is `main:<execution UUID>:<durable turn ordinal>`; ordinal comes from the owner's journal, never current list length. Owner43 must allocate it under lock.

Preparation captures, materializes, recaptures, counts, optionally compacts/adopts, and reserves. authorize_send verifies request hash/count/capacity, archives/readbacks request and marks sent under fresh guard. It makes no main provider call. No generation on a preparation permit alone. Lost acknowledgement after mark_sent is unknown until owner reconciliation; no blind replay. Summary calls remain solely inside #43 gate. Same-question interval rendering must use the approved persisted plan/summaryInput/finalEligible and whole dispatchProfile on reserve/archive/send/unadopted recovery/adoption; current prefix-tail assembly must be removed by #43.

Provider `Usage` is nullable; existing `UsageSettlement(state,input_tokens,output_tokens,source)` requires nonnegative integers and state succeeded/failed/outcome_unknown. Proposed owner-approved mapping, implemented once in #43 journal, not another #44 budget counter:

- Both reported totals known: use reported totals/source; retain real zero.
- Any missing component: use the corresponding existing reserved component; retain any known component. Source is estimated unless both are unknown, when source is unknown. Retain original nullable provider usage in the call's strict result metadata so estimates are never presented as reported usage.
- Partial/missing terminal, transport uncertainty, cancellation after sent: outcome_unknown; journal enforces at least reserved input/output and never refunds by timeout. Local protocol rejection with definitive completed provider outcome can settle failed; source authority still gates any content.
- Before sent: a separate owner cancellation command releases only provably unsent reservation once; no fake cancelled UsageSettlement. After sent, safe late accounting can run without source membership; it cannot finalize content.

Required exact addition: `journal.settle_generation(receipt, *, terminal_state: Literal['succeeded','failed','outcome_unknown'], usage: Usage|None) -> dict[state,input_tokens,output_tokens]`. It reads the receipt's reserved totals itself in the same metadata-only transaction, performs the mapping above through existing settlement arithmetic, and preserves raw usage metadata. No caller-supplied guessed reservation values. Existing `settle` remains the lower-level operation; transaction-local extraction avoids nested commits. #42 reviews shared data changes; none is needed to Usage/UsageSettlement for this mapping.

## 15. Concrete atomic native-chat command delta — sole owner #43

Actual `repo.create_chat(owner, *, thread_id,user_message_id,assistant_message_id,request_id,request_sha256,policy,deadline_at,lease_expires_at)` requires **already existing** completed user/streaming assistant, then starts its own transaction and inserts a running execution. Calling legacy prepare_chat (which commits) then create_chat cannot provide atomic admission. Legacy finalize_chat independently commits assistant/leaf and cannot satisfy source/cancel/CAS adoption. NativeGuard requires assistant still streaming and lifecycle prepared/running/waiting_context, so validate BEFORE terminal updates.

Proposed additions are concrete methods in existing repository/journal, implemented by #43 after owner review. No new shared generic service/engine or shadow lifecycle. #44 provides only the native chat writer callback below; #43 owns the transaction, locking, replay, receipts and persistence tests. New return data stays local to #43 unless #42 explicitly accepts a shared export.

```python
repo.start_chat(owner: ContextOwner, *, thread_id: str, request_id: str,
    idempotency_key: str, request_intent_sha256: str, expected_parent_id: str|None,
    edit_message_id: str|None, policy: dict, request_manifest: dict,
    lease_expires_at: datetime,
    write_native: Callable[[Session], tuple[str, str]]) -> dict
# {execution_id,user_message_id,assistant_message_id,version,context_version,replayed}

repo.finish_chat(owner: ContextOwner, *, receipt: AccountingReceipt,
    expected_version: int, expected_context_version: int,
    result_sha256: str, answer: str,
    write_native: Callable[[Session, str, str], None]) -> dict
# {execution_id,assistant_message_id,version,state:'succeeded',replayed}

repo.lookup_chat_request(*, workspace_id: str, actor_user_id: str,
    request_id: str) -> dict|None
repo.reconcile_chat_terminal(*, workspace_id: str, actor_user_id: str,
    execution_id: str, call_id: str, result_sha256: str) -> dict|None
```

**Start transaction:** current authorization first, then lookup both requestId/idempotency-key identities and compare stable client intent before any mutable parent/profile/source preflight. Matching accepted request returns existing IDs without callback or model/retrieval IO. Only a new intent resolves current parent/edit/profile and freezes the execution snapshot under owner guards; see §20 for exact collision/replay ordering. Invoke the transaction-neutral native writer once to insert user/pending assistant, native scope/input-evidence/citation snapshots and thread title/time fields, returning their exact IDs. Register execution and initial request metadata in **that same Session transaction**; preserve nullable active-leaf anchor and designated selected-parent ancestry. No meta until commit. Concurrent duplicate submission must converge on one accepted pair using unique keys, rollback loser inserts, then fresh authorized lookup. `create_chat`'s row insertion/validation is factored transaction-locally by its owner, not reimplemented by #44.

The concrete API callback is a refactor of native prepare_chat's existing ORM write block: `write_prepared_chat(db: Session, preparation: PreparedChatInput) -> tuple[str,str]`. PreparedChatInput is API-local, containing question, resolved parent, timestamp, model labels, scoped asset IDs and exact resolved evidence/retrieval snapshot values already used today. IO/retrieval/image decoding is completed before this call. Callback performs only the existing native DB inserts/updates; no commit/rollback, source grants, provider calls or external object IO. #43 rejects transaction-control callbacks and revalidates referenced native snapshot versions/current asset eligibility before admission commit. API #44 owns callback code only after exact approval. This is the existing native write seam inside the owner's transaction, not a second journal/authorizer.

**Finish transaction:** acquire normal live guard while assistant remains streaming, match expected execution/context, receipt main-call identity/input capture/request/result hashes, complete durable answer result, current source/transitive uses, lease/cancel/native anchor and whole-reader authority. Idempotent prior committed finish is checked before attempting a live guard that correctly rejects terminal owners. Invoke `write_final_chat(db, assistant_id, thread_id)` callback to apply already-validated answer/citations/history references and native leaf update without commit; mark execution succeeded/version increment/finished timestamp in the same transaction. Call result/response payload must match the durable hash exactly. Lost ACK uses terminal reconciliation; serialize native citations/done only after receipt. Post-commit stream errors never call legacy fail_chat. Failure/cancel finish uses the same owner terminal command family and existing native failed-message/citation cleanup semantics, never an independent callback commit.

### Small required execution metadata/schema amendment

Existing execution table lacks a durable body/scope manifest or idempotency-key uniqueness. Proposal for #43/#42 review: add only `request_manifest JSONB NOT NULL` and `idempotency_key varchar(128) NOT NULL` plus unique `(workspace_id,actor_user_id,idempotency_key)`; retain existing unique actor/workspace/request_id. New strict manifest schema `chat-request-v1` contains protocolVersion,threadId,resolvedParentId,editMessageId,questionSha256,assetScope (none/all_ready/selected + exact selected IDs),historyScope,selectionText or null,evidence locator/version refs,profile binding hash,immutable control limits. Question body remains native user.content. Exact selection is needed for faithful restart and must be bounded/provenance-checked, not silently lost. No credentials/endpoints/native audience/private mode field. Existing pre-runtime rows cannot be backfilled with invented scopes; require explicit legacy-disabled discriminator/backfill rule approved by owner, then reject resume where manifest is absent. Migration revision/path remains owner-assigned, not authored here.

Immutable control limits: maxToolCalls,maxToolResultBytes,maxTaskResultBytes,maxAttempts,maxWallSeconds; usage derives from authoritative memory_calls/root ancestry. These are not mutable counters. Tool/archive admissions enforce them under root guard. DeadlineAt remains policy authority; maxWallSeconds only derives it at root start. Stable request-intent hash includes validated client body/route/actor/workspace with supplied-versus-omitted field semantics. First accepted resolved parent/profile/control/source snapshots have a separate execution binding hash; see §20. Never include mutable server resolution in the replay intent hash.

### Remaining durable call/control methods required, not simulated

```python
journal.accept_main_result(captured, policy, receipt, *, text: str,
    calls: tuple[ToolCall, ...], usage: Usage|None, result_sha256: str) -> dict
# Durable exact validated turn; group_id/member IDs when calls exist, else final-result identity.
journal.complete_chat_tool(owner, *, group_id: str, provider_call_id: str,
    state: Literal['succeeded','failed','cancelled','outcome_unknown'],
    result_ref: dict|None, source_refs: tuple[SourceReference, ...]) -> dict
repo.cancel_chat(*, workspace_id, actor_user_id, execution_id,
    request_id, expected_version) -> dict
repo.claim_chat(*, execution_id, worker_id, lease_token_hash,
    lease_expires_at, expected_version) -> ContextOwner
repo.renew_chat(owner, *, expected_version, lease_expires_at) -> dict
repo.resume_chat(owner, *, request_id, expected_version) -> dict
repo.retry_chat(owner, *, request_id, expected_version, new_execution_id,
    new_assistant_id, new_lease_token_hash, lease_expires_at) -> dict
```

Exact additions need #43 acceptance, not runtime stubs. accept_main_result revalidates capture and archives typed validated result before any tool executes; declaration member ID/name/arguments hash/order binds parent main receipt under lock. complete_chat_tool writes exact result/support and only marks full group complete when every member known terminal. `ToolArchive.persist` currently accepts an already complete group and is not declaration-before-effect journaling; factor its archive/readback/completion into these owner commands rather than repeat a completed group on crash. Stable group/member keys derive from originating receipt and ordinal; never from model-generated prose. Local helper completed maps explicitly to owner succeeded; failed/cancelled map unchanged; pending/unknown never enters a completed ContextUnit result-state tuple.

Claim/renew/cancel/retry share owner enum `prepared,running,waiting_context,succeeded,failed,cancel_requested,cancelled,outcome_unknown`. Retry keeps root budget/deadline, unique retry_of and new assistant sibling; no second user. Lifecycle operations and request replay metadata need owner-defined idempotency storage; do not reuse private memory_operations with its unrelated record FK. Prefer existing execution/call strict manifests with stable operation keys if owner can prove uniqueness; any extra columns/constraints must be reviewed before implementation. This is an explicit unresolved storage decision for these later control endpoints; it does not block the profile composition slice (§19).

## 16. Fixed capability/counter configuration and minimal multimodal delta

### Deployment-owned fixed registry, no model-name inference

Actual ModelConnection has capability/source/revision/protocol/provider/model/base_url/api_key/timeout/max_output_tokens; no physical context/tool/tokenizer profile. `connection_profile(connection).config_fingerprint` already fingerprints configured connection including credential identity without exposing the secret. Use it as an exact lookup discriminator, not evidence of capacity.

Proposed **server-injected immutable registry object**, loaded by composition owner from reviewed deployment JSON, schema `chat-provider-registry-v1`; no new settings/credential loader inside neutral code and no automatic remote discovery. Loader/bootstrap path assignment stays #42/controller. No populated model capacities are invented in this design. Exact profile entry:

```text
{schemaVersion:'chat-provider-profile-v1', profileId, profileVersion,
 connectionFingerprint, protocol, model, providerIdentity, adapterVersion,
 contextWindowTokens, maxOutputTokens, inputCeiling, safetyMargin,
 supportsTools, supportsStreamingTools, supportsCancellation, supportsImages,
 counter:{id,version,mode:'exact'|'estimated',implementationId,parameters},
 images:null|{mediaTypes:['image/png'],maxImages,maxBytesPerImage,maxTotalBytes,
              maxWidth,maxHeight,maxTokensPerImage,accountingVersion},
 watermarks:{soft_ratio,target_ratio,min_new_tokens,min_gain_tokens,max_chunk_calls,max_units},
 maxSummaryWallSeconds,maxMergeCalls}
```

Required fields strict/no defaults from model name. Dimensions/capacity positive, safetyMargin nonnegative, output within physical bounds, strict booleans, all implementation IDs from a closed local registry. Match connectionFingerprint+protocol+model+adapterVersion exactly; unknown/ambiguous entry rejects. Registry provenance and source documentation for capacities/image bounds must be independently reviewed. A model alias or compatible provider name grants no tools/images/counter capability. Runtime profile fingerprint is canonical SHA-256 of connection fingerprint + entire approved entry; persist that and #43 dispatchProfile, not the JSON secrets/endpoint. Connection/credential/config revision change forces explicit approved rebind/recount under root budget.

Proposed first concrete API functions, no new shared ports:

```python
resolve_chat_profile(connection: ModelConnection, *, registry: Mapping,
    connection_fingerprint_for: Callable[[ModelConnection], str],
    requested_output_tokens: int, require_cancellation: bool = False) -> ResolvedChatProfile
build_chat_generation(profile: ResolvedChatProfile, *, transport: HTTPTransport,
                      cancelled: Callable[[], bool] | None = None) -> tuple[GenerationPort, TokenCounter]
```

ResolvedChatProfile is API-local data holding existing ModelConnectionSnapshot, CountingProfile, Capabilities and frozen numeric/policy data; no lifecycle/receipt authority. `resolve_chat_profile` is pure. `build_chat_generation` remains unimplemented pending the R2/R4 small review. It receives a caller-owned transport; composition owns `with model_client(...)` and completes all iteration/cleanup inside it. No second connection is accepted or client created by build. Explicit protocol mapping anthropic_messages→anthropic; endpoint uses existing validated OpenAI base/path and DeepSeek endpoint builder semantics. Reuse existing origin/DNS, trust_env=False, follow_redirects=False, no retries and timeout/response bounds; never pass bare uncontrolled httpx.Client. API owns credentials; no neutral app import.

Counter implementationId chooses an explicitly registered tokenizer-specific callback or CharacterEstimateCounter with reviewed characters_per_token/protocol_overhead_tokens. Only tokenizer-bound proven counting may claim exact. Estimated text counts stay estimated and require approved safety margin. Missing image-accounting profile rejects before provider send; base64 character length is not image-token accounting.

### Minimal owner42 shared ABI proposal for actual legacy PNG input

Current `_build_generation_user_message` generates user text followed by PNG data-URL images, detail=high, from targets and visual enrichment. Preserve exactly those bytes/order/detail and native evidence snapshots. Existing neutral content:str cannot carry them. Proposed additive shared DTO (sole #42 author; independent owner review before edits):

```python
@dataclass(frozen=True)
class GenerationImage:
    media_type: Literal['image/png']
    data_base64: str
    width: int
    height: int
    detail: Literal['high'] = 'high'

# Append at end; current four positional fields/text calls remain unchanged.
GenerationMessage.images: tuple[GenerationImage, ...] = ()
```

Only user messages may carry images, appended after content; this is sufficient for the inspected native shape and preserves ordering without an unneeded general content-part union. API currently resolves and fully reads/decodes native image bytes without the proposed pre-allocation bounds. The original native loader/render owner must implement §21 source/decode/render admission before this image bridge may activate; bounded final GenerationImage validation alone is insufficient. After that admission, preserve exact native bytes and base64 encode once. Strict profile max dimensions/count/decoded bytes/total bytes and base64 validation; no remote URL/file locator accepted by the adapter. Dataclass dimensions must match decoded bytes, not untrusted caller labels. Unsupported MIME/order/role rejects explicitly, never drops image or substitutes OCR. Text-only requests and accepted provider fragment parsers stay unchanged.

Minimal #44 adapter amendment after #42 ABI approval: append local `Capabilities.supports_images: bool = False` (not a shared port), reject image requests unless that capability and the explicit counting profile agree; `_requests.py` validates image bounds and serializes user content to Responses input_text/input_image(data URL,detail), ChatCompletions text/image_url(data URL,detail), Anthropic text/image source{type:base64,media_type,data}; preserve existing provider header/endpoint handling. Expand payload/request/archive byte caps coherently to the reviewed image limits, not a global unbounded max. `GenerationRequest`, GenerationEvent, ToolCall and streaming parsing ABI need no change. Tool results remain text. #43 archive.asdict will carry image tuple data, but its readers/restore constructors and hash limits must explicitly support the additive field before restart acceptance; ignoring fields on readback is forbidden.

Counter counts exact serialized text/tool framing and explicit image tokens from the reviewed profile. Proposed minimal estimated implementation: invoke existing text counter on a deterministically redacted image payload (replace only base64 data with empty string, retain framing); add image count × reviewed maxTokensPerImage for validated dimensions under the profile maximum. Mark result estimated. Exact implementation must have provider/model-specific supported image algorithm; no generic exact assertion. Full payload hash/archive retain original base64, and count result includes the same frozen profile/accountingVersion; redaction is solely a counter projection, not a transmitted input change. Invalid dimensions or absent documented upper bound gives context_capacity_unknown. Physical capacity H uses this combined count with existing #43 policy.

Images in the protected current question remain protected whole units. Earlier visual inputs cannot be summarized from missing bytes or extracted text pretending full image parity; require exact persisted authorized originals and image-aware summary input/counting or retain them protected and fail capacity explicitly. Full legacy parity includes normal text+image answer success under supported profile; unsupported gate is a safety outcome, not parity evidence. Provider fixtures for the actual existing PNG shapes across all three protocols plus original native visual tests and image/count/restart/source-revocation negatives are required before activation.

## 17. Source/history consumption — exact authority and owner deltas

Current #43 register_source/read_source accepts shared chat_message on the designated ancestry or frozen Research evidence for Research owners. It does not authorize arbitrary workspace history or chat asset content. Its private-kind rejection remains mandatory. #42 AccessPort.authorize is private management access and must never be used as whole-output-audience approval.

Two concrete incompatibilities need #43 changes before consumption:

1. native_source accepts failed assistant body, while coverage validation requires contiguous direct-parent units. Legacy continuation traverses failed ancestors but excludes their error prose. Required owner projection: keep exact failed node/revision/parent in ancestry/coverage proof, render **zero model messages** for it and prohibit its prose from summary chunks/search snippets. Add a metadata-only ContextUnit representation in #43's local units/materializer/packing, preserving complete ancestry and interval indices. Do not inject an invented failure-text placeholder or remove a node from parent proof. Native visible history still displays failures.
2. ToolArchive.persist rejects empty source tuple. Lawful empty search or known tool failure can have zero content leaves. Permit zero leaves only with a strict code-owned result descriptor proving empty/error disposition and exact authorized query/scope; it contains no source body. Nonempty result must carry all actual hit dependencies. Do not attach an unrelated user/source merely to satisfy nonempty predicate. Exact failed/cancelled statuses remain paired; unknown blocks group completion.

### Exact proposed consumption methods on owner services

Use existing SourceReference for registered text sources; keep tool originals as archive group/member ranges. The following earlier repo.search_chat_history/read_chat_source names are withdrawn implementation proposals, not a second source service. §20 replaces them with the original #43 issuer→#42 controlled source/query/range chain; its exact accepted Python signatures come from those owners:

```python
repo.search_chat_history(owner: ContextOwner, *, query: str, scope: dict,
    source_kinds: tuple[str, ...], from_at: datetime|None, to_at: datetime|None,
    limit: int, cursor: str|None) -> dict
# {items:[{sourceRef,contentKind,excerpt,provenance,occurredAt,branchRelation}],
#  nextCursor,truncated,retrieval:{mode,indexGeneration,policyVersion}}
repo.read_chat_source(owner: ContextOwner, reference: SourceReference, *,
    start: int, end: int|None, cursor: str|None) -> dict
# Approved read_source envelope; Unicode codepoint range and bounded returned tokens.
archive.read_range(owner, group_id, call_id, *, start, end)  # existing original read
```

Original #43-issued frozen history policy sets authority; client request scope and model tool scope only narrow its intersection (§20). request_manifest alone grants no history access. `current_branch` resolves exact accepted user ancestry, not the thread's newest leaf. Workspace history/explicit other-thread scope requires the reviewed source-read extension below and truthful index readiness; until implemented return `memory_index_not_ready`/unsupported-source error, not another corpus or an unlabeled lexical fallback. Native frozen Research evidence remains a distinct internal port and cannot be reclassified as workspace history evidence.

Required smallest #43/#42 source changes:

- Keep existing `chat_message` kind. Add a separate query/read admission path for eligible other-thread messages with current workspace readership, frozen history scope, exact revision and branchRelation. Do not relax native_source's current-branch compaction predicate globally. Tool-result leaves may reference such read-admitted messages, and read_registered must distinguish direct current-branch coverage from external history leaves under the same immutable envelope. Source rows grant no access by themselves.
- Activate `content_unit` and exact explicit evidence-locator input references for native chat. Use current asset/workspace/ready/deleted checks, processing/index generation, representation/parser version, immutable locator payload/hash and body/image hash. Owner chooses reviewed native kind/check constraints and strict version JSON; no schema edit by #44. Explicit visual target may have no text ContentUnit, so it cannot be faked as one.
- Persist direct tool/snapshot/source uses and original raw leaves for every admitted hit/image. Version/ACL/erase/revocation checks at hydration, archive adoption, summary adoption, main authorize_send and final finish. Request manifest contains resource scope and identity; it grants no frozen forever permission.
- Search index owner provides exact eligible-source generation and query implementation from approved design. No index native-ID guessing. Current_branch direct exact reads can operate without hybrid index; search remains honestly unavailable until that index exists. This limits activation, not the full contracted outcome.

Entire-reader authorization: current source readers must cover the existing output's full workspace readership, including later current members under native workspace semantics. Source membership of the requester alone is insufficient. Private instructions/revisions, whether requester-owned or another member's, cannot be queried/hydrated/indexed into any shared consuming boundary. `search_memory` has the legitimate empty eligible result for this release; it makes no private owner query and creates no inferred candidate. Source excerpts/locator titles/ranking/cursors also require authorization before exposure.

Code dispatch table in eventual API `chat_tools.py` is exactly search_memory/search_history/read_source; it calls these owner methods and existing archive reads. Query1..4000, limit1..20 default6, before/after0..2000, cursor15-minute binding and token cap remain approved. It validates DTO schema only and translates returned statuses; it does not authorize via app-level imitation, query private tables, generate source IDs or write journals independently. Empty/error result provenance records its code-owned scope/query descriptor. Repeated normalized query + same exact result IDs/versions twice yields no_new_information under durable owner result history; local caps do not replace that check.

## 18. Exact runtime result/error/stream mapping and native request ordering

No replacement of §9's approved envelopes. Mode1/meta/delta/citations/done/error timing, input validation priority and branch semantics remain unchanged. Mode2 emits exact approved provisional delta `{executionId,text,provisional:true}`, full history_sources, memory_status, context_status with resumed and context_compacted after atomic commit; no execution_state/tool_status/mandatory sequence substitution.

### Provider event → internal/public action

| Parsed event / owner result | Internal action | Public mapping |
|---|---|---|
| TextDelta, tools disabled by exact request | Feed unchanged into accepted nonpublishing collector | Mode1 delta immediately; mode2 provisional delta may stream immediately; final acceptance still required |
| TextDelta, tool-capable turn type still unknown | Feed collector and retain mixed/type-unknown presentation buffer | No completed answer presentation; release only when answer type is known, using approved provisional delta, without imposing post-commit first-text rule |
| ToolCallDelta/ToolCallComplete | Collector preserves parsed values; no execution before valid terminal+owner accept_main_result | Never stream arguments/reasoning as final-answer text |
| Usage | Preserve None/provenance; journal mapping §14 only | No guessed/exact billing statement |
| TurnComplete(tool_calls), full stream accepted | Owner persists main result and declared group before tools | memory_status for actual searching_memory/searching_history/reading_source calls; no new tool_status |
| TurnComplete(answer), full stream accepted | Owner durable result, source/lease/cancel checks, finish transaction | Provisional text remains provisional until done after finish; native citations separate |
| Gate begins compaction / committed checkpoint | Emit owner operation/coverage/count metadata | context_status(compacting); context_compacted only commit; context_status(resumed); continue same submission automatically |
| Stream failure/invalid terminal/cancel | No tool/final adoption; owner failed/unknown/cancel state + late metadata settlement | Exact error envelope, no subsequent done; refresh distinguishes durable state from provisional text |

Existing GenerationEvent provides no universal early answer-type event for tool-capable streams. Do not infer answer-only from first text token or absence of a tool so far. Safe type-known moment can be the terminal for such a stream; that mixed/type-unknown buffering is already approved. It does not authorize delaying text-only mode1 or all mode2 answers until DB commit. API presentation consumes a bounded event tee while the accepted collector handles terminal validity; collector itself stays nonpublishing and unchanged. Reconnect never replays provider calls or guesses missing partial text. #46 must prove first-text/progress/mixed/error/reload behavior in real UI before acceptance.

### Stable error mapping (no raw provider exception/body)

The mapping below is proposed API composition behavior. Existing mode1 preflight HTTP error precedence/shapes remain intact; mode2 structured HTTP and SSE mappings apply after acceptance as specified.

| Actual/source code family | Mode2 HTTP before stream / durable disposition / SSE |
|---|---|
| context_access_denied, shared_source_unavailable for inaccessible identity | 404; terminate content authority; sanitized error, no existence details |
| source_version_changed, context_branch_changed, context_changed, profile_changed, counter_changed_or_invalid | 409; waiting_context if recoverable/authorized, otherwise fail closed; context_status(waiting_context) then error with retryable only when actionable change exists |
| context_busy | 503/retryable; bounded owner transaction retry only, no repeated model call |
| context_limit_exceeded, checkpoint_interval_metadata_required, checkpoint_rendering_metadata_required | 422 for immutable input impossibility or 409 recoverable context state; waiting_context; preserve last good checkpoint. Never activate interval-unimplemented fallback as success |
| context_budget_exhausted, expired root deadline | 429 / failed or owner-defined terminal; retryable=false unless explicit remaining-budget-safe operation exists; no budget reset |
| context_cancelled, context_cancelled_or_terminal, context_lease_lost | No new send; owner cancel/lease reconciliation. Old worker cannot mark another worker failed; subscription reports current authorized state |
| call_outcome_unknown / ambiguous transport-send outcome | 409 recovery status; outcome_unknown; no automatic replay, explicit retry semantics preserved |
| call_idempotency_conflict, idempotency_conflict, accounting_receipt_conflict, dispatch_payload_changed | 409; stop; no transformed permit/result or silent retry |
| capability_unsupported, context_capacity_unknown, memory_counting_profile_unknown, generation_input_unsupported | 422 before send; no guessed capacity/image omission; configuration action required |
| memory_index_not_ready / memory_index_mismatch | 503 actionable retrieval unavailability; no private/alternate index fallback |
| generation_protocol_invalid, chat_turn_* malformed/bounds, missing terminal | Safe generation_failed/protocol code; no accepted answer/tool; sent accounting follows owner uncertainty |

The adapter's exact `ProtocolError` must be mapped by an allowlisted code table; unrecognized exceptions use generation_failed without stringifying payloads. Accounting errors do not erase an already succeeded native terminal. `context_status` carries operationKey/checkpointId and nullable owner IDs from real owner receipts, never inferred from local turn count. Approved `context_compacted.coveredThroughUnitKey` is cumulative dependency frontier; unitCount refers to covered original units. Interval omission/render plan is internal and must not be misrepresented as all frontier units hidden. Any extra interval observability field requires additive owner/#46 review, not a renamed event.

## 19. Necessary owner deltas, immediate eligible code and activation gate

This is a **design-only** amendment. The following is the exact approval/ownership split, with no duplicate ABI or generic engine scaffold:

| Delta | Sole author after independent approval | Scope / prerequisite |
|---|---|---|
| D44-R1 native start/finish/request replay + live/terminal guards | #43 | Existing repository/journal transaction-local refactor and concrete commands §15. #44 native DB-only writer callbacks separately approved; no independent native commit |
| D44-R2 result declaration/member completion, nullable usage settlement and lifecycle operations | #43 | Existing memory_calls/root budget, exact keys/receipts/status mapping. Request/control metadata migration needs #43/#42 reviewed delta; no in-memory substitute |
| D44-R3 fixed profile resolver + secure neutral provider construction | #44 API service; #42/controller bootstrap/registry ownership | API-local module + tests, closed implementation registry, exact fingerprint match, real existing transport injection; no route activation or shared settings edit |
| D44-R4 GenerationImage + appended images field | #42 shared memory.py/exports only | Minimal additive ABI; independent owner review. Existing text callers remain compatible |
| D44-R5 image serializer/count/archive compatibility | #44 adapters after R4; #43 own archive/packing readers | Exact legacy PNG byte/order/detail preservation, explicit profile image accounting and bounds. No legacy rewrite or token guesses |
| D44-R6 failed-ancestor projection, empty result provenance, asset/external-history leaves | #43 source/archive plus #42 shared/schema review | Exact source/envelope/ACL/current-version authority; index implementation assigned by controller; no fake sources |
| D44-R7 interval/profile implementation | #43 | Approved B34DEAC... plan/input/result/recovery/render contract, real PG/restart/two-episode proof |
| D44-R8 thin runtime routing and approved stream projection | #44 narrow registered routers/chat.py lease + services; #46 public UI | Preserve require_stream_chat_access/dependency order; no deps/other40 edits; actual accepted owner APIs only |

**Superseded by current R3-A authorization in the small contract:** one new API-local `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` plus dedicated `apps/api/tests/test_chat_runtime_profile.py`, implementing only §16 `resolve_chat_profile` and `build_chat_generation` against existing neutral DTOs/adapters/secure transport. Pure profile resolution and synthetic transport construction must prove exact lookup/fingerprint/counter/capability/endpoint mapping, unknown-profile rejection, no secret persistence, no redirects and no network at construction. Text-only supported profile fixtures are labeled synthetic; this slice does not claim multimodal/full-loop parity. Image entries reject until R4/R5 accepted. No schema, shared ABI, router, runner, admission/finalization or provider parsing change. This is real composition code for actual existing adapters, not a fake gate/journal/authorizer. Deployment registry population/loader and route activation remain disabled until their separate grants.

Next native runtime slice after R1/R2/R6/R7 accepted commit: integrate start → actual gate.prepare → authorize_send → accepted provider/collector → owner main result/tool journal → next actual gate → atomic finish in focused API services. It must demonstrate a single current question, no new user turn, post-question complete groups crossing thresholds twice, interval reconstruction after restart, lawful same audience and unchanged native effects/budgets/cancel. No semantic loop test double can replace this acceptance. Native visual parity R4/R5 and actual source/index capabilities remain activation prerequisites; no whole-product completion based on a text-only composition test.

Review submission requirements: approve exact API-local R3 signatures and file grant independently; owner43 reviews R1/R2/R6 against its actual accepted core and interval changes; owner42 reviews R4 and schema/shared consequences. Record accepted commit/API/hash at integration, replacing observations only after verification. Native lifecycle/control idempotency storage in §15 remains an explicit owner decision before those endpoints, not hidden scaffolding. Router lease must be registered exactly before any router write. No #40 dependencies or other files change.

Verification for this amendment: actual source/contract/review inspection and source SHA-256 only. No runtime test rerun, PostgreSQL, provider/model calls, service changes or hosted-check claims. The accepted helper/provider hashes and original review/evidence artifacts are preserved. Durable write-back is this amended contract; production/source/schema/native product files remain untouched.

## 20. F44-R1/R2/R3/R4 correction and original-owner handoff

Read the complete new runtime review, exact SHA-256 `e06bd82578182a2944dee2f0658558f620e60984318264274eb00fbe7a4e9468`. These are developer corrections for recheck, not independent closures.

**R2/R4 controlling small contract:** `lanes/issue44-profile-binding.md`. R3-A pure registry/profile resolution is authorized in exactly two new files; R3-B build waits only for its own small binding/lifecycle approval, not #43 completion. Existing global capability fingerprint is unchanged; source/revision and actual connection values are additionally bound, effective output ceiling takes min(application,physical), and builder cannot accept an unrelated connection/fingerprint. No exact counter or production capacity is supplied. Explicit transport ownership is the composition `with model_client` lifetime; no client creation hidden inside build.

### R1 — stable POST intent versus first accepted execution snapshot

Two distinct hashes are required, with one execution owner/table:

- `request_intent_sha256`: canonical validated client intent plus HTTP method/route/actor/workspace. Preserve field-presence semantics for parentMessageId/editMessageId and relevant defaults: omitted parent is a tagged omitted value; explicit null/id is tagged supplied even where native resolver currently treats null like omission. Preserve array order where meaningful, use strict validated values, and exclude mutable active leaf, resolved profile/credentials, selected current sources, server budget/deadline and lease. Do not hash raw JSON spelling/whitespace.
- `execution_binding_sha256`: first acceptance's resolved parent/edit ancestry, exact profile/connection revision, control limits, frozen policy, selected source/evidence snapshot and native identity manifest. Store in the first accepted request_manifest/owner journal, revalidate current permission for use, and never recompute it to reinterpret an old POST.

After current workspace/actor authorization, lookup requestId and idempotency key **before** resolving implicit parent, model profile, retrieval, image preparation or any native writer callback. If both identify the same existing execution and intent matches, return its same execution/message identities and current safe status, even after active leaf/config/credential changes. If one key collides with a different intent/identity, return409 without callbacks. If neither exists, resolve current environment and admit once under the owner transaction; concurrent unique-key loser rolls back its native writes and does fresh authorized lookup. Same intent does not restore revoked source access or allow a revoked actor to poll body/status. Content replay uses current source authorization.

Existing accepted request snapshots remain immutable. Explicit retry/rebind is a separate command with new authorized identity where specified, original cumulative budget and its own reviewed transition; repeated POST is not an implicit rebind. Lost admission/final ACK uses these identities, never current leaf inference.

Original #43 owns exact start/replay storage and transaction factoring; #44 owns only approved native transaction-neutral writer callback later. Required tests: replay after successful finish/leaf move/profile and credential rotation returns same IDs with zero preparation/model/callback; changed question/explicit parent conflicts; revoked actor denied; concurrent requestId/key cross-collision and lost ACK preserve one native pair. No new idempotency framework or second execution table.

### R3 — one original history authority and consumption chain

Withdraw §17's separately proposed repo search/read implementation and request_manifest-as-authority. Align with original #42 `issue42-shared-sources.md` and original #43 issuer/consumer owner:

1. Existing strict compaction-policy-v1 exact seven keys keeps its meaning/hash/replay. History defaults disabled through a read-only accessor; no injected default/history member or old-task hash rewrite.
2. Original owners review strict compaction-policy-v2: same budget/deadline keys plus history. history-policy-v1 is exactly disabled `{schemaVersion,enabled:false}` or enabled `{schemaVersion,enabled:true,audience:'workspace',allowedScopes,sourceKinds,policyVersion:'history-runtime-v1'}` with unique allowed enums and unknown-field rejection. Only new explicitly authorized tasks enable accepted source kinds. Exact persisted canonical ordering survives retry.
3. First acceptance derives history authority as installed/approved server capability intersect validated client historyScope. The resulting frozen history policy is the sole authority. request_manifest keeps the client intent and resulting policy hash for audit, not a second grant. Retry inherits that policy; tool scope can only narrow. Private content remains entirely excluded, including requester-owned data and all-reader native workspace semantics.
4. #43 NativeGuard locks owner/root/workspace/member/lease/branch and issues a transaction-local HistorySession for the exact frozen policy. #42 original source/query/range modules work only through that controlled transaction/session. #43 keeps registration/staleness, archive/journal, complete-group/use predicates, suppression and adoption. #44 maps tool DTOs and orchestrates; it cannot construct HistorySession, add an API authorizer or duplicate query/registry logic.
5. Final accepted `history_search(owner,query)` / `history_read(owner,selection,cursor)` issuer signatures and #42 consumer methods are delivered by those two original owners at exact commits. Working drafts are not accepted interfaces. No additional implementation owner is assigned.

Cursor binds stable source/version/fixed expanded terminal window/owner/history-policy/scope and approved paging-policy version. It does **not** pin connection/counter fingerprint, context_version, renewable lease, previous full GenerationRequest hash or old tool call ID. Every page uses the current profile, counter and actual request: reauthorize the entire output audience through the original #43 issuer→#42 source authority, validate current dispatch capability, count that exact request and enforce current remaining budget. Profile/counter/request changes alone do not invalidate an otherwise authorized stable source window; each call journals its own current binding/count/request hash. Insufficient current capacity leaves the cursor unchanged. Changed policy/source/version or failed current authorization/capability rejects without substituting a source. Native source owner's exact final cursor contract controls; this lane adds no parallel signer. This alignment remains subject to exact #42/#43 owner review, alongside R1 and R5.

Original empty-result union remains narrow: code-owned search_history zero_hits with complete corpus generation, or shared search_memory policy_excluded with no private query. Genuine read/hit refs remain even for empty source bodies. No arbitrary nonempty body/known failure can self-certify no-source status. Group/source/use SQL proof and graph suppression remain original-owner obligations. Required two-call pagination test stitches exact window despite changed request/hash/history; insufficient remaining capacity leaves cursor unchanged. No fake empty-source provenance, no guessed lexical-as-hybrid claim.

### Usage correction retained with the owner

Complete known usage with provider source=estimated stays estimated; it never becomes reported merely because both numbers exist. Known reported zero stays zero. Partial missing components use existing reservation and retain raw nullable usage/source metadata; both absent stays unknown provenance. Sent uncertainty retains conservative reservations. This is implemented once by #43 metadata-only settlement without hydrating source/result bodies, with replay/late-revocation/zero/None/estimated tests; #44 owns no arithmetic copy.

## 21. F44-R5 — native source-read/decode/render bounds before image activation

Actual native behavior inspected: storage.download_bytes calls response.read() without explicit cap; image evidence target downloads full object and calls image.load() before crop geometry checks; PDF target downloads source, then renders150dpi pixmap before checking1280 edge and re-rendering. visual_enrichment image count does not cap explicit+retrieved source bytes or intermediate decode/render allocations. Earlier “existing bounded loader” assertion is withdrawn.

Required original native storage/image/PDF owner amendment (proposal only, no files changed): one immutable per-admission image budget with strictly validated configured limits `maxSourceBytesPerObject,maxSourceBytesTotal,maxDecodePixelsPerObject,maxDecodedBytesPerObject,maxDecodedBytesTotal,maxRenderPixelsPerOperation,maxRenderBytesPerOperation,maxRenderBytesTotal,maxImages,maxPngBytesPerImage,maxPngBytesTotal,maxDecodeRenderOperations,deadline`. Real values need resource measurements and owner review; this contract creates no production defaults or capabilities.

- **Source read:** authorize exact native object/version before fetch; reserve task aggregate upper bound before reading. Stat/content-length may reject early but is not trusted as sole bound. Incrementally read at most remaining per-object/task bytes plus one detection byte, enforce deadline, reject on excess and always close/release response. Never call full response.read() then claim prevention. Stream SHA-256 and match the original source version; failures release only provably unused reservations, with concurrent reads counted atomically by the native owner.
- **Image decode:** after bounded source bytes, inspect PNG header dimensions/format before image.load/crop. Reject width/height/pixel arithmetic overflow or expected source geometry mismatch. Require `width*height <= maxDecodePixelsPerObject`; conservatively derive decoded channel/stride bytes and check per-object/task limits before allocation. Pillow decompression warnings become rejection, not silent disablement. Header checks alone do not bound malformed decoder/internal overhead; native execution must have a reviewed hard memory/time boundary (isolated bounded decoder worker if library cannot enforce it) before claiming full allocation protection. No such worker is implemented or authorized by this text slice.
- **PDF parse/render:** bounded source bytes precede opening PDF. Parsing may itself allocate before page geometry is available, so apply the same reviewed hard memory/time execution boundary. Determine clip/page rotation/geometry and the existing eventual render transform first; compute ceil(pixel width)*ceil(pixel height), channels/stride and conservative renderer overhead bounds before any get_pixmap. Reject if limits cannot be met. Remove the oversized first150dpi allocation by computing the exact transform the native final render would have used in advance; preserve pixel rounding/clip behavior with byte/geometry parity fixtures. Do not introduce a new downscale policy to make an input pass. If equivalent sizing cannot be established, reject explicitly rather than claim unchanged crop bytes.
- **Aggregate output:** reserve count across explicit targets/regions first, followed by retrieved crops in native order. Account per-operation CPU/time, peak allocations and cumulative output bytes; optional retrieval output limits do not waive explicit-target or shared aggregate caps. Check PNG encoding output incrementally where supported, or reserve a proven encoding upper bound before encoding. Unsupported input fails with a bounded resource error; no skipped explicit region/image, silent shrink or OCR replacement.
- **Provider bridge:** only validated native crop bytes enter proposed GenerationImage with original ordering/detail=high and exact source refs. Base64 and request-archive size limits are a later independent boundary; they cannot fix earlier read/decode/render over-allocation. Anthropic retains its native image block form without fabricated detail field.

Original-owner evidence required before R4/R5 multimodal activation: read response larger than claimed length and exact cap boundary; concurrent aggregate overrun; compressed image with huge header/decode size; malformed PNG; huge PDF page/clip/rotation with allocation denied **before** first pixmap; decoder timeout/memory abort cleanup; explicit multiple targets/multiple regions then retrieved crops preserving actual native bytes/order/geometry under supported bounds. Show resource admission events/allocation hooks, not just final DTO rejection. No production activation from synthetic capacity profiles or post-read size checks.

R1/R3/R5 corrections remain owner-review proposals and do not block authorized text-only pure profile resolve. Full same-question tools, source authority, repeated post-question compaction, frozen budget/effects/cancel, legacy visual parity and approved provisional SSE/UI still require actual owner implementation/runtime evidence. This task does not close #44/#41 or waive merge/service gates.
