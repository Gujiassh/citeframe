# Issue41 — independent Critical design review

**Current disposition: R1–R16 closed at design level; no open P0/P1 design findings.** Final targeted R4 verification is recorded below for design SHA-256 `D0F38DCC2B34B4F1F8D9F55372EC79551D057A44AE3BF368784E14ACAF3EE01B`. Narrow #42 P1a is design-eligible; integrated design is conditionally accepted, excluding authorization of the unapproved A1 audience branch. Product implementation remains blocked on #40 merge/handoff and controller go-ahead. All Issue41 implementation/runtime/model/UI evidence remains unrun. Earlier findings and dispositions are retained as historical review records.

Historical first review, 2026-09-28: effective `spec.md` §§1–11; `design.md` §§1–17 (the completion addendum appeared during review); final available `code-inventory.md`; relevant baseline source. Current HEAD `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`. #40 PR47 has the controller-reported external MinIO registry 401 CI blocker and no handoff; this review did not independently probe CI or services. No product/test/service/branch changes or paid evaluation.

## Findings — severity first

Section references below are to `design.md`; line anchors identify the reviewed snapshot. A1 is an existing escalated authorization gate, not a newly invented review requirement.

### R2 — P1: the proposed shared provider implementation is still API-owned

**§2.1 table and provider extraction paragraph, lines 61–78; §§9.2, 15.2.** `citeframe_memory` is neutral, but the new structured adapters are placed in `apps/api/.../services/generation_protocol/`; Worker composition is told to use the same adapters. That either adds Worker imports of API implementation for new paths or creates duplicate adapter implementations. Port declarations alone do not make the actual shared implementation neutral. The baseline Worker/API coupling is explicitly legacy, not a precedent to extend.

**Correction:** locate the required protocol adapters, tokenizer/counting primitives and their configuration DTOs in one neutral implementation module/package used directly by both composition roots. Avoid a second parallel set of ports in `citeframe_contracts/memory.py` and memory-service `ports.py`; choose one contract owner. API/Worker supply credentials/settings at composition, with no neutral import of application settings or routes. Name the final import graph and deployment/lock/import-smoke changes. Parity-test only the extracted primitives needed by new paths, before adding tool behavior. Do not postpone this prerequisite until P6 while P5 Worker summary generation already needs it.

### R3 — P1: lifecycle transitions still contradict preserved user intent

**§§4.3, 6.2, 17.2; lines 171–196, 355–365, 839.** The final edit adds revision status, resolving the earlier missing historical-status field. The transition table still maps active/inactive/superseded to invalidated and then invalidated to active, while the following paragraph forbids reactivating disabled or superseded records. It does not specify how recomputation reconstructs the latest durable user intent, or how a user's disable action during invalidation wins over a pending recompute. Implementing the displayed state machine would reactivate the wrong records.

**Correction:** define a single consistent transition/CAS table. Either separate user lifecycle intent from source validity (expiry may be a read predicate), or explicitly reconstruct the latest applicable user intent from the newly persisted revision history under the same record lock. Recompute repairs validity, never reverses disable/supersede/delete. Specify invalidate→disable→recompute, inactive→invalidated→recompute and superseded→invalidated→recompute. Historical revision status must remain frozen, while present readability stays separately gated. Avoid redundant authorities or status-only revisions without a defined audited meaning.
### R4 — P1: instruction erasure violates its own CHECK; retention lacks reference-safe order

**§§4.2, 4.3–4.4, 11.1–11.2, 17.1/17.5; lines 160–167, 628–640, 818, 866–868.** Remember/correct/confirm instructions require nonempty content, yet erasure sets that content NULL without an erased discriminator or an exception to the CHECK. Cleanup cannot satisfy both contracts. Separately, “source tombstones 30 days after cleanup” is incompatible with live source FKs in revisions, coverage, dependencies and source-lifetime suppressions unless referential retention and purge order are defined. §17 correctly retains referenced tool objects; that does not solve these relational cases.

**Correction:** give instruction content an explicit irreversible erased state/timestamp with mutually consistent content/hash CHECKs; retain content-free actor/action identity. Specify reference-aware cleanup order and which metadata remains while a revision, snapshot, frozen binding or suppression still references it. No native archive cascade and no removal of support links that violates the mandatory-support trigger. The 30-day value is a controller-set cleanup policy for eligible unreferenced data, not a promise to break live FKs. PostgreSQL tests must execute actual delete/erase and replay, not just empty-table downgrade.

### R5 — P1: raw-leaf dependencies do not capture memory disable/delete/supersession

**§§4.1, 4.4, 5, 9.3, 11.2, 17.1; lines 140, 218–234, 334, 558, 638, 820.** `derived_source_links` links only `memory_sources` to revisions/snapshots; the source kinds do not include a memory revision or task snapshot. Chat execution manifests also contain only SourceRefs. Flattening to original leaves is valuable for source deletion, but loses the direct edge “summary/tool result/execution consumed memory M revision V”. Disabling/deleting/correcting M does not invalidate its still-valid original message/instruction leaves. The prose requires invalidating dependent summaries/bindings, but the general chat/task graph cannot locate or validate all such consumers. Research's revision-ID JSON is only a partial special case.

**Correction:** retain direct typed dependencies on consumed memory revisions/task snapshots as well as the necessary raw-leaf provenance, or an equivalent explicit consumer-use manifest queried at every eligibility/adoption boundary. State how status/version changes fence queued and in-flight consumers; do not invalidate shared raw sources simply to hide one private memory. Add reverse cases: summarize M, disable/delete/correct M while its raw source survives, then resume/reuse the summary and tool result. No old wording may re-enter default context. A small typed dependency design should replace parallel ad hoc graphs where practical.

### R6 — P1: Research binding cardinality and mutable protocol budget are inconsistent

