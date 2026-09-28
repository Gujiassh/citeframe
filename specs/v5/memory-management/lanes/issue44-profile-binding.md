# Issue44 R2/R4 — exact profile-only implementation contract

Status: R3-A pure resolve/schema code independently ACCEPTED at review SHA-256 `7ec60a4e923c158133868c85948bf1291f2ff63fcdeb445bd2596ac03292cb50`; product/test bytes frozen. R2/R4 text-profile design is accepted; R3-B endpoint addendum below awaits review and build remains unimplemented. Governing review: reviews/issue44-chat-loop.md SHA-256 `e06bd82578182a2944dee2f0658558f620e60984318264274eb00fbe7a4e9468`. Only new product files `apps/api/src/ai_pdf_api/services/chat_runtime_profile.py` and `apps/api/tests/test_chat_runtime_profile.py` are assigned. No production profile/capacity/exact counter or loader is authorized.

## 1. Pure R3-A callable and trust boundary

```python
resolve_chat_profile(
    connection: ModelConnection, *, registry: Mapping[str, object],
    connection_fingerprint_for: Callable[[ModelConnection], str],
    requested_output_tokens: int,
    require_cancellation: bool = False,
) -> ResolvedChatProfile
```

The callback is a trusted composition dependency, invoked by resolve on the **same supplied immutable ModelConnection**. Production composition binds `lambda c: connection_profile(c).config_fingerprint`; tests bind a labeled synthetic deterministic function. Do not accept an independently supplied fingerprint string or another connection in build. This injection keeps settings/secret loading out of the pure module; it does not let an untrusted request supply the callback. No IO, dynamic imports, downloads, network, DB or credential loader in this module.

Existing global connection_profile semantics stay unchanged for Research. It does not include source/revision. Registry entries additionally require exact `connectionSource`, `connectionRevision`, `nativeProtocol` and the existing `connectionFingerprint`. connectionFingerprint in both registry and callback result must be canonical 64-character lowercase hexadecimal SHA-256; malformed values reject. Match all four plus providerIdentity/model/neutral protocol/adapterVersion against the actual connection. Revision1→2 with identical existing fingerprint rejects the old entry. No model aliases/default lookup.

Raw protocol mapping is closed: openai_responses→openai_responses/ResponsesAdapter/native-v1; openai_chat_completions→openai_chat_completions/ChatCompletionsAdapter/native-v1; anthropic_messages→anthropic/AnthropicAdapter/native-v1. Other raw protocols reject. Distinct neutral protocol is included even when adapterVersion strings coincide. Endpoint derivation belongs later trusted composition; pure result pins exact base_url but does not normalize URLs, resolve DNS or construct/send a client.

Runtime binding fingerprint = SHA-256 of strict canonical JSON `{schemaVersion:'chat-runtime-binding-v1',connectionFingerprint,connectionSource,connectionRevision,nativeProtocol,neutralProtocol,providerIdentity,model,baseUrlSha256,timeoutSeconds,applicationMaxOutputTokens,effectiveMaxOutputTokens,profileEntry}`. profileEntry is the complete validated immutable entry. Credentials are never included in plaintext; their identity is carried by the existing trusted fingerprint. Base URL is hashed here, not persisted. Keep the exact connection in a private repr=False field solely for short-lived later construction; repr/public metadata expose neither endpoint nor credentials. Copy mutable registry inputs into immutable module-local values; later caller mutation cannot alter resolved meaning.

A changed endpoint/model/protocol/provider/secret/timeout/source/revision/output cap must either fail entry selection or produce a different bound fingerprint requiring explicit new owner binding. Old resolved object retains only its original connection; build cannot receive a substitute. No old runtime dispatch authority follows from re-resolving new configuration.

## 2. Strict registry and effective limits

Root exact shape: `{schemaVersion:'chat-provider-registry-v1',profiles:[entry,...]}`. Entry is §16's exact chat-provider-profile-v1 fields plus connectionSource/connectionRevision/nativeProtocol above:

`schemaVersion,profileId,profileVersion,connectionFingerprint,connectionSource,connectionRevision,nativeProtocol,protocol,model,providerIdentity,adapterVersion,contextWindowTokens,maxOutputTokens,inputCeiling,safetyMargin,supportsTools,supportsStreamingTools,supportsCancellation,supportsImages,counter,images,watermarks,maxSummaryWallSeconds,maxMergeCalls`.

Unknown/missing fields reject throughout, including nonselected entries. profileId/profileVersion are nonempty strings. Profiles have unique profileId and unique connection selector tuple; duplicate/ambiguous registry rejects rather than choosing first. Empty or unknown profile rejects. Text-only implementation requires supportsImages=False and images=null. Capability flags strictly bool; supportsStreamingTools implies supportsTools. ModelConnection capability=generation/source in server|workspace/revision strict integer>=0, nonempty model/provider/base_url/key/protocol, positive finite timeout, positive strict-int max_output_tokens. Validate all numeric values with bool excluded; reject NaN/Infinity.

