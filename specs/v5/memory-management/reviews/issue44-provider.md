# Issue 44 neutral provider foundation — independent Critical review

**Current disposition: ACCEPT — neutral text-provider core only.** Final bounded recheck against integrated shared contract `a07b881529aded9dfcbead0634ec1eea15a7d36c`: 117 independent tests pass; F44-1/F44-3 closed and F44-2 retained closed. Exact candidate manifest and evidence are in the final section below. No broader feature or live-provider acceptance.

## Historical review checkpoint — evidence retained, disposition superseded

**Disposition: CHANGES REQUESTED. Two P1 findings remain open: F44-1 and the narrowed F44-3. F44-2 is closed for total-token translation.**

Review checkpoint: 2026-09-28 19:04 +08:00. Independent reviewer authored only this file. Findings are returned through controller to the original #44 developer; the #42 owner alone changes shared contracts.

## Findings, severity first

### F44-1 — P1, OPEN: redirects can disclose Anthropic credentials

**References:** `packages/memory-service/src/citeframe_memory/adapters/_generation.py:73`; `packages/backend-contracts/src/citeframe_contracts/memory.py:150–152`.

The adapter passes secret headers to the injected transport without enforcing a no-redirect policy. The shared `HTTPTransport.stream` contract has no redirect-policy parameter. An ordinary `httpx.Client(follow_redirects=True)` satisfies this call shape.

**Independent observation:** a mock 307 from `https://first.test/messages` to `https://second.test/messages` produced two HTTP requests, both carrying the synthetic Anthropic `x-api-key`, and then returned a successful answer. No real key or network connection was used. The developer's added actual-httpx redirect regressions independently fail for all three adapters.

**Required rework:** controller coordinates the sole #42 contract owner and original #44 developer to enforce no redirects at the shared transport boundary, including when the injected client defaults to following them. Retain one transport port. Assert no second request, no credential forwarding and no successful terminal event for 3xx; retain ordinary successful-response parity. Inspect the exact integrated contract and rerun all three regressions.

### F44-3 — P1, OPEN, narrowed: incomplete final Responses messages still become successful answers

**Reference:** `packages/memory-service/src/citeframe_memory/adapters/_streams.py:114–129`, especially the message branch at line 122.

The rework rejects incomplete final **function_call** items, but the final **message** branch does not check its status. A streamed `partial` followed by:

```json
{
  "type": "response.completed",
  "response": {
    "status": "completed",
    "output": [{
      "type": "message",
      "id": "message_A",
      "role": "assistant",
      "status": "incomplete",
      "content": [{"type": "output_text", "text": "partial"}]
    }]
  }
}
```

still returns:

```text
TextDelta(text='partial')
Usage(input_tokens=None, output_tokens=None, source='unknown')
TurnComplete(reason='answer')
```

**Required rework:** apply terminal-integrity validation to final message items as well, both in `response.output_item.done` and completed output. Explicit incomplete/in-progress statuses must not yield a successful terminal event. Add positive completed-message parity and negative variants; no new schema or orchestration framework is needed.

**Verified partial closure:** independently replayed the original mismatched tool item ID, incomplete final function and contradictory `incomplete_details` probes. All now raise `generation_protocol_invalid`. Valid identified/fragmented calls pass. Those repaired variants do not close the remaining message-status case.

### F44-2 — P1, CLOSED within total-token accounting scope

**Reference:** `adapters/_streams.py::AnthropicState.set_usage`, line 207 onward.

The earlier implementation omitted cache-read and cache-creation input. Original independent fixture input=10, cache_read=1000, cache_creation=500, output=2 had returned input=10.

Rework retains cumulative components and replaces repeated reported values before summing. The same independent HTTP fixture now returns **Usage(1510, 2, 'reported')**. Independently executed tests cover uncached-only, cache read, cache creation, combined, repeated cumulative data, updates and missing/unknown fields. Unknown totals remain unknown. This closes the reported total-input omission; the flattened DTO does not establish exact pricing-category billing.

## Evidence and scope judgment

