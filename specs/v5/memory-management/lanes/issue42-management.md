# Issue #42 owner-private management API consumer contract

Status: **PROPOSED — assigned Critical reviewer approval required before routing/code writes.**
Date: 2026-09-28. Parent #41 remains open; intended delivery is a partial #42 PR.

## Authority, identity and acceptance boundary

- Workspace `D:/Code/citeframe-lanes/issue42-management`; branch `work/issue42-memory-management-api`; clean starting HEAD `32bb6764c785a0d3e424519d9a977df5182b4927`.
- Fixed integration includes reviewed PR48 `492624c` and **unmerged** #40 candidate `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`. Neither PR48 nor #40 is represented as merged. Latest user instruction permits dependent coding; dependent merge remains gated.
- Governing spec v4, final A1 choice2, design §§3–5, 7.1, 7.3 and 12.1; existing P1a implementation review remains scoped to its core. R1–R16 are not reopened.
- Deliver authenticated HTTP management of existing instruction-only P1a data and strict OpenAPI DTOs for #46. Private input is confined to owner storage/management, including when the caller is a workspace owner. No shared chat/Research input, tools, summaries, checkpoints, plans or other derived reuse; no native private-task/audience feature.
- Actual #46 UI, BFF, model quality, compaction, hosted CI/image and parent completion are separate acceptance boundaries.

## 1. Exact mounted subset

Base `/v1/workspaces/{workspace_id}`. JSON names are camelCase; UUID values canonical lowercase strings; dates timezone-aware ISO8601 UTC on output. New DTOs reject unknown fields, booleans as integers, numeric strings as versions, and naive timestamps. Scope is explicitly workspace-only and private. IDs/roles/author/source authority always come from authenticated server state.

| Method/path relative to base | Input | Successful response |
|---|---|---|
| GET `/memories` | `status=active` default; active/inactive/superseded/invalidated/expired/deleted/all; `scope=workspace`; limit 1..100 default30; cursor optional | 200 `{items:MemoryDto[],nextCursor:string|null}` |
| GET `/memories/{memory_id}` | UUID | 200 `{memory:MemoryDto}`; deleted owner gets410 |
| GET `/memories/{memory_id}/revisions` | limit/cursor as list | 200 `{items:MemoryDto[],nextCursor}`; deleted owner gets410, with no historical body |
| POST `/memories` | CreateRequest below; Idempotency-Key | 201 MutationReceipt |
| POST `/memories/{memory_id}/corrections` | CorrectionRequest; Idempotency-Key | 201 CorrectionReceipt (successor) |
| PATCH `/memories/{memory_id}` | `{requestId,expectedVersion,intent:'inactive'}`; Idempotency-Key | 200 MutationReceipt |
| DELETE `/memories/{memory_id}` | JSON `{requestId,expectedVersion}`; Idempotency-Key | 200 DeleteReceipt after synchronous core erase |
| GET `/memories/requests/{request_id}` | UUID | 200 OperationDto, content-free;404 if unknown/inaccessible |
| GET `/memories/operations/{operation_id}` | UUID | 200 OperationDto, content-free;404 if unknown/inaccessible |
| POST `/sources/read` | `{sourceRef:{sourceId,sourceVersion,contentSha256,span:null}}` | 200 InstructionSourceDto; exact instruction version/hash only |

Static request/operation routes precede the typed UUID record route. All requests use the original `x-user-id` and `x-ai-pdf-internal-token` authentication chain through unchanged #40 `require_workspace_member`. No user/role/grant fields are forwarded from JSON.

CreateRequest: `{requestId,kind,content,conditions,scope:{kind:'workspace'},pinned:false,validUntil:null,sourceRefs:[]}`. `kind/content/conditions/scope/requestId` required; pinned, validUntil and empty sourceRefs have the displayed defaults. Content length1..4000, kind preference/constraint/fact/decision. Conditions `{subject:string1..256,applicability:string1..2000,effectiveFrom:timestamp|null}` (effectiveFrom default null). Pinned is a strict boolean and true is permitted only for constraint/decision. Null expiry means no expiry. No trimming, summarization or inference changes the proposition. The API call is the attributable explicit manual remember action.

