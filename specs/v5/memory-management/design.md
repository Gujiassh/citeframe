# Current implementation authority

Effective spec v4 §§13–14 governs shared-output exclusion and parallel worktrees. Private storage/management is supported; private recall into shared tasks and new audience/private-task schema are excluded. Prior review hashes are historical design evidence; this scope revision requires explicit consumer isolation tests.

# Issue41 memory management — revised implementation design

Status: **R1–R16 design review closed at its recorded scope; v4 authorizes isolated parallel implementation. P1a implementation acceptance and subsequent consumer reviews are recorded separately.**

Authority: repository `spec.md` v4 §§1–14 and the full external `C:/Users/baiao/Documents/Codex/2026-09-21/ai-ensemble-fork/outputs/Citeframe-记忆管理改造方案.md` v2, read 2026-09-28. The repository specification and current authorization govern long-term admission. Candidate wording remaining in the external proposal does not authorize inferred personal-memory persistence. Source baseline remains `8812fda4d69b7f0e654e749c357fa05b5e8da72f`; inspection observed Issue40 commit `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae` on `refactor/workspace-access-dependencies`. A later read-only verification observed HEAD `5903d60b7103d32d7d8a0c173691250407460b13`; this lane did not change Git state or re-audit that concurrent delta. PR47 remains unmerged by the current controller instruction, with a previously reported external image401 blocker. Exact merged handoff is required before dependent route integration; the approved isolated neutral lanes proceed from the fixed main baseline.

This document is the consolidated normative candidate; its sections contain the operative contracts. [code-inventory.md](code-inventory.md) records actual source behavior. [reviews/design-review.md](reviews/design-review.md) supplied R2–R16 and the O22–O30/CO01–CO12 oracle supplement; §15 maps corrections for re-review, without self-approving them.

## 1. Outcome and invariants

Deliver four layers: recent complete interactions, source-backed semantic task memory, eligible private long-term memory, and exact authorized original-source access. Ordinary chat and Research must automatically compact **before every main-model dispatch**, including tool continuations, role transitions and recovery, in the same running task without a new user message. Source fidelity, permissions, native workflow state, budgets and cancellation remain authoritative.

1. Long-term admission requires an attributable explicit remember/confirmation action or a verifiable scoped observation. Ambiguous inferred user attributes/intents are rejected before candidate/job/output/vector persistence. No long-term candidate state exists. Observations never become user confirmation through repetition, summaries or evaluation.
2. Unresolved Research facts/conflicts remain task memory. Model suggestions and hypotheses retain attribution. Source text is untrusted data and cannot authorize instructions or privileges.
3. Private visibility and applicability are separate. Initially use stable workspace/thread/run IDs; no free-text project identity, user-global search or sharing product.
4. Native messages, assets, notes, citations, evidence handles, task success/failure, conflict decisions and report publication keep their meanings. Compaction changes only the next model input representation.
5. Disable/delete/supersede of a consumed memory and invalidation of any source immediately fence dependent contexts. Another surviving source permits a new validated computation; old derived wording remains unavailable until then.
6. Compaction keeps run/step/attempt, completed tool state, publication state, cumulative budgets and cancellation. A valid checkpoint is committed atomically with its coverage/head; no empty or failed summary advances coverage.
7. Frozen Research evidence scope never expands from historical memory. A history reference is not a verified evidence handle. Current revocation/deletion overrides use of a previously frozen memory checkpoint.
8. Save receipts follow observed DB commit. Remote call uncertainty is durable and cannot be hidden by automatic resend. No claim of exactly-once external model invocation.
9. Engineering trace, semantic quality and visible browser acceptance are separate required evidence. No paid evaluation is authorized.

## 2. Architecture, ownership and minimal neutral boundary

```text
Web feature -> BFF -> API router -> citeframe_memory use cases
Worker / Research composition ----> citeframe_memory use cases
API composition / Worker composition -> citeframe_memory.adapters
citeframe_memory -> citeframe_contracts.memory + citeframe_persistence
shared adapters -> neutral DTOs + injected HTTP/counting/object-store ports
```

**One contract owner:** `packages/backend-contracts/src/citeframe_contracts/memory.py` owns all shared DTOs, exceptions and Protocols: `AccessPort`, `GenerationPort`, `EmbeddingPort`, `TokenCounter`, `ObjectStorePort`, `Clock`, and immutable `ModelConnectionSnapshot`. Do not create a parallel `memory-service/ports.py`. Standard-library contracts import neither application nor ORM. Neutral implementations may depend on these contracts and neutral persistence; neither imports API/Worker settings, services, routes, credentials loaders or metrics globals.

| Proposed path | Responsibility / first consumer |
|---|---|
| `packages/memory-service/src/citeframe_memory/{access,sources,commands,lifecycle}.py` | Owner-private commands and source eligibility; #42 P1a starts instruction-only |
| `packages/memory-service/src/citeframe_memory/{context,summaries,retrieval,tool_loop}.py` | Pre-dispatch packing, bounded summary calls, hybrid query and loop; add with actual consumers |
| `packages/memory-service/src/citeframe_memory/adapters/{responses,chat_completions,anthropic,counting}.py` | One shared implementation of necessary native protocols and counting primitives |
| `packages/backend-persistence/src/citeframe_persistence/models/{memory,memory_context}.py` | Single Base models; staged tables/constraints in §12 |
| `apps/api/src/ai_pdf_api/services/memory_composition.py` | Map existing workspace config/session/transport/object-store adapters to neutral inputs |
| `apps/api/src/ai_pdf_api/{schemas,routers}/memory.py` | Strict API DTO mapping and thin authenticated routes |
| `apps/worker/src/ai_pdf_worker/memory/{processor,composition}.py` | Receive ports from existing bootstrap; direct neutral imports only |
| `apps/worker/src/ai_pdf_worker/research/adapters/{generation,memory}.py` | Existing generation seam plus thin memory binding integration; no new Worker→API imports |
| `apps/web/src/lib/memory/{types,client,normalize,use-memory}.ts` | DTOs, request recovery and runtime state |
| `apps/web/src/components/memory/{memory-panel,memory-editor,memory-source-view}.tsx` | Real workspace management and source drill-down |

Both composition roots pass runtime endpoint/secret/model/timeout/fingerprint in `ModelConnectionSnapshot`, plus an HTTP transport and observation callbacks. Existing bootstrap can supply existing connection-resolution callbacks; adding imports of API provider implementation inside Worker is forbidden. Extract only primitives needed by both consumers and parity-test those before new behavior. No blanket legacy-service refactor, new service deployment, compatibility facade or duplicated provider implementation.

Shared adapters/counting must land before #43 executes any summary call, not after it in the final chat slice. Update API/Worker local dependency declarations, their lockfiles, deploy requirement/install layers and CI neutral import smoke with the new package when first introduced. Import tests run adapters/use cases with `ai_pdf_api` and `ai_pdf_worker` unavailable and assert both composition roots instantiate the same classes.

Issue40 owns nine routers and existing SSOT README/system-architecture. Coordinate overlap through controller after handoff. API routes reuse `require_workspace_member/owner` and preserve existing validation/authorization precedence. Neutral access is a mandatory injected authorizer with no permissive missing-resolver fallback. This phase owns only design.md and code-inventory.md.

## 3. Scope, audience and authority

### 3.1 Private records and access

All memory records have workspace and owner. Applicability is `workspace | thread | research_run`; P1a only permits workspace applicability. Every normal read/mutation/embedding/extraction/summary requires current actor membership, unarchived workspace, exact target ownership/audience and eligible sources. Workspace owner cannot read another user's private memory. No actor comes from model parameters. Legacy ChatMessage lacks author attribution; never infer it from thread creator/role. New messages register authenticated source actor atomically; legacy statements need a new explicit confirmation action to establish user confirmation.

`AccessContext={actorUserId,workspaceId,role,purpose,threadId?,branchLeafId?,runId?,stepId?,attemptId?,outputAudience,allowedHistoryScopes}` is server-owned. Purpose is management/chat/research_planning/research_task. `allowedHistoryScopes` is an intersection with the output audience and existing native ACL; it is not a privilege supplied by a tool. Current task context and private memories never flow into a wider-readable output.

### 3.2 Shared-output boundary (final scope)

Existing chat and Research outputs remain workspace-readable. No new native audience column, private thread/run mode, conversion or sharing product is implemented. Owner-private memory remains available only through authorized private management/storage operations; it is not automatically reused in shared chat or Research.

Every shared model-input path excludes private content: context assembly, search_memory/search_history/read_source, summaries/checkpoints, planning and all derived outputs. A requester's individual source access is insufficient; source readership must cover the output audience. Server-injected purpose and existing source visibility enforce this before provider dispatch and result adoption. Private management source reads are not model-tool permissions. With no currently authorized shared memory entries, shared search_memory returns no private hits. Lawful shared history/source retrieval remains supported within the authorized task/history envelope.

Automatic shared-task compaction uses only lawful shared task context; frozen Research evidence rules remain intact. Negative fixtures inject private markers owned by the caller and another member, then inspect prompt/tool/SSE/checkpoint/summary/planner/artifact/log outputs. No new private-mode activation or pending A1 gate exists.

### 3.3 Lifecycle maintenance after revocation

User-content work stops on membership loss/archive. Cleanup uses a distinct **server-created maintenance command**, not the former actor's read authority. Its capability is exactly `{commandId,workspaceId,kind:'invalidate'|'erase',targetIds,expectedDeletionOrSourceVersion,issuedAt}` persisted during the authorized mutation or a native source lifecycle transition. Initiator identity is audit data; no fallback to another user/owner.

Maintenance may suppress eligible rows, clear owned derived bytes, delete exactly registered derived object/index entries and settle its own command. It cannot read source bodies for generation, call models, search unrelated records, recompute memories, restore validity or change native archives. It remains claimable/retryable after requester removal/workspace archive. Commands are immutable in target/scope; retries CAS command version and recheck target tombstone/source invalidation. Recompute is a separate user-content action requiring current authorization and never runs under maintenance capability.

Existing users/workspaces FKs use RESTRICT for retained audit identities; no cascade from membership deletion. A hard user/account-erasure policy is outside this design; physical user removal is refused while audit references remain unless separately approved identity anonymization preserves integrity. Membership loss alone does not remove user rows or strand cleanup. P1a erasure is synchronous DB-only and needs no worker/outbox.

## 4. Persistence and dependency contracts

### 4.1 Types and conventions

`ID=varchar(36)` canonical UUID; `V=bigint >=1`; `TS=timestamptz UTC`; `SHA=char(64)` lowercase hexadecimal; `J=JSONB`. `?` means nullable; otherwise NOT NULL. JSON has strict tagged schema, unknown keys rejected. SQLite JSON/unit tests do not establish PostgreSQL integrity. Tables use ordinary FKs/UNIQUE/CHECK; named cross-row triggers are limited to the predicates enumerated below. No RLS or generic graph framework is introduced.

### 4.2 Instructions, source versions and eligible provenance

```text
memory_instructions:
 id ID PK; workspace_id ID FK workspaces; actor_user_id ID FK users;
 operation varchar(16); request_id ID; target_memory_id ID?;
 expected_version V?; content text?; content_sha256 SHA?;
 created_at TS; erased_at TS?;
 UNIQUE(workspace_id,actor_user_id,request_id)
```

Operation CHECK remember/correct/confirm/deactivate/delete. For remember/correct/confirm: either live `(erased_at IS NULL AND content length 1..4000 AND hash present)` or erased `(erased_at IS NOT NULL AND content IS NULL AND hash IS NULL)`. Deactivate/delete always have NULL content/hash; erased_at may record final cleanup. Erasure is irreversible; trigger `instruction_erasure_monotonic` rejects erased→live and mutation of actor/action/request identity. P1a supports remember/correct/deactivate/delete; confirm activates with its exact UI/source proposition contract later. Content-free action identity remains for CAS/replay audit.

