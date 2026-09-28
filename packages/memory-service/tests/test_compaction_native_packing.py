"""Native serializer/counting regressions; no provider calls or persistence claims."""
from dataclasses import asdict, replace
import json

import pytest

from citeframe_contracts.memory import GenerationMessage, GenerationRequest, ModelConnectionSnapshot, ToolCall, ToolDefinition
from citeframe_memory.adapters import CharacterEstimateCounter, CountingProfile
from citeframe_memory.compaction.guards import canonical
from citeframe_memory.compaction.packing import partition_summary_chunks, plan_compaction
from citeframe_memory.compaction.policy import Capacity, CompactionError, CompactionPolicy, CounterIdentity, capacity_for
from citeframe_memory.compaction.units import ContextUnit

PROTOCOLS = ("openai_responses", "openai_chat_completions", "anthropic")
POLICY = CompactionPolicy(min_new_tokens=1, min_gain_tokens=1)


def native_counter(protocol, *, context=8000, output=1000):
    connection = ModelConnectionSnapshot(protocol, "https://fixture.invalid", "fixture", "fixture-key", 2, "same-profile", context, output)
    profile = CountingProfile(protocol, "fixture", "same-profile", context, "character", "v1", "estimated")
    counter = CharacterEstimateCounter(profile, characters_per_token=4, protocol_overhead_tokens=8)
    identity = CounterIdentity("character", "v1", "estimated", "same-profile")
    return connection, counter, identity


def parallel_group(key, states):
    calls = tuple(ToolCall(f"{key}-{i}", "read_source", canonical({"source": f"原文-{i}", "condition": "only batch=8", "negated": True})) for i in range(2))
    return ContextUnit(key, "tool_group", (
        GenerationMessage("assistant", "保留完整批次", calls),
        *(GenerationMessage("tool", f"{states[i]}: 原文😀 37.5 ms; never production; only batch=8\\n", tool_call_id=call.call_id) for i, call in enumerate(calls)),
    ), states)