CorrectionRequest: `{requestId,expectedVersion,kind,content,conditions,pinned:false,validUntil:null}`; same validation. Creates a new identity and atomically supersedes the predecessor through the existing command. It does not overwrite history or transfer scope. No sourceRefs/confirmation/actor fields accepted.

Unsupported scope (`thread`, `research_run`, global, named project, shared visibility) returns422; never coerced to workspace. Nonempty sourceRefs return422 invalid_source_ref. PATCH active/pinned/validUntil changes return422 unsupported_operation; no reactivation or metadata-edit implementation is implied. Client-supplied confirmation or author fields return422 invalid_request. P1a creates explicit_remember; this endpoint offers no sourced_observation or model-confirmation admission.

## 2. Output DTOs for #46

MemoryDto is a discriminated union on contentAvailable:

- Available: `{id,workspaceId,ownerUserId,visibility:'private',scope:{kind:'workspace',threadId:null,runId:null},version,revisionId,intent,validity,displayStatus,kind,confirmation,conditions,pinned,validUntil,supersedesId,createdAt,updatedAt,contentAvailable:true,content,sourceRefs}`.
- Unavailable: `{id,version,intent,validity,displayStatus,contentAvailable:false,reason:'erased'|'source_unavailable'}`. No semantic body, conditions, hash or substituted empty string. List `status=deleted|all` may include this minimal tombstone; direct current/history return410 for erased identities.
- intent active/inactive/superseded/deleted and validity valid/invalidated come from the exact persisted revision, including history. Existing stored confirmation is preserved, never upgraded. Never serialize the dynamic internal MemoryView directly or rewrite that shared DTO. Present readability is computed separately under the guarded query below.
- displayStatus precedence: current record deleted, displayed revision superseded, displayed revision inactive, stored-invalidated OR present-support-unavailable, expired, active. Expiry means validUntil<=current UTC; it changes display eligibility, not persisted intent or validity. `status` filters this exact projection of the current revision. Inactive/superseded unavailable records retain their respective displayStatus; the contentAvailable discriminator additionally conveys suppression.
- createdAt is record creation; updatedAt is the displayed revision creation. For an available revision, sourceRefs are the complete exact support references `{sourceId,sourceVersion,contentSha256,span:null}`; no unrelated source enumeration.

Present-readability truth table (after fresh workspace/member and exact owner authorization):

| Persisted displayed revision / current record | Present support state | Public validity | contentAvailable / reason | displayStatus / list filter | Operation poll |
|---|---|---|---|---|---|
| Historical active, stored valid; current record not deleted | Any support stale/deleted/unavailable/missing or instruction/hash invalid | valid | false / source_unavailable | invalidated | Evaluate current head separately by these same rules |
| Stored invalidated, nonterminal active | All supports readable, or any unavailable | invalidated | false / source_unavailable | invalidated | false if this is current head |
| Inactive or superseded, stored valid or invalidated | Any support unavailable, or stored invalidated | Exact stored value | false / source_unavailable | inactive or superseded respectively | false if this is current head |
| Active/inactive/superseded, stored valid, not erased | Every support readable and exact | valid | true / no reason | active/expired, inactive, or superseded respectively | true if this is current head |
| Current record deleted, or displayed revision erased | Any | Exact stored value (no relabeling) | false / erased | deleted for current list/replay; current/history GET410 | false; intent deleted and currentVersion from current head |

Every support edge of the displayed revision must resolve to the same authorized workspace/owner, exact current source version and live instruction with matching content hash; missing confirmation support also fails closed. One surviving support cannot authorize old wording. Guard all support checks through serialization. Unavailable DTOs contain no content, conditions, sourceRefs or source hashes, including on list/history/mutation replay. Immutable historical validity is never replaced by a dependency-derived invalidated value. Current/readable inactive, superseded and expired records remain explicit management history, with no shared-task reuse. Operation polling always computes contentAvailable from the **current resource head**, never resultVersion's historical bytes, and always returns content-free metadata.

MutationReceipt: `{requestId,operationId,resultVersion,memory:MemoryDto,indexState:'not_enabled'}`. resultVersion is the operation's committed version; memory is the currently authorized projection and may have advanced or become unavailable during later replay. CorrectionReceipt adds `supersededMemoryId` from the verified operation target. DeleteReceipt: `{requestId,operationId,resultVersion,id,intent:'deleted',version,cleanupState:'completed'}`. Completion describes synchronous P1a-owned database erasure, with reference-safe source retention; it promises no raw archive, backup or provider-retention deletion.

