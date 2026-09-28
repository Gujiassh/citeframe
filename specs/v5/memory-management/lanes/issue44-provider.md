# Issue 44 neutral provider foundation

## Delivery boundary

- Branch: `work/issue44-memory-provider`.
- Starting ref: main `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Isolated workspace: `D:/Code/citeframe-lanes/issue44-provider`.
- Scope: neutral Responses, Chat Completions and Anthropic-compatible adapters, explicit counting/capacity, dedicated synthetic protocol tests.
- Shared DTOs, exceptions, ports, package root/scaffold and dependency/deployment changes belong exclusively to #42. No duplicate port declarations or branch merge is authorized here.
- No persistence/journal schema, application wiring, tool execution loop, compaction orchestration, Research activation or UI acceptance is included. This is a partial prerequisite for #44; #44 and #41 remain open.

## Governing decisions

Read the approved design, repository spec including full section 12, and external proposal section 12. The synchronized spec v4 sections 13–14 and latest controller instruction govern implementation. A1 is resolved: existing shared outputs keep their visibility; private storage/management remains separate; shared prompt, tools, history, sources, summaries, checkpoints, planning and outputs must never ingest private data, including the requester's own private content. Shared automatic compaction and frozen Research evidence requirements remain in full downstream scope.

Adapters receive already-authorized neutral inputs. This lane provides no source retrieval or permission service; integration must enforce the shared-output exclusion before dispatch and result adoption. Parser tests cannot establish end-to-end privacy or compaction acceptance.

## Acceptance oracle

1. Native request mapping and exact text fixtures retain required provider behavior without application imports.
2. Tool IDs remain exact; fragmented arguments are bounded, validated JSON objects. Duplicate/unknown calls, unmatched results and incomplete groups fail closed.
3. Only explicit successful protocol terminal markers produce successful turns. Refusal, invalid/incomplete output, cancellation and transport errors cannot become text-only success.
4. Tools and streaming tools require explicit capabilities before transport dispatch. Prose never creates tool calls.
5. Capacity and counter identity/version/mode are explicit; unknown capacity or unsupported accounting rejects. Estimates are labeled; provider-reported usage is distinguished from estimated and unknown values.
6. Injected configuration/transport has no API/Worker/settings/credential-loader dependency; import smoke makes both apps unavailable.
7. Synthetic fixtures establish protocol mechanics only. No paid model calls, real-model quality, database recovery, actual loop or visible-product claim.

## Dependencies and delivery state

- #42 contract/scaffold commit `cfa4ab9a948f447e20964cd42e657f8830bb1615` and required redirect-policy correction `a07b881529aded9dfcbead0634ec1eea15a7d36c` were integrated by controller. Current local `memory.py` SHA-256: `B1A0D53B5D21BAC31AC12609A5A798CCEDA5F9AAB43EEFAA4E178A3D9D5AAE45`. This lane did not edit/copy/merge shared declarations. Verification uses only this worktree's contract.
- Shared application dependency declarations, locks and deployment integration remain #42/controller-owned.
- Assigned independent reviewer will judge this lane separately. Prior R1–R16 closure is design-only.
- Local GitHub remote and local/global `gujishh` identity match. Initial `gh auth status` reported invalid authentication; push/draft PR may require controller delivery.
- Workbench bootstrap read the registered `memory44-provider` task. Workbench and global-memory writeback are outside this writable lane; durable implementation evidence is recorded here for controller synchronization. No private MEMORY was read.

## Verification

Bounded-rework controller rerun: **117 passed in 0.47s**, against local HEAD `a07b881529aded9dfcbead0634ec1eea15a7d36c`, Python 3.12 / pytest 8.4.2 and httpx 0.28.1. Socket connections were denied, API/Worker imports were blocked, and source/contract hashes stayed unchanged throughout execution. AST and trailing-whitespace checks passed all 13 owned Python files plus the shared contract. Earlier 106-pass/3-fail evidence is superseded by the corrected candidate. Independent final recheck remains required; this is not shipping approval.

The current shared `GenerationMessage.content` contract is text-only. Multimodal input is rejected; multimodal accounting and parity require an owner-reviewed DTO extension and are outside this candidate. Model endpoints are injected as full protocol URLs; application composition remains outside the lane.



## Implementation and use

Public exports in `citeframe_memory.adapters`:

- `ResponsesAdapter`, `ChatCompletionsAdapter`, `AnthropicAdapter`: shared `GenerationPort.stream_turn(GenerationRequest)` emits the exact shared event DTOs. `generate()` aggregates a text answer and rejects tool turns.
- `Capabilities`: explicit protocol/version and tools/streaming-tools/cancellation flags. Protocol/version mismatch or unsupported requested capability rejects before transport.
- `CountingProfile`, `PayloadTokenCounter`, `CharacterEstimateCounter`: explicit model/protocol/fingerprint/capacity/counter identity and version. The injected counter receives the full native serialized payload including tools, calls, results and framing. Its model-specific tokenization/accounting accuracy is the caller's responsibility. Character estimates require explicit ratio/overhead and always return estimated mode; these tests do not calibrate a production safety margin.
- `WireLimits`: default arguments 16 KiB, IDs 255 UTF-8 bytes, aggregate request/turn 1 MiB, per-event 256 KiB, 10,000 events and 16 calls. Limits reject oversized input/output without truncation.

Connections supply the complete native endpoint URL and credentials directly to injected `HTTPTransport`. No application settings, credential loader, HTTP client factory or metrics global is imported. Every transport request explicitly passes `follow_redirects=False`, including with a redirect-enabled client default. The adapter performs one streamed provider turn; transport owns IO deadlines and honors the required redirect policy. Cooperative cancellation is checked before dispatch, between decoded events and before completion. A blocking transport read is bounded by the injected transport's timeout behavior.

The native state machines preserve exact call IDs and native index order, assemble fragmented arguments, validate the entire call batch before any complete call event, and require protocol completion. Responses terminal text/call payloads are reconciled when supplied. Tool history requires every exact result before a new non-tool message. Supported JSON-schema keywords are explicit; unknown keywords reject before dispatch. No prose-tools or text fallback exists.

`TextDelta` and `ToolCallDelta` are provisional. Consumers must wait for `TurnComplete` before accepting an answer or executing a tool batch, and must discard provisional results on error/cancellation. Transport closure succeeds before terminal success. Missing usage stays unknown; partial reported usage keeps absent fields as `None`. Failed/unknown calls do not establish zero cost; future ledger integration must retain its reservation/unknown-outcome rules.

## Evidence and remaining integration

- [Reproduction and scope](../evidence/issue44-provider/README.md)
- [Full scoped pytest output](../evidence/issue44-provider/pytest.txt)
- [Stable candidate source/test hashes](../evidence/issue44-provider/sha256.txt)
- [Assigned independent review](../reviews/issue44-provider.md), maintained by its owner.

No API/Worker composition, dependency locks/deployment, privacy source admission, call journal, runtime loop, automatic compaction, Research integration, semantic-model quality or visible UI was exercised. Shared deployment/dependency integration remains #42/controller-owned. No live provider or paid model was called. No issue closure or merge is authorized by this foundation evidence.

Commit/push/PR delivery status is recorded below after the attempted delivery operation. Reviewer-owned files are excluded from developer staging.

## Bounded review rework and delivery status

| Finding | Corrected candidate / evidence | Review disposition |
|---|---|---|
| F44-1 | `_generation.py` passes required `follow_redirects=False`. All three actual-httpx cross-origin 307 fixtures use a redirect-enabled client, reject the response, observe only the first destination and emit no successful terminal event. | Implemented; final independent recheck pending |
| F44-2 | Prior cumulative uncached/cache-read/cache-creation translation retained unchanged by this bounded rework. | Independently closed for total-token translation; no pricing-category billing claim |
| F44-3 residual | `_streams.py` rejects explicit noncompleted final message status at `response.output_item.done` and completed response output. Six negative cases cover incomplete/failed/in_progress; two positive cases preserve completed and omitted status. Prior tool-identity and incomplete-function/details repairs remain covered. | Implemented; final independent recheck pending |

Only `_generation.py`, `_streams.py` and `test_native_provider.py` changed in this bounded implementation rework. Lane/evidence records were refreshed separately; the independent review artifact remains reviewer-owned. The developer is stopped and available for recheck findings.

Current HEAD is the controller-integrated shared correction `a07b881529aded9dfcbead0634ec1eea15a7d36c`. Provider changes remain unstaged. No staging, commit, push or PR operation was attempted in this rework; controller owns delivery and PR attachment after independent acceptance. The earlier staging permission failure and local gh authentication limitation remain recorded in the prior handoff. No merge or issue closure is claimed.

Suggested commit subject: `feat(memory): add neutral provider and counting adapters`.
PR references: `Refs #44 (partial prerequisite); parent #41 remains open.`