```text
memory_sources:
 id ID PK; workspace_id ID FK; kind varchar(32); native_id ID;
 instruction_id ID? FK memory_instructions; source_version V;
 native_version J; content_sha256 SHA?; actor_user_id ID? FK users;
 audience varchar(16); owner_user_id ID? FK users;
 state varchar(16); created_at TS; invalidated_at TS?;
 UNIQUE(workspace_id,kind,native_id,source_version)
```

P1a CHECK kind='memory_instruction', instruction_id non-NULL and native_id=instruction_id, private audience/owner=actor. Later source activation expands kind with explicit resolvers: chat_message/content_unit/note/research_evidence/research_artifact/tool_result. State current/stale/deleted/unavailable; hash may be NULL only for erased/deleted source metadata. One current version via partial UNIQUE(workspace,kind,native_id) WHERE state=current. No full raw archive duplication. New native mutation and source invalidation commit together; exact-source readers also validate current native state.

| Kind | Exact native_version / contentKind | Bounds and authority |
|---|---|---|
| memory_instruction | instructionId, requestId / explicit_instruction | Exact user text, actor and action; erased body unreadable |
| chat_message | messageId,parentMessageId,role,status,contentSha256 / original_message | Completed original text; explicit registered actor or unknown; branch edits retain originals |
| content_unit | assetId,contentUnitId,representationId,processingGeneration,indexVersion,parserVersion,locatorId,locatorKind,textSha256 / normalized_content_unit | Current ready/nondeleting generation for new retrieval; original file via native route |
| note | noteId,updatedAt,bodySha256 / note_body | Current unarchived body; nonexistent old bytes return 410 |
| research_evidence | runId,executionSnapshotId,evidenceSnapshotId,evidenceHandleId,sourceFingerprintSha256 / evidence_excerpt | Existing internal capability/frozen source policy; no public memory endpoint bypass |
| research_artifact | runId,artifactId,schemaVersion,contentSha256 / artifact_text | Native visibility/type/retention; internal artifacts remain internal |
| tool_result | callId,groupId,resultSha256,protocolVersion / tool_result | Exact committed result with direct dependencies and original source leaves |

`SourceRef={sourceId,sourceVersion,contentSha256,span:null|{kind:'text',start,end}|{kind:'locator',locatorId}}`; Unicode code-point offsets, 0<=start<end<=exact text length. Hash pins the named contentKind. A Research excerpt is labeled evidence_excerpt; it is never represented as the whole original. Full normalized unit/message reads paginate exact ranges beyond 2000/4000-char snapshots, or return source_version_unavailable. No arbitrary URL/object key/path reads. Underlying deleting/deleted sources are unavailable through new memory paths even if native history retains excerpts.

### 4.3 Records, revisions, intent and validity

```text
memory_records:
 id ID PK; workspace_id ID FK; owner_user_id ID FK;
 scope_kind varchar(16); thread_id ID? FK; run_id ID? FK;
 visibility varchar(16) DEFAULT 'private'; current_version V;
 supersedes_id ID? FK memory_records; created_at TS;
 UNIQUE(workspace_id,id); UNIQUE(workspace_id,owner_user_id,id);
 UNIQUE(supersedes_id) WHERE supersedes_id IS NOT NULL

memory_revisions:
 workspace_id ID FK; memory_id ID; version V; revision_id ID UNIQUE;
 intent varchar(16); validity varchar(16); cause varchar(24);
 kind varchar(16); content text?; content_sha256 SHA?;
 confirmation varchar(24); confirmation_source_id ID FK memory_sources;
 conditions J?; pinned boolean; valid_until TS?;
 instruction_id ID? FK memory_instructions; created_at TS; erased_at TS?;
 PRIMARY KEY(memory_id,version); UNIQUE(workspace_id,revision_id);
 FK(workspace_id,memory_id)->memory_records(workspace_id,id)
```

Record composite FK `(id,current_version)->memory_revisions(memory_id,version)` is deferred and added after both tables. This is the only current head/version; do not add another mutable record status. P1a scope CHECK workspace with both IDs NULL; later thread/run scopes have exactly their native target, same workspace checked at service boundary. Visibility always private. Supersession requires same workspace/owner/scope, no self/cycle; one successor. Use composite FKs for owner/workspace joins, locked command checks for scope and acyclic transition.

Revision CHECK intent=`active|inactive|superseded|deleted`; validity=`valid|invalidated`; cause=`create|correct|deactivate|reactivate|invalidate|recompute|delete|support_added|expiry_changed`. Kind preference/constraint/fact/decision; confirmation explicit_remember/user_confirmed/sourced_observation. Observation requires fact and pinned=false. Conditions strict `{subject:string(1..256),applicability:string(1..2000),effectiveFrom:TS|null}`. Pinned only explicitly requested confirmed constraint/decision. One live/erased revision CHECK requires either (a) erased_at IS NULL, content length 1..4000, content_sha256 present and conditions non-NULL satisfying the strict conditions schema above, or (b) erased_at IS NOT NULL and conditions, content and content_sha256 ALL SQL NULL. Conditions is nullable only in the erased branch; an empty object is not valid conditions. State/provenance fields are immutable historical facts; the sole later revision mutation is irreversible byte erasure under the named maintenance command. Present readability also checks current dependencies/intent; historical revision state is never relabeled.

`defaultEligible = current.intent=active AND current.validity=valid AND not expired AND all direct/raw dependencies eligible AND current ACL`. API returns both intent and validity; display status is a projection with precedence deleted > superseded > inactive > invalidated > expired > active. Expiry is a read predicate, not a background action that loses intent.

**Single transition/CAS rule:** every command locks record, compares expected current_version, appends one revision, advances head atomically. Source invalidation appends validity=invalidated preserving current intent. Disable sets intent=inactive preserving validity. Correct creates a new identity and atomically appends intent=superseded to old record. Delete sets intent=deleted and suppresses all bodies immediately. Recompute may change content/support/validity only; it always copies latest intent and cannot run for deleted identity.

| Interleaving | Commit rule / result |
|---|---|
| invalidate → disable → recompute | Old recompute CAS fails; new computation uses latest inactive revision; result inactive+valid |
| inactive → invalidate → recompute | Intent remains inactive throughout; repaired validity cannot enable recall |
| superseded → invalidate → recompute | Intent remains superseded, successor unchanged; historical repair only when explicitly needed |
| delete races recompute | Delete wins suppression; stale recompute fails CAS; no recreation of identity |
| new correction races disable | One expected-version winner; other receives version_conflict and must explicitly reread |

Source invalidation is immediately effective through dependency checks even before fanout appends invalidated revisions. Computation must revalidate exact current revision/intent at adoption. No source-body invalidation is used to hide one private memory.

### 4.4 One typed consumer-use relation

`memory_uses` retains **direct consumed revisions/checkpoints/results** and supporting raw leaves. P1a installs only consumer_revision + source columns; later migration adds columns when their tables exist.

```text
id ID PK; workspace_id ID FK;
consumer_revision_id ID? FK memory_revisions(revision_id);
consumer_snapshot_id ID? FK task_memory_snapshots;
consumer_call_id ID? FK memory_calls; consumer_call_part varchar(8)?;
source_id ID? FK memory_sources;
used_revision_id ID? FK memory_revisions(revision_id);
used_snapshot_id ID? FK task_memory_snapshots;
used_tool_call_id ID? FK memory_calls;
observed_head_version V?; use_mode varchar(16);
atom_key varchar(128); support_group varchar(128); relation varchar(16);
```

CHECK exactly one consumer, exactly one dependency; consumer_call_part input/result iff consumer_call set; mode default/history/support; relation supports/contradicts/context/confirmation. Unique consumer+part+dependency+atom/group via partial indexes per actual type. Index each dependency FK for reverse lookup. Memory revisions consume original sources only; snapshots/call inputs/results consume sources and earlier revisions/snapshots/completed tool results. Source edges also contain flattened original-leaf support; direct edges must never be replaced by only raw leaves. Same-workspace constraints use composite unique/FKs on new rows; user/audience compatibility checked by mandatory authorizer under locks. No cross-workspace edges.

Direct revision use records the observed record head version and use_mode. Default context requires that exact revision still be current, active, valid and unexpired; historical access can show labeled superseded/inactive text only to an authorized explicit history request, and cannot reactivate it in default context. Deletion blocks every mode. Snapshot uses validate committed status plus all its dependencies. Tool-result uses validate complete group and live direct dependencies. Edges point to earlier committed snapshots/calls; service enforces bounded acyclic chains by recorded sequence/parent, not an open-ended user-authored graph.

Disable/delete/correct increments memory head; queued and in-flight consumers see mismatch at read, pre-dispatch and final CAS. Reverse fanout marks affected snapshot/result invalidated and schedules safe rebuild where permitted. A surviving raw source does not authorize reuse of the old summary wording. Rebuild each atom only from complete surviving support groups and exact eligible originals; invalidate the entire old consumer first. A disabled/superseded contribution must be omitted from default memory context, not restored by dropping its direct edge and rereading raw leaves. Independently requested original history may be represented only as labeled history under its own authorization and support. A new explicit history query may produce a new labeled result under historical mode; old default-context result is never silently relabeled.

Named deferred trigger `memory_revision_support_required` checks insert/head-advance/support-delete at commit: every non-erased revision has a confirmation/source support edge, and its declared confirmation_source is in that support set. P1a can enforce this exactly with instruction-only supports. No generic trigger claims to prove semantic truth or all polymorphic source permissions. Erasure retains support identities/edges; physical graph cleanup is reference-safe (§5).

## 5. Admission, commands, cleanup and retention

### 5.1 Per-item confirmation and source fidelity

An explicit remember request saves the actual attributable proposition without a mechanical second confirmation. The source action, exact proposition/span, actor and scope must be unambiguous. For explicit confirmation, the action references the displayed proposition ID/hash or an exact quoted proposition; “yes” with several possible referents is insufficient. Legacy unknown-author messages, assistant proposals and tool observations cannot confer user confirmation.

A rendering may retain explicit provenance only if its per-item source mapping preserves subject, modality, time, conditions, quantifiers, values/units and negation, with no additional claim. Prefer exact text/extractive spans; trivial whitespace/format normalization is allowed. A materially changed proposition requires a new attributable user action. Corpus evaluation measures extraction quality and never authorizes this item's confirmation. Ambiguous extracts are rejected in memory before eligible jobs/results/indexes are persisted. Rejected body/provider output is not written to diagnostics. Observations remain sourced_observation across merging, correction and summarization unless a separate user action creates a new explicitly confirmed proposition.

Verifiable observations require original available source, exact scope/conditions/time and source support. Unresolved Research claims/conflicts stay task-local. Credentials/private keys/session tokens and unsupported sensitive content are rejected before indexing; logs contain rejection codes only. Long-term extraction triggers are explicit_remember/explicit_confirmation/verified_observation, with source IDs and policy, never an archive-wide personal-inference scan.

Deduplication is exact normalized proposition + conditions + kind + confirmation class + owner/scope/validity; no semantic similarity or newest timestamp decides equivalence. Add support with CAS and independent source validation. Explicit correction creates successor; unresolved contradiction remains task memory with both sources. Saved receipts follow committed operation state even if indexing is pending.

### 5.2 Transaction and lock protocol

For normal memory commands: existing workspace row → actor membership row → native/source rows ordered by kind/ID → memory record heads ordered by ID → consumer head → operation/call rows. API supplies authenticated actor; no fallback authorizer. P1a has only workspace/member/instruction/record/operation locks. Research retains native Run→Step→Attempt→Ledger order after workspace/member guard; it then acquires source/record/context locks. Source invalidation does not synchronously acquire Research locks in reverse order: it changes source state under source guard, with eligibility denial effective immediately, and fanout later locks native roots in native order.