Only counter implementationId=`character-estimate-v1`, mode=`estimated`, parameters exact `{characters_per_token:positive_finite_number,protocol_overhead_tokens:nonnegative_int}` is enabled. id/version nonempty strings. No constant counter, JSON tokenizer or exact-mode implementation. Unknown implementation/mode rejects; no registry dynamic import. All entries are synthetic in tests; no deploy-loadable profile file is created.

Watermarks exact `soft_ratio,target_ratio,min_new_tokens,min_gain_tokens,max_chunk_calls,max_units`; `0<target<soft<1`, remaining positive strict ints. maxSummaryWallSeconds positive finite; maxMergeCalls strict int0..2. Capacity, inputCeiling and output caps positive strict ints; safetyMargin strict int>=0. Physical output ceiling must be < physical context.

Effective output ceiling = min(entry.maxOutputTokens,connection.max_output_tokens). Requested reserve must be positive strict int <= effective output ceiling; reject rather than silently clamp a requested output. Hard input=min(entry.inputCeiling,entry.contextWindowTokens−requested_output_tokens−entry.safetyMargin); require 0<floor(target*hard)<floor(soft*hard)<hard. No registry value raises the application output cap; no physical-capacity inference from application max output.

ResolvedChatProfile is frozen/API-local, not a shared port. It carries private original connection, runtime fingerprint, immutable validated policy values, requested_output_tokens/effective max/hard/soft/target input, existing CountingProfile and Capabilities. All carry the same runtime binding identity where their DTO supports it. No ModelConnectionSnapshot endpoint is invented during pure resolution; R3-B creates it from the exact pinned connection/validated endpoint. Counter construction in R3-A may expose an existing CharacterEstimateCounter from validated immutable CountingProfile/parameters for deterministic tests; it makes no generation call or exact-count claim.

Stable safe ProtocolError codes: chat_profile_invalid (shape/type/relationships), chat_profile_unknown (no exact match), chat_profile_ambiguous (duplicate identities/selectors), chat_counter_unsupported (mode/implementation), chat_images_unsupported, chat_output_limit, chat_capacity_invalid, chat_cancellation_unsupported. Error messages contain no raw entry/endpoint/key. Malformed fingerprint callback result rejects; callback exceptions become safe profile error.

## 3. R3-B builder — proposal only, wait for small-contract approval

```python
build_chat_generation(
    profile: ResolvedChatProfile, *, transport: HTTPTransport,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[GenerationPort, TokenCounter]
```

No second ModelConnection or separately supplied fingerprint. Builder only uses pinned connection and resolved immutable values. A nonnull cancelled callback requires supportsCancellation=True at construction; reject before any send. Snapshot uses effective max output ceiling and the same runtime fingerprint as CountingProfile; requested output reserve is checked again at request admission, not silently changed.

**Composition owns client lifecycle:**

```python
with model_client(pinned_connection.base_url, pinned_connection.timeout_seconds) as client:
    generation, counter = build_chat_generation(profile, transport=client, cancelled=cancelled)
    # All generation iteration/iterator closure completes inside this scope.
```

Build never creates, closes or stores a separate client pool. Production injection must be existing secure model_client (origin/DNS policy, trust_env=False, follow_redirects=False, no retries, bounded response/time); tests inject a context-owned httpx.Client with MockTransport. Context owner closes on normal completion, construction failure, cancellation, unknown outcome and runner shutdown, after active iterator closure. No reliance on adapter private attributes. Returning an iterator outside the with is forbidden. No new service/context wrapper or shared transport-close ABI.

Before R3-B code, owner review must accept exact endpoint construction using existing native protocol-specific builders and validation while preserving raw base binding. Build/config tests must prove zero sends at construction, drift cannot substitute connection, all3 actual adapter classes and client closure under every exit. R3-A does not implement build or a placeholder raising NotImplementedError.

## 4. Evidence and limits

Required R3-A actual-code tests: strict unknown/duplicate/missing entries, bool-vs-int/finite/relationship checks, all3 explicit raw mappings, source/revision changes with unchanged existing fingerprint, secret/endpoint/model/protocol/timeout drift, app-vs-physical stricter cap and request reserve, exact/images/counter rejection, cancellation flag, immutable input copies, safe repr/errors and no IO/settings import. Counter tests stay estimated and use actual CharacterEstimateCounter/native serializer only where an explicit synthetic snapshot is supplied; no physical/tokenizer accuracy inference.

No shared/native/router/assets/settings/DTO/CI file change, no #43 wait for this pure slice, no production activation. R1/R3/R5 remain separate original-owner runtime amendments. No commits/push/paid calls.

## 5. R3-B endpoint addendum — proposed, no builder activation