OperationDto: `{requestId,accepted:true,operationId,state:'committed',resourceId,resultVersion,currentVersion,intent,contentAvailable,cleanupState:'not_required'|'completed'}`. No content/conditions/source hash/request digest/request key. cleanupState=completed only for the delete operation, otherwise not_required. A stored unsettled operation yields409 operation_in_progress; no invented completion DTO. Existing synchronous core does not create durable queued work. Unknown request404 is an observation at lookup time, not proof that another in-flight transaction cannot commit.

InstructionSourceDto: `{sourceRef,content,contentKind:'explicit_instruction',occurredAt,sourceState:'current',provenance:{role:'user',actorUserId,actorAttribution:'authenticated',threadId:null,runId:null,parentMessageId:null,confirmation:'explicit_remember'},branchRelation:'other_task',truncated:false,nextCursor:null}`. Exact manual source<=4000 characters returned in full; no model token-budget promise. sourceVersion is a strict integer>=1; contentSha256 is exactly64 lowercase hexadecimal characters. This subset accepts span:null only, no before/after/cursor expansion. Owned stale/deleted/unavailable/version-or-hash mismatch returns410; absent/cross-owner/cross-workspace source returns404. No latest-version fallback, native source resolver, arbitrary URL/path or raw-source delete route.

## 3. Paging and bounded queries

- List uses immutable `(record.created_at DESC,id DESC)` keyset ordering, limit+1; revisions use `(version ASC)` keyset ordering. Queries filter workspace and authenticated owner before limit; revisions additionally filter the authorized record. No offset pagination or unbounded history materialization.
- Cursor is versioned canonical JSON encoded base64url plus HMAC-SHA256, domain-separated for memory-management using the existing internal API secret. Payload binds actor, workspace, endpoint, target memory (history), normalized status/scope/limit, order and last key, with15-minute expiry. It contains no memory text, source hash or credentials. Compare MAC in constant time, cap cursor length4096 and reject malformed/tampered/expired/wrong-binding cursors with422 invalid_cursor. Reauthorize every page; a cursor grants no access.
- Pages are live views, not a database snapshot across requests. Concurrent creation before the last key is seen on refresh; correction/status changes may move records into/out of a filter. Ordering stays deterministic and immutable. Deletion/revocation is always checked on the next page. UI retains no snapshot-completeness assumption.

## 4. Session, authorization and transaction boundary

Observed core: every public MemoryCommands method uses `with session.begin()`; #40 member dependency already SELECTs through get_db and therefore autobegins its Session. Passing that Session directly into the command is invalid.

1. Run unchanged #40 dependency. Copy only authenticated user/workspace scalar IDs; dependency role is not final authority. Its read Session remains owned by get_db and is closed there. Do not commit/rollback it, expunge its objects, nest begin, or use begin_nested to hide the boundary.
2. Composition opens a **fresh independent Session bound to the same Engine**, with no pre-command query. Inject neutral `WorkspaceAccess(fresh_session)` and server-only `AccessContext(actor,workspace,'management','private')`. Core mutation opens, locks, reauthorizes, writes and commits its own transaction. It remains the only persistence implementation.
3. Read-only query/projection module owns one fresh transaction per bounded read. Use existing private authorizer first (workspace/member row locks), then exact owner/source/head guards in core lock order. Keep projection and JSON serialization inside those guards; return detached JSON data. No lazy ORM access outside the transaction, streaming or locks over network backpressure.
4. After a mutation commits, project its operation/current resource through a new guarded read transaction. Never return a pre-commit receipt. If authorization disappears or projection fails after commit, return a sanitized failure; preserve requestId for receipt polling. A later deleted resource projects a content-free tombstone. No second mutation, compensating rollback or claim that commit failed follows projection failure.
5. Source reads first establish owned registry identity under guards (404 nonenumeration), compare the supplied version/hash, then call existing `resolve_instruction` within that same transaction. It rechecks management purpose/ownership and exact live instruction/hash. No copying of resolver/persistence code.
6. Commit acknowledgement uncertainty returns503 outcome_unknown with requestId. Reconcile in a fresh connection using actor-bound operation query; never infer rollback, automatically assign a new requestId, or resend on the client's behalf. Core errors and unknown database details are not echoed/logged with submitted text.