Readers take shared source/member/audience/head guards through bounded serialization/enqueue or dispatch authorization. Invalidators/revokers take conflicting write guards. Final adoption retains the same authorization/source guards through CAS and commit. No lock spans remote IO or network backpressure. Already-enqueued bytes or dispatched provider input cannot be recalled; subsequent reads/chunks/dispatches/commit must pass the updated guards. Missing membership fails closed. Native membership removal/workspace archive must follow this guard protocol for enabled memory paths.

Create inserts instruction/source, record+first revision/supports and idempotent result in one transaction. Correct locks predecessor, creates successor and new instruction/supports, marks predecessor superseded atomically. Source change marks registry invalid and schedules bounded fanout in the same native mutation transaction. Erase commits tombstone/suppression before physical asynchronous work. Native rows/content remain unchanged by memory cleanup.

### 5.3 Idempotency and instruction-only P1a erasure

```text
memory_operations:
 id ID PK; workspace_id ID FK; actor_user_id ID FK;
 request_id ID; method varchar(8); path varchar(512); key varchar(128);
 request_sha256 SHA; state varchar(16); resource_id ID?;
 result_version V?; http_status int?; created_at TS; settled_at TS?;
 UNIQUE(workspace_id,actor_user_id,request_id);
 UNIQUE(workspace_id,actor_user_id,method,path,key)
```

State in_progress/committed/failed. Key ASCII 8..128; request hash covers validated canonical body/method/path, expected version and source refs. Same key/requestId with different body is 409 idempotency_conflict; simultaneous same request observes one mutation. No stored response body: replay reauthorizes and constructs available resource/tombstone DTO. Committed create whose body was later erased returns erased metadata, never original body. Unknown DB acknowledgement queries the unique operation identity on a new connection; it is not assumed rolled back. In-progress/uncertain operations cannot expire by age.

P1a delete synchronously appends deleted revision, marks solely dependent instruction/source bodies erased/deleted, sets conditions/content/content_sha256 ALL NULL and erased_at non-NULL on ALL revisions of that record, including historical and newly appended deleted revisions, and records suppression/operation metadata in the same DB transaction. Identity/version/intent/provenance, support/FKs, CAS and idempotency metadata remain intact. No external object/index exists, so no cleanup job is required. Historical provenance/state IDs remain; shared source identity is not erased while another live memory legitimately depends on it. Default P1a uses one instruction per explicit operation, avoiding hidden shared ownership. Tombstoned record/operation/source identities suppress duplicate extraction/replay; a new explicit instruction/requestId creates a fresh identity. Mandatory-support links are retained during byte erasure.

### 5.4 Later asynchronous lifecycle work

Add `memory_jobs` only when a real model/index/object consumer needs it: `id,workspace_id,initiator_user_id,authority_kind,kind,target_manifest J,dedupe_key SHA UNIQUE,state,state_version,attempt,max_attempts,lease_token_hash?,lease_expires_at?,created_at,settled_at?,error_code?`. IDs/FKs use §4.1; state queued/running/succeeded/failed/cancelled/outcome_unknown; authority user_content/lifecycle. CHECK lifecycle permits only invalidate/erase; user_content permits extract/index/recompute (foreground compaction uses native context execution, not this generic job queue). Strict manifest contains exact typed target IDs/versions and original source refs, max128 KiB/2048 refs; no unvalidated extracted text or client object keys.

Lifecycle claim checks durable server command and exact resource ownership even after initiator revocation. User-content claim/adoption reauthorizes initiator and dependencies. Lease 60 seconds/heartbeat15, max3 attempts defaults; stale lease cannot adopt. Only proven-unsent calls and idempotent maintenance auto-retry; sent unknown model outcome sets outcome_unknown. Cleanup enumerates only owned derived object keys from metadata; never arbitrary native archive prefixes. Failed cleanup remains suppressed and retryable.

### 5.5 Reference-safe cleanup and TTL

1. Commit logical suppression/version fence. No search/source/read/replay may reveal deleted content.
2. Invalidate direct and transitive consumers. Stop new adoption, keep necessary identity/ledger metadata.
3. Erase owned revision conditions/content/content_sha256 together and instruction content/hash; delete eligible vector/text/result objects. Later consumers must enumerate content-bearing derived JSON/request/result copies under this same erasure policy before declaring cleanup complete; free-text semantic payload is not content-free audit metadata. Referenced tool results required for a valid checkpoint follow source lifetime; no compaction-driven archive deletion.
4. Retain content-free source/support/action/tombstone IDs while referenced by revisions, coverage, snapshots, frozen bindings, operations, suppressions or unsettled calls. Do not delete support links to satisfy a TTL.
5. Only when an entire target is terminal, no recovery/frozen/live consumer refers to it and retention permits physical removal: remove target's outgoing uses/coverage, target payload metadata, then now-unreferenced source registry rows; erase exclusively owned instruction identity last if unreferenced. Deferred support trigger still passes because referencing revision is removed in the same transaction. All FKs RESTRICT by default; no cascade to native archives. Cycles in record/current revision are broken only in explicit guarded purge of the whole unreferenced record, not routine erase.

Proposed config: unreferenced settled intermediate result objects24h; settled operation/call diagnostic metadata30d; retired index cleanup target24h. Source tombstone30d begins only after the last reference and replay-suppression need ends. Unknown outcomes, unsettled reservations, uncertain commits and required idempotency/suppression metadata have **no age-only expiry**. Explicit reconciliation or safe closed disposition preserves content-free deduplication/accounting before a cleanup clock starts. These are controller-owned application cleanup defaults; no backup/provider-retention or raw archive deletion promise. Public delete response distinguishes application retrieval suppression and cleanup completion/failure.

## 6. Context execution, snapshots, call journals and index storage

These structures are added with their first consumers in §12, never prebuilt in P1a.

### 6.1 Native context owners and snapshots

Chat mode2 requires `chat_memory_executions`: `id ID PK,workspace_id FK,actor_user_id FK,thread_id FK,user_message_id FK,assistant_message_id FK UNIQUE,request_id ID,request_sha256 SHA,retry_of_id ID? FK self,attempt_number int,state varchar(24),version V,context_version bigint>=0,checkpoint_id ID? FK task_memory_snapshots,anchor_leaf_id ID?,policy J,deadline_at TS,cancel_requested_at TS?,error_code?,created_at,finished_at?`. UNIQUE(workspace,actor,request_id); UNIQUE(retry_of_id) WHERE retry_of_id non-NULL prevents concurrent duplicate child retries. State prepared/running/waiting_context/succeeded/failed/cancel_requested/cancelled/outcome_unknown. Version is lifecycle CAS; context_version is model-input/coverage CAS. Native user/assistant rows retain current status vocabulary; execution supplies richer recovery state. Mode2 request replay never creates duplicate messages.

Research reuses `ResearchStepAttempt` and native state/lease: add `memory_context_version bigint NOT NULL DEFAULT 0 CHECK>=0` and nullable `memory_checkpoint_id FK task_memory_snapshots`. Task-global/branch scope remains native run/step/branch_key. Do not add new chat branch tables: native parent ancestry plus immutable source-prefix leaf manifest establishes coverage and reuse. All append/branch/adopt operations lock thread; mode2 rejects adoption if its captured active leaf/context revision no longer matches. Failed assistant ancestors remain explicit failed units, not confirmed facts.

```text
task_memory_snapshots:
 id ID PK; workspace_id ID FK; owner_user_id ID? FK; audience varchar(16);
 thread_id ID? FK; run_id ID? FK; step_id ID? FK; attempt_id ID? FK;
 branch_key varchar(128)?; anchor_leaf_id ID? FK chat_messages;
 parent_snapshot_id ID? FK self; version V; context_version bigint>=0;
 status varchar(16); summary J?; schema_version varchar(32);
 policy_snapshot J; provider_fingerprint SHA; counter_version varchar(64);
 input_sha256 SHA; manifest_sha256 SHA; operation_key SHA UNIQUE;
 before_tokens bigint; after_tokens bigint; count_source varchar(16);
 generation_call_id ID? FK memory_calls; created_at TS; invalidated_at TS?;
 erased_at TS?

task_memory_coverage:
 snapshot_id ID FK; ordinal int>=0; unit_key varchar(160);
 source_id ID? FK; tool_group_id ID? FK memory_calls;
 source_version V?; parent_message_id ID?;
 PRIMARY KEY(snapshot_id,ordinal); UNIQUE(snapshot_id,unit_key)
```

Snapshot CHECK: chat has thread/anchor, no run/step/attempt; Research has run/step/attempt and optional native branch_key, no thread. Status committed/invalidated/erased; committed summary non-NULL, erased summary NULL with erased_at; counts>=0; count_source exact/estimated. Version is immutable checkpoint chain version; `(native context owner, context_version, operation_key)` is the adoption identity, not a separate task-head table. Coverage is exact ordered complete-unit manifest; source xor tool_group, source_version required for source. Run/step/attempt identity checked against native composite relations and locked chain. The native owner pointer plus CAS is the only active checkpoint authority; immutable snapshots may be reused only after ancestry/dependency proof.

Summary strict schema `task-memory-v2` includes `goals,confirmedConstraints,confirmedDecisions,facts,completedWork,failedAttempts,conflicts,unresolved,nextSteps,progress`. Atom `{key,text,attribution:'user_explicit'|'sourced_observation'|'model_proposal',sourceRefs,conditions[],quantities:[{value,unit,qualifier}],negated}`. Each important atom has original support; confirmed arrays require attributable action. CompletedWork/failedAttempts include exact native tool/step IDs/outcomes with source refs; native status is supplied by code. Progress `{stepId,stateVersion,status,artifactIds}` is code-owned. Conflict `{key,sideA,sideB,resolution,decisionSource}` preserves both original sides. Research facts add `{executionSnapshotId,claimId,evidenceHandleIds,evidenceSnapshotIds,verificationStatus,conflictStatus}` from native ledgers. Arrays<=128, atom text<=2000, serialized summary<=128KiB; these bounds cannot justify omission of mandatory facts—stop if safe representation does not fit.

### 6.2 Immutable base and per-call manifests

`research_memory_bindings` is an **Attempt base context**, not the evolving input: `id,workspace_id,run_id,step_id,attempt_id UNIQUE,execution_snapshot_id?,planning_revision_id?,base_snapshot_id?,base_manifest J,workflow_version_id,policy J,manifest_sha256,created_at`. Exactly one execution/planning revision; base immutable; each per-call manifest references this binding plus newly discovered tools/sources. A base dependency no longer eligible blocks its use; it does not silently bind latest memory. No special duplicate binding-source table: use §4.4 relations attached to the actual snapshots/call inputs, with base_manifest listing exact initial dependencies.

```text
memory_calls:
 id ID PK; workspace_id ID FK; actor_user_id ID FK;
 chat_execution_id ID? FK; research_attempt_id ID? FK; job_id ID? FK;
 base_binding_id ID? FK; purpose varchar(24); logical_key varchar(160);
 ordinal int>=0; parent_call_id ID? FK self; native_provider_call_id ID? FK;
 native_tool_call_id ID? FK; research_budget_ledger_id ID? FK;
 provider_tool_call_id varchar(255)?;
 state varchar(24); context_version bigint>=0; checkpoint_id ID? FK;
 input_manifest J; request_object_key varchar(1024)?; request_sha256 SHA;
 result_object_key varchar(1024)?; result_sha256 SHA?; result_state varchar(16);
 result_manifest J?; result_tokens bigint? CHECK>=0;
 policy_fingerprint SHA; reserved_input bigint; reserved_output bigint;
 actual_input bigint?; actual_output bigint?; usage_source varchar(16);
 cost_microunits bigint?; reservation_state varchar(16);
 no_progress_boundary_sha256 SHA?; created_at TS; sent_at TS?; settled_at TS?;
 UNIQUE(owner,logical_key) via partial unique indexes on each owner column
```

