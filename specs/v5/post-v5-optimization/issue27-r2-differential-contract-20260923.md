# Issue 27: explicit R2 differential contract

## Candidate scope

Prerequisite PR #28 retains the frozen 41-path extraction (38 R2 files, two minimal W1 files, and four locale lines). Additional approved repairs cover final adoption authorization/retry provenance, the actual nullable Step input lease contract, initial panel retry, and the current-candidate A2 clock/storage/oracle adaptations. No architecture #26 changes, historical fixture text/hash changes, or inherited unrelated dirty files are included.

## Exact delta manifest

The baseline remains `d1b5945e977445e4db6bf56ef54cf61607ead2e2`. Both executions use the same frozen Python and SQLite SQL clock (2026-08-24 04:00 UTC). Production lease durations, token checks, recovery and storage-adoption gates remain active.

| Location | Allowed delta | Production cause / oracle |
| --- | --- | --- |
| transitions DB | New `research_publication_intents`, exactly empty | New saga table; every pre-existing table/column/row remains strict |
| process DB | One intent bound to final artifact/publisher/run/approved snapshot | `publication_prepare`, `publication_finalize`; complete lifecycle below |
| final Artifact.object_key | `research/{workspace}/{run}/{artifact}/final.md` → same prefix + `/publication/1/final.md` | Generation-owned PUT and adoption; Artifact ID and every other field unchanged |
| raw and terminal object payload maps | Exactly that one key rename | Exact report bytes/hash/size remain unchanged; all stored Research objects correspond to Artifact ownership, no unexplained keys |
| final publisher step_succeeded, final artifact_published, run_completed | Exactly three newly generated event UUIDs differ | Intent allocation adds one UUID before terminal events. Unique `(run_id,dedupe_key)` establishes a bijection, exact event type/seq/payload/references and wire→DB IDs are checked. No ordinal UUID matching |
| scheduler | Baseline 3 business calls; candidate 8 one-attempt calls plus one identified maintenance call, then False | Existing A2 scheduler split plus R2 due-terminal sweep. Model calls, ledger, events, run and other DB rows remain unchanged across maintenance |
| committed intent maintenance | `last_error_code`: null→`publication_terminal_sweep_pending`; `orphan_sweep_after`: NOW→NOW+30s | First terminal sweep schedules its observation. All remaining intent fields and all business rows unchanged; next frozen-clock call must be False |

Event IDs are public SSE `eventId` fields. This mapping only covers separately generated cross-version fixture events; SSE `id:` remains the original sequence cursor. Same persisted events are checked across repeated publication and a fresh reader session using production serialization; no historical event IDs are migrated or regenerated. Generation keys are storage fields, not artifact DTO fields.

## Intent fields and lifecycle

`a2a_r2_publication_oracle.py` constructs the entire expected row, rejects extra/missing fields, and checks these groups:

- Identity/ownership: `id`, `workspace_id`, `run_id`, `step_id`, `attempt_id`, `execution_snapshot_id`, `logical_key`, `artifact_id`, `committed_artifact_id`.
- Storage/rendering: `object_prefix`, `current_object_generation`, `current_object_key`, `adopted_object_generation`, `adopted_object_key`, `content_type`, `render_schema_version`, `payload_bytes`, `byte_size`, `content_sha256`, `selection_json`, `selection_sha256`.
- Lifecycle/fence: `status`, `state_version`, `claim_generation`, `claim_owner`, `claim_token_hash`, `claim_expires_at`, `claim_heartbeat_at`, `next_reconcile_at`, `reconcile_attempt_count`, `last_error_code`, `orphan_sweep_after`, `created_at`, `updated_at`, `resolved_at`.

A read-only after-commit observer records five actual committed DB/object snapshots: prepared(1), uploaded(2), committing(3), committed(4), committed terminal sweep(4). Originating attempt worker identity and creator membership are captured from their persisted rows; they are not inferred from UUID order. Upload/committing cannot change business rows. Prepared has no final object; every later phase contains the exact adopted bytes. Current generation/claim fields clear only at commit. Report data preserves all raw database rows, schema column lists, lifecycle states and original reports, with independent SHA-256 digests. The existing A2 process-worker identity normalization is checked against its raw projection; no new ID/hash/time scrub is applied.

The happy-path differential proves the above exact lifecycle only. Failure/reconciliation/compensation/orphan behavior is separately executed by `test_research_worker_evidence_publication.py` and `test_research_publication_adoption.py`: lost prepare/final commit responses, origin lease expiry and fencing, revoked creator before/after PUT, cancelled adoption, two-pass compensation, foreign object ownership, missing adopted objects, late orphan PUT and replay projection tampering. These fixture tests do not prove PostgreSQL lock behavior or a real object store/process crash.

## Result and negative controls

The new report schema separates `rawEqual` (expected false), `historicalInvariantsEqual`, `r2DeltaValid`, `unknownDifferences`, and `accepted`. Legacy `equal` remains raw equality and is false. The original A2 historical evidence is unchanged. Unknown tables, columns, fields, bytes, IDs, hashes, timestamps, extra steps and accounting remain failures.

Live-report mutations cover report bytes, evidence relation, revoked authorization, foreign intent ownership/snapshot/claim worker/token, extra business step, duplicate accounting, unknown table/field/empty-table column, raw-only tamper, orphan object, event wrong run/dedupe/payload/duplicate/missing/wire ID, extra maintenance call/provider invocation/budget change, and unexplained timestamp. Existing wrong facade, real pytest-plugin pollution and lease fencing controls remain active.

## Nullable input and panel retry

A null Step input uses exactly the existing lease fallback `sha256(step.id)`; both origin and current attempt hashes must equal that value. Explicit inputs remain exact. Tests cover valid single/retry cases, independent origin/current mismatches, foreign run/workspace/snapshot/Step, invalid tools and unfinished origin.

The Web change only restores exported refresh when no run has loaded: list, choose latest, load detail; errors and empty states recover. Existing selected-run refresh is retained. Workspace/selection request guards discard late first-load detail results. Three mocked-browser flows cover initial list failure, initial detail failure and retry to empty; typecheck/lint are separate. A visible real-service walkthrough and additional workspace-race evidence remain open.

## Verification / gates

At the working candidate: API adoption/publication/persistence/migration/storage regression 152 passed; executable A2 runner/facade/pollution 3 passed; mocked-browser retry 3 passed; Web tsc and changed-file lint exit 0. Same-HEAD rerun and CI follow the commit. Independent Hubble review, actual PostgreSQL saga recovery/concurrent permission ordering, real object-store crash behavior and service-backed UI remain required. No merge is authorized by these local results.
