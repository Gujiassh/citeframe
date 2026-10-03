# Issue42 index activation — native integration contract

Status: design only, targeted review pending. 2026-09-29. No source issuer, index activation, route or schema is enabled by this document.

## 1. Baseline and delivery boundary

This integration applies the accepted `issue42-shared-sources.md` §§4–9 (SHA256 `2befea01c88ff5fc7d3f8f54c23c9f22b9bb850dd5619dbf819d1091dcf3c042`) and `issue42-index-canonical-delta.md` (`3e8a8f2f98917545df3bafe19b83869db6dec32ee0b27a8c9f32f49b71974625`). Their source/version/range, strict v1/v2 runtime policy, empty-result and canonical profile contracts remain authoritative.

Pending code review freezes `models/memory_index.py` at `ec63758e965f39bffdd7e36ec08dbc9f32bfa895c88c396d04d8a4b1d23d723a` and `tests/test_history_index_postgres.py` at `eea4224239b8f799d4d6dcb3c965961fc1a56efdc6ae93a897cfc453c4d95a2d`. Its 138-test local evidence establishes declared-set storage constraints; real native enumeration, source authorization and mutation retirement remain integration work. The earlier 39-test partial run retains its original scope.

Controller reports PR54 CI1 `4fd450c` with API 1127 passed/6 skipped, PostgreSQL 1670 and dedicated 508. These are controller-supplied results, not a local rerun. Controller owns the exact dependency merge after frozen review; no sibling imports or uncommitted dependency assumptions enter runtime acceptance.

## 2. Native enumeration and exact public adapters

All model paths below are under `packages/backend-persistence/src/citeframe_persistence/models/`. Enumeration starts from native tables, including eligible originals that have never been registered. It may not enumerate only `memory_sources`. For each enabled kind, build one complete workspace corpus manifest, then apply the issued task's branch/frozen scope as a separate query projection. A branch ID never stands for workspace corpus generation. Exceeding the accepted set/byte/guard bounds fails the build explicitly; truncation cannot activate a generation or report zero hits.

| Kind / native joins | Exact original and identity | Admission before content hydration |
|---|---|---|
| `chat_message`: `chat_message.py` joined to `chat_thread.py` | Full `content`; existing monotonic `compaction_revision` and exact native tuple; only completed user/assistant rows in public history | Same live workspace and unarchived thread; current-branch projection follows issued ancestry. Workspace projection includes eligible messages on other branches/threads. Citation/input-evidence dependencies must remain readable. No message-author inference from thread creator. |
| `note`: `note.py`, `note_source.py` | Full `body_md`, title kept separate; successor adds accepted monotonic note revision, including dependency/lifecycle changes and ABA protection | Unarchived note; all NoteSource asset/representation/locator dependencies satisfy shared-reader and current-source rules. Null citation linkage does not erase asset provenance. Creator/editor IDs are audit metadata. |
| `content_unit`: `content_unit.py`, `asset.py`, `asset_representation.py`, `evidence_locator.py` | Full `text_content`; exact unit/asset/representation/locator, processing generation, index version, parser/generator identity and body hash | Asset ready and not deleting/deleted, current generation/index; every join agrees on workspace and asset identity. Unit-relative offsets do not reuse representation `char_start`/`char_end`. |
| `research_artifact`: `research_artifact.py`, `research_run.py`, producing step/attempt and execution/version/claim/evidence joins | Exact verified object bytes, strict UTF-8 decode, no JSON rewriting; immutable artifact ID/hash/schema and producing provenance | Native `visibility=user` and allowlist `research_plan`, `evidence_bundle`, `conflict_report`, `final_report`, `trace_export`; live run/workspace, unexpired retention, valid producing/frozen provenance and recursively readable dependencies. Internal artifacts are excluded. Supersedes linkage alone does not make an older immutable artifact unavailable; actual lifecycle/retention rules decide. |

Existing read boundaries are `apps/api/src/ai_pdf_api/routers/{chat,notes,assets,research}.py`, `services/research/research_artifacts.py::{list_artifacts,get_artifact}` and `research_views.py::artifact_detail`. The adapter must reuse their provenance rules and verified artifact-byte path without routing memory-service back through API imports. API membership alone and `visibility=user` alone are insufficient shared-output proofs.