| Review area | Status | Direct evidence / limit |
|---|---|---|
| Governing goal and current scope | Pass, review scope | Full canonical specification/design/inventory/reviews read; latest spec v4 §§13–14 and explicit authorization govern. |
| Neutral architecture and exact DTO imports | Pass, inspected candidate | One shared contract, no duplicate port; API/Worker imports blocked during local tests; no application module loaded. Injected connection, transport and observer; no global secret/settings/metrics dependency found. |
| Native protocol/request parity | Partial pass | Text and native tool/result mapping, fragmented/interleaved IDs/arguments, group validation and bounded errors exercised. F44-3 blocks terminal-integrity acceptance. |
| Credential/transport security | **Blocked** | F44-1 reproduced with actual httpx over mock HTTP. |
| Cancellation and transport lifetime | Pass, bounded cooperative scope | Pre-dispatch/between-event/pre-completion cancellation and generator-close tests; no late terminal success; transport closes before terminal event. Blocking IO interruption is not demonstrated; timeout behavior belongs to injected transport. |
| Usage translation | Pass, represented token fields | F44-2 corrected; partial/unknown/invalid counts exercised. No exact billing claim. |
| Counting plumbing/provenance | Pass, synthetic scope | Complete native text/tool payload reaches injected counter; model/protocol/fingerprint/capacity/version mismatch rejects; estimates labeled. |
| Actual known-tokenizer or official count accuracy | **Blocked / unrun** | `test_token_counting.py:21` injects a callback returning 123. No real tokenizer/provider accuracy or calibrated estimate safety margin is demonstrated. |
| Multimodal parity/accounting | Not implemented in this candidate | Shared message content is text-only; unsupported multimodal input rejects before HTTP. No image counting or broader parity acceptance. |
| Both application composition roots / deployment | Unrun | Direct neutral import is verified; actual API/Worker binding, class identity at those roots, locks and deployment are later owner/controller integration. |
| Shared-context exclusion of all private data | Required later; unrun here | No consumer integration. Private management permission cannot authorize private content in shared model inputs, tools, summaries, checkpoints, planning, logs or outputs. |
| Same-run automatic compaction / Research / UI | Outside this prerequisite; unaccepted | #43, later #44 loop, #45 and visible acceptance remain required. No parent completion inferred. |
| New schema, services, DB or product/test changes by reviewer | Not applicable | No such reviewer action. Only this artifact was written. |

**Current-code judgment:** do not accept the candidate while F44-1/F44-3 remain. **End-state judgment:** the neutral adapter/request/parser/counting separation and one shared contract point toward the approved architecture. Bounded corrections can retain that structure; no broad redesign is requested.

## Exact baseline, candidate and ownership

- Worktree: `D:/Code/citeframe-lanes/issue44-provider`; branch `work/issue44-memory-provider`.
- Initial clean starting SHA: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- During review, controller externally integrated shared contract/scaffold commit **`cfa4ab9a948f447e20964cd42e657f8830bb1615`**. Reviewer did not change Git state. Its four-file delta adds contract exports, `memory.py`, package manifest and root initializer. Provider implementation/tests remain uncommitted.
- Exact local shared `memory.py` SHA-256: **`7FE4D79830E7484F9D1FBB98E090BF837A9FD2D49819F4C5C2E41DA6D2716F4C`**.
- Developer/controller-owned reviewed delta: 10 adapter modules, 3 dedicated test modules, lane/evidence records. Shared contract/manifests/exports remain #42-owned.
- Full new source/test content was inspected. `git diff 8812fda... -- apps/api apps/worker` is empty. No new Worker-to-API imports or application wiring appear.
- No provider commit/push/PR was created by this reviewer. Developer ledger reports its staging attempt blocked by index.lock permission; this is not reviewer-authored Git activity.
- `git diff --no-index --check -- NUL <each new Python file>` found one nonblocking extra blank line at `_wire.py:145`; LF/CRLF warnings are environment notices. No code was changed to clean these.

Latest authorization permits the neutral parallel lane independently of #40 merge. A1 FINAL CHOICE 2 excludes new audience/private-thread/private-run schema and private recall into shared tasks. These supersede older A1/#40 gates in the historical design review. No private MEMORY or profile history was read.