No existing core/shared DTO/model/migration/source extensions or #40 router/dependency edits are proposed. A new neutral `management_queries.py` may implement only bounded owner queries/projection metadata and operation lookup; it must reuse authorization/source resolution and contain no mutation implementation. API service handles HTTP projection/cursor/error composition. Existing source/current helpers returning narrower DTOs do not justify changing their public contract.

## 5. Error and replay rules

New-route errors only: `{detail:{code,message,retryable,requestId:string|null,currentVersion?:integer}}`. Router-local exception translation covers dependency HTTP errors and validation without changing global/legacy handlers or #40 dependencies. Messages below are literal fixed strings. No input value, validation input/ctx, exception repr, source hash or matched admission text is returned/logged.

| HTTP/code | Fixed message | retryable | Condition |
|---|---|---|---|
|401 authentication_required|Authentication required.|false|Missing/invalid original auth headers|
|404 workspace_not_found|Workspace not found.|false|Dependency workspace denial or fresh core workspace/member denial, including unknown x-user-id, removal, archive and unsupported role|
|404 memory_not_found|Memory not found.|false|Absent/cross-owner/cross-workspace record; includes workspace owner accessing another member's private data|
|404 source_not_found|Source not found.|false|Absent/cross-owner/cross-workspace source|
|404 operation_not_found|Operation not found.|false|Unknown/inaccessible request or operation|
|409 version_conflict|Memory version changed.|false|CAS mismatch after owner authorization|
|409 terminal_memory|Memory cannot be changed by this operation.|false|Owned terminal transition|
|409 idempotency_conflict|Request identity conflicts with an existing operation.|false|Canonical command/body collision|
|409 operation_in_progress|Operation has not settled. Poll using the original request ID.|true|Stored unsettled operation|
|410 erased|Memory content has been erased.|false|Owner current/history read of erased record|
|410 source_version_unavailable|Source version is unavailable.|false|Owned exact version/hash unavailable|
|422 invalid_request|Invalid request.|false|JSON, path/query/body/key structural validation; forbidden identity/confirmation fields|
|422 invalid_scope|Memory scope is unsupported.|false|Explicit unsupported scope|
|422 invalid_source_ref|Source reference is unsupported.|false|Nonempty create sourceRefs or unsupported source span/context expansion|
|422 invalid_cursor|Cursor is invalid or expired.|false|Malformed/expired/tampered/wrong-binding cursor|
|422 unsupported_operation|Memory operation is unsupported.|false|PATCH reactivation or pin/expiry-only mutation|
|422 sensitive_content_unsupported|Submitted content contains an unsupported credential pattern.|false|Exact approved shared admission rejection; no API clone|
|503 temporarily_unavailable|Memory service is temporarily unavailable. Retry using the original request identity.|true|Known transient database failure without an uncertain commit|
|503 outcome_unknown|Operation outcome is unknown. Poll using the original request ID.|true|Commit acknowledgement uncertain|

Authorization/validation precedence for these new routes follows the actual FastAPI boundary, made explicit and tested:

1. Invalid JSON syntax on a JSON-body route is422 invalid_request with requestId null, including when authentication is absent. This response has no authorization/resource assertion and never echoes parser input.
2. For a syntactically valid body (including missing body), unchanged require_workspace_member runs its header/token and initial workspace lookup:401 first, then404 workspace_not_found. An inaccessible workspace wins over malformed/missing key, UUID/query or body schema. These denials use requestId null.
3. After the dependency succeeds, structural path/query/body/key validation runs; missing/invalid key or multiple structural errors produce422 invalid_request. If structurally valid input has multiple unsupported features, priority is invalid_scope, invalid_source_ref, unsupported_operation. Cursor decoding/verification follows these checks. Unknown/forged authority fields are structural errors. A presently unsupported role that passed the unchanged initial dependency may therefore receive422 for an invalid payload; it receives404 for valid input at the locked guard. No stale dependency role classifies an error.
4. With valid inputs, fresh transaction authorization precedes target lookup, source availability, version metadata, admission and mutation. Map core workspace_unavailable or membership_required uniformly to404 workspace_not_found; do not distinguish removal from unknown role or perform a denial-classification query. Foreign/missing IDs return their404 before owner-only410/CAS metadata. Core ordering determines replay/CAS/admission after this guard; the admission hook preserves approved core ordering.

