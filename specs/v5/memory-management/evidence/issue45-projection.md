# Issue45 slice45a0 — native projection developer evidence

Date: 2026-09-28. Status: implemented, unactivated; awaiting appointed independent implementation review. Controller owns integration/release. Eligibility approval for this pure slice does not approve the full integration contract or any schema.

## Artifact and scope

Worktree: `D:/Code/citeframe-lanes/issue45-research`.
Branch: `work/issue45-research-memory`.
Starting and final HEAD: `812ebb1ed9bdddf8ef3dc44f9aeb8387036607cd`.
PR49 + PR48 remain unmerged prerequisites per controller; this work makes no mergeability/release claim.

Only three new files authored:

- `apps/worker/src/ai_pdf_worker/research/memory_context.py`
- `apps/worker/tests/test_research_memory_context.py`
- `specs/v5/memory-management/evidence/issue45-projection.md` (this record)

Initial untracked lane/review documents were preserved. No existing Worker file, `__init__`, shared ABI, registry, resolver, DTO, model, migration, provider, activation or canonical/#40/historical-tree product file was changed. No Git write, commit, push, PR operation, service/database execution, network/model/paid call occurred.

Authority read locally:

| Artifact | SHA-256 |
| --- | --- |
| spec.md, authorized v4 | A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85 |
| lanes/issue45-research.md, full contract still in independent re-review | 2019A9F4038646694071CB430FAF9ADB6CDBD1679A7827772BDBD5F1186CCF39 |
| reviews/issue45-research-design.md | DDA0AB297204AAD77D2962869210036006D21523307F29161830B1FFF2B82995 |

## Implemented API and semantic oracle

`research/memory_context.py:34::project_context` consumes existing `StepLease`, exact `GenerationResearchAgents._json` variables mapping, resolved prompt text, authorized task goal/constraints, consuming role/Step kind, and an explicitly ordered sequence of native `ResearchAdaptiveTurn | ResearchConflictTurn` objects. It returns local dictionary transcript data; no serialized/persisted/shared schema is installed.

- Current goal, constraints, prompt and entire native role input occupy a protected section. This preserves exact claim/evidence associations, excerpts, result schemas, quantities, negation and uncertainty without selecting fields or inferring confirmation. A later compactor must honor protection; no compactor exists in this slice.
- History preserves caller order and complete request/result groups. Tables supply no global cross-Step chronology, so the projection does not invent one. Duplicate composite locators fail explicitly rather than replacing earlier data.
- Adaptive locators retain `(stepId, turnNumber)`; conflict locators retain `(stepId, operationNumber)`. No row UUID or provider/tool-call ID is fabricated. Each source descriptor explicitly remains unregistered.
- Producer Step/Attempt comes from the original row; consumer Step/Attempt/number/role comes from the supplied lease/context. Lease tokens are omitted. Conflict Step kind remains `conflict_decision_gate`, with `inspect -> investigator`, `verify -> verifier`, `critic -> critic`; search/finish have no model role. This is native phase attribution, without a claim that a provider call occurred.
- Adaptive result bodies are copied exactly; request availability is `not_stored`, retaining only the existing hash. Query is separate native metadata and is never labeled an original request body.
- Conflict request bodies are exact **native operation arguments**. For example, a verify journal carries revisions/evidence; the nested verifier `_json` input carries claims/evidence/reasonTaxonomy/resultSchema. The projection never converts one into a purported original of the other.
- Native `started` stays `started`, with no recorded result. It is neither a successful outcome nor an inferred replay outcome. Native persistence may classify replay as outcome_unknown using context absent here. Succeeded rows require a result body and matching native canonical hash. Inconsistent status/body/hash, invalid bounds/phase, foreign object types and unloaded ORM attributes fail locally.
- All bodies are copied without aliasing or mutation. Embedded instructions remain nested transcript data; no provider messages or executable tools are built.

## Existing type/API compatibility evidence

