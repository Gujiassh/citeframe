# Issue 41 — independent Critical design oracles

Date: 2026-09-28 (Asia/Shanghai). Phase: baseline inspection and semantic-oracle establishment; separate design audit pending controller request.
Risk: **Critical** — privacy, permissions, persistence, migrations, source fidelity, cross-process recovery and user-visible behavior.
Owned artifact: `specs/v5/memory-management/reviews/design-oracles.md` only.

## 1. Governing outcome and authority

The goal covers ordinary chat **and** Research: bounded recent context, semantic task summaries, justified cross-conversation memory, corrections/supersession, proactive history search and exact source reading, permission/lifecycle enforcement, actual provider/tool/stream execution, and usable memory management. Research retains conditions, negation, conflicts, evidence links and recovery bindings. Original chat, evidence, task and report storage meanings remain invariant. Memory tables alone cannot satisfy this outcome.

Authorities read:

- Full 360-line proposal, sections 1–11: `C:/Users/baiao/Documents/Codex/2026-09-21/ai-ensemble-fork/outputs/Citeframe-记忆管理改造方案.md`.
- Latest assignment overrides proposal candidate/sharing language: private default; **no ambiguous-inference long-term candidate path**; explicit remember requests / confirmed decisions, constraints and preferences / verifiably sourced observations only. Observed information never becomes user confirmation by relabeling. Unresolved Research facts/conflicts remain task-local.
- Source deletion invalidates dependent memories/summaries before async cleanup; surviving sources require recomputation. Research frozen scope cannot expand.
- Necessary contracts and migrations require auditable design and independent review before implementation. New sharing, raw archive deletion and evidence-permission expansion are outside authorization.
- `D:/AI/profile/AGENTS.windows.md`, `MEMORY-POLICY.md`, `SOUL.md`, `IDENTITY.md`; `D:/Code/AGENTS.md`, its `.grok/AGENTS.md` redirect, `apps/web/AGENTS.md`; project-architecture skill and architecture-guidance reference. No private `MEMORY.md` was read. Project artifacts provide the relevant history for this isolated reviewer.
- `specs/v5/memory-management/spec.md` and `delivery.md` were read during baseline inspection. At the subsequent design review, the effective spec was reread: §§6–7 now explicitly admit only authorized/verifiable information and prohibit persistence of unvalidated intermediate long-term content. The controller removed the earlier generic candidate wording. The no-ambiguous-long-term-candidate oracle remains governing; spec edits remain outside this reviewer lane.

This document records review obligations and baseline observations. It does not author product code, migrations, tests or the developer design, or approve an unreviewed design.

## 2. Baseline and evidence boundary

- Canonical: `D:/Code/citeframe`, branch `refactor/workspace-access-dependencies`.
- Starting HEAD: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Dirty work belongs to Issue40: access router dependencies; four embedding/image test updates; workspace-access tests/docs/evidence. Observed `git diff --stat`: 15 tracked files, 583 insertions / 220 deletions. This is a worktree observation, not an immutable merged baseline or Issue41 work.
- Remote: `https://github.com/Gujiassh/citeframe.git`; local/global Git identity agrees (`gujishh`). No config changes, branch changes, worktrees, staging, commits, resets, stash, service or shared workbench changes performed.
- Design/inventory were absent at initial listings. `design.md` appeared before artifact write; it is intentionally **not reviewed in this phase**. Baseline inspection did not wait for it.
- Evidence: source inspection and read-only Git metadata. No tests, migrations, server, browser, paid model evaluations or shared-service probes ran. Inspected test definitions are regression anchors, not newly accepted executions.

Selected SHA-256 fingerprints distinguish inspected content from HEAD; these support identity only:

| File | Observed hash |
| --- | --- |
| `apps/api/src/ai_pdf_api/services/chat.py` | `DD6D28F8629C1655ACA238B817ACE9BE81C4DFB33C4198027B8FE9F966973C91` |
| `apps/api/src/ai_pdf_api/routers/chat.py` | `9062FA3B3592C441FC8917EE76A3892A17821DAE10F922A2A229750D49450A73` |
| `apps/api/src/ai_pdf_api/routers/deps.py` | `AC067CDAE26A100C99DC435EE3B5D76F5BCB0084F3B371E30942CF2C11CF38DA` |
| `apps/api/src/ai_pdf_api/services/research/research_context_policy.py` | `1FF008C6297E69C40FB37168321E7F528D640AD5489614FCA613F915C5190290` |
| `apps/worker/src/ai_pdf_worker/research/adapters/generation.py` | `7C79295517357E7538AE0C7AAE8778DACFB693061F0192DA07F0C706C9A2EF15` |

Final read-only verification observed a concurrent external HEAD advance to `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae` (`refactor(api): unify workspace authorization dependencies`) on the same branch; tracked `git diff --stat` was then empty. This reviewer made no commit. All five content fingerprints above were rechecked and unchanged. This records external baseline movement, not a merge/handoff acceptance.

Re-anchor against the exact Issue40 merged handoff before implementation. Starting HEAD alone does not include the inspected dirty dependency behavior.

## 3. Baseline risk gaps and design gates

These are design risks exposed by source inspection, not findings against the unreviewed design.

### Critical G1 — private context can leak through workspace-readable outputs

`routers/chat.py:list_threads`, `get_workspace_thread`, `list_thread_messages` authorize workspace membership rather than thread creator identity. A private memory recalled for A may be copied into an assistant message that B can read. Private data can also reach shared Research plans/reports, summaries, tool traces, caches or logs.

Require an explicit **output-audience rule**, covering prompts, answers, stored messages, task summaries, artifacts, source drill-down, tool storage and observability. Owner-scoped memory queries alone do not prove private-default behavior. Test a second member reading the resulting output after reload. Preserve existing chat/Research visibility and introduce no implicit sharing. If these constraints prevent a planned integration, expose that product limitation and unmet acceptance gate; do not silently omit capability or disclose private context.

### Critical G2 — historical actor identity cannot be inferred from thread ownership

`packages/backend-persistence/src/citeframe_persistence/models/chat_message.py` has role/content/thread/workspace/parent, but no per-message user identity. `ChatThread.created_by_user_id` identifies the creator. `services/chat.py:prepare_chat` discards `user_id`; members can send to workspace-accessible threads.