**§§10.2–10.3, 17.3; lines 591–608, 845–852.** One immutable binding per Attempt is frozen before a provider call, while subsequent history tools discover additional sources and subsequent calls use them. There is no specified relationship between that immutable manifest and each evolving call input. §17.3 adds cumulative “binding-local protocol state” and a binding policy, but neither is present in the binding schema; the sidecar call table has only request hash, not the described durable request/manifest state. Recovery cannot deterministically establish the input set and remaining budget merely from the base binding hash.

**Correction:** choose one concrete model, preferably immutable Attempt base context plus append-only per-call input/source manifests and a single versioned protocol-budget owner under native lock order. Specify source union, hashes, changed-source checks, resume versus new Attempt, and how native reservations and sidecar tool reservations settle once. Persist the exact cumulative policy/counters or define a locked deterministic fold over complete ledger rows; do not leave an in-memory accumulator. Include new planner cap/default-zero old-release parity from §17.3. Native `lease.py:_ledger_and_limits` currently returns zero planning tools; `tools.py:begin_tool_call` is execution/role-specific. Keep those old-run semantics and avoid double accounting.

### R7 — P1: history-only, cross-conversation and recovery APIs are not yet executable contracts

**§§7.1–7.2, 9.3–9.4, 12.2, 17.1–17.2; lines 375–458, 560–568, 659, 820–841.** Several user paths still depend on unstated request/response semantics:

- Mode 2 proposes an “explicit empty asset selection”, but the existing `SelectedAssetScope.assetIds` requires at least one ID. There is no exact versioned request union/alternative or request discriminator contract. The final §17.8 now supplies event envelopes; it does not fix the request union.
- Default history search is current task/branch; cross-task lookup requires explicit orchestration scope, but no such selector/envelope is defined. `threadId` narrows to a known thread; it cannot express proactive workspace-history lookup when the relevant thread is unknown.
- After a timeout before response/meta, the client has requestId/key but may not have operationId/assistantMessageId. Polling by those server IDs is not a complete unknown-acceptance recovery path. Define same-key replay/pending lookup returning the existing identifiers, and its safe error envelope.
- Explicit retry creates a new attempt, while chat execution has one terminal state and one assistant message; specify whether retry creates a new execution/request identity or a child attempt, how message duplication is avoided, and which version cancel compares.

**Correction:** supply discriminated mode-1/mode-2 DTOs, exact read-only history scope selector within a server-established authorized envelope, and request-ID/key-based status/replay flow; implement the now-specified §17.8 SSE DTOs/ordering. Preserve existing asset citations and mode-1 errors. Source responses must also carry enough explicit role/provenance metadata for the promised original-source view. Table-driven parser/API cases should cover no assets, unknown history location, acceptance-before-meta loss, retry and cancel/success race. A2 is necessary to the stated outcome and can be resolved by the controller; no additional user gate for these engineering details.

### R8 — P1: an evaluation policy must not substitute for attributable confirmation

**§6.1 step 4, line 345; §§1.1, 4.3, 14.2.** “Materially paraphrased decisions require confirmation **or an annotated semantic validation policy**” leaves a path for policy/model evaluation to confer `user_confirmed` status. Corpus-level semantic validation does not establish this user's confirmation of this proposition. The effective spec's §§6–7 now correctly exclude generic long-term candidate persistence; that correction is acknowledged.

**Correction:** bind every confirmed/explicit statement to an actual attributable instruction or confirmation action and its proposition/span. A meaning-preserving rendering may retain that provenance only under the defined per-item source-fidelity rule; a materially different proposition requires a new user action. Quality policy is evidence about extraction behavior, never authorization. Reject ambiguity before jobs/results/indexes; observations remain observations through dedupe and corrections. Do not require mechanical confirmation of every verbatim explicit remember request.

### R9 — P1: migration/slice ordering commits to unresolved A1 and cross-migration references

**§§4, 13.1–13.4, 15.2, 17.1; lines 205–208, 685–711, 792–802, 820.** M2 includes execution journals/budgets; the now-defined `chat_memory_executions` constraints require private thread audience, whose columns arrive only in M3/A1. M1 snapshot generation-call references also precede the proposed call table. The design has not listed when cyclic/cross-stage FKs and constraint triggers are installed or enabled. P1 is broad enough to build task/audience contracts and all source hooks before A1, although only a much smaller owner-private persistence core is scope-independent.

**Correction:** provide a dependency-ordered migration manifest: table creation, deferred/cyclic FK addition, trigger installation/validation, backfill and activation. Move audience-dependent chat/task execution constraints after approved privacy contracts; split M2 if necessary. State the mixed-version deployment fence that stops an old API/Worker binary reading private tasks, not only a feature flag that old binaries do not understand. Keep the existing rollback refusal for populated private data. Narrow P1 as below; do not ship speculative full M1 merely because it is additive. #40 handoff remains an external prerequisite, not permission to work around its CI blocker.

### R10 — P1: revocation can strand required cleanup under the requester's permission

**§§3.1, 4.6, 11, 17.2/17.5; lines 98, 283–312, 638–644, 833–870.** Every job has `actor_user_id`, and the stated worker rule revalidates requester membership at claim. That is correct for model/extraction/index work but leaves invalidation/erasure with no defined authority after that actor is removed or the workspace is archived. Required cleanup could remain permanently queued, despite already-committed delete suppression.

**Correction:** distinguish user-content jobs from narrowly authorized lifecycle maintenance. Maintenance executes only a durable, server-created deletion/invalidation command for its exact owned resources, without granting user reads/model dispatch or falling back to another member/owner. Preserve attributable initiator metadata. Define claim/retry and FK behavior after membership loss/user lifecycle, and test revoke immediately after delete commit with cleanup paused. This is an explicit maintenance capability, not a generic permission bypass.

## Closed security-contract finding after concurrent completion