| Actual native source | Compatibility evidence |
| --- | --- |
| `packages/backend-contracts/src/citeframe_contracts/__init__.py::StepLease` | Imported directly; no clone. Consuming Step/Attempt/number retained, lease token excluded. |
| `apps/worker/src/ai_pdf_worker/research/agents.py:316::_json` | Existing input is `Mapping[str, object]`. Projection accepts that mapping unchanged. The test invokes the real `GenerationResearchAgents.verifier` method with existing `DraftClaim`/`EvidenceHandle`/`StepLease` types and intercepts `_json` locally, checking its complete exact variables mapping without a model call. |
| `packages/backend-persistence/src/citeframe_persistence/models/research_adaptive_turn.py:9` | Imported actual ORM class. Mapper tests assert the two-column primary key, absent `id`, absent request_json. Synthetic rows use actual columns. |
| `packages/backend-persistence/src/citeframe_persistence/models/research_conflict_turn.py:8` | Imported actual ORM class. Mapper tests assert the two-column primary key and absent `id`; phase/status/body semantics follow current fields. |
| `packages/research-persistence/src/citeframe_research_persistence/adaptive_turns.py:12` | Actual persistence inserts only with result and stores request hash/query, not full request. Ordinal bound reused from native autonomy module. |
| `packages/research-persistence/src/citeframe_research_persistence/conflict_investigation.py:21` | Actual persistence has started/succeeded rows; result-less replay can return outcome_unknown, which is not a stored status. Operation bound reused from conflict_policy. |
| `packages/research-persistence/src/citeframe_research_persistence/errors.py::canonical_sha256` | Reused for existing native request/result body checks; hashes do not establish authorization, provenance or semantic truth. |
| `apps/worker/src/ai_pdf_worker/research/conflict_investigation.py::investigate` | Inspected actual nested-role calls and operation arguments. No provider IDs are derived from operations. |

Runtime import-path probe confirmed `ai_pdf_worker.research.memory_context`, `citeframe_contracts`, `citeframe_persistence.models`, and `citeframe_research_persistence.errors` resolve beneath this authorized worktree. Existing canonical Worker virtualenv was used solely as read-only Python tooling, with lane-local PYTHONPATH and bytecode disabled.

## Exact developer test commands/results

All commands ran from the worktree root in PowerShell. Environment setup:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH=((@(
  'apps/worker/src','apps/api/src','packages/backend-contracts/src',
  'packages/backend-persistence/src','packages/research-persistence/src',
  'packages/memory-service/src','packages/prompt-contracts/src'
) | ForEach-Object { Join-Path $PWD $_ }) -join ';')
```

New slice only:

```powershell
& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider apps/worker/tests/test_research_memory_context.py -q
```

Final result: **36 passed in 1.30s**, exit 0.

New slice plus adjacent existing deterministic tests:

```powershell
& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider apps/worker/tests/test_research_memory_context.py apps/worker/tests/test_research_adaptive_retrieval.py apps/worker/tests/test_research_conflict_investigation.py apps/worker/tests/test_research_v5c_agent_io.py -q
```

Final result: **70 passed in 2.02s**, exit 0. The existing 34 tests are regression support, not production activation evidence. No database fixture or external model is used.

The new tests exercise exact protected content, all six role labels, real verifier-input compatibility, two turns on one researcher Step and two operations on one gate Step, preserved mixed input order, producer/consumer distinction, phase/nested role identity, missing adaptive originals, started/failure/unresolved data, instruction-as-data, no minted authority/IDs, copy isolation, native PKs and negative body/hash/ordinal/phase/status/unloaded-row cases.

An initial developer run had 28 pass/1 fail: an overly broad test searched for the word `confirmation` anywhere, including the protected constraint `Do not infer confirmation.` The oracle was corrected to test for minted field names. Final runs above include the corrected oracle and expanded fixtures; no product behavior was changed to suppress the literal constraint.

Read-only workspace checks:

```powershell
git --no-optional-locks diff --exit-code
git --no-optional-locks diff --cached --exit-code
git --no-optional-locks status --short
git rev-parse HEAD
git branch --show-current
git remote -v
git config --local --get-regexp '^user\.'
git config --global --get-regexp '^user\.'
git config user.name
git config user.email
```

Tracked worktree/index diffs empty; only authorized new files plus the two pre-existing untracked design documents. Remote is `https://github.com/Gujiassh/citeframe.git`; no local user override; effective/global identity `gujishh <baiaoshh@163.com>`. No config change.

