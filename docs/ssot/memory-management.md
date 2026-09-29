# Memory management

Authority: `specs/v5/memory-management/spec.md` v4 §§13–14 and `design.md` §12.1. Private records are available only through owner-private management. Existing chat and Research remain workspace-readable; private content is excluded from every shared model/tool/summary/checkpoint/planning path, including when the requester owns that private content. No private native task/audience schema is added.

## P1a implementation boundary

The isolated #42 lane adds six instruction-only tables: instructions, sources, records, revisions, revision-source uses, and operation receipts. Neutral commands implement remember, current/history/source reads, correction with one successor, deactivation, deletion, and fresh-session request reconciliation. Membership and unarchived-workspace checks retain row guards through transaction completion; only recognized owner/member roles and exact record ownership are accepted. Shared purposes fail closed before reading payloads.

Delete clears conditions, content and content hash on every revision synchronously. Support identities, version history and idempotency metadata remain. Instruction bodies are retained while another non-erased dependent still legitimately uses them. An erased identity cannot receive a live successor revision; an explicit new request can create a fresh identity.

The migration is additive over `s3a4b5c6d7e8`, installing six tables and narrowly scoped integrity triggers. Downgrade refuses any populated memory table and retains shared extensions. No source backfill, native mutation hook, API/UI activation, provider calls, index/job or compaction schema is included.

## Delivery state

Contract/scaffold: commit `eac4de4`, owned solely by #42. Provider #44 consumes `citeframe_contracts.memory` and owns only neutral adapters and their tests. Persistence candidate and evidence are recorded in `specs/v5/memory-management/lane42-report.md`. Independent acceptance is owned by `reviews/issue42-implementation.md`; test counts alone do not accept later runtime/UI/model stages.

Automatic shared-task compaction remains a later required delivery under the full specification. P1a does not activate it or complete issues #42/#41.

## Shared-history contracts and independent GenerationImage delivery

Current history helper/test/workflow received original independent bounded acceptance, including fresh full42-case source review and controller101localpass. Original historic test bytes were not retained; no historical loader-only equivalence is claimed. GenerationImage is an independently validated type only; GenerationMessage remains four fields without image consumer activation. Source authority, DB/index/hybrid, native runtime and real UI remain mandatory follow-ups. Separate branch work/issue42-shared-source-contracts preserves PR48 original893de951. This slice stacks reviewed43 compaction dependency; frozen hosted101 pending.
## Frozen neutral-core acceptance — 2026-09-29

Original independent reviewer accepted exact45-file manifest A9C9385497F7092DC958ABFA218C3AEA13D089C97EBF621E92D46A24334375FB. F43-I3/I4 closed through pre-write historical interval authentication and absent/valid-only summary persistence under existing call locks; no schema expansion in that correction. Current independent22+176 targeted cases passed;508 collected only. Earlier486 independently executed cases apply to old44-file identity. Controller independently reran current66 cases in131.65s with zero manifest changes, ownPG stopped. Exact evidence and limits remain in reviews/issue43-compaction.md and evidence/issue43/controller-i3i4-verification.md.

Controller may commit this reviewed neutral core and integrate accepted PR49 dependency. No actual Chat/Research route, whole-source/index, semantic-model or visible-UI acceptance is claimed. CI and exact dependency integration remain required. A1choice2 and same-run automatic continuation requirements remain unchanged. All parent/child issues stay open.

## CI integration repair accepted — 2026-09-29

Original reviewer accepted fixture E6A33A64 with106real-PG cases and boundary5FC30A4E with20cases plus27DDL/12FK mutation probes. Controller independently ran both boundary modules at the same hash:20passed1.57s, zero skip, existing Starlette warning. This is compiled metadata/import evidence, not an additional PostgreSQL run. Historical fixture uses fullt4; current runtime uses fullu5. Frozen source snapshot itself contains81tables/97indexes; approved prior deltas produce85native tables/97indexes. The unchanged45core identity remains accepted. Prior local0315a735 corrects migration head assertions. Push these reviewed integration fixes for fresh complete CI; actualChat/Research/UI remain unaccepted.

## HC02 import boundary correction accepted

Originalreviewb3c40990 accepted test1d17c3ad: exactlythree same-package relative imports,16rejectcontrols and isolated -I-S-B checkout/type-identity checks. Reviewer25API+2Worker+101pure passed; controllerindependent25API passed0.23s atsamehash. Existingdeploy/lock/export/Docker baselines unchanged. This fixes only the third API failure; inherited43a2a pair remains pending. Index candidate/canonicaldelta are excluded from this commit and retain independent gates.
