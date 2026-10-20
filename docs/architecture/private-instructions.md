# Private instructions

`citeframe-memory-service` provides persistence commands for manually supplied,
owner-private instructions. This foundation mounts no HTTP routes or UI and does
not inject private instructions into Chat or Research.

## Access boundary

[MemoryCommands](../../packages/memory-service/src/citeframe_memory/commands.py)
requires a `management` purpose, `private` output audience, a live workspace,
recognized owner/member membership and exact record ownership. Workspace and
membership row guards remain held through transaction completion. Current,
history, source and reconciliation reads use the same boundary.

Private instructions are excluded from shared Chat/Research prompts, tools,
summaries, checkpoints, planning and output, including for their owner. Private
management access grants no shared retrieval or task-adoption authority.

## Storage and commands

The additive migration
[`t4b5c6d7e8f9`](../../apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py)
follows `s3a4b5c6d7e8` and installs six tables:

| Table | Purpose |
| --- | --- |
| `memory_instructions` | Explicit operations, raw instruction content and attribution |
| `memory_records` | Stable record identity, current version and successor linkage |
| `memory_revisions` | Versioned content, conditions, intent and validity |
| `memory_sources` | Exact instruction source identity and current availability |
| `memory_uses` | Revision-to-source support and confirmation relationships |
| `memory_operations` | Idempotency keys, request fingerprints and receipts |

Remember, correct, deactivate and delete run in transactions. Mutations of an
existing record require its exact expected version. Correction supersedes its
predecessor and creates one successor. Terminal states and database constraints
prevent resurrection or a second successor. Request/key replay must match the
original operation fingerprint; reconciliation reads the committed receipt from a
fresh session after an uncertain acknowledgement.

[Admission](../../packages/memory-service/src/citeframe_memory/admission.py)
scans content, condition subject and applicability independently for its finite
credential patterns. Rejection occurs before new instruction construction or DML,
after authorization, replay, version and terminal-state checks. It preserves the
original text and returns `sensitive_content_unsupported`. Encoded credentials and
patterns outside that finite predicate are outside its detection contract.

## Invalidation and erasure

Source invalidation marks affected revisions invalid without rewriting their
content. Deletion synchronously clears content, hashes and conditions from every
revision of the deleted record. History and replay retain audit identities and
receipts without returning erased statements. An instruction body needed by a
different live dependent is retained until its last dependent is erased; this does
not restore the deleted record. Exact source reads reject unavailable or erased
instructions.

Downgrade refuses populated memory tables and leaves shared extensions intact.
The foundation adds no source backfill, native mutation hook, history index,
background job, provider adapter or compaction checkpoint schema. Its PostgreSQL
integrity guarantees require the shipped migration and triggers; SQLite metadata
compatibility does not enable memory commands there.