Require trustworthy actor/provenance for new saves and confirmations, and a policy for unattributable historical messages. Never backfill ownership/confirmation from creator, current reader, a `user` role, ordering or model inference. Enumerate an additive sidecar/contract and callers if needed. A co-member's correction cannot supersede someone else's private decision.

### High G3 — deletion signals differ from derived-data invalidation

`routers/assets.py:delete_asset` commits `status="deleting"` and cleanup job under asset lock. `deleted_at` is set later in `services/ingestion.py:process_delete_cleanup`. Retrieval requires ready/current/nondeleted assets. Chat citation `sourceAvailable` uses `deleted_at`. Research `load_frozen_evidence` returns its retained excerpt even with `source_available=False`.

Require synchronous eligibility/invalidation for new derived data: pending/failed cleanup, transitive summary dependencies, all reads, delayed jobs and in-flight adoption. Waiting for index cleanup or `deleted_at` is insufficient. Preserve historical evidence/citation/report contracts; retained excerpt storage does not authorize returning removed sources through new memory tools. Distinguish thread archive, source removal, memory delete, disable and expiry. No new raw archive deletion.

### High G4 — excerpt paths do not establish exact original retrieval

Chat retrieval prompt takes 4,000 characters/unit and citation snapshots 800; Research search captures `text_content[:2000]`, and load returns that snapshot.

Require typed reference identity/version, exact range and continuation, and explicit distinction between evidence excerpt, normalized representation, original message and original file bytes. No paraphrase/snippet labeled complete original; no newest-version substitution after reindex. `read_source` must reject arbitrary object keys, URLs, filesystem paths and cross-workspace IDs.

### High G5 — provider interfaces currently expose text, not an agent tool cycle

`GenerationProvider` exposes `generate -> str`, `stream -> Iterator[str]`. Responses streaming extracts text/completion; Chat Completions rejects `tool_calls`; DeepSeek has an Anthropic-compatible mapping/parser. Chat SSE has `meta`, `delta`, `citations`, `done`, `error`. BFF upstream fetch has no explicit request signal, and inspected chat submission does not prove end-to-end cancellation.

Require actual protocol capability matrix, typed call IDs/arguments/results, fragmented-stream assembly, terminal validation, client parser changes, bounded orchestration and cancellation. Unsupported capabilities need explicit errors; no ignored tool call, success with empty answer, silent text-only fallback or “saved” before durable success. External-call unknown and database-commit unknown outcomes need distinct handling.

### High G6 — Research already has frozen versions and recovery authority

Neutral persistence commands own leases/ledgers; execution freezes workflow/Agent IO/context/provider/source bindings. Context packing performs typed batching, not semantic summary extraction. Provider ledgers gate call counts and per-call tokens; new cumulative limits cannot silently replace existing semantics. Conflict journals retain outcome-unknown operations.

Require memory binding/version strategy, role-by-role use, old-run readers, replay and revocation precedence, task-state authority and exact budget integration. A frozen memory snapshot cannot override current source invalidation. Memory cannot become current verified evidence or rewrite original claims, decisions, conflict journals, events or report editions.

### High G7 — races can recreate deleted or superseded facts

No existing inspected memory revision/extraction/invalidation contract establishes these guarantees. Require DB constraints, CAS predicates, scoped idempotency/request hashes, transaction/lock order, invalidation fences and job/outbox lifecycle. Cover delete versus index/recompute, concurrent correction, duplicate saves, revoke versus adoption, crashes around commit and late model completion. Merging source IDs does not prove surviving sources support old wording.

### High G8 — budget reduction needs semantic and real-product acceptance

Small prompts and valid JSON do not prove conditions/negation/precision/corrections survived. Existing chat requires ready asset scope and successful retrieval/targets before generation; memory-only/history-only requests cannot assume this prerequisite disappears.

Require explicit no-ready-assets entry behavior, whole turn/tool units, summary coverage, summary failure/required-input overflow behavior and provider-specific accounting. Labeled semantic fixtures and visible UI walkthrough are independent gates. No paid evaluation is authorized in this phase.

## 4. Actual baseline paths

Paths are relative to canonical repository; symbols supplement line anchors where Issue40 is moving routes.

