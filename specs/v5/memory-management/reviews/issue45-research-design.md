# Issue45 Research — independent Critical design review

Date: 2026-09-28 (Asia/Shanghai)
Latest disposition: **BOUNDED DESIGN APPROVE — candidate 249C97FD closes F45-1-R1 and F45-4-R1; see final targeted re-review below. No native-key/schema/ABI implementation or runtime acceptance is granted.** Earlier findings and dispositions follow as history.

Reviewed candidate: `specs/v5/memory-management/lanes/issue45-research.md`, complete file, SHA-256 **A8212B018FD36D7D972C2D732D5F78C61EACE553148A91FAC97D6CE301726CAD**.

This is a replacement independent review under #41. Per the controller handoff, original reviewer `agt_1e53da00` failed twice with `PROVIDER_EXECUTION_ERROR` and produced no artifact. That is a documented availability deficit; this review does not supersede an adverse review or constitute review shopping. The controller owns relay to original developer `agt_af167b31`. No developer was contacted or replaced by this reviewer.

## Findings, ordered by severity

### F45-1 — P1: the journal source contract requires native UUIDs that do not exist

**Candidate:** §5, line 80 (`research_journal` tagged version and “native_id is real native row/artifact UUID”).

**Actual contracts:**

- `packages/backend-persistence/src/citeframe_persistence/models/research_adaptive_turn.py:13–20`: primary key is `(step_id, turn_number)`; no row UUID. The row records `created_by_attempt_id`, query, request/result hashes and result JSON.
- `models/research_conflict_turn.py:23–40`: primary key is `(step_id, operation_number)`; no row UUID. Phase and request/result hashes are separate attributes.
- `packages/research-persistence/src/citeframe_research_persistence/adaptive_turns.py::adaptive_turn`: the initial request check creates no row when result is absent. A committed row stores the result and request hash, not the original full request JSON. Conflict journals do store request JSON and started/succeeded state.
- Current #43 `models/memory.py:53–69` has `native_id varchar(36)`, unique `(workspace_id,kind,native_id,source_version)` and one current source per `(workspace_id,kind,native_id)`. `register_source` treats another version of the same native ID as replacement and marks the prior source stale.

The proposed `nativeRecordId`/`nativePhase` fields do not identify either composite key. Substituting `step_id` would collapse several independent turns/operations into one source identity; registering the next turn as its next version would invalidate still-required earlier history. Fabricating a row UUID would contradict the candidate's own native-identity rule. The adaptive request cannot be read back from a nonexistent native request-body column.

**Required correction / owner:** original #45 developer specifies tagged locators with the actual `(stepId,turnNumber)` and `(stepId,operationNumber)` identities, original producing Attempt versus current consuming Attempt, phase/status and exact request/result hash semantics; artifact sources retain actual artifact UUIDs. State precisely which body comes from a native committed result and which comes from the authorized per-call request archive. #43/source-schema owner, coordinated with #42, must approve the registry identity/current-version/uniqueness representation and resolver ABI that can retain multiple such sources concurrently. No provider-tool IDs, fake journal UUIDs, generic transcript table or timestamp-as-version shortcut.

**Acceptance discriminator:** two adaptive turns and two conflict operations from the same Step remain independently addressable/current; selecting or compacting the later record does not invalidate or replace the earlier one. Retry can reference an eligible earlier producer without relabeling its Attempt. Wrong turn/operation/phase/hash and uncommitted result fail. The exact adaptive sent request is recovered only from an explicitly bound durable request object, never reconstructed and called original evidence.

### F45-2 — P1: the frozen policy has no complete approved native hash/write/read/transaction binding

**Candidate:** §6.1–3, lines 88–90, and §7, lines 100–102.

The candidate requires full-wrapper fingerprint pinning and checks at capture/reserve/adopt/send. It lists new columns and a proposed manifest projection, but does not define the native approval/hash change that makes those values frozen. Its listed projection also has no explicit full-wrapper fingerprint field. The #43 compaction-policy hash covers only the smaller cumulative policy, so it cannot establish `allowedHistoryScope`, allowed kinds/tools, packing/counter or tool-budget authority by itself.

**Actual contracts:**

- `packages/research-persistence/src/citeframe_research_persistence/snapshot_integrity.py:71–229` constructs the canonical planning, proposed-execution and persisted-execution hash payloads. These payloads currently have neither `memory_policy_json` nor `planning_max_tool_calls`. `execution_snapshot_provenance_is_valid` compares these source/persisted payloads and their native approval graph.
- `apps/api/src/ai_pdf_api/services/research/research_runs.py:131–189` creates and hashes the plan revision; `research_plan_approval.py:207–232` verifies the approved plan and creates the execution snapshot. These are essential frozen-write owners, absent from the candidate's exact delta/file slice table.
- #43 `compaction/guards.py::_research` ends with `self.policy = None`; `repository.py::_capture` compares caller policy to native policy only when the latter exists. The current `CapturedContext` DTO has a compaction `policy_fingerprint` and opaque native-manifest string, with no specified validated Research binding extension. `CallJournal.reserve` compares the compaction fingerprint across the phase ledger.

Adding the columns and Worker projection alone leaves a validly shaped changed native memory policy outside the existing approved snapshot hash. A first-call fingerprint can faithfully record such a changed policy without proving it was authorized at native freeze. This is an unclosed design contract, not an assertion that an enabled production path already leaks data.