The issuer verifies a policy under which the original and every dependency are readable by all workspace output readers, including future members; it rejects custom/owner-private/unknown restrictions before body, title, snippet, score/count or object fetch. Metadata discovery stays internal. All memory records remain private: shared `search_memory` is explicitly policy-excluded with zero private revision reads. No new audience schema or evidence promotion is introduced.

For every resolved text, check native version and UTF-8 hash before slicing. Returned body is exactly `original[start:end]` in Unicode code points. Index chunks use the accepted 1200/200 profile without normalization or title concatenation. Empty originals retain a real source reference and zero chunks; an empty manifest requires successful exhaustive enumeration. Binary asset originals remain on authorized native file/locator routes. They are not reconstructed from content units.

## 3. Single authority and real search path

The existing checkout's `packages/memory-service/src/citeframe_memory/compaction/sources.py` currently reads internal chat ancestry (completed **or failed**) and frozen Research evidence. Public completed-chat/note/unit/artifact access is a distinct approved predicate added by #43; internal compaction semantics stay unchanged.

Required path: native transaction-issued HistorySession → metadata authorization and corpus/query scope → #43 `repository.py::register_source` exact allocator/replay → native adapter verification → accepted pure `history/ranges.py` and `history/search.py` → #43 ToolArchive/use graph → current request recount and journal dispatch. #42 contributes public native resolver/enumeration implementation only under a targeted future file grant. It creates no parallel source registry, issuer, proof DTO, checkpoint renderer or request-count policy.

#43 owns `guards.py`, `sources.py`, `repository.py::{capture,adopt,checkpoint_summary}`, `archive.py::ToolArchive.persist`, and `journal.py::{reserve,mark_sent}` consumption of the same issued predicate. Legacy v1 tasks retain history-disabled behavior; only native-owned strict v2 policy can enable history. Management authorization cannot authorize task adoption.

Search uses an active compatible manifest, authorized projection and accepted simple FTS/trigram/RRF profile. A missing/stale requested generation returns `index_not_ready`; no silent empty corpus or mode substitution. Archive actual generation dependencies even for zero hits. Policy exclusion and exhaustive zero-hit outcomes remain distinct and permit empty source tuples without artificial edges. Real reads retain their real refs.

Each page reauthorizes and recounts the current complete GenerationRequest/ModelConnectionSnapshot through #43 policy and actual counter identity, archiving that request hash. Stable source/window authority and fixed endpoint survive a new tool ID, request hash or valid profile on a later page. Preserve accepted one-time expansion, shrink-to-fit, terminal-window and progress rules; do not restart page one when dispatch framing changes.

## 4. Activation, native writers and atomic retirement

Use the approved order: workspace → native parents/rows → registry sources → existing consumers → index manifests/entries, with deterministic identity ordering and bounded lock failure. Workspace serialization is shared by **all relevant writers**, so insertion of a new eligible original cannot race past activation. Row locks on already enumerated sources alone do not protect corpus completeness.

Build work may occur outside the final transaction. Final activation locks the workspace/native scope, re-enumerates the entire native corpus, registers/verifies exact sources, compares the complete canonical source_set and profile_snapshot, verifies all original slices/chunk counts and generation membership, and atomically retires the prior generation and activates the candidate. Object/network work stays outside held DB guards: artifact bytes are fetched after metadata authorization, then metadata/hash/retention are revalidated at the guarded publication point. Candidate failure leaves the previous still-valid generation unchanged.

Exact writer hooks requiring native-owner grants:

- `apps/api/src/ai_pdf_api/services/chat.py::{prepare_chat,finalize_chat,fail_chat}` and `routers/chat.py::archive_thread`: message insertion/completion/content/status/parent changes; thread archive/restore and branch changes. Branch changes invalidate issued query authority; only corpus-affecting changes retire the corresponding workspace manifest.
- `services/notes.py::{create_note,update_note,archive_note}` and NoteSource INSERT/UPDATE/DELETE: note content/title/dependency/lifecycle revision. Exact no-op keeps revision; real mutation, restore or delete/reinsert gets a fresh monotonic stamp. `updated_at` is not the revision oracle.
- `routers/assets.py::{retry_asset,reindex_asset,delete_asset,retry_delete_asset}`, `services/ingestion.py::{process_ingestion_job,process_delete_cleanup,_activate_current_embeddings}`: status/generation/index/deletion transitions. Retirement starts with `deleting`, before remote cleanup. Current `delete_asset` locks Asset before workspace; its future wrapper must acquire workspace first.
- Content replacement/purge paths: API `modalities/{pdf,image}_ingestion.py`; Worker `ingestion/{html,docx,document,audio,pptx,video,xlsx}_ingestion.py`. SQL coverage must include ContentUnit, AssetRepresentation and EvidenceLocator mutations even when invoked outside these functions.
- Research publication: `packages/research-persistence/src/citeframe_research_persistence/{plan,completion,publication,publication_finalize}.py`, artifact/run lifecycle mutations and producing/dependency changes. Retention expiry is checked on every read/adoption/dispatch and activation even without a SQL mutation; no existing expiry scheduler is assumed. An expiry/cleanup writer must retire affected generations before deleting metadata/objects.
- Workspace archive and membership changes: native `workspaces`/`workspace_memberships` SQL hooks and issuer revalidation; revocation must suppress further reads/dispatch. Existing membership insertion does not grant private records shared visibility.