### Stable reviewed file manifest

Paths below are under `packages/memory-service/`. Hashes matched across the independent local suite and final inspection.

| File | SHA-256 |
|---|---|
| src/citeframe_memory/adapters/__init__.py | 7A2007637C49D1B0182B11358806A311D35447C895E06A5F7C0DAD47E5A2B936 |
| src/citeframe_memory/adapters/_generation.py | 2F5FD14C399DC08C8F78E885CD862C59CAE952D80BC72DB05E766E9E22B65575 |
| src/citeframe_memory/adapters/_requests.py | C4AE3E5E73DE7DE6B8866C11E34BF4E29498304EB2F2A1D6F1472941282ECA05 |
| src/citeframe_memory/adapters/_schema.py | F2C1AC23A02AA92F1430EC35DD38ADC72DD4B2266B0CD81C6F1807F9230C7993 |
| src/citeframe_memory/adapters/_streams.py | 3E51614F82243234B354C2EC2009D90AE90EF504DA04BD840FCA31778F608B67 |
| src/citeframe_memory/adapters/_wire.py | EA4950CECD93723E6CE8B85D3CA58E4FC4168F3BC4539BDE23A3E02A93C5C656 |
| src/citeframe_memory/adapters/anthropic.py | ED2E46B975AD7D2ED236104AA6B895F532C06E379EE4999E88E005A97613B619 |
| src/citeframe_memory/adapters/chat_completions.py | DAE0354EF864B1463C29AADBD9962C904B5C951D00C7D092087226EC4A6B3F27 |
| src/citeframe_memory/adapters/counting.py | 5852ABE7D7A0D2951E4FB31F29CDD5B4DA38AC20AD2DDC977E5813B3FEC8FCA1 |
| src/citeframe_memory/adapters/responses.py | 1C7D1A28C30B460C74EE3F2525375EE605AA81FEBA94854BBE45B4DD9B275C4E |
| tests/test_native_provider.py | 35A7FCA919C8D7CA8A276F27B5224C0F4D2815BD1516139DB0B045333D3CC285 |
| tests/test_token_counting.py | 11A44906087EDF51C4231C4F4EC85FEE6333D590C0076D8B0E8F623D8CCD45FE |
| tests/test_wire_provider.py | 43724DB0321E944DAE14BBEDAF8702938909E6DBB4DE1F1EDDBC84925A63B4FD |

Authority read: effective spec v4 SHA-256 `566F549B415E34C1E7317A9A630BF0E11545FB3F689A55ECD0CD8E78AF990874`; design with current-authority preamble `B06F0E0CB36B01EFFFE007560C11F6DCC507031F851237DAF0452BBBD13CB690`; historical design review `C80C0BEE585A25744FCDD054A979128C0C4080593A5EB4EB8280D28E36A1FDCC`. Subsequent document changes require their own scope comparison.

## Independent execution record

Read-only interpreter: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, CPython 3.12.14, pytest 9.1.1, httpx 0.28.1. No installation, live-provider call, service or database access. Bytecode/cache writes disabled.

1. **Baseline:** 45 passed in 0.82s, existing `apps/api/tests/test_providers.py` at clean 8812fda; sockets denied, conftest/plugin autoload/cache disabled.
2. **Early draft:** missing shared contract initially prevented collection. Read-only #42 source overlay subsequently passed 17 wire tests, then 49 tests. These were dependency-overlay evidence and are superseded by the local-contract run.
3. **Stable local candidate:** **106 passed, 3 failed in 0.41s**. All three failures are `test_provider_redirects_disabled_with_permissive_httpx_client[ResponsesAdapter|ChatCompletionsAdapter|AnthropicAdapter]`. Hashes unchanged during execution; application imports list empty.
4. **Independent HTTP reverse probes:** reproduced cross-origin synthetic-key forwarding and incomplete-final-message success; reran original cached-usage and tool-identity/incomplete-function/incomplete-details cases to verify their repairs. Synthetic transport mechanics only.

