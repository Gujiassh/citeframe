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