| Ref | Actual path / symbol | Observed semantics and preservation boundary |
| --- | --- | --- |
| B01 | `apps/api/src/ai_pdf_api/routers/deps.py:require_user_id`, `get_accessible_workspace`, `require_workspace_member`; `apps/web/src/app/api/workspaces/[workspaceId]/chat/stream/route.ts` | BFF obtains session and injects identity; API validates internal token. Membership excludes archived workspaces. Request-local `WorkspaceAccess` does not prove in-flight revocation. |
| B02 | `packages/backend-persistence/src/citeframe_persistence/models/{chat_thread,chat_message}.py`; `apps/api/src/ai_pdf_api/schemas/chat.py:ChatStreamRequest`, `Message` | Parent-linked messages, mutable active leaf, thread creator, no per-message actor/version. Question max 12,000; existing asset/evidence scope contract. |
| B03 | `apps/api/src/ai_pdf_api/services/chat.py:prepare_chat`, `_get_message_lineage` (around 65, 385); router `_resolve_parent_message_id` (324 onward) | Parent/thread/workspace validated; completed ancestors in parent order. Failed assistant parent can be continued but its error text is omitted from generation lineage. Edit forks from old user's parent and retains original rows. No semantic summary/token-selection/history-tool loop found here. |
| B04 | Same service: `_resolve_asset_scope`, `_build_retrieval_context`, `_build_user_prompt`, `_build_generation_user_message` | Requires eligible assets and retrieval or explicit target; system prompt + completed lineage + evidence prompt; character-limited excerpts; visual enrichment supplies multimodal payloads. |
| B05 | Same service: `finalize_chat`, `fail_chat`; `routers/chat.py:stream_chat` | Prepared user/assistant/citation rows commit before generation. Success stores stripped answer and active leaf; failure stores failed assistant, removes its citations/locators and makes it active. SSE: meta, deltas, citations, done; `GeneratorExit` fails unfinished generation. New tool rows must not recast existing message/citation semantics. |
| B06 | `apps/api/src/ai_pdf_api/services/providers.py:GenerationProvider`, `OpenAIGenerationProvider`, `_read_response_stream`, `DeepSeekGenerationProvider`; `services/chat_completions.py` | Text-only public generation contract and protocol-specific completion checks. No inspected generic tool/usage stream; unknown usage/cost cannot become measured billing. |
| B07 | `apps/api/src/ai_pdf_api/services/retrieval.py:retrieval_scope_statement` (57–98) and dense/lexical queries | Joined asset/unit/representation/locator workspace and identity, current generation/index, ready/nondeleted source. History search needs its own authorization/source semantics. |
| B08 | `routers/assets.py:delete_asset` (1505 onward); `services/ingestion.py:process_delete_cleanup` (329 onward); `routers/chat.py:to_citation`, `to_input_evidence` | Deletion queued before physical cleanup; retained locator/excerpt serialization. New derived eligibility must become immediate without rewriting old snapshots. |
| B09 | `apps/api/src/ai_pdf_api/services/research/research_context_policy.py:pack_provider_messages` (377 onward), `decode_compact_payload`; `research_agent_io_registry.py:estimate_text_tokens` (395 onward) | Complete typed batching; mandatory overflow rejects before send. UTF-8 byte-count/4 rounded estimate is labeled local; not exact token measurement or semantic compression. |
| B10 | `apps/worker/src/ai_pdf_worker/research/adapters/generation.py:LedgeredGeneration._generate`; `adapters/evidence.py:SqlEvidenceToolPort` | Frozen role/version/profile, reserved/sent/reconciled calls, output ceilings, estimated/nonfinal unknown usage. Handles validate workspace/run/snapshot/step/branch/generation/index. |
| B11 | `apps/api/src/ai_pdf_api/services/research/research_worker_evidence.py:_frozen_execution_context`, `search_frozen_evidence`, `load_frozen_evidence` (55, 178, 420) | Frozen source scope, tool provenance, 2,000-character snapshots, exact handle ordering; retained content and current availability are distinct. |
| B12 | `packages/research-persistence/src/citeframe_research_persistence/{lease,membership,provider,tools,publication_adoption}.py` | Run → Step → Attempt → Call → Ledger lock chain; active lease/creator checks; adoption locks membership through commit. Provider/tool count reservations, per-call token ceilings, nullable cost. Static inspection does not reverify every runtime boundary. |
| B13 | Same package `adaptive_turns.py`, `conflict_investigation.py`, journal/report integrity modules; API `services/research/research_report_edit.py` | Frozen input/result journals and unknown outcomes; report edits check creator/membership, original artifact ID/hash and expected version. These are integration regression anchors. |
| B14 | `apps/worker/src/ai_pdf_worker/research/persistence.py`; `packages/backend-contracts`, `backend-persistence`, `research-persistence`; `apps/api/alembic/versions` | Neutral contracts/mappings/persistence and API-owned Alembic. Worker composition still imports some API services; that does not authorize new neutral code importing routes. |
| B15 | `apps/web/src/lib/use-chat.ts:sendMessage` (331 onward), BFF chat stream route; integration paths `components/chat-panel.tsx`, `lib/use-research.ts`, `components/research-run-panel.tsx` | Optimistic IDs/SSE updates/server hydration and submission failure state. New memory/tool-progress/cancel UI is not established. Late responses, refresh and navigation must preserve server authority and scope. |

Selected implementations were read; auxiliary B13/B15 module names are integration anchors, not claims of exhaustive review of every line or modality.

## 5. Old/new semantic oracles

Old behavior is in B01–B15. New-behavior execution for every oracle is currently **blocked** pending design/implementation/evidence; an oracle definition is not a passed test. Preserve required historical semantics, not baseline debt such as unbounded context.