**Required correction / owner:** #45/native snapshot owners specify versioned canonical payload additions at plan creation, approval and persisted snapshot reconstruction; planning policy and execution policy must each acquire their deadline once at the declared phase boundary and preserve it across retries. Preserve byte-identical old-release hash semantics when disabled. #42 approves the shared execution/planning DTO and converters. #43 owns a concrete transaction-neutral binding/resolver ABI that derives authoritative policy and permitted role/operation from locked native rows, includes the full-wrapper fingerprint in captured/per-call context, and rechecks it at every content admission/adoption/send boundary. Define native frozen provider fingerprint versus neutral connection fingerprint explicitly; the native reservation requires its existing provider/model/fingerprint tuple and mandatory capability matcher. No wrapper may commit or roll back the journal's Session.

**Acceptance discriminator:** mutate only history scope, allowed tools, planner cap, packing/counter or connection metadata in otherwise well-formed rows; reject before any source/body read, reservation or send, including before the first call and after restart. Compare approved-source and persisted enabled payloads. Old NULL-policy fixtures retain their original hashes/zero planner tools. Race mutation/revoke/cancel against the actual native transaction, not an in-memory precheck.

### F45-3 — P1: upstream role authorization still lacks an exact resolver and database predicate contract

**Candidate:** §3 “Native Research sources”, §5 “Cross-role”, and §6 source-owner handoff. The stated native dependency and permitted-handle rules are appropriate, but not yet a freezeable authorization mapping.

**Actual contracts:**

- #43 `compaction/sources.py:24–28` requires `handle.owner_step_id == current Step.id`.
- The shipped-candidate migration `u5c6d7e8f9a0_inloop_compaction.py:261–265`, function `compaction_source_scope`, repeats same-step evidence ownership in SQL. Snapshot coverage/dependency integrity calls that predicate. Changing only a Python resolver will still reject lawful upstream-role adoption; loosening that predicate to same-run would admit more than the native role input.
- Worker `handlers.py:256–284` passes completed branch claims and original evidence to the verifier. Its immediate predecessor is `join`, while the evidence handles belong to researcher Steps. API `research_worker_state.py:89–120` binds claim evidence to the actual producing researcher Step; `load_step_handler_input:301–318` separately checks direct dependencies. Direct-predecessor equality alone cannot authorize these handles.
- `conflict_investigation.py:105–115` runs a nested verifier under the investigation/gate lease. A role-to-Step-kind equality check would reject this legitimate call; trusting a caller's `role` string would not establish authority.

**Required correction / owner:** #45 supplies an explicit matrix for planner, researcher, top-level verifier, critic, investigator, nested verifier/critic and synthesizer: accepted workflow/Step/operation phase, exact claim/handle selection, producing Step/Attempt and completed dependency path, plus current frozen asset/generation/index/fingerprint checks. #43 implements the corresponding transaction-neutral resolver and coordinated SQL source-scope/use/coverage predicates under its single adoption owner. The matrix must cover direct calls as well as inherited checkpoint/journal reads. Public `read_source` stays denied for internal evidence; shared history never issues citation handles or gains authority by matching a run ID.

**Acceptance discriminator:** lawful verifier access to researcher evidence and lawful nested-verifier access succeed without cloning handles. An unrelated branch, omitted claim, wrong workflow/phase, noncompleted predecessor, stale source generation or forged same-run handle fails before body admission and before atomic adoption. Exercise both resolver and real database predicate paths. No new output permissions are needed.

### F45-4 — P1: planner-tool accounting/reclaim is omitted from the proposed integration slice

**Candidate:** §6.4, §7 and 45c (lines 91, 102–115, 124).

The candidate enables planner tools through #43 sidecars and the existing planning ledger, but gives only a general reservation/settlement requirement. It does not assign the planner-sidecar reclaim hook, define tool-specific terminal transitions, or state which rows count toward provider-call versus tool budgets.

**Actual contracts:**

- `packages/research-persistence/src/citeframe_research_persistence/state.py::reclaim_expired_research_steps` locates only `ResearchProviderCall` and execution `ResearchToolCall` rows (lines 172–225), reconciles those ledgers, then abandons the Attempt (lines 333–349). A planning tool stored only in `memory_calls` is invisible to it. The candidate's file ownership table does not include `state.py`.
- `tools.py::begin_tool_call` requires an execution snapshot and researcher/investigation Step; `complete_tool_call` rolls the Session back on callback failure. It cannot be passed unchanged as a transaction-neutral shared sidecar callback for every role or for planning.
- Current #43 `NativeAccounting` supplies provider reserve/send/reconcile only. `CallJournal.reserve` admits provider purposes only; its current `billed` fold includes all rows except `no_dispatch`, including archive `tool_group` metadata. The candidate correctly says archive metadata must not be billed as provider calls, but the exact purpose-specific fold/tool ABI remains open.
- Approved `design.md §10.3` explicitly requires reclaim to settle planner-sidecar reservations before declaring the Attempt reconciled.

**Required correction / owner:** #45/native persistence owner owns a bounded `state.py`/tool-command change; #43 owns sidecar commands and atomic fold integration. Specify batch allowance reservation, individual result/terminal identity, planner versus execution ledger linkage, one charge/release, and reclaim/cancel/revoke races. Existing native tool/provider arithmetic remains authoritative. Define provider-call counts, tool counts, summary counts, result-token consumption and archive-only records separately. Account for completed native evidence tools across roles/Attempts without rebilling them. Tool callback failure must propagate to the one transaction owner; no nested commit/rollback. This needs an explicit ownership transfer and review before tool activation.