def projection(unit):
    return {"sourceUnit": {"key": unit.key, "kind": unit.kind,
            "messages": [asdict(message) for message in unit.messages],
            "resultStates": list(unit.result_states)}}


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("states", [("succeeded", "failed"), ("failed", "cancelled"), ("cancelled", "succeeded")])
def test_native_toolless_summary_chunks_preserve_parallel_transcripts(protocol, states):
    connection, counter, identity = native_counter(protocol)
    units = tuple(parallel_group(f"batch-{i}", states) for i in range(3))
    tool = ToolDefinition("read_source", "Read original source", '{"type":"object"}')
    main = GenerationRequest(tuple(message for unit in units for message in unit.messages), 100, tools=(tool,))
    assert counter.count(main, connection).tokens > 0
    template = GenerationRequest((GenerationMessage("system", "Summarize attributed source data."),), 100, purpose="compact_chunk")
    expected_one = replace(template, messages=template.messages + (GenerationMessage("user", canonical(projection(units[0]))),))
    limit = counter.count(expected_one, connection).tokens
    chunks = partition_summary_chunks(template, units, input_limit=limit, policy=POLICY,
        connection=connection, counter=counter, identity=identity)
    assert tuple(unit for chunk in chunks for unit in chunk.units) == units
    assert len(chunks) == 3
    for chunk in chunks:
        assert len(chunk.units) == 1
        assert chunk.request.tools == ()
        assert chunk.request.purpose == "compact_chunk"
        assert chunk.request.messages[:1] == template.messages
        assert all(not message.tool_calls and message.tool_call_id is None and message.role != "tool" for message in chunk.request.messages)
        projected = chunk.request.messages[1:]
        assert len(projected) == 1 and projected[0].role == "user"
        assert projected[0].content == canonical(projection(chunk.units[0]))
        assert json.loads(projected[0].content) == json.loads(canonical(projection(chunk.units[0])))
        assert chunk.count == counter.count(chunk.request, connection)
        assert chunk.count.tokens <= limit <= connection.context_window_tokens - template.max_output_tokens


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("change", ["context", "output"])
def test_stale_capacity_rejected_with_unchanged_profile_identity(protocol, change):
    original, _, _ = native_counter(protocol, context=1000, output=500)
    template = GenerationRequest((GenerationMessage("system", "rules"),), 100)
    stale = capacity_for(original, template, POLICY, input_ceiling=900, safety_margin=0)
    connection, counter, identity = native_counter(protocol, context=200 if change == "context" else 1000, output=500)
    if change == "output":
        template = replace(template, max_output_tokens=400)
    assert connection.config_fingerprint == original.config_fingerprint
    units = (ContextUnit("current", "messages", (GenerationMessage("user", "x" * 500),), protected=True),)
    with pytest.raises(CompactionError, match="^capacity_profile_mismatch$"):
        plan_compaction(template, units, recent_units=1, new_unit_keys=frozenset(), policy=POLICY,
            capacity=stale, connection=connection, counter=counter, identity=identity)


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_current_output_above_profile_rejected(protocol):
    connection, counter, identity = native_counter(protocol, context=1000, output=100)
    template = GenerationRequest((GenerationMessage("system", "rules"),), 101)
    units = (ContextUnit("current", "messages", (GenerationMessage("user", "question"),), protected=True),)
    with pytest.raises(CompactionError, match="^invalid_capacity_reserve$"):
        plan_compaction(template, units, recent_units=1, new_unit_keys=frozenset(), policy=POLICY,
            capacity=Capacity(800, 640, 480), connection=connection, counter=counter, identity=identity)


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_stricter_current_capacity_preserved(protocol):
    connection, counter, identity = native_counter(protocol, context=1000, output=100)
    template = GenerationRequest((GenerationMessage("system", "rules"),), 100)
    units = (ContextUnit("current", "messages", (GenerationMessage("user", "question"),), protected=True),)
    capacity = capacity_for(connection, template, POLICY, input_ceiling=300, safety_margin=20)
    result = plan_compaction(template, units, recent_units=1, new_unit_keys=frozenset(), policy=POLICY,
        capacity=capacity, connection=connection, counter=counter, identity=identity)
    assert result.reason == "below_soft"
    assert result.original_count == counter.count(result.original_request, connection)
    assert result.original_count.tokens < capacity.soft < capacity.hard == 300


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_current_physical_margin_rejects_unreserved_capacity(protocol):
    connection, counter, identity = native_counter(protocol, context=1000, output=100)
    template = GenerationRequest((GenerationMessage("system", "rules"),), 100)
    units = (ContextUnit("current", "messages", (GenerationMessage("user", "question"),), protected=True),)
    unreserved = capacity_for(connection, template, POLICY, input_ceiling=900, safety_margin=0)
    with pytest.raises(CompactionError, match="^capacity_profile_mismatch$"):
        plan_compaction(template, units, recent_units=1, new_unit_keys=frozenset(), policy=POLICY,
            capacity=unreserved, connection=connection, counter=counter, identity=identity, safety_margin=20)


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_tool_transcript_chunks_obey_current_physical_cap(protocol):
    connection, counter, identity = native_counter(protocol)
    units = (parallel_group("batch-a", ("failed", "cancelled")), parallel_group("batch-b", ("failed", "cancelled")))
    template = GenerationRequest((GenerationMessage("system", "Summarize source data."),), 100, purpose="compact_chunk")
    expected = replace(template, messages=template.messages + (GenerationMessage("user", canonical(projection(units[0]))),))
    one_count = counter.count(expected, connection).tokens
    connection, counter, identity = native_counter(protocol, context=one_count + 100 + 20)
    chunks = partition_summary_chunks(template, units, input_limit=9999, policy=POLICY,
        connection=connection, counter=counter, identity=identity, safety_margin=20)
    assert tuple(unit for chunk in chunks for unit in chunk.units) == units
    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.count == counter.count(chunk.request, connection)
        assert chunk.count.tokens <= one_count == connection.context_window_tokens - template.max_output_tokens - 20