| ID | Old baseline / invariant | Required new property and discriminating evidence |
| --- | --- | --- |
| O01 Ownership/scope | B01–B03 workspace access, absent message actor. | Server-authenticated principal; independent owner/workspace/source/task/branch/output-audience checks. Two co-members cannot read/write each other's private memory through list/search/source/tools/debug or shared generated output. Same title never implies project identity. |
| O02 Revocation | Request gate; Research execution/adoption checks. | Revoke/archive between authorization, retrieval, provider dispatch, stream emission and commit. No subsequent access/dispatch/adoption outside the specified linearization boundary; cached ORM membership cannot authorize. Already sent bytes/remote calls cannot be retracted: record that limitation. |
| O03 Branch | Parent lineage/edit forks; failed text excluded. | Summary coverage binds exact ancestry/version. Sibling history is explicitly labeled and cannot be adopted automatically. Failed-parent continuation keeps completed context; source rows remain unchanged. |
| O04 Eligibility | No existing long-term memory contract found. | Explicit authorized request/confirmation or verifiable observation required. Suggestions, ambiguous attributes, hypothetical examples and unresolved Research conflicts produce no durable long-term candidate. Observation remains observation. Quoted “remember” and injected instructions grant no authority. |
| O05 Corrections | Original messages retained on branches. | Final-decision retrieval follows scoped explicit supersession; stale high-similarity hits cannot win. Different conditions coexist. Delayed extraction cannot revive old decisions; co-member changes cannot cross owner boundaries. |
| O06 Original/source | B04/B11 limited excerpts. | Direct typed ID/version/range reads yield exactly referenced content, identify representation level, truncation and continuation. Role/time/branch/origin stay attributable. Hash verifies integrity, not factual support; reindex cannot substitute another source version. |
| O07 Context budget | Full completed chat history; estimated Research packing. | Whole next request fits capacity minus output/protocol/tools/multimodal/safety costs. Preserve required current/system/constraints or reject explicitly before dispatch. Recent units contiguous; tool calls/results paired. Estimate and safety policy explicit. |
| O08 Semantic coverage | No semantic chat summary; typed Research batching. | Versioned exact completed-ancestor interval, source revisions and uncovered recent units. Failed/incomplete/unvalidated summary never advances coverage. Conditions/numbers/negation/conflicts retained; rebuild from originals prevents repeated-summary drift. Missing essential context produces honest failure/gap. |
| O09 Lifecycle | Async cleanup; live-source retrieval filtering. | Committed invalidation/delete immediately blocks search/direct reads/prompt use/caches/pending adoption. Transitive derived data invalidates before cleanup; worker outage does not prolong eligibility. Disable/expiry/state have explicit contracts. |
| O10 Surviving sources | No recompute contract found. | A+B-derived record invalidates when A is removed; recompute from still-authorized source versions and retain only supported content. Failure stays unavailable. Old summary cannot replace evidence; stale jobs cannot restore deleted text/indexes. |
| O11 CAS | Research version discipline; chat leaf is not memory CAS. | Two edits from one version yield one winner and explicit conflict with draft retained. Revision/source merge/supersession/job writes atomic as designed. No cross-owner chains, cycles, lost successful save or silent overwrite. |
| O12 Idempotency/unknown | Research journals/ledgers. | Same scoped key+payload yields same durable result; changed payload conflicts. Lost acknowledgement never duplicates memory/revisions/jobs. Unknown external outcome is neither success nor safe resend; reconcile without changing immutable call identity/hash. |
| O13 Active tools | Text generation/SSE only. | Actual provider → structured tool call → server validation → bounded result → continuation → answer path for all three tools. Stable source/status/truncation metadata; no tool-supplied identity/privilege expansion; explicit unknown/malformed/unsupported-call outcome. |
| O14 Limits/cancel | Research reservations; no accepted chat loop cancellation. | Concrete per-round/cumulative provider/tool/result-token/time/repetition ceilings enforced before work, including parallel calls at last slot. Cancellation prevents new dispatch/late adoption. Pending/unknown calls and background extraction/summary/rerank usage remain accounted with honest provenance. |
| O15 Stream/failure | Baseline SSE success/failure and provider terminal checks. | Fragmented args, partial text, missing terminal, refusal, truncation/disconnect/error cannot become completed answer or successful save. Preserve payloads or define reviewed additive/versioned events/readers. Tool status stays distinct from assistant prose/evidence citations. |
| O16 Research evidence | Frozen handles/claims/journals/reports. | Memory may guide permitted planning but cannot be verified citation or widen assets. Verifier checks frozen evidence; conditions/unresolved sides remain separate. Original Claim text, locators/fingerprints, conflict journal and report-edit semantics unchanged. |
| O17 Recovery | Frozen versions, DB authority, leases. | Pin memory/context inputs for recovery, revalidate current eligibility. Old-run readers retain frozen semantics. Branch memories isolate updates and merge with provenance, never overriding DB step/run statuses or join authority. |
| O18 Migration | API-owned migration/shared mappings. | Old message/citation/evidence/task/report rows and meanings compare equal except enumerated additive contracts. No inferred historical owner/confirmation or bulk promotion. Fresh/staged upgrade, restart/backfill and rollback limits explicit. |
| O19 Architecture | Neutral persistence, explicit composition roots. | New shared memory modules do not import API routes/FastAPI authorization shortcuts. Explicit principal/access/source/provider/storage ports; context/extraction/lifecycle/storage/UI responsibilities separated. No large router/shell absorbs orchestration. |
| O20 Visible management | Existing chat hydration; no new UI accepted. | User can find/list/source-inspect/correct/disable/delete memory, recover conflict/failure and refresh to truth. No false physical-purge promise; draft retained; account/navigation change cannot render late private output. No-data/no-assets paths explicit. |
| O21 Quality/absence | No Issue41 quality baseline measured. | Labeled answer/support/condition/correction/uncertainty cases for both chat and Research. Misses express uncertainty. Scripted fixtures demonstrate mechanics only; real-model semantic quality is separately authorized/evidenced. Thresholds follow labels and baseline. |

## 6. Required auditable design/migration packet

Before implementation, design and code inventory must provide:

1. **Coverage map:** every outcome and O01–O21 to API/Worker/Web, persistence owner and evidence. Deferred capability keeps an unmet delivery gate.
2. **Exact types/contracts:** owner/scope/visibility/provenance, source unions/versions, eligibility/confirmation, task versus long-term state, revisions/supersession, summary coverage, idempotency/jobs/indexes; nullability, immutable fields, composite references, uniqueness/check constraints, forbidden transitions; requests/responses/errors/SSE and every affected caller.
3. **Authority/audience matrix:** member/owner/nonmember/revoked user, actor versus thread creator, task/branch/API/worker/output audience. Cover direct IDs, cursor tokens, caches, embeddings, provider/reranker disclosure and logs. Workspace ownership grants no automatic access to another user's private memory.
4. **State and transaction diagrams:** explicit save/extraction/correction/invalidation/recompute/disable/delete/retry/unknown commit; durable point before “saved”; linearization and lock order against Research roots. Do not hold locks across unbounded provider IO without a justified bounded protocol.
5. **Provider/tool loop:** actual capabilities/protocols, text/image/tool formats, streamed arguments, token/estimate policy, concrete hard limits, timeout/cancel propagation, usage and terminal/error persistence. Specify behavior when necessary context/tool capabilities are unavailable.
6. **Research impact:** every role's integration, branch identity, frozen evidence/memory binding, old v2/v3/v4 workflow and IO/context registry readers, ledger semantics, journals, correction projection, report edits and source-invalid resume.
7. **Migration:** exact post-Issue40 predecessor, tables/fields/indexes/constraints, API Alembic ownership, API/Worker deployment compatibility, active-write/backfill concurrency, historical attribution limits, restartability, locking/capacity and rollback/data-retention limits. No raw archive deletion.
8. **Lifecycle:** every read/write, cached prompt, summary, lexical/vector hit and delayed job obeys current eligibility; duplicate/tombstone retention, retry visibility, no secrets/unneeded text in diagnostics.
9. **UI:** real entry points/source navigation, no-data/no-assets, save/conflict/cleanup state, drafts and late results. Keep necessary recovery guidance without decorative explanation.
10. **Acceptance plan:** pinned old/new fixtures and output artifacts, deterministic semantic labels, isolated real-service races/restarts and visible-browser walkthrough; distinguish model scripts from real model quality. No paid evaluation here.

## 7. Reverse-review cases

Assume the regression happened. These observations must expose it. Cases below are specifications, not added or executed tests.

