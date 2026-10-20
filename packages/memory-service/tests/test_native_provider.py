"""Synthetic transport fixtures exercise neutral DTOs without application imports."""

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

from citeframe_contracts.memory import GenerationMessage, GenerationRequest, ModelConnectionSnapshot, ProtocolError, TextDelta, ToolCall, ToolCallComplete, ToolDefinition, TurnComplete, Usage
from citeframe_memory.adapters import AnthropicAdapter, Capabilities, ChatCompletionsAdapter, ResponsesAdapter


TOOL = ToolDefinition("search_history", "Search lawful shared history", '{"type":"object","properties":{"q":{"type":"string"}},"required":["q"],"additionalProperties":false}')


class SyntheticTransport:
    def __init__(self, events, *, status=200):
        self.events = events
        self.status_code = status
        self.requests = []
        self.closed = False

    @contextmanager
    def stream(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        try:
            yield self
        finally:
            self.closed = True

    def iter_lines(self):
        for event in self.events:
            yield "data: " + (event if isinstance(event, str) else json.dumps(event))
            yield ""

    def read(self):
        raise AssertionError("error response bodies must not be read")


def connection(protocol):
    return ModelConnectionSnapshot(protocol, "https://synthetic.invalid/endpoint", "synthetic-model", "synthetic-key", 2, "synthetic-fingerprint", 10000, 1000)


def adapter(cls, events, **kwargs):
    transport = SyntheticTransport(events)
    caps = Capabilities(cls.protocol, cls.adapter_version, True, True, True)
    return cls(connection(cls.protocol), transport, caps, **kwargs), transport


def text_events(cls, text="first second"):
    if cls == ResponsesAdapter:
        return [{"type": "response.output_text.delta", "delta": text}, {"type": "response.completed", "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 2}}}]
    if cls == ChatCompletionsAdapter:
        return [{"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": "stop"}]}, {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}, "[DONE]"]
    return [{"type": "message_start", "message": {"usage": {"input_tokens": 5}}}, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}, {"type": "content_block_stop", "index": 0}, {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}}, {"type": "message_stop"}]


def request(*, tools=()):
    return GenerationRequest((GenerationMessage("system", "rules"), GenerationMessage("user", "question")), 77, tools=tools)


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_text_stream_and_usage_parity(cls):
    # Legacy test_providers.py text fixtures: stream preserves text; generate strips.
    instance, transport = adapter(cls, text_events(cls, " first second "))
    events = list(instance.stream_turn(request()))
    assert events == [TextDelta(" first second "), Usage(5, 2, "reported"), TurnComplete("answer")]
    assert transport.closed
    assert instance.generate(request()) == "first second"
    method, url, sent = transport.requests[0]
    assert method == "POST" and url == "https://synthetic.invalid/endpoint"
    assert sent["timeout"] == 2 and sent["json"]["stream"] is True
    assert sent["json"].get("max_output_tokens", sent["json"].get("max_tokens")) == 77
    if cls == AnthropicAdapter:
        assert sent["json"]["system"] == "rules"
    elif cls == ResponsesAdapter:
        assert sent["json"]["input"] == [{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}]


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_native_history_call_result_pairing(cls):
    instance, transport = adapter(cls, text_events(cls))
    call = ToolCall("native-call", TOOL.name, '{"q":"x"}')
    history = GenerationRequest((GenerationMessage("user", "question"), GenerationMessage("assistant", "", (call,)), GenerationMessage("tool", "lawful result", tool_call_id=call.call_id)), 77, tools=(TOOL,))
    list(instance.stream_turn(history))
    sent = transport.requests[0][2]["json"]
    if cls == ResponsesAdapter:
        assert sent["input"][-1] == {"type": "function_call_output", "call_id": "native-call", "output": "lawful result"}
    elif cls == ChatCompletionsAdapter:
        assert sent["messages"][-1]["tool_call_id"] == "native-call"
    else:
        assert sent["messages"][-1]["content"][0]["tool_use_id"] == "native-call"
    assert "lawful result" in json.dumps(sent)


