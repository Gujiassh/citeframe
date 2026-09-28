"""Synthetic text profiles only; no production capacities or model calls."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ai_pdf_api.services.chat_runtime_profile import resolve_chat_profile
from ai_pdf_api.services.model_config_types import ModelConnection
from citeframe_contracts.memory import GenerationMessage, GenerationRequest, ModelConnectionSnapshot, ProtocolError


PROTOCOLS = {"openai_responses": "openai_responses", "openai_chat_completions": "openai_chat_completions", "anthropic_messages": "anthropic"}


def synthetic_fingerprint(connection):
    # Revision/source are deliberately absent, matching the existing binding limitation.
    return sha256(json.dumps([connection.model, connection.provider, connection.protocol, connection.api_key]).encode()).hexdigest()


def fixture(protocol="openai_responses"):
    connection = ModelConnection("generation", "server", 1, protocol, "synthetic-provider", "synthetic-model", "https://synthetic.invalid/base", "synthetic-secret", 2.0, 200)
    entry = {
        "schemaVersion": "chat-provider-profile-v1", "profileId": "synthetic-profile", "profileVersion": "v1",
        "connectionFingerprint": synthetic_fingerprint(connection), "connectionSource": "server", "connectionRevision": 1,
        "nativeProtocol": protocol, "protocol": PROTOCOLS[protocol], "model": connection.model,
        "providerIdentity": connection.provider, "adapterVersion": "native-v1", "contextWindowTokens": 1000,
        "maxOutputTokens": 300, "inputCeiling": 800, "safetyMargin": 50, "supportsTools": True,
        "supportsStreamingTools": True, "supportsCancellation": False, "supportsImages": False,
        "counter": {"id": "synthetic-estimate", "version": "v1", "mode": "estimated", "implementationId": "character-estimate-v1",
                    "parameters": {"characters_per_token": 4.0, "protocol_overhead_tokens": 8}},
        "images": None, "watermarks": {"soft_ratio": 0.8, "target_ratio": 0.5, "min_new_tokens": 1,
                    "min_gain_tokens": 1, "max_chunk_calls": 2, "max_units": 4},
        "maxSummaryWallSeconds": 3.0, "maxMergeCalls": 2,
    }
    return connection, {"schemaVersion": "chat-provider-registry-v1", "profiles": [entry]}


def resolve(connection, registry, **kwargs):
    return resolve_chat_profile(connection, registry=registry, connection_fingerprint_for=kwargs.pop("connection_fingerprint_for", synthetic_fingerprint), requested_output_tokens=kwargs.pop("requested_output_tokens", 100), **kwargs)


def change(entry, path, value):
    for part in path.split(".")[:-1]:
        entry = entry[part]
    entry[path.split(".")[-1]] = value


@pytest.mark.parametrize("protocol,neutral", PROTOCOLS.items())
def test_exact_mapping_and_actual_estimated_counter(protocol, neutral):
    connection, registry = fixture(protocol)
    seen = []
    def trusted(actual):
        seen.append(actual)
        return synthetic_fingerprint(actual)
    profile = resolve(connection, registry, connection_fingerprint_for=trusted)
    assert seen == [connection] and seen[0] is connection
    assert profile._connection is connection
    assert profile.capabilities.protocol == neutral
    assert profile.capabilities.adapter_version == "native-v1"
    assert profile.counting_profile.protocol == neutral
    assert profile.counting_profile.config_fingerprint == profile.runtime_fingerprint
    snapshot = ModelConnectionSnapshot(neutral, "https://synthetic.invalid/explicit-test-endpoint", connection.model,
        connection.api_key, connection.timeout_seconds, profile.runtime_fingerprint, 1000, 200)
    counter = profile.create_counter()
    result = counter.count(GenerationRequest((GenerationMessage("user", "合成 text"),), 100), snapshot)
    larger = counter.count(GenerationRequest((GenerationMessage("user", "合成 text" * 100),), 100), snapshot)
    assert result.mode == "estimated" and result.config_fingerprint == profile.runtime_fingerprint
    assert larger.tokens > result.tokens > 8
    assert profile.create_counter() is not counter
    with pytest.raises(ProtocolError):
        counter.count(GenerationRequest((GenerationMessage("user", "text"),), 100), replace(snapshot, config_fingerprint="drift"))


@pytest.mark.parametrize("physical,application,reserve,effective,hard", [(300,200,100,200,800),(150,200,150,150,800),(300,400,300,300,650)])
def test_physical_application_caps_and_input_reserve(physical, application, reserve, effective, hard):
    connection, registry = fixture()
    connection = replace(connection, max_output_tokens=application)
    registry["profiles"][0]["maxOutputTokens"] = physical
    profile = resolve(connection, registry, requested_output_tokens=reserve)
    assert profile.effective_max_output_tokens == effective
    assert profile.requested_output_tokens == reserve
    assert (profile.hard_input_tokens, profile.soft_input_tokens, profile.target_input_tokens) == (hard, int(.8*hard), int(.5*hard))


@pytest.mark.parametrize("reserve", [0,-1,True,1.5,None,201,301,float("nan"),float("inf")])
def test_invalid_requested_reserve(reserve):
    connection, registry = fixture()
    with pytest.raises(ProtocolError, match="^chat_output_limit$"):
        resolve(connection, registry, requested_output_tokens=reserve)


_INVALID = [
    ("schemaVersion", "unknown"), ("profileId", ""), ("profileVersion", 1), ("connectionFingerprint", None),
    ("connectionSource", "other"), ("connectionRevision", True), ("connectionRevision", -1),
    ("nativeProtocol", "anthropic"), ("protocol", "anthropic"), ("adapterVersion", "v2"),
    ("model", ""), ("providerIdentity", ""), ("supportsTools", 1), ("supportsStreamingTools", "true"),
    ("supportsCancellation", None), ("supportsImages", 0), ("supportsTools", False),
    ("contextWindowTokens", 0), ("contextWindowTokens", True), ("maxOutputTokens", 1000),
    ("maxOutputTokens", 1.5), ("inputCeiling", -1), ("safetyMargin", -1), ("safetyMargin", True),
    ("maxSummaryWallSeconds", float("nan")), ("maxSummaryWallSeconds", float("inf")), ("maxSummaryWallSeconds", True),
    ("maxMergeCalls", 3), ("maxMergeCalls", -1), ("maxMergeCalls", True),
    ("counter.id", ""), ("counter.version", None), ("counter.parameters.characters_per_token", 0),
    ("counter.parameters.characters_per_token", True), ("counter.parameters.characters_per_token", float("nan")),
    ("counter.parameters.characters_per_token", float("inf")), ("counter.parameters.protocol_overhead_tokens", -1),
    ("counter.parameters.protocol_overhead_tokens", True), ("counter.parameters.protocol_overhead_tokens", 1.5),
    ("watermarks.soft_ratio", 1), ("watermarks.target_ratio", .8), ("watermarks.target_ratio", 0),
    ("watermarks.soft_ratio", float("nan")), ("watermarks.target_ratio", float("inf")), ("watermarks.soft_ratio", True),
    ("watermarks.min_new_tokens", 0), ("watermarks.min_gain_tokens", True), ("watermarks.max_chunk_calls", -1), ("watermarks.max_units", 1.5),
]


@pytest.mark.parametrize("path,value", _INVALID)
@pytest.mark.parametrize("nonselected", [False, True])
def test_strict_all_entry_values(path, value, nonselected):
    connection, registry = fixture()
    entry = registry["profiles"][0]
    if nonselected:
        entry = deepcopy(entry)
        entry.update(profileId="other", connectionFingerprint="0" * 64)
        registry["profiles"].append(entry)
    change(entry, path, value)
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(connection, registry)


@pytest.mark.parametrize("path", ["", "entry", "counter", "parameters", "watermarks"])
@pytest.mark.parametrize("operation", ["missing", "unknown"])
def test_exact_shapes(path, operation):
    connection, registry = fixture()
    target = registry if not path else registry["profiles"][0]
    if path in ("counter", "parameters"):
        target = target["counter"]
    if path == "parameters":
        target = target["parameters"]
    if path == "watermarks":
        target = target["watermarks"]
    if operation == "missing":
        del target[next(iter(target))]
    else:
        target["unknown"] = "synthetic-secret"
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(connection, registry)


@pytest.mark.parametrize("field,value,code", [
    ("counter.mode", "exact", "chat_counter_unsupported"),
    ("counter.implementationId", "dynamic.module:callback", "chat_counter_unsupported"),
    ("supportsImages", True, "chat_images_unsupported"), ("images", {}, "chat_images_unsupported"),
    ("inputCeiling", 1, "chat_capacity_invalid"), ("safetyMargin", 900, "chat_capacity_invalid"),
])
def test_disabled_capabilities_and_unusable_capacity(field, value, code):
    connection, registry = fixture()
    change(registry["profiles"][0], field, value)
    with pytest.raises(ProtocolError, match=f"^{code}$"):
        resolve(connection, registry)


@pytest.mark.parametrize("duplicate", ["id", "selector"])
def test_duplicate_identity_or_selector(duplicate):
    connection, registry = fixture()
    second = deepcopy(registry["profiles"][0])
    second["connectionFingerprint" if duplicate == "id" else "profileId"] = "0" * 64 if duplicate == "id" else "other"
    registry["profiles"].append(second)
    with pytest.raises(ProtocolError, match="^chat_profile_ambiguous$"):
        resolve(connection, registry)


@pytest.mark.parametrize("field,value", [("source","workspace"),("revision",2),("model","changed"),("provider","changed"),("protocol","anthropic_messages"),("api_key","changed-secret")])
def test_identity_drift_rejects_old_entry(field, value):
    connection, registry = fixture()
    new = replace(connection, **{field:value})
    if field in ("source", "revision"):
        assert synthetic_fingerprint(new) == synthetic_fingerprint(connection)
    with pytest.raises(ProtocolError, match="^chat_profile_unknown$"):
        resolve(new, registry)


@pytest.mark.parametrize("field,value", [("base_url","https://changed.invalid/raw/"),("timeout_seconds",3.0),("max_output_tokens",190)])
def test_other_connection_drift_changes_runtime_binding(field, value):
    connection, registry = fixture()
    old = resolve(connection, registry)
    new = resolve(replace(connection, **{field:value}), registry)
    assert old.runtime_fingerprint != new.runtime_fingerprint
    assert old._connection is connection


@pytest.mark.parametrize("field,value", [("capability","embedding"),("source","invalid"),("revision",True),("revision",-1),("model",""),("provider",None),("base_url",""),("api_key",None),("protocol",""),("timeout_seconds",0),("timeout_seconds",True),("timeout_seconds",float("nan")),("timeout_seconds",float("inf")),("max_output_tokens",True),("max_output_tokens",0)])
def test_invalid_actual_connection(field, value):
    connection, registry = fixture()
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(replace(connection, **{field:value}), registry)


def test_unknown_and_empty_and_malformed_root():
    connection, registry = fixture()
    for value in ({"schemaVersion":"chat-provider-registry-v1","profiles":[]},):
        with pytest.raises(ProtocolError, match="^chat_profile_unknown$"):
            resolve(connection, value)
    with pytest.raises(ProtocolError, match="^chat_profile_unknown$"):
        resolve(replace(connection, protocol="openai"), registry)
    for value in (None, [], {"schemaVersion":"bad","profiles":[]}, {"schemaVersion":"chat-provider-registry-v1","profiles":()}):
        with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
            resolve(connection, value)
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(object(), registry)


def test_cancellation_requires_explicit_boolean_capability():
    connection, registry = fixture()
    with pytest.raises(ProtocolError, match="^chat_cancellation_unsupported$"):
        resolve(connection, registry, require_cancellation=True)
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(connection, registry, require_cancellation=1)
    registry["profiles"][0]["supportsCancellation"] = True
    assert resolve(connection, registry, require_cancellation=True).capabilities.supports_cancellation


@pytest.mark.parametrize("returned", [None,1,True,""," ","fp","F" * 64,"a" * 63,"g" * 64])
def test_malformed_callback_result(returned):
    connection, registry = fixture()
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(connection, registry, connection_fingerprint_for=lambda _: returned)


def test_safe_callback_error_and_repr():
    connection, registry = fixture()
    def broken(_):
        raise ValueError(connection.api_key + connection.base_url)
    with pytest.raises(ProtocolError) as caught:
        resolve(connection, registry, connection_fingerprint_for=broken)
    assert str(caught.value) == "chat_profile_invalid" and caught.value.__suppress_context__
    profile = resolve(connection, registry)
    assert connection.api_key not in repr(profile) and connection.base_url not in repr(profile)
    assert connection.api_key not in repr(profile.profile_entry) and connection.base_url not in repr(profile.profile_entry)


def test_result_deep_copy_immutable_policy_and_canonical_fingerprint():
    connection, registry = fixture()
    profile = resolve(connection, registry)
    entry = registry["profiles"][0]
    binding = {"schemaVersion":"chat-runtime-binding-v1","connectionFingerprint":synthetic_fingerprint(connection),
        "connectionSource":connection.source,"connectionRevision":connection.revision,"nativeProtocol":connection.protocol,
        "neutralProtocol":"openai_responses","providerIdentity":connection.provider,"model":connection.model,
        "baseUrlSha256":sha256(connection.base_url.encode()).hexdigest(),"timeoutSeconds":connection.timeout_seconds,
        "applicationMaxOutputTokens":200,"effectiveMaxOutputTokens":200,"profileEntry":entry}
    expected = sha256(json.dumps(binding, sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    assert profile.runtime_fingerprint == expected
    assert resolve(connection, deepcopy(registry)).runtime_fingerprint == expected
    with pytest.raises(FrozenInstanceError):
        profile.hard_input_tokens = 0
    for target, key in ((profile.profile_entry,"profileId"),(profile.profile_entry["counter"],"id"),
                        (profile.profile_entry["counter"]["parameters"],"characters_per_token"),
                        (profile.profile_entry["watermarks"],"soft_ratio")):
        with pytest.raises(TypeError):
            target[key] = 0
    entry["counter"]["parameters"]["characters_per_token"] = 10
    entry["watermarks"]["soft_ratio"] = .9
    entry["profileVersion"] = "v2"
    assert profile.profile_entry["counter"]["parameters"]["characters_per_token"] == 4
    assert profile.runtime_fingerprint == expected
    assert resolve(connection, registry).runtime_fingerprint != expected


def test_isolated_import_and_resolution_without_app_loaders_or_network():
    script = '''
import importlib.abc, sys, socket, runpy
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("sqlalchemy", "httpx")) or (fullname.startswith("ai_pdf_api.") and fullname not in {
            "ai_pdf_api.services", "ai_pdf_api.services.chat_runtime_profile", "ai_pdf_api.services.model_config_types"}):
            raise AssertionError("forbidden dependency: " + fullname)
sys.meta_path.insert(0, Block())
def deny(*args, **kwargs):
    raise AssertionError("network forbidden")
socket.socket = deny
ns = runpy.run_path(sys.argv[1])
connection, registry = ns["fixture"]()
ns["resolve"](connection, registry).create_counter()
module = sys.modules["ai_pdf_api.services.chat_runtime_profile"]
assert callable(module.build_chat_generation)
assert not any(name in sys.modules for name in ("ai_pdf_api.core.settings", "ai_pdf_api.services.model_endpoint", "ai_pdf_api.services.providers", "ai_pdf_api.services.model_transport"))
'''
    result = subprocess.run([sys.executable,"-B","-c",script,str(Path(__file__).resolve())], capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("fingerprint", ["fp", "F" * 64, "a" * 63, "g" * 64])
def test_registry_fingerprint_is_canonical_sha256(fingerprint):
    connection, registry = fixture()
    registry["profiles"][0]["connectionFingerprint"] = fingerprint
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$"):
        resolve(connection, registry)


@pytest.mark.parametrize("location", ["endpoint", "entry", "oversized_integer"])
def test_canonical_encoding_errors_are_safe(location):
    connection, registry = fixture()
    if location == "endpoint":
        connection = replace(connection, base_url="https://synthetic.invalid/" + chr(0xD800))
    elif location == "entry":
        registry["profiles"][0]["profileId"] = chr(0xD800)
    else:
        registry["profiles"][0]["watermarks"]["max_units"] = 10 ** 5000
    with pytest.raises(ProtocolError, match="^chat_profile_invalid$") as caught:
        resolve(connection, registry)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("field,value", [("source", "workspace"), ("revision", 2), ("model", "changed"), ("provider", "changed"), ("protocol", "anthropic_messages")])
def test_actual_selector_fields_cannot_be_replaced_by_fingerprint_alone(field, value):
    connection, registry = fixture()
    unchanged_fingerprint = synthetic_fingerprint(connection)
    with pytest.raises(ProtocolError, match="^chat_profile_unknown$"):
        resolve(replace(connection, **{field: value}), registry,
                connection_fingerprint_for=lambda _: unchanged_fingerprint)


@pytest.mark.parametrize("field,entry_field,value", [("source", "connectionSource", "workspace"), ("revision", "connectionRevision", 2)])
def test_explicit_new_source_revision_entry_has_new_runtime_binding(field, entry_field, value):
    connection, registry = fixture()
    old = resolve(connection, registry)
    registry["profiles"][0][entry_field] = value
    new = resolve(replace(connection, **{field: value}), registry)
    assert old.runtime_fingerprint != new.runtime_fingerprint

@pytest.fixture
def builder_dependencies(monkeypatch):
    from pydantic_settings import BaseSettings, EnvSettingsSource, DotEnvSettingsSource
    monkeypatch.setattr(EnvSettingsSource, "_load_env_vars", lambda self: {})
    monkeypatch.setattr(DotEnvSettingsSource, "_load_env_vars", lambda self: {})
    # Actual Settings defaults only: environment, dotenv and secret-file sources never run.
    monkeypatch.setattr(BaseSettings, "settings_customise_sources", classmethod(
        lambda cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings: (init_settings,)))
    from ai_pdf_api.core.settings import settings
    monkeypatch.setattr(settings, "model_private_origins", {})
    from ai_pdf_api.services import model_endpoint, model_transport, providers
    from ai_pdf_api.services.chat_runtime_profile import build_chat_generation
    from types import SimpleNamespace
    return SimpleNamespace(build=build_chat_generation, endpoint=model_endpoint, transport=model_transport, providers=providers)


def builder_profile(protocol="openai_responses", *, source="server", provider="openai", base="https://fixture.invalid", key="synthetic-key", cancellation=False):
    connection, registry = fixture(protocol)
    connection = replace(connection, source=source, provider=provider, base_url=base, api_key=key)
    registry["profiles"][0].update(connectionSource=source, providerIdentity=provider,
        connectionFingerprint=synthetic_fingerprint(connection), supportsCancellation=cancellation)
    return resolve(connection, registry)


def synthetic_sse(protocol, *, incomplete=False):
    if protocol == "openai_responses":
        events = [{"type":"response.output_text.delta","delta":"synthetic answer"},
                  {"type":"response.completed","response":{"status":"completed"}}]
    elif protocol == "openai_chat_completions":
        events = [{"choices":[{"index":0,"delta":{"content":"synthetic answer"},"finish_reason":"stop"}]}, "[DONE]"]
    else:
        events = [{"type":"message_start","message":{}},
                  {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}},
                  {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"synthetic answer"}},
                  {"type":"content_block_stop","index":0},
                  {"type":"message_delta","delta":{"stop_reason":"end_turn"}}, {"type":"message_stop"}]
    if incomplete:
        events = events[:1]
    return "".join("data: " + (event if isinstance(event,str) else json.dumps(event)) + "\n\n" for event in events).encode()


def install_synthetic_wire(monkeypatch, dependencies, body, *, address="93.184.216.34", peer_address=None, read_error=False):
    """Synthetic DNS answers and numeric wire peer below the real policy backend."""
    import socket
    peers, dials = [], []
    class WirePeer:
        def __init__(self):
            self.closed = False
            self.writes = []
            self.tls_hosts = []
            self.reads = 0
            self.response = b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        def read(self, max_bytes, timeout=None):
            self.reads += 1
            if read_error:
                if self.reads > 1:
                    raise dependencies.transport.httpcore.ReadError("synthetic sent read failure")
                max_bytes = self.response.index(b"\r\n\r\n") + 4 + body.index(b"\n\n") + 2
            data, self.response = self.response[:max_bytes], self.response[max_bytes:]
            return data
        def write(self, buffer, timeout=None):
            self.writes.append(bytes(buffer))
        def close(self):
            self.closed = True
        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            self.tls_hosts.append(server_hostname)
            return self
        def get_extra_info(self, info):
            return (peer_address or address, 443) if info == "server_addr" else None
    def dial(self, host, port, timeout=None, local_address=None, socket_options=None):
        dials.append((host, port))
        peer = WirePeer()
        peers.append(peer)
        return peer
    monkeypatch.setattr(dependencies.transport, "_resolve", lambda host, port, timeout: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))])
    monkeypatch.setattr(dependencies.transport.httpcore.SyncBackend, "connect_tcp", dial)
    return peers, dials


class TestChatGenerationBuilder:
    @pytest.mark.parametrize("source,provider,protocol", [
        ("workspace","openai","openai_responses"),("workspace","openai","openai_chat_completions"),
        ("server","openai","openai_responses"),("server","openai","openai_chat_completions"),
        ("server","deepseek","anthropic_messages")])
    @pytest.mark.parametrize("path", ["", "/", "/custom", "/custom/", "/v1", "/v1/", "/anthropic", "/anthropic/", "/anthropic/v1", "/anthropic/v1/"])
    def test_endpoint_table_zero_sends(self, builder_dependencies, monkeypatch, source, provider, protocol, path):
        deps = builder_dependencies
        profile = builder_profile(protocol,source=source,provider=provider,base="https://fixture.invalid"+path)
        peers,dials = install_synthetic_wire(monkeypatch,deps,b"")
        original = profile.runtime_fingerprint
        with deps.transport.model_client(profile._connection.base_url,2) as client:
            generation,counter = deps.build(profile,transport=client)
            expected_path = path.rstrip("/")
            if source == "server":
                if provider == "openai":
                    expected_path = expected_path if expected_path.endswith("/v1") else expected_path+"/v1"
                else:
                    expected_path = "/custom/anthropic/v1" if expected_path == "/custom" else "/anthropic/v1"
            suffix = {"openai_responses":"/responses","openai_chat_completions":"/chat/completions","anthropic_messages":"/messages"}[protocol]
            assert generation.connection.endpoint == "https://fixture.invalid"+expected_path+suffix
            assert generation.connection.config_fingerprint == counter.profile.config_fingerprint == original
            assert generation.connection.max_output_tokens == profile.effective_max_output_tokens
            assert generation.transport is client
            assert not client.is_closed
            assert peers == dials == []
        assert client.is_closed and profile.runtime_fingerprint == original
        assert profile._connection.base_url == "https://fixture.invalid"+path

    @pytest.mark.parametrize("protocol,provider,adapter_name", [("openai_responses","openai","ResponsesAdapter"),("openai_chat_completions","openai","ChatCompletionsAdapter"),("anthropic_messages","deepseek","AnthropicAdapter")])
    def test_actual_secure_send_headers_and_close(self,builder_dependencies,monkeypatch,protocol,provider,adapter_name):
        from citeframe_contracts.memory import TurnComplete, Usage
        deps=builder_dependencies
        profile=builder_profile(protocol,provider=provider,key="  synthetic-key \t")
        original=profile.runtime_fingerprint
        peers,dials=install_synthetic_wire(monkeypatch,deps,synthetic_sse(protocol))
        with deps.transport.model_client(profile._connection.base_url,2) as client:
            generation,counter=deps.build(profile,transport=client)
            assert type(generation).__name__ == adapter_name
            assert peers == []
            request=GenerationRequest((GenerationMessage("user","synthetic question"),),100)
            iterator=generation.stream_turn(request)
            try:
                events=list(iterator)
            finally:
                iterator.close()
            assert events[-1] == TurnComplete("answer")
            assert any(isinstance(event,Usage) and event.source == "unknown" for event in events)
            assert counter.count(request,generation.connection).mode == "estimated"
            wire=b"".join(peers[0].writes).lower()
            expected=b"x-api-key: synthetic-key\r\n" if protocol=="anthropic_messages" else b"authorization: bearer synthetic-key\r\n"
            assert expected in wire and b"  synthetic-key" not in wire
            assert peers[0].tls_hosts == ["fixture.invalid"]
            assert dials == [("93.184.216.34",443)]
            assert generation.connection.api_key == "synthetic-key"
            assert not client.is_closed
        assert client.is_closed and peers[0].closed
        assert profile._connection.api_key == "  synthetic-key \t" and profile.runtime_fingerprint == original

    @pytest.mark.parametrize("source,provider,protocol", [("workspace","deepseek","anthropic_messages"),("server","anthropic","anthropic_messages"),("server","openai","anthropic_messages"),("server","deepseek","openai_responses"),("workspace","other","openai_responses")])
    def test_unsupported_combinations(self,builder_dependencies,monkeypatch,source,provider,protocol):
        deps=builder_dependencies
        profile=builder_profile(protocol,source=source,provider=provider)
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"")
        with deps.transport.model_client(profile._connection.base_url,2) as client:
            with pytest.raises(ProtocolError,match="^chat_endpoint_unsupported$"):
                deps.build(profile,transport=client)
        assert client.is_closed and peers == dials == []

    @pytest.mark.parametrize("base,code", [("https://fixture.invalid/a b","model_endpoint_invalid"),("http://fixture.invalid","model_endpoint_denied"),("https://metadata","model_endpoint_invalid"),("https://user:password@fixture.invalid","model_endpoint_invalid"),("https://fixture.invalid?q=x","model_endpoint_invalid"),("https://fixture.invalid#x","model_endpoint_invalid"),("https://fixture.invalid/%61","model_endpoint_invalid")])
    def test_invalid_raw_url(self,builder_dependencies,monkeypatch,base,code):
        deps=builder_dependencies
        profile=builder_profile(base=base)
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"")
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            with pytest.raises(ProtocolError,match=f"^{code}$"):
                deps.build(profile,transport=client)
        assert client.is_closed and peers == dials == []

    @pytest.mark.parametrize("normalized,code", [("https://fixture.invalid/bad%path","model_endpoint_invalid"),("https://other.invalid/v1","model_endpoint_denied")])
    def test_final_validation_and_origin(self,builder_dependencies,monkeypatch,normalized,code):
        deps=builder_dependencies
        monkeypatch.setattr(deps.providers,"_normalize_openai_base",lambda _:normalized)
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"")
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            with pytest.raises(ProtocolError,match=f"^{code}$"):
                deps.build(builder_profile(),transport=client)
        assert client.is_closed and peers == dials == []

    def test_whitespace_only_rejects_before_send(self,builder_dependencies,monkeypatch):
        deps=builder_dependencies
        with pytest.raises(ProtocolError,match="^chat_profile_invalid$"):
            builder_profile(key=" \t ")
        # Exercise builder defense independently of the resolver's earlier rejection.
        profile=builder_profile()
        profile=replace(profile,_connection=replace(profile._connection,api_key=" \t "))
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"")
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            with pytest.raises(ProtocolError,match="^generation_not_configured$"):
                deps.build(profile,transport=client)
        assert client.is_closed and peers == dials == []

    @pytest.mark.parametrize("cancelled,code", [(lambda:False,"chat_cancellation_unsupported"),(True,"chat_profile_invalid")])
    def test_cancellation_rejected_at_construction(self,builder_dependencies,monkeypatch,cancelled,code):
        deps=builder_dependencies
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"")
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            with pytest.raises(ProtocolError,match=f"^{code}$"):
                deps.build(builder_profile(),transport=client,cancelled=cancelled)
        assert client.is_closed and peers == dials == []

    @pytest.mark.parametrize("mode", ["iterator_close","cancel","incomplete","pre_cancel","sent_read_error"])
    def test_iterator_and_client_cleanup(self,builder_dependencies,monkeypatch,mode):
        deps=builder_dependencies
        peers,dials=install_synthetic_wire(monkeypatch,deps,synthetic_sse("openai_responses",incomplete=mode=="incomplete"),read_error=mode=="sent_read_error")
        cancelled=[mode=="pre_cancel"]
        closed=[]
        original_close=deps.transport._ResponseStream.close
        def tracked_close(stream):
            closed.append(True)
            return original_close(stream)
        monkeypatch.setattr(deps.transport._ResponseStream,"close",tracked_close)
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            generation,_=deps.build(builder_profile(cancellation=True),transport=client,cancelled=lambda:cancelled[0])
            iterator=generation.stream_turn(GenerationRequest((GenerationMessage("user","synthetic"),),100))
            try:
                if mode=="pre_cancel":
                    with pytest.raises(ProtocolError,match="generation_cancelled"):
                        next(iterator)
                else:
                    assert next(iterator).text == "synthetic answer"
                    if mode=="cancel":
                        cancelled[0]=True
                        with pytest.raises(ProtocolError,match="generation_cancelled"):
                            list(iterator)
                    elif mode in ("incomplete", "sent_read_error"):
                        code = "generation_protocol_invalid" if mode == "incomplete" else "generation_transport_error"
                        with pytest.raises(ProtocolError, match=f"^{code}$"):
                            list(iterator)
            finally:
                iterator.close()
            assert not client.is_closed
            assert bool(closed) == (mode!="pre_cancel")
        assert client.is_closed
        assert all(peer.closed for peer in peers)
        assert len(dials) == (0 if mode=="pre_cancel" else 1)
        if mode == "sent_read_error":
            assert peers[0].writes and peers[0].reads == 2

    @pytest.mark.parametrize("case", ["request_origin","private_dns","peer_mismatch"])
    def test_real_security_boundary(self,builder_dependencies,monkeypatch,case):
        from ai_pdf_api.services.model_config_types import ModelConfigurationError
        deps=builder_dependencies
        peers,dials=install_synthetic_wire(monkeypatch,deps,b"",address="127.0.0.1" if case=="private_dns" else "93.184.216.34",peer_address="93.184.216.35" if case=="peer_mismatch" else None)
        with deps.transport.model_client("https://fixture.invalid",2) as client:
            if case=="request_origin":
                with pytest.raises(ModelConfigurationError) as caught:
                    client.get("https://other.invalid")
                assert caught.value.code == "model_endpoint_denied"
            else:
                generation,_=deps.build(builder_profile(),transport=client)
                with pytest.raises(ProtocolError,match="generation_transport_error"):
                    list(generation.stream_turn(GenerationRequest((GenerationMessage("user","synthetic"),),100)))
        assert client.is_closed
        assert bool(dials) == (case=="peer_mismatch")
        assert all(peer.closed for peer in peers)

    @pytest.mark.parametrize("failure", ["construction", "runner_shutdown"])
    def test_exception_exits_owned_client_context(self, builder_dependencies, monkeypatch, failure):
        deps = builder_dependencies
        peers, dials = install_synthetic_wire(monkeypatch, deps, synthetic_sse("openai_responses"))
        error = ProtocolError if failure == "construction" else KeyboardInterrupt
        with pytest.raises(error):
            with deps.transport.model_client("https://fixture.invalid", 2) as client:
                profile = builder_profile(provider="unsupported" if failure == "construction" else "openai")
                generation, _ = deps.build(profile, transport=client)
                iterator = generation.stream_turn(GenerationRequest((GenerationMessage("user", "synthetic"),), 100))
                try:
                    assert next(iterator).text == "synthetic answer"
                    raise KeyboardInterrupt()
                finally:
                    iterator.close()
        assert client.is_closed
        assert len(dials) == (0 if failure == "construction" else 1)
        assert all(peer.closed for peer in peers)
