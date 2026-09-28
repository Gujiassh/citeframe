# Issue45 slice45a0 — independent Critical implementation review

Date: 2026-09-28 (Asia/Shanghai)

## Disposition

**BOUNDED APPROVE — pure, unactivated native projection only. No blocking implementation finding within the authorized two-file scope.** The projection preserves the inspected native data meanings and points toward the approved integration boundary. It does not implement automatic compaction or establish storage, database, runtime, privacy authorization, model-semantic or UI acceptance. Aggregate resource-bound admission remains an explicit integration evidence gap below.

Independent reviewer under #41; controller owns relay and integration. Original design owner is `agt_af167b31`. Per controller, `agt_d03b4a29` implemented the authorized lane as a documented filesystem-deficit replacement, with one product owner. Original reviewer `agt_1e53da00` failed twice with PROVIDER_EXECUTION_ERROR and left no artifact; this review is the availability replacement, not review shopping.

Read-only implementation tree: `D:/Code/citeframe-lanes/issue45-research`, baseline `812ebb1ed9bdddf8ef3dc44f9aeb8387036607cd`. The lane ref was inspected through filesystem metadata, without a Git command in this turn. No claim is made that these uncommitted files are part of that commit or have been integrated into canonical #40.

## Exact artifacts

Paths in this table are relative to the read-only implementation tree unless marked canonical.

| Artifact | SHA-256 |
|---|---|
| `apps/worker/src/ai_pdf_worker/research/memory_context.py` | `8F013879533AD1B648EFB51DA76507E845F395CAC993AC0EBA55C76146588E0D` |
| `apps/worker/tests/test_research_memory_context.py` | `CA54B56226A4236608B8CF6010513E0BD8557F18291B13C36B7825C0F911692C` |
| Developer `specs/v5/memory-management/evidence/issue45-projection.md` | `AFB1DA7DFCEDCDE4B293CEDD15C09191D31079745C062F19765EBC381FDBFFA6` |
| Actual `apps/worker/src/ai_pdf_worker/research/agents.py` | `EA3842D4228897A9ECBD2D550A70FF340536CC669D6D686271322DE2AE81C4EB` |
| Canonical `specs/v5/memory-management/lanes/issue45-research.md` | `249C97FD1705AFCA6481566FD49F1511A6D0E2F82E2C5933BEAD80212FBB89F4` |
| Canonical spec v4 `specs/v5/memory-management/spec.md` | `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85` |
| Canonical `specs/v5/memory-management/design.md` | `068F9112279B55C6B9E1AB63730EF053F9E0B8A570C0EC4929677CE92502B1BB` |

Implementation/test bytes matched the requested pins before and after verification. Developer evidence's older design/review references are provenance for that implementation turn; the final canonical design disposition is in the updated `reviews/issue45-research.md`. Hashes identify inspected artifacts; acceptance rests on the actual source/body/identity checks below.

## Semantic oracle and inspected behavior

The full governing outcome remains a pre-dispatch gate for every Research role/continuation/recovery and two threshold crossings in the same live Attempt without a new user message. This slice supplies lossless, attributed input to that future gate. Its immediate oracle is exact protected input plus native journal bodies/identities, without reconstructed originals, implicit ORM loading, new authority or fabricated model-call identities.