Exactly one chat_execution/research_attempt/job; purpose main/compact_chunk/compact_merge/extract/embed/search_memory/search_history/read_source/tool_group. State reserved/sent/succeeded/failed/cancelled/outcome_unknown; result_state absent/valid/invalidated/erased; reservation_state reserved/settled. Nullable usage means unknown. Provider tool ID is a native string preserved exactly; server IDs remain UUIDs. A group row purpose=tool_group contains exact provider turn ID, ordered call ID set and member result refs/status in its result manifest; each member uses parent_call_id. Group completion is all members terminal with protocol-valid result pairing. No model dispatch consumes a partial parallel group.

Strict input_manifest: `{schemaVersion:1,owner:{...},baseBindingId:null|ID,contextVersion,checkpointId:null|ID,unitManifest:[{unitKey,kind,sourceRefs,callIds}],directUses:[{kind:'memory_revision'|'task_snapshot'|'tool_result',id,version?,useMode}],nativeState:{runVersion?,stepVersion?,attemptId?,leaseGeneration?,activeLeafId?,cancelVersion},profileFingerprint,counter:{id,version,mode},policyFingerprint,inputTokens,outputReserve}`. Max2048 units/128KiB manifest, sorted canonical hash; text bodies stored only in authorized source/result/request objects. Each direct use also becomes memory_uses input edge. The actual sent payload is hash-addressed in the authorized request object for deterministic recovery; do not persist unvalidated extraction responses. Secret headers/endpoints are excluded.

Next input union = eligible base + latest committed checkpoint + uncovered source units + complete results of already committed tool groups selected for this call. Record exclusions/summarized intervals via coverage; never silently replace a source version. Persist immutable per-call manifest/hash **after final compaction and before dispatch**, under native context/source guards. This makes subsequent discovered sources and role inputs auditable. A changed source invalidates adoption/dispatch even if a base snapshot was valid.

### 6.3 One budget owner, deterministic cumulative fold

Chat execution policy is immutable; resolve retry_of ancestry to its root and lock that root before admission or settlement, then the current execution row. Fold reservations/usage across every descendant under the root; child creation takes the same root guard. A bounded ancestry walk (max16 attempts; further retry returns retry_limit) prevents unbounded recovery chains. The root deadline/policy remains authoritative, so concurrent retry cannot race or reset allowance. Research uses existing plan/execution `ResearchBudgetLedger` and its state_version under native lock order. New frozen plan/execution field `memory_policy_json J?` records cumulative protocol/summary limits; NULL means legacy disabled. Add `planning_max_tool_calls integer DEFAULT 0 CHECK>=0`; old revisions keep zero. No separate mutable Research protocol budget table or binding-local in-memory counters.

For enabled runs, remaining allowance is a deterministic locked fold of complete memory_calls linked to that native ledger: reserved/sent/unknown calls charge reservations; settled calls charge validated actual or conservative estimated usage; main, compact and tool purposes all count. Research provider usage/reservations remain authoritative native rows joined by unique native_provider_call_id; sidecar does not bill again. User-content job calls have their own bounded policy in job manifest. Keep cumulative input/output/tool-result/summary-call counters as fold results, not a competing mutable authority. Unknown usage never refunds reservations automatically.

Native reservations and sidecar row/manifest insert commit in one transaction. Execution tool calls reuse ResearchToolCall; planner read tools store reservation_state and research_budget_ledger_id in their sidecar, atomically reserve/settle that ledger once. No separate planner reservation table. Reclaim locks native chain, settles only still-reserved rows, increments native ledger version, and leaves sent provider calls unknown. A sidecar cannot be settled twice or reset across compaction/role changes. Fold is run/plan ledger scoped across Attempts, so an explicit retry cannot reset cumulative allowance.

### 6.4 Separate hybrid index

`memory_index_entries(id,workspace_id,owner_user_id?,audience,source_id?,memory_revision_id?,chunk_ordinal,text_content,text_sha256,index_generation,embedding_space,provider,model,model_version,dimensions,config_fingerprint,embedding vector(1024)?,state,created_at)`: XOR source/revision, ordinal>=0,generation>=1,space memory_text/history_text,state pending/ready/retired,dimensions=1024,ready requires vector. FK and UNIQUE(target,chunk,generation), current-scope B-tree, GIN simple FTS, GiST trigram, cosine HNSW on ready rows. No fake ContentUnit or Asset. Dimension change needs reviewed migration; no padding.

`memory_index_manifests(id,workspace_id,owner_user_id?,audience,source_kind,generation,profile_fingerprint,source_set J,source_set_sha256,state,created_at,activated_at?)`: source_set strict exact eligible SourceRef/revision list, bounded batches with one manifest per owner/workspace/kind; state building/active/retired/failed; one active generation per scope. Activate only when every manifest member has matching ready chunks and is still eligible. For larger corpora paginate manifests into typed membership rows when measured size requires it, not as P1a scaffolding. All queries rejoin current heads/dependencies; old/missing profile fingerprints rejected. Matching tuple space/provider/model/version/dimensions/fingerprint/generation is mandatory.

## 7. Executable API and tool contracts

### 7.1 Memory management

API prefix `/v1/workspaces/{workspaceId}`, BFF `/api/workspaces/{workspaceId}`. Reuse trusted session/internal token and Issue40 member/owner dependencies. All mutation requests have `requestId:ID`, Idempotency-Key and, for existing records, expectedVersion>=1. Identity/visibility/confirmation cannot be supplied by client. New routes reject unknown fields. Existing endpoints retain their existing error shapes/precedence.

New error `{detail:{code,message,retryable,requestId,currentVersion?}}`; only authorized owners see version metadata. 401 auth;404 missing/inaccessible;409 version/idempotency/operation_in_progress/source_context_conflict;410 erased/source_version_unavailable;422 ineligible/sensitive/invalid_scope/invalid_source_ref;429 bounded budget;503 index_not_ready/transient unavailable. No raw provider secrets/errors. Status/code details remain stable across API/BFF.

| Route | Request | Response |
|---|---|---|
| GET `/memories` | status/scope filters, limit1..100 default30, signed cursor | `{items:MemoryDto[],nextCursor}`; own only |
| GET `/memories/{id}` and `/revisions` | history limit/cursor | current or immutable revision DTOs with present availability |
| POST `/memories` | requestId,kind,content,conditions,scope,pinned=false,validUntil=null,sourceRefs=[] |201 `{memory,operationId,indexState:'not_enabled'|'pending'|'ready'}` |
| POST `/memories/{id}/corrections` | requestId,expectedVersion,content,kind,conditions,validUntil,pinned |201 successor + supersededMemoryId/operationId |
| PATCH `/memories/{id}` | requestId,expectedVersion, intent?:active/inactive,pinned?,validUntil? |200 current + operationId; cannot rewrite content/scope |
| DELETE `/memories/{id}` | requestId,expectedVersion |200 synchronous P1a erase or202 async `{id,intent:'deleted',version,operationId,cleanupState}` |
| GET `/memories/requests/{requestId}` | actor-bound request identity |200 accepted/state/operation/resource/version metadata,404 unknown; no body replay |
| GET `/memories/operations/{id}` | none | operation/cleanup state, safe error and current resource metadata |
| POST `/memories/{id}/cleanup-retry` | requestId,expectedVersion |202 only already-issued maintenance command; no new target set |
| POST `/memories/search`, `/history/search`, `/sources/read` | same strict tool DTOs below | authorized result envelopes |

`MemoryDto={id,workspaceId,ownerUserId,visibility:'private',scope:{kind,threadId:null|ID,runId:null|ID},version,revisionId,intent,validity,displayStatus,kind,confirmation,conditions,pinned,validUntil,supersedesId,createdAt,updatedAt,contentAvailable:true,content,sourceRefs}`. Unavailable body is a discriminated `{id,version,intent,validity,displayStatus,contentAvailable:false,reason}`; no empty-string stand-in. Deleted GET returns410 to authorized owner,404 otherwise; operation polling remains content-free. Historical state fields stay frozen; source/ACL checks may remove current readability.

P1a exposes only neutral commands/tests, not mounted routes/UI; this table defines eventual consumer contract. Path order reserves requests/operations/search/history/sources before typed UUID record routes. A timeout before receiving operationId polls by requestId or replays same body/key; it never creates a new requestId automatically.

### 7.2 Discriminated chat requests and durable recovery

Keep current mode1 body/schema and errors: no protocolVersion or protocolVersion=1 means the existing `{threadId,question,assetScope:{mode:'all_ready'}|{mode:'selected',assetIds:[one or more unique IDs]},selectionText?,evidenceTargets?,parentMessageId?,editMessageId?}`. Existing request parser behavior, 12000-character question/selection limits and native asset citation schema stay unchanged. In particular no-ready/no-match behavior remains in mode1. All model dispatches still pass the context safety gate after ordinary preparation.

Mode2 strict DTO:

```typescript
type ChatV2 = {
  protocolVersion:2; requestId:UUID; memoryMode:"enabled";
  threadId:UUID; question:string; // 1..12000, never silently truncated
  assetScope:{mode:"none"}|{mode:"all_ready"}|{mode:"selected";assetIds:UUID[]};
  historyScope:"current_branch"|"workspace_history";
  parentMessageId?:UUID|null; editMessageId?:UUID;
  selectionText?:string; evidenceTargets?:EvidenceTarget[];
};
```

Selected still requires >=1 unique ID. None requires no evidenceTargets/selectionText; it intentionally enables memory/history-only preparation with no embedding of asset query and no fake asset. All_ready/selected retain current readiness/access validation. Mode2 can continue with history when scoped asset retrieval returns no match; empty native citations accurately report that no asset evidence supports the answer. Private recall is excluded from this shared output mode. Parent/edit mutual semantics retain native branch edit rules. Missing historyScope is validation error for mode2: UI explicitly establishes the envelope, default selector current_branch, and offers workspace_history for proactive cross-conversation lookup without needing a known thread ID. Model cannot widen it.

`POST /chat/stream` mode2 requires Idempotency-Key, atomically registers request, user message, pending assistant and chat execution before meta. Execution is durable and processed under a renewable lease (fields lease_token_hash?,lease_expires_at?,worker_id? on execution; no extra queue table). SSE subscription loss does not cancel mode2 business work; explicit cancel does. BFF request abort ends subscription, not accepted execution. The existing mode1 disconnect behavior remains; an internal chat_memory_executions context owner is required for its gate/checkpoint (server-generated request identity, no client replay API guarantee). Its disconnect cancellation follows mode1 semantics, and every actual mode1 main send passes the same gate without exposing new request semantics.

`GET /chat/requests/{requestId}` returns `{requestId,accepted:true,executionId,userMessageId,assistantMessageId,version,contextVersion,state,checkpointId,phase,canResume,error}` to its actor;404 unknown after current authorization. If acceptance response/meta is lost, poll by requestId; unknown allows exact same-key POST replay. Reused identity with differing hash409. Same accepted POST attaches to existing execution/status stream and never dispatches again. `GET /chat/executions/{id}/events` subscribes to current authorized snapshot + future events; no claim of replaying missing token deltas. Refresh loads committed messages plus execution state; unfinished answer is provisional.

`POST /chat/executions/{id}/cancel {requestId,expectedVersion}` compares execution lifecycle version under lock; cancel success prevents dispatch/checkpoint/adoption, committed success returns succeeded. `POST .../resume {requestId,expectedVersion}` resumes waiting_context only after changed actionable condition/explicit safe retry, rechecks sources/profile/lease and remaining original budgets, keeps execution/message identity, does not rerun completed tools. Successful automatic compaction needs neither endpoint nor new user input.

`POST .../retry {requestId,expectedVersion}` is explicit retry of failed/outcome_unknown only: create a **new execution identity** with retry_of_id, incremented attempt_number and a new pending assistant sibling under the same original user message; no second user message. Unique retry_of and operation key prevent concurrent duplicate retries. A subsequent retry targets that child. Root execution policy/deadline/cumulative allowance is retained across descendants; retry cannot clear spent/unknown usage. Proven completed tool results may be referenced after eligibility checks; an unknown provider operation is not implicitly replayed. Warn about possible duplicated provider cost; a retry request authorizes that new dispatch. If unchanged source/budget conditions still block, return409/429, not another empty assistant.

