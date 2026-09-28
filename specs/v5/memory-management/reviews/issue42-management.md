# Issue 42 management API — independent Critical review

## Disposition

**BOUNDED MANAGEMENT IMPLEMENTATION ACCEPT — M42-I1 CLOSED.** Exact repair manifest `56502f436c9fb6b93d5f926f6dc767f09d4190703a8c65a014bc77cf9ea6ab5a`. Original three reverse cases pass over live socket HTTP; ten PG orderings,1748 combined tests and76 lifecycle HTTP checks pass independently. Broader local-suite/hosted CI, prerequisite merge/release and UI/shared-model/full #42/#41 gates remain separate. See final exact repair re-review below.

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

## Mounted implementation review I1 — RETURN FOR TARGETED REWORK

**Disposition: RETURN FOR TARGETED REWORK — M42-I1 is open.** The mounted implementation is not accepted. The separately reviewed CI step-local environment correction is accepted for local wiring only. Admission source integration is verified; its earlier activation dependency is satisfied for this candidate. Full API acceptance still requires the error-serialization repair and targeted independent re-review.

### High — M42-I1: authorization guards end before owner-only error metadata is serialized

**Locations:** `apps/api/src/ai_pdf_api/services/memory_management.py:70–75,94–109,127–135,150–155`; `apps/api/src/ai_pdf_api/routers/memories.py:89–113`. Existing success-only guard test: `apps/api/tests/test_memory_management.py:508–531`.

The successful response path validates and renders JSONResponse inside `_read`'s guarded transaction. Owner-only error paths leave that transaction before the router builds their response:

- CAS/terminal handling reads an authorized current version in a fresh transaction, exits it, then raises `ManagementError(code, version)`; the router later serializes `currentVersion`.
- Deleted current/history and unavailable exact-source paths raise inside the query callback; `_read` unwinds/rolls back, releasing the workspace/member guards before the router serializes owner-only410 `erased`/`source_version_unavailable`.

This violates the approved transaction-through-serialization boundary and creates a membership-revocation window for resource existence/version metadata. Normal foreign-owner requests remain404 in the executed tests; no private body disclosure was observed. The finding is specifically the owner-only error metadata race.

**Independent real-PG reproduction:** instrument `JSONResponse.render` without changing product code; capture the latest connection that executed the actual membership `FOR UPDATE`; at the beginning of rendering the target error, inspect that connection and, when closed, remove the fixture membership through a separate committed connection before calling the original renderer. Each request uses the unchanged member dependency and fresh `get_db` sessions. Observed:

| Scenario | Guard at error render | Revocation committed before bytes | Result | Next fresh request |
|---|---|---|---|---|
| Stale expectedVersion after v2 exists | closed; in_transaction=false | yes |409 version_conflict, currentVersion=2 |404 |
| Owner current GET after delete | closed | yes |410 erased |404 |
| Owner exact-source read after source erasure | closed | yes |410 source_version_unavailable |404 |

The existing success-render assertion passes because it exercises create/current success only. Revocation-before-conflict-lookup tests also pass; they do not cover the interval after that lookup and before error serialization.

**Required original-developer rework:** retain the actual fresh workspace/member/owner/source guards through construction of the final JSON bytes for authorization-sensitive409/410 responses, using a cohesive route-local/error-composition boundary. Keep fixed messages, requestId rules, nonenumerating404 behavior, and no metadata on authorization loss. Do not edit existing #40 dependencies, global/legacy handlers, core commands or shared ABI. Avoid a second preflight authorization that releases its guard before rendering. Add focused regression tests for version_conflict and terminal_memory plus erased current/history and unavailable exact-source paths; prove the guard is held at error serialization and that revocation before the guarded read yields404 without currentVersion. Preserve failure recovery and serialization-before-network-backpressure behavior.

### Exact candidate identities

HEAD: `7d47607778a9212e9f3cb076442cd7c497c1f8ca`.

Frozen product manifest: `evidence/issue42-management/candidate.json`, SHA-256 **`a953983d83a1edae9be478470f666c0a9463edc970b9739ba803b917995246f5`**. All product, dedicated test, fixture and dependency entries matched that manifest throughout review. Concurrent changes were confined to the separately authorized workflow/evidence follow-up; they are not silently included in the frozen product identity.