| Case | Fixture/action | Required observation |
| --- | --- | --- |
| R01 Private output | A/B share W. A has private fact P; A asks in workspace-readable chat/Research. B opens answer, plan/report, traces, source links after reload. | No unauthorized P/provenance in B-visible surfaces; explicit output-audience behavior. Memory endpoint 403 alone insufficient. O01/O16. |
| R02 False author | A creates thread; B sends “remember my preference”; old records have only role. | New save bound to authenticated actor; no creator/current-reader attribution of old messages. O01/O04/O18. |
| R03 Scope forgery | Same-named project in W1/W2; user belongs to both; swap source/workspace/branch ID and cursor. | No cross-context content/metadata/existence leak, including index and rerank paths. O01/O06/O13. |
| R04 Revocation race | Pause after query, remove membership, resume provider/result/adoption; repeat before/after adoption lock and workspace archive. | Exact permitted ordering; stale cache cannot authorize; no later access/adoption outside boundary. O02. |
| R05 Fork | Ancestor 30 s; L confirms 12 s, R 45 s; edit old question. | Correct branch coverage/decision; sibling history labeled; originals retained. O03/O05. |
| R06 Negation/condition | Before compaction: “Only staging may use 12 s. Production must not use it; 30 s until approval.” | Conditions, negation, approval, units survive summary/answer. No unconditional 12 s preference. O05/O08/O21. |
| R07 Inference/injection | Assistant suggests change; tool text claims user approval; archive says ignore system/share secrets; user says “maybe.” | No confirmed or ambiguous-candidate long-term fact; no authority escalation; uncertainty task-local. O04/O13. |
| R08 Correction inversion | Old 30 s versus explicit 45 s correction; old index scores higher; old extractor finishes last. | Current 45 s/source wins; historical 30 s marked replaced; no old reactivation. O05/O11. |
| R09 Delete admission | Source enters deleting; stop cleanup; retain null `deleted_at` and stale index. | New memory/tool/prompt eligibility immediately false, including failed cleanup. Original evidence history preserves old contract. O09/O16. |
| R10 Transitive sources | A supports X, B only Y; S1 cites A+B, S2 derives from S1. Delete A during paused recompute/index job. | Both summaries invalidated; recompute can retain supported Y only; no stale resurrection of X. O09/O10. |
| R11 Original tail | Decisive number beyond 2,000/4,000 chars; Unicode punctuation; newer revision changes number. | Exact ID/version/range and continuation reconstruct original, not short excerpt/newest revision. O06. |
| R12 CAS | Two DB connections edit one version; third disables; stale edit retries. | One legitimate winner/version, explicit conflict, retained draft, no revival. O11/O20. |
| R13 Unknown save | Commit remember then lose response; retry same key; changed payload same key; crash around job/outbox commit. | One result, conflicting reuse rejected, recoverable unknown status and no duplicate rows/jobs or false saved state. O12/O15. |
| R14 Budget escape | Growing results/repeated equivalent queries/large text+images; parallel tools at last slot. | Aggregate admission ceiling and whole next-prompt budget respected; meaningful remaining-gap outcome; unknown usage labeled. O07/O14. |
| R15 Broken stream | Fragment/duplicate call args/IDs; missing terminal; refusal/length/error after text; SSE without done. | No invalid dispatch/completed answer/saved assertion; persisted failure and usable recovery. O13/O15. |
| R16 Cancel/late | Cancel before send, during source/provider IO and before commit; switch user/workspace while streaming. | No next dispatch or late wrong-context UI/adoption; remote unknown accounted. O02/O14/O20. |
| R17 Frozen escape | Memory cites C; run frozen to A/B; verifier/synthesizer asked to use C or erase conflict from memory. | No C evidence admission; original claim/handle/conflict contract preserved; unresolved stays explicit. O16/O17. |
| R18 Recovery | Resume old workflow; memory changed/disabled/source revoked since checkpoint; stale worker finishes expired lease. | Pinned inputs verified, live eligibility wins, no unauthorized latest-memory substitution or stale adoption. O09/O17. |
| R19 Coverage hole | Summary fails or valid JSON omits negation; summary jobs race with branch edits. | No unsupported coverage advance; exact interval/CAS, explicit required-context failure; labels detect semantic omission. O08/O21. |
| R20 Upgrade | Populated chats/failed branch/citation note/old Research/conflict journal/report edit; interrupt backfill. | Old IDs/locators/rows/events/replay meanings preserved; no guessed owner/confirmation; feature delta separately compared. O18. |
| R21 Real entry | Empty memory/no-ready-assets; explicit save; long conversation/read original; concurrent edit; disable/delete; refresh/revoke. | Clear supported path and actionable failure/recovery, durable truth, retained draft. Actual user walkthrough required. O20/full goal. |

## 8. Verification requirements

### Existing regression anchors — inspected or located, not executed

- `apps/api/tests/test_chat_service.py`: branches/failed parents, retrieval isolation/current index, persisted prompt/top-K, citation geometry and persistence.
- `apps/api/tests/test_chat_router.py`: thread lifecycle, parent-ordered active branch and HTTP failed-parent continuation.
- `apps/api/tests/test_embedding_current_scope.py`, `test_embedding_index_contract.py`, `test_image_evidence_lifecycle.py`: current source/index boundaries; Issue40 dirty files, not reviewer-owned.
- `apps/api/tests/test_research_v5c_contract.py`: typed compact round-trip/malformed batches/overflow, registry, nullable pricing and per-call ceilings.
- `apps/api/tests/test_research_persistence_boundary.py`, `test_chat_import_boundaries.py`: neutral imports/composition and modality boundaries.
- Additional located candidates: API `test_research_publication_adoption.py`, `test_research_conflict_integrity.py`, `test_research_report_edit.py`; Worker `test_research_v5c_agent_io.py`, `test_research_adaptive_retrieval.py`, `test_research_conflict_investigation.py`; Web `src/lib/use-chat.test.ts`, `e2e/research-run.spec.ts`.