requestId rules: (a) syntax and initial dependency failures always null; (b) after dependency success, mutations may echo only the submitted canonical UUID requestId extracted from a JSON object, even if another field fails validation; invalid/missing requestId is null; (c) request polling uses the valid canonical request_id path value after dependency success; (d) other read/source/list/operation routes use null on error. A successful operation lookup returns its persisted original requestId. Recovery never generates a replacement identity automatically.

currentVersion is optional **only** on409 version_conflict/terminal_memory. Obtain it by a new fresh guarded owner-record read after command rollback, not from the dependency object or exception. If membership/workspace access disappears, replace the409 with404 workspace_not_found; if the target is no longer owned/available, replace it with404 memory_not_found. If that lookup has a transient DB error, return503 temporarily_unavailable. None includes currentVersion. If it succeeds, return the newly observed currentVersion, explicitly not a historical snapshot of the failed CAS. All other errors omit currentVersion. Locked reauthorization failures after initial validation retain the requestId derived above; no foreign metadata is exposed.

A postcommit projection authorization failure follows the same404 rules; it does not assert rollback. A transient postcommit projection failure returns503 outcome_unknown so the original request identity is polled. No403 role variant exists in this lane. Unmounted routes/methods keep normal framework404/405 behavior; this matrix applies to mounted handlers.

Idempotency-Key is required for mutations: ASCII visible characters33..126, length8..128. requestId canonical UUID; expectedVersion strict integer>=1. Core canonical method/path/body digest remains authoritative, including its internal `/memory/.../{action}` command path. HTTP paths map one-to-one onto the four commands; do not create another operation store or digest interpretation.

Existing semantics to preserve explicitly: scope is `(workspace,actor)`; same requestId or same key+command identifies one operation. Core accepts identical-body replay using a second requestId with the same key, and identical-body replay using a second key with the same requestId; return the original requestId/operationId. Only the original stored requestId can be polled. A collision selecting two different operations or different validated command body returns409. #46 must retain the original pair and body until receipt is resolved. Replay may return an erased projection and never restores historical content. A correction receipt identifies its original successor even after later corrections.

## 6. Explicit nonimplemented operations and owner delta

No mounted search_memory, `/memories/search`, `/history/search`, hybrid index/backfill, embeddings, async jobs, cleanup-retry, restore/reactivate, pin/expiry-only edits, native source kinds, observations, confirm/extraction, thread/run/global scope or shared model tools. Unsupported method/body returns405/422 or unmounted route404; none returns fabricated success, pending index or queued job. IndexState is always not_enabled.

**Admission dependency (M42-C1):** controller contract [issue42-admission.md](issue42-admission.md) assigns original P1a developer `agt_3a16f73b` and original Critical reviewer `agt_a74ed9c2` the new neutral admission module and minimal remember/correct hooks. The shared deterministic predicate checks exact content plus conditions.subject and conditions.applicability, without transformation, schema/shared-DTO change, payload logging or model calls. It raises MemoryError code `sensitive_content_unsupported`, mapped to the422 above. The API invokes the existing commands and consumes that approved error; it neither clones nor bypasses the predicate.

Supported categories and negative controls are defined solely by the admission owner's finite reviewed rule inventory: private-key PEM; credential-bearing authorization/cookie headers; labeled credentials including enumerated Chinese labels; password-bearing URIs; auditable recognized provider-token patterns. Negative credential discussion, public keys/certificates, token counts and unrelated preferences remain controls. This conservative supported-pattern boundary does not claim detection of arbitrary secrets, obfuscation, unlabeled values or every personal datum, nor semantic confirmation.

After consumer approval, unaffected API/read/test work may proceed. API code may depend on the predicate/error once the exact core contract is accepted; **mounting create/correct waits for the exact independently approved dependency integration** recorded by controller commit/hash. Core contract acceptance and integration are currently pending, with no fabricated implementation hash. No fail-open stub or alternate admission path is permitted. This ownership decision replaces the prior unresolved-policy question; independent acceptance of actual core implementation remains a separate gate.