### 7.3 History tools and original-source metadata

`search_memory {query:string(1..4000),kinds?:Kind[],scopeKinds?:Scope[],includeHistory?:boolean=false,limit?:int1..20=6,cursor?}`. Default current active eligible revisions; historical question requires includeHistory and returns labeled state/successor refs. `search_history`:

```typescript
type HistoryQuery = {
  query:string;
  scope:{kind:"current_branch"}|{kind:"workspace_history"}|
        {kind:"thread";threadId:UUID;leafId?:UUID};
  sourceKinds?:("chat_message"|"note"|"content_unit"|"research_artifact")[];
  from?:ISO8601;to?:ISO8601;limit?:number;cursor?:string;
};
```

Scope is checked against server allowedHistoryScopes from task creation. Workspace_history searches eligible authorized sources in this workspace, including unknown thread locations, never any private records, including those owned by the requesting actor; thread/leaf narrows within envelope. Current_branch requires task thread/leaf from AccessContext; Research instead uses its own task/allowed planning history envelope. A Research planning query may choose workspace_history only within its frozen permitted planning audience; report evidence still uses native evidence tools. No workspace/user/object-path tool parameters.

`read_source {sourceRef,before?:int0..2000,after?:int0..2000,cursor?}` reads exact text/locator range, max2000 returned tokens by default with continuation. Context cannot cross source/version boundaries. Public read rejects internal evidence/checkpoints; native evidence port handles them with unchanged permission. Historical instructions remain untrusted data.

Results `{items,nextCursor,truncated,retrieval:{mode:'hybrid',indexGeneration,policyVersion}}`; direct read `{sourceRef,content,contentKind,occurredAt,sourceState,provenance,branchRelation,truncated,nextCursor}`. Provenance is `{role:'user'|'assistant'|'tool'|'document',actorUserId:UUID|null,actorAttribution:'authenticated'|'unknown'|'not_applicable',threadId:null|UUID,runId:null|UUID,parentMessageId:null|UUID,confirmation:null|Confirmation}` subject to existing audience; no guessed author. Hits carry sourceRef/excerpt/contentKind/time/provenance/branchRelation; memory hits also identity/version/intent/validity/confirmation/supersession. BranchRelation current_ancestor/other_branch/other_task labels adoption limits. Signed cursors bind actor/scope/filter/profile/source generation with15-minute expiry and reauthorize on use.

## 8. Automatic in-loop compaction and atomic checkpoints (#43)

### 8.1 Mandatory pre-dispatch gate

`prepare_main_dispatch(owner,proposed_input,expected_context_version)` is the sole entry before every main-model call: initial chat, each tool continuation, every Research role including planner/verifier/critic/synthesizer, adaptive/investigation rounds, and resumed dispatch. It validates current source/direct-use permissions, builds complete units, counts the exact final protocol payload and either supplies a committed context/checkpoint or a bounded error. It never replaces a request already streaming. Orchestration continues automatically with the returned input; compaction does not require a user turn.

Capability snapshot contains contextWindowTokens, outputReserve, protocol/tool overhead, safetyMargin, per-call ceiling, counterId/version/mode and profile fingerprint. Hard input H is the minimum of true model input availability and existing per-call input ceiling; a frozen Research input ceiling is **not** the model context capacity. Unknown model/multimodal accounting returns context_capacity_unknown; no guessed capacity. Count image cost, all tool definitions/call/result framing and protocol delimiters; estimates are labeled and conservative.

Policy strict fields: `softRatio,targetRatio,minNewCompressibleTokens,minGainTokens,maxCompactionEpisodes,maxChunkCalls,maxMergeCalls,maxCompactionWallMs,maxSummaryInputTokensTotal,maxSummaryOutputTokensTotal,maxMainCalls,maxToolCalls,maxInputTokensTotal,maxOutputTokensTotal,deadlineAt,counterVersion`. Require 0<targetRatio<softRatio<1. Prototype defaults soft0.80,target0.60,minNew256,minGain128; tune by measured fixtures/controller review. Hard limit is enforced independently. Summary calls count toward cumulative allowances; reserve enough headroom for the next main answer before starting a compaction episode.

Pack mandatory system/current request/explicit constraints/native pending state first, latest whole units next, valid snapshot and applicable eligible memories, then bounded retrieval fragments. Mandatory material that cannot fit produces context_limit_exceeded; never silently slice it. Soft share defaults may guide selection but cannot override semantics or be called quality evidence.

### 8.2 Units, parallel calls and oversized originals

Chat source history uses exact parent ancestry and explicit completed/failed unit dispositions. A tool group is the provider assistant call batch plus **all** matching terminal results in declared order, including failed/cancelled results. If any parallel member is pending/unknown, the group cannot be compressed or sent as a partial continuation. Initial implementation executes tools sequentially, but protocol fixtures and grouping must support multiple calls returned together. Unknown non-idempotent native tool outcomes preserve existing stop/recovery policy.

For a result too large for inline context, persist its complete original result object with call/group ID, hash, byte length, source dependencies and audience **before** marking tool complete. Use streaming object upload with proposed caps 16 MiB/result and 64 MiB/execution, admitted under the root/native ledger guard including pending uploads; temp uploads count against the same cap and are cleaned only after terminal reconciliation. These are operational defaults. Use a complete hash/length-verified object before committing its reference; if full persistence fails/limit exceeded, record a failed result, not a successful truncated original. Native Research evidence remains its original excerpt contract. Return a bounded excerpt + SourceRef + explicit truncated/continuation in the corresponding result slot. The assistant-call/result pairing survives even when content is externalized. Results required by a valid checkpoint cannot age out as disposable transport bytes.

### 8.3 Trigger, hysteresis and no-progress

Before each dispatch, if counted input>=softRatio*H and enough new complete compressible material exists, compact to <=targetRatio*H. Initial overfull history can compact without prior checkpoint. Subsequent episodes require new eligible coverage or a materially changed source/input policy; no repeated compression of the same boundary solely to chase a token target. Compaction-operation key hashes owner/contextVersion, source/direct-use manifest, covered complete-unit boundary, parent checkpoint, policy/profile.

Persist a no-progress disposition on the compact call for that boundary when validated result fails minGain or no compressible region exists. If no remote call was needed, record a terminal local compact disposition with zero reservation, no native_provider_call_id and an explicit no_dispatch reason in result_manifest; it consumes no provider-call slot and remains recoverable by the operation key. The same unchanged boundary cannot trigger another automatic episode. If original input fits H, continue unchanged with observable soft-compaction failure/no_progress; if it exceeds H, enter waiting_context with context_limit_exceeded and recovery reason. A new tool group or changed relevant input may permit another bounded episode; counters/deadline do not reset. New task content must be distinguished from obsolete candidates, not treated as permission to apply an old summary.

Candidate decision: adopt only a structurally/source-valid, nonempty candidate with gain>=minGain and rebuilt input<=targetRatio*H. A candidate below H but above target is not adopted: a remaining bounded merge may try to reach target, otherwise record target_not_reached and apply the original-input-safe/over-hard rule above. Invalid candidates, exhausted episode limits and known temporary failure use that same finite rule; no extra episode starts on an unchanged failed frontier. Unknown summary outcome keeps its reservation and cannot be automatically resent; authorized original input may continue only if H and remaining allowance permit.

### 8.4 Bounded nonrecursive summary path

`generate_compaction_chunk` calls neutral GenerationPort directly through ledger reservation, with `purpose=compact_chunk|compact_merge`, no tools and **no call back into prepare_main_dispatch**. Summary tasks are task-local and cannot create long-term memory. Partition old material by complete units; large bodies already have original refs and may be summarized through exact bounded source slices while preserving the parent tool group's indivisible coverage/adoption unit.

Default episode max8 chunk calls + max2 merge calls, max60 seconds, execution total max2 episodes/20 summary calls; these defaults need prototype measurement and controller selection. Research policies may allow more episodes within native run budget; acceptance fixture requires two committed compactions in one live Attempt, then separately exercises native role changes and resumed dispatches. Every chunk/merge input itself fits its independently counted cap including output reserve. If chunk summaries cannot merge within the bounded two-stage fan-in, stop with no checkpoint rather than recursively summarizing. No infinite retries, zero-content summary, or hidden unledgered model call. Retry only proven-unsent or known failed operations once within the same episode allowance; outcome_unknown never auto-resends.

Chunk inputs include exact source refs and indispensable constraints/propositions; merge retains all support and conflicts. Every fourth incremental checkpoint (or sooner on correction/conflict/fidelity failure) rebuilds from original covered units using the same bounded path. If raw rebuild cannot fit within allowed chunk/resources, return a bounded recoverable error rather than continuously summarizing summaries.

### 8.5 Atomic adoption and native state preservation

1. Under owner/source/member guards capture contextVersion, current checkpoint/version, native active leaf or run/step/attempt versions/lease, cancel state, complete-unit manifest and direct dependency head versions. Register stable operation key.
2. Release locks; reserve/call bounded summaries and persist safe validated chunk results/usage. No coverage changes yet.
3. Validate schema, exact ranges/provenance, critical values/units/conditions/negation, complete group IDs and all native progress/status fields. Rebuild next protocol payload; recount using frozen counter. Require minimum gain and next input at or below the lower target (therefore hard-safe), per §8.3.
4. Reacquire the same native chain/source/member/audience/head guards. Compare **contextVersion + parent checkpoint version + full source/direct-use manifest + native leaf/state/lease/cancel fingerprint**. Any mismatch rejects adoption. A single bounded rebuild from refreshed eligible input is allowed within original episode budgets; otherwise context_changed waiting state.
5. The #42 persistence command, co-designed with #43 before schema freeze, performs the entire adoption transaction; #43 calls it once and never updates a second pointer separately. In one transaction insert committed task_memory_snapshot, ordered coverage, memory_uses, and advance native owner checkpoint pointer/contextVersion via CAS. Research also records its new context checkpoint reference in the native checkpoint payload/sidecar contract (§10); it does not complete the business step. Commit first; only then assemble next call from this checkpoint and uncovered units.
6. Persist final main-call input manifest/reservation and recheck authorization before dispatch. Continue the same task automatically.

Coverage is exact ordered prefix/set of original complete units; no holes, sibling branches or double-covered tool groups. Uncovered failure attempts and pending state remain explicit. Common-prefix snapshots can be reused only after native ancestry and current dependency checks. No new branch identity tables or independent summary-head framework.

Compaction never updates native run/step/attempt identity, succeeded tools, conflict outcomes, publication intents or cumulative counters. Native cancel/lease state can only be observed, not cleared. New incoming message/branch switch advances/changes native context and makes an old candidate fail CAS; it cannot attach to the new user input. Concurrent compactors have one CAS winner; loser does not advance coverage or repeat completed tools.

### 8.6 Failure, cancellation and crash windows

| Window | Durable truth / action |
|---|---|
| Candidate/chunk generation fails | Original input and old committed checkpoint retained; if input<=H continue automatically, else bounded waiting_context |
| No compressible units or no gain | Persist no-progress boundary; no repeated automatic call for same boundary; hard-overflow is recoverable error |
| Cancel/revocation/deletion during generation | No next request or checkpoint adoption; late result rejected by native/source guards; safe usage reconciliation allowed |
| Crash before external send | Reserved unsent call can be cancelled/retried without double charge |
| Sent but no durable result | outcome_unknown; no blind retry and no coverage advancement |
| Result durable, before checkpoint commit | Recover exact result/hash and input manifest; revalidate context and commit once or discard; no second generation needed |
| Commit acknowledgement lost | Query operation key/native checkpoint pointer on new connection; reuse committed checkpoint or keep old; never infer success from object existence |
| Crash after checkpoint, before next call | Restore committed checkpoint and uncovered groups, fold same budgets, do not repeat completed tools/publication |
| Native Attempt expired/replaced | Old lease cannot adopt; new native Attempt may reuse only committed eligible checkpoint/results under native retry policy and a new base binding |