@pytest.mark.parametrize("messages", [
    (GenerationMessage("tool", "orphan", tool_call_id="missing"),),
    (GenerationMessage("assistant", "", (ToolCall("x", TOOL.name, '{"q":"x"}'),)),),
    (GenerationMessage("assistant", "", (ToolCall("x", TOOL.name, '{"q":"x"}'),)), GenerationMessage("user", "interleave")),
    (GenerationMessage("user", [{"type": "input_image"}]),),
])
def test_provider_rejects_invalid_history_before_transport(messages):
    instance, transport = adapter(ResponsesAdapter, [])
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(GenerationRequest(messages, 77, tools=(TOOL,))))
    assert transport.requests == []


def test_provider_capabilities_fail_closed_before_transport():
    transport = SyntheticTransport([])
    instance = ResponsesAdapter(connection(ResponsesAdapter.protocol), transport, Capabilities(ResponsesAdapter.protocol, "native-v1"))
    with pytest.raises(ProtocolError, match="memory_tools_unsupported"):
        list(instance.stream_turn(request(tools=(TOOL,))))
    assert transport.requests == []


def test_provider_tool_completion_only_after_valid_terminal_and_schema():
    events = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "native", "function": {"name": TOOL.name, "arguments": '{"q":"x"}'}}]}, "finish_reason": "tool_calls"}]}, "[DONE]"]
    instance, _ = adapter(ChatCompletionsAdapter, events)
    output = list(instance.stream_turn(request(tools=(TOOL,))))
    assert [value for value in output if isinstance(value, ToolCallComplete)] == [ToolCallComplete(ToolCall("native", TOOL.name, '{"q":"x"}'))]
    assert output[-2:] == [Usage(None, None, "unknown"), TurnComplete("tool_calls")]
    for invalid in ('{"q":3}', '{"q":"x","private":true}'):
        events[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = invalid
        output = []
        with pytest.raises(ProtocolError):
            for event in instance.stream_turn(request(tools=(TOOL,))):
                output.append(event)
        assert not any(isinstance(event, (ToolCallComplete, TurnComplete)) for event in output)


@pytest.mark.parametrize("events", [
    [{"choices": [None]}],
    [{"choices": [{"delta": {"tool_calls": [None]}}]}],
    [{"choices": [{"index": True, "delta": {"content": "secret"}, "finish_reason": "stop"}]}, "[DONE]"],
    [{"choices": [{"delta": {"content": "partial"}}]}],
])
def test_provider_malformed_events_are_safe_typed_errors(events):
    instance, transport = adapter(ChatCompletionsAdapter, events)
    with pytest.raises(ProtocolError) as error:
        list(instance.stream_turn(request()))
    assert str(error.value) == "generation_protocol_invalid"
    assert transport.closed


def test_provider_cancellation_closes_transport_without_completion():
    observed = []
    cancelled = [False]
    instance, transport = adapter(ResponsesAdapter, text_events(ResponsesAdapter), cancelled=lambda: cancelled[0], observer=lambda event, **kwargs: observed.append((event, kwargs)))
    stream = instance.stream_turn(request())
    assert isinstance(next(stream), TextDelta)
    cancelled[0] = True
    with pytest.raises(ProtocolError, match="generation_cancelled"):
        list(stream)
    assert transport.closed and observed[-1][1]["error_code"] == "generation_cancelled"
    assert all(event != "completed" for event, _ in observed)


def test_provider_generator_close_cancels_transport():
    instance, transport = adapter(ResponsesAdapter, text_events(ResponsesAdapter))
    stream = instance.stream_turn(request())
    next(stream)
    stream.close()
    assert transport.closed


def test_provider_pre_cancel_and_http_error_do_not_expose_body():
    instance, transport = adapter(ResponsesAdapter, [], cancelled=lambda: True)
    with pytest.raises(ProtocolError, match="generation_cancelled"):
        list(instance.stream_turn(request()))
    assert not transport.requests
    instance, transport = adapter(ResponsesAdapter, [])
    transport.status_code = 401
    with pytest.raises(ProtocolError, match="generation_http_error"):
        list(instance.stream_turn(request()))


def test_provider_responses_final_item_mismatch_rejected():
    events = [{"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "call_id": "x", "name": TOOL.name}}, {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"q":"x"}'}, {"type": "response.function_call_arguments.done", "output_index": 0, "arguments": '{"q":"x"}'}, {"type": "response.completed", "response": {"status": "completed", "output": [{"type": "function_call", "call_id": "WRONG", "name": TOOL.name, "arguments": '{"q":"x"}'}]}}]
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request(tools=(TOOL,))))


def test_provider_anthropic_rejects_content_after_finish():
    events = text_events(AnthropicAdapter)
    events.insert(-1, {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": "late"}})
    instance, _ = adapter(AnthropicAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


def test_provider_optional_responses_done_framing():
    events = text_events(ResponsesAdapter) + ["[DONE]"]
    instance, _ = adapter(ResponsesAdapter, events)
    assert instance.generate(request()) == "first second"
    instance, _ = adapter(ResponsesAdapter, ["[DONE]"])
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


def test_provider_close_after_terminal_stays_completed():
    observed = []
    instance, transport = adapter(ResponsesAdapter, text_events(ResponsesAdapter), observer=lambda event, **kwargs: observed.append(event))
    stream = instance.stream_turn(request())
    for event in stream:
        if isinstance(event, TurnComplete):
            assert transport.closed
            stream.close()
            break
    assert observed == ["started", "completed"]


def test_provider_transport_exit_failure_has_no_success():
    class ExitFailure(SyntheticTransport):
        @contextmanager
        def stream(self, *args, **kwargs):
            yield self
            raise OSError("sensitive transport details")
    transport = ExitFailure(text_events(ResponsesAdapter))
    instance = ResponsesAdapter(connection(ResponsesAdapter.protocol), transport, Capabilities(ResponsesAdapter.protocol, "native-v1"))
    output = []
    with pytest.raises(ProtocolError, match="generation_transport_error"):
        for event in instance.stream_turn(request()):
            output.append(event)
    assert not any(isinstance(event, (TurnComplete, ToolCallComplete)) for event in output)


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_empty_answers_fail(cls):
    instance, _ = adapter(cls, text_events(cls, " \n"))
    with pytest.raises(ProtocolError):
        instance.generate(request())


@pytest.mark.parametrize("schema", [
    '{"type":"object","minimum":1}',
    '{"type":"object","properties":{"q":{"type":"string","items":{"type":"integer"}}}}',
    '{"type":"object","properties":{"q":{"type":"string","maxLength":1.5}}}',
    '{"type":"object","properties":{"q":{"type":"array","items":{"type":"integer"},"maxItems":true}}}',
])
def test_provider_unsupported_schema_rejected_before_transport(schema):
    instance, transport = adapter(ResponsesAdapter, [])
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request(tools=(replace(TOOL, parameters_json=schema),))))
    assert not transport.requests


def test_provider_schema_enum_type_and_negative_number_bounds():
    from citeframe_memory.adapters._schema import check_schema, validate
    schema = {"type": "integer", "minimum": -3, "maximum": 1}
    check_schema(schema)
    validate(-2, schema)
    with pytest.raises(ValueError):
        validate(True, {"type": "boolean", "enum": [1]})


@pytest.mark.parametrize("field,value", [("context_window_tokens", True), ("max_output_tokens", True), ("timeout_seconds", float("nan")), ("timeout_seconds", float("inf"))])
def test_provider_invalid_capacity_preflight(field, value):
    instance, transport = adapter(ResponsesAdapter, [])
    instance.connection = replace(instance.connection, **{field: value})
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))
    assert not transport.requests