| Review area | Result and evidence |
|---|---|
| Module boundary | **Pass, pure scope.** `memory_context.py::project_context` takes the existing StepLease, exact supplied role variables and ordered native journal rows. It returns local dictionaries. No DB/session command, source registration, GenerationRequest construction, storage, ledger, summary, runtime wiring or shared DTO clone is added. |
| Exact protected content | **Pass.** Lines 79–90 copy the goal, constraints, system prompt and entire roleInput, retaining claim/handle order, original excerpts, quantities, negations, uncertainty and schema. No selection or inferred confirmation is performed. Deep-copy tests establish body isolation and no input mutation for native JSON-shaped fixtures. |
| Composite native identity | **Pass.** `_project_journal` uses adaptive `(stepId,turnNumber)` and conflict `(stepId,operationNumber)`, not a row UUID. Native mapper tests confirm the two-column PKs and adaptive absence of request_json. Duplicate locators reject rather than replace earlier records. No registry current-version uniqueness is implemented or claimed. |
| Order and producer/consumer | **Pass.** Lines 62–78 preserve caller history order, including interleaved Steps and nonnumeric order. Native tables have no cross-Step chronology to infer. Original `created_by_attempt_id` remains producer; current lease remains consumer. Step kind and nested role remain distinct. Lease token is omitted. |
| Nested native roles | **Pass, attribution only.** Native phases inspect/verify/critic map to investigator/verifier/critic under conflict_decision_gate; search/finish have no model role. All six model role labels are allowed. This mapping does not assert that a provider call occurred, or authorize the supplied consuming role. |
| Exact native journal body | **Pass.** Conflict request body stays operation arguments, separate from current `_json` variables. Succeeded result requires a matching native canonical hash. Started requires null result/hash and remains started/not_recorded; the projector does not infer the persistence replay outcome_unknown state. |
| Missing original/unknown recovery | **Pass, representation only.** Adaptive request remains not_stored with existing request hash; query is separately attributed. It is never reconstructed into an original request. No archive recovery or resend function exists. Native `conflict_turn` can classify replay as outcome_unknown with context unavailable to this projector. Its stored row status must not be rewritten by the projector. |
| ORM implicit-loading guard | **Pass, static plus local negative.** Lines 94–98 type-check and inspect unloaded state before reading any mapped attribute. The detached, incompletely loaded real SQLAlchemy row raises the deliberate ValueError rather than an attribute-load error. Fully loaded state is not proof of commit, authorization or provenance. No SQL/integration claim follows from this test. |
| Native bounds and determinism | **Pass within supplied-input scope.** Native constants constrain adaptive ordinals to 0..2 and conflict ordinals to 0..12; bool/invalid ordinals reject. Duplicate rejection bounds records per composite Step/kind. Repeated projections preserve exact order/bodies and deterministic JSON for tested native-shaped data. No random/time/global state is consulted. Aggregate limits are not enforced here; see E45-1. |
| Authority and IDs | **Pass, no minted authority.** Descriptors are explicitly unregistered. No sourceId, provider-call/tool-call ID, confirmation, evidence upgrade or read-authority field is generated. Existing IDs inside original native bodies remain original data. Instruction-like text is nested data; there is no provider serialization here to establish downstream injection handling. |
| Storage/native ledger/privacy/runtime/UI | **Blocked / out of this acceptance.** No migration, DB, native transaction, source ACL or private-data exclusion boundary is exercised. No dispatch, checkpoint, cancellation/reclaim, publication or visible UI path is activated. |

The function deliberately relies on callers to supply lawful, committed, fully loaded, authorized data. A transient fully populated ORM fixture can pass its local shape/hash checks. That is appropriate for this unactivated projection's declared boundary and must never be promoted to proof that its input came from an authorized committed row. Final A1 excludes all private data, including requester-owned data, before shared projection. No private mode/audience/output permission or inferred long-term candidate path is added.

## Independent execution

Both exact test commands were independently executed successfully, rather than accepted from developer counts. From `D:/Code/citeframe-lanes/issue45-research`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH=((@(
  'apps/worker/src','apps/api/src','packages/backend-contracts/src',
  'packages/backend-persistence/src','packages/research-persistence/src',
  'packages/memory-service/src','packages/prompt-contracts/src'
) | ForEach-Object { Join-Path $PWD $_ }) -join ';')

& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -B -m pytest `
  -p no:cacheprovider apps/worker/tests/test_research_memory_context.py -q

& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -B -m pytest `
  -p no:cacheprovider `
  apps/worker/tests/test_research_memory_context.py `
  apps/worker/tests/test_research_adaptive_retrieval.py `
  apps/worker/tests/test_research_conflict_investigation.py `
  apps/worker/tests/test_research_v5c_agent_io.py -q
