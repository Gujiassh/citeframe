# Chat runtime profiles

`chat_runtime_profile.py` resolves a trusted provider policy against one `ModelConnection`. Its builder returns a neutral generation adapter and a character-estimate counter. The module is text-only and has no production loader or native dispatch caller. It supplies no calibrated model registry, model-quality evidence or complete issue44 runtime.

## Registry identity

The resolver requires `chat-provider-registry-v1` and an actual list of profiles. It validates every entry, including entries that do not match the selected connection. Unknown fields, malformed nested policies, duplicate profile IDs and duplicate connection selectors fail closed.

Selection requires the exact connection fingerprint, source, revision and native protocol. The model and provider identity must also match. Registry order provides no authority, and resolution supplies no model aliases or default profile. A trusted callback supplies the connection fingerprint.

Entries use `chat-provider-profile-v1` and adapter version `native-v1`. Capability flags must be booleans, and streaming tools require tools support. Any image support or non-null image policy is rejected, even on an unselected entry. The resolver does not strip images or estimate them as text.

## Capacity and estimated counts

The effective output ceiling is the smaller of the profile's physical output limit and the application's configured output cap. A requested output reserve must be a positive integer within that ceiling. The hard input limit is:

```text
min(inputCeiling, contextWindowTokens - requested_output_tokens - safetyMargin)
```

The resolver floors the configured soft and target ratios against that hard limit. Resolution requires `0 < target < soft < hard`. A configuration cap alone does not establish physical context capacity.

The only supported counter is `character-estimate-v1` in `estimated` mode. Its parameters are positive finite characters per token and nonnegative integer protocol overhead. Counter ID, version and policy remain part of the resolved identity. The module supplies no model-specific calibration artifact or exact-token guarantee.

The runtime fingerprint binds the validated profile entry and connection identity, including the base-URL hash, timeout, application cap and effective output ceiling. The request-specific output reserve is not part of that fingerprint. Two resolved profiles can therefore share a fingerprint while having different input limits.

The builder's counter and connection snapshot expose the effective output ceiling. They do not enforce the resolved hard, soft or target input limits. A future per-call admission operation must count the actual serialized request, bind its current output reserve and enforce the matching limits before every send.

## Resolved state

`ResolvedChatProfile` is frozen and holds copied, recursively frozen profile dictionaries. Later registry mutation does not change its policy. The builder uses the pinned original connection and accepts no replacement connection.

The connection and profile entry are omitted from the resolved profile's representation. The shared connection snapshot omits its API key from its representation. Arbitrary snapshot contents still require normal secret-safe handling. A fingerprint or frozen Python value provides no authorization or source provenance.

## Builder routes and transport ownership

The builder supports these routes:

| Connection source | Provider | Native protocol |
| --- | --- | --- |
| Workspace or server | OpenAI | OpenAI Responses |
| Workspace or server | OpenAI | OpenAI Chat Completions |
| Server | DeepSeek | Anthropic Messages |

Other combinations fail before construction or send. The builder validates the raw base URL and final protocol endpoint. It applies the existing server normalization only on the declared routes and requires the final endpoint to retain the original origin. DNS, IP and connected-peer restrictions belong to the supplied secure transport.

Construction creates no HTTP client and sends no request. The caller owns the client context and stream closure. Cancellation requires both the declared capability and a callable callback. Cooperative cancellation does not interrupt blocked I/O.

Pure resolution avoids settings, endpoint helpers, ORM, HTTP clients and Worker imports. Builder imports the native endpoint and adapter helpers only when called. It reuses native API-key normalization and fixed configuration error codes.

## Native integration limits

Native composition still requires an approved registry with model-specific capacity and estimate provenance. It also requires current connection and source authority, every-send request admission, budget and lifecycle checks, and client cleanup. Shared-message composition must preserve the existing exclusion of private instructions for every owner. This module loads no private storage and does not validate the authority of future supplied messages.

There is no native Chat loop, tool dispatcher, compaction adoption, checkpoint or UI activation in this module. Synthetic transport tests establish construction, policy and cleanup behavior within their stated controls. They establish no live provider calibration or quality result.

See [chat_runtime_profile.py](../../apps/api/src/ai_pdf_api/services/chat_runtime_profile.py) and [profile tests](../../apps/api/tests/test_chat_runtime_profile.py).
