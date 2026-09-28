# Issue44 R3-A profile resolver — bounded candidate evidence

Date: 2026-09-28. Fixed controller baseline b0e30fb24d3c119573ea7a5d1a7b1607da2fc602; same authorized workspace. Governing original review SHA-256 `e06bd82578182a2944dee2f0658558f620e60984318264274eb00fbe7a4e9468` was fully read for F44-R1–R5. This is developer/controller verification, not independent reviewer closure.

## Exact candidate

| Artifact | SHA-256 |
|---|---|
| lanes/issue44-profile-binding.md | `26186416599bc39e3732f2842f77e84f4d6f6b347d461578eda2d16e83976338` |
| lanes/issue44-chat-loop.md | `5d032056a20e89d394a781303f37f698ab09ee63ea9bac4d030486e0e9de7a0f` |
| apps/api/src/ai_pdf_api/services/chat_runtime_profile.py | `c3f5df0bbc9ff52259afcee07a2c5dc4da53cee6472788b67536f7ced073cdf8` |
| apps/api/tests/test_chat_runtime_profile.py | `e0ec4b923a191e65068ecf4db4cd327a7c79d54dd47edcb0c3e2b71e719ba823` |

First two paths are relative to specs/v5/memory-management. The small contract was first presented at 66a1e32e...; current exact version additionally states canonical lowercase SHA-256 fingerprint validation and nonempty profileId/profileVersion strings. Use the full final hash above for review.

Product changes are exactly two new assigned files. Pure resolve validates all registry entries/closed counter implementations, invokes the trusted fingerprint function on the same immutable connection, binds source/revision and actual connection fields, enforces stricter physical/application output caps and requested reserve, computes bounded watermarks and returns an immutable local profile. Only existing CharacterEstimateCounter is instantiated; all resulting counts are estimated. No ModelConnectionSnapshot endpoint or client is fabricated by resolve. build_chat_generation and placeholders are absent.

The trusted fingerprint callback belongs to future authenticated composition, not request/tool parameters. Existing capability fingerprint algorithm remains unchanged. Synthetic fixtures deliberately omit source/revision from their old fingerprint to reproduce the independent review's binding condition; exact explicit selectors reject stale entries, and newly approved source/revision entries generate a different runtime binding. This is actual resolver execution, not a new run of the reviewer's global-function AST probe.

## Executed tests

Original implementation agent: **183 dedicated tests passed in0.85s**. Controller verification of actual local files: **364 passed in1.59s**, exactly183 profile +64 helper +117 provider/counting/wire. No skips/deselections/xfail or zero collection allowed; expected total364 enforced. Network connect/connect_ex/create_connection denied. Imported profile path asserted local. Only ai_pdf_api.services, chat_runtime_profile and model_config_types application modules were permitted; all other API/Worker modules denied. No conftests, plugin autoload, bytecode or pytest cache. The dedicated isolated subprocess additionally denies HTTP/SQL dependencies and settings/loaders while resolving and constructing the estimate counter.

Invocation uses the read-only cached dependency PYTHONPATH environment recorded in lane contract §13 plus apps/api/src, PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Exact pytest args:

```text
--noconftest --strict-markers -p no:cacheprovider -o pythonpath=
-o xfail_strict=true -q
apps/api/tests/test_chat_runtime_profile.py
packages/memory-service/tests/test_chat_loop_turns.py
packages/memory-service/tests/test_native_provider.py
packages/memory-service/tests/test_token_counting.py
packages/memory-service/tests/test_wire_provider.py
```

Actual-code oracles include strict nested unknown/missing fields, duplicate selectors/IDs, booleans/numbers/nonfinite values, output reserves/hard and watermark relations, source/revision/model/protocol/provider drift, endpoint/timeout/application-cap binding, secret-fingerprint drift, malformed fingerprint, callback/Unicode/canonical errors, immutable copied inputs, safe repr, cancellation capability and rejection of images/exact/unknown counter implementation. Three actual neutral serializers are exercised by CharacterEstimateCounter on explicitly synthetic snapshots. Neither synthetic physical capacities nor character estimates establish production provider capacity/tokenizer accuracy.

Frozen prior helper/test/workflow hashes were checked against accepted values and remain unchanged. No CI collection change was authorized for this new API test; hosted enforcement is controller-assigned later. No hosted/PG/native transaction/image/UI test claim.

## Contract corrections and remaining scope

Runtime §20 separates stable client intent from first accepted resolved snapshot and requires replay lookup before active-leaf/profile/source preflight; R1 needs real owner transaction replay/lost-ACK/collision proof. History now uses the original #43 transaction issuer→#42 source/query/range chain and strict versioned policy, with stable source-window cursor identity and per-call current counting; no second #44 history authorizer/implementation. §21 records actual unbounded source/decode/render behavior and proposes separate pre-read/pre-allocation limits to the original native owner; no native loader/render code was changed.

R3-B build waits for original reviewer acceptance of the exact R2/R4 small contract, including composition-owned with model_client lifecycle and injected transport. No new wait for #43 is imposed on that small review. Full start/finish/journal/source/interval/multimodal/SSE/runtime/UI work, actual production profiles and merge/service gates remain outstanding. This pure slice does not close #44/#41 or authorize activation.

Write-back is this evidence log and the two owned contracts. No shared/native/router/assets/settings/DTO/adapter/helper/CI edits, Git commands, commits/push, private memory access, real credentials or live/paid model calls. Original reviewer artifacts remain untouched. Return exact candidate to original reviewer; no finding is self-closed.


## 2026-09-29 — endpoint/cursor addendum and dedicated CI candidate