**R1 — initial P0, resolved at design level by §17.7 (lines 885–885).** The final addendum defines shared source/membership/task-audience read locks, existing workspace/membership guards, serialization and bounded enqueue/dispatch authorization under the guard, conflicting invalidator writes, and no lock across remote IO/backpressure. It explicitly distinguishes already-enqueued bytes from new reads and requires subsequent checks. This closes the initial check-then-use design finding. It still requires concrete PostgreSQL/runtime barrier evidence; no implementation security pass is given. Missing membership fails closed. The final adopter must retain the same source/authorization guard through its CAS/commit, consistent with §5.1.

**Prior-review open count: P0 = 0; P1 = 9 (R2–R10).** The later spec v3 supplement adds R11–R16 and retains these findings. A1 remains the separately escalated, unapproved output-privacy expansion and blocks activation. It is not reported as an invented new defect. §17.8 also resolves the missing new-event envelopes and provider string-call-ID versus server-UUID distinction; R7 is narrowed to the remaining request/scope/recovery contracts.
## Scope and simplicity judgment

The high-level plan covers the full goal and correctly separates task memory, long-term memory, native evidence and real quality/UI acceptance. §17 materially improves source fidelity, unknown-call recovery, planner budget defaults and referenced-result retention. Full schema acceptance still requires R2–R10; R1 is design-resolved as recorded above.

**Necessary mechanisms:** immutable source/revision provenance; CAS; source eligibility and consumer dependencies; idempotent write/cleanup recovery; durable externally dispatched call identity; per-call budgets; Research's native authority; separate new-mode transport contracts. Removing these would weaken a required invariant.

**Simplify before implementation:**

1. Do not build all approximately twenty proposed tables, generic jobs, every source kind and triggers in the first persistence PR. Add each structure with its first real consumer and its negative tests.
2. Prefer ordinary composite FKs, UNIQUE/CHECK constraints and typed relations for same-owner/workspace/version invariants. Keep constraint triggers only for genuinely cross-row invariants, with a named predicate and insert/update/delete firing coverage. “Service plus triggers for all polymorphic references” is too broad to review and maintain. No need to introduce RLS or another authorization framework.
3. Use one immutable revision reference/current head representation where possible. Avoid independent duplicated version/status authorities unless their consistency rule has a clear consumer. Separate source validity from user intent (R3).
4. Prefer one typed dependency/consumer-use representation covering the actual edges; retain raw-leaf expansion as provenance/eligibility support. Do not replace it with an unbounded general graph framework.
5. The two new branch sidecars in §17.7 need a specific consumer justification. Native parent ancestry plus immutable prefix/leaf manifests may already support summary reuse; prefer that unless stable branch identity is demonstrably required. If retained, define its current-leaf/concurrent-append semantics without rewriting native history. This is a simplification recommendation, not a new product gate.
6. Keep provider implementation neutral in one place (R2); one port owner; thin application composition. No wholesale legacy-provider/retrieval rewrite or new service deployment is needed.
7. Reuse native Research reservations and lock roots. Add only missing sidecar protocol information; justify a separate planner reservation table against keeping settlement fields with its owning call. Exactly-once accounting is the invariant, not the table count.
8. Default to sequential tools, no cross-request private content cache, no paid reranker or standalone memory agent. These are suitable scoped choices already in the candidate.

A3 count/time/token limits, soft packing shares, batch sizes and A4 active-store cleanup targets are controller-owned operational defaults. They need consistent storage, measurement and error behavior, not a fresh user approval question for each number. Any backup/provider-retention promise remains limited to what operations can actually guarantee. A5 workspace-local initial applicability may be controller-approved as a recorded delivery boundary; it must not imply user-global/project-identity support.

## Exact bounded next slice

**Now:** design rework only, in the currently assigned documentation ownership. No product edits, migrations, service work or branch change while #40 has no handoff. A1 remains pending with the main controller; this review neither approves nor rejects the candidate private-thread/run expansion on the user's behalf.

**Feasible after #40 handoff + narrow corrected design approval, without waiting for A1:** `P1a / #42 owner-private explicit-instruction persistence`.

Allowed scope:

- Neutral contracts/models/commands and one additive migration for attributable **manual explicit instructions**, owner+workspace-private memory records/revisions, their direct support links, operation idempotency and content-free erasure/suppression metadata.
- Only the `memory_instruction` source resolver, fail-closed injected actor/membership validation, and workspace-local applicability. No inference, model calls, embeddings or automatic promotion. Preserve extension seams without inventing private thread/run contracts.
- Transactional create/read-current-and-history/correct/deactivate/delete primitives, consistent state/CAS, instruction/revision erasure and replay. Add a minimal durable cleanup/outbox only if that slice actually has asynchronous resources; do not prebuild the six-kind job engine.
- Existing neutral model exports and API-owned Alembic registration; narrowly assigned package/manifests and deterministic PostgreSQL/unit/import tests. Feature remains unmounted/unactivated until its own API/UX slice is reviewed.
- Tests: two users in one workspace plus cross-workspace IDs; unauthorized/missing authorizer denial; two-writer CAS; one successor; idempotent retry after lost commit acknowledgement; erased content not replayed; instruction CHECK-compatible cleanup; no unrelated/native row mutation; populated upgrade and guarded downgrade.

Explicitly excluded from P1a: native thread/run audience columns, source hooks on chat/assets/notes/Research, history backfill, task snapshots/heads, semantic extraction/summary, index manifests/vectors, provider/tool/SSE executions, Research bindings/releases, UI and private-context injection. Those remain required later; this subset is not Issue41 completion. It does not authorize changing scope ownership to fit existing workspace-readable output.

R3/R4/R8 and the instruction-only portions of R5/R9/R10 need a corrected, independently reviewed P1a contract before its implementation. Remaining findings block their respective later slices. No need to finish unrelated provider or Research runtime code to prove this bounded core.

## Evidence-scoped decision