### Reproduce the local suite

Run from this worktree; all sources are local to it:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH="$PWD/packages/memory-service/src;$PWD/packages/backend-contracts/src"
@'
import sys, socket, pytest, importlib.abc, pathlib, hashlib
class NoApplications(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('ai_pdf_api', 'ai_pdf_worker')):
            raise AssertionError('application import forbidden: ' + fullname)
sys.meta_path.insert(0, NoApplications())
import citeframe_contracts.memory as shared
print('LOCAL_SHARED_CONTRACT', shared.__file__)
def deny(*args, **kwargs):
    raise AssertionError('network forbidden')
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
paths = sorted(pathlib.Path('packages/memory-service').rglob('*.py'))
paths += [pathlib.Path(shared.__file__)]
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
status = pytest.main(['--noconftest', '-p', 'no:cacheprovider',
                     '-o', 'pythonpath=', '-q', 'packages/memory-service/tests'])
after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
print('STABLE_CONTENT', before == after)
for path, digest in after.items():
    print('SHA256', path, digest)
print('APPLICATION_IMPORTS',
      [m for m in sys.modules if m.startswith(('ai_pdf_api', 'ai_pdf_worker'))])
raise SystemExit(status)
'@ | & D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -
```

The import-smoke subprocess inherits bytecode-disabled local source paths. Its inspected body only imports neutral modules; no network activity occurs there. The 45-test baseline command uses the same socket denial, with `pytest.main(['--noconftest','-p','no:cacheprovider','-q','apps/api/tests/test_providers.py'])` and the repository's normal pythonpath configuration.

### Reproduce the remaining terminal-status case

With the same local PYTHONPATH and bytecode settings, run this through the same interpreter on stdin:

```python
import json, socket, httpx
from citeframe_contracts.memory import (
    GenerationMessage, GenerationRequest, ModelConnectionSnapshot
)
from citeframe_memory.adapters import ResponsesAdapter, Capabilities

def deny(*args, **kwargs):
    raise AssertionError("network forbidden")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
connection = ModelConnectionSnapshot(
    "openai_responses", "https://synthetic.invalid/responses",
    "synthetic", "synthetic-key", 2, "fp", 10000, 100
)
request = GenerationRequest((GenerationMessage("user", "hello"),), 50)
events = [
    {"type": "response.output_text.delta", "delta": "partial"},
    {"type": "response.completed", "response": {
        "status": "completed", "output": [{
            "type": "message", "id": "message_A", "role": "assistant",
            "status": "incomplete",
            "content": [{"type": "output_text", "text": "partial"}]
        }]
    }}
]
wire = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
with httpx.Client(transport=httpx.MockTransport(
    lambda request: httpx.Response(200, text=wire)
)) as transport:
    adapter = ResponsesAdapter(
        connection, transport, Capabilities(connection.protocol, "native-v1")
    )
    print(list(adapter.stream_turn(request)))
