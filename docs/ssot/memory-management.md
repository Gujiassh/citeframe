# Memory management

Authority: `specs/v5/memory-management/spec.md` v4 §§13–14 and `design.md` §12.1. Private records are available only through owner-private management. Existing chat and Research remain workspace-readable; private content is excluded from every shared model/tool/summary/checkpoint/planning path, including when the requester owns that private content. No private native task/audience schema is added.

## P1a implementation boundary

The isolated #42 lane adds six instruction-only tables: instructions, sources, records, revisions, revision-source uses, and operation receipts. Neutral commands implement remember, current/history/source reads, correction with one successor, deactivation, deletion, and fresh-session request reconciliation. Membership and unarchived-workspace checks retain row guards through transaction completion; only recognized owner/member roles and exact record ownership are accepted. Shared purposes fail closed before reading payloads.

Delete clears conditions, content and content hash on every revision synchronously. Support identities, version history and idempotency metadata remain. Instruction bodies are retained while another non-erased dependent still legitimately uses them. An erased identity cannot receive a live successor revision; an explicit new request can create a fresh identity.

The migration is additive over `s3a4b5c6d7e8`, installing six tables and narrowly scoped integrity triggers. Downgrade refuses any populated memory table and retains shared extensions. No source backfill, native mutation hook, API/UI activation, provider calls, index/job or compaction schema is included.

## Delivery state

Contract/scaffold: commit `eac4de4`, owned solely by #42. Provider #44 consumes `citeframe_contracts.memory` and owns only neutral adapters and their tests. Persistence candidate and evidence are recorded in `specs/v5/memory-management/lane42-report.md`. Independent acceptance is owned by `reviews/issue42-implementation.md`; test counts alone do not accept later runtime/UI/model stages.

Automatic shared-task compaction remains a later required delivery under the full specification. P1a does not activate it or complete issues #42/#41.

## Geometry bounded delivery

At base7d6be8a, original developer delivered geometry-only implementation and dedicated frozen Linux workflow. Independent original reviewBC5B2A72 accepted exact product62B89093/test538AB2C3/workflow82600A9C; reviewer119plus96PDF/512Decimal/14type controls. Controller1191.45s and exactworkflow1192.88s, actionlint0. No native source/decoder activation, Linux outcome pending, launcher/build still outside authorization. This follow-up branch preserves PR52 head. Actual Chat/Research same-run runtime and UI remain required.
