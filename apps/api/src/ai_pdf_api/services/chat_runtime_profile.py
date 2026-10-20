"""Pure, text-only binding of reviewed provider policy to one connection."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from types import MappingProxyType

from citeframe_contracts.memory import GenerationPort, HTTPTransport, ModelConnectionSnapshot, ProtocolError, TokenCounter
from citeframe_memory.adapters import Capabilities, CharacterEstimateCounter, CountingProfile

from .model_config_types import ModelConnection


_PROTOCOLS = {
    "openai_responses": "openai_responses",
    "openai_chat_completions": "openai_chat_completions",
    "anthropic_messages": "anthropic",
}
_ENTRY_KEYS = frozenset("""
schemaVersion profileId profileVersion connectionFingerprint connectionSource
connectionRevision nativeProtocol protocol model providerIdentity adapterVersion
contextWindowTokens maxOutputTokens inputCeiling safetyMargin supportsTools
supportsStreamingTools supportsCancellation supportsImages counter images watermarks
maxSummaryWallSeconds maxMergeCalls
""".split())
_COUNTER_KEYS = frozenset("id version mode implementationId parameters".split())
_WATERMARK_KEYS = frozenset("soft_ratio target_ratio min_new_tokens min_gain_tokens max_chunk_calls max_units".split())


def _fail(code: str = "chat_profile_invalid") -> None:
    raise ProtocolError(code)


def _shape(value: object, keys: set[str] | frozenset[str]) -> dict:
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail()
    return dict(value)


def _string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _fingerprint(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _integer(value: object, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def _positive(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _entry(value: object) -> dict:
    entry = _shape(value, _ENTRY_KEYS)
    for key in ("profileId", "profileVersion", "connectionFingerprint", "nativeProtocol",
                "protocol", "model", "providerIdentity", "adapterVersion"):
        if not _string(entry[key]):
            _fail()
    if not _fingerprint(entry["connectionFingerprint"]):
        _fail()
    if (entry["schemaVersion"] != "chat-provider-profile-v1"
            or entry["connectionSource"] not in ("server", "workspace")
            or not _integer(entry["connectionRevision"], 0)):
        _fail()
    if (entry["nativeProtocol"] not in _PROTOCOLS
            or entry["protocol"] != _PROTOCOLS[entry["nativeProtocol"]]
            or entry["adapterVersion"] != "native-v1"):
        _fail()
    for key in ("supportsTools", "supportsStreamingTools", "supportsCancellation", "supportsImages"):
        if type(entry[key]) is not bool:
            _fail()
    if entry["supportsStreamingTools"] and not entry["supportsTools"]:
        _fail()
    if entry["supportsImages"] or entry["images"] is not None:
        _fail("chat_images_unsupported")
    for key in ("contextWindowTokens", "maxOutputTokens", "inputCeiling"):
        if not _integer(entry[key], 1):
            _fail()
    if (not _integer(entry["safetyMargin"], 0)
            or entry["maxOutputTokens"] >= entry["contextWindowTokens"]):
        _fail()
    if (not _positive(entry["maxSummaryWallSeconds"])
            or not _integer(entry["maxMergeCalls"], 0) or entry["maxMergeCalls"] > 2):
        _fail()
    counter = _shape(entry["counter"], _COUNTER_KEYS)
    if not _string(counter["id"]) or not _string(counter["version"]):
        _fail()
    if counter["mode"] != "estimated" or counter["implementationId"] != "character-estimate-v1":
        _fail("chat_counter_unsupported")
    params = _shape(counter["parameters"], {"characters_per_token", "protocol_overhead_tokens"})
    if (not _positive(params["characters_per_token"])
            or not _integer(params["protocol_overhead_tokens"], 0)):
        _fail()
    counter["parameters"] = params
    entry["counter"] = counter
    watermarks = _shape(entry["watermarks"], _WATERMARK_KEYS)
    if (not _positive(watermarks["target_ratio"]) or not _positive(watermarks["soft_ratio"])
            or not 0 < watermarks["target_ratio"] < watermarks["soft_ratio"] < 1):
        _fail()
    for key in _WATERMARK_KEYS - {"soft_ratio", "target_ratio"}:
        if not _integer(watermarks[key], 1):
            _fail()
    entry["watermarks"] = watermarks
    return entry


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return value


@dataclass(frozen=True)
class ResolvedChatProfile:
    _connection: ModelConnection = field(repr=False)
    runtime_fingerprint: str
    profile_entry: Mapping[str, object] = field(repr=False)
    requested_output_tokens: int
    effective_max_output_tokens: int
    hard_input_tokens: int
    soft_input_tokens: int
    target_input_tokens: int
    counting_profile: CountingProfile = field(repr=False)
    capabilities: Capabilities

    def create_counter(self) -> CharacterEstimateCounter:
        parameters = self.profile_entry["counter"]["parameters"]
        return CharacterEstimateCounter(self.counting_profile, **parameters)


def resolve_chat_profile(
    connection: ModelConnection, *, registry: Mapping[str, object],
    connection_fingerprint_for: Callable[[ModelConnection], str],
    requested_output_tokens: int, require_cancellation: bool = False,
) -> ResolvedChatProfile:
    if not isinstance(connection, ModelConnection):
        _fail()
    if (connection.capability != "generation" or connection.source not in ("server", "workspace")
            or not _integer(connection.revision, 0)
            or not _positive(connection.timeout_seconds)
            or not _integer(connection.max_output_tokens, 1)
            or type(require_cancellation) is not bool):
        _fail()
    if not all(_string(value) for value in (
        connection.model, connection.provider, connection.base_url, connection.api_key, connection.protocol,
    )):
        _fail()
    if connection.protocol not in _PROTOCOLS:
        _fail("chat_profile_unknown")
    try:
        fingerprint = connection_fingerprint_for(connection)
    except Exception:
        raise ProtocolError("chat_profile_invalid") from None
    if not _fingerprint(fingerprint):
        _fail()
    root = _shape(registry, {"schemaVersion", "profiles"})
    if root["schemaVersion"] != "chat-provider-registry-v1" or type(root["profiles"]) is not list:
        _fail()
    entries = [_entry(value) for value in root["profiles"]]
    ids, selectors = set(), set()
    selected = None
    selector = (fingerprint, connection.source, connection.revision, connection.protocol)
    for entry in entries:
        identity = tuple(entry[key] for key in (
            "connectionFingerprint", "connectionSource", "connectionRevision", "nativeProtocol",
        ))
        if entry["profileId"] in ids or identity in selectors:
            _fail("chat_profile_ambiguous")
        ids.add(entry["profileId"])
        selectors.add(identity)
        if (identity == selector and entry["model"] == connection.model
                and entry["providerIdentity"] == connection.provider):
            selected = entry
    if selected is None:
        _fail("chat_profile_unknown")
    entry = selected
    effective = min(entry["maxOutputTokens"], connection.max_output_tokens)
    if not _integer(requested_output_tokens, 1) or requested_output_tokens > effective:
        _fail("chat_output_limit")
    hard = min(entry["inputCeiling"], entry["contextWindowTokens"] - requested_output_tokens - entry["safetyMargin"])
    try:
        soft = math.floor(entry["watermarks"]["soft_ratio"] * hard)
        target = math.floor(entry["watermarks"]["target_ratio"] * hard)
    except (OverflowError, ValueError):
        raise ProtocolError("chat_capacity_invalid") from None
    if not 0 < target < soft < hard:
        _fail("chat_capacity_invalid")
    if require_cancellation and not entry["supportsCancellation"]:
        _fail("chat_cancellation_unsupported")
    try:
        binding = {
            "schemaVersion": "chat-runtime-binding-v1", "connectionFingerprint": fingerprint,
            "connectionSource": connection.source, "connectionRevision": connection.revision,
            "nativeProtocol": connection.protocol, "neutralProtocol": entry["protocol"],
            "providerIdentity": connection.provider, "model": connection.model,
            "baseUrlSha256": sha256(connection.base_url.encode("utf-8")).hexdigest(),
            "timeoutSeconds": connection.timeout_seconds,
            "applicationMaxOutputTokens": connection.max_output_tokens,
            "effectiveMaxOutputTokens": effective, "profileEntry": entry,
        }
        runtime = sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    except (UnicodeError, ValueError, TypeError, OverflowError):
        raise ProtocolError("chat_profile_invalid") from None
    counting = CountingProfile(entry["protocol"], connection.model, runtime, entry["contextWindowTokens"],
                               entry["counter"]["id"], entry["counter"]["version"], "estimated")
    capabilities = Capabilities(entry["protocol"], entry["adapterVersion"], entry["supportsTools"],
                                entry["supportsStreamingTools"], entry["supportsCancellation"])
    return ResolvedChatProfile(connection, runtime, _freeze(entry), requested_output_tokens,
                               effective, hard, soft, target, counting, capabilities)


def build_chat_generation(
    profile: ResolvedChatProfile, *, transport: HTTPTransport,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[GenerationPort, TokenCounter]:
    if not isinstance(profile, ResolvedChatProfile):
        _fail()
    if cancelled is not None:
        if not callable(cancelled):
            _fail()
        if not profile.capabilities.supports_cancellation:
            _fail("chat_cancellation_unsupported")
    connection = profile._connection
    route = (connection.source, connection.provider, connection.protocol)
    if route not in {
        ("workspace", "openai", "openai_responses"),
        ("workspace", "openai", "openai_chat_completions"),
        ("server", "openai", "openai_responses"),
        ("server", "openai", "openai_chat_completions"),
        ("server", "deepseek", "anthropic_messages"),
    }:
        _fail("chat_endpoint_unsupported")

    from ai_pdf_api.services.model_config_types import ModelConfigurationError
    from ai_pdf_api.services.model_endpoint import endpoint_origin, validate_base_url
    from ai_pdf_api.services.providers import _normalize_api_key, _normalize_deepseek_base, _normalize_openai_base
    from citeframe_memory.adapters import AnthropicAdapter, ChatCompletionsAdapter, ResponsesAdapter

    adapter, suffix = {
        "openai_responses": (ResponsesAdapter, "/responses"),
        "openai_chat_completions": (ChatCompletionsAdapter, "/chat/completions"),
        "anthropic_messages": (AnthropicAdapter, "/messages"),
    }[connection.protocol]
    try:
        raw_base = validate_base_url(connection.base_url)
        base = raw_base
        if connection.source == "server":
            base = (_normalize_deepseek_base if connection.provider == "deepseek" else _normalize_openai_base)(base)
        endpoint = validate_base_url(base + suffix)
        if endpoint_origin(endpoint) != endpoint_origin(raw_base):
            _fail("model_endpoint_denied")
    except ModelConfigurationError as error:
        code = error.code if error.code in {"model_endpoint_invalid", "model_endpoint_denied"} else "chat_profile_invalid"
        raise ProtocolError(code) from None
    api_key = _normalize_api_key(connection.api_key)
    if api_key is None:
        _fail("generation_not_configured")
    snapshot = ModelConnectionSnapshot(
        profile.capabilities.protocol, endpoint, connection.model, api_key,
        connection.timeout_seconds, profile.runtime_fingerprint,
        profile.counting_profile.context_window_tokens, profile.effective_max_output_tokens,
    )
    return adapter(snapshot, transport, profile.capabilities, cancelled=cancelled), profile.create_counter()