**Acceptance discriminator:** reserve a planner tool batch, expire/cancel before and after a result, then reclaim and retry. No stranded reservation, double increment/refund, auto-reexecution of a completed tool or budget reset. Reclaim-first and completion-first yield one durable outcome. Mix main/chunk/merge calls, native evidence tools, memory tools and archive-only rows on one phase ledger. Verify provider slots and monetary totals against native rows, and tool/result limits against their specified fold.

### F45-5 — P2: the no-binding-table proposal and tool names disagree with operative SSoT

**Candidate:** §6.3–4, lines 90–91.

`design.md §6.2` defines an immutable per-Attempt `research_memory_bindings` base; §10.2 requires creating it at Attempt start; §12.2 M6 includes its table and call-binding FKs. #43 intentionally deferred base bindings until the Research consumer. Candidate §6.3 now substitutes native snapshots plus individual manifests. That may be a reasonable narrower design, but no explicit supersession/equivalence contract defines the durable pre-first-call base/inherited checkpoint or its relationship to subsequent manifests. #43's earlier decision not to install an unused table does not approve this #45 replacement.

Separately, `design.md §10.3` names native tool CHECK values `memory.search/history.search/source.read`; candidate §6.4 names `search_memory/search_history/read_source`. Public/model tool names may intentionally differ from native journal names, but an explicit mapping is required before changing the native CHECK. Current native values are only `evidence.search/evidence.load`.

**Required correction / owner:** original #45 developer submits a named SSoT amendment to the #41 controller and shared owners: exact Attempt-base authority and creation/recovery semantics, full policy/base/dependency fingerprint representation, no-table impact on binding references and M6; exact model-to-native tool-name mapping. Preserve one native context pointer and one ledger. The controller synchronizes governing design/SSoT only after approval. This reviewer makes no shared-spec edits and does not authorize new tables by implication.

## Governing outcome and semantic oracle

The accepted target remains an enabled Research task checking the exact final main request before **every** send: planner; baseline/adaptive researcher; verifier; critic; investigator and nested model roles; synthesizer; both persisted and graph compositions; tool continuation and recovery. Summary calls are bounded, ledgered, tool-less and nonrecursive. Join and publisher have no invented generation call.

One live native Attempt must cross threshold twice, commit two exact context checkpoints and continue without any new user message. Coverage retains original order/protected anchors and complete groups, with no omitted or duplicated unit. Run/Step/Attempt identity, original evidence/claim semantics, completed tools, frozen scope, phase-root cumulative budgets/deadlines, cancellation, unknown outcomes and publication ownership remain native. A later natural role transition/retry is tested separately; it does not substitute for that same-Attempt proof.

Final A1 choice 2 is preserved in the candidate: no private native mode, audience column or changed output permission. Every private datum, including requester-owned memory/instructions/conditions/source metadata, is excluded from shared prompts, tools, history/source retrieval, planning, summaries/checkpoints and derived outputs/logs. Uncertainty and conflict stay attributed task-local data. No inferred long-term candidate path is authorized.

Acceptance compares actual original inputs, reconstructed requests, role outputs and native business/accounting trajectory. Hashes identify those artifacts; hash equality or summary-row counts do not establish authorization, factual fidelity or user-visible success.

## What the static review does support

- The actual Worker seam inventory is substantially correct: `GenerationResearchAgents._json` reaches `LedgeredGeneration._generate`; the latter packs before reservation and has two provider-send branches. The gate must run before that rejecting packer, and the enabled branch must not subsequently reserve/send through the legacy path. Planner construction uses the literal `execution_snapshot_id="planning"`; the real Step plan revision must supply persisted identity.
- Existing verifier input contains original evidence excerpts and exact claim/handle associations. Keeping those protected is necessary; a history summary cannot establish report evidence.
- The proposed one-owner transaction for snapshot + exact coverage + direct/raw dependencies + Attempt pointer/CAS is aligned with the governing outcome. Business `checkpoint_artifact_id` and run publication pointers remain separate. `_checkpoint_artifact` really requires an execution snapshot; it cannot serve planning compaction.
- The design preserves provider unknown outcomes, last-good context and accounting-only late settlement. #43 F43-1's narrow aggregate/pricing-row metadata allowance is retained; it is not represented as zero native ORM body loading. No source/object/private-memory read is permitted under that late-settlement authority.
- The candidate correctly records #43 P43-A1/A2/A3 as open dependencies. Its exact key/anchor requirement is the correct direction for repeated compaction; the current prefix `covered_count` API/schema is not an accepted #45 integration ABI. No new finding here closes or re-adjudicates the existing #43 review.

## Minimal nonoverlapping slice that can proceed

**Recommended controller assignment: 45a0 — deterministic native context projection and native-identity fixtures.** Developer: original `agt_af167b31`; independent reviewer: this replacement lane, retained for re-review. No authoring is performed by this review. A controller file grant is still required.

Exclusive proposed new files:

- `apps/worker/src/ai_pdf_worker/research/memory_context.py`
- `apps/worker/tests/test_research_memory_context.py`

Both product adapter paths were absent at inspection. Keep the slice narrowly useful: project existing native role input and committed adaptive/conflict results into attributed, non-executable transcript data; preserve actual composite locators, order, exact claims/evidence references and uncertainty; provide tests for two independent records under one Step, protected goal/constraints and nested-role identity. Treat projected source descriptors as unregistered data, with no claim of read authority or invented provider calls. Do not clone shared SourceReference/Generation DTOs or add a new persisted contract. Tests use synthetic lawful inputs and existing native types, with no model/network calls.

Exclude `adapters/memory.py` composition/activation for now, all existing Worker files, migrations/models/registries, shared DTOs, native source/ledger commands, provider adapters and API/UI routes. Those require the exact affected contracts above. This slice neither waits for unrelated #40 image recovery nor claims automatic compaction delivered. If the projection requires a shared ABI change, stop only that affected part and route the delta to its owner. Production composition resumes when #43's corrected gate/coverage ABI is pinned and the native authority/accounting amendments are approved.

## Exact approval and ownership handoff checklist

These are approvals/handoffs still required, not permission grants from this review:

| Delta | Required owner and contract surface |
|---|---|
| Native policy fields and planner cap | #45 native model owner with #42/controller: `models/research_run.py`, nullable `memory_policy_json` on plan/execution and nonnegative `planning_max_tool_calls DEFAULT 0`; strict wrapper validator and frozen write/load/hash payloads in `snapshot_integrity.py`, `research_runs.py`, `research_plan_approval.py`, native planning/execution read DTOs and Worker `core.py` converters. Exact disabled/legacy hash behavior must be frozen. |
| Native binding / shared ABI | #42 owns `ApprovedResearchExecution`/planning DTO changes; #43 owns `compaction.py`, captured native manifest and transaction-neutral authoritative policy/role/source callbacks. Define full-wrapper fingerprint, phase ledger/deadline, base/inherited checkpoint and immutable per-call evolution. SSoT supersession for the no-table choice must precede schema freeze. |
| Native source locators/authorization | #43/source-schema owner coordinated with #42: two new kinds, exact tagged composite locator/version representation, registry uniqueness/current-source semantics, original-body provenance, upstream-role resolver, and `compaction_source_scope` plus use/coverage integrity predicates. Shared history envelope/resolver remains a separately assigned prerequisite; private management is never its fallback. |
| Coverage correction | Existing #43 owner: replace prefix-only planner/repository/DTO/schema assumptions with explicit ordered covered identities/replacement positions while retaining the single atomic checkpoint/coverage/dependency/pointer transaction. #45 supplies native units/anchors. P43-A1/A2/A3 remain open. |
| Native memory tools | #45 owns proposed native tool/lease/reclaim commands; #43 owns sidecar purpose/command/terminal/fold contracts. Settle exact native/model tool-name mapping, planner sidecar behavior, execution-role allowances and no nested transaction ownership. No evidence-handle creation for memory tools. |
| Business checkpoint schema2 | #45 owns `completion.py` writer and Worker consumers; API owner owns `research_worker_state.py::_load_synthesis_selection` and other native read projections. Artifact `schema_version="2"` and payload version/closed shape must agree; the four memory-link fields bind the producer Attempt/checkpoint/context version/manifest and frozen policy, with defined null/no-compaction behavior. Cross-role restore must distinguish producer context from current Attempt. Preserve schema1 reads and publisher idempotency. |
| Event/read API | API/native-event owner and #46: exact `memoryContext` DTO field types/nullability, closed `context_status` event version/fields, durable projection, dedupe/sequence behavior and run-detail selection when branches compact concurrently. Update native `constants.py`/`events.py` and `ResearchEvent` CHECK consistently; run/step metadata carries no bodies or secrets. Existing cancel/retry write requests remain unchanged. |
| Migration / activation | One assigned successor after the actual integrated #43 head, revision ID allocated by controller. Include approved native policy/cap, source identity/predicate, tool/event constraint changes without recreating #43 tables/pointer columns or amending a published migration. Install enabled readers before release registration/activation, fence unsupported binaries, and retain guarded downgrade. Shared owners synchronize ORM/Alembic/DTO/SSoT together. |

The planner and execution ledgers remain distinct native phase authorities. Preserving root budgets means preserving each actual ledger across roles/retries, including spent/reserved/unknown usage; no independent memory budget table and no invented whole-run monetary ledger.

## Evidence scope and remaining acceptance

| Area | Result of this review |
|---|---|
| Exact governing goal, A1 and complete pinned candidate inspected | **pass — static identity/scope only** |
| Worker dispatch/restore inventory | **pass — bounded static inventory; runtime coverage unproved** |
| Native journal identity | **blocked — F45-1** |
| Frozen policy / authorization / transaction ABI | **blocked — F45-2/F45-3** |
| Tool accounting/reclaim and consistent SSoT | **blocked — F45-4/F45-5** |
| Atomic integration contract direction | **pass — one-owner design invariant only; exact corrected coverage/predicates remain blocked** |
| Product implementation, PostgreSQL migration/constraints/races, runtime crash recovery | **blocked / not executed or accepted here** |
| Model semantic fidelity and real visible UI | **blocked / not executed; separate required gates** |
| New private native product, evidence expansion, inferred long-term candidates | **not applicable / excluded** |

Required implementation evidence remains T45-01–11, with these especially discriminating negatives: two same-Attempt compactions after a protected current question; tool-less summaries through each real neutral serializer/counter; stale capacity rejection; forged upstream-role source and native policy; private markers owned by requester/second member/owner; exact native mixed-purpose budgets and unknown usage; actual commit-ACK loss and all-old/all-new recovery; no completed-tool/publication replay; valid-JSON semantic omission; and a real page that resumes automatically through both organizing phases and survives refresh/cancel/failure. Deterministic streams can establish mechanics without paid calls. Real semantic quality remains unaccepted until separately authorized evidence exists.

Reverse-review questions: if a second episode silently omits a turn, F45-1 plus ordered-unit reconstruction must catch it; if the verifier reads another branch or a nested role is rejected, F45-3 must catch it; if a policy changes without new approval, F45-2 must catch it; if expiry strands planner reservations or archives consume provider slots, F45-4 must catch it. Native predicate and payload tests are necessary in addition to hashes.

## Inspection identities and reproducibility

Canonical Worker/native baseline: `D:/Code/citeframe`, branch `refactor/workspace-access-dependencies`, HEAD `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`. Initial canonical status contained only untracked `docs/ssot/memory-management.md` and `specs/v5/memory-management/`; tracked #40 files were clean. No canonical product or Git state was changed.

#43 read-only baseline: `D:/Code/citeframe-lanes/issue43-compaction`, branch `work/issue43-inloop-compaction`, HEAD `cae6379e1f3743b944b745797cf6f157b1915654` plus unfinished dirty/untracked product work. Its DTO/core/migration are candidate files, not accepted ABI. Selected Option A design approval at `ED10B657B3DE9862D3601A8917B798AADE08B21E18CB48D66448BC5D2EEEE1E9` remains bounded to its original scope. Current pure audit still requires P43-A1/A2/A3 rework. The separate prepared-chat lifecycle amendment also remains marked awaiting approval; it supplies no Research acceptance.

| Artifact (canonical unless prefixed #43) | SHA-256 at inspection |
|---|---|
| `specs/v5/memory-management/spec.md` | `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85` |
| `specs/v5/memory-management/design.md` | `068F9112279B55C6B9E1AB63730EF053F9E0B8A570C0EC4929677CE92502B1BB` |
| #43 `specs/v5/memory-management/lanes/issue43-compaction.md` | `A895BCF30B5617DA9A14D961ED1ECB7DCA06152CEFD80479ED2742373252024A` |
| #43 `specs/v5/memory-management/reviews/issue43-compaction.md` | `1A46554A52902CBCCFBB59F32220F17A4FA161C756AC28EF373B167978783219` |
| #43 `packages/backend-contracts/src/citeframe_contracts/compaction.py` | `D77617A25ECF5CD9C0B808537F6C884B7EE67E2A2250BB0D955E99597DDB5E2B` |
| #43 `packages/backend-contracts/src/citeframe_contracts/memory.py` | `B1A0D53B5D21BAC31AC12609A5A798CCEDA5F9AAB43EEFAA4E178A3D9D5AAE45` |
| #43 `packages/memory-service/src/citeframe_memory/compaction/guards.py` | `4858DDFD0A9FAB77BAE8EC26577B4BCCE2E78F687B788BE2F12302506414FC7A` |
| #43 `compaction/sources.py` (same package) | `D783D49F377459FD5A1B9DDD544562EA1DC5741947DF24642AE882A35AF5A66E` |
| #43 `compaction/repository.py` | `83ACC2592F0477B748B1FBF2F3990F9B613E11DA8911CD11FF9B301825627482` |
| #43 `compaction/journal.py` | `0643125D343A6A1E978B80804744077ED6BB640137DF40A6885DDC2D7CF5E8A3` |
| #43 `compaction/gate.py` | `208F53802C4EF837626760D92FEB356D8855AAFC5DEE7F4DFD81FF1F478EA8F8` |
| #43 `apps/api/alembic/versions/u5c6d7e8f9a0_inloop_compaction.py` | `5CA29D7517C65710133AE5A1EAAD4A6F59BF10A35126656B01C2D631EB043468` |

Executed read-only: `python -B D:/Code/dev-workbench/scripts/prepare_session.py --repo-path D:/Code/citeframe`, referenced workbench project/state/task reads; remote and local/global identity reads; `git --no-optional-locks status --short`, branch/HEAD reads; targeted `Get-Content`, `rg`, `Test-Path`, `Get-FileHash`. #43 Git reads initially encountered safe-directory ownership rejection; command-local `git -c safe.directory=D:/Code/citeframe-lanes/issue43-compaction ...` permitted inspection without changing config. Broad outputs that truncated were followed by focused reads for the cited contracts. No test, migration, service, database, browser or model execution occurred. No paid call occurred.

Write-back check: durable findings and handoff are recorded only in this new reviewer artifact. Private MEMORY/daily memory was not read. No profile-memory, shared workbench/spec, product, package, Git/index/config/branch or #43 worktree write was made. No background reviewer task remains. The controller should relay these bounded findings to `agt_af167b31`, obtain the owner-approved exact amendments, and return a newly pinned candidate for independent re-review.

## Targeted re-review — candidate 2019A9F4 (2026-09-28)

**Latest disposition: REWORK REQUIRED, limited to F45-1-R1 (P1 request-identity conflation) and F45-4-R1 (P2 expiry-state mapping).** F45-2, F45-3 and F45-5 are closed at design scope. The composite-native-key portion of F45-1 and the missing reclaim/accounting ownership portion of F45-4 are repaired. No broad redesign or repeat of already-resolved findings is requested.

Exact complete candidate: `lanes/issue45-research.md`, SHA-256 **`2019A9F4038646694071CB430FAF9ADB6CDBD1679A7827772BDBD5F1186CCF39`**, matched before and after inspection. This section supersedes the initial finding dispositions above for this candidate only. Native-key/schema/ABI implementation is **not authorized** by this review. Controller owns relay to original developer `agt_af167b31`.

### F45-1-R1 — P1: the archived role-input hash cannot equal the conflict-journal request hash

**Candidate location:** §5.1 line 99; related `ResearchInvocation.nativeInputSha256` at line 116 and request-source binding at line 101.

The revised envelope stores the pre-pack native role variables as `nativeInput`, then requires `nativeInputSha256` to equal the adaptive/conflict native `request_sha256` where applicable. Actual conflict orchestration hashes a different object from the variables supplied to `_json`:

| Path | Native conflict request | Actual pre-pack role variables |
|---|---|---|
| Investigator inspect | `conflict_investigation.py:77–85`: payload containing claims, evidence, remainingSearches, previousInspections, gaps | `agents.py:312–314`: `{investigation: payload, resultSchema: ...}` |
| Nested verifier | `conflict_investigation.py:109–115`: `{revisions, evidence: full native evidence dataclasses}` | `agents.py:218–242`: `{claims, evidence: selected excerpt/locator/fingerprint projection, reasonTaxonomy, resultSchema}` |
| Nested critic | `conflict_investigation.py:139–145`: `{claims: full VerifiedClaim dataclasses}` | `agents.py:257–266`: `{claims: id/text/status projection, resultSchema}` |

All Worker paths are under `apps/worker/src/ai_pdf_worker/research/`. The neutral `packages/research-persistence/src/citeframe_research_persistence/conflict_investigation.py::conflict_turn` calculates `canonical_sha256(request)` and checks it against the exact stored native request JSON. `GenerationResearchAgents._json:324–329` serializes the different role-variable object. Identical canonicalization does not make these different payloads identical.

An implementation of the current equality rule would reject legitimate investigator/nested-verifier/nested-critic dispatch or record the journal request under the misleading identity of the actual role input. This affects the every-role goal and exact original-request recovery. It is a static contract mismatch; no enabled runtime failure is claimed.

**Narrow correction:** keep distinct, explicitly named identities for (1) native journal request and its composite locator/hash, (2) pre-pack role variables and their own hash, and (3) the final post-gate GenerationRequest and its dispatch hash. For each journal-backed invocation, bind the deterministic versioned native-request-to-role projection to the same approved role/schema/authority; do not require hashes of different representations to be equal. Declare which hash `ResearchInvocation` carries and preserve both identities in the request envelope/input manifest. Nonjournal roles have no invented journal request. Existing native journal payloads/hashes remain unchanged. #45 specifies the projection; #43 owns the shared invocation/archive/manifest amendment. No new source table or product scope is required to repair this contract.

**Acceptance discriminator:** use actual investigator, nested verifier and nested critic builders with synthetic native records. Verify the original journal hash matches its native row; the role-input hash matches exactly the variables passed into `_json`; the provider hash matches the exact returned gate request. Those values may legitimately differ. Alter the journal, a projected evidence excerpt, result schema or invocation independently and reject the affected binding. Recover the three identities without rebuilding a missing original archive, and retain no-resend behavior for sent-unknown calls. Include adaptive researcher as the case where native request and role variables currently do coincide.

The composite `native_key` repair itself is accepted at design scope: distinct turn/operation/body-part keys and partial current/version uniqueness avoid cross-turn replacement, and the candidate now distinguishes native result bodies from archived requests. The remaining issue is the archive's representation/hash mapping.

### F45-4-R1 — P2: reserved execution-tool expiry has two conflicting native terminal states

**Candidate location:** §8.2 line 239 versus §8.3 line 252.

The transition table specifies `reserved→cancelled (cancel/expiry before start)` with native execution tool state `cancelled`. The reclaim section delegates native execution-tool settlement to the existing native reclaimer and makes the hook mirror its winner. Actual `packages/research-persistence/src/citeframe_research_persistence/state.py:333–344` sets **both requested and running** expired tool calls to `abandoned`, decrements one reservation and increments the native actual/Attempt tool counters once. It does not distinguish the proposed sidecar's proven-unsent state. The candidate does not explicitly change that native state mapping.

The one-slot accounting rule is consistent; the exact terminal contract is not. A consumer requiring the table's native `cancelled` state cannot simply mirror the native expiry winner. Do not rewrite an already-terminal native row on late receipt to obtain that equality.

**Narrow correction:** distinguish explicit cancellation from lease-expiry reconciliation in the table. Preserve native expiry `abandoned` and specify its sidecar mapping using the already-recorded start/unsent evidence: proven unstarted can have sidecar cancelled/zero result tokens; started with uncertain result retains unknown/conservative result tokens. Record native status separately from sidecar disposition. The owner should freeze this mapping for planner-sidecar and execution-native paths, including completion-first/reclaim-first. Any different desired native state transition must be an explicit bounded native change, not assumed from unchanged reclaim arithmetic.

**Acceptance discriminator:** expiry with native requested + sidecar reserved and expiry with native running + sidecar sent; explicit cancel before start; result completion before expiry; expiry before late completion. Assert the declared native/sidecar terminal pair, one native slot settlement, correct result-token reservation and no terminal rewrite/refund/reexecution.

### Resolved findings and bounded design acceptance

| Original finding | Re-review disposition and evidence |
|---|---|
| F45-1 composite source identity | **Repaired at design scope**, §5.1 lines 82–97: real composite locators, separate body-part keys, nullable native_id only for journal kind, native_key/current/version uniqueness, producer/consumer distinction and no fabricated native/provider IDs. Request-archive mapping remains blocked only by F45-1-R1. |
| F45-2 frozen policy | **Closed at design scope**, §§6.1–6.3: planning wrapper, approved execution template and resolved execution wrapper are separately defined; real phase timestamps fix deadlines; canonical planning/source/persisted builders and API write/read owners are enumerated; disabled payloads omit every new key; row immutability blocks paired policy/hash rewrites; full policy authority is rechecked transactionally. Native and neutral provider fingerprints are distinct. Actual implementation/mutation races remain untested. |
| F45-3 source authorization | **Closed at design scope**, §5.2: completed transitive join/researcher provenance, explicit investigator/nested verifier/nested critic phases, selected claims/handles and current frozen assets; paired Python resolver and SQL source/use/coverage checks derive consumer invocation from immutable manifests; inherited leaves are reauthorized for the consumer. This approves the authorization design direction, not current same-Step resolver behavior or a schema grant. The request identity correction above must be applied consistently to its invocation binding. |
| F45-4 reclaim/accounting omission | **Repaired at design scope**, §8: whole-batch admission, planner-sidecar versus native execution children, one native charge, purpose-specific provider/tool/result folds, native evidence mirror, transaction-neutral arithmetic, pre-abandonment reclaim and cancel/idle ownership are explicit. Only F45-4-R1 terminal mapping remains open. |
| F45-5 SSoT/base/name mismatch | **Closed at design scope**, §§7–8.1: no-table proposal withdrawn; approved immutable Attempt-base table/first-use/retry/inherited-context semantics retained; underscore public names map explicitly to dotted native CHECK/policy names. Schema2 carries producer/base provenance without a second live pointer. Controller/shared-owner synchronization and grants still precede implementation. |

No defect was found in the proposed bounded composite-key string length or independence of current-source identities. Direct-SQL CHECK/index/locator equality, P1a parity and migration/down tests are still required before implementation acceptance. New frozen-field/journal/decision immutability predicates likewise require enabled/disabled native write-path parity testing; this review has executed no DDL and grants none.

The final A1 privacy boundary, uncertainty retention and one atomic checkpoint/coverage/dependency/live-pointer transaction remain intact. Preserve the literal same-live-Attempt two-crossing requirement, root phase budgets, native cancellation, unknown-call treatment and publication identity. Design scope does not establish any of those runtime results.

### 45a0 readiness retained

**Ready for controller assignment at the previously accepted unactivated scope**, unchanged two proposed new files:

- `apps/worker/src/ai_pdf_worker/research/memory_context.py`
- `apps/worker/tests/test_research_memory_context.py`

Both paths were still absent. Original developer `agt_af167b31` can project supplied synthetic native data using real composite locators, attributed uncertainty and exact role/evidence content. Include independent journal-request and role-input descriptors so the pure projection does not encode the false equality identified above. Descriptors grant no source authority. No shared DTO cloning, source registration, native_key/schema work, adapter wiring, ledger/native command, API/UI activation or model call is included. Controller's explicit file grant remains necessary; unrelated #40 work need not block this slice.

### Unchanged #43 gates and execution evidence

The #43 DTO remains SHA-256 `D77617A25ECF5CD9C0B808537F6C884B7EE67E2A2250BB0D955E99597DDB5E2B`. The current #43 review is now SHA-256 `E05A87F5AF808FA5F4AF7AF9F3D3C351448F0102E5B8917F07B9DEF0B1FEDB6B`; it adds bounded prepared-chat lifecycle design approval and explicitly leaves **P43-A1/P43-A2/P43-A3 open**. That amendment does not approve #45 upstream-source expansion or this Research ABI. No pure-finding waiver is made here.

Canonical branch/HEAD remained `refactor/workspace-access-dependencies` / `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`; initial unrelated untracked documentation state remained present. Governing spec/design hashes still match the initial review. Rechecked native evidence identities:

| Native file | SHA-256 |
|---|---|
| Worker `research/agents.py` | `EA3842D4228897A9ECBD2D550A70FF340536CC669D6D686271322DE2AE81C4EB` |
| Worker `research/conflict_investigation.py` | `FB4CF2ACDAA3C441EFDF56439E7C81DFFD9AAB48E96583A455C7EC45B4EAA425` |
| neutral `citeframe_research_persistence/conflict_investigation.py` | `B396A22AEA799A1324DACC7824A3F0367CF2BA25A7F44324B7BC1E8F642AA9C1` |
| neutral `citeframe_research_persistence/state.py` | `C6BE335EB5C51020036747B5F4A3777179DE0D05AE2FF21DEAE964CFFC27E057` |

Evidence is complete candidate reading plus targeted native source, DTO, current #43 review, status/HEAD and hash reads. No tests, database/migration, provider/model, browser or service execution was performed; no runtime or semantic/UI pass is claimed. Same-session bootstrap remains the earlier read-only profile/prepare_session inspection; no private memory was loaded. Write-back is this own-review update only, preserving the initial review as history. No product, Git/config/index, shared spec/workbench or #43 file was written.

## Final targeted re-review — candidate 249C97FD (2026-09-28)

**BOUNDED DESIGN APPROVE. No remaining finding in the two requested corrections or targeted regression checks of the already-accepted sections.** This disposition supersedes the 2019A9F4 residuals at design scope only. It grants no native-key/schema/ABI work, wiring, storage, runtime, semantic-quality or UI acceptance.

Exact canonical contract: `specs/v5/memory-management/lanes/issue45-research.md`, SHA-256 **`249C97FD1705AFCA6481566FD49F1511A6D0E2F82E2C5933BEAD80212FBB89F4`**. Governing spec v4 remains `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85`; design remains `068F9112279B55C6B9E1AB63730EF053F9E0B8A570C0EC4929677CE92502B1BB`.

### Residual closures

| Finding | Disposition and exact contract evidence |
|---|---|
| F45-1-R1, P1 | **Closed at design scope.** §5.1, lines 99–113, defines separate nativeJournalRequestSha256, roleVariablesSha256 and providerRequestSha256, each bound to its own original body. The request envelope, immutable manifest and §5.2 ResearchInvocation agree. The versioned projection binds approved role/schema/native inputs; investigator wrapping, verifier selected evidence/taxonomy and critic claim projection are explicit. Adaptive coincidence is limited to its actual builder; nonjournal roles have no invented journal. Missing archives remain unavailable; sent-unknown calls are not resent. Native journal bytes/hashes remain unchanged. |
| F45-4-R1, P2 | **Closed at design scope.** §8.2, lines 250–259, distinguishes explicit pre-start cancellation from lease expiry. Native requested/running expiry remains abandoned; sidecar proven-unstarted is cancelled/zero result tokens, whereas started/uncertain is outcome_unknown/conservative tokens. Native status is separately recorded. Locked durable pre-reclaim start evidence, atomic mark-start-before-IO and ambiguity handling prevent a late or ambiguous result from becoming a zero-cost cancellation. The native winner and one-slot settlement remain immutable. |

Actual Worker `research/agents.py` remains SHA-256 `EA3842D4228897A9ECBD2D550A70FF340536CC669D6D686271322DE2AE81C4EB`. Independent pure builder capture in the separate projection review exercised investigator, verifier and critic with actual registry schemas, checking full variables and distinct native-request representations without calling a provider or inventing successful output. That supports the representation correction; it does not test archive binding, post-gate provider-request equality or recovery. Native expiry evidence remains `citeframe_research_persistence/state.py` as cited in the preceding review, with the design now preserving that transition.

### Accepted-section regression check

- **Pass, design only — §5.1 composite keys:** real Step+ordinal/body-part identities, separate producer/consumer, partial current/version uniqueness and unchanged native journal semantics remain. No fabricated row/provider-tool ID is introduced.
- **Pass, design only — §6 policy:** enabled planning/proposal/approval/persisted hash chain and full-wrapper authority remain transactional; disabled hash payloads omit the new keys. Native and neutral fingerprints stay distinct; phase deadlines remain rooted at the original phase boundary.
- **Pass, design only — §5.2 authorization:** completed upstream dependency/claim/handle provenance, nested gate roles and exact operation binding still require coordinated SQL and Python checks. Consumer authorization is reapplied to inherited leaves. No same-run privilege or new output permission is granted.
- **Pass, design only — §§7–8:** immutable Attempt-base table and single live pointer remain; snapshot+coverage+uses+CAS has one transaction owner. Planner reclaim, purpose-specific folds, native evidence accounting once, explicit public-to-native tool mapping and separate planner/execution identities remain intact.
- **Pass, scope only — A1 and governing goal:** all private data stays excluded, including requester-owned data; uncertainty stays task-local. Every actual main dispatch and recovery path still requires the gate, and two compactions in the same live Attempt without new user input remain mandatory. Frozen evidence, phase budgets, cancellation, unknown outcomes and publication ownership are unchanged.

### Implementation gates and smallest slice

The previously proposed **unactivated 45a0** slice remains valid. Its separately authorized implementation is reviewed in `reviews/issue45-projection.md`; that result is not derived from this design approval. Original `agt_af167b31` retains design ownership. The controller identified `agt_d03b4a29` as the read-only-lane implementation replacement because of the canonical worker's filesystem deficit; this preserves one product owner for the slice. Controller owns relay and integration.

The exact owner approvals enumerated in this review and contract §9 remain necessary for native_key/uniqueness/migration, ResearchInvocation/request-envelope/shared DTOs, native freeze fields/hash writers, Research source SQL+Python resolver, Attempt bindings/call FK/schema2 and native tool/reclaim changes. None is implemented or authorized by this verdict. There is no blanket wait for unrelated #40 work.

Current #43 DTO hash remains `D77617A25ECF5CD9C0B808537F6C884B7EE67E2A2250BB0D955E99597DDB5E2B`. Its review has advanced to `03AC7FA67F60B01FBD986660B88B5AC07B24B437B08604198242EBFE80D8FFEA`: the latest interval/profile review requires P43-I1/P43-I2 rework and records bounded progress on the original A1/A2/A3 counterexamples without closing the whole pure/core gate. This #45 review neither waives those gates nor claims that earlier reported #43 hashes describe its current implementation. Re-pin the final approved ABI before dependent wiring.

Evidence boundary: targeted normative contract/native reads, exact hashes, separate pure tests/builder capture only. No DDL, DB, storage, provider/model, Git command or UI execution in this final targeted pass. No product/shared-spec/workbench write. Same-session bootstrap was read-only; no private MEMORY/daily memory was read. Write-back is limited to the two own-review artifacts. Earlier no-test statements apply to their historical design-review turns, not the separate 45a0 implementation verification below.