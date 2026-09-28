# Issue43 native prepared-chat lifecycle — bounded exact amendment

Status: **Awaiting controller/original independent reviewer approval; affected schema edits withheld.**

Approved Option A baseline remains `ED10B657B3DE9862D3601A8917B798AADE08B21E18CB48D66448BC5D2EEEE1E9`. This amendment leaves its mutation fence, accounting boundary, privacy rules, ownership and atomic transaction unchanged.

## Native evidence and acceptance gap

`apps/api/src/ai_pdf_api/services/chat.py` lines171–188 prepares a completed user message and a streaming assistant child. It leaves `ChatThread.active_message_id` unchanged; first-turn active leaf is NULL. Finalize/fail assigns the assistant leaf at lines309/338. Existing completed-chat fixtures do not establish this pre-dispatch lifecycle.

Approved `design.md` §6.1 explicitly declares `chat_memory_executions.anchor_leaf_id ID?` and snapshot `anchor_leaf_id ID?`. The exact lane delta and implemented new schema require a nonnull execution anchor and a nonnull chat snapshot anchor. Current `create_chat` uses the native active leaf, so first-turn owner creation fails. Current source ancestry excludes the newly prepared user when the active leaf still points to an older message.

## Exact requested correction

| Owned file / boundary | Precise correction |
|---|---|
| `packages/backend-persistence/src/citeframe_persistence/models/memory_context.py` | Set only `chat_memory_executions.anchor_leaf_id` nullable. In `ck_task_snapshot_owner`, remove only the chat arm's `anchor_leaf_id IS NOT NULL` condition. Preserve thread/Research XOR, all native FKs and other constraints. |
| `apps/api/alembic/versions/u5c6d7e8f9a0_inloop_compaction.py` | Match those two changes in the new successor DDL; predecessor remains `t4b5c6d7e8f9`. No historical migration modification or follow-on chain split. |
| Owned `compaction/guards.py`, `sources.py`, `repository.py` | Preserve anchor meaning as captured `thread.active_message_id`, including NULL. Authorize designated current-task ancestry from existing execution assistant→user→selected native parent IDs. Never admit streaming assistant content as a source. Keep complete thread revisions/membership and captured native active leaf in CAS fingerprint; unrelated leaf switches reject. No native raw-record mutation. |
| NEW `test_compaction_native_lifecycle.py` and lane evidence | Reproduce first-turn NULL leaf and later-turn old active leaf with streaming assistant; verify current-user exact readback, neutral initial/continuation admission, retained native raw fields, late branch-switch rejection, finalized historical checkpoint behavior. |

No additional existing-file transfer, native writer edits, private/audience mode, provider ABI, independent context head, frozen evidence expansion or long-term candidate path is requested.

## Atomic transaction unchanged

Workspace/member/native-thread/current-execution and complete bounded message guards → exact lawful current-task sources → snapshot with nullable captured anchor + ordered coverage + direct/raw uses → real execution pointer/context-version CAS → deferred manifest/scope integrity → commit receipt. Generation/object IO stays outside guarded DB transactions. The original sequence-based Option A metadata fence remains unchanged.

## Approval boundary

This amendment changes the precise reviewed nullability predicate. It must not be silently implemented under the prior hash. The remaining neutral implementation and verification can continue; actual prepared-chat acceptance remains blocked until this amendment is approved and implemented. API/Worker/UI wiring still belongs to #44/#45/#46.
