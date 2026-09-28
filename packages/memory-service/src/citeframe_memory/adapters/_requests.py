"""Serialize complete neutral conversation units into native request payloads."""

import json
import math

from ._schema import schemas, validate
from ._wire import WireLimits, bounded_text, strict_json


def prepare(request, connection, limits=WireLimits()):
    if type(connection.timeout_seconds) not in (int, float) or not math.isfinite(connection.timeout_seconds) or connection.timeout_seconds <= 0:
        raise ValueError("invalid timeout")
    if type(connection.max_output_tokens) is not int or connection.max_output_tokens < 1:
        raise ValueError("invalid model output capacity")
    if not all(isinstance(value, str) and value for value in (connection.model, connection.endpoint, connection.config_fingerprint)):
        raise ValueError("invalid model connection")
    if type(connection.context_window_tokens) is not int or connection.context_window_tokens < 1:
        raise ValueError("unknown model capacity")
    if type(request.max_output_tokens) is not int or not 0 < request.max_output_tokens <= connection.max_output_tokens:
        raise ValueError("invalid output capacity")
    if request.max_output_tokens >= connection.context_window_tokens:
        raise ValueError("output reserve exhausts context capacity")
    if request.purpose not in {"main", "compact_chunk", "compact_merge"} or (request.purpose != "main" and request.tools):
        raise ValueError("invalid generation purpose")
    if len(request.tools) > limits.max_calls:
        raise ValueError("tool definition count limit")
    definitions = schemas(request.tools, limits)
    pending = set()
    seen = set()
    for message in request.messages:
        bounded_text(message.content, limits.max_text_bytes, "message")
        if message.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("unsupported message role")
        if pending and message.role != "tool":
            raise ValueError("incomplete tool result group")
        if message.role == "tool":
            if message.tool_calls or message.tool_call_id not in pending:
                raise ValueError("unmatched tool result")
            pending.remove(message.tool_call_id)
        elif message.tool_call_id is not None:
            raise ValueError("tool result ID on non-tool message")
        if message.tool_calls:
            if message.role != "assistant" or len(message.tool_calls) > limits.max_calls:
                raise ValueError("invalid tool call group")
            for call in message.tool_calls:
                bounded_text(call.call_id, limits.max_id_bytes, "call ID", empty=False)
                bounded_text(call.name, limits.max_id_bytes, "tool name", empty=False)
                bounded_text(call.arguments_json, limits.max_argument_bytes, "tool arguments", empty=False)
                if call.call_id in seen or call.name not in definitions:
                    raise ValueError("duplicate call or unknown tool")
                validate(strict_json(call.arguments_json), definitions[call.name])
                seen.add(call.call_id)
                pending.add(call.call_id)
    if pending or not request.messages:
        raise ValueError("incomplete generation input")
    bounded_text(json.dumps(payload(request, connection), ensure_ascii=False, allow_nan=False), limits.max_text_bytes, "request payload")
    return definitions


def payload(request, connection):
    protocol = connection.protocol
    result = {"model": connection.model, "stream": True}
    if request.temperature is not None:
        if type(request.temperature) not in (int, float) or not 0 <= request.temperature <= 2:
            raise ValueError("invalid temperature")
        result["temperature"] = request.temperature
    if protocol == "openai_responses":
        result["max_output_tokens"] = request.max_output_tokens
        messages = []
        for msg in request.messages:
            if msg.role == "tool":
                messages.append({"type": "function_call_output", "call_id": msg.tool_call_id, "output": msg.content})
            else:
                if msg.content or not msg.tool_calls:
                    messages.append({"role": msg.role, "content": msg.content})
                for call in msg.tool_calls:
                    messages.append({"type": "function_call", "call_id": call.call_id, "name": call.name, "arguments": call.arguments_json})
        result["input"] = messages
        if request.tools:
            result["tools"] = [{"type": "function", "name": tool.name, "description": tool.description, "parameters": strict_json(tool.parameters_json)} for tool in request.tools]
    elif protocol == "openai_chat_completions":
        result["max_tokens"] = request.max_output_tokens
        result["stream_options"] = {"include_usage": True}
        messages = []
        for msg in request.messages:
            mapped = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id is not None:
                mapped["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                mapped["tool_calls"] = [{"id": call.call_id, "type": "function", "function": {"name": call.name, "arguments": call.arguments_json}} for call in msg.tool_calls]
            messages.append(mapped)
        result["messages"] = messages
        if request.tools:
            result["tools"] = [{"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": strict_json(tool.parameters_json)}} for tool in request.tools]
    elif protocol == "anthropic":
        result["max_tokens"] = request.max_output_tokens
        system = [msg.content for msg in request.messages if msg.role == "system"]
        if system:
            result["system"] = "\n\n".join(system).strip()
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                block = {"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": msg.content}
                if messages and messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list) and all(item["type"] == "tool_result" for item in messages[-1]["content"]):
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
                continue
            content = msg.content
            if msg.tool_calls:
                content = ([{"type": "text", "text": msg.content}] if msg.content else []) + [{"type": "tool_use", "id": call.call_id, "name": call.name, "input": strict_json(call.arguments_json)} for call in msg.tool_calls]
            messages.append({"role": msg.role, "content": content})
        result["messages"] = messages
        if request.tools:
            result["tools"] = [{"name": tool.name, "description": tool.description, "input_schema": strict_json(tool.parameters_json)} for tool in request.tools]
    else:
        raise ValueError("unsupported protocol")
    return result


def serialized(request, connection):
    prepare(request, connection)
    return json.dumps(payload(request, connection), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
