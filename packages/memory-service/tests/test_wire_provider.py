"""Synthetic native wire fixtures; no live provider or credential access."""

import pytest

from citeframe_memory.adapters._streams import AnthropicState, ChatState, ResponsesState
from citeframe_memory.adapters._wire import CallBuffer, WireLimits, sse_events


def parse(state, events):
    for event in events:
        state.feed(event)
    return state.result(require_done=not isinstance(state, ChatState))


def test_provider_responses_existing_text_fixture_parity():
    # apps/api/tests/test_providers.py::test_openai_generation_provider_streams_response_text_deltas
    events = [
        {"type": "response.output_text.delta", "delta": "first"},
        {"type": "response.output_text.delta", "delta": " second"},
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    assert parse(ResponsesState(WireLimits()), events) == ("first second", [], {})


def test_provider_chat_fragmented_native_ids_names_arguments():
    events = [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_", "type": "function", "function": {"name": "search_", "arguments": '{"q":'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "123", "function": {"name": "history", "arguments": '"x"}'}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        "[DONE]",
    ]
    assert parse(ChatState(WireLimits()), events) == ("", [("call_123", "search_history", {"q": "x"})], {"input_tokens": 10, "output_tokens": 5})


def test_provider_responses_native_tool_completion():
    events = [
        {"type": "response.output_item.added", "output_index": 1, "item": {"type": "function_call", "id": "item1", "call_id": "native1", "name": "read_source", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 1, "delta": '{"id":'},
        {"type": "response.function_call_arguments.delta", "output_index": 1, "delta": '"src"}'},
        {"type": "response.function_call_arguments.done", "output_index": 1, "arguments": '{"id":"src"}'},
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    assert parse(ResponsesState(WireLimits()), events)[1] == [("native1", "read_source", {"id": "src"})]


def test_provider_anthropic_native_tool_completion():
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 3, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "tool1", "name": "search_history", "input": {}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"q":"x"}'}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    assert parse(AnthropicState(WireLimits()), events) == ("", [("tool1", "search_history", {"q": "x"})], {"input_tokens": 3, "output_tokens": 4})


@pytest.mark.parametrize("state,events", [
    (ResponsesState, [{"type": "response.output_text.delta", "delta": "partial"}]),
    (ResponsesState, [{"type": "response.completed", "response": {"status": "incomplete"}}]),
    (ChatState, ["[DONE]"]),
    (ChatState, [{"choices": [{"delta": {"content": "partial"}, "finish_reason": "length"}]}]),
    (AnthropicState, [{"type": "message_start", "message": {}}, {"type": "message_stop"}]),
])
def test_provider_incomplete_and_invalid_terminal_rejected(state, events):
    with pytest.raises(ValueError):
        parse(state(WireLimits()), events)


@pytest.mark.parametrize("arguments", ['[]', '{"a":1,"a":2}', '{"a":NaN}', '{'])
def test_provider_tool_arguments_are_strict_objects(arguments):
    buffer = CallBuffer(WireLimits())
    buffer.start(0, "id", "name")
    buffer.append(0, arguments=arguments)
    with pytest.raises(ValueError):
        buffer.complete()


def test_provider_duplicate_ids_rejected():
    buffer = CallBuffer(WireLimits())
    for index in range(2):
        buffer.start(index, "same", "name")
        buffer.append(index, arguments="{}")
    with pytest.raises(ValueError):
        buffer.complete()


def test_provider_argument_bytes_and_total_metadata_bounded():
    buffer = CallBuffer(WireLimits())
    buffer.start(0, "id", "name")
    with pytest.raises(ValueError):
        buffer.append(0, arguments="中" * 6000)
    state = ResponsesState(WireLimits(max_text_bytes=80))
    with pytest.raises(ValueError):
        for _ in range(10):
            state.feed({"type": "response.in_progress"})
    with pytest.raises(ValueError):
        list(sse_events([": heartbeat"] * 20, WireLimits(max_text_bytes=80)))


def test_provider_sse_json_and_missing_delimiter():
    assert list(sse_events(['data: {"type":"x"}', '', 'data: [DONE]', ''], WireLimits())) == [{"type": "x"}, "[DONE]"]
    with pytest.raises(ValueError):
        list(sse_events(['data: {"type":"x"}'], WireLimits()))


def test_provider_prose_is_never_a_tool():
    text = 'Call search_history({"q":"private"})'
    result = parse(ChatState(WireLimits()), [{"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}, "[DONE]"])
    assert result == (text, [], {})