def test_provider_total_request_and_schema_limits_before_transport():
    instance, transport = adapter(ResponsesAdapter, [])
    huge = GenerationRequest(tuple(GenerationMessage("user", "x" * 100000) for _ in range(11)), 77)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(huge))
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request(tools=(replace(TOOL, description="x" * 16385),))))
    assert not transport.requests


def test_provider_imports_without_api_or_worker():
    import os
    import subprocess
    import sys
    script = """
import sys
from importlib.abc import MetaPathFinder
class NoApps(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('ai_pdf_api', 'ai_pdf_worker')):
            raise AssertionError('application import forbidden')
sys.meta_path.insert(0, NoApps())
from citeframe_memory.adapters import ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter, PayloadTokenCounter
assert not any(name.startswith(('ai_pdf_api', 'ai_pdf_worker')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=os.environ.copy(), check=False)
    assert result.returncode == 0, result.stderr


def test_provider_parallel_native_calls_preserve_order_and_ids():
    calls = [{"index": index, "id": f"native-{index}", "function": {"name": TOOL.name, "arguments": '{"q":"x"}'}} for index in (1, 0)]
    events = [{"choices": [{"delta": {"tool_calls": calls}, "finish_reason": "tool_calls"}]}, "[DONE]"]
    instance, _ = adapter(ChatCompletionsAdapter, events)
    output = list(instance.stream_turn(request(tools=(TOOL,))))
    assert [event.call.call_id for event in output if isinstance(event, ToolCallComplete)] == ["native-0", "native-1"]


def test_provider_one_invalid_parallel_call_blocks_all_completions():
    calls = [{"index": index, "id": f"native-{index}", "function": {"name": TOOL.name, "arguments": args}} for index, args in ((0, '{"q":"x"}'), (1, '{"q":false}'))]
    instance, _ = adapter(ChatCompletionsAdapter, [{"choices": [{"delta": {"tool_calls": calls}, "finish_reason": "tool_calls"}]}, "[DONE]"])
    output = []
    with pytest.raises(ProtocolError):
        for event in instance.stream_turn(request(tools=(TOOL,))):
            output.append(event)
    assert not any(isinstance(event, (ToolCallComplete, TurnComplete)) for event in output)


def test_provider_responses_final_message_cannot_replace_function():
    events = [{"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "call_id": "x", "name": TOOL.name}}, {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"q":"x"}'}, {"type": "response.function_call_arguments.done", "output_index": 0, "arguments": '{"q":"x"}'}, {"type": "response.completed", "response": {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "wrong"}]}]}}]
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request(tools=(TOOL,))))


@pytest.mark.parametrize("cls", [ResponsesAdapter, AnthropicAdapter])
def test_provider_parallel_fragmented_tools(cls):
    if cls == ResponsesAdapter:
        events = [{"type": "response.output_item.added", "output_index": index, "item": {"type": "function_call", "call_id": f"native-{index}", "name": TOOL.name, "arguments": ""}} for index in (1, 0)]
        for fragment in ('{"q":', '"x"}'):
            events += [{"type": "response.function_call_arguments.delta", "output_index": index, "delta": fragment} for index in (1, 0)]
        events += [{"type": "response.function_call_arguments.done", "output_index": index, "arguments": '{"q":"x"}'} for index in (1, 0)]
        events += [{"type": "response.completed", "response": {"status": "completed"}}]
    else:
        events = [{"type": "message_start", "message": {}}]
        events += [{"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": f"native-{index}", "name": TOOL.name, "input": {}}} for index in (1, 0)]
        for fragment in ('{"q":', '"x"}'):
            events += [{"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": fragment}} for index in (1, 0)]
        events += [{"type": "content_block_stop", "index": index} for index in (1, 0)]
        events += [{"type": "message_delta", "delta": {"stop_reason": "tool_use"}}, {"type": "message_stop"}]
    instance, _ = adapter(cls, events)
    output = list(instance.stream_turn(request(tools=(TOOL,))))
    assert [event.call.call_id for event in output if isinstance(event, ToolCallComplete)] == ["native-0", "native-1"]
    assert output[-1] == TurnComplete("tool_calls")


@pytest.mark.parametrize("result_ids", [("a",), ("a", "a"), ("a", "wrong")])
def test_provider_parallel_history_requires_all_exact_results(result_ids):
    calls = tuple(ToolCall(key, TOOL.name, '{"q":"x"}') for key in ("a", "b"))
    messages = (GenerationMessage("assistant", "", calls),) + tuple(GenerationMessage("tool", "result", tool_call_id=key) for key in result_ids)
    instance, transport = adapter(ResponsesAdapter, [])
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(GenerationRequest(messages, 77, tools=(TOOL,))))
    assert not transport.requests


@pytest.mark.parametrize("usage", [{"input_tokens": -1}, {"output_tokens": True}, {"input_tokens": "5"}])
def test_provider_invalid_reported_usage_rejected(usage):
    events = text_events(ResponsesAdapter)
    events[-1]["response"]["usage"] = usage
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


def test_provider_partial_usage_does_not_invent_missing_tokens():
    events = text_events(ResponsesAdapter)
    events[-1]["response"]["usage"] = {"input_tokens": 5}
    instance, _ = adapter(ResponsesAdapter, events)
    assert Usage(5, None, "reported") in list(instance.stream_turn(request()))


def test_provider_output_reserve_must_leave_input_room():
    instance, transport = adapter(ResponsesAdapter, [])
    instance.connection = replace(instance.connection, context_window_tokens=77)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))
    assert not transport.requests



@pytest.mark.parametrize("terminal", [
    {"output": [{"type": "message", "content": [{"type": "output_text", "text": "wrong"}]}]},
    {"output_text": "wrong"},
    {"output": []},
])
def test_provider_responses_terminal_text_must_match_deltas(terminal):
    events = text_events(ResponsesAdapter)
    events[-1]["response"].update(terminal)
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


def test_provider_responses_matching_terminal_text():
    events = text_events(ResponsesAdapter)
    events[-1]["response"].update({
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "first"},
            {"type": "text", "text": " second"},
        ]}],
        "output_text": "first second",
    })
    instance, _ = adapter(ResponsesAdapter, events)
    assert instance.generate(request()) == "first second"


def test_provider_responses_terminal_text_cannot_replace_missing_deltas():
    instance, _ = adapter(ResponsesAdapter, [{"type": "response.completed", "response": {
        "status": "completed", "output_text": "unstreamed answer",
    }}])
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


@pytest.mark.parametrize("start,delta,total", [
    ({"input_tokens": 10}, {"output_tokens": 2}, 10),
    ({"input_tokens": 10, "cache_read_input_tokens": 1000}, {"output_tokens": 2}, 1010),
    ({"input_tokens": 10, "cache_creation_input_tokens": 500}, {"output_tokens": 2}, 510),
    ({"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500}, {"output_tokens": 2}, 1510),
    ({"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500}, {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500, "output_tokens": 2}, 1510),
    ({"input_tokens": 10, "cache_read_input_tokens": 1000}, {"cache_read_input_tokens": 1200, "output_tokens": 2}, 1210),
    ({"cache_read_input_tokens": 1000}, {"output_tokens": 2}, None),
    ({"input_tokens": None, "cache_read_input_tokens": 1000}, {"output_tokens": 2}, None),
    ({"input_tokens": 10, "cache_read_input_tokens": None}, {"output_tokens": 2}, None),
    ({}, {"output_tokens": 2}, None),
])
def test_provider_anthropic_total_input_usage(start, delta, total):
    events = text_events(AnthropicAdapter)
    events[0]["message"]["usage"] = start
    events[-2]["usage"] = delta
    instance, _ = adapter(AnthropicAdapter, events)
    assert Usage(total, 2, "reported") in list(instance.stream_turn(request()))


def test_provider_anthropic_all_usage_unknown():
    events = text_events(AnthropicAdapter)
    events[0]["message"]["usage"] = {"input_tokens": None}
    events[-2]["usage"] = {"output_tokens": None}
    instance, _ = adapter(AnthropicAdapter, events)
    assert Usage(None, None, "unknown") in list(instance.stream_turn(request()))


def responses_identified_tool_events():
    item = {"type": "function_call", "id": "item_A", "call_id": "call_A", "name": TOOL.name, "arguments": ""}
    final = dict(item, arguments='{"q":"x"}', status="completed")
    return [
        {"type": "response.output_item.added", "output_index": 0, "item": item},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "item_A", "delta": '{"q":'},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "item_A", "delta": '"x"}'},
        {"type": "response.function_call_arguments.done", "output_index": 0, "item_id": "item_A", "arguments": '{"q":"x"}'},
        {"type": "response.output_item.done", "output_index": 0, "item": final},
        {"type": "response.completed", "response": {"status": "completed", "output": [final]}},
    ]


def test_provider_responses_identified_fragmented_tool():
    instance, _ = adapter(ResponsesAdapter, responses_identified_tool_events())
    output = list(instance.stream_turn(request(tools=(TOOL,))))
    assert ToolCallComplete(ToolCall("call_A", TOOL.name, '{"q":"x"}')) in output
    assert output[-1] == TurnComplete("tool_calls")


@pytest.mark.parametrize("position", [1, 3, 4, 5])
def test_provider_responses_rejects_mismatched_native_item_ids(position):
    events = responses_identified_tool_events()
    if position < 4:
        events[position]["item_id"] = "item_B"
    elif position == 4:
        events[position]["item"] = dict(events[position]["item"], id="item_B")
    else:
        events[position]["response"]["output"] = [dict(events[position]["response"]["output"][0], id="item_B")]
    instance, _ = adapter(ResponsesAdapter, events)
    output = []
    with pytest.raises(ProtocolError):
        for event in instance.stream_turn(request(tools=(TOOL,))):
            output.append(event)
    assert not any(isinstance(event, (ToolCallComplete, TurnComplete)) for event in output)


@pytest.mark.parametrize("position", [4, 5])
def test_provider_responses_rejects_incomplete_final_function(position):
    events = responses_identified_tool_events()
    if position == 4:
        events[4]["item"] = dict(events[4]["item"], status="incomplete")
    else:
        events[5]["response"]["output"] = [dict(events[5]["response"]["output"][0], status="incomplete")]
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request(tools=(TOOL,))))


def test_provider_responses_rejects_contradictory_completed_response():
    events = text_events(ResponsesAdapter)
    events[-1]["response"]["incomplete_details"] = {"reason": "max_output_tokens"}
    instance, _ = adapter(ResponsesAdapter, events)
    with pytest.raises(ProtocolError):
        list(instance.stream_turn(request()))


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_redirects_disabled_with_permissive_httpx_client(cls):
    import httpx
    requests = []

    def handler(incoming):
        requests.append(incoming)
        if incoming.url.host == "first.test":
            return httpx.Response(307, headers={"location": "https://second.test/endpoint"})
        body = "".join("data: " + (event if isinstance(event, str) else json.dumps(event)) + "\n\n" for event in text_events(cls))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as transport:
        instance = cls(replace(connection(cls.protocol), endpoint="https://first.test/endpoint"), transport, Capabilities(cls.protocol, "native-v1"))
        output = []
        with pytest.raises(ProtocolError, match="generation_http_error"):
            for event in instance.stream_turn(request()):
                output.append(event)
    assert [incoming.url.host for incoming in requests] == ["first.test"]
    assert not any(isinstance(event, TurnComplete) for event in output)



@pytest.mark.parametrize("status", ["incomplete", "failed", "in_progress"])
@pytest.mark.parametrize("position", ["item_done", "response_output"])
def test_provider_responses_rejects_noncompleted_message_item(status, position):
    item = {"type": "message", "id": "message_A", "role": "assistant",
            "status": status, "content": [{"type": "output_text", "text": "partial"}]}
    events = [{"type": "response.output_text.delta", "delta": "partial"}]
    if position == "item_done":
        events.append({"type": "response.output_item.done", "output_index": 0, "item": item})
        events.append({"type": "response.completed", "response": {"status": "completed"}})
    else:
        events.append({"type": "response.completed", "response": {"status": "completed", "output": [item]}})
    instance, _ = adapter(ResponsesAdapter, events)
    output = []
    with pytest.raises(ProtocolError):
        for event in instance.stream_turn(request()):
            output.append(event)
    assert not any(isinstance(event, (ToolCallComplete, TurnComplete)) for event in output)


@pytest.mark.parametrize("status", [None, "completed"])
def test_provider_responses_accepts_completed_or_unspecified_message_status(status):
    item = {"type": "message", "id": "message_A", "role": "assistant",
            "content": [{"type": "output_text", "text": "answer"}]}
    if status is not None:
        item["status"] = status
    events = [
        {"type": "response.output_text.delta", "delta": "answer"},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"status": "completed", "output": [item]}},
    ]
    instance, _ = adapter(ResponsesAdapter, events)
    assert instance.generate(request()) == "answer"


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
@pytest.mark.parametrize("stage", ["started", "completed"])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, ProtocolError])
def test_provider_observer_failure_has_stable_safe_boundary(cls, stage, error_type):
    import traceback
    sentinel = "synthetic-observer-private-diagnostic"
    observed = []

    def observer(event, **kwargs):
        observed.append((event, kwargs["error_code"]))
        if event in {stage, "failed"}:
            raise error_type(sentinel)

    instance, transport = adapter(cls, text_events(cls), observer=observer)
    emitted = []
    with pytest.raises(ProtocolError, match="^generation_observer_error$") as error:
        for event in instance.stream_turn(request()):
            emitted.append(event)
    assert not any(isinstance(event, TurnComplete) for event in emitted)
    assert observed[-1] == ("failed", "generation_observer_error")
    assert (not transport.requests) if stage == "started" else transport.closed
    assert not sentinel in "".join(traceback.format_exception(error.value)), "Observer diagnostic escaped"


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
@pytest.mark.parametrize("failure", ["transport", "protocol", "cancelled", "generator_close"])
def test_provider_failed_observer_preserves_primary_failure_and_cleanup(cls, failure):
    observed = []

    def observer(event, **kwargs):
        observed.append((event, kwargs["error_code"]))
        if event == "failed":
            raise RuntimeError("synthetic-failed-observer-diagnostic")

    instance, transport = adapter(cls, [] if failure == "protocol" else text_events(cls), observer=observer)
    if failure == "transport":
        def broken_lines():
            raise OSError("synthetic-transport-diagnostic")
            yield
        transport.iter_lines = broken_lines
    if failure == "cancelled":
        instance.cancelled = lambda: transport.closed
    stream = instance.stream_turn(request())
    emitted = []
    if failure == "generator_close":
        assert isinstance(next(stream), TextDelta)
        stream.close()
        code = "generation_cancelled"
    else:
        code = {"transport": "generation_transport_error", "protocol": "generation_protocol_invalid", "cancelled": "generation_cancelled"}[failure]
        with pytest.raises(ProtocolError) as error:
            for event in stream:
                emitted.append(event)
        assert str(error.value) == code
    assert transport.closed
    assert observed[-1] == ("failed", code)
    assert not any(isinstance(event, TurnComplete) for event in emitted)


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_observer_close_after_terminal_stays_completed(cls):
    observed = []

    def observer(event, **kwargs):
        observed.append(event)
        if event == "failed":
            raise RuntimeError("synthetic-failed-observer-diagnostic")

    instance, transport = adapter(cls, text_events(cls), observer=observer)
    stream = instance.stream_turn(request())
    for event in stream:
        if isinstance(event, TurnComplete):
            stream.close()
            break
    assert transport.closed and observed == ["started", "completed"]


def native_tool_batch(cls, calls):
    events = [] if cls != AnthropicAdapter else [{"type": "message_start", "message": {}}]
    for index, (call_id, name, arguments) in enumerate(calls):
        if cls == ResponsesAdapter:
            events.extend([
                {"type": "response.output_item.added", "output_index": index, "item": {"type": "function_call", "call_id": call_id, "name": name}},
                {"type": "response.function_call_arguments.delta", "output_index": index, "delta": arguments},
                {"type": "response.function_call_arguments.done", "output_index": index, "arguments": arguments},
            ])
        elif cls == ChatCompletionsAdapter:
            events.append({"choices": [{"delta": {"tool_calls": [{"index": index, "id": call_id, "function": {"name": name, "arguments": arguments}}]}, "finish_reason": None}]})
        else:
            events.extend([
                {"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}}},
                {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": arguments}},
                {"type": "content_block_stop", "index": index},
            ])
    if cls == ResponsesAdapter:
        events.append({"type": "response.completed", "response": {"status": "completed"}})
    elif cls == ChatCompletionsAdapter:
        events.extend([{"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, "[DONE]"])
    else:
        events.extend([{"type": "message_delta", "delta": {"stop_reason": "tool_use"}}, {"type": "message_stop"}])
    return events


NUMERIC_TOOL = ToolDefinition("numbers", "Synthetic numbers", '{"type":"object","properties":{"values":{"type":"array","items":{"type":"number"}}},"required":["values"],"additionalProperties":false}')


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
@pytest.mark.parametrize("invalid", ["expanded_number", "high_surrogate", "low_surrogate"])
@pytest.mark.parametrize("valid_first", [True, False])
def test_provider_rejects_entire_canonical_batch_before_any_completed_call(cls, invalid, valid_first):
    from citeframe_memory.adapters._wire import WireLimits
    if invalid == "expanded_number":
        arguments, name = '{"values":[' + ','.join(['1e9'] * 1500) + ']}', NUMERIC_TOOL.name
    else:
        arguments, name = json.dumps({"q": chr(0xd800 if invalid == "high_surrogate" else 0xdc00)}), TOOL.name
    assert len(arguments.encode("utf-8")) <= WireLimits().max_argument_bytes
    calls = [("valid-call", TOOL.name, '{"q":"valid"}'), ("invalid-call", name, arguments)]
    if not valid_first:
        calls.reverse()
    instance, transport = adapter(cls, native_tool_batch(cls, calls))
    emitted = []
    with pytest.raises(ProtocolError, match="^generation_protocol_invalid$"):
        for event in instance.stream_turn(request(tools=(TOOL, NUMERIC_TOOL))):
            emitted.append(event)
    assert transport.closed
    assert not any(isinstance(event, (ToolCallComplete, Usage, TurnComplete)) for event in emitted)


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
@pytest.mark.parametrize("limit_delta", [-1, 0])
def test_provider_canonical_numeric_utf8_byte_boundary(cls, limit_delta):
    from citeframe_memory.adapters._wire import WireLimits
    from citeframe_memory.chat_loop.turns import collect_turn
    raw = '{"values":[' + ','.join(['1e9'] * 20) + ']}'
    canonical = '{"values":[' + ','.join(['1000000000.0'] * 20) + ']}'
    limit = len(canonical.encode("utf-8")) + limit_delta
    assert len(raw.encode("utf-8")) <= limit
    instance, transport = adapter(cls, native_tool_batch(cls, [("numeric-call", NUMERIC_TOOL.name, raw)]), limits=WireLimits(max_argument_bytes=limit))
    req = request(tools=(NUMERIC_TOOL,))
    emitted = []
    if limit_delta < 0:
        with pytest.raises(ProtocolError, match="^generation_protocol_invalid$"):
            for event in instance.stream_turn(req):
                emitted.append(event)
        assert not any(isinstance(event, (ToolCallComplete, TurnComplete)) for event in emitted)
    else:
        turn = collect_turn(instance.stream_turn(req), req)
        assert turn.calls == (ToolCall("numeric-call", NUMERIC_TOOL.name, canonical),)
        assert turn.reason == "tool_calls"
    assert transport.closed


@pytest.mark.parametrize("cls", [ResponsesAdapter, ChatCompletionsAdapter, AnthropicAdapter])
def test_provider_valid_unicode_numeric_batch_preserves_ids_order_and_collector_parity(cls):
    from citeframe_memory.adapters._wire import WireLimits
    from citeframe_memory.chat_loop.turns import collect_turn
    canonical = json.dumps({"q": "é猫" * 50}, ensure_ascii=False, separators=(",", ":"))
    calls = [("first-call", TOOL.name, canonical), ("second-call", NUMERIC_TOOL.name, '{"values":[1e2]}')]
    limit = max(len(canonical.encode("utf-8")), len('{"values":[100.0]}'.encode("utf-8")))
    instance, transport = adapter(cls, native_tool_batch(cls, calls), limits=WireLimits(max_argument_bytes=limit))
    req = request(tools=(TOOL, NUMERIC_TOOL))
    turn = collect_turn(instance.stream_turn(req), req)
    assert turn.calls == (ToolCall("first-call", TOOL.name, canonical), ToolCall("second-call", NUMERIC_TOOL.name, '{"values":[100.0]}'))
    assert transport.closed and turn.reason == "tool_calls"