#43's **single successor migration** owns integration of the two index tables, native revision/event triggers, registry kind/check deltas and invalidation functions. Its actual revision ID is assigned by #43 after reconciling the current migration head. Do not edit shipped t4/u5 or create a competing successor. API hooks improve lock order; SQL enforcement also covers direct writes and bulk cleanup.

Within the mutation transaction, discharge pending snapshot INSERT completeness and deferred coverage/use/pointer constraints at the approved barrier **before** native mutation. Then update/tombstone current sources, retire affected corpus manifests, remove affected derived index payload across generations, and apply reverse closure through the existing source/snapshot/tool-result graph. Suppress dependent snapshots, checkpoints and in-flight saved results; zero-hit archives are included through generation dependence. Use only existing graph edges, never a nonexistent `used_revision_id`. No new adoption is allowed after the barrier. Separate adoption statements followed by mutation are supported; both same-data-modifying-CTE probes must reject.

Normal change/deletion preserves permitted lineage metadata while denying stale hydration; privacy erasure additionally removes sensitive derived payload synchronously under the accepted erasure rules. Commit exposes neither a current stale index nor an admissible stale result. Object deletion may retry after this DB denial boundary. `mark_sent` remains dispatch linearization: pre-send invalidation prevents transport; already sent bytes cannot be recalled.

## 5. Owner handoff and direct acceptance

1. #42: preserve frozen storage candidate; after review/grant, implement native metadata enumeration, exact public resolvers and build/search integration in new owned modules. First native milestone is completed current-branch chat exact paging; label it explicitly as that subset.
2. #43: issue/consume history authority, extend the sole registry/graph and own the unique successor migration and atomic invalidation. Review the native writer lock adjustments together with their API/Worker/Research owners before editing them.
3. API/Worker native owners: wire those explicit writers and eventual tool entrypoints to the accepted seam. Full workspace notes, content units and Research artifacts remain mandatory follow-ons. Hybrid additionally requires real compatible query/document embeddings and truthful mode reporting; no paid backfill or evaluation is authorized here.

Required native PostgreSQL oracles, beyond the frozen storage tests:

- Seed real native originals in multiple threads/branches and all four kinds, including never-registered rows. Compare exhaustive expected UUID/version/hash sets against the activated manifest; unavailable adapters, overflow and unauthorized dependencies must not become successful empty corpora.
- Spy object/body hydration for requester-only, wrong workspace, revoked membership, archived, expired, internal and dependency-restricted cases: zero prohibited hydration and no title/score/count leak. Shared memory search reads zero private revisions.
- Read full originals through multiple pages (emoji, combining marks, CRLF, empty bodies); exact concatenated slices and hashes, no duplicate/drop, fixed terminal endpoint. New per-page request/profile/counter identity does not reset source/window authority; each page archives its own full request hash.
- Race activation against native insert, completion, note ABA/restore, dependency change, asset generation switch/delete and artifact expiry; test API writers and direct SQL. Exactly one valid outcome commits; no partial active generation or stale permitted result survives.
- In one transaction adopt then mutate with the pending barrier; inspect direct/transitive sources, zero-hit archive, checkpoint and saved result suppression. Both same-statement CTE variants reject. Race deletion against archive/adopt/mark_sent; assert transport-call count at the dispatch boundary.
- Upgrade populated real predecessor DB through the sole successor, preserve native evidence/DDL invariants, test rollback guard, and prove no production index activation merely from importing models. Lexical relevance evidence is separate from synthetic-vector SQL checks and later embedding integration.

This document records proposed integration and acceptance boundaries only. No new runtime or PostgreSQL execution occurred in this design slice.