A resumable context-limit condition stores last valid checkpoint and safe failure metadata. Resume/retry requires an actionable change or explicit approved attempt and remaining policy budget; it does not manufacture capacity or clear unknown costs. Source-invalid checkpoint blocks dispatch and can be rebuilt from authorized originals only within frozen Research scope. If required evidence is gone, use native replan/retry error path; do not use newest unrelated evidence.

## 9. Retrieval, native tool loop and stream (#44)

### 9.1 Retrieval behavior

Apply workspace/owner/audience/source-kind/current revision/dependency/expiry predicates before lexical/vector candidate limits and recheck before return. Reuse tested neutral primitives extracted from current CJK/Latin lexical tokenization, simple FTS/trigram, pgvector cosine and deterministic RRF. Initial pool40/channel, max200 eligible candidates/channel, return<=20; no unbounded widening or paid reranker. RRF60 is a ranking default, not a probability or quality metric. Direct source IDs bypass similarity, never permissions.

Separate memory_text/history_text from asset text indexes. Default memory recall joins current active+valid revision. Final-decision query follows explicit successor relations and conditions; time or similarity cannot resolve conflicts. Historical result states are labeled. Old/missing provider/model/dimensions/version/fingerprint/generation gives memory_index_mismatch; unbuilt scope gives memory_index_not_ready. No silent lexical-only mode labeled hybrid. Management/direct source read can operate while index pending. No cross-request private content cache or separate memory agent.

### 9.2 Protocol implementation and capability gating

`GenerationPort.stream_turn` emits typed TextDelta, ToolCallDelta, ToolCallComplete, Usage and TurnComplete(answer|tool_calls), or ProtocolError. Native call string IDs are retained in memory_calls.provider_tool_call_id; server progress IDs are UUIDs. Assemble fragments up to16KiB arguments/1MiB provider turn; require unique IDs, valid JSON/tool schema and explicit completed turn before dispatch. Unknown tool/invalid JSON gets bounded typed error; never guess arguments or parse tool calls from prose.

| Neutral adapter | Protocol mapping | Capability requirement |
|---|---|---|
| responses.py | function_call + argument deltas, function_call_output by call_id, completed response | Synthetic recorded protocol fixture proves terminal/call behavior |
| chat_completions.py | assistant tool_calls, tool role/tool_call_id, finish_reason tool_calls/stop | Current text adapter rejects calls; reviewed typed adapter must pass pairing/fragment tests |
| anthropic.py | tool_use/tool_result blocks, message_delta stop_reason + message_stop | Test actual compatible shape; provider name alone grants no capability |
| counting.py | model-specific tokenizer/count port and multimodal/protocol accounting | Explicit context capacity/counter version; no byte/4 estimate called exact |

Freeze supportsTools/supportsStreamingTools/supportsCancellation/protocol/adapterVersion/context policy. Unsupported tool mode fails before dispatch with memory_tools_unsupported. Existing text-only providers may still use mode1 with the same hard-budget gate if counting/capacity is known. Neutral summary adapters are available before #43. Legacy Worker imports stay outside new path; direct import smoke verifies R2.

### 9.3 Bounded task loop

Policy defaults max4 main turns,6 tools total,2 tools per provider group,2000 inline result tokens/tool,8000 inline result tokens/task,120s task wall deadline. Compaction has explicit reserved allocation within this deadline and native total call/token limits; maxMain excludes summary purposes but both charge total provider allowance. Research applies the smaller native frozen remaining allowance and memory policy. Empty or unknown cost never means free budget.

Loop: assemble committed units → **prepare_main_dispatch** → atomically journal final input/reserve → mark sent → accept complete native turn → persist complete tool group/results → reauthorize → **prepare_main_dispatch again**, even without new user input → next main turn. Reserve final-answer allowance before additional tools/compaction. Repeated normalized query plus same result IDs/versions twice returns no_new_information. A changed result set permits another bounded call, not a budget reset.

Existing side-effecting Research operations and publication stay outside read-only memory tools; compaction/recovery consult completed native journals and never replay them to rebuild model context. Model-facing memory tools are read-only. Explicit remember is an application command validated against user source; model text cannot assert committed save.

### 9.4 SSE and recoverable status

Mode1 retains existing meta/delta/citations/done/error semantics. Mode2 meta adds `{protocolVersion:2,requestId,executionId,version,contextVersion}` to message IDs. Additional envelopes:

- memory_status `{executionId,phase:'searching_memory'|'searching_history'|'reading_source',callId}`.
- context_status `{executionId|null,runId|null,stepId|null,attemptId|null,contextVersion,phase:'compacting'|'resumed'|'waiting_context',operationKey,checkpointId:null|ID,reason}`.
- context_compacted `{...owner IDs,checkpointId,coveredThroughUnitKey,unitCount,beforeTokens,afterTokens,countSource,counterVersion,policyVersion,durationMs}`; only after atomic commit.
- history_sources `{executionId,items:[{sourceRef,contentKind,excerpt,provenance,occurredAt,branchRelation}],truncated}`.
- memory_saved `{operationId,memoryId,version,indexState}` after durable save only.
- mode2 delta `{executionId,text,provisional:true}`; done `{threadId,assistantMessageId,executionId,version}` after accepted final answer; error `{executionId,code,message,state,retryable}` with no subsequent done.

Native citations remain unchanged and separate from history refs. Buffer mixed text/tool turns until type known; do not expose reasoning/tool arguments as completed answer. A resumed SSE subscriber receives current status plus future events; persisted call/checkpoint metadata reconstruct status without replaying model calls. Research emits equivalent safe context-status metadata through its versioned native event channel (new event type/schema release); logs contain IDs/ranges/counts, never sensitive body text.

## 10. Research integration across every dispatch (#45)

### 10.1 Native entry points and role behavior

Current `research/agents.py::_generate_json` reaches `research/adapters/generation.py::LedgeredGeneration.generate/_generate`; adaptive retrieval invokes that generate_json path, conflict investigation uses its existing checkpointed operation flow. Place the new-version pre-dispatch gate at the ledgered generation entry after role payload construction and before request fingerprint/reservation. Verify planner, each researcher turn, verifier, critic/investigation and synthesizer all use it, including alternate retry/resume paths. Native structural `research-typed-batches-v1` compaction remains lossless encoding; semantic checkpoint selection occurs before final provider serialization/count. Summary calls deliberately use the nonrecursive compact path with native reservations.

| Role | Task memory | Native authority retained |
|---|---|---|
| Planner | Goal/explicit constraints/eligible planning history | Frozen planning source envelope; no new report evidence |
| Researcher | Branch query history/facts/gaps with original handles | Existing evidence.search/load, frozen subset and branch provenance |
| Verifier | Conditions + claims + **loaded original frozen evidence** | Memory summary never suffices to support claim |
| Critic/investigator | Both conflict sides and failed/completed investigation operations | Native conflict states/decisions/journal; no replay during compaction |
| Synthesizer | Verified claims and unresolved conditions | Citations only native supported handles; no historical-memory citation substitution |
| Publisher | Native completed result plus current source/audience guard | Existing publication intents/adoption/reconcile; no duplicate publish |

### 10.2 Per-Attempt base, per-dispatch evolution and checkpoint recovery

At native Attempt start create immutable base binding from approved execution/planning revision, workflow/agent-IO/context version and inherited eligible task checkpoint. Each actual main or summary dispatch creates its own immutable input_manifest and source/direct-use edges. Tool results extend only subsequent manifests. Binding uniqueness per Attempt never constrains later call manifests to the initial source set. Role transitions use new native Step/Attempt/base as normal and may reference only eligible upstream committed checkpoints/claims; role changes do not reset run ledger budgets.

The existing native attempt's memory_context_version/pointer is advanced in the same DB transaction as task snapshot/coverage/uses. The next native business `execution_checkpoint` payload version includes `{memoryCheckpointId,memoryContextVersion,memoryManifestSha256,contextPolicyVersion}` alongside unchanged execution/claims/tool state. Do not overwrite native business checkpoint_artifact_id or run.latest_checkpoint_artifact_id just to represent compaction. Recovery loads native business checkpoint and the attempt's committed memory pointer, verifies both and restores the uncovered completed tool journal. Planning compaction uses native planning Attempt/pointer and does not call `_checkpoint_artifact` helper that currently requires an execution snapshot.

Native run/step/attempt identities, lease, completed_nodes, tool outcomes, evidence snapshots, conflict journals and publication intent remain unchanged by a compaction commit. Stale old worker cannot adopt after lease expiration. New Attempt creation is exclusively native retry/reclaim behavior; it creates a new base, revalidates eligible checkpoint/complete tool results and keeps run/plan cumulative accounting. No latest-memory substitution into a previously dispatched call. Known complete call output can be adopted only against its exact manifest; unknown result retains native outcome_unknown behavior.

Source/member/memory-head changes invalidate calls/checkpoints regardless of frozen context identity. If a safe new context can be assembled without widening frozen evidence, create a new contextVersion before an unsent call; otherwise native retry/replan remains explicit. Previously sent call inputs are immutable audit facts. Failed compaction with hard-safe original payload continues automatically; hard overflow preserves native last-good state and exposes research_context_limit_exceeded/waiting-context failure reason through native failed-step/retry rules. It must not report step success, reset Attempt, or auto-run prior tools.

### 10.3 Exact ledger/release changes

New workflow/agent-IO/context-policy versions freeze memory_policy_json and counting capability. Old releases keep original parsing/policy/zero planning tools, no semantic memory binding; automatic compaction for old frozen runs is not silently enabled. New normal runs use new reviewed version. Deployment acceptance must test both.

`research_plan_revisions.planning_max_tool_calls DEFAULT0` and plan/execution memory_policy_json are additive. Native `_ledger_and_limits` reads the new planner cap for enabled release; never bypass zero by direct sidecar calls. Execution `ResearchToolCall` name CHECK adds memory.search/history.search/source.read with explicit per-role policy; evidence handle creation stays exclusive to evidence tools. Planner read tools use native planning ledger plus memory_calls reservation_state; no execution-only tool row workaround. Existing native provider logical keys use `memory:<purpose>:<owner>:<operationKey>:<ordinal>`; no new purpose column required there.

Every native provider call has at most one matching sidecar, UNIQUE(native_provider_call_id). Sidecar native ledger ID must match attempt's plan/execution ledger. Summary calls reserve on the same ledger and count toward native max_provider_calls and cumulative enabled memory policy. Fold under native ledger lock includes all Attempts on that ledger, all sent/unknown/reserved purposes and inline tool-result tokens (the declared result_tokens column on calls). Native actual/estimated money remains authoritative and nullable. Sidecar settlement updates native provider/tool reservation exactly once in one transaction; reclaimer must settle planner-sidecar reservations before declaring the Attempt reconciled. Duplicate completion uses state CAS and cannot refund/recharge.

No native per-call input/output ceiling is reinterpreted as cumulative allowance or model capacity. New cumulative policy is separately frozen, folded and tested. At least two compactions in one Research task must retain increasing totals, stable tool identities and unchanged publication count.

## 11. Visible user management and in-task continuity (#46)

Real entry: sign in → `/workspaces` → workspace → `/workspaces/{workspaceId}` → Settings → Memory. Member sees only own memory; owner-only model settings remain separate. Flat list/editor/source view with status/scope filters; Add, Sources, Correct, Deactivate, Delete. Display intent and source-invalidity independently where needed. No explanation-only subtitle or extra feature card.