Write-back check completed: exact dependency, bounded changes, stable hashes, reproducible tests and acceptance limitations are recorded in the lane/evidence. No private/profile-memory or out-of-lane workbench write occurred. Controller synchronizes its shared ledger.

## PR49 delivery and scoped final acceptance

This checkpoint supersedes the earlier pending-delivery and pending-recheck statuses above; historical evidence remains retained.

- PR: https://github.com/Gujiassh/citeframe/pull/49 (controller reports pushed; draft delivery, no merge claim).
- Provider commit: `20717edba6e77e100e0cb2d18e6d75361a678586`.
- Independent review artifact commit: `c739650f8f85d1d4c23745b1de104b624bd05d71`.
- Original reviewer final disposition: **ACCEPT, neutral text-provider core only**. Final exact-candidate rerun: 117 passed with network/application-import denial. F44-1/F44-3 closed; F44-2 remains closed for total-token translation. This maps to the cleaned `_wire.py` content and the provider commit.
- The evidence manifest now corrects only the stale `_wire.py` EOF-formatting hash to `17A31AA4AAE50FFDB3CEE93F41C8A95A87E005FBB62EA707624ABDA6AE319D25`, matching the reviewer's final manifest. No adapter code changed in this CI slice.
- New hosted workflow `.github/workflows/memory-provider.yml` is authorized separately. Existing `ci.yml`, shared dependencies, locks and deployment remain untouched and #42/controller-owned. This small CI delta requires the original reviewer's separate review; core acceptance does not pre-approve it.
- The workflow targets only `test_native_provider.py`, `test_token_counting.py` and `test_wire_provider.py` through the frozen API dev environment and local neutral source paths. No PostgreSQL suite or database URL is required by this dedicated job.
- Controller retains commit/push/PR attachment and merge decisions. No Git writes are performed by this lane for the CI delta. #44/#41 remain open; downstream composition, real tokenizer/model quality, private-source exclusion, loops, compaction, Research and UI acceptance remain outside the core approval.