R3-A code is independently ACCEPTED in original review SHA-256 `7ec60a4e923c158133868c85948bf1291f2ff63fcdeb445bd2596ac03292cb50`: reviewer executed 364 tests plus 48 targeted checks and 192 JSON mutations. Those are prior reviewer results; this delta does not rerun or enlarge that approval. R2/R4 closure remains text-profile scope. R1/R3/R5 exact original-owner review and implementation remain pending.

Current changes are limited to the new `.github/workflows/chat-runtime-profile.yml`, profile-binding §5 endpoint addendum/status, chat-loop cursor wording (§7/§20), and this appended evidence. Historical evidence and original review remain intact. Product/test bytes are frozen. No builder, schema, native/router, config loader, shared DTO, adapter, old neutral workflow or production activation changes.

Endpoint addendum distinguishes workspace exact-base from server OpenAI v1 normalization, confines DeepSeek rewriting to server/deepseek/anthropic_messages, and rejects other combinations. It defines raw/final validation, same-origin check, pinned private connection access in trusted composition, snapshot timing and actual DNS/dial enforcement. Server ChatCompletions explicit routing is identified as proposed; no legacy factory parity claim. Builder is still absent and this addendum requires original review.

Stable cursor excludes connection/counter fingerprints, context version, renewable lease and previous request/tool-call identity. Every page obtains current profile/counter/request authorization and budget through the same #43→#42 authority. Insufficient budget leaves cursor unchanged. No second history permission authority is added.

### Actual workflow verification

New independent job uses checkout@v4/setup-uv@v6, `uv sync --project apps/api --frozen --extra dev`, then `uv run --project apps/api --frozen --no-sync python` with the committed heredoc. It explicitly selects only `apps/api/tests/test_chat_runtime_profile.py`, requires exactly 183 collected and 183 passed call reports, and rejects skip/deselect/xfail/missing/collect-only. API imports allow only the two package containers plus chat_runtime_profile and model_config_types; other API and all Worker imports reject. Socket creation/socketpair/create_connection and DNS functions reject. Local profile and memory contract module paths are asserted. Existing neutral workflow retains full application denial unchanged.

Developer extracted final workflow runner: **183 passed in 0.85s, exit 0**. Controller separately executed the same final heredoc unchanged: **183 passed in 0.76s, exit 0**. Controller's absent-path control exited **1** with `required chat profile test file is missing`. Developer also verified socket, DNS, forbidden API, Worker, collect-only and wrong imported-profile location controls all exit 1. Controls modify only in-memory runner strings; no product/test mutation.

Reproduction from workspace root uses the read-only cached dependency PYTHONPATH recorded in prior evidence, prefixed with local apps/api/src, packages/memory-service/src and packages/backend-contracts/src; PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Exact runner extraction/execution:

```python
p = Path('.github/workflows/chat-runtime-profile.yml')
body = textwrap.dedent(p.read_text().split("python - <<'PY'\n", 1)[1].rsplit('          PY', 1)[0])
subprocess.run([sys.executable, '-B', '-c', body], check=True)
```

Local verification used system Python with cached dependencies; it did **not** execute uv sync, install dependencies, or run hosted Ubuntu Actions. Hosted dedicated-job success remains controller/CI evidence pending push. No PG or live/paid model call was run.

Additional controller check extracted actual capabilities.normalize_provider_endpoint via AST with only stdlib urlsplit/urlunsplit. All 20 assertions for 5 paths × trailing slash variants × OpenAI/DeepSeek passed. This verifies existing path normalization for the proposed table; it does not execute a builder or validate network destinations. Workspace exact-base behavior was checked against the actual call site.

### Exact candidate hashes (SHA-256)

| File | Hash |
|---|---|
| `.github/workflows/chat-runtime-profile.yml` | `4a816968a145398cf6eebf32bed98a24c5845a75a004cce2184b4bab84b24f06` |
| `lanes/issue44-profile-binding.md` | `06c1837f709d2ba7e01acc69a26d3f3f3474e653c89e01dd6a13760408455647` |
| `lanes/issue44-chat-loop.md` | `721738b24f85957985bb91e2af632ed698da664f47c79d4e4f34a02288594c9d` |
| frozen `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` | `c3f5df0bbc9ff52259afcee07a2c5dc4da53cee6472788b67536f7ced073cdf8` |
| frozen `apps/api/tests/test_chat_runtime_profile.py` | `e0ec4b923a191e65068ecf4db4cd327a7c79d54dd47edcb0c3e2b71e719ba823` |
| unchanged `.github/workflows/memory-provider.yml` | `bbef4aed401e013e1e09a0206d2bd8fc01635de1b54b5c7fc3f52974873ec091` |

Lane paths are relative to specs/v5/memory-management. Write-back is this owned evidence and contracts; external workbench/private memory are not written under the current workspace-only permission. No Git calls, commits/push or model spend. Original reviewer recheck of this CI/docs delta and hosted execution remain outstanding. Full chat-loop/compaction/source/multimodal/SSE/UI delivery is not claimed.

## Controller pre-PR verification

Controller independently ran the 183 profile tests (0.60s), then extracted and executed the exact accepted workflow heredoc with isolated PYTHONPATH and plugin autoload disabled: 183 passed in0.54s. No network/provider invocation. Original appointed reviewer separately accepted the frozen profile and CI; review2240D791 retains F44-B1 for the future builder. This commit ships only pure resolution/schema/estimated counting and its dedicated CI. No builder, deployment profile, router/native lifecycle/source or actual-loop activation is included.

Baseline b0e30fb24d3c119573ea7a5d1a7b1607da2fc602 combines unmerged PR49@812ebb1 and unmerged PR47@1b9e1168. DraftPR stacks on PR49 and declares PR47 as a separate prerequisite. No baseline is represented as merged.