## 7. Required independent evidence after approval

Dedicated API tests on a newly initialized disposable PostgreSQL cluster, followed by a separate live uvicorn HTTP process using the unmodified membership/auth dependencies and full migrated disposable database. No production services/credentials, paid models or old-tree writes. Existing Python/PG binaries may be read-only tools with lane-local imports and bytecode writes disabled.

| Oracle | Separate PG integration and live HTTP expectations |
|---|---|
|Manual workflow|Empty list; exact create/current/source; correction yields successor and frozen predecessor history; inactive; refresh; delete and receipt|
|Access|Missing/bad headers401; revoked/archived404; unknown role404; member managing own data succeeds; workspace owner/second member reading other's IDs404; cross-workspace IDs/cursors404/422; purpose/audience never client-controlled|
|Versions/source|Two same-version corrections one winner; stale409; predecessor terminal conflict; forged hash/version410 only to owner,404 otherwise; no latest substitution|
|Paging|Multi-page lists/history; no unbounded materialization; tampering, expiry, cross-actor/workspace/filter/record cursor rejection; revocation between pages|
|Request recovery|Same-pair replay, changed body409, core alternate-pair semantics, concurrent replay; dropped HTTP response after durable commit then original request polling; separate real DB after-commit acknowledgement loss and fresh-session reconciliation|
|Deletion|Conditions-only marker erased across all revisions; owner410 versus other404, unavailable list tombstone, no body in request/operation receipts or old-create replay; shared legitimate source preserved; native archives unchanged|
|Transaction|Dependency SELECT autobegin does not cause nested begin/accidental commit; revoke/archive between dependency and core authorization fails; projection failure after commit remains recoverable; no lazy load after locks release|
|Contract/isolation|Strict OpenAPI unions, unsupported scope/fields refused, no arbitrary authority/source grants; no chat/Research registration or consumer dependency added; sanitized error/evidence contains no auth header values or submitted sensitive bytes|

Focused fixture data is prepared at `apps/api/tests/fixtures/memory/management_contract_cases.json`:19 exact error/race cases, the existing lifecycle create/deactivate/invalidate sequence with persisted-vs-public revision expectations, all-support suppression, deletion and receipt checks. JSON syntax and case-ID uniqueness were checked; these are unexecuted test inputs, not API/PG acceptance. Admission payload cases deliberately depend on the core owner's approved synthetic corpus and define no duplicate validator.

Store synthetic HTTP method/path/status/safe-body assertions and exact commands under lane-owned evidence. Supporting unit/TestClient checks must be labeled separately from real socket HTTP. No test has been executed for this proposed contract. Runtime and API usability remain unaccepted until evidence and independent implementation review.

## 8. Approval and handoff

Assigned independent reviewer recorded by prepare_session task: `agt_4e74d255`; this session's collaboration inventory exposes only `/root`, so controller must deliver this candidate to that existing reviewer. The original reviewer-owned `reviews/issue42-management.md` returned M42-C1/C2/C3 at hash618410d; its other bounded contract judgments remain passed. This candidate changes only the operative admission dependency, error/precedence and historical-readability clauses plus focused fixtures; targeted re-review remains pending. The review artifact is left untouched. Do not substitute self-approval or a new unassigned review. Approval must identify this file/hash, confirm the separately owned admission dependency gate, and explicitly approve endpoint/DTO/error/paging/replay/session boundaries above before routing writes.

Allowed subsequent files: NEW `apps/api/src/ai_pdf_api/routers/memories.py`, `schemas/memory.py`, thin `services/memory_management.py`; NEW neutral management query module if needed; `apps/api/src/ai_pdf_api/main.py` import/registration only; dedicated API tests and lane spec/evidence. All Git writes, commit/push/PR attachment and dependent merge are controller-owned. No existing core/#43/#40/legacy/frontend files are assigned here.

Bootstrap verified remote GitHub Gujiassh/citeframe; local/global user identity match. prepare_session succeeded and its project/state/task were read. Private profile MEMORY was not read. Write-back check: durable lane state is this artifact; shared workbench/profile writes are outside the granted workspace. Controller can checkpoint `memory42-management-api` with contract-review pending. No product code or Git state changed.
