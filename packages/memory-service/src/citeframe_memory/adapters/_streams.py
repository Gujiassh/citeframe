"""Native streaming state machines. No provider text is interpreted as a tool."""

from ._wire import CallBuffer, WireLimits, bounded_text


class StreamState:
    def __init__(self, limits: WireLimits):
        self.limits = limits
        self.calls = CallBuffer(limits)
        self.text = ""
        self.terminal = False
        self.usage = {}
        self.reason = None
        self.events = 0
        self.bytes = 0

    def guard(self, event):
        import json
        self.events += 1
        self.bytes += len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
        if self.events > self.limits.max_events or self.bytes > self.limits.max_text_bytes:
            raise ValueError("provider turn limit exceeded")
        if self.terminal:
            raise ValueError("event after terminal marker")
        if not isinstance(event, dict):
            raise ValueError("invalid provider event")

    def delta(self, value):
        value = bounded_text(value, self.limits.max_text_bytes, "text delta")
        self.text = bounded_text(self.text + value, self.limits.max_text_bytes, "turn text")
        return value

    def set_usage(self, value, input_key="input_tokens", output_key="output_tokens"):
        if not isinstance(value, dict):
            raise ValueError("invalid usage")
        for wire_key, key in ((input_key, "input_tokens"), (output_key, "output_tokens")):
            if wire_key in value:
                number = value[wire_key]
                if type(number) is not int or number < 0:
                    raise ValueError("invalid usage count")
                self.usage[key] = number

    def result(self, *, require_done=False):
        if not self.terminal:
            raise ValueError("incomplete provider turn")
        calls = self.calls.complete(require_done=require_done)
        if self.reason == "tool_calls" and not calls:
            raise ValueError("tool terminal without calls")
        if self.reason == "answer" and calls:
            raise ValueError("answer terminal with calls")
        if not calls and not self.text.strip():
            raise ValueError("empty provider answer")
        return self.text, calls, self.usage


class ChatState(StreamState):
    def feed(self, event):
        if event == "[DONE]":
            if self.reason is None:
                raise ValueError("missing finish reason")
            if self.terminal:
                raise ValueError("duplicate terminal")
            self.terminal = True
            return None
        self.guard(event)
        if event.get("error"):
            raise ValueError("provider error")
        if event.get("usage") is not None:
            self.set_usage(event["usage"], "prompt_tokens", "completion_tokens")
        choices = event.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError("invalid choices")
        if not choices:
            if event.get("usage") is None:
                raise ValueError("missing choice")
            return None
        choice = choices[0]
        if type(choice.get("index", 0)) is not int or choice.get("index", 0) != 0 or self.reason is not None:
            raise ValueError("invalid choice index or repeated finish")
        delta = choice.get("delta", {})
        if not isinstance(delta, dict) or delta.get("refusal") or delta.get("function_call"):
            raise ValueError("unsupported or refused delta")
        for call in delta.get("tool_calls", []):
            index = call.get("index")
            if type(index) is not int or index < 0:
                raise ValueError("invalid tool index")
            if call.get("type", "function") != "function":
                raise ValueError("unsupported tool type")
            if index not in self.calls.calls:
                self.calls.start(index)
            function = call.get("function", {})
            self.calls.append(index, call_id=call.get("id", ""), name=function.get("name", ""), arguments=function.get("arguments", ""))
        reason = choice.get("finish_reason")
        if reason is not None:
            if reason not in {"stop", "tool_calls"}:
                raise ValueError("incomplete or refused finish reason")
            self.reason = "tool_calls" if reason == "tool_calls" else "answer"
        text = delta.get("content")
        return self.delta(text) if text is not None else None


