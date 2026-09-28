# Issue 42 management API — independent Critical review

## Disposition

**BOUNDED CONSUMER-CONTRACT APPROVAL.** Current reviewed contract SHA-256: `2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802`. M42-C2/C3 are closed at contract scope. Unaffected read/query/projection/paging and DTO/router authoring may proceed; create/correct activation and final API acceptance remain gated on exact shared admission integration and independent runtime review. See targeted re-review C2 below for the authoritative permission boundary.

Reviewer scope: owner-private management API consumer of accepted instruction-only P1a. Governing authority: full specification v4, design §7.1 and final A1; no broad R1–R16 re-review. UI, chat/Research quality, shared-output integration and full #42/#41 acceptance remain separate.

Fixed HEAD verified: `32bb6764c785a0d3e424519d9a977df5182b4927`, incorporating reviewed #48 `492624c1f36e17f94f7e5010bf9e374edc40ec2c` and pending #40 candidate `1b9e1168c2c2b1548febc1fcb5997d4310bfe511`. This is an unmerged integration candidate. Release remains gated on prerequisite integration; unrelated coding is unaffected.

At initial inspection the developer-owned `specs/v5/memory-management/lanes/issue42-management.md` did not exist and the worktree was clean. Its exact public contract cannot yet be judged. This preparation does not authorize routes.

## Bootstrap and ownership

- Loaded applicable Windows/global rules, interaction files and memory policy; ran `prepare_session.py --repo-path D:/Code/citeframe-lanes/issue42-management` and read its linked project/state/task. No private MEMORY or dated private memory was accessed.
- Read-only Git identity/remote/HEAD/status inspection matched the GitHub repository and local/global identity. No Git mutation, product write, model call or native archive change.
- Reviewer writes only this file. Developer owns its lane contract and, after bounded approval, new memories router/schema/thin composition/query, main registration, dedicated tests/docs. Existing dependency/router/core/model/migration/shared ABI changes require controller handoff.
- Durable review evidence is retained here; workbench/controller relay and any broader write-back belong to the controller under this ownership boundary.

## Verified dependency and transaction facts

1. `apps/api/src/ai_pdf_api/routers/deps.py:64,96`: `require_workspace_member` uses `Depends(get_db)` and executes a workspace/member SELECT. It returns an ORM workspace plus role. This lookup is an initial access check, with no transaction-scoped row locks.
2. `apps/api/src/ai_pdf_api/db/session.py:9–18`: `SessionLocal` uses ordinary SQLAlchemy autobegin; `get_db` yields one session and closes it in `finally`. It does not commit. FastAPI's installed dependency solver caches dependency results by default.
3. `packages/memory-service/src/citeframe_memory/commands.py:89,95,104,116,153`: commands/read/history/source/reconcile explicitly own `with session.begin()`. Feeding the dependency's already-started session directly to these methods produces an already-begun transaction error. A wrapper `begin()` or `begin_nested()` does not establish the existing command's required clean-session boundary.
4. `packages/memory-service/src/citeframe_memory/access.py:18–30`: the core authorizer locks workspace then actor membership, checks archive and role in `owner|member`, and enforces exact private management purpose/owner. The consumer must retain those guards in the transaction doing the actual read/mutation, including query-only endpoints; stale dependency role/workspace objects cannot replace this check.
5. `commands.py:108–122,141–197`: replay and reconcile reconstruct current resource availability, while retaining committed result version/operation identity. Exact request identity, key collision domain, CAS/terminal response mapping and unknown-ack handling must be declared by the actual contract. A fresh request/session must remain usable after failure.
6. `sources.py:9–24`: the core resolver looks up owned workspace-bound instructions; its `SourceUnavailable` combines absent/inaccessible and unavailable states. It does not accept an expected source version/hash/span. Public exact-source and owner-only 404/410 distinctions need an explicit authorized consumer query/composition contract before activation.
7. Core `MemoryView` is smaller than the planned public DTO. It does not supply full record metadata, immutable historical availability metadata, pagination or body-free operation envelopes. Public serialization and source eligibility must therefore be reviewed from the developer's concrete contract rather than inferred from this internal type.