### Dedicated CI verification

- Workflow SHA-256: `0147FB741DB6ED737942A258F189B0D561CEC77BD1B688FFA247D82A86FA5412`.
- Parsed the YAML with PyYAML 6.0.3 `BaseLoader` and verified PR/main-push triggers, existing action versions, frozen API dev installation, absent service dependencies and exactly the three named test paths.
- Extracted and executed the workflow's exact embedded Python runner locally with the previously documented read-only pytest/httpx cache dependencies: **117 passed in 0.43s**. API/Worker imports and socket connections are denied by that runner. The `--noconftest` and cleared pytest pythonpath options isolate the dedicated files from future #42 PostgreSQL discovery/conftest loading; no database URL is supplied or needed.
- Independently exercised the runner's guard: collection skip, test skip, deselection and zero collection each fail; a successful execution remains successful. Application-import and network-denial checks pass. No skip, marker exclusion, broad test directory or hard-coded test count bypasses execution.
- Recomputed all 14 entries of the existing candidate manifest: all match. Its only edited line is the stale `_wire.py` EOF hash. Adapter/test/dependency/shared-workflow files have no delta.
- `git diff --check` passes after the documentation update. No Git writes, services, live providers or paid calls were used.
- Local checks establish workflow structure and exact runner behavior. Ubuntu Actions execution and `uv sync --project apps/api --frozen --extra dev` installation were not run locally; hosted evidence remains pending controller delivery and CI. Original reviewer separately reviews this CI delta before acceptance.