| Evidence level | Required artifact | Limitation |
| --- | --- | --- |
| D Design/static | Exact contract/migration/state/authority/dependency review and reverse-case mapping. | Can approve design scope; cannot prove races/model quality/usability. |
| T Deterministic | Exact command/environment, labeled inputs/sources/expected versus actual outputs, injected complete/incomplete/tool/error providers and negative controls. | Scripted provider validates mechanics, not deployed model's semantic choices. |
| M Migration | Disposable real PostgreSQL fresh and populated staged upgrade; old-row/payload comparison, version readers, restart/backfill/locks/rollback limits. | SQLite/create_all/metadata counts do not prove production migration/locks. No shared migration authorized here. |
| R Runtime/security | Isolated real API/BFF/Worker, PostgreSQL/object store; two users/workspaces, actual races/index lag/process exits/lease expiry/cancel/revocation. Network, ledger, jobs and DB observations with precise order. | Injected model valid for mechanics; real model quality separate. Issue40 success cannot accept Issue41. |
| U Visible UI | Ordinary visible-browser workspace/chat/Research navigation through all new flows, source inspection, failure recovery, reload/restart; bounded screenshots/recording plus network/state linkage. | API success/headless DOM/mocks/components alone cannot establish usable flow. None ran here. |
| Q Semantic quality | Annotated chat/Research corpus and old/new outputs: conditions, negation, precision, corrections, support, uncertainty; latency and honest usage/cost. | Paid runs require separate authorization. With no real-model evidence, Q stays blocked, separate from T. |

Each evidence result records exact SHA plus dirty diff/fixtures, command, environment/provider type, raw artifact, expected invariant, observation, scope status and limits. New-feature and historical-invariant comparators stay separate; no broad whitelist hides altered storage/API meaning. Resolve actual test/typecheck/e2e/Alembic commands from manifests before execution; no guessed command is reported as passed.

## 9. Evidence-scoped disposition and handoff

| Review area | Status | Evidence scope |
| --- | --- | --- |
| Governing goal/latest authorization captured | **pass** | Full goal mapped, ambiguous long-term candidate/new sharing/evidence expansion excluded. |
| Baseline inspection/oracle establishment | **pass** | Code-grounded entry points, risks, old/new invariants and reverse cases recorded; static only. |
| Existing application runtime/security correctness | **blocked** | This inspection does not independently accept Issue40 or all prior Research behavior. |
| Issue41 design/contracts/migration approval | **blocked** | Developer design/inventory not audited in this phase; G1–G8 and §6 require answers. |
| Product/unit/integration acceptance | **blocked** | No Issue41 implementation or executed fixture evidence accepted here. |
| Migration/locks/races/restart acceptance | **blocked** | No Issue41 production-database evidence. |
| Provider/tool/SSE/cancel acceptance | **blocked** | Existing text paths do not prove required tool orchestration. |
| Visible UI acceptance | **blocked** | No actual memory-flow walkthrough. |
| Real model quality | **blocked** | No model evaluation; paid runs unauthorized. Deterministic mechanics are separate. |
| New sharing/raw archive deletion/evidence expansion | **not applicable** | Outside authorized scope; not a safety pass. Any proposal reopens authorization. |
| Reviewer product/test/migration edits | **not applicable** | Only this document is owned. |

Baseline/oracle phase is complete. This artifact grants no implementation approval. On the next controller request, audit developer design/inventory against the full goal, G1–G8, O01–O21 and R01–R21; report findings first with exact sections and scoped disposition. Preserve original chat/Research semantics and canonical dirty worktree.

Write-back check: durable findings are contained in this sole owned repository artifact. No private/global memory or shared workbench write is appropriate to this isolated lane; no duplicate global note created.


## 10. Subsequent design-review status — 2026-09-28

The requested independent audit of the effective design (including the concurrently completed section 17) is recorded in [design-review.md](design-review.md). Integrated design disposition: **rework required**, with nine open P1 findings. The initial P0 fencing-contract finding was closed at design level by the concurrently completed §17.7; its runtime evidence remains pending. A1 remains controller-escalated and unapproved; A2 and numerical operational choices do not create new per-number user gates. An A1-independent explicit-instruction persistence subset is feasible only after narrow corrected-contract review and the Issue40 handoff. All runtime, migration, visible-UI and real-model-quality oracles remain unexecuted. Baseline-phase pass above retains its original static scope.

## 11. Mandatory same-run automatic compaction — spec v3 §12

Authority update, 2026-09-28: full external proposal v2 (419 lines) and repository spec v3 read; complete §12 text matches. This extends the original outcome to automatic compaction during one task, including every main dispatch/tool continuation/Research role change/resume. Healthy compaction preserves execution identities and automatically continues without new user input. It is separate from long-term admission; task uncertainty remains permitted. No Codex internal algorithm or encrypted format is promised. A1 audience and #40 baseline gates are unchanged.

Existing O01–O21/R01–R21 remain applicable. New oracles below are **defined, not executed**. They extend O07/O08/O12/O14/O17/O20/O21; the prior static baseline pass supplies no compaction acceptance. Design gaps and exact PR ownership are in the requirement-update section of `design-review.md` (R11–R16). R2–R10 remain open.

### Additional old/new oracles