```

Actual reviewer results:

- **36 passed in 1.14s**, exit 0.
- **70 passed in 1.88s**, exit 0. This contains the same 36 plus 34 adjacent tests; it is not 106 distinct tests.

Sandbox permitted execution. No bypass was used. Bytecode, pytest cache and plugin autoload were disabled. Canonical virtualenv was used as read-only tooling; PYTHONPATH pointed to the lane. An additional `python.exe -B -` import probe asserted that `ai_pdf_worker.research.memory_context`, `citeframe_contracts`, `citeframe_persistence.models` and `citeframe_research_persistence.errors` all resolve beneath the lane root; all four passed.

### Actual role-builder check beyond test labels

The six-label parametrization supplies one generic mapping to the projector; it does not prove all six live builders or their runtime call paths. The submitted test's real verifier-method capture uses a synthetic resultSchema and scripted return solely to complete that method. It is useful input-shape evidence, with no model/verification-truth claim.

A separate reviewer stdin probe used `GenerationResearchAgents(None)` to obtain the actual current production registry and real result schemas. It constructed existing DraftClaim, VerifiedClaim, EvidenceHandle and StepLease values, invoked **actual investigator, verifier and critic methods**, and replaced only the `_json` boundary with a capture that:

1. Called the real `project_context` with the exact variables just built by the method.
2. Compared the complete protected roleInput to those variables and checked separate consumer gate kind/role and deep-copy identity.
3. Raised a sentinel exception immediately, so no provider or fabricated successful role output was used.

Full-body assertions passed for:

- Investigator: `{investigation: exact supplied native payload, resultSchema: actual investigator schema}`.
- Nested verifier: exact claims/evidenceHandleIds, selected evidenceHandle/excerpt/assetId/locatorId/sourceFingerprintSha256, reasonTaxonomy and actual verifier schema.
- Nested critic: exact id/text/status projection and actual critic schema.

Separate native operation argument bodies were compared with their respective role-variable bodies using native canonical_sha256; all three legitimately differed. No native source/resolver/validator was substituted, and no helper assigned synthetic journal data authority or changed its meaning. Output: **PASS: 3 actual native builders, exact bodies with real registry schemas, separate journal/role representations; stopped before provider/output validation**, exit 0. Synthetic input IDs/body values prove shape preservation only. This probe does not implement or accept the later versioned journal-to-role binding or third, final-provider-request identity.

## Evidence gaps and follow-on ownership

### E45-1 — aggregate resource bounds are caller/integration obligations

`memory_context.py:34–90` accepts an arbitrary Sequence of rows across distinct Steps and deep-copies entire role/journal bodies. It has **no aggregate journal-count, body-byte, output-byte, nesting-depth or elapsed-time cap**. Native ordinal limits bound each Step/kind, not the total cross-Step envelope. Native conflict persistence separately limits canonical request/result bodies to 1,000,000 bytes; merely being a fully loaded ORM object does not establish passage through that writer.

This is an explicit limitation of the accepted pure projection, not a new authorization to add an arbitrary local truncation rule or shared ABI. It is not accepted as a bounded retrieval/admission API for untrusted or arbitrary input. Before wiring, #45 native loading/composition and #43 source/packing owners must pin and enforce the approved finite source/byte envelope **before body loading/copying**, fail rather than truncate protected data, and provide exact-limit/one-over-limit and multi-Step tests. Current tests establish deterministic copying and native ordinal bounds only. No global resource-bound acceptance is claimed.

### Other required evidence before dependent activation

- **#45/#43:** actual committed source/producer/dependency authorization, immutable per-call journal/role/provider archive binding, missing-original handling and no resend for sent-unknown. Projector body hashes do not establish any of these.
- **#42/#43/native owners:** explicit approval of native_key/index/migration, source resolver plus SQL predicates, policy hash/freeze and DTOs, immutable Attempt bindings, schema2 and native tool/reclaim deltas. Local dictionaries freeze no shared schema/API/ABI.
- **Compaction and native owners:** one atomic checkpoint+exact coverage+dependencies+Attempt pointer, every role/runner/recovery dispatch, two episodes within one live Attempt, preserved frozen evidence/root budgets/cancel/unknown and no completed-tool/publication replay. No duplicate native accounting or invented provider-tool ID can be introduced during integration.
- **Privacy/semantic/UI owners:** real all-owner private-data exclusion before shared context, task-local uncertainty with no inferred long-term candidates, semantic fidelity and the actual visible automatic flow. Pure tests establish none of these acceptance layers.

Current #43 DTO: `D77617A25ECF5CD9C0B808537F6C884B7EE67E2A2250BB0D955E99597DDB5E2B`. Current #43 review: `03AC7FA67F60B01FBD986660B88B5AC07B24B437B08604198242EBFE80D8FFEA`. Its latest bounded interval/profile review records progress on original P43-A1/A2/A3 counterexamples but requires P43-I1/P43-I2 rework; it does not close the whole pure/core gate. This review supplies **no #43 waiver** and does not independently accept that moving implementation.

Reverse review: relabeling an earlier producer, collapsing turns, changing excerpt/schema content, fabricating an adaptive original, silently loading an expired attribute or turning a search/finish record into a provider call would be caught by the local identity/body/negative oracles. Unauthorized committed-looking rows, excessive aggregate inputs, missing archive recovery, source revocation and actual double accounting would require the later integration oracles above; the present green tests cannot catch or certify those boundaries.

## Preservation and write-back

Only canonical `reviews/issue45-research.md` and this new `reviews/issue45-projection.md` were written by this review turn. Neither product tree, #43 tree, shared specification, workbench nor Git state was edited. No Git/model/paid/network/database/service/UI call was made in this turn. Existing canonical #40 work was left untouched. Earlier same-session profile/prepare_session bootstrap remains read-only; no private MEMORY/daily memory was read. Durable write-back is these own-review artifacts only. Controller owns relay and any subsequent integration decision.