| Area | Status | Basis / limit |
| --- | --- | --- |
| Earlier-scope coverage and effective-spec alignment | **pass for prior scope only; spec v3 §12 blocked** | Existing coverage retained; mandatory same-run compaction gaps are R11–R16 in the supplement. |
| Integrated design and full M1–M4 approval | **blocked** | R2–R10 require implementable contract corrections; R1 requires later runtime verification. |
| A1 private output expansion | **blocked — authorization pending** | Already escalated; do not activate private reuse or write its native schema contract yet. |
| A2 and numerical engineering defaults | **controller decision** | A2 supports original scope; A3–A7 are reviewable engineering decisions, not new per-number user gates. |
| P1a independent storage subset | **feasible, not yet implementation-authorized** | Bounded scope above; corrected narrow design and #40 handoff still required. |
| Implementation/DDL/migration/runtime/security/UI/model quality | **blocked / unrun** | Source/design inspection only; no passing tests, deployed behavior or model-quality claim. |
| Sharing/raw archive deletion/evidence expansion | **not applicable** | Outside scope, no permission fallback. |

## Review identity and write-back

Reviewed design SHA-256: `E6AE3615CD173B34B136624EA450FA4D5038329ABD3076F5990C4C0155F8E498` (896 lines, including §§17.7–17.8 and revision-status addition). The earlier 876-line snapshot was superseded during review; findings were narrowed against the final snapshot.
Effective spec SHA-256: `1D97EDACCAD610530A7D90F79FB749B0F4543278929ADD3E8C676ADA7CA51FFC`.
Inventory SHA-256: `71DC3D70E0E4FC20F64F226163A2F0F460EF7B79A8F5504D7B46B2347E942377`.

Relevant code cross-checks: `services/chat.py`, chat schema/SSE parser and BFF; neutral `research_run.py`, `research_execution.py`; research-persistence `lease.py`, `tools.py`, `provider.py`, `completion.py`; current Alembic `s3a4b5c6d7e8` predecessor. Existing provider matcher helper has a legacy `True` fallback when no resolver is supplied, while reserve requires a matcher: the new paths must require injected authorization/config validation and must not reuse a permissive fallback.

Durable findings are stored only in this review and the owned oracle update. No private/profile memory or shared workbench write; no product code authored. Runtime gates remain in `design-oracles.md`; this report does not repeat or supersede their real-evidence requirements.

## Requirement update — automatic same-run compaction (2026-09-28)

**Integrated design remains NOT ACCEPTED.** This bounded supplement adds R11–R16; it preserves R2–R10 pending the original developer's rework, the design-level R1 closure, the A1 audience gate and the #40 handoff gate. The prior “full-goal coverage” assessment applies to the earlier requirement snapshot; effective spec v3 §12 coverage is now **blocked**.

Read the entire external proposal v2 (419 lines), including complete §12. Read effective repository spec v3; its complete §12 matches the proposal text. External §§3/6/7 retain some older candidate terminology; external §11, effective repo §§6–7/11 and the latest explicit authorization continue to prohibit ambiguous long-term candidates. Task-local uncertainty and candidate compaction summaries are distinct from long-term admission.

Review identity for this supplement: design `313AAC4B7820422DC1ED3F1E5D922D52320867BF93AB853AB573358081ECBA44` (898 lines); spec v3 `6097FDB5BF494A5754D4DF3593774FECFE235ED47F40BDFAE604CB61257E6713`; external proposal v2 `2CDCC439805FAFB630C59F2F73E6C75A41E4D12AC6467CFD608780122F844967`. Only source/document inspection; no implementation or runtime acceptance.

### R11 — P1: no mandatory every-dispatch gate or hysteresis contract

**New requirement §§12.1–12.2; design §§8.1–8.2, 9.3, 10.1.** Current triggers concern completed old prefixes, phase completion and changed goals. Packing shares and “four incremental updates before rebuild” do not define an automatic soft trigger and lower target. The loop has no compulsory gate before first send, each tool continuation, role change and resumed send.

**Correction:** define one neutral pre-main-dispatch contract invoked at all those points, after the next complete input is assembled and before call admission/send. Record model/counter/policy identity, safe hard input ceiling, trigger and lower target; require target < trigger <= hard ceiling and sufficient newly compactable work for repeat compaction. Recount the complete rebuilt request including tools/protocol/output reserve. Persist or reproducibly derive no-gain suppression keyed to the same input boundary/policy, so an unchanged boundary cannot spin. Successful compaction returns the next request to the running loop without new user input. Do not replace context inside an already-streaming call. Defaults remain controller-owned engineering choices.

### R12 — P1: snapshot-head CAS does not atomically switch active execution context

**New §12.4; design §§4.4, 5.1, 8.2, 17.1.** The existing immutable summary/head CAS is useful, but no transaction binds its adoption to the active chat/Research context version, journal frontier, cancellation/lease and next-dispatch pointer. Checkpoint metadata also lacks a complete specified before/after count and counter/profile binding. Two compactions or a new message/tool result can leave a valid historical snapshot that is stale for the live execution.

**Correction:** specify one atomic adoption command owned by #42, with #43 defining its semantics: immutable candidate/checkpoint + exact coverage/source/group manifest + expected parent/context version + counted next-input fingerprint; atomically CAS the execution's active-context reference after guarded source/audience/lease/cancel checks. Store or link policy/model/counter versions, count provenance, before/after measures and stable operation identity. Nothing advances coverage/pointer before commit. On conflict reject or boundedly rebuild; retain any newer tail only under a proved coverage policy. Reuse existing snapshot/journal mechanisms where feasible. #43 must not implement a second independent pointer update after a #42 commit.

### R13 — P1: whole completed-assistant units cannot handle growing in-flight tool history