Read-only installed-runtime probe (stdin script via `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, `PYTHONDONTWRITEBYTECODE=1`) observed FastAPI **0.139.0**, SQLAlchemy **2.0.51**. An in-memory `SELECT 1` changed `Session.in_transaction()` from false to true; a subsequent `with session.begin()` raised `InvalidRequestError: A transaction is already begun on this Session.` Session close returned it to false. This verifies session mechanics only; it is not PostgreSQL/API acceptance.

## Semantic acceptance oracles for the bounded delta

| Area | Required direct evidence | Current disposition |
|---|---|---|
| Exact contract | Submitted file hash; complete enabled route/DTO/error/request-key/CAS/paging/source contract, explicit excluded routes/features; strict unknown-field rejection and trusted actor injection | blocked: delta absent |
| Private management | Two members plus workspace owner; foreign/private/missing IDs non-enumerating 404; only authorized owner sees erased 410 and version metadata; no shared-output reuse | blocked: implementation absent |
| Transaction composition | Actual dependency graph/session ownership; locked role/member/archive recheck through actual command/query transaction; no accidental commit or nested begin; concurrent revocation/archive checks | blocked: implementation absent |
| Idempotency and CAS | Same-key concurrent mutation, changed-body collision, stale version/terminal behavior, lost acknowledgement recovered by request identity on fresh session; replay after correction/deletion never restores old bytes | blocked: implementation absent |
| Paging and exact sources | Signed actor/workspace/filter/order/version-bound cursor, expiry/tamper/cross-owner rejection, bounded stable traversal; exact instruction version/hash/Unicode range and source scope; no latest-version substitution or caller attribution | blocked: implementation absent |
| Erasure and preservation | Delete clears content/hash/conditions on every revision; sources/actions erased when solely dependent; surviving legitimate successor source preserved; native archives unchanged; history/source/replay/poll cannot reveal erased bytes | blocked: implementation absent |
| Independent execution | Real disposable PostgreSQL and live HTTP requests through mounted application with actual dependencies and fresh sessions; no provider calls, model/index stubs or production database | blocked: implementation absent |
| UI and chat/Research quality | Separate later acceptance; no implication from API result | not applicable to this lane |

The concrete contract may further bound optional surfaces. Its review must establish those bounds before implementation; this table grants no new API surface or authorization.

## Inspected baseline SHA-256

| Artifact | SHA-256 |
|---|---|
| `specs/v5/memory-management/spec.md` | `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85` |
| `specs/v5/memory-management/design.md` | `828EFFB02B5FBF9818604E35EA13662814E12CCC605B704DD895FD7BBAFE6236` |
| `apps/api/src/ai_pdf_api/routers/deps.py` | `AC067CDAE26A100C99DC435EE3B5D76F5BCB0084F3B371E30942CF2C11CF38DA` |
| `apps/api/src/ai_pdf_api/db/session.py` | `DAAF80E3F87F419A25718EB7466D2FBAF3035AD5A5102ECF9080E6F0149F839F` |
| `packages/memory-service/src/citeframe_memory/access.py` | `286A3FFECDD83469C871351264283F078749FFEA06622B60BD1C33DCBBBB972B` |
| `packages/memory-service/src/citeframe_memory/commands.py` | `2F9285E6049ED52D4EB66E957647E1CE8A88BF0773C149B7785CA7090A07A2C7` |
| `packages/memory-service/src/citeframe_memory/sources.py` | `805F7E5BE3B807444615327B45BC51CBA3E19EA04BA6BAF24D25413E83DF4CE3` |

## Contract review C1 — actual submitted delta

**Disposition: RETURN FOR BOUNDED CONTRACT REWORK. No route/product implementation approval yet.**

Reviewed developer artifact: `specs/v5/memory-management/lanes/issue42-management.md`, SHA-256 **`5C2DED75CEF5812A6B382F8CD0B62C9BE6C7877C06B5BB91480C5AE2F04CF98E`**, against fixed HEAD above. The earlier waiting state is superseded by this review. Product code is still absent. This disposition concerns the submitted consumer contract only and does not reopen the accepted P1a core or R1–R16.

### Findings requiring disposition before implementation

**M42-C1 — High: sensitive-input admission remains an explicit unresolved activation requirement.**

- Evidence: lane line98 requests a controller/core-owner decision. Governing spec §6.2 prohibits credential content in long-term memory; design §5.1 line198 requires rejection before indexing. Current `MemoryStatement` checks only structural fields; `MemoryCommands.remember/correct` persist those fields without an admission predicate. `indexState:not_enabled` does not prevent the stored content/conditions from containing a credential.
- Required disposition: controller must supply a bounded policy/ownership decision before create/correct are approved. If implementing a shared predicate, hand off the exact new/changed core file scope and obtain its focused review; record its applicability to content and both condition strings, rejection code, safe diagnostics, limitations and synthetic acceptance fixtures. Any relaxation of the governing rule needs explicit authority and a documented scope change. Reviewer cannot infer that authorization from this proposal.
- No private examples or model classifier are requested. The original core remains accepted at its recorded evidence scope; public activation is the new decision point.

**M42-C2 — Medium: error behavior and membership-race classification need an exact consumer decision.**

- Evidence: lane lines76–88 declare a common error envelope but specify `retryable` only for503; fixed messages are not enumerated. They do not define mixed-invalid-request/auth precedence or requestId derivation for request polling versus mutation validation. Lines81–82 distinguish missing membership404 from invalid role403. Core `access.py:27–30` raises the same `AccessDenied('membership_required')` for both.
- Required rework: finish the bounded error matrix with fixed safe message/retryable values and requestId/currentVersion inclusion rules; name the validation/auth precedence for the new routes. Explain how a role change/removal between dependency and command authorization is classified without trusting the initial `WorkspaceAccess.role` or mapping every `membership_required` to403. This can be a fresh locked, scope-only classification after denial using the new query composition, or a controller-approved simpler nonenumerating response; no existing dependency/core rewrite is implicitly authorized. Define the response if access disappears while obtaining version metadata.
- Verification: combine malformed/missing key or body with unauthenticated/inaccessible workspace requests; race member removal versus role change after the original dependency SELECT; assert exact status/code/flags, no foreign currentVersion, and a usable subsequent fresh request.503 recovery must retain the original request identity and must not instruct clients to generate a new one.

**M42-C3 — Medium: historical validity and present availability need one explicit mapping.**

- Evidence: lane lines45–46 promise immutable historical state and a display projection using present source availability; they do not say whether public `validity` comes from persisted revision state or a present dependency-derived override. Core `commands.py:69–86` returns a dynamic invalidated `MemoryView.validity` even for an earlier stored-valid revision, and retains its statement when the dependency is invalid. Directly mapping that view would not establish the promised immutable-history/body-suppression contract.
- Required rework: define a compact DTO truth table for (a) stored-valid historical revision whose source is now stale/deleted, (b) stored-invalidated revision, (c) inactive/superseded revision with unavailable source, and (d) deleted current record. Explicitly select persisted historical `validity`, present `contentAvailable/reason`, displayStatus/filter behavior and operation-poll contentAvailable. Preserve historical persisted state and suppress unavailable semantic bytes; do not modify the shared internal DTO. All direct supports must be checked; one surviving support alone cannot make old derived wording readable.
- Verification: invalidate an instruction after creating and deactivating a record, then query current/history/list/status/poll; compare stored revision states with returned DTOs and assert no unavailable body/conditions/source hash. This is a concrete consumer projection check, not a new invalidation engine.

### Bounded design judgments already reached

| Submitted area | Judgment at contract scope |
|---|---|
| A1, owner-only workspace scope, explicit excluded features, no inference/index stubs/native archive deletion | pass |
| Enabled route subset; create/correct/deactivate/delete reuse of P1a commands; indexState not_enabled; separate UI/BFF acceptance | pass, subject to findings above |
| Fresh independent Engine-bound command Session after unchanged dependency; no commit/rollback of dependency session; postcommit guarded projection and lost-ack polling | pass at design scope; actual PG/live HTTP still required |
| Replay's original requestId/operationId, resultVersion distinct from current version, alternate-pair behavior explicitly preserving existing core | pass at design scope |
| Live-view keyset paging, bound/expiring signed cursor and no unbounded history materialization | pass at design scope |
| Full exact manual instruction only, span:null, source version/hash pin, explicit 404/410 distinction and no arbitrary context expansion | pass at design scope; implement strict positive sourceVersion and lowercase64-hex hash validation |
| Public error contract, admission and history availability mapping | blocked by M42-C1/C2/C3 |
| Product implementation/real PostgreSQL/live HTTP/security acceptance | blocked: product implementation not submitted |
| Full #42/#41, UI/chat/Research quality, prerequisite merge/release | not accepted by this review |

Controller relay: send C1–C3 to the original developer, obtain the admission-policy ownership decision, then submit the revised contract with exact hash for targeted re-review. No new agent, broad design rewrite or existing core/#40 edit is requested. A bounded approval must explicitly replace this disposition before the developer starts product implementation.

### Concurrent contract refresh checked

Before delivery, the developer artifact changed to SHA-256 **`618410D57C7F77C9CE2101F21D2724985D6A92F5DE99329B4488820189DD0F64`**. Re-read the submitted contract: it clarifies unknown x-user-id as workspace404 (consistent with the unchanged member dependency) and records observing the initial reviewer preparation. M42-C1/C2/C3 remain open; **RETURN FOR BOUNDED CONTRACT REWORK** applies to this exact newer hash. No product approval is implied by the earlier scope-level passes.

## Targeted consumer-contract re-review C2 — bounded authoring approval

**Disposition: BOUNDED CONSUMER-CONTRACT APPROVAL. M42-C2 and M42-C3 are closed at contract scope. M42-C1 remains an admission implementation/integration/runtime gate for create/correct activation and final API acceptance.**

Exact reviewed artifacts:

| Artifact | SHA-256 |
|---|---|
| `lanes/issue42-management.md` | `2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802` |
| `lanes/issue42-admission.md` (controller dependency/ownership boundary only) | `9A8D943A39ADE6B224E9A21A6B9FF0485E9F3B7963094E21868441AD64DC2693` |
| `apps/api/tests/fixtures/memory/management_contract_cases.json` | `34B9CA270EE2291D8302F7923A5DA2814CE103DB714800CE265958346AEA2A3D` |

HEAD remains `32bb6764c785a0d3e424519d9a977df5182b4927`. Rechecked dependency/session/access/command hashes match the baseline above. No product implementation was submitted or accepted during this re-review. Earlier RETURN dispositions are superseded only within the authoring scope below.

### Operative findings and closures

**M42-C2 — CLOSED at consumer-contract scope.** Lane §§4–5, particularly lines88–123, now provide literal safe messages, retryability, requestId provenance, currentVersion omission rules, and mixed-invalid-request/auth ordering. Missing membership, archive and unsupported roles uniformly map to workspace404 at the fresh locked guard. There is no role403 branch and no stale-role denial-classification query. Foreign records/sources remain nonenumerating404; owner-only410 and conflict metadata require current authorization.

The declared ordering is compatible with inspected installed FastAPI source: JSON decoding precedes dependency solving; nested dependencies run before endpoint body-schema validation. A malformed JSON422 with null requestId does not reveal resource state. Syntactically valid requests encounter the unchanged auth/workspace dependency before endpoint validation; invalid input can receive422 after initial dependency success without reaching the locked role check. With valid inputs the fresh core/query guard remains authoritative. Implementation must realize the declared dependency graph and route-local translation; this source inspection does not substitute for the mixed-error HTTP fixtures.

Conflict metadata uses a new guarded owner read after rollback. Lost access replaces409 with the appropriate404, without currentVersion; a successful lookup exposes only the newly observed owned version. Postcommit projection failures preserve recovery semantics: access failure404 makes no rollback claim; transient projection/unknown acknowledgement503 directs polling by the original identity. RequestId is null for syntax/initial dependency failures and derived only by the enumerated route-specific rules afterward. Existing legacy/global handlers remain untouched.

**M42-C3 — CLOSED at consumer-contract scope.** Lane §2, lines43–65, now explicitly separates persisted revision intent/validity from present readability and display filtering. The truth table preserves historical stored-valid values when a source becomes unavailable, suppresses content/conditions/sourceRefs/hashes, retains inactive/superseded display precedence, suppresses stored-invalidated revisions even when supports appear readable, and handles deletion through erased tombstones or owner410. Every support and the confirmation support must pass current guarded checks; one surviving source does not authorize old wording. Operation polling is content-free and derives availability from the current head. Public projection must not directly serialize the dynamic internal MemoryView.

The proposed create→deactivate→invalidate fixture has persisted states `(active,valid)`, `(inactive,valid)`, `(inactive,invalidated)` and matching public-history validity values, with all three bodies suppressed after invalidation. Current list filtering remains inactive/all; operation polls reflect the current unavailable head. This is consistent with the existing lifecycle implementation and the revised public contract. Exact source input now also specifies positive strict sourceVersion and lowercase64-hex hash.

**M42-C1 — SEPARATELY OWNED, STILL GATED.** Lane §6 records the controller's original P1a developer/reviewer assignment and a single neutral finite predicate covering content and both condition strings, raising the stable422 code through existing commands. The controller has approved the category-family direction; exact rule inventory and implementation acceptance remain pending. This review accepts the consumer's dependency boundary only. It does not approve the category inventory, an implementation hash, arbitrary-secret detection, a relaxed admission rule, or activation without the integrated predicate.

### Exact permission to proceed

The retained original API developer may now author within the already assigned file boundary:

- Authenticated owner-only list/current/history reads, content-free request/operation lookup and exact instruction-source reads.
- New bounded query/projection and signed live-view keyset paging code; fresh-session composition; strict DTOs/OpenAPI types and new-router-local safe error translation.
- DTO and routing/composition authoring for the declared subset, with real existing-core command wiring and focused tests. Deactivate/delete reuse is unaffected by the new-proposition admission dependency; their implementation and erasure/CAS acceptance still require independent runtime review.
- Main registration for the unaffected implemented surfaces and dedicated disposable-PG/live-HTTP test preparation. Create/correct DTOs and route logic may be authored while their registration/activation remains withheld.

**Create/correct must remain unmounted/inactive until the controller integrates the exact independently accepted shared predicate and command hooks, recording commit/hash and original reviewer evidence.** No placeholder endpoint may return success, no skip may be reported as acceptance, and no API-local clone, bypass or fail-open fallback is permitted. Unmounted endpoints use ordinary framework behavior rather than an invented successful receipt. The exact core-owned error contract must be accepted before code relies on it as an available dependency.

This permission does not authorize edits to existing #40 dependencies/routers, global or legacy error handlers, existing core commands/models/migrations, or shared ABI. The separate original P1a lane owns its admission-module/minimal-command delta. Any additional ownership change returns to the controller.

### Evidence and remaining gates

| Area | Disposition |
|---|---|
| Consumer error/precedence, source validation and immutable-history/present-availability contract | pass at contract scope |
| Unaffected read/query/projection/paging and DTO/router authoring | approved within the scope above |
| Shared admission exact rule inventory / implementation / no-write and replay parity | blocked pending original admission lane review/integration |
| Create/correct mounting/activation | blocked on that admission gate |
| Actual management implementation, real PostgreSQL and live socket HTTP behavior | not yet accepted; independent execution required |
| Final API acceptance, full #42/#41, UI/BFF/chat/Research quality and prerequisite merges/release | not accepted by this review |

Evidence this turn: full operative contract and controller admission-boundary read; read-only installed FastAPI source-order inspection through `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe` with bytecode disabled; JSON fixture consistency check (19 unique error cases, expected metadata omission and historical-validity/body-suppression values). The JSON remains labeled `prepared_not_executed`. No API, PostgreSQL, predicate or live-HTTP test ran. The contract's precedence test language is treated as the required oracle; its explicit unexecuted status governs the current evidence claim.

Runtime review must exercise those exact error/race cases through unchanged real dependencies and fresh sessions, inspect persisted historical payloads/erasure, and separately prove shared admission rejection before any write once integrated. No broad R1–R16 work is requested. Controller can relay this bounded approval now; the original API developer need not wait on admission to implement the unaffected surfaces.

Write-back check: durable disposition is recorded solely in this reviewer-owned file. No private memory, product/Git/model writes, shared workbench edits, production database actions or native archive changes occurred.