| Product/test artifact | Reviewed SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/main.py` | `da153ec753c03628a68335d91f6e196d26f41cd11f0dc6b5a684858d11d06e1d` |
| `apps/api/src/ai_pdf_api/routers/memories.py` | `0047bcf26b7149b64b91bfe53c099c4d2b0d12c0d4c9038eda4c025d1dc667be` |
| `apps/api/src/ai_pdf_api/schemas/memory.py` | `cb61bc652e98999b1741557c32c136ad0e85fdc62921cff732436c0c5b723dda` |
| `apps/api/src/ai_pdf_api/services/memory_management.py` | `8f37f45c83267f57e959bcf0996f6dcf03dc77890c1a1c4881b9cf4f314657dd` |
| `packages/memory-service/src/citeframe_memory/management_queries.py` | `53464b1b938ba398f93e557d82b11146a1e1b5c86703f756f4903c27a1882598` |
| `apps/api/tests/test_memory_management.py` | `b1f677de7504f4841f15aa09d38d222762f06a7ca3fd50e592bb39d0c62497ae` |
| `lanes/issue42-management.md` | `af82373eb17ae00c5ec24d0bbeb9e19ed40297205263a699dc5be4d96804aac7` |
| Live extracted OpenAPI, independently identical | `2a789047302af6d23bcbf2829fc44ff9326ecda2f05769b47089e8ceb648a8e1` |

Admission source `893de951672f1a374d552425dfb2b3e7c3e6a223` is integrated at this HEAD. Inspected original implementation ACCEPT in `reviews/issue42-admission.md`, integration reconciliation, actual neutral predicate and its pre-first-write command hook. Existing dependency/access/source files retain their pinned hashes. No broad P1a/R1–R16 redesign was performed.

### Independent execution and direct assertions

A new reviewer-owned PostgreSQL **17.11** cluster was initialized at `.local-runtime/reviewer-management/pgdata`, loopback **56642**, database **citeframe_memory42_test**, synthetic role **reviewer_management**. Full Alembic upgrade reached `t4b5c6d7e8f9`. The developer's cluster/port and all production databases were untouched.

Environment: bytecode disabled; repository-local source imports; `CITEFRAME_MEMORY42_POSTGRES_URL=postgresql+psycopg://reviewer_management@127.0.0.1:56642/citeframe_memory42_test`. Interpreter: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`.

Executed:

```text
python -B -m pytest
  packages/memory-service/tests/test_instruction_memory.py
  packages/memory-service/tests/test_admission.py
  packages/memory-service/tests/test_admission_postgres.py
  apps/api/tests/test_memory_management.py
  apps/api/tests/test_workspace_router.py
  apps/api/tests/test_persistence_boundary.py
  apps/api/tests/test_research_persistence_boundary.py
  -p no:cacheprovider -q --tb=short
  --basetemp=.local-runtime/reviewer-management/pytest-tmp
```

**1738 passed, zero skipped, 37.77s**, one existing Starlette/httpx deprecation warning. The total includes1603 pure admission cases and other static/SQLite tests; it is not represented as1738 PostgreSQL cases. The new46-test suite contains37 PG-backed cases and9 pure DTO cases.

Read the actual SQL observers, six-table equality checks, historical persisted-state comparisons, FK-safe erasure/replay, source preservation, revocation/role/archive hooks, CAS races, after-commit fault injection and log-redaction assertions before rerun. No-write admission observes zero INSERT/UPDATE/DELETE attempts for both commands × three fields, not merely successful rollback.

**Live HTTP:** independently executed the submitted `live_http.py` against full `ai_pdf_api.main:app`, actual uvicorn loopback **56643**, unchanged real auth/member dependencies, generated local-only token and the reviewer PG database. **76 checks passed.** The source was loaded/compiled in memory with only output destinations changed to reviewer scratch and the documented port/URL environment changed; assertions/product code were unmodified. Output redirection preserved developer-owned `openapi.json`/`live-http.json`. This verifies the actual mounted implementation via socket HTTP, separately from TestClient. Raw TCP dropped responses, committed request polling and clean replay were exercised.

**Additional independent PG-backed TestClient probes:** alternate requestId/same key and same requestId/alternate key return the original receipt; polling an unstored alias returns404. Injected postcommit projection SQL failure returns503 outcome_unknown, then fresh polling/replay finds one committed operation. Owned terminal409/currentVersion, deleted-owner410 versus foreign404 and erased old-create replay passed. Checked strict OpenAPI extra-field rejection schemas, the contentAvailable discriminated union, empty-only create sourceRefs, positive exact-source version, null span, not_enabled index state and every declared error response model. These focused passes do not resolve M42-I1.