Add explicit statement/scope/expiry; pending save retains draft and key. Timeout polls requestId. Correction submits expectedVersion, displays successor, and preserves local draft on409 with current server value and explicit resave. Deactivate during invalidation remains inactive after rebuild. Source view shows original role/actor attribution/time/branch/contentKind and exact version/span. Unavailable source never opens newest data or internal checkpoint. Delete states original conversations/documents remain; show retrieval suppression vs application cleanup pending/failed/completed, no false restore. Refresh loads server state; local drafts stay runtime state, not persisted Workspace/localStorage. Workspace/user switch aborts subscriptions and clears private content; late responses are generation-key checked.

Chat mode2: explicit history scope selector, `assetScope:none` for history-only question, No private-mode control or indicator is added. Within one submitted task, multiple tool groups can cross threshold; show concise **正在整理上下文 / Organizing context**, then resume the same answer automatically. No Continue button or new message for normal compaction. Error displays actionable missing capacity/budget/source condition and an authorized Resume/Retry action using §7.2; it does not imply that retry will bypass unchanged limit. Refresh/subscription loss shows current phase/checkpoint and eventual committed answer. Explicit Cancel persists cancellation and rejects late checkpoint/result adoption.

Research stays Chat → Research. All roles/tool continuations/resume pass compaction; at least two status transitions visible in acceptance fixture. Native run/step progress is not reset by organizing state. Planning history refs and verified report citations are distinct. Refresh restores native run plus context status; failure shows native retry/replan options. Private run mode is excluded; shared-task compaction uses only lawful task-shared inputs.

Web code owns strict memory/chat mode2/SSE normalizers in feature modules, BFF allowlists and trusted identity forwarding. Do not overload native Citation or Workspace payload. Read current chat/research types, adapters and installed Next16 guidance before implementation. No code/UI implementation occurred in this design phase.

## 12. Dependency-ordered migrations and narrow #42 delivery

No DDL is executed now. Current inspected Alembic head `s3a4b5c6d7e8` follows `r2f3a4b5c6d7`; controller must supply exact merged #40 SHA and revalidated head. Revision IDs are allocated then. New objects are introduced with first real consumer/tests; no twenty-table initial migration.

### 12.1 P1a / #42 — independently approvable instruction-only core

P1a is design-approved and implementation-authorized in its isolated worktree at main8812fda; unrelated neutral code does not depend on #40 merge:

- Only neutral contracts/commands/model exports and one additive migration for memory_instructions, instruction-only memory_sources, workspace-private memory_records/revisions, revision→source support subset of memory_uses, memory_operations. Content-free record/source/action/operation tombstones provide suppression; no separate generic suppression/job table.
- Physical record schema initially has workspace scope only (no thread_id/run_id columns); revision confirmation only explicit_remember/user_confirmed from actual manual action, no sourced_observation activation. No inference/extraction/model/embedding call.
- `AccessPort` is injected and required; commands fail closed on missing authorizer. Only exact manual instruction resolver. User creates/corrects/disables/deletes own record; source/actor attribution cannot be caller-overridden.
- Transactional create/read-current/history/correct/deactivate/delete, CAS/successor uniqueness, loss-of-ack idempotency and synchronous DB byte erasure per §§4–5. No asynchronous resource exists, so no jobs/outbox.
- No mounted router/UI, native source hooks, chat/thread/run audience columns, task checkpoints, history backfill/index, provider/tool/SSE execution, Research binding or private-context injection.

P1a DDL order: (1) instructions with target_memory_id temporarily without FK; (2) sources with instruction FK and unique workspace/owner identity; (3) records without current-version FK; (4) revisions with record/source/instruction FKs; (5) revision-source uses; (6) operations; (7) add deferred record(current_version)→revision FK and instruction target FK; (8) install named erasure/support/head predicates, validate constraints; (9) empty initial memory backfill and feature unmounted. No source-content backfill. Commands and migration share the same CHECK enum/erasure shape.

Specific predicates: `instruction_erasure_monotonic` on instruction update; `revision_erasure_monotonic` on revision update (the sole allowed value-changing transition is live→erased: atomically set conditions/content/content_sha256 ALL SQL NULL and erased_at from NULL to non-NULL, with every other field unchanged; an already-erased row may only remain unchanged, never restore payload or change erased_at); `memory_revision_support_required` deferred on revision insert, record-head advance and uses insert/update/delete validates required confirmation support/same owner+workspace for instruction-only source; successor scope/acyclicity validated under locked command and unique successor constraint. FKs enforce IDs/workspace, not model semantics. PostgreSQL tests insert illegal rows directly to exercise these predicates. Erasing bytes keeps all support IDs, so no trigger exemption conceals unsupported live memory.

### 12.2 Later dependency manifest

| Migration/contract stage | Ordered creation and activation | Issue / prerequisite |
|---|---|---|
| M1 P1a | Exact six-table core above, delayed cyclic FKs/triggers; no native mutations | #42; #40 handoff + narrow review |
| M2 native provenance/lifecycle | Extend source resolvers one kind at a time and add real async jobs when needed; source mutation hooks + guards before enabling that kind; add thread/run applicability columns only with tested resolver | #42; M1; explicit overlap ownership |
| M3a neutral protocol + journal skeleton | Neutral adapters/counting/contracts first; create chat execution row without checkpoint FK; create memory_calls without snapshot/binding FKs; keep new dispatch unactivated | #44 prerequisite for #43; M2 sources needed by fixtures; no private-task/audience constraint |
| M3b compaction core | #42 owns atomic storage/adoption primitives co-designed with #43; create task_memory_snapshots after calls, then coverage; add snapshot generation_call FK, execution checkpoint FK, call checkpoint FK, memory_uses snapshot/call/direct-use columns and XOR/uniques; validate all; native ancestry/context CAS implementation | #42 atomic storage + #43 core; M3a; no private recall into shared tasks |
| M4 index | Separate index entries/manifests, generation/profile eligibility, bounded backfill/dry run | #42; M2; no model backfill without allowance |
| M6 Research bindings/release | Create base bindings referencing native Attempts and optional snapshot; add call binding/native-ledger FKs and uniqueness; add Attempt context columns/FKs and plan/execution memory_policy/planner cap; expand tool/event constraints; register immutable release rows last | #45; M3b; private injection excluded |
| M7 API/UI activation | Mode2/parser/request replay, tool loop, all pre-dispatch seams, management and native context events/normalizers; enable only matched versions | #44/#46; required storage/compaction/tests; private mode excluded |

Cross-stage columns/FKs are installed only when targets exist; migration code must explicitly list create/add/validate sequence. Circular calls↔snapshot/binding references are initially nullable, then FKs added after both tables; enabled code requires their purpose-specific relationships. No placeholder FK to a future migration or trigger that references an absent audience column. Chat execution tracks current workspace-visible tasks; private-output activation is outside this delivery. M3a is a small shared prerequisite, not a full generic agent framework.

New tables carry `UNIQUE(workspace_id,id)` where composite referencing requires it; revisions include workspace_id with FK `(workspace_id,memory_id)->records(workspace_id,id)` and unique(workspace_id,revision_id). Same-workspace sources/calls/snapshots use equivalent composite FKs. These denormalized scope columns are FK-checked, never independent authority. Cross-owner instruction support checks remain the named bounded predicate above; native polymorphic source permission is enforced by resolver under guard, not blanket SQL triggers.

### 12.3 Deployment and downgrade fence

Deployment must preserve source/audience checks for all new shared-context consumers. New code does not create private native tasks, modify existing output visibility or require a private-task deployment fence.

Downgrade: reverse dependencies and named triggers/FKs, never drop shared pgvector/pg_trgm extensions or native data. P1a down works on empty fixture; nonempty user memory requires approved export/erasure and no unsettled operations, otherwise abort. M3/M6 down refuses active/unknown calls, referenced checkpoints or frozen new releases; settle/export or roll forward. Production default is guarded refusal/roll-forward repair, with disposable populated upgrade and safe-down rehearsal evidence.

### 12.4 Backfill and retention safety

No old conversation becomes confirmed memory automatically. Backfill only enabled source metadata/history index, with exact actor unknown where native evidence lacks authorship. Stable ID/source-version batches200, high-water manifest and idempotent job key; lock/revalidate each source, skip archived/deleting/failed/internal-ineligible entries. Interrupted batch replay cannot resurrect a tombstone or substitute a newer source version into old context.

Default backfill dry-run lists synthetic/authorized IDs and counts, no provider calls. Production embeddings need resource/cost allowance; local stubs validate mechanics only. New index generation activates only after exact eligible manifest completion; incomplete scope returns not_ready. Backfill never overwrites original source rows and does not delete archives. Reference-safe TTL and revocation maintenance from §5 remain active during rollback/recovery.

## 13. Evidence and acceptance plan

### 13.1 Fixed source/provenance and lifecycle fixtures

Use synthetic versioned sources under future `apps/api/tests/fixtures/memory/`, with exact actor/workspace/audience, parent graph, native versions, indispensable propositions and support spans. Evidence under `specs/v5/memory-management/evidence/` only after ownership grant. No real private data/credentials.

| Fixture | Oracle and required result |
|---|---|
| F01 precision | “37.5 ms only for batch=8; never production” survives summary and answer with exact source support |
| F02 correction/CAS |10→12 explicit correction; concurrent correction/disable one winner; one successor |
| F03 attribution | suggestion/maybe/ambiguous yes produce no long-term body/job/vector; explicit quoted confirmation succeeds; eval policy cannot authorize it |
| F04 observations | sourced config/time remains observation through dedup/rewrite; unresolved Research conflict stays task-local |
| F05 branch/scope | same-name workspaces and forked contradictory decisions; no leak/adoption; common prefix proved by ancestry |
| F06 privacy | another member and owner denied private outputs/source/event/download/search/cursor; shared prompt excludes private input |
| F07 intent-validity | invalidate→disable→recompute, inactive→invalidate→recompute, superseded→invalidate→recompute retain intent; delete beats late result |
| F08 direct consumption | summary/tool result consumed M; disable/delete/correct M with raw source intact; old consumer blocked at resume/dispatch; no source-wide suppression |
| F09 / ER01 erasure/FKs | Put unique synthetic marker `ER01_CONDITIONS_ONLY_7C92` only in conditions.subject or conditions.applicability, never content, across multiple revisions. After synchronous P1a delete commit, inspect every owned persisted semantic payload: marker absent and all revision conditions/content/hash NULL with erased_at set. Retained identity/support/FKs/CAS/idempotency remain valid; GET/history deny erased payload, same-key replay cannot disclose or restore it, and referenced tombstone TTL remains blocked. Direct PostgreSQL writes reject erased rows retaining conditions/content/hash, live rows with missing/malformed conditions, and erased→live restoration. Preserve unrelated native archives and another live record’s legitimate source. |
| F10 revoked maintenance | pause cleanup after delete commit, remove requester/archive workspace, retry exact command succeeds without reads/models or another user's authority |
| F11 original tail | decisive text beyond 2000/4000 chars, Unicode range and changed revision; exact reconstruction or410, never latest substitution |
| F12 requests | mode1 selected-empty rejected; mode2 none succeeds without fake assets; workspace_history locates unknown thread; pre-meta loss/same-key replay/retry/cancel race |
| F13 protocol/index | fragmented/duplicate calls, invalid JSON, wrong finish/refusal; stale fingerprint/wrong dimension/missing capacity rejected |
| F14 migration parity | populated source/chat/citation/failed parent/report/conflict data unchanged; no inferred author; guarded down and shared-output filtering excludes owner-private inputs |

### 13.2 Mandatory §12 automatic compaction fixtures

