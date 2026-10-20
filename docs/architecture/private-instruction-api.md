# Private instruction management API

The API mounts manual, owner-private instruction management at `/v1/workspaces/{workspace_id}`. The router composes the existing private instruction commands and transaction-bound query projection. It does not enable instruction reuse in shared Chat or Research, model-generated extraction, general memory search/indexing, or a browser interface.

## Endpoints and request identity

| Method and relative path | Behavior |
| --- | --- |
| `POST /memories` | Create an explicit instruction-backed memory. |
| `GET /memories` | List the current owner's records using status, workspace scope, limit, and cursor. |
| `GET /memories/{id}` | Read the current authorized resource. |
| `GET /memories/{id}/revisions` | Read authorized revisions with bounded pagination. |
| `POST /memories/{id}/corrections` | Create a correction successor with an expected version. |
| `PATCH /memories/{id}` | Deactivate using `intent=inactive` and an expected version. |
| `DELETE /memories/{id}` | Erase using an expected version. |
| `GET /memories/operations/{id}` | Recover content-free operation metadata. |
| `GET /memories/requests/{request_id}` | Recover by the original request identity. |
| `POST /sources/read` | Read one exact, current owner-private instruction source. |

Mutations require a canonical UUID `requestId` and an `Idempotency-Key` of 8 to 128 printable non-space ASCII characters. Expected versions are strict positive integers. The commands reconcile the original request/key and payload before creating a new operation; replay retains its original `resultVersion`, while readback projects the current authorized resource. Reusing an identity for different input is a conflict. Correction returns the committed successor and predecessor identity. Deactivation and deletion do not grant a generic metadata-edit operation.

Inputs reject extra fields. The caller cannot choose actor, owner, audience, or confirmation authority. Create accepts only workspace scope and an empty `sourceRefs` list; it records the authenticated explicit instruction. Content is limited to 4,000 characters, condition subject to 256, and applicability to 2,000. Dates require timezone-aware ISO values. Kinds are preference, constraint, fact, and decision; only constraint and decision may be pinned. Content, condition subject, and applicability reject U+0000 with 422 `invalid_request` and `retryable=false` before command writes. Ordinary Unicode and newline characters retain their exact values. These are manual instruction contracts, independent of shared-history or image-source DTOs.

## Authorization, errors, and rendering

Internal-token/user authentication and workspace membership dependencies establish request identity. Each use case then opens a fresh PostgreSQL session and reauthorizes the workspace, recognized member role, actor, private audience, and management purpose under row locks. Record, source, and operation lookups include workspace and actor/owner. Workspace ownership does not permit reading another member's private records.

For valid JSON, authentication and the workspace dependency precede structural schema validation. Invalid JSON syntax can return 422 before authentication. Unsupported-role requests with invalid fields can fail structural validation before the fresh role guard; valid input reaches the nondisclosing authorization result. Unknown or cross-owner objects return 404. Only a freshly guarded owner can receive erased/stale-source 410 or conflict/terminal 409 with current-version metadata.

Success payload validation, JSON serialization, and owner-only domain-error rendering occur inside the fresh authorization transaction while its locks remain held. Mutation conflict/terminal metadata is read and rendered through that same guarded path after the failed command rolls back. Responses contain completed bytes before the session closes; ASGI transmission occurs after the transaction exits. Application integration must preserve this lock-through-render boundary without extending database locks across network delivery.

Errors use fixed codes/messages without submitted content, raw SQL, or underlying exception text. Request-ID echo is allowed only after the dependency passes and the identifier is valid. Unknown service errors map to a generic retryable 503. A failed commit acknowledgement or late readback failure can produce `outcome_unknown`; it does not prove the mutation rolled back. Recover through the original request/operation identity rather than inventing a new mutation. Authorization can be lost after commit, in which case a denied receipt does not undo the operation.

## Admission, erasure, and unavailable content

Before fresh instruction/source/record/revision/use/operation DML, the existing finite credential-admission policy scans content and condition fields independently. Rejection returns a fixed 422 without echoing the submitted text or its fingerprint. The recognized lexical patterns have finite coverage; they do not provide general secret or PII detection. See [private instruction persistence](private-instructions.md).

Deletion synchronously clears the target's content, conditions, and hashes across every revision and clears unshared instruction bodies/source hashes. Stable identity, receipts, lineage, and audit fields remain. A correction instruction still supporting a different live successor is retained for that successor's authority. Historical projection checks the current erased head, so old revision reads cannot recover a deleted body's text.

A readable revision requires every support source to remain available and its confirmation source to remain eligible. Unavailable projections omit content, conditions, owner, and source-reference fields and report their limited status/reason. Inactive, superseded, expired, invalidated, and erased states retain distinct meanings; a surviving support alone cannot make an unavailable revision readable.

## Pagination and source reads

List/revision pages default to 30 records and allow at most 100. Management cursors are signed, expire 15 minutes after issuance, and bind actor, workspace, endpoint, page size, filters, and resource where applicable. A cursor is not a frozen read snapshot or a new permission; each page uses fresh authorization/current state. Invalid, expired, or mismatched cursors return the fixed cursor error.

Source reads require exact source ID, version, SHA-256, and null span. They return a current explicit instruction with authenticated attribution; they do not provide history ranges, source search, branch admission, or a shared-source capability. Operation/request recovery is content-free and actor/workspace-bound. Mutation receipts report `indexState=not_enabled` where applicable.

Private instructions, including the requester's own, remain excluded from all shared Chat/Research prompts, tools, summaries, checkpoints, planning, and derived outputs. Owner-private management preserves those audience boundaries. 

Source entry points: [router](../../apps/api/src/ai_pdf_api/routers/memories.py), [HTTP schemas](../../apps/api/src/ai_pdf_api/schemas/memory.py), [service](../../apps/api/src/ai_pdf_api/services/memory_management.py), and [query projection](../../packages/memory-service/src/citeframe_memory/management_queries.py).