**New §12.3; design §§4.4, 4.6, 8.1–8.3, 9.3, 17.5.** §8.1 defines a unit as user plus completed assistant answer; a single running answer can accumulate many completed tool rounds before that answer exists. Pairing individual call/results is also insufficient for a provider turn that emitted a parallel group whose other results are still pending. Current snapshot schema does not explicitly encode failed attempts and pending operational state required by §12.3.

**Correction:** define immutable journal-level complete interaction units/group IDs for the running answer, preserving native provider call IDs, ordered results and terminal failures. A parallel group is indivisible until all members have a contract-valid result/terminal outcome; no main continuation with a partial group. Keep pending group/execution state outside generated factual claims. Preserve failure history as attributed status, not a successful fact or instruction. Archive oversized raw tool results durably before replacing them with bounded source refs; state byte/resource ceilings, retention/deletion dependencies and failure behavior if archive cannot commit. Do not let the 1 MiB transport/journal limit become silent raw-result truncation. Original messages/evidence are not deleted by compaction.

### R14 — P1: summarizer path, chunk limits and no-gain outcomes are unspecified

**New §§12.5–12.6; design §§8.2–8.3, 9.3–9.4.** Rebuilding from raw sources may exceed the summarizer's own context. No bounded nonrecursive chunk-and-merge path or candidate acceptance/no-gain transition is defined. Existing summary failure handling preserves the old boundary, but does not specify automatic safe continuation or bounded retry suppression under repeated soft-threshold checks.

**Correction:** introduce an explicitly separate summary-call path that cannot call the main compaction gate recursively. Partition complete source units; bound chunk input/output, chunk count, merge depth/calls, elapsed time and total resource reservations, including the case where the merge itself cannot fit. Recount before adoption. Publish a finite transition table for valid gain/target reached, insufficient gain, invalid candidate, no compactable history, temporary failure, unknown external outcome and still-over-hard-limit. If old authorized context still fits the hard ceiling, bounded automatic continuation may use it without changing the checkpoint. Otherwise stop with a specific recoverable error after bounded work. Never adopt empty/invalid summaries, silently lose mandatory data or automatically resend an uncertain summary call.

### R15 — P1: repeated compactions need same-execution versions and continuous budgets

**New §12.5 and §12.8(2,4–6); design §§9.3–9.4, 10.2, 17.3; extends R6.** The single immutable Research binding per Attempt has no versioned active compaction chain, and the design does not connect summary work/chunking with main-loop continuation accounting and replay position. Ordinary compaction must not be implemented by the existing explicit retry/new-Attempt path, a budget reinitialization or replay of the whole handler.

**Correction:** keep run/step/Attempt and native evidence/side-effect state unchanged for healthy automatic compaction; version only context/checkpoint/per-call manifests. Show two compactions inside one live Research Attempt plus dispatch through a role change using the role's native identity. Compaction and chunk calls consume bounded allowances under the same parent cumulative ledger/deadline; never reset call ordinal, final-answer reservation, cancellation, preconditions or publication idempotency. Resume from committed context and settled tool results; never repeat completed side effects/publication. Crash recovery must distinguish precommit candidates, committed checkpoint/not-yet-sent next request, and sent-but-unknown calls. Preserve native lease-expiry rules: compaction cannot revive a terminal Attempt; record genuine native lease recovery separately from compaction, rather than claiming a new Attempt is same-Attempt continuation. Existing source-invalid/replan gates do not become a routine compaction path.

### R16 — P1: acceptance lacks same-run traces and durable automatic-progress recovery

**New §§12.7–12.8; design §§12.3, 14, 17.8.** Existing long-conversation walkthrough and generic “summarizing” event do not demonstrate compaction within one submitted task, two Research threshold crossings, no-input continuation, crash-point adoption or refreshed current compaction state.

**Correction:** add acceptance cases CO01–CO12 and O22–O30 in the oracle supplement. Persist/project enough operation/checkpoint progress to recover after refresh/disconnect; transient SSE alone is insufficient. Automatic success resumes the task without a Continue action; hard failure is understandable and recoverable. Engineering traces must correlate execution/step/Attempt, role, call/group IDs, context versions/frontiers, before/after counts and count source, budget deltas, cancellation, compaction reason/result and publication identity, without sensitive text. Semantic fidelity and real visible UI each retain their own gate; scripted models cannot accept either real model quality or usability.

### Ownership, co-location and merge order

- **#42:** atomic storage/adoption/CAS, immutable checkpoint/coverage/dependency primitives and idempotency. #43 co-defines the exact contract before its migration is fixed. Existing narrow P1a remains a safe conditional subset; it does not provide or accept these compaction primitives.
- **#43:** neutral pre-dispatch policy, hysteresis, checkpoint construction/adoption orchestration, bounded nonrecursive summarizer, failure/no-gain state and deterministic fixtures. Keep count/recount/adoption semantics cohesive; do not create another scheduler or general checkpoint framework.
- **#44:** invoke that gate on every chat send/continuation, complete group journal/archive integration, same-execution loop/cancel/recovery and SSE. Its neutral provider foundation (R2) must be available before #43's shared summarizer uses real adapters; land that prerequisite separately or co-locate it by controller assignment.
- **#45:** invoke the same gate at Research dispatch/role/resume boundaries, version context within existing native identities and ledgers, repeated-compaction/recovery and evidence/publication parity. Extend native recovery within its owner rather than duplicating it in #43.
- **#46:** visible automatic-compaction progress, uninterrupted continuation, hard-failure and refresh/reconnect walkthroughs for chat and Research.

Required order is approved shared contract → #42 atomic primitives + neutral provider prerequisites → #43 policy/summarizer → #44/#45 integrations → #46 cross-layer acceptance. Cohesive cross-layer PRs may be controller-assigned where splitting would expose half an atomic protocol; implementation remains ownership-bounded. Do not merge pointer/coverage adoption halves as independently usable behavior. A1 and #40 gates are unchanged.