class ResponsesState(StreamState):
    def __init__(self, limits):
        super().__init__(limits)
        self.framing_done = False
        self.item_ids = {}

    def check_item_id(self, key, item_id):
        if item_id is not None:
            bounded_text(item_id, self.limits.max_id_bytes, "item ID", empty=False)
            if self.item_ids.get(key) != item_id:
                raise ValueError("response item identity mismatch")

    def reconcile_item(self, item, key):
        if item.get("type") == "function_call":
            self.check_item_id(key, item.get("id"))
            if item.get("status", "completed") != "completed":
                raise ValueError("incomplete final function item")
            call = self.calls.calls.get(key)
            if call is None or item.get("call_id") != call["id"] or item.get("name") != call["name"] or item.get("arguments") != call["arguments"]:
                raise ValueError("tool final item mismatch")
        elif item.get("type") == "message":
            if item.get("status", "completed") != "completed":
                raise ValueError("incomplete final message item")
            for part in item.get("content", []):
                if part.get("type") not in {"output_text", "text"}:
                    raise ValueError("unsupported final message content")
        elif item.get("type") != "reasoning":
            raise ValueError("unsupported final response item")

    def feed(self, event):
        if event == "[DONE]":
            if not self.terminal or self.framing_done:
                raise ValueError("premature or duplicate framing sentinel")
            self.framing_done = True
            return None
        self.guard(event)
        kind = event.get("type")
        if kind == "response.output_text.delta":
            return self.delta(event.get("delta"))
        if kind == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                item_id = item.get("id")
                if item_id is not None:
                    bounded_text(item_id, self.limits.max_id_bytes, "item ID", empty=False)
                    if item_id in self.item_ids.values():
                        raise ValueError("duplicate response item ID")
                self.item_ids[event["output_index"]] = item_id
                self.calls.start(event["output_index"], item.get("call_id", ""), item.get("name", ""))
                self.calls.append(event["output_index"], arguments=item.get("arguments", ""))
            elif item.get("type") not in {"message", "reasoning"}:
                raise ValueError("unsupported response item")
        elif kind == "response.function_call_arguments.delta":
            self.check_item_id(event["output_index"], event.get("item_id"))
            self.calls.append(event["output_index"], arguments=event.get("delta"))
        elif kind == "response.function_call_arguments.done":
            key = event["output_index"]
            self.check_item_id(key, event.get("item_id"))
            if key not in self.calls.calls or event.get("arguments") != self.calls.calls[key]["arguments"]:
                raise ValueError("tool arguments completion mismatch")
            self.calls.finish(key)
        elif kind == "response.completed":
            response = event.get("response", {})
            if response.get("incomplete_details") is not None:
                raise ValueError("contradictory incomplete response")
            if "output" in response:
                output = response["output"]
                if not isinstance(output, list):
                    raise ValueError("invalid final output")
                for index, item in enumerate(output):
                    self.reconcile_item(item, index)
                final_calls = {index for index, item in enumerate(output) if item.get("type") == "function_call"}
                if set(self.calls.calls) != final_calls:
                    raise ValueError("missing final call")
                final_text = "".join(
                    bounded_text(part.get("text"), self.limits.max_text_bytes, "final text")
                    for item in output if item.get("type") == "message"
                    for part in item.get("content", [])
                )
                if final_text != self.text:
                    raise ValueError("final response text mismatch")
            if "output_text" in response:
                final_text = bounded_text(response["output_text"], self.limits.max_text_bytes, "final text")
                if final_text != self.text:
                    raise ValueError("final response text mismatch")
            if response.get("status") != "completed":
                raise ValueError("missing completed response status")
            if response.get("usage") is not None:
                self.set_usage(response["usage"])
            self.reason = "tool_calls" if self.calls.calls else "answer"
            self.terminal = True
        elif kind == "response.output_item.done":
            self.reconcile_item(event.get("item", {}), event["output_index"])
        elif kind in {"response.failed", "response.incomplete", "error", "response.refusal.delta", "response.refusal.done"}:
            raise ValueError("incomplete or refused response")
        elif kind not in {"response.created", "response.in_progress", "response.output_item.done", "response.content_part.added", "response.content_part.done", "response.output_text.done", "response.reasoning_summary_part.added", "response.reasoning_summary_part.done", "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done"}:
            raise ValueError("unsupported response event")
        return None


class AnthropicState(StreamState):
    def __init__(self, limits):
        super().__init__(limits)
        self.started = False
        self.blocks = {}
        self.input_usage = {}

    def set_usage(self, value, input_key="input_tokens", output_key="output_tokens"):
        if not isinstance(value, dict):
            raise ValueError("invalid usage")
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            if key in value:
                number = value[key]
                if number is not None and (type(number) is not int or number < 0):
                    raise ValueError("invalid usage count")
                self.input_usage[key] = number
        if "input_tokens" in self.input_usage and all(number is not None for number in self.input_usage.values()):
            self.usage["input_tokens"] = sum(self.input_usage.values())
        else:
            self.usage.pop("input_tokens", None)
        if "output_tokens" in value:
            number = value["output_tokens"]
            if number is None:
                self.usage.pop("output_tokens", None)
            elif type(number) is not int or number < 0:
                raise ValueError("invalid usage count")
            else:
                self.usage["output_tokens"] = number

    def feed(self, event):
        self.guard(event)
        kind = event.get("type")
        if kind == "ping":
            return None
        if kind == "message_start":
            if self.started:
                raise ValueError("duplicate message start")
            self.started = True
            self.set_usage(event.get("message", {}).get("usage", {}))
            return None
        if not self.started:
            raise ValueError("missing message start")
        if self.reason is not None and kind != "message_stop":
            raise ValueError("content after message finish")
        if kind == "content_block_start":
            index = event["index"]
            block = event.get("content_block", {})
            if type(index) is not int or index < 0 or index in self.blocks:
                raise ValueError("invalid block index")
            self.blocks[index] = block.get("type")
            if block.get("type") == "tool_use":
                if block.get("input") != {}:
                    raise ValueError("streamed tool must start with empty input")
                self.calls.start(index, block.get("id", ""), block.get("name", ""))
            elif block.get("type") == "text":
                return self.delta(block.get("text", ""))
            else:
                raise ValueError("unsupported content block")
        elif kind == "content_block_delta":
            index = event["index"]
            delta = event.get("delta", {})
            if self.blocks.get(index) == "text" and delta.get("type") == "text_delta":
                return self.delta(delta.get("text"))
            if self.blocks.get(index) != "tool_use" or delta.get("type") != "input_json_delta":
                raise ValueError("mismatched content delta")
            self.calls.append(index, arguments=delta.get("partial_json"))
        elif kind == "content_block_stop":
            index = event["index"]
            if index not in self.blocks or self.blocks[index] == "closed":
                raise ValueError("unknown or duplicate block stop")
            if self.blocks[index] == "tool_use":
                self.calls.finish(index)
            self.blocks[index] = "closed"
        elif kind == "message_delta":
            if self.reason is not None or any(value != "closed" for value in self.blocks.values()):
                raise ValueError("unfinished blocks or repeated finish")
            reason = event.get("delta", {}).get("stop_reason")
            if reason not in {"end_turn", "stop_sequence", "tool_use"}:
                raise ValueError("incomplete or refused stop reason")
            self.reason = "tool_calls" if reason == "tool_use" else "answer"
            self.set_usage(event.get("usage", {}))
        elif kind == "message_stop":
            if self.reason is None:
                raise ValueError("missing stop reason")
            self.terminal = True
        else:
            raise ValueError("unsupported anthropic event")
        return None