| ID / external §12.8 | Engineering trace and semantic oracle |
|---|---|
| C01 /1 | One ChatV2 request, no subsequent user message; tool groups grow past soft threshold; committed checkpoint then next main dispatch/final answer same execution; mandatory source facts retained |
| C02 /2 | One Research run crosses threshold at least twice (including role/continuation path); two committed checkpoints in the same live Attempt, plus native role/resume dispatch coverage; counters monotonic across roles; precise numbers/conditions/negation/conflicts/handles correct |
| C03 /3 | Multiple tool calls in one provider turn, delayed final result; no half-group coverage/dispatch; oversized full result durable with bounded ref; no compressible units and still-too-large merge are bounded errors |
| C04 /4 | Old/new full native trajectory comparison: no repeated completed side-effect/investigation tool, exactly same native publication intent/adoption count; cumulative usage/cancel unchanged by checkpoint |
| C05 /5 | Crash during candidate, after result durability, before/after checkpoint commit and before next dispatch; coverage no gaps/duplicates; unknown send never claimed exactly-once or silently retried |
| C06 /6 | Concurrent message/branch switch/compactors, source delete, direct-memory disable, member revoke, cross-user/workspace IDs; stale source/context/CAS/lease blocks late adoption |
| C07 /7 | Valid JSON with omitted qualifier/negation/support is a negative-quality case; semantic reviewer detects error despite structural pass; compare original inputs, summaries and supported answers |
| C08 /8 | Real page displays Organizing context, automatically resumes with no user action; hard-limit failure has clear recovery; refresh restores task/checkpoint/cancel state |
| C09 /12.2/12.5 | Same no-gain boundary not retried; new complete group permits another bounded episode; chunk/merge calls never recurse into compaction; caps and reserved final-answer headroom enforced |
| C10 /12.4/12.6 | Unknown DB commit reconciles by stable operation key; cancelled/expired Attempt cannot adopt late summary; last-good checkpoint remains intact on all failures |

Reviewer oracle cross-map (all unexecuted): O22→§8.1/8.3, O23→§8.5, O24→§8.2, O25→§8.4, O26–O27→§§6.3/10, O28→§8.3/8.6, O29→§8.5/8.6, O30→§§11/13. CO01→C01; CO02→C02; CO03→C09; CO04→C03/C05; CO05→C03/F11 (including archive-write failure); CO06→C03/C09; CO07→C03/C09/C10; CO08→C06; CO09→C06/C10; CO10→C05/C10; CO11→C07; CO12→C08. Execute the reviewer cases with their exact fault variants; this mapping does not narrow their acceptance.

Required per-dispatch trace: task/run/step/attempt/execution IDs, main logical key, contextVersion and checkpoint ID, complete-unit coverage manifest hash/range, input before/after, trigger/no-progress reason, counter id/mode/version, policy/profile fingerprint, summary operation/parent/chunk/merge call IDs and usage, native role/group/frontier IDs, target/soft/hard thresholds, reservation/settlement/cumulative deltas, deadline and publication identity, native budget ledger version, cancel/lease state, source/direct-use validation disposition. IDs/counts only in ordinary logs; synthetic source manifests and safe request hashes in evidence. Record one trace row for **every** main dispatch, including no-compaction and resumed dispatch; missing row is a seam-coverage failure.

### 13.3 Evidence levels and commands

D=design/static; T=deterministic provider/protocol/unit; M=real PostgreSQL migration/CAS/races; R=isolated API/BFF/Worker/object-store recovery; Q=annotated semantic model quality; U=real visible browser. Each reports pass/blocked/not applicable, exact SHA/config/command/fixture, expected/actual result and limitations. T cannot accept Q; row counts/checkpoint creation/token savings cannot accept C01/C02/C08.

Use deterministic recorded synthetic provider streams and embeddings for T/R. Real-model semantic evidence requires an approved local model; if unavailable, Q remains blocked. No paid evaluation. Report per-proposition correctness/source support, recall@k only on fully labeled eligible corpus, stale-use/exposure/semantic omission counts, latency and reported/estimated/unknown token/cost separately. Do not collapse into invented quality score. Any leakage, deleted-body replay, wrong confirmation, silent overwrite, unsupported citation or critical lost condition blocks release.

Planned commands, not executed evidence:

```text
uv run --project apps/api pytest <explicit new memory/compaction test paths>
uv run --project apps/worker pytest <explicit new dispatch/recovery test paths>
uv run --project apps/api pytest apps/api/tests/test_chat_service.py apps/api/tests/test_chat_router.py apps/api/tests/test_providers.py
uv run --project apps/api pytest apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini check
pnpm --filter @citeframe/web test
pnpm --filter @citeframe/web exec tsc --noEmit
pnpm --filter @citeframe/web lint
pnpm --filter @citeframe/web build
pnpm --filter @citeframe/web e2e
```

Run migration/down/race tests only on disposable PostgreSQL; exact populated before/after source payloads and illegal-row tests required. Import smoke omits API/Worker modules and checks neutral adapter identity. Existing Research compact/agent-IO/adaptive/conflict/publication regression fixtures must stay valid for old releases.

Real browser: normal login/workspace → Memory first-use/add/source/correction/two-tab409/deactivate/delete/refresh/revoke; then single-request chat C01 and multi-compaction Research C02, C08 failure/recovery/cancel. Correlate visible status and final answer with actual network/DB/call trace. API mocks/headless assertions alone do not accept the user experience. Independent reviewer inspects governing outcome before checklists and reverse-tests the failure cases.

## 14. Controller decisions and Issue/PR map

A1 is resolved: no native private-output mode or audience schema; private memory never enters shared model paths. A2 mode2/history scope, A3 bounded capabilities, A5 initial scopes, A6 additive contracts and A7 versioned Research integration are authorized in-scope engineering decisions for controller acceptance after independent review. A4 is application-cleanup configuration with recovery-safe TTL; no backup/provider-retention promise. No new sharing, native archive deletion or evidence privilege expansion is authorized.

Every implementation slice has one developer and independent reviewer; controller owns integration and actual PR assignment. All slices stay under parent #41 and existing linked children; no new Issues are created by this lane.

| Issue / slice | Deliverable and dependency | Acceptance boundary |
|---|---|---|
| #42 P1a | Instruction-only core §12.1 from fixed isolated main after narrow review | Explicit owner-private commands/erasure/idempotency; no APIs/UI/model/runtime acceptance |
| #42 later | Atomic checkpoint/coverage/adoption storage co-designed with #43; activated native source provenance, lifecycle maintenance, direct uses and retrieval indexes; no native audience schema | F01–F14 relevant data/ACL/runtime gates |
| #44 prerequisite | One neutral protocol/count implementation and durable call/execution owner skeleton, before summary consumer | Parity/import tests, no premature private/model feature activation |
| #43 compaction core | Bounded summaries, complete-unit coverage, atomic native context CAS/checkpoint, no-progress/failure semantics; depends on shared call prerequisite | C03/C05/C06/C07/C09/C10; semantic evidence separate |
| #44 chat loop | Both chat dispatch gates, mode2 exact request/scope/replay/retry, native tool loop and SSE | C01 + complete request/protocol/recovery/browser trace |
| #45 Research | Every role/continuation/resume gate, per-call manifests/native budgets, repeated compaction and checkpoint recovery | C02/C04/C05/C06/C10 with frozen evidence and old-run parity |
| #46 management/UI/trace | Memory management, context-status/reconnect UX, per-dispatch engineering trace and integrated real-page acceptance | C08 plus Q/U and full parent acceptance |

#43 can review/test the core before #44 loop activation; #45 supplies Research-owned additions after that core. P1a approval cannot be generalized to full foundational schema, A1 or parent completion. #42 and neutral #44 implement concurrently in explicitly authorized isolated worktrees from main8812fda; only later #40-dependent route integration waits for its merged baseline. Shared contract owner is #42; atomic checkpoint/coverage/adoption remains cohesive.

## 15. Review resolution and complete proposal coverage

These are developer corrections submitted for independent re-review, not closed-review claims.

| Finding | Normative resolution | Negative acceptance |
|---|---|---|
| R2 | §2 one contract owner; neutral protocol/counting implementations, direct roots, lock/deploy/import updates; prerequisite before #43 | Import with both apps unavailable; one implementation per protocol |
| R3 | §4.3 immutable revisions separate intent/validity, one current head and CAS table | F07 interleavings preserve disable/supersede/delete |
| R4 | §§4.2–4.3/5.3/5.5/12.1 live/erased conditions+content+hash CHECK and irreversible all-revision clearing; retained identities/support, reference-safe purge | F09/ER01 conditions-only marker, physical erase, denied history/replay, FK integrity and direct-SQL rejection |
| R5 | §4.4 typed direct revision/snapshot/result dependencies plus raw leaves; source/head checks at all consumption/adoption boundaries | F08 old source survives while consumed memory changes |
| R6 | §§6.2–6.3/10 Attempt base plus immutable evolving per-call manifest and locked native-ledger fold | C02/C04/C05 totals/source union/recovery, default-zero old planner |
| R7 | §7 exact mode1/mode2 none union, history scope envelope, requestId lookup/replay and retry-child identity | F12 lost meta/no assets/unknown thread/cancel race |
| R8 | §5.1 per-item attributable action/proposition support only; evaluation grants no confirmation | F03 ambiguous/material paraphrase rejection |
| R9 | §12 exact P1a, ordered delayed FK/trigger installation, consumer-first stages and mixed-binary fence | F14 populated upgrade/down/fence tests |
| R10 | §§3.3/5.4 narrow server maintenance capability; P1a synchronous DB erase | F10 cleanup completes after actor revocation without model/read privilege |
| R11 | §§8.1/8.3/9.3/10.1 mandatory every-dispatch gate and hysteresis | O22/CO01–CO03 |
| R12 | §§6.1/8.5 #42-owned atomic coverage/source/context pointer CAS, #43 orchestration | O23/CO08/CO10 |
| R13 | §§6.2/8.2 complete in-flight groups and durable oversized-result refs | O24/CO04–CO05 |
| R14 | §§8.3–8.6 bounded nonrecursive chunk/merge and finite failure/no-progress rules | O25/O28/CO03/CO06–CO07 |
| R15 | §§6.3/10 same-Attempt context chain and continuous native budgets/recovery | O26–O27/CO02/CO10 |
| R16 | §§9.4/11/13 durable progress, correlated trace and separate semantic/browser gates | O30/CO11–CO12 |
| R1 preserved | §5.2 guarded read/enqueue and final guarded CAS/commit | Runtime barrier test, no security pass from prose |

| Proposal section | Operative design coverage |
|---|---|
|1–3 four layers/source preservation | §§1,3–6 |
|4 budgeting/semantic summary | §§6,8 |
|5 active retrieval/tool loop | §§7,9 |
|6 long-term admission/update | §§4–5 |
|7 Research evidence/recovery | §§6,10 |
|8 permissions/management/deletion | §§3–5,7,11 |
|9 modules/persistence | §§2,4,6,12 |
|10 engineering/semantic/UI acceptance | §13 |
|11 authorized rules | §§1,3,5,14 |
|12.1 same-task automatic continuation | §§8.1,9.3,10.1; C01/C02 |
|12.2 every dispatch/soft-lower target/no-progress | §§8.1/8.3; C09 and per-dispatch trace |
|12.3 complete groups/original oversized results/fidelity | §§6.1,8.2/8.4; C03/C07 |
|12.4 atomic version/source/context checkpoint | §§6.1–6.2,8.5,10.2; C05/C06/C10 |
|12.5 native state/budget/nonrecursive bounded summary | §§6.3,8.4–8.5,10.3; C02/C04/C09 |
|12.6 safe failure/cancel/revocation | §§8.6,7.2; C05/C06/C10 |
|12.7 visible status/refresh/privacy-safe traces | §§9.4,11,13.2; C08 |
|12.8 mandatory acceptance1–8 | §13.2 C01–C08, independently scoped T/M/R/Q/U evidence |

Handoff: only this design and inventory are authored in this lane. No product code, migration execution, tests, services, model evaluations, Git-state or shared workbench/profile-memory changes. Design review is complete; product tests and acceptance remain required. A1 is resolved. Only overlapping #40 integration requires its handoff. Reviewer R11–R16 and O22–O30/CO01–CO12 are mapped into the normative contracts and acceptance cases above; their independent re-review and execution remain pending.
