"""Synthetic typed transitions and native serializer compatibility; no loop runtime."""

from contextlib import contextmanager
from dataclasses import replace
import json

import pytest

from citeframe_contracts.memory import (
    GenerationMessage, GenerationRequest, ModelConnectionSnapshot, ProtocolError,
    TextDelta, ToolCall, ToolCallComplete, ToolCallDelta, ToolDefinition,
    TurnComplete, Usage,
)
from citeframe_memory.adapters import (
    AnthropicAdapter, Capabilities, CharacterEstimateCounter, ChatCompletionsAdapter, CountingProfile,
    PayloadTokenCounter, ResponsesAdapter,
)
from citeframe_memory.chat_loop.turns import (
    ToolOutcome, TurnIdentity, TurnLimits, collect_turn, continuation_decision,
)

TOOL = ToolDefinition("search_history", "Synthetic tool", '{"type":"object","properties":{"q":{"type":"string"}},"required":["q"],"additionalProperties":false}')
REQUEST = GenerationRequest((GenerationMessage("user", "question"),), 100, tools=(TOOL,))
IDENTITY = TurnIdentity("execution", "root", "provider-call")
CALLS = (ToolCall("native-0", TOOL.name, '{ "q": "first" }'), ToolCall("native-1", TOOL.name, '{"q":"second"}'))


def tool_turn(calls=CALLS):
    return collect_turn([*(ToolCallComplete(call) for call in calls), TurnComplete("tool_calls")], REQUEST)


def test_turn_collector_retains_exact_calls_order_usage_and_text():
    usage = Usage(10, None, "estimated")
    turn = collect_turn([
        TextDelta("provisional "),
        ToolCallDelta(1, '{"q":', "native-", "search_"),
        ToolCallDelta(0, '{ "q": "first" }', "native-0", TOOL.name),
        ToolCallDelta(1, '"second"}', "1", "history"),
        *(ToolCallComplete(call) for call in CALLS), usage, TurnComplete("tool_calls"),
    ], REQUEST)
    assert turn.text == "provisional " and turn.calls == CALLS
    assert turn.calls[0] is CALLS[0] and turn.calls[1] is CALLS[1]
    assert turn.usage is usage


@pytest.mark.parametrize("usage", [Usage(0, 0, "reported"), Usage(None, 2, "estimated"), Usage(None, None, "unknown")])
def test_turn_usage_provenance_and_none_preserved(usage):
    turn = collect_turn([TextDelta(" answer "), usage, TurnComplete("answer")], REQUEST)
    assert turn.text == " answer " and turn.usage is usage


def test_turn_absent_usage_is_unknown():
    assert collect_turn([TextDelta("answer"), TurnComplete("answer")], REQUEST).usage == Usage(None, None, "unknown")