### CI follow-up — bounded local wiring ACCEPT

Separately reviewed `.github/workflows/ci.yml` SHA-256 **`de69b0aaff39849af7f0cab8fe2302685dcac5fd35bd1de3063b1205b523422c`**. Compared to the frozen candidate workflow `f599f0ce1dd1080ee60c5ce15b99981f1586522e8a141478395ee8a778fbb6f9`, its sole change is the regular `pytest apps/api/tests` step-local `CITEFRAME_MEMORY42_POSTGRES_URL`, exactly matching the preceding dedicated step's already-created disposable database. Removing precisely those two added lines reconstructs the prior raw-byte hash. No job-wide grant, service change, skip/deselection or different test command was added.

Independent `CI=true` execution of the affected46 tests against the dedicated reviewer URL: **46 passed, zero skipped, 25.19s**. Independent missing-URL control: selected PG fixture **errors** with `CI requires CITEFRAME_MEMORY42_POSTGRES_URL`; no skip or fallback. The dedicated command explicitly includes all46 consumer tests alongside the original core/admission suites. This accepts local wiring and fail-closed collection behavior; it is not hosted-CI or broad API-suite acceptance. The developer's concurrent broader local API run/evidence was not used as a passing oracle here.

### Review judgments and evidence limitations

| Area | Current disposition |
|---|---|
| Owner/workspace/current-member checks on ordinary paths, private-purpose injection, no shared model reuse | pass for inspected/executed scope; error guard race M42-I1 blocks overall security acceptance |
| Dependency autobegin separation, no dependency commit or nested begin, shared-command ownership | pass |
| Historical persisted validity, all-support present availability, exact source/Unicode fidelity, erasure and safe replay/poll | pass for executed scenarios; owner-only error serialization still requires repair |
| Finite admission integration, pre-DML rejection, safe codes/redaction, edited same-identity recovery | pass within approved lexical scope; no universal-secret guarantee |
| Idempotency alternate-pair semantics, CAS, late projection and lost-ack recovery | pass for executed scenarios; conflict error serialization still requires repair |
| Strict public DTO/OpenAPI, signed scoped/expiring paging, unsupported authority/scope rejection | pass for inspected/executed scope |
| Architecture | New router/schema/thin composition/neutral queries and main registration stay within ownership; scoped error-composition repair required; no core/shared refactor authorized |
| CI environment follow-up | bounded local wiring ACCEPT; hosted/broad-suite result separate |
| Mounted API final acceptance | **blocked by M42-I1** |
| UI/BFF/chat/Research quality, full #42/#41, prerequisite merge/release | not accepted by this review |

Reviewer scratch evidence is under `.local-runtime/reviewer-management/` (not product/release artifacts):

| File | SHA-256 |
|---|---|
| `pytest.txt` | `aebab61a82783e54f1a3d360761116bd64f3612873d1942fd9ef4fffdf2fb97e` |
| `live-http.json` | `b579fd209daf22af8cf271372da14bdd31d0e39bd14d7991f63e9e8773fd4d9e` |
| `conflict-guard-probe.txt` | `366a9cf6fa773979a49cda32fe1510947e4647ac7f5a1e6b9a121514289ba49f` |
| `error-guard-probe.txt` | `6bfb5ffb8a53b910254e057fdb7416027e6a96a0db46677c69431f57591f0870` |
| `supplemental.txt` | `375111ecd49e7832f8b9b77425505105e99f043f8016a7cfdbad9edd9cd1a16a` |
| `ci-api.txt` | `201a3e763e828ee2c23a3fa8075dfbcbac840668ed49a0b6dc8c65fb4c321c24` |

Runtime cleanup: uvicorn subprocess terminated by the harness. Fast PG shutdown timed out; immediate stop targeted only the verified reviewer cluster path/PID/port. Final `pg_isready` reported no response on56642 and `postmaster.pid` was absent. No other cluster was stopped or filesystem tree deleted.

Controller relay: return M42-I1 to the retained original API developer, preserve the frozen-product identity in the repair manifest, and request only the new-route/error-composition and focused test delta. Re-review the changed hashes and the reproduced failure cases before final API approval. CI follow-up acceptance does not override this product disposition. Durable write-back is this review only; no product/test/Git/model, private-memory or shared-workbench writes occurred.

## M42-I1 exact repair re-review — BOUNDED IMPLEMENTATION ACCEPT