The following closed routing table preserves existing native endpoint rules. `source`, `provider`, and raw `protocol` come solely from the profile's pinned ModelConnection. Matching a pure R3-A profile does not authorize an unsupported endpoint combination.

| Source | Provider | Raw protocol | Validated base rule | Final suffix / neutral adapter |
|---|---|---|---|---|
| workspace | openai | openai_responses | exact base, as `_BoundProvider.adapter(exact_base=True)` | `/responses` / ResponsesAdapter |
| workspace | openai | openai_chat_completions | exact base | `/chat/completions` / ChatCompletionsAdapter |
| server | openai | openai_responses | existing `_normalize_openai_base` | `/responses` / ResponsesAdapter |
| server | openai | openai_chat_completions | existing `_normalize_openai_base`; explicit ChatCompletions route | `/chat/completions` / ChatCompletionsAdapter |
| server | deepseek | anthropic_messages | existing `_normalize_deepseek_base` | `/messages` / AnthropicAdapter |
| any other combination | any | any | reject before construction/send with safe `ProtocolError(code="chat_endpoint_unsupported")` | no inferred route |

The server ChatCompletions row proposes explicit neutral routing using the existing ChatCompletions endpoint rule; it does not claim the legacy server factory already dispatches that protocol separately. No arbitrary Anthropic-compatible provider or workspace receives the DeepSeek rewrite. Expanding supported combinations requires its own explicit contract.

All examples use the synthetic origin `https://fixture.invalid`. Entries below show final paths for Responses; for the two OpenAI columns only, substitute `/chat/completions` for the final `/responses` when the raw protocol is openai_chat_completions.

| Raw base path | Workspace OpenAI exact | Server OpenAI normalized | Server DeepSeek anthropic_messages |
|---|---|---|---|
| empty or `/` | `/responses` | `/v1/responses` | `/anthropic/v1/messages` |
| `/custom` or `/custom/` | `/custom/responses` | `/custom/v1/responses` | `/custom/anthropic/v1/messages` |
| `/v1` or `/v1/` | `/v1/responses` | `/v1/responses` | `/anthropic/v1/messages` |
| `/anthropic` or `/anthropic/` | `/anthropic/responses` | `/anthropic/v1/responses` | `/anthropic/v1/messages` |
| `/anthropic/v1` or `/anthropic/v1/` | `/anthropic/v1/responses` | `/anthropic/v1/responses` | `/anthropic/v1/messages` |

Validation/construction sequence, proposed for R3-B only:

1. Trusted composition takes `pinned_connection = profile._connection`, the existing private immutable field, in its bounded construction scope. This is intentional API-local composition access; no new accessor, shared export, second connection argument, settings reload, or adapter-private-field access is needed. Do not log/serialize that value or retain it beyond execution lifetime.
2. Composition lazily imports existing `model_endpoint.validate_base_url`, `endpoint_origin`, and `model_transport.model_client` after pure resolution. Validate the pinned **raw** base before entering `with model_client(pinned_connection.base_url, pinned_connection.timeout_seconds) as client`. The existing client also validates its base on construction. R3-A remains free of these settings-dependent imports.
3. Inside that context, build independently validates the same pinned raw base, applies only the selected table rule to the validated base (existing native normalizers imported at build time), appends the fixed suffix, validates the final endpoint with `validate_base_url`, and requires `endpoint_origin(final) == endpoint_origin(validated_raw)`. Reject invalid/denied URLs using the existing safe model_endpoint_invalid/model_endpoint_denied codes and reject an origin mismatch as model_endpoint_denied, without exposing raw URLs/keys. There is no caller-supplied endpoint override. Raw base hash in the accepted runtime binding stays unchanged by normalization.
4. Only after these checks construct ModelConnectionSnapshot with the validated final endpoint, pinned model/credentials, effective output ceiling and resolved runtime fingerprint; instantiate the selected neutral adapter with the injected client and existing estimated counter. Neither construction nor URL validation performs DNS/HTTP. All iteration and iterator closure remain inside the composition-owned client context, including error/cancel/unknown exits.
5. Actual request origin enforcement remains in ModelTransport; actual DNS/IP admission remains at PolicyNetworkBackend's resolve/dial boundary. Pure resolution and syntax/origin validation do not certify DNS destinations. Existing trust_env=False/follow_redirects=False and no retry semantics stay unchanged.

This table is grounded in workspace_providers._BoundProvider.adapter, providers._normalize_openai_base/_normalize_deepseek_base, capabilities.normalize_provider_endpoint, chat_completions.ChatCompletionsProvider, model_endpoint and model_transport. R3-B tests must cover every row, all three actual adapters, unsupported combinations, invalid raw/final URLs and origin mismatch, zero construction sends, raw-binding preservation and context/iterator cleanup before implementation acceptance. R1/R3/R5 still require exact original-owner review; no shared/source/schema/native/image changes are granted by this addendum.