@pytest.mark.parametrize("events", [
    [], [TextDelta("partial")], [TurnComplete("answer")],
    [TextDelta(" \n"), TurnComplete("answer")],
    [TextDelta("answer"), TurnComplete("answer"), TurnComplete("answer")],
    [TextDelta("answer"), TurnComplete("answer"), TextDelta("late")],
    [TextDelta("answer"), TurnComplete("answer"), Usage(1, 1)],
    [TurnComplete("tool_calls")],
    [ToolCallComplete(CALLS[0]), TurnComplete("answer")],
    [ToolCallComplete(CALLS[0]), ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")],
    [ToolCallComplete(CALLS[0]), ToolCallComplete(replace(CALLS[0], arguments_json='{"q":"different"}')), TurnComplete("tool_calls")],
    [ToolCallDelta(0, "{}", "different", TOOL.name), ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")],
    [ToolCallDelta(0, "{}", CALLS[0].call_id, "different"), ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")],
    [ToolCallDelta(0, "{}", CALLS[0].call_id, TOOL.name), TurnComplete("tool_calls")],
    [ToolCallComplete(replace(CALLS[0], name="undeclared")), TurnComplete("tool_calls")],
    [ToolCallComplete(CALLS[0]), ToolCallDelta(0, "late"), TurnComplete("tool_calls")],
    [TextDelta("answer"), Usage(1, 1), Usage(1, 1), TurnComplete("answer")],
    [TextDelta("answer"), Usage(True, 1), TurnComplete("answer")],
    [TextDelta("answer"), Usage(-1, 1), TurnComplete("answer")],
    [ToolCallDelta(True, "{}"), ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")],
    [object()],
])
def test_turn_invalid_or_nonmonotonic_events_never_return_acceptance(events):
    with pytest.raises(ProtocolError):
        collect_turn(events, REQUEST)


def test_turn_requires_stream_exhaustion_after_terminal():
    closed = []
    def events():
        try:
            yield TextDelta("answer")
            yield TurnComplete("answer")
            raise RuntimeError("synthetic sensitive details")
        finally:
            closed.append(True)
    with pytest.raises(ProtocolError, match="^chat_turn_stream_failed$"):
        collect_turn(events(), REQUEST)
    assert closed == [True]


@pytest.mark.parametrize("when", ["before", "during", "after_terminal"])
def test_turn_cancellation_never_accepts_late_output(when):
    cancel = [when == "before"]
    closed = []
    def events():
        try:
            yield TextDelta("answer")
            if when == "during": cancel[0] = True
            yield TurnComplete("answer")
            if when == "after_terminal": cancel[0] = True
        finally:
            closed.append(True)
    with pytest.raises(ProtocolError, match="chat_turn_cancelled"):
        collect_turn(events(), REQUEST, cancelled=lambda: cancel[0])
    if when != "before": assert closed == [True]


def test_turn_close_failure_prevents_acceptance():
    class Events:
        def __iter__(self): return self
        def __init__(self): self.events = iter([TextDelta("answer"), TurnComplete("answer")])
        def __next__(self): return next(self.events)
        def close(self): raise RuntimeError("sensitive details")
    with pytest.raises(ProtocolError, match="^chat_turn_stream_close_failed$"):
        collect_turn(Events(), REQUEST)


@pytest.mark.parametrize("events,limits", [
    ([TextDelta("中中"), TurnComplete("answer")], TurnLimits(max_bytes=5)),
    ([TextDelta("a"), TextDelta("b"), TurnComplete("answer")], TurnLimits(max_events=2)),
    ([ToolCallComplete(CALLS[0]), ToolCallComplete(CALLS[1]), TurnComplete("tool_calls")], TurnLimits(max_calls=1)),
    ([ToolCallDelta(0, "123"), ToolCallDelta(0, "456")], TurnLimits(max_argument_bytes=5)),
    ([ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")], TurnLimits(max_argument_bytes=5)),
    ([ToolCallComplete(CALLS[0]), TurnComplete("tool_calls")], TurnLimits(max_identity_bytes=3)),
])
def test_turn_bounds_fail_closed(events, limits):
    with pytest.raises(ProtocolError, match="chat_turn_limit_exceeded"):
        collect_turn(events, REQUEST, limits=limits)


@pytest.mark.parametrize("statuses", [("completed", "completed"), ("failed", "completed"), ("cancelled", "failed")])
def test_turn_known_results_return_only_gate_required_with_unchanged_identity(statuses):
    turn = tool_turn()
    outcomes = tuple(ToolOutcome(call.call_id, status, f"original {status}") for call, status in zip(CALLS, statuses))
    decision = continuation_decision(REQUEST, turn, IDENTITY, reversed(outcomes))
    assert decision.action == "gate_required" and decision.identity is IDENTITY
    assert decision.outcomes == outcomes
    assert decision.request.messages[:len(REQUEST.messages)] == REQUEST.messages
    assistant, *results = decision.request.messages[len(REQUEST.messages):]
    assert assistant.tool_calls == CALLS
    assert [message.tool_call_id for message in results] == [call.call_id for call in CALLS]
    assert [json.loads(message.content) for message in results] == [{"status": item.status, "content": item.content} for item in outcomes]
    assert decision.request.tools is REQUEST.tools
    assert decision.request.max_output_tokens == REQUEST.max_output_tokens
    assert decision.request.purpose == REQUEST.purpose


@pytest.mark.parametrize("outcomes,reason", [
    ([], "pending_results"),
    ([ToolOutcome("native-0", "completed", "result")], "pending_results"),
    ([ToolOutcome("native-0", "pending"), ToolOutcome("native-1", "completed", "result")], "pending_results"),
    ([ToolOutcome("native-0", "unknown"), ToolOutcome("native-1", "completed", "result")], "unknown_result"),
])
def test_turn_incomplete_results_do_not_construct_continuation(outcomes, reason):
    decision = continuation_decision(REQUEST, tool_turn(), IDENTITY, outcomes)
    assert decision.action == "stop" and decision.stop_reason == reason
    assert decision.request is None and decision.identity is IDENTITY


def test_turn_cancelled_execution_cannot_continue_with_complete_results():
    decision = continuation_decision(REQUEST, tool_turn(), IDENTITY, [ToolOutcome(call.call_id, "completed", "result") for call in CALLS], cancelled=True)
    assert decision.action == "stop" and decision.stop_reason == "cancelled" and decision.request is None


def test_turn_identical_result_delivery_deduplicates_locally_in_member_order():
    first, second = [ToolOutcome(call.call_id, "completed", "result") for call in CALLS]
    decision = continuation_decision(REQUEST, tool_turn(), IDENTITY, [second, first, second])
    assert decision.outcomes == (first, second)
    assert len(decision.request.messages) == len(REQUEST.messages) + 3


@pytest.mark.parametrize("outcomes", [
    [ToolOutcome("wrong", "completed", "result")],
    [ToolOutcome("native-0", "completed", "result"), ToolOutcome("native-0", "failed", "result")],
    [ToolOutcome("native-0", "completed", "first"), ToolOutcome("native-0", "completed", "different")],
    [ToolOutcome("native-0", "completed")],
])
def test_turn_mismatched_or_unpaired_results_rejected(outcomes):
    with pytest.raises(ProtocolError):
        continuation_decision(REQUEST, tool_turn(), IDENTITY, outcomes)


@pytest.mark.parametrize("protocol", ["openai_responses", "openai_chat_completions", "anthropic"])
@pytest.mark.parametrize("second_status", ["failed", "cancelled"])
def test_turn_continuation_uses_actual_neutral_counter_and_native_serializer(protocol, second_status):
    turn = tool_turn()
    decision = continuation_decision(REQUEST, turn, IDENTITY, [ToolOutcome(call.call_id, status, "original result") for call, status in zip(CALLS, ("completed", second_status))])
    connection = ModelConnectionSnapshot(protocol, "https://synthetic.invalid/endpoint", "synthetic", "synthetic-key", 2, "fp", 8000, 1000)
    captured = []
    profile = CountingProfile(protocol, "synthetic", "fp", 8000, "synthetic-counter", "v1", "estimated")
    count = PayloadTokenCounter(profile, lambda payload: captured.append(json.loads(payload)) or 123).count(decision.request, connection)
    assert count.mode == "estimated" and count.tokens == 123
    estimator = CharacterEstimateCounter(profile, characters_per_token=4, protocol_overhead_tokens=8)
    estimate = estimator.count(decision.request, connection)
    assert estimate.mode == "estimated" and estimate.tokens > 8
    assert estimate == estimator.count(decision.request, connection)
    wire = captured[0]
    if protocol == "openai_responses":
        assert [item["call_id"] for item in wire["input"] if item.get("type") == "function_call_output"] == [call.call_id for call in CALLS]
    elif protocol == "openai_chat_completions":
        assert [item["tool_call_id"] for item in wire["messages"] if item["role"] == "tool"] == [call.call_id for call in CALLS]
    else:
        assert [item["tool_use_id"] for item in wire["messages"][-1]["content"]] == [call.call_id for call in CALLS]
    assert "original result" in json.dumps(wire) and json.dumps(second_status) in json.dumps(wire).replace('\\"', '"')


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_turn_collects_actual_adapter_typed_output_with_synthetic_transport(cls):
    args = '{"q":"first"}'
    if cls is ResponsesAdapter:
        events = [
            {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "id": "item", "call_id": "native-0", "name": TOOL.name, "arguments": ""}},
            {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "item", "delta": args},
            {"type": "response.function_call_arguments.done", "output_index": 0, "item_id": "item", "arguments": args},
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    elif cls is ChatCompletionsAdapter:
        events = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "native-0", "function": {"name": TOOL.name, "arguments": args}}]}, "finish_reason": "tool_calls"}]}, "[DONE]"]
    else:
        events = [
            {"type": "message_start", "message": {}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "native-0", "name": TOOL.name, "input": {}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": args}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
            {"type": "message_stop"},
        ]
    class SyntheticTransport:
        status_code = 200
        closed = False
        @contextmanager
        def stream(self, *args, **kwargs):
            try: yield self
            finally: self.closed = True
        def iter_lines(self):
            for event in events:
                yield "data: " + (event if isinstance(event, str) else json.dumps(event))
                yield ""
    transport = SyntheticTransport()
    connection = ModelConnectionSnapshot(cls.protocol, "https://synthetic.invalid/endpoint", "synthetic", "synthetic-key", 2, "fp", 8000, 1000)
    adapter = cls(connection, transport, Capabilities(cls.protocol, "native-v1", True, True))
    turn = collect_turn(adapter.stream_turn(REQUEST), REQUEST)
    assert turn.calls == (ToolCall("native-0", TOOL.name, args),)
    assert turn.reason == "tool_calls" and turn.usage == Usage(None, None, "unknown")
    assert transport.closed


def test_turn_protocol_failure_after_terminal_prevents_acceptance():
    def events():
        yield TextDelta("answer")
        yield TurnComplete("answer")
        raise ProtocolError("synthetic_terminal_failure")
    with pytest.raises(ProtocolError, match="synthetic_terminal_failure"):
        collect_turn(events(), REQUEST)


def test_turn_cancellation_during_close_prevents_acceptance():
    cancel = [False]
    class Events:
        def __iter__(self): return self
        def __init__(self): self.events = iter([TextDelta("answer"), TurnComplete("answer")])
        def __next__(self): return next(self.events)
        def close(self): cancel[0] = True
    with pytest.raises(ProtocolError, match="chat_turn_cancelled"):
        collect_turn(Events(), REQUEST, cancelled=lambda: cancel[0])


def test_turn_conflicting_terminal_rejected():
    with pytest.raises(ProtocolError, match="chat_turn_event_after_terminal"):
        collect_turn([ToolCallComplete(CALLS[0]), TurnComplete("tool_calls"), TurnComplete("answer")], REQUEST)


def test_turn_result_duplicate_flood_and_encoded_content_bounded():
    outcome = ToolOutcome("native-0", "completed", "result")
    with pytest.raises(ProtocolError, match="chat_turn_limit_exceeded"):
        continuation_decision(REQUEST, tool_turn(), IDENTITY, [outcome] * 3, limits=TurnLimits(max_events=2))
    outcomes = [ToolOutcome(call.call_id, "completed", "\n" * 100) for call in CALLS]
    with pytest.raises(ProtocolError, match="chat_turn_limit_exceeded"):
        continuation_decision(REQUEST, tool_turn(), IDENTITY, outcomes, limits=TurnLimits(max_bytes=300))


def test_turn_answer_has_no_tool_continuation():
    answer = collect_turn([TextDelta("answer"), TurnComplete("answer")], REQUEST)
    with pytest.raises(ProtocolError, match="chat_turn_continuation_not_applicable"):
        continuation_decision(REQUEST, answer, IDENTITY, [])