**Disposition: ACCEPT for the reviewed owner-private management API implementation. M42-I1 CLOSED. No remaining finding in this bounded implementation scope.** This replaces the prior implementation RETURN for the exact repaired files below. Full-repository API-suite/hosted CI, prerequisite merge/release, UI/BFF/shared chat/Research and full #42/#41 acceptance remain separate.

### Exact accepted repair

Base supplied for this repair remains `7d47607778a9212e9f3cb076442cd7c497c1f8ca`; no Git command/API was invoked in this re-review.

`evidence/issue42-management/i1-candidate.json` SHA-256: **`56502f436c9fb6b93d5f926f6dc767f09d4190703a8c65a014bc77cf9ea6ab5a`**.

| Repaired artifact | Accepted SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/routers/memories.py` | `0d00e0ff0fd37d1278048e264b68b86c98f3a52ae59ea7667648aed8eb0f4c10` |
| `apps/api/src/ai_pdf_api/services/memory_management.py` | `189a86b0a99e3947e3915e43436f0eaf6e540397158d58929c7940a233d6d61f` |
| `apps/api/tests/test_memory_management.py` | `4ff2b6a7a3cacd999f98e6003673e9306f213503b61dee9d569fa88140331ea5` |

Rechecked actual bytes at start and closeout. Main registration, public schema, neutral management query, fixture, core/admission/dependency files retain their prior reviewed identities. Workflow remains **`de69b0aaff39849af7f0cab8fe2302685dcac5fd35bd1de3063b1205b523422c`**; the earlier bounded local CI-wiring acceptance is unchanged. No new existing-dependency/global-handler/core/shared-ABI edit was introduced.

### Why M42-I1 is closed

The router has one fixed safe error renderer. Its composition dependency captures only the authorized requestId value before entering command/query transactions and supplies the renderer to the API service. `_read` catches domain errors and constructs their final JSONResponse bytes inside the same fresh authorization transaction. Conflict/terminal handling performs its post-rollback guarded owner/version lookup through this boundary. The Session context exits before the Response is handed to ASGI.

This repairs both previously observed paths: explicit currentVersion metadata and erased/source-unavailable410. No second unlocked authorization preflight was added; no shared command or persistence rule changed. Body reading/awaiting occurs before the guarded synchronous use case, and locks do not extend over socket transmission. The route-local renderer retains the same fixed error codes/messages/retry flags, requestId rules and version-only-on-owned409 contract.

### Independent original three reverse probes — actual socket HTTP

Recreated the original **version conflict, erased current, and unavailable exact-source** cases against the repaired full `ai_pdf_api.main:app` in actual uvicorn subprocesses on loopback56643. Product files were unmodified. Test-only renderer/ASGI instrumentation was installed in each subprocess; no test endpoint or auth/dependency override was added.

For each case:

1. Observe the real membership `FOR UPDATE` connection immediately before final error rendering; it is open and in a transaction.
2. Attempt membership DELETE in a separate PostgreSQL transaction with100ms lock timeout. All three attempts fail with **55P03**, proving the guard actually blocks revocation during rendering.
3. Run the original renderer and confirm the guard remains active after the final bytes exist.
4. At `Response.__call__`, confirm guards are released, commit membership deletion successfully, and compare the outgoing response body with those already-rendered bytes.
5. Immediately before forwarding `http.response.body` to uvicorn's real ASGI send, confirm guards remain released and bytes are unchanged. The client receives the authorized409/410 response; its next fresh request receives **404 without currentVersion**.

| Original failure case | Guard holds through final bytes | Revocation succeeds before transport send | Fresh request |
|---|---|---|---|
| version_conflict/currentVersion | pass; competing DELETE55P03 during render | pass |404 |
| erased current | pass; competing DELETE55P03 during render | pass |404 |
| source_version_unavailable | pass; competing DELETE55P03 during render | pass |404 |

The response sent after revocation was serialized while authorization guards still held. No claim is made that already-authorized/rendered bytes can be recalled after guards release; locks are intentionally released before network backpressure.

### Independent ten PostgreSQL orderings and regressions

Inspected the new test's actual competing DELETE,55P03 assertion, response-body comparison, pre-send release assertion and fresh404 checks. Independently ran:

```text
python -B -m pytest
  apps/api/tests/test_memory_management.py::test_owner_error_serialization_holds_guards_until_bytes
  -p no:cacheprovider -vv --tb=short
  --basetemp=.local-runtime/reviewer-i1/ordering-tmp