**Updated disposition:** R2–R10 remain open; R11–R16 add six P1 requirement-compliance gaps. No new P0 is asserted by this bounded update. Requirement/oracle mapping is complete at document scope; current §12 design acceptance, engineering execution, semantic quality and visible UI are **blocked/unrun**. No paid model evaluation or product/service/branch work was performed. Write-back is confined to these existing reviewer artifacts.

## Stable consolidated candidate — independent re-review, 2026-09-28

### Findings first

**R4 — P1, OPEN (narrowed): the erasure shape still retains proposition-bearing conditions.** Current `design.md` **§4.3 lines 130–143, §5.3 line 218, §5.5 lines 226–234, §12.1 lines 545–553**. `memory_revisions.conditions` is required JSON containing free-text `subject` and `applicability` (up to 2000 characters). Delete clears only `content/content_sha256` on every revision; the named revision erasure trigger explicitly allows only `content/hash/erased_at` changes. Consequently a condition such as `{subject:"Project Cedar",applicability:"only the private acquisition environment uses account 7412",effectiveFrom:null}` survives the advertised synchronous DB byte erasure. A tombstone/read filter suppresses retrieval but does not make those retained semantic fields content-free. There is no declared need or authorization to retain this second copy of the deleted proposition.

**Implementable correction (bounded, no extra table/job):**

1. Treat `conditions` as erasable semantic payload. Define one live/erased revision CHECK: live has validated conditions and content/hash; erased has `conditions IS NULL`, `content IS NULL`, `content_sha256 IS NULL`, and `erased_at IS NOT NULL`. Make the column nullable only for that erased branch. Do not substitute an empty object that pretends to be valid conditions.
2. Permit exactly this monotonic clearing in `revision_erasure_monotonic`; retain immutable identity/version/intent/provenance/support metadata. Clear conditions across **all** revisions in the existing P1a delete transaction. Keep support/FKs/idempotency identities; do not erase native original archives or another live record's legitimate source.
3. Extend F09 with a unique synthetic marker present **only in conditions**, plus historical revisions. Assert its absence from P1a-owned persisted semantic payloads after delete/commit, while retained support constraints, history denial and request replay still work. Direct SQL must reject erased rows retaining conditions, live rows missing conditions and erased-to-live restoration. Later consumers must inventory their own content-bearing JSON/request/result objects under the same erasure policy; do not label arbitrary free-text JSON as audit metadata.

The original instruction CHECK and reference-safe TTL defects are repaired. R4 stays open solely for the residual shape above. This affects both the integrated design and P1a; it does not require reopening any approved persistence rule. **P0: 0 identified; P1: 1 open.** No other blocking defect was identified in this exact candidate at design scope.

### Prior-finding disposition (operative contracts inspected)

“Closed” below means **closed at design level only**; it never means implemented or race-tested. Current section references replace the old snapshot's numbering.

| Finding | Disposition | Operative basis / residual obligation |
|---|---|---|
| R2 | Closed, design-only | §2 lines 25–50 and §12.2 M3a put actual protocol/counting implementations in neutral `citeframe_memory.adapters`, one DTO/port owner in `citeframe_contracts.memory`, injected composition and app-unavailable import smoke before #43 use. Implementation graph still unproven. |
| R3 | Closed, design-only | §4.3 separates immutable revision intent/validity, sole current head, expiry predicate and explicit CAS interleavings; recompute copies latest inactive/superseded intent and cannot resurrect deletion. |
| R4 | **Open, narrowed P1** | §§4.2/5.5 repair erased instructions and reference-safe purge; revision conditions remain outside the erasure discriminator/trigger. Apply the three corrections above. |
| R5 | Closed, design-only | §4.4 records direct revision/snapshot/tool dependencies plus raw leaves; checks head/use mode, rejects disabled/superseded contribution laundering and invalidates old consumers before surviving-source rebuild. |
| R6 | Closed, design-only | §§6.2–6.3/10 specify immutable Attempt base plus evolving per-call manifests, locked cumulative fold, unique native call link and atomic settlement; planner cap defaults to zero for old releases. |
| R7 | Closed, design-only | §§7.1–7.3 define strict mode2 `none`, explicit history envelope, actor-bound pre-meta request lookup/replay, child retry identity/root budget, provenance/ranges and exact failure distinctions; mode1 assets/citations remain separate. |
| R8 | Closed, design-only | §5.1 binds confirmation to the actual action/proposition/span. Material change needs a new action; corpus evaluation cannot confer confirmation. Observations and Research uncertainty remain correctly attributed. |
| R9 | Closed, design-only | §12 stages six-table P1a, delayed cyclic FKs/predicates, M3a before summary use, co-owned M3b atomic adoption and M5 after A1. Explicit old-binary fence and populated downgrade refusal replace unsafe flag-only assumptions. R4 independently blocks P1a erasure approval. |
| R10 | Closed, design-only | §§3.3/5.4 distinguish exact server-issued invalidate/erase authority from user-content permission; revocation/archive cannot strand maintenance or grant recompute/read/model authority. P1a is synchronous DB-only. |
| R11 | Closed, design-only | §§8.1/8.3/9.3/10.1 require every-main-dispatch gate, true capacity/counter provenance, lower-target hysteresis and durable unchanged-frontier suppression. |
| R12 | Closed, design-only | §§6.1/8.5/10.2 make checkpoint, exact coverage/direct uses and native live pointer/contextVersion one #42-owned transaction, with source/head/leaf/lease/cancel CAS; no second pointer commit in #43. |
| R13 | Closed, design-only | §§6.2/8.2 support complete journal groups inside an unfinished answer, terminal failures, no partial parallel group, full verified oversized-result archive before bounded refs and finite archive failure. |
| R14 | Closed, design-only | §§8.3–8.6 give independent nonrecursive counted chunk/merge calls, finite fan-in/call/time budgets, lower-target adoption, no-gain/invalid/unknown dispositions and safe-original continuation versus over-hard stop. |
| R15 | Closed, design-only | §§6.3/8.5–8.6/10 preserve native identities, settled tools/publication, continuous budgets/deadline and unknown reservations; require two checkpoints in one live Attempt and distinguish native lease recovery. |
| R16 | Closed, design-only | §§9.4/11/13 define durable refresh/progress, automatic no-input continuation, actionable failures and correlated per-dispatch evidence; engineering, semantic quality and real browser gates stay separate. |

