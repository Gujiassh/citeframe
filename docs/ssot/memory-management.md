# Memory management

Authority: `specs/v5/memory-management/spec.md` v4 §§13–14 and `design.md` §12.1. Private records are available only through owner-private management. Existing chat and Research remain workspace-readable; private content is excluded from every shared model/tool/summary/checkpoint/planning path, including when the requester owns that private content. No private native task/audience schema is added.

## P1a implementation boundary

The isolated #42 lane adds six instruction-only tables: instructions, sources, records, revisions, revision-source uses, and operation receipts. Neutral commands implement remember, current/history/source reads, correction with one successor, deactivation, deletion, and fresh-session request reconciliation. Membership and unarchived-workspace checks retain row guards through transaction completion; only recognized owner/member roles and exact record ownership are accepted. Shared purposes fail closed before reading payloads.

Delete clears conditions, content and content hash on every revision synchronously. Support identities, version history and idempotency metadata remain. Instruction bodies are retained while another non-erased dependent still legitimately uses them. An erased identity cannot receive a live successor revision; an explicit new request can create a fresh identity.

The migration is additive over `s3a4b5c6d7e8`, installing six tables and narrowly scoped integrity triggers. Downgrade refuses any populated memory table and retains shared extensions. No source backfill, native mutation hook, API/UI activation, provider calls, index/job or compaction schema is included.

## Delivery state

Contract/scaffold: commit `eac4de4`, owned solely by #42. Provider #44 consumes `citeframe_contracts.memory` and owns only neutral adapters and their tests. Persistence candidate and evidence are recorded in `specs/v5/memory-management/lane42-report.md`. Independent acceptance is owned by `reviews/issue42-implementation.md`; test counts alone do not accept later runtime/UI/model stages.

Automatic shared-task compaction remains a later required delivery under the full specification. P1a does not activate it or complete issues #42/#41.

## Native settlement preparation delivery — 2026-09-29

This isolated follow-up starts from PR51 e7b3e86ae4de70764c4d17bcbe272686c1c8063a on work/issue45-memory-settlement. Original developer agt_d03b4a29 and independent reviewer agt_26025b40 accepted the exact bounded native tools.py transaction-neutral extraction. Public error/rollback/lock/field/flush semantics remain unchanged; the private inner command supports future caller-owned atomic composition and is not activated here. Controller independently ran56 tests including55PG,23.59s, owncluster stopped. Reviewer ran120+11 additionalPG scenarios; no Alembic parity claim follows from ORM-created fixture tables.

Dedicated workflow E17B81A4 independently accepted after F45-CI-1 invalid job runner context and F45-CI-2 empty-reason XPASS fixes. Reviewer actionlint0 and actual5 guard probes; controller actionlint0. Earlier reviewer120 inlinePG pass remains prior-workflow evidence. New hosted frozen install/job remains pending; local uv startup was denied and not replaced. Full Research schema/source/reclaim/every-dispatch and same-live-Attempt compaction/UI remain unaccepted. Existing PR51 stays pure projection and unchanged.
