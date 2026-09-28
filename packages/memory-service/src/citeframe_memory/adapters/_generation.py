"""Provider generation against injected transport and immutable connection config."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from citeframe_contracts.memory import (
    GenerationEvent, GenerationObserver, GenerationRequest, HTTPTransport,
    ModelConnectionSnapshot, ProtocolError, TextDelta, ToolCall, ToolCallComplete,
    ToolCallDelta, TurnComplete, Usage,
)

from ._requests import payload, prepare
from ._schema import validate
from ._streams import ResponsesState
from ._wire import WireLimits, sse_events


@dataclass(frozen=True)
class Capabilities:
    protocol: str
    adapter_version: str
    supports_tools: bool = False
    supports_streaming_tools: bool = False
    supports_cancellation: bool = False


class NativeGenerationAdapter:
    protocol = ""
    adapter_version = "native-v1"
    state_type = ResponsesState

    def __init__(self, connection: ModelConnectionSnapshot, transport: HTTPTransport,
                 capabilities: Capabilities, *, limits: WireLimits = WireLimits(),
                 cancelled: Callable[[], bool] | None = None,
                 observer: GenerationObserver | None = None):
        self.connection = connection
        self.transport = transport
        self.capabilities = capabilities
        self.limits = limits
        self.cancelled = cancelled
        self.observer = observer

    def _observe(self, event, code=None):
        if self.observer is not None:
            self.observer(event, config_fingerprint=self.connection.config_fingerprint, error_code=code)

    def _cancel(self):
        if self.cancelled is not None and self.cancelled():
            raise ProtocolError("generation_cancelled")

    def stream_turn(self, request: GenerationRequest) -> Iterator[GenerationEvent]:
        import json
        try:
            caps = self.capabilities
            if self.connection.protocol != self.protocol or caps.protocol != self.protocol or caps.adapter_version != self.adapter_version:
                raise ProtocolError("generation_capability_mismatch")
            if request.tools and not (caps.supports_tools is True and caps.supports_streaming_tools is True):
                raise ProtocolError("memory_tools_unsupported")
            if self.cancelled is not None and caps.supports_cancellation is not True:
                raise ProtocolError("generation_cancellation_unsupported")
            definitions = prepare(request, self.connection, self.limits)
            wire = payload(request, self.connection)
            self._cancel()
            headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
            if not isinstance(self.connection.api_key, str) or not self.connection.api_key.strip():
                raise ProtocolError("generation_not_configured")
            if self.protocol == "anthropic":
                headers.update({"x-api-key": self.connection.api_key, "anthropic-version": "2023-06-01"})
            else:
                headers["Authorization"] = "Bearer " + self.connection.api_key
            state = self.state_type(self.limits)
            self._observe("started")
            with self.transport.stream("POST", self.connection.endpoint, headers=headers, json=wire, timeout=self.connection.timeout_seconds, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ProtocolError("generation_http_error")
                for event in sse_events(response.iter_lines(), self.limits):
                    self._cancel()
                    before = {key: value.copy() for key, value in state.calls.calls.items()}
                    text = state.feed(event)
                    for index, call in state.calls.calls.items():
                        self._cancel()
                        previous = before.get(index, {"id": "", "name": "", "arguments": ""})
                        args = call["arguments"][len(previous["arguments"]):]
                        call_id = call["id"][len(previous["id"]):]
                        name = call["name"][len(previous["name"]):]
                        if args or call_id or name:
                            yield ToolCallDelta(index=index, arguments_delta=args, call_id=call_id or None, name=name or None)
                    if text:
                        self._cancel()
                        yield TextDelta(text)
                self._cancel()
                _, calls, usage = state.result(require_done=self.protocol != "openai_chat_completions")
                for call_id, name, arguments in calls:
                    if name not in definitions:
                        raise ProtocolError("generation_unknown_tool")
                    validate(arguments, definitions[name])
            self._cancel()
            for call_id, name, arguments in calls:
                self._cancel()
                yield ToolCallComplete(ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), allow_nan=False)))
            self._cancel()
            yield Usage(usage.get("input_tokens"), usage.get("output_tokens"), "reported" if usage else "unknown")
            self._cancel()
            self._observe("completed")
        except GeneratorExit:
            self._observe("failed", "generation_cancelled")
            raise
        except ProtocolError as exc:
            self._observe("failed", str(exc))
            raise
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, UnicodeError):
            self._observe("failed", "generation_protocol_invalid")
            raise ProtocolError("generation_protocol_invalid") from None
        except Exception:
            self._observe("failed", "generation_transport_error")
            raise ProtocolError("generation_transport_error") from None
        yield TurnComplete(state.reason)

    def generate(self, request: GenerationRequest) -> str:
        chunks = []
        for event in self.stream_turn(request):
            if isinstance(event, TextDelta):
                chunks.append(event.text)
            elif isinstance(event, TurnComplete) and event.reason != "answer":
                raise ProtocolError("generation_answer_required")
        return "".join(chunks).strip()