```

**10 passed, zero skipped, 5.76s.** Five scenarios—version conflict, terminal memory, erased current, erased history, unavailable source—each cover (a) guarded render then release/revoke before ASGI send and (b) revocation before the fresh guarded read. The latter always returns404 without owner-only metadata and never invokes the409/410 renderer. These ten cases use TestClient transport with real PG and are distinct from the three instrumented live socket probes above.

Independently reran the same seven-suite command documented in review I1, changing only basetemp to `.local-runtime/reviewer-i1/pytest-tmp`: **1748 passed, zero skipped, 41.24s**. It includes all **56 management tests:47 PG-backed cases and9 pure DTO cases**, as well as1603 pure admission cases and the previously listed core/native boundary regressions. The ten ordering tests are included in1748 and were also rerun separately; these totals are not additive or all-PG claims.

The unchanged `live_http.py` lifecycle harness was independently rerun against the repaired mounted app and a fully migrated fresh reviewer PostgreSQL database: **76 live socket-HTTP checks passed**. Only scratch-output destinations and port/URL environment were redirected in memory; assertions and product code were unchanged. The extracted OpenAPI remains byte-identical to the earlier reviewed artifact: **`2a789047302af6d23bcbf2829fc44ff9326ecda2f05769b47089e8ceb648a8e1`**.

Additional independent PG-backed probes reconfirmed alternate-requestId/same-key and same-requestId/alternate-key replay return the original receipt, unstored alias polling404, and late postcommit projection failure returns outcome_unknown with the correct requestId followed by successful fresh polling/replay of one committed operation. Existing combined tests recheck validation/auth priority, dependency-autobegin separation, conflict-lookup revocation/role races, no-DML admission/redaction, source/history availability and erasure. One pre-existing Starlette/httpx deprecation warning remains; it is not a failure or skip.

Runtime: newly initialized reviewer PostgreSQL17.11, `.local-runtime/reviewer-i1/pgdata`, loopback56642, `citeframe_memory42_test`, synthetic role `reviewer_management`; full Alembic head `t4b5c6d7e8f9`. Interpreter `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, bytecode disabled, repository-local imports and cacheprovider disabled. No production database was used.

### Broader local-suite evidence remains limited

The developer's broader local API result remains **1011 passed,29 failed,9 skipped**. This re-review neither reran that broad suite nor claims a pristine-parent suite result. The supplied audit separates **24 first-failing artifact/provenance checks** (22 M402 and2 R100) from **5 environment failures** (3 Windows subprocess/access and2 missing-tsx Research SSE); all29 are not represented as CRLF failures.

Independently verified the current raw and CRLF-normalized bytes of the three pinned artifacts reproduce the audit's reported checkout and expected parent hashes. No historical artifact, expected hash, provenance contract or test was modified. This supports the narrow byte-drift explanation for those first-failing checks, not a blanket claim that subsequent checks or a pristine full suite pass. Artifact/checkout repair, any remaining broad-suite failures and hosted CI require their own owner/controller disposition; they do not reopen this repaired management-only scope.

### Evidence identities, cleanup and handoff

Reviewer scratch `.local-runtime/reviewer-i1/`:

| Evidence | SHA-256 |
|---|---|
| `pytest.txt` | `1636bf56540cf66273f840f407ee2cd24c87e4ca8cce0da7fe907ea790309e56` |
| `ten-orderings.txt` | `1abd2bfb0268789543395b0aea4147f0f6cc4d7d1e0c9edc3d2a08733424b202` |
| `original-three-socket-probes.json` | `a8dde849614b833110438df0a567011f74839bc4a92923571cf9757d5fc5e7f3` |
| `live-http.json` | `5dea4b24719e4573cc0d4035ff5ec6ecc9aa6f93929655357477d2494b1476d3` |
| `recovery-supplement.txt` | `be7a072055df71b581b545f4550b886c63b8cb85e54c4c8d81e0c8b1f48153c9` |

All reviewer uvicorn subprocesses were terminated. Exact-path-checked reviewer PG shutdown succeeded;56642 reports no response and postmaster.pid is absent. No other cluster was stopped and no filesystem tree was deleted.

**Controller handoff:** the bounded management implementation and M42-I1 repair are accepted at the exact hashes above. Preserve the separate broader-suite/hosted CI, prerequisite merge/release and UI/BFF/chat/Research gates. No full #42/#41 claim follows. Only this reviewer-owned durable artifact was updated. No product/test/historical-artifact edits, Git/model calls, or private-memory/shared-workbench access or writes occurred in this re-review.
