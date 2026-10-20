"""Synthetic exact-counter injection and explicitly estimated counting evidence."""

from dataclasses import replace

import pytest

from citeframe_contracts.memory import GenerationMessage, GenerationRequest, ModelConnectionSnapshot, ProtocolError
from citeframe_memory.adapters import CharacterEstimateCounter, CountingProfile, PayloadTokenCounter


def fixture():
    connection = ModelConnectionSnapshot("openai_responses", "https://synthetic.invalid/responses", "synthetic", "synthetic-key", 2, "fp", 8000, 1000)
    request = GenerationRequest((GenerationMessage("user", "问题"),), 100)
    profile = CountingProfile(connection.protocol, connection.model, "fp", 8000, "synthetic-counter", "v1", "exact")
    return connection, request, profile


def test_counting_exact_injected_counter_receives_full_protocol_payload():
    connection, request, profile = fixture()
    seen = []
    counter = PayloadTokenCounter(profile, lambda wire: seen.append(wire) or 123)
    result = counter.count(request, connection)
    assert (result.tokens, result.mode, result.counter_version, result.config_fingerprint) == (123, "exact", "v1", "fp")
    assert '"max_output_tokens":100' in seen[0] and '"model":"synthetic"' in seen[0] and "问题" in seen[0]


def test_counting_character_estimate_never_exact():
    connection, request, profile = fixture()
    with pytest.raises(ValueError):
        CharacterEstimateCounter(profile, characters_per_token=4, protocol_overhead_tokens=8)
    counter = CharacterEstimateCounter(replace(profile, mode="estimated"), characters_per_token=4, protocol_overhead_tokens=8)
    result = counter.count(request, connection)
    assert result.mode == "estimated" and result.tokens > 8


@pytest.mark.parametrize("change", [{"context_window_tokens": 0}, {"model": "unknown"}, {"config_fingerprint": "stale"}, {"counter_version": ""}, {"mode": "unknown"}])
def test_counting_unknown_or_mismatched_profile_rejected(change):
    connection, request, profile = fixture()
    with pytest.raises(ProtocolError, match="memory_counting_profile_unknown"):
        PayloadTokenCounter(replace(profile, **change), lambda _: 1).count(request, connection)


@pytest.mark.parametrize("value", [-1, True, 1.5, None])
def test_counting_invalid_counts_rejected(value):
    connection, request, profile = fixture()
    with pytest.raises(ProtocolError, match="memory_counting_invalid"):
        PayloadTokenCounter(profile, lambda _: value).count(request, connection)


def test_counting_payload_includes_tool_schema_calls_results_and_framing():
    from citeframe_contracts.memory import ToolCall, ToolDefinition
    connection, request, profile = fixture()
    tool = ToolDefinition("lookup", "description", '{"type":"object","properties":{}}')
    messages = (GenerationMessage("assistant", "", (ToolCall("native", "lookup", "{}"),)), GenerationMessage("tool", "result marker", tool_call_id="native"))
    request = replace(request, messages=messages, tools=(tool,))
    seen = []
    result = PayloadTokenCounter(replace(profile, mode="estimated"), lambda wire: seen.append(wire) or len(wire)).count(request, connection)
    assert result.mode == "estimated"
    for marker in ('"tools":', '"parameters":', '"function_call"', '"function_call_output"', '"call_id":"native"', "result marker", '"stream":true'):
        assert marker in seen[0]


@pytest.mark.parametrize("change", [{"counter_id": 1}, {"counter_version": True}])
def test_counting_metadata_requires_strings(change):
    connection, request, profile = fixture()
    with pytest.raises(ProtocolError):
        PayloadTokenCounter(replace(profile, **change), lambda _: 1).count(request, connection)