```

F44-1's developer-authored regression bodies currently present are at `tests/test_native_provider.py:495–516`; execute the suite command with `-k redirects_disabled` for the focused three-provider reproduction. The independent earlier Anthropic variant additionally recorded the actual synthetic header on both mock destinations.

## Handoff and write-back

Controller returns F44-1 to the original #44 developer plus sole #42 contract owner, and the narrowed F44-3 to the original #44 developer. Re-review requires the exact integrated contract and corrected file hashes, all dedicated tests, the negative HTTP probes and actual diff inspection. No provider/model quality or full-feature acceptance follows from a green adapter suite.

This review checkpoint is complete with changes requested. Durable results are contained only here; no private/profile memory, shared workbench, canonical file, product/test source, Git index/ref, service or database was modified by the reviewer. No commit or push was made.

## Final bounded recheck — 2026-09-28

**ACCEPT — neutral text-provider core only. F44-1 and F44-3 are closed; F44-2 remains closed. No new finding was identified in this bounded correction.**

### Governing scope and exact candidate

Revalidated effective specification v4 §§13–14 before code acceptance. A1 remains Choice 2: no private thread/run mode or native audience schema; private storage/management does not authorize private data in any shared consuming boundary. Those downstream exclusion tests remain required and unexecuted here. Same-run compaction remains a later #43/#44-loop/#45 obligation.

Verified local HEAD **a07b881529aded9dfcbead0634ec1eea15a7d36c** and inspected its actual diff from cfa4ab9: the sole shared-contract change adds the required keyword-only `follow_redirects: bool` and documents total-input usage semantics. No duplicate port or application dependency was introduced.

Compared every source/test file against the previous review manifest: only `_generation.py`, `_streams.py` and `test_native_provider.py` changed among the 13 provider files. Inspected those bounded edits and added tests. Other 10 file hashes are unchanged. Provider implementation/tests remain uncommitted; this acceptance identifies their content hashes, not a future provider commit. Controller owns commit/push/PR.

### Independent closure evidence

| Finding | Independent reproduction and observation | Disposition |
|---|---|---|
| F44-1 | Verified the exact shared signature requires the redirect keyword; the common adapter passes `follow_redirects=False` for all three protocols. Using actual `httpx.Client(follow_redirects=True)` with MockTransport, independently tested **301, 302, 303, 307 and 308 for each adapter**. Each run observed only first.test, raised generation_http_error, emitted no ToolCallComplete/TurnComplete and never observed completed. No request or secret header reached second.test. Normal nonredirected text responses still completed for all three. | **Closed** |
| F44-3 residual | Independently supplied final MESSAGE items with **incomplete, failed and in_progress**, separately at output_item.done and response.completed.output. All six variants raised generation_protocol_invalid before successful terminal events; provisional text did not become an accepted answer. Completed and omitted item status both passed with explicit completed response metadata. The earlier tool-item identity/incomplete-function/incomplete_details regressions remain covered by the passing dedicated suite. | **Closed** |
| F44-2 | Retained prior closure. Independently replayed base=10, cache-read=1000 and cache-creation=500, repeated cumulatively in message_delta: returned Usage(1510,2,'reported'), without duplicate charge. Shared Usage docstring now explicitly states total-input semantics. | **Closed for total-token translation; no pricing-category billing acceptance** |

This is behavioral evidence from synthetic HTTP, with no live-provider request or model call. It establishes the bounded transport/parser correction and preserves existing text parity.

### Dedicated suite and execution safeguards

Fresh independent retry: **117 passed in 0.29s**. Read-only interpreter was `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe` (CPython 3.12.14, pytest 9.1.1, httpx 0.28.1). Local provider and local shared-contract source paths only; no cross-worktree contract overlay.

Used the earlier recorded suite command with these same settings:

- PYTHONDONTWRITEBYTECODE=1, interpreter -B, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1;
- local PYTHONPATH containing packages/memory-service/src and packages/backend-contracts/src;
- `pytest.main(['--noconftest','-p','no:cacheprovider','-o','pythonpath=','-q','packages/memory-service/tests'])`;
- a meta-path finder rejects ai_pdf_api/ai_pdf_worker imports;
- socket.socket.connect, connect_ex and socket.create_connection replaced with a denial function.

The independent HTTP probes ran under the same import/network guards, constructed their own fixtures without importing developer test helpers, and used only httpx.MockTransport. Source, tests and contract hashes matched before/after the suite and probes; application import list was empty.

Reproduction anchors retained above: the previous independent incomplete-message script now raises generation_protocol_invalid; vary its status across the three values and place the same item in output_item.done to reproduce the six negatives. For redirects, the dedicated test `test_provider_redirects_disabled_with_permissive_httpx_client` now passes for all three adapters; the independent probe additionally varied the redirect status through 301/302/303/307/308 while retaining the same first.test→second.test target and success-shaped second response. Positive ordinary responses and completed/omitted message-status cases were checked separately.

### Final acceptance boundary

- **Accepted:** neutral text-provider core, including native tool-call wire assembly/result pairing, strict terminal validation, no-redirect transport behavior, represented usage translation and existing synthetic counting/provenance plumbing.
- **Architecture accepted within this boundary:** one shared contract, injected configuration/transport, no new Worker-to-API imports, no additional schema/framework. Bounded fixes preserve the intended neutral ownership.
- **Not accepted or claimed:** live-provider compatibility/model quality, real tokenizer/official counting accuracy, calibrated estimation margins, multimodal parity, exact billing, application composition/deployment, private-source exclusion at consumers, journal/recovery behavior, automatic compaction, chat/Research loop integration or UI usability.
- Cooperative cancellation retains its prior scope; blocking IO interruption depends on the injected transport's timeout behavior.
- Historical test failures and earlier manifests remain above as evidence of the defects and their progression. This final scoped disposition supersedes their open findings; it does not generalize a local PASS to #44 or #41 completion.

### Final exact candidate manifest

All hashes below were independently verified against the local candidate after the passing run.

| Repository-relative file | SHA-256 |
|---|---|
| `packages/memory-service/src/citeframe_memory/adapters/__init__.py` | `7A2007637C49D1B0182B11358806A311D35447C895E06A5F7C0DAD47E5A2B936` |
| `packages/memory-service/src/citeframe_memory/adapters/_generation.py` | `F7E2335BA034FB79573799916C80529FF540B186C9D97D21556788AC9D0CAD7A` |
| `packages/memory-service/src/citeframe_memory/adapters/_requests.py` | `C4AE3E5E73DE7DE6B8866C11E34BF4E29498304EB2F2A1D6F1472941282ECA05` |
| `packages/memory-service/src/citeframe_memory/adapters/_schema.py` | `F2C1AC23A02AA92F1430EC35DD38ADC72DD4B2266B0CD81C6F1807F9230C7993` |
| `packages/memory-service/src/citeframe_memory/adapters/_streams.py` | `40629D07A39B74BE2295FFD092A06ADB29CF1A9ACDEE44799C4EE118D52A4EFC` |
| `packages/memory-service/src/citeframe_memory/adapters/_wire.py` | `17A31AA4AAE50FFDB3CEE93F41C8A95A87E005FBB62EA707624ABDA6AE319D25` |
| `packages/memory-service/src/citeframe_memory/adapters/anthropic.py` | `ED2E46B975AD7D2ED236104AA6B895F532C06E379EE4999E88E005A97613B619` |
| `packages/memory-service/src/citeframe_memory/adapters/chat_completions.py` | `DAE0354EF864B1463C29AADBD9962C904B5C951D00C7D092087226EC4A6B3F27` |
| `packages/memory-service/src/citeframe_memory/adapters/counting.py` | `5852ABE7D7A0D2951E4FB31F29CDD5B4DA38AC20AD2DDC977E5813B3FEC8FCA1` |
| `packages/memory-service/src/citeframe_memory/adapters/responses.py` | `1C7D1A28C30B460C74EE3F2525375EE605AA81FEBA94854BBE45B4DD9B275C4E` |
| `packages/memory-service/tests/test_native_provider.py` | `2A210C9F6A7E1B0DA85BDA9FB1F386E26BB91CA5DA1BEBF9FD425D94342415B1` |
| `packages/memory-service/tests/test_token_counting.py` | `11A44906087EDF51C4231C4F4EC85FEE6333D590C0076D8B0E8F623D8CCD45FE` |
| `packages/memory-service/tests/test_wire_provider.py` | `43724DB0321E944DAE14BBEDAF8702938909E6DBB4DE1F1EDDBC84925A63B4FD` |
| `packages/backend-contracts/src/citeframe_contracts/memory.py` | `B1A0D53B5D21BAC31AC12609A5A798CCEDA5F9AAB43EEFAA4E178A3D9D5AAE45` |

Prior review artifact SHA-256 before append: `002FCF41A57533DF7AC3FD03959AC2327DA9F32CA948EA7C0E16D37199C2A422`. Recheck recorded at 2026-09-28T19:24:04.507598+08:00.

### Reviewer completion and write-back

Bounded recheck complete; no remaining F44-1/F44-2/F44-3 rework is requested for this exact candidate. No product, contract, manifest, Git index/ref, service, DB, canonical or shared-workbench write was performed. No live/paid model call. Only this original review was updated; all earlier review evidence was retained. Durable write-back is this appended closure and manifest. Controller retains delivery ownership.

### Final delivery-snapshot confirmation

During report delivery, controller-side staging and an external `_wire.py` cleanup became visible. The actual unstaged diff removes only the extra blank line at EOF previously noted by this reviewer. No semantic code changed. The final manifest above already pins the cleaned `_wire.py` SHA-256 `17A31AA4AAE50FFDB3CEE93F41C8A95A87E005FBB62EA707624ABDA6AE319D25`; the earlier historical manifest is preserved unchanged.

Independently reran the complete dedicated suite after that cleanup with the same network/app-import denial: **117 passed in 0.38s**, all candidate source/test hashes stable during the run and application import list empty. The scoped ACCEPT remains valid for this final manifest. Reviewer performed no staging or other Git write.

Controller subsequently created provider commit 20717edba6e77e100e0cb2d18e6d75361a678586, parent a07b881529aded9dfcbead0634ec1eea15a7d36c, while this reviewer delivered the report. Read-only verification confirmed that all 14 entries in the final manifest still match the current worktree. This maps the content-scoped ACCEPT to that controller-created commit; no reviewer commit/push or remote CI/PR acceptance is implied.


## Scoped hosted-CI review — 2026-09-28

**ACCEPT — the new dedicated provider workflow and its scoped manifest/document delta. No actionable finding identified.** F44-1/F44-3 remain closed; F44-2 remains closed for total-token translation. The accepted neutral text-provider core and all earlier review evidence are retained unchanged.

### Scope and candidate identity

Revalidated effective specification v4 §§13–14 / A1 Choice 2. This change enforces the three existing synthetic provider/counting suites in an isolated CI job. It introduces no audience/private-thread/private-run schema, consumer integration, or wider acceptance. Private-source exclusion at every later shared consuming boundary and same-run compaction remain required downstream oracles.

Read-only HEAD at review: `c739650f8f85d1d4c23745b1de104b624bd05d71`; accepted provider commit: `20717edba6e77e100e0cb2d18e6d75361a678586`; integrated shared-contract commit: `a07b881529aded9dfcbead0634ec1eea15a7d36c`. The CI candidate is an uncommitted delta identified by these SHA-256 hashes:

| Repository-relative file | SHA-256 |
|---|---|
| `.github/workflows/memory-provider.yml` | `0147FB741DB6ED737942A258F189B0D561CEC77BD1B688FFA247D82A86FA5412` |
| `specs/v5/memory-management/evidence/issue44-provider/sha256.txt` | `49207EF2E3F86ADFE03D26D18666C6683DF24FC6DAD9EE8A9D247596C82CF571` |
| `specs/v5/memory-management/lanes/issue44-provider.md` | `0A3183ED5CC2961F47AC12CBAC20AF46E3A24BF0E3419D409BC1AF2F4715A2D7` |

Review artifact SHA-256 before this append: `CB93ABCAA2C6D1CF9839CC75092B414135621141BD0F6A23041C936AEECE0A9D`.

### Independent verification

| Area | Result and evidence |
|---|---|
| Frozen environment and exact contract | **PASS.** Installation is `uv sync --project apps/api --frozen --extra dev`; execution is `uv run --project apps/api --frozen --no-sync python -`. Explicit repository source paths precede installed packages. The runner asserts the imported contract resolves to this checkout's `packages/backend-contracts/src/citeframe_contracts/memory.py`. Its hash remains `B1A0D53B5D21BAC31AC12609A5A798CCEDA5F9AAB43EEFAA4E178A3D9D5AAE45`. |
| Exact YAML/heredoc | **PASS.** Parsed the actual file with PyYAML 6.0.3 BaseLoader; verified PR/main-push triggers, standalone job, permissions and frozen commands. The extracted run block has the exact quoted `<<'PY'` opener and unindented `PY` terminator after YAML deindent. Its Python AST parses; feeding the shell block to Git Bash `bash -n` exits 0. The workflow uses the correct Linux colon-separated PYTHONPATH. |
| Exact runner execution | **PASS.** Executed the extracted Python body without modifying it, using read-only `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`, CPython 3.12.14 / pytest 9.1.1 / httpx 0.28.1 (matching locked pytest/httpx versions). Only the local environment's PYTHONPATH separator was adapted for Windows. Independent initial run: **117 passed in 0.33s**; final exact-file rerun: **117 passed in 0.38s**, exit 0. PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 were retained. |
| Isolation and collection | **PASS.** Before collection, the runner rejects ai_pdf_api/ai_pdf_worker imports and denies socket connect/connect_ex/create_connection. It verifies application modules are absent afterward. An additional observation-only collection probe confirmed exactly 117 items from `test_native_provider.py`, `test_token_counting.py`, `test_wire_provider.py`, with no API/Worker, sqlalchemy, psycopg or psycopg2 modules loaded. No broad directory target, PostgreSQL service or database URL is used. |
| Failure/skip enforcement | **PASS.** Exact three-file selection uses `--noconftest --strict-markers -p no:cacheprovider -o pythonpath= -o xfail_strict=true -q`. Current dedicated sources contain no skip/xfail/selection weakening. Exercised the extracted RequireExecutedTests class through actual pytest hooks using in-memory items: a clean pass exits 0; failure, runtime skip, collection skip, partial deselection with a remaining passing item, zero collection, strict expected-failure and explicitly nonstrict expected-failure cases all exit 1. No continue-on-error or failure suppression appears in the job. |
| Privileges and external calls | **PASS within test-runner scope.** `contents: read`, ordinary pull_request/main-push events, ten-minute timeout, no secrets, pull_request_target, privileged command, service or paid-model invocation. Dependency setup uses the ordinary hosted install path. Python connection guards protect fixture execution; this is not a claim of an OS-level network sandbox or offline dependency installation. |
| Manifest/document delta | **PASS.** Recomputed all 14 manifest entries, all matching. Its sole changed entry corrects the already accepted `_wire.py` EOF-cleaned hash to `17A31AA4AAE50FFDB3CEE93F41C8A95A87E005FBB62EA707624ABDA6AE319D25`. The lane document records scoped core acceptance, CI behavior and pending hosted evidence accurately. Product/tests, shared contract, API dependency files/lock and existing #42-owned `.github/workflows/ci.yml` have no delta from accepted provider commit. |

### Standalone PR49 and later PR48 integration

**PASS for the inspected dependency/collection structure.** The current API frozen lock supplies the fixture dependencies; PYTHONPATH supplies the local provider package, so standalone PR49 does not require PR48's package registration. Read-only comparison with the #42 worktree shows its package root remains inert and its persistence tests are in a separate `test_instruction_memory.py`. Explicit three-file targets, disabled plugin autoload, `--noconftest` and the overridden empty pytest pythonpath avoid that PostgreSQL collection path after integration. The workflow has no `needs` coupling to #42 CI. Shared contracts/manifests remain single-owner; no duplicate port or Worker-to-API import is introduced.

Actual merged PR48 execution and the owner-maintained merged dependency locks still require controller/hosted verification. This structural review does not certify an unexecuted future merge snapshot.

### Limits and handoff

Ubuntu Actions execution and `uv sync --project apps/api --frozen --extra dev` installation were **not run locally**. Local evidence covers the exact runner, compatible shell syntax, candidate hashes, negative enforcement oracles and inspected dependency structure. Hosted results remain pending controller push/CI; no remote-green claim is made.

No live-provider compatibility, model-quality, real tokenizer accuracy, chat/UI, privacy-consumer integration, automatic compaction or full #44/#41 completion is accepted by this CI review. The workflow remains aligned with the neutral prerequisite architecture.

Write-back check: durable scoped judgment and exact evidence are appended only to this original review. No product, test, workflow, contract, manifest, lane document, Git index/ref, private/profile memory, canonical/shared-workbench, service or DB write was performed by the reviewer. Controller retains commit/push/PR ownership.