R1 remains closed at design level: §5.2 preserves conflicting source/member guards through bounded read/enqueue/dispatch authorization and final adoption commit. Actual PostgreSQL/runtime barriers remain mandatory; no new permission fallback is accepted.
### Integrated contract and minimality judgment

The consolidated design covers the full four-layer/chat/Research goal and spec v3 §12, subject to R4 and the existing A1 activation gate. In particular, §8.5 binds exact complete-unit coverage and checkpoint to the live context CAS; §§8.2/8.4 separate indivisible group adoption from bounded raw-body slicing; §8.6 explicitly covers generation, precommit, unknown acknowledgement, committed-before-send, cancellation/source revocation and native lease expiry. §§6.3/10 retain budget ownership and business checkpoint/publication identity. C02 requires **two committed compactions in one live Attempt**, then separately checks native role/resume dispatches; C05/C06/C10 cover crash and invalidation races. These are implementable design contracts, not observed successful executions.

The simplification requests were materially adopted: six P1a tables, no jobs/outbox without async resources, no extra chat branch identity or task-head table, one typed use relation, native Research ledgers with deterministic folds, and no planner reservation table or generic scheduler. Keep those boundaries. The remaining cross-row support/erasure predicates have an explicit invariant and are justified; ordinary composite FKs/unique constraints handle scope/identity. No additional schema layer is required to fix R4. Fixed operational numbers are controller-tunable engineering defaults, not user-blocking questions.

**Neutrality checked against actual baseline:** `apps/worker/src/ai_pdf_worker/research/adapters/generation.py` lines 5–24 still import API observability/providers/context policy/agent IO; `_ensure_provider` lines 62–68 imports API workspace-model resolution. The proposed `packages/memory-service` does **not yet exist**. Therefore this review accepts only the new design's explicit neutral ownership/import graph, not a claim that the current application graph is neutral. #44's prerequisite must inject the shared implementation rather than use the existing API provider factory for new memory/summary paths. App-unavailable import smoke, dependency/lock/deploy updates and both-root class-identity checks remain required; legacy coupling need not be wholesale refactored.

Source spot-checks also confirmed native Attempt status/lease/checkpoint ownership in `packages/backend-persistence/src/citeframe_persistence/models/research_execution.py`, the actual generation packing/hash/reservation/send seam, planning ledger defaults in `citeframe_research_persistence/lease.py`, and execution-only checkpoint construction in `completion.py`. No test, migration or service was run. Exact-source availability, corrected-decision precedence, frozen evidence, source deletion before cleanup and no ambiguous inferred confirmation remain operative requirements rather than presumed runtime properties.

### Evidence-scoped disposition and exact next slice

| Scope | Status | Meaning |
|---|---|---|
| Goal/spec v3/full external v2 coverage and independent re-review | **pass — static scope** | Full consolidated design/inventory inspected, previous findings individually adjudicated; external stale candidate wording does not override effective admission rules. |
| Integrated design | **blocked — bounded R4 correction** | All other prior findings closed design-only. A1 branch remains conditional and unapproved; full private-output implementation/activation cannot be accepted. |
| #42 P1a design eligibility | **blocked — same R4 correction only** | The instruction-only slice and dependency order are otherwise suitable and A1-independent. No broad schema redesign requested. |
| Product implementation authorization now | **blocked** | No #40 handoff or controller go-ahead. Controller reports PR47 product independent ACCEPT/core six green at `5903d60b`, with external image401 merge hold; this lane did not re-verify CI. |
| T/M/R implementation, PostgreSQL/migration/race/recovery, import/provider/tool/SSE | **blocked / unrun** | Design closure and Issue40 checks establish none of this Issue41 evidence. |
| Q real-model semantic quality | **blocked / unrun** | Synthetic deterministic streams are mechanics fixtures; no paid evaluation and no actual local-model quality evidence. |
| U visible browser | **blocked / unrun** | Require ordinary chat/Research entry, same-submission compaction/progress, failure/cancel/refresh and server-trace correlation; no UI acceptance from documents. |
| New sharing, raw archive deletion, evidence permission expansion | **not applicable / excluded** | No authorization inferred. |

**Allowed now:** original developer may make the bounded R4 design correction in its owned documents when directed by controller; this reviewer has changed only review files. No product/service/branch work follows this review.

**Eligible after that correction is independently checked, exact #40 handoff and controller authorization:** #42 P1a only—neutral contracts/model exports/manual-instruction commands plus one additive migration for `memory_instructions`, instruction-only `memory_sources`, workspace-private `memory_records`/`memory_revisions`, revision→source `memory_uses`, and `memory_operations`; create/read/history/correct/deactivate/delete with CAS/support/idempotency and synchronous semantic-byte erasure, plus bounded deterministic/PostgreSQL/import tests. No mounted route/UI, provider/model/index/job/backfill/native-source hook, checkpoint, Research binding or A1-dependent audience schema. Thus P1a cannot prematurely commit to private thread/run ownership.

Later merge order in §§12/14 is accepted at design scope: neutral #44 protocol/count/journal prerequisite before #43; #42 atomic storage co-designed with #43 before schema freeze; #44/#45 invoke the gate and native recovery; #46 verifies visible experience. Do not split checkpoint/coverage/live-pointer adoption into separately usable commits. A1 and #40 gates remain unchanged.

### Stable artifact identity and reviewer completion