Write-back check: PR49 delivery, scoped final core acceptance, CI verification and limitations are recorded here; historical sections and the original test log/review remain unchanged.

## Authorized PR48 dependency merge reconciliation

Controller began the no-commit merge of `work/issue42-memory-persistence` at `1d4f9e377785bda28c62029cd524c3cd6ba4c567` into provider HEAD `eb3f022ae099fceb56e2c08066689c1090d1bfe5`. This checkpoint records the integrated working tree before controller staging/merge commit; it is not a new commit or merge-completion claim.

The sole conflicted source, `packages/backend-contracts/src/citeframe_contracts/__init__.py`, was written byte-for-byte from `git show 1d4f9e3:packages/backend-contracts/src/citeframe_contracts/__init__.py`. It preserves #42's consolidated memory imports and single shared export extension. No ABI was invented or modified beyond selecting that exact accepted target.

- Exact target/source SHA-256: `8EFB07BF464BCAA1D745B3B1455E6825AA45BE96B4C0B56435F34FC8FA8D5091`.
- Exact target Git blob: `ad1689e568a54202e51fadc62fbe107ee4e7f51d`.
- Size/format: 11,130 bytes, LF; equality with raw target bytes verified; conflict markers absent.
- All 14 provider/contract candidate-manifest entries still match. Provider adapters/tests and `.github/workflows/memory-provider.yml` are unchanged; workflow SHA-256 remains `0147FB741DB6ED737942A258F189B0D561CEC77BD1B688FFA247D82A86FA5412`.
- All other automatically staged files belong to the reviewed #42 dependency and were untouched. The index retains the unmerged entry until controller stages this source; no Git index/ref write was performed here.

### Integrated-tree verification

Reused the existing read-only `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe` with `-B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and this worktree's local neutral source paths. No install, service, DB or model call was performed.

| Check | Explicit scope / execution | Result |
|---|---|---|
| Neutral provider | Exact embedded runner from `memory-provider.yml`; three explicit provider/counting/wire files, network and application-import denial | **117 passed in 0.36s** |
| API deploy | `pytest --noconftest -p no:cacheprovider -q apps/api/tests/test_deploy_dependencies.py` plus fresh verified workspace-local `--basetemp` | **6 passed in 0.19s** |
| Worker deploy | `pytest --noconftest -p no:cacheprovider -q apps/worker/tests/test_deploy_dependencies.py` | **2 passed in 0.06s** |
| Persistence boundaries | `pytest --noconftest -p no:cacheprovider -q apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py` | **13 passed in 2.72s** |

Deploy/boundary invocations also denied socket connection entry points in the test process; application imports remain permitted for the boundary tests that explicitly verify existing composition identities. The first API deploy invocation returned 5 passed/1 setup error because the default user pytest temp directory was inaccessible. Re-running all six with a fresh workspace-local basetemp resolved that environment error; no test/product code changed.

The 44 PostgreSQL persistence cases were **not run** and are not reported as passed or accepted. Their fixture requires `CITEFRAME_MEMORY42_POSTGRES_URL` pointing to the disposable `citeframe_memory42_test` database; it fails in CI when absent. These non-DB checks do not establish migration/CAS/erasure/runtime acceptance.

`git diff --check` passes for the working-tree correction/report. Controller retains staging, merge commit, push and PR decisions; original reviewer performs the subsequent integrated-snapshot check. Write-back is confined to this lane report, with no profile/private-memory or shared workbench update.