| ID | Existing design/evidence boundary | Required new oracle |
| --- | --- | --- |
| O22 Every-dispatch policy | §8 has packing/phase triggers; §9 has a tool loop. | Every actual main dispatch has a recorded gate for its exact next input, including first/tool/role/resume. Count profile/version/provenance and full request overhead; lower target < soft trigger <= safe hard ceiling. Unknown capacity fails closed. Unchanged no-gain frontier is not retried in a loop; new compactable work is required. No midstream context replacement. |
| O23 Atomic adoption | Summary head CAS exists in design; live-context switch is unspecified. | Checkpoint body/parent/input fingerprint, exact coverage/source/group versions, policy/model/counter versions and before/after count are bound to an atomic expected-context CAS plus active pointer switch. One winner; no partial coverage advance or stale winner after message/tool/branch/source/cancel changes. Historical valid snapshots alone cannot authorize next dispatch. |
| O24 Legal units and raw results | Existing unit ends at a completed assistant answer. | Completed journal tool groups within an unfinished answer can compact; incomplete parallel groups cannot be split. Each call keeps exactly its matched terminal result/status. Oversized raw results are durably archived with source-safe bounded refs; archive failure cannot yield a successful dangling ref. Resource limits remain explicit. |
| O25 Bounded summarizer | Raw rebuild suggested; no chunk algorithm/limits accepted. | Summarizer uses a separate nonrecursive path, complete-unit chunking and bounded merge/call/token/time/resource budgets. Its input, each chunk and merge are checked. Critical facts/failures/pending state/conflicts retain attribution. Summary data has no system-instruction or evidence-grant authority. |
| O26 Same-execution continuation | Research binding is immutable per Attempt; new context chain pending. | Successful healthy compaction changes only context representation/version; same chat execution and run/step/Attempt continue without user action. Native roles/preconditions/evidence/settled tools and publication identities remain authoritative. At least two compactions are demonstrable within one live Research Attempt/task. |
| O27 Budget and outcome continuity | Native reservation and unknown-outcome rules exist. | Main and summary/chunk work are charged to their declared continuous parent allowances, deadline and call order. No reset or duplicate settlement; unknown usage stays reserved/accounted as specified. No completed side effect/publication is replayed because context compacted. No external exactly-once claim. |
| O28 Failure/no gain | Prior summary failure keeps old boundary. | Invalid/no-gain/no-prefix/over-target/over-hard candidates follow a finite decision table. Old committed context stays unchanged. Continue automatically with it only when authorized and under the hard ceiling; otherwise bounded retry or specific recoverable stop. No empty summary, truncation of mandatory content or spin at the same boundary. |
| O29 Cancel/source/crash fence | Existing R1 guard contract and native leases still apply. | Cancel/deletion/revocation wins before adoption or next dispatch; late summary cannot update a cancelled/invalid context. Crash before commit leaves old checkpoint; crash after commit recovers the committed one. Neither replays settled tools. Lost commit acknowledgement reconciles stable operation identity. Sent unknown calls are not blindly repeated; expired native Attempts are never revived. |
| O30 Trace/quality/UI | Prior tests and UI plan are not execution evidence. | Engineering evidence shows one user submission → growing tool history → committed compaction(s) → automatic final result, with continuous identities/counters. Independently labeled semantic cases detect omissions. Actual browser shows progress, no Continue requirement on success, meaningful hard failure and refresh/reconnect truth. Each evidence scope is reported independently. |

### Compaction-specific negative and positive acceptance cases

Each case includes expected inputs/frontiers and raw before/after artifacts. Scripted responses may prove orchestration only; do not use them to claim natural-language semantic quality.

| Case | Trigger/fault | Required discriminating observation |
| --- | --- | --- |
| CO01 One chat submission | Successive tool rounds cross soft threshold while assistant answer is unfinished. | Gate runs after each round, checkpoint commits and same execution automatically reaches final answer with no second user message. Trigger/target/counting provenance recorded. O22/O24/O26. |
| CO02 Repeated Research | Within one live Attempt, new complete tool history crosses threshold twice; later exercise role change and resume dispatch. | Two distinct committed context versions; same identity across each compaction, normal role identity preserved; no skipped gate, reset ledger or changed frozen evidence. O22/O26/O27. |
| CO03 Hysteresis/no gain | Hover below/at/above soft trigger; candidate unchanged or larger; invoke again with identical boundary, then append genuinely new complete work. | Correct threshold relation; bounded no-gain suppression; no repeated charge/spin on unchanged boundary; newly eligible work can trigger again. O22/O28. |
| CO04 Parallel incomplete | One provider turn issues A/B/C; A completes, B delayed, C fails; crash/reorder delivery. | No prefix takes A while dangling B/C; explicit terminal failures preserve group validity; exact call IDs/results neither missing nor duplicated. Sequential execution does not waive group semantics. O24/O29. |
| CO05 Huge result | Raw tool output exceeds transport/context cap; decisive value near tail; archive write fails in a separate variant. | Durable exact raw content + bounded versioned refs/continuation, including tail; archive failure yields bounded failure and no dangling successful result. No fake tool association or silent truncation. O24/O25. |
| CO06 Summary itself too large | Raw prefix exceeds summarizer capacity; many complete units; merge cannot fit; one indivisible unit too large. | Bounded chunks/merge, no recursive main gate, every call within capacity and cumulative limit; documented terminal outcome when reduction cannot fit. O25/O27/O28. |
| CO07 Failed/no-prefix/hard-limit | Invalid JSON/semantic rejection, no old complete interval, zero gain, post-compact still over hard cap, oversize required current request. | No adoption/coverage movement; original-safe case continues automatically; unsafe case finite stop/recovery, no empty summary or dropped mandatory input. O28. |
| CO08 Competing adoption | Two candidates from version V; new message/tool result arrives, branch switches; add cross-user/workspace forged IDs. | At most one matching-context CAS; stale candidate denied or rebuilt; exact tail/coverage policy; no other-branch facts or scope leakage. O23/O29. |
| CO09 Cancel/revoke/delete | Pause summary after generation, before adoption and after adoption before next send; cancel/remove membership/delete source. | Guard decides ordering; late result cannot advance cancelled/invalidated execution; next send rechecks committed checkpoint dependencies. No permission fallback or stale-summary dispatch. O29. |
| CO10 Crash boundaries | Kill during candidate generation, just before DB commit, after commit before acknowledgement and after checkpoint commit before next send; separate sent-but-unknown call. | Old versus new checkpoint selected by actual durable commit; no coverage holes/double coverage/duplicate side effects or publication. Reconcile key before retry; unknown remote calls remain unknown. Genuine native lease expiry/recovery separately identified, never called compaction-driven new Attempt. O23/O27/O29. |
| CO11 Meaning-negative control | Summary keeps valid schema/source IDs but drops “not”, condition, exact unit, failed-attempt warning or one unresolved conflict side; inject historical instructions. | Semantic evaluator flags failure despite structural pass; summary does not gain instruction/confirmation/evidence authority. Preserve source-versioned original for comparison. O25/O30. |
| CO12 Visible continuation | Normal browser task compacts; refresh/disconnect during compaction, then test bounded hard failure and recovery. | UI shows brief organizing state and resumes without Continue on successful compaction; refresh reflects server checkpoint/operation; explicit failure action when genuinely blocked. No phantom second task/message or misleading saved/complete indicator. O30. |

### Evidence and merge obligations