Source-inspection HEAD: `5903d60b7103d32d7d8a0c173691250407460b13`; branch `refactor/workspace-access-dependencies`. Final read-only verification observed concurrent HEAD `1b9e1168c2c2b1548febc1fcb5997d4310bfe511` (latest commit normalizes endings in two Issue40 documents); this reviewer made no Git-state change and infers no handoff or CI resolution. Candidate SHA-256 values were unchanged across inspection:

| Artifact | SHA-256 |
|---|---|
| `design.md` (715 lines) | `069DE6DA37D5C57FAF8C7CB7B1C77679B1A9F819D85483351E2BC61699C12C07` |
| `spec.md` v3 (419 lines) | `6097FDB5BF494A5754D4DF3593774FECFE235ED47F40BDFAE604CB61257E6713` |
| `code-inventory.md` (156 lines) | `B64CE2486733285D2740E60389ADA1A9720CB35A60AE85B2BF12EEA6E6881B25` |
| External proposal v2 (419 lines) | `2CDCC439805FAFB630C59F2F73E6C75A41E4D12AC6467CFD608780122F844967` |

Full external proposal was read in the prior phase and rechecked against the effective spec; complete §12 remains identical. This re-review inspected the complete current 715-line design and 156-line inventory, not only §15's developer resolution claims. Earlier review sections retain historical evidence and are superseded only for the dispositions stated here.

Reviewer lane complete: **no required reviewer work continues in the background**. R4 correction and subsequent targeted approval are handed back to controller/original developer; a further review requires a new request/candidate. Write-back check: durable results are confined to these two owned review artifacts; no private/global memory or shared workbench changes, no product/test edits, migration execution, model calls, service or Git-state changes.
## Final targeted R4 verification — 2026-09-28

**Result: R4 CLOSED at design level. No new issue found in the bounded correction.** This check is limited to the seven operative replacements below; it carries forward the prior independent closures of R1–R3/R5–R16 without reopening or claiming to rerun the broader review.

Verified actual `design.md` SHA-256 before inspection: `D0F38DCC2B34B4F1F8D9F55372EC79551D057A44AE3BF368784E14ACAF3EE01B`.

| Replacement | Actual contract inspected | Result |
|---|---|---|
| §4.3 line 135 | `conditions J?` permits storage of erased SQL NULL | Pass, design-only |
| §4.3 line 143 | Live requires valid non-NULL conditions and content/hash; erased requires conditions/content/hash ALL SQL NULL and erased_at set; empty object is invalid | Pass, design-only |
| §5.3 line 218 | Synchronous delete clears all three fields on ALL historical and newly appended deleted revisions in the same transaction; identity/support/FKs/CAS/idempotency survive | Pass, design-only |
| §5.5 line 230 | Erasure explicitly includes conditions and later owned content-bearing JSON/request/result copies; native archive retention remains unchanged | Pass, design-only |
| §12.1 line 553 | Exact monotonic live→erased transition, all other fields unchanged; already-erased rows cannot restore payload or change erased_at | Pass, design-only |
| F09/ER01 line 602 | Conditions-only marker across revisions, physical payload inspection, denied history/replay, retained support integrity; direct SQL rejects missing/malformed live conditions, retained erased payload and resurrection | Pass, test specification only |
| §15 R4 line 680 | Resolution mapping accurately names the repaired CHECK, all-revision clearing and negative tests | Pass, mapping only; closure follows the operative clauses above |

§5.4's narrow lifecycle authority and §5.5's reference-safe cleanup remain consistent with the correction. The new erased branch preserves existing content-free metadata and adds no table, job, permission fallback or native archive deletion. No runtime, PostgreSQL, fixture or model test was executed; F09/ER01 is an acceptance requirement, not a test result.

### Final scoped disposition

| Scope | Disposition |
|---|---|
| R4 correction / prior R1–R16 design findings | **Pass at design scope; all closed.** No open P0/P1 design finding remains from this review. |
| Integrated design | **Conditionally accepted at design level.** The previously reviewed contracts plus this repair meet the governing design requirements. A1-dependent audience changes remain an unapproved proposal and cannot be implemented/activated by this acceptance. Prior merge-order, atomicity and evidence obligations remain in force. |
| #42 P1a | **Design-eligible, A1-independent.** Exact allowed subset below; no further R4 design correction required. |
| Product permission now | **Blocked.** #40 is not merged/handed off and controller has not authorized product work. |
| Issue41 T/M/R, real-model Q, visible-browser U | **Blocked/unrun.** Design acceptance does not establish implementation, race safety, semantic quality or usability. |
| New sharing/raw archive deletion/evidence-permission expansion | **Not applicable/excluded.** |

**Exact P1a eligibility:** neutral contracts/model exports/manual instruction commands and one additive migration for `memory_instructions`, instruction-only `memory_sources`, workspace-private `memory_records`/`memory_revisions`, revision→source `memory_uses` and `memory_operations`; fail-closed injected access, create/read/history/correct/deactivate/delete, CAS/support/idempotency and synchronous all-revision semantic-payload erasure, with bounded deterministic/PostgreSQL/import verification. No mounted API/UI, provider/model/index/job/backfill/native-source hook, task checkpoint, Research binding or A1-dependent audience schema. Implementation still requires exact #40 handoff, revalidated migration head/ownership and controller go-ahead.

**Controller-reported #40 gate (not independently rerun here):** exact HEAD `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`, all six core CI checks green and independent ACCEPT; three runtime checks remain blocked by unauthorized pinned MinIO server/mc image pulls. Main remains `8812fda`; no merge/handoff. This supersedes older CI summaries without weakening the gate. A1 remains unapproved.

**Reviewer lane complete; no required reviewer work is active.** Only the two owned review artifacts were updated. No product/test/service/Git/profile/shared-workbench modification, migration or model evaluation. Write-back is confined to these review records.