## Limitations and exact follow-on ownership

This is developer evidence for a pure, unactivated projection. Appointed reviewer `agt_26025b40` has not independently reviewed these implementation files in this session. Original designer `agt_af167b31` retains canonical design ownership. Controller relays findings and owns release/integration.

Caller preconditions remain real: all supplied bodies must already be authorized for shared task output, excluding every private owner's memory. A fully loaded ORM object does not prove commitment, producer provenance, ancestry, allowed evidence scope or current permissions; this function cannot establish those facts. It offers no private mode/audience field, memory lookup, source resolver or confirmation/evidence upgrade. Privacy and authorization integration are unproved.

No shared ABI delta was needed for the bounded projection. Later work requires approved owner deltas:

1. #43 archive/source owner: store/read exact original role/provider requests when required; adaptive hash/result alone cannot recover them. Conflict operation arguments cannot substitute for final provider requests.
2. #43/shared source and #42/native owners: approved source-locator/registry/resolver ABI, native commit/provenance and dependency authorization, immutable policy/base bindings and source-scope predicates. These local dictionaries do not freeze or implement that ABI.
3. Existing compaction/native owners: repeated same-Attempt coverage, one native ledger, exact request gating, cancellation/recovery, completed-tool/publication no-repeat proof. None is implemented or accepted here.
4. Controller/API/UI owners: full runtime and real visible UI acceptance, including twice-compaction within the same live Attempt without new input; semantic model quality remains separately gated.

## Artifact hashes and write-back

| New implementation artifact | SHA-256 |
| --- | --- |
| apps/worker/src/ai_pdf_worker/research/memory_context.py | 8F013879533AD1B648EFB51DA76507E845F395CAC993AC0EBA55C76146588E0D |
| apps/worker/tests/test_research_memory_context.py | CA54B56226A4236608B8CF6010513E0BD8557F18291B13C36B7825C0F911692C |

This evidence file's final hash is supplied in the handoff, avoiding a self-referential hash.

Bootstrap read applicable profile/workspace instructions, SOUL/IDENTITY, MEMORY-POLICY and subagents skill. `python` with bytecode disabled ran `D:/Code/dev-workbench/scripts/prepare_session.py --repo-path D:/Code/citeframe-lanes/issue45-research`; linked project/state/task files were read. Private MEMORY and daily memory were never read. Write-back check: durable findings are recorded here within the exclusive grant; profile memory and external workbench remain untouched. Controller can checkpoint the linked task using this evidence. No background test or delegated task remains.

## Controller delivery checkpoint

Controller reran projection plus native-adjacent tests:70passed in1.92s with lane-local import paths and bytecode/cache disabled. Appointed independent reviewer separately approved pure45a0 at36/70tests, with actual role-builder captures and preserved implementation hashes. The exact fullResearch design249C97FD is approved at design scope only. No schema/ABI/runtime activation grant follows this pure code delivery; aggregate input bounding remains a mandatory pre-load integration requirement. DraftPR will stack on PR49@812ebb1 and does not close45/41. No paid model or actual automatic-compaction/UI acceptance.

### Final formatting and verification

The original developer removed only two empty EOF lines from the test after review. Final test raw SHA-256: FAF4F76F83F401CF15BE285E29F9B8D3758AE5F1F8578F89568EA36AE97786A9. Implementation bytes are unchanged. Controller reran all 36 projection tests: 36 passed in 2.14s. This supersedes only the earlier test-file formatting hash; independent acceptance remains bounded to pure, unactivated projection.