- **Engineering trace:** record call purpose and identity, execution/run/step/Attempt/role, group/frontier/context versions, compaction operation/parent/checkpoint, trigger/target/hard values, count source and before/after values, reservation/settlement/cumulative deltas, deadlines, failure/cancel/adoption and tool/publication identity. Raw transcript comparisons prove no repeated completed effects. Do not log sensitive body text.
- **Semantic quality:** original → checkpoint → final answer proposition/support comparison; quantified/conditional/negative facts, failure status, uncertainty/conflicts and native evidence links. Include deliberately wrong but structurally valid summaries. No paid evaluation authorized; real model quality stays blocked when not actually measured.
- **Real UI:** visible service-backed chat and Research entry, same-submission automatic progression, status, hard failure and refresh/reconnect. API traces, fixture rows or screenshots of a standalone component do not replace this.
- **Ownership:** #42 owns atomic primitives, with #43 co-design before schema freeze; #43 owns policy/checkpoint orchestration/bounded summarizer; #44 owns chat gate/tool groups/SSE; #45 owns repeated Research compactions/roles/recovery; #46 owns visible acceptance. Neutral provider foundation must precede its use by #43. Split or co-locate PRs under controller ownership so checkpoint/coverage/live-pointer adoption is one transaction and no caller bypasses the gate.

Status: authority and bounded oracle update **pass at documentation scope only**; current §12 design acceptance and all engineering/quality/UI execution **blocked**. Prior good work, existing review findings and the conditional P1a subset are retained. No product/test/service/branch or shared workbench edits; no private memory or paid model calls. Durable write-back is these owned review files.

## 12. Stable consolidated design re-review — 2026-09-28

Current disposition is recorded in [design-review.md](design-review.md), “Stable consolidated candidate”. Design SHA-256 `069DE6DA37D5C57FAF8C7CB7B1C77679B1A9F819D85483351E2BC61699C12C07`; effective spec v3 SHA-256 `6097FDB5BF494A5754D4DF3593774FECFE235ED47F40BDFAE604CB61257E6713`. These dispositions supersede earlier open counts, without removing or weakening O01–O30, R01–R21 or CO01–CO12.

- **R2–R3 and R5–R16: closed at design level only.** Current design §§6–10 now specify every-dispatch hysteresis, complete in-flight tool groups, bounded nonrecursive summary generation, atomic checkpoint/coverage/live-pointer CAS, same-Attempt repeated compactions and continuous native budgets/recovery; §§11/13 specify correlated real-UI and semantic acceptance. O22–O30/CO01–CO12 have satisfactory operative design coverage. Their execution remains **blocked/unrun**, not passed.
- **R4: one open P1, narrowed to proposition-bearing erasure fields.** Instructions' erased CHECK and reference-safe retention are repaired, but revision `conditions.subject/applicability` remains stored after the specified body/hash erasure, and the named trigger does not permit clearing it. Integrated design and #42 P1a approval remain **blocked** on that bounded correction. R1 stays closed design-only; no new P0 identified.
- A1 output audience is still unapproved; #40 PR47 merge/handoff is still held externally. P1a scope remains instruction-only and does not authorize a wrong private-task contract. Neutral package ownership is accepted in the design; actual `packages/memory-service` is absent and legacy Worker API imports remain, so no import/runtime pass is claimed.

### Bounded additional reverse case — ER01 (O09/O12/O18/O20; F09)

Create a synthetic explicit memory whose unique marker occurs **only** in `conditions.subject` or `conditions.applicability`, then produce multiple revisions and delete it. Required result after P1a synchronous delete commit: all owned revision semantic payloads, including conditions, are erased; content-free identity/support/idempotency metadata remains valid; GET/history cannot disclose the marker and same-key replay cannot restore it. PostgreSQL direct-row attempts must reject erased content/conditions retention, live rows without valid conditions and erased-to-live restoration. Preserve unrelated original chat/Research archives and another live memory's source. For later stages, enumerate content-bearing derived JSON/request/result copies separately from content-free audit fields before claiming cleanup complete. This case detects a successful `content=NULL` update that leaves the deleted proposition in an auxiliary field.

**Evidence scope:** governing-goal/re-review/oracle coverage **pass (static)**; integrated/P1a design **blocked on R4**; all Issue41 deterministic execution, real PostgreSQL migration/races, runtime recovery/security, real-model quality and visible browser acceptance **blocked/unrun**. Scope expansion into new sharing/raw archive deletion/evidence permissions **not applicable/excluded**. No paid evaluation or service changes. Full adjudication, bounded correction and stable inventory/proposal hashes are in the companion review; no broad oracle rewrite is needed.

Reviewer work for this request is complete; no required work continues in this lane. Write-back remains solely these owned review files, with no shared workbench/private-memory changes.
## 13. Final targeted R4 closure — 2026-09-28

Design SHA-256 `D0F38DCC2B34B4F1F8D9F55372EC79551D057A44AE3BF368784E14ACAF3EE01B`: the seven bounded replacements in §4.3 (field and CHECK), §5.3, §5.5, §12.1, F09/ER01 and the R4 resolution row were independently inspected. R4 is **closed at design level**: conditions are nullable only for erased revisions; synchronous delete clears conditions/content/hash on every revision; the monotonic trigger forbids other mutation/restoration; F09/ER01 specifies conditions-only marker, malformed direct-SQL and resurrection negatives. No correction-induced issue was found. The preceding R4-open disposition is superseded; all earlier oracles and execution requirements remain intact.

- **#42 P1a: design-eligible**, solely the six-table instruction-only/manual-command/DB-erasure subset defined in the companion review. No A1 audience contract is presumed.
- **Integrated design: conditionally accepted at design scope**, carrying forward the prior independent review; A1 remains unapproved and its audience branch is not authorized. No open P0/P1 design findings remain.
- **Product authorization: blocked.** Controller reports #40 HEAD `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`, six core CI green/independent ACCEPT, but three runtime checks blocked by unauthorized pinned MinIO server/mc pulls; main remains `8812fda`, no merge/handoff. No CI/runtime check was rerun here.
- **ER01 and all Issue41 T/M/R/Q/U execution: blocked/unrun.** Test specifications are not executed evidence. No paid model evaluation.

Final targeted check complete; no required reviewer work remains active. Only owned review files updated; no product/service/Git/profile/shared-workbench modifications. Durable write-back is this note and the companion final R4 disposition.