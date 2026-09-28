# Issue41 — actual code inventory

Read-only source inspection, 2026-09-28. Companion: [design.md](design.md). This inventory describes observed behavior and proposed seams, not implemented Issue41 behavior.

## 1. Baseline, worktree and ownership

- Requested source baseline: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Canonical path: `D:/Code/citeframe`; branch throughout inspection: `refactor/workspace-access-dependencies`.
- Initial `git status --short`: nine modified API routers (`assets/chat/deps/evaluation/jobs/model_settings/notes/research/workspaces`); four modified embedding/image tests; two modified SSOT files; new workspace-access tests/SSOT and Issue40 spec/evidence. These were pre-existing Issue40 work, not owned by Issue41 developer.
- During inspection, another actor advanced HEAD to `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae` (`refactor(api): unify workspace authorization dependencies`). This developer did not commit or modify branch state. No merge/main acceptance is inferred. Re-pin implementation baseline through controller after Issue40 integration.
- Final read-only verification observed concurrent HEAD `5903d60b7103d32d7d8a0c173691250407460b13` on the same branch; that delta has not been re-audited here and is not a controller handoff.
- Remote inspected: `https://github.com/Gujiassh/citeframe.git`. Local/global identity matched (`gujishh`); no identity changes made.
- Only authored files: `specs/v5/memory-management/design.md` and this inventory. Concurrent `spec.md`, `delivery.md`, `reviews/`, and `docs/ssot/memory-management.md` were observed after drafting began and left untouched; their content is not claimed as this developer's work.
- No reset, stash, switch, worktree creation, commit, push, migration, model call or paid evaluation was performed.

### Instructions/context read

`D:/AI/profile/AGENTS.windows.md` including Global Requirement Alignment and writing rules; `MEMORY-POLICY.md`; SOUL/IDENTITY; `D:/Code/AGENTS.md`; `apps/web/AGENTS.md`; `project-architecture/SKILL.md` and architecture guidance; full external proposal v2 including §12, repository spec v3, independent R2–R16 and O22–O30/CO01–CO12 supplement; linked workbench `projects/--Code--citeframe/project.md`, `state.json`, `tasks/workspace-access-dependencies-20260928.md`. prepare_session was already run by controller. Private MEMORY.md and shared state writes were excluded. Repository search found no root or feature-specific AGENTS beyond web; inaccessible pytest caches were not inspected.

## 2. Ordinary chat and source identity

| Actual path / symbol | Verified behavior | Design consequence |
|---|---|---|
| `apps/api/src/ai_pdf_api/services/chat.py::prepare_chat` | Discards user_id; resolves ready asset scope; embeds current question; errors if neither retrieval nor evidence targets; appends system, completed ancestors and current retrieval-enriched user message | Need authenticated source attribution, versioned memory-only mode, budget assembler; preserve current ordinary mode contract |
| Same, `_get_message_lineage` | Loads thread messages, traverses parent IDs with cycle/missing-parent checks, keeps completed nodes, reverses to ancestor order | Summary coverage must bind exact parent chain and completed units; active leaf alone is insufficient |
| Same, `active_message_path` | Uses thread.active_message_id, includes status-bearing nodes, validates graph | UI/history branch semantics cannot be rewritten as flat timestamp history |
| Same, `finalize_chat` / `fail_chat` | Completion writes assistant and active leaf; failure removes pending citations, stores failed message; transaction commits | Tool turns need sidecar storage, complete-output proof, cancellation/source invalidation guard |
| Same, `_build_user_prompt` / `_build_retrieval_context` | Selection text currently sliced to 12000 chars; retrieved text to 4000 each | Existing char truncation cannot be claimed as token-exact or complete summary coverage |
| `packages/backend-persistence/src/citeframe_persistence/models/chat_message.py::ChatMessage` | UUID strings; workspace/thread/parent; role/content/status; model and nullable usage; no actor/revision/deleted_at | No inferred historical user confirmation; registry sidecar for new actor/version provenance |
| `.../models/chat_thread.py::ChatThread` | Creator, title, active leaf, archive/timestamps; no private audience | Existing workspace readership makes private-output audience an approval gate |
| `apps/api/src/ai_pdf_api/routers/chat.py::get_workspace_thread/list_threads/list_thread_messages` | Workspace and unarchived thread filters, no creator-only read predicate | A private-memory answer would otherwise be readable by other members |
| Same, `archive_thread` | Workspace owner or creator can archive; sets archived_at | Existing Delete Thread is archive, not raw erasure; derived availability must respect archive |
| Same, `stream_chat` | meta → provider string deltas → final citations/done; errors/failure; GeneratorExit marks interruption | Needs bounded typed tool loop, durable cancellation, source-safe terminal state; preserve asset citations |
| `apps/api/src/ai_pdf_api/schemas/chat.py` | Existing typed requests/asset scope/evidence targets | Add mode2 explicitly; do not silently change old asset-grounding request behavior |

## 3. Providers, capabilities and streaming

| Path / symbol | Verified behavior | Integration seam |
|---|---|---|
| `apps/api/src/ai_pdf_api/services/providers.py::GenerationProvider` | generate returns str; stream Iterator[str]; GenerationMessage is dict[str,object] | New structured native tool-turn contract needed |
| Same, `OpenAIGenerationProvider`, `_read_response_stream` | OpenAI Responses adapter with explicit response completion parsing | Native function-call/result support requires protocol fixtures |
| `services/chat_completions.py::ChatCompletionsProvider` | Requires stop finish; rejects tool_calls/refusal in generate and stream; maps existing text/image messages | Current compatibility endpoint does not imply active memory tools support |
| `services/providers.py::DeepSeekGenerationProvider`, `_split_deepseek_system_and_messages`, `_map_messages_for_deepseek_anthropic` | Maps system text to top-level, accepts user/assistant roles, maps text/base64 images | Need tool_use/tool_result protocol support and actual completion-marker fixture; not a role-string patch |
| `services/capabilities.py::CapabilityProfile` / `build_capability_registry` | Provider/model/adapter/model-version, limits, pricing, boundary policy and config fingerprint | Add tested tool support and explicit capacity/counting policy; existing generation limits include timeout/output, not complete context window |
| `services/workspace_models.py`, `workspace_providers.py`, `model_config_types.py` | Current workspace model composition and typed connection configuration | Reuse resolver at application composition; inject into neutral services |
| `apps/web/src/app/api/workspaces/[workspaceId]/chat/stream/route.ts` | Trusted server session/headers; streaming proxy; displayed requestInit has no Request.signal forwarding | Explicit abort propagation and durable cancellation endpoint required |
| `apps/web/src/lib/chat/sse.ts::dispatchEvent/consumeChatStream` | Parses known meta/delta/citations/done/error; rejects invalid citation envelope; EOF without terminal event fails | Add typed memory/history events separately; preserve terminal and citation strictness |

Provider capability probing/evaluation was not run. No claim is made that deployed endpoints accept native tools.

## 4. Neutral packages and dependency direction

- `packages/backend-contracts/src/citeframe_contracts/__init__.py`: standard-library DTOs/Protocols, `ApprovedResearchExecution`, `ToolExecutionContext`, `EvidenceHandle`, `LoadedEvidence`, `ResearchState`, `ResearchLedger`. README explicitly states pure contracts. Add memory contracts as a cohesive module, avoid growing the initializer with business code.
- `packages/backend-contracts/src/citeframe_contracts/validation.py`: existing shared validation seam.
- `packages/backend-persistence/src/citeframe_persistence/base.py` and `models/`: canonical SQLAlchemy Base/mappings. API `models/*.py` are compatibility surfaces; do not create a second Base.
- `packages/research-persistence/src/citeframe_research_persistence/`: existing neutral commands/repositories/locks/lease/provider/tools/membership/recovery/publication. Preserve its transactional ownership.
- `packages/research-persistence/.../ports.py`: provider resolver/object-store ports; `provider.py` explicitly requires injected capability matcher in reservations. New neutral service uses the same dependency principle.
- `apps/api/src/ai_pdf_api/services/research/research_worker_tools.py`: commit/rollback facade over neutral tool persistence. Shared services must not import this facade or routers.
- `apps/worker/pyproject.toml`: still depends on ai-pdf-api and neutral packages. `research/adapters/generation.py` imports API provider/context-policy services; Worker `main.py` composes API settings/session/providers/ingestion. This existing coupling is observed; no new Worker-to-API imports are permitted for memory integration, including service/protocol imports.
- `packages/shared-types` and `packages/prompt-contracts` currently contain scaffolding/readme surfaces, not an established complete memory contract implementation. Web feature-local typed DTOs align with existing project practice.

Sole proposed DTO/Protocol owner: `packages/backend-contracts/src/citeframe_contracts/memory.py`, including access, generation, embedding, counting, storage and connection snapshot contracts. No parallel memory-service ports/types owner. Proposed shared protocol placement: `packages/memory-service/src/citeframe_memory/adapters/{responses,chat_completions,anthropic,counting}.py`, consumed directly by both API and Worker composition. Worker receives neutral connection/session/transport/object-store ports from existing bootstrap; shared adapters import neither application. Extract only required shared primitives with parity fixtures. This is a candidate seam, not an existing package or blanket service refactor.

Mixed-responsibility risks: chat.py combines scope/retrieval/prompt/persistence; providers.py combines embeddings and multiple protocols; retrieval.py combines modality constraints/SQL/ranking; Research core/handlers/adapters coordinate many contracts; SettingsPanel/chat-panel/workspace-context already compose substantial UI behavior. Add cohesive memory modules and thin composition changes. Avoid wholesale unrelated refactors; if provider primitives must move, parity-test extraction before new semantics.

## 5. Retrieval/index and raw source lifecycle

| Actual path | Verified facts | Required preservation |
|---|---|---|
| `services/retrieval.py::retrieval_scope_statement` | Joins ContentUnit/Asset/Representation/EvidenceLocator; workspace consistency, current generation/index, ready/nondeleted, modality signatures | New memory/history uses separate source eligibility; never fabricate asset ContentUnits |
| Same, `retrieve_content` / dense ANN helpers | pgvector cosine, current embedding scope, binary candidate option, SQLite test path | Reuse infra/primitives, not asset-specific ACL query |
| Same, `retrieve_lexical_content`, `_lexical_terms`, `_rrf_merge` | PostgreSQL lexical/trigram and CJK/Latin handling plus deterministic hybrid RRF | Ranking reuse with separate source types; no quality probability label |
| `services/embedding_index.py::EmbeddingIndexContract` | provider/model/dimensions/version/fingerprint; explicit mismatch requires reindex; legacy support exists for older native jobs | New memory index requires complete fingerprints and rejects legacy mismatches |
| `models/content_unit_embedding.py` (neutral) | Vector(1024), JSON SQLite variant, current HNSW cosine/binary indexes, asset/unit FKs | Separate memory tables/spaces; no dimension padding or fake asset FK |
| `models/note.py` | Mutable body/title, updated_at/actor, archive; no immutable body revision history | Registry can detect stale notes; cannot return nonexistent old bytes |
| `models/message_citation.py`, `message_input_evidence.py`, `evidence_locator.py` | Existing source/evidence snapshot contracts used by chat | Keep meanings and return shapes, use separate history refs |
| `routers/assets.py::delete_asset` | Locks asset, enqueues delete_cleanup, transitions deleting | Invalidate memory in same logical-delete transaction before object cleanup |
| `services/ingestion.py::process_delete_cleanup` | Deletes raw/derived object keys, invokes adapter cleanup, marks deleted_at/status after work | No new raw deletion policy; derived read gate must not wait for physical cleanup |
| `services/ingestion.py` reindex/reprocessing paths | Current-generation/index lifecycle already exists | Hook source invalidation and stale-profile job rejection |

No source registry, memory revision table, semantic task-summary store, history-memory vector table or active history tool was found in these inspected paths. The statement is scoped to inspected source, not a runtime feature probe.

## 6. Research ledger, evidence and recovery

| Actual path / anchor | Observed contract | Design consequence |
|---|---|---|
| `models/research_run.py` (neutral) | Plan/execution snapshots, frozen workflow/model/retrieval/budget fields | New policy versions cannot rewrite frozen snapshots |
| `models/research_execution.py::ResearchToolCall` | CHECK names evidence.search/load; execution_snapshot_id required; unique logical attempts/order | Memory tools require reviewed checks/policies; planner cannot use execution-only row blindly |
| Same, `ResearchProviderCall` | reserved/sent/succeeded/failed/outcome_unknown/cancelled; logical_call_key; usage/reservations/fingerprint | Reuse native reservation ledger; sidecar must not double-count |
| Same, `ResearchBudgetLedger` | Exactly one plan/execution owner; reserved/actual tools/provider/tokens/cost and state_version | Planning tool allowance needs explicit new frozen field; no hidden unlimited tool budget |
| `models/research_artifact.py` | Internal execution_checkpoint/verification_result; user final_report; retention classes; immutable object hashes | Public memory read_source cannot expose internal artifacts |
| Same, `ResearchClaim`, `ResearchEvidenceSnapshot`, `ResearchClaimEvidence` | supported/unsupported, conflict statuses, support/contradict links and source fingerprints | Task summaries preserve status/IDs; promotion requires original support |
| `services/research/research_context_policy.py` | research-typed-batches-v1 columnar compaction preserving full shape/IDs; packing/limit checks | Existing structural compression is distinct from new semantic summary |
| `services/research/research_agent_io_registry.py::estimate_text_tokens` | UTF-8 byte count divided by four rounded up | Estimated token policy; new counters/versioning needed |
| `apps/worker/src/ai_pdf_worker/research/tools.py::EvidenceToolRegistry` | Frozen asset subset, issued handles, strict provenance/branch/step/generation/index, load <=12000 chars | Memory tool refs never mint or replace native evidence handles |
| `research/adapters/evidence.py::SqlEvidenceToolPort` | Restore/search/load scoped through Research service | Keep native evidence route for current report support |
| `research/adapters/generation.py::LedgeredGeneration` | Reserve/reconcile external calls, heartbeat/context pack/profile validation | Gate exact next input before final request hash/reservation on every role/call; native cost authority retained |
| `research/engine.py` recovery validation | Execution snapshot drift and checkpoint invalidity checks; claim/source comparison | Add versioned memory binding, never latest-summary substitution |
| `research/handlers.py` | Branch/verifier/critic/synthesizer completion; native conflict investigation/resume | Semantic summary cannot set success or resolve conflict |
| `research/adaptive_retrieval.py`, `conflict_investigation.py` | Existing bounded adaptive/investigation modules | Reuse workflow boundaries; memory lookup must remain inside frozen budgets |
| `citeframe_research_persistence/completion.py::_checkpoint_artifact` | Object-backed internal execution checkpoint schema version 1; attempt/run checkpoint pointers | Preserve business checkpoint pointers; add context version/pointer to native Attempt and a reference in new checkpoint payloads; retain old-run path |
| `.../state.py::reclaim_expired_research_steps` | Reserved calls cancel; sent calls become outcome_unknown with estimated usage; publication-owned attempts excluded | Memory recovery must respect uncertain outcome and publication ownership |
| `.../membership.py::ensure_creator_membership` | Membership loss cancels/finalizes or rejects current run | Revalidate memory/source and private audience on every invocation |
| `.../provider.py::reserve_provider_call` | Requires frozen matching profile and capability matcher | No silent profile drift or unledgered summary call |
| `.../tools.py::begin_tool_call` | Researcher/investigation and execution-specific role gating; reserves tool count | Extend deliberately, distinguish planner's frozen allowance |
| `services/research/research_artifacts.py` | User artifact list/get restrict visibility and kinds | Preserve even when linked through memory Sources UI |
| `services/research/research_recovery.py` | Versioned/idempotent manual retry via neutral transition | New invalidated binding surfaces through controlled retry/replan |

## 7. Web visible entry and existing state

- `apps/web/src/app/workspaces/[workspaceId]/page.tsx`: actual workspace shell, header tabs Chat/Notes/Settings, EvidenceViewer aside. No separate workspace-shell.tsx exists in the inspected tree.
- `components/settings-panel.tsx`: settings form, owner-only model config, evaluation and reindex composition. Proposed Memory section must be available to every member for their own records.
- `components/workspace-sidebar.tsx`: thread/create/archive and workspace navigation; current new thread is shared by current API contract.
- `components/chat-panel.tsx`: Chat/Research mode selector, ResearchRunPanel composition, model-settings/reindex recovery link.
- `components/research-run-panel.tsx`: run status/steps, conflict investigation, artifacts/evidence, report edit. Exact private-audience/status source flow needs integrated changes, not a detached demo page.
- `lib/workspace-view-state.ts`: runtime tabs `chat|notes|settings`, selection/evidence panel state. Keep memory editor state separate from persisted workspace.
- `lib/chat/{types,client,normalize,sse,submission}.ts`: actual chat DTO and SSE ownership; `use-chat.ts` orchestrates requests.
- `lib/research/{types,client,sse,server-route,server-route-policy}.ts`, `use-research.ts`: Research DTO and BFF allowlisting seams.
- Web AGENTS requires reading installed Next.js 16 documentation before implementation. This phase writes no Next code and makes no runtime UI claim.

## 8. Migrations and validation facilities

- `apps/api/alembic/env.py`: imports neutral persistence Base/models; database URL from API settings; compare_type/server_default enabled.
- Current latest revision inspected: `s3a4b5c6d7e8_workspace_model_configs.py`, down `r2f3a4b5c6d7`. Its downgrade deliberately raises until approved export. Follow cautious production rollback behavior.
- `r2f3a4b5c6d7_conflict_investigation.py`, `q1e2f3a4b5c6_research_adaptive_turns.py`, `p0d1e2f3a4b5_research_autonomy.py`: current Research evolution; new memory schema must use current chain.
- `c2e4f8a1b7d9_add_chat_message_branches.py`, `e6a7b8c9d0f1_repair_legacy_chat_message_order.py`: branch/order history. Preserve parent semantics; no timestamp-as-lineage backfill.
- `a8c9d0e1f2a3_add_lexical_retrieval_index.py` historically indexed document_chunks; current retrieval uses ContentUnit. Do not copy historical table names into new migration.
- `f2a4c6e8b0d1_add_embedding_current_scope.py`: current-index lifecycle background.
- Existing API tests: `test_chat_service.py`, `test_chat_router.py`, `test_providers.py`, `test_chat_import_boundaries.py`, `test_embedding_index_contract.py`, `test_embedding_current_scope.py`, `test_persistence_boundary.py`, `test_research_persistence_boundary.py`, `test_research_worker_budget_recovery.py`, `test_research_router_recovery.py`, `test_research_adaptive_recovery.py`, migration tests.
- Worker has `test_v5b_recovery.py` and broader Research tests; web `lib/chat/*.test.ts`, `use-chat.test.ts`, `lib/research/*.test.ts`; real e2e `authenticated-smoke.spec.ts`, `research-run.spec.ts`, `report-edit.spec.ts`, multimodal flows.
- `apps/web/package.json`: tsx node tests, eslint, Next build, Playwright. Add explicit `tsc --noEmit` acceptance; bundling alone is insufficient.
- `.github/workflows/ci.yml`: PostgreSQL pgvector 17, API/Worker locks/import smoke, pytest, Alembic upgrade/check, Worker fast/acceptance split. Add new neutral package to lock/deploy/import gates after approval.

### Same-run dispatch and checkpoint seams (source-inspected)

- `apps/worker/src/ai_pdf_worker/research/agents.py::_generate_json` calls injected generation; `research/adapters/generation.py::LedgeredGeneration._generate` resolves frozen role/IO/context, packs messages, hashes the final request, reserves/marks sent, calls provider with lease heartbeat, and reconciles failures/unknown usage. New-version compaction goes before the final hash/reservation at this common seam, covering each role, continuation and resume; it cannot be only a new-user-message hook.
- `research/adaptive_retrieval.py::research_adaptively` checkpoints turn/request before generation and reuses replayed results. `research/conflict_investigation.py` journals per-operation phases and uncertain operations. Context compaction must preserve those completed/unknown positions and must not restart handlers/tools to reconstruct history.
- `packages/research-persistence/src/citeframe_research_persistence/completion.py::_checkpoint_artifact` requires an execution snapshot, so it cannot blindly store planner context. Design uses a small memory-context reference on native Attempt plus immutable task snapshots; business publication/checkpoint identities remain native.
- Native planning `_ledger_and_limits` supplies tool limit zero; new planning allowance must be explicitly frozen, with old runs retaining zero. Provider logical call keys are free-form; summary purpose can live in the memory call sidecar without a new native provider-purpose enum.
- `apps/api/src/ai_pdf_api/schemas/chat.py::SelectedAssetScope` requires at least one asset ID. Mode2 needs an explicit none union, history envelope and request-key recovery; mode1 errors remain unchanged.

### Dependency-ordered candidate implementation

`design.md` §12 defines M1 instruction-only P1a (#42), M2 source activation, M3a shared adapters/counting/call prerequisites (#44), M3b atomic checkpoint persistence (#42 co-designed with #43) and compaction core (#43), M4 indexes, conditional M5 A1 audience, M6 native Research (#45), and M7 API/UI activation (#44/#46). Cross-stage and cyclic FKs are added only after target tables; no prebuilt scheduler or branch framework. API/Worker package/lock/deploy/import smoke must cover the same neutral adapter owner before summary use.

P1a includes only injected-authorized owner/workspace-private manual instructions, current/history/correct/deactivate/delete commands, intent/validity CAS, direct instruction support, idempotency and DB byte erasure with reference-safe metadata. No mounted API/UI, provider, index, native hooks, task checkpoints or Research contracts in this first subset. Later compaction storage adoption is one #42-owned transaction, never separately committed snapshot and live pointer updates.

## 9. Inspection limitations and handoff

Evidence is source reading/search and Git state inspection. No database was queried or migrated, no test suite/model endpoint was executed, and no browser walkthrough was performed. Structural existence/tests in the tree are not green runtime evidence. Some broad command output was truncated; substantive findings above were followed by focused symbol/range reads. Paths are repository-relative unless absolute. New paths/contracts in design.md are proposals and must not be described as existing code.

Before the first product PR: controller assigns overlap ownership; pin post40 SHA/migration head; independent reviewer verifies proposal coverage, privacy audience decision, source admission, full deletion/read paths and Research frozen scope; resolve design gates; rerun current tests and establish annotated baseline. Only then implement the approved slice.

### Current design disposition

Parent #41 and children #42–#46 are controller-created and linked; design slices map there. A1 output audience remains the sole escalated material existing-visibility expansion. A2/A3/A5/A6/A7 are in-scope engineering decisions for controller acceptance after independent review. A4 is application-cleanup operational configuration with recovery-safe TTL exclusions; no backup/provider-retention guarantee is introduced. Unknown/unsettled recovery and idempotency metadata cannot expire solely by age. Independent review delivered R2–R10 and the spec v3 §12 supplement R11–R16/O22–O30/CO01–CO12. Consolidated design §§2–13 contain corrections and §15 maps each finding; independent re-review is pending, with no developer closure claim. Controller reports Hegel PR47 externally blocked by image401; no branch/product authorization follows.
