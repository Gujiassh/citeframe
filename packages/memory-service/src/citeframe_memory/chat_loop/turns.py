"""Collect typed provider turns and propose continuations that still require a gate.

Provider adapters own wire parsing and argument-schema validation. These helpers
own no authorization, dispatch, publication, journal or budget state.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
import json
from typing import Literal

from citeframe_contracts.memory import (
    GenerationEvent, GenerationMessage, GenerationRequest, ProtocolError,
    TextDelta, ToolCall, ToolCallComplete, ToolCallDelta, TurnComplete, Usage,
)


@dataclass(frozen=True)
class TurnLimits:
    max_events: int = 10000
    max_bytes: int = 1048576
    max_calls: int = 16
    max_argument_bytes: int = 16384
    max_identity_bytes: int = 255

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("invalid_turn_limits")


@dataclass(frozen=True)
class CollectedTurn:
    reason: Literal["answer", "tool_calls"]
    text: str
    calls: tuple[ToolCall, ...]
    usage: Usage


@dataclass(frozen=True)
class TurnIdentity:
    execution_id: str
    root_id: str
    call_id: str


@dataclass(frozen=True)
class ToolOutcome:
    call_id: str
    status: Literal["completed", "failed", "cancelled", "pending", "unknown"]
    content: str | None = None


@dataclass(frozen=True)
class ContinuationDecision:
    action: Literal["gate_required", "stop"]
    identity: TurnIdentity
    outcomes: tuple[ToolOutcome, ...]
    request: GenerationRequest | None = None
    stop_reason: str | None = None


def _size(value, limit):
    if not isinstance(value, str):
        raise ProtocolError("chat_turn_invalid_text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise ProtocolError("chat_turn_invalid_text") from None
    if size > limit:
        raise ProtocolError("chat_turn_limit_exceeded")
    return size


def _identity(value, limits):
    size = _size(value, limits.max_identity_bytes)
    if not value:
        raise ProtocolError("chat_turn_missing_identity")
    return size


def _cancel(check):
    if check is not None and check():
        raise ProtocolError("chat_turn_cancelled")


def collect_turn(events: Iterable[GenerationEvent], request: GenerationRequest, *,
                 limits: TurnLimits = TurnLimits(),
                 cancelled: Callable[[], bool] | None = None) -> CollectedTurn:
    """Return only after terminal validation and successful iterator exhaustion."""
    text = []
    calls = []
    ids = set()
    fragments = {}
    usage = None
    reason = None
    size = 0
    allowed = {tool.name for tool in request.tools}
    if len(allowed) != len(request.tools):
        raise ProtocolError("chat_turn_duplicate_tool_definition")
    _cancel(cancelled)
    iterator = iter(events)
    try:
        for count, event in enumerate(iterator, 1):
            _cancel(cancelled)
            if count > limits.max_events:
                raise ProtocolError("chat_turn_limit_exceeded")
            if reason is not None:
                raise ProtocolError("chat_turn_event_after_terminal")
            if isinstance(event, TextDelta):
                size += _size(event.text, limits.max_bytes)
                text.append(event.text)
            elif isinstance(event, ToolCallDelta):
                if calls or type(event.index) is not int or event.index < 0:
                    raise ProtocolError("chat_turn_invalid_delta")
                if event.index not in fragments:
                    if len(fragments) >= limits.max_calls:
                        raise ProtocolError("chat_turn_limit_exceeded")
                    fragments[event.index] = ["", "", 0]
                fragment = fragments[event.index]
                for offset, value in enumerate((event.call_id, event.name)):
                    if value is not None:
                        size += _size(value, limits.max_identity_bytes)
                        fragment[offset] += value
                        _size(fragment[offset], limits.max_identity_bytes)
                arg_size = _size(event.arguments_delta, limits.max_argument_bytes)
                fragment[2] += arg_size
                size += arg_size
                if fragment[2] > limits.max_argument_bytes:
                    raise ProtocolError("chat_turn_limit_exceeded")
            elif isinstance(event, ToolCallComplete):
                call = event.call
                if not isinstance(call, ToolCall) or call.call_id in ids:
                    raise ProtocolError("chat_turn_duplicate_or_invalid_call")
                size += _identity(call.call_id, limits)
                size += _identity(call.name, limits)
                size += _size(call.arguments_json, limits.max_argument_bytes)
                if not call.arguments_json or call.name not in allowed:
                    raise ProtocolError("chat_turn_undeclared_call")
                if len(calls) >= limits.max_calls:
                    raise ProtocolError("chat_turn_limit_exceeded")
                if fragments:
                    ordered = sorted(fragments)
                    if len(calls) >= len(ordered):
                        raise ProtocolError("chat_turn_call_set_mismatch")
                    call_id, name, _ = fragments[ordered[len(calls)]]
                    if (call_id and call_id != call.call_id) or (name and name != call.name):
                        raise ProtocolError("chat_turn_call_identity_mismatch")
                ids.add(call.call_id)
                calls.append(call)
            elif isinstance(event, Usage):
                if usage is not None or event.source not in {"reported", "estimated", "unknown"}:
                    raise ProtocolError("chat_turn_invalid_usage")
                for value in (event.input_tokens, event.output_tokens):
                    if value is not None and (type(value) is not int or value < 0):
                        raise ProtocolError("chat_turn_invalid_usage")
                usage = event
            elif isinstance(event, TurnComplete):
                if event.reason not in {"answer", "tool_calls"}:
                    raise ProtocolError("chat_turn_invalid_terminal")
                reason = event.reason
            else:
                raise ProtocolError("chat_turn_invalid_event")
            if size > limits.max_bytes:
                raise ProtocolError("chat_turn_limit_exceeded")
        _cancel(cancelled)
        if reason is None:
            raise ProtocolError("chat_turn_missing_terminal")
        if fragments and len(fragments) != len(calls):
            raise ProtocolError("chat_turn_call_set_mismatch")
        answer = "".join(text)
        if (reason == "answer" and (calls or not answer.strip())) or (reason == "tool_calls" and not calls):
            raise ProtocolError("chat_turn_terminal_mismatch")
        result = CollectedTurn(reason, answer, tuple(calls), usage if usage is not None else Usage(None, None, "unknown"))
    except ProtocolError:
        raise
    except Exception:
        raise ProtocolError("chat_turn_stream_failed") from None
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                raise ProtocolError("chat_turn_stream_close_failed") from None
    _cancel(cancelled)
    return result


def continuation_decision(request: GenerationRequest, turn: CollectedTurn,
                          identity: TurnIdentity, outcomes: Iterable[ToolOutcome], *,
                          limits: TurnLimits = TurnLimits(),
                          cancelled: bool = False) -> ContinuationDecision:
    """Pair known outcomes; a returned request has no send/authorization authority."""
    if not isinstance(identity, TurnIdentity) or type(cancelled) is not bool:
        raise ProtocolError("chat_turn_invalid_transition")
    for value in (identity.execution_id, identity.root_id, identity.call_id):
        _identity(value, limits)
    if cancelled:
        return ContinuationDecision("stop", identity, (), stop_reason="cancelled")
    if turn.reason != "tool_calls" or not turn.calls or request.purpose != "main":
        raise ProtocolError("chat_turn_continuation_not_applicable")
    expected = {call.call_id for call in turn.calls}
    if len(expected) != len(turn.calls) or len(expected) > limits.max_calls:
        raise ProtocolError("chat_turn_invalid_call_set")
    by_id = {}
    size = 0
    for count, outcome in enumerate(outcomes, 1):
        if count > limits.max_events:
            raise ProtocolError("chat_turn_limit_exceeded")
        if not isinstance(outcome, ToolOutcome):
            raise ProtocolError("chat_turn_invalid_result")
        size += _identity(outcome.call_id, limits)
        if outcome.call_id not in expected:
            raise ProtocolError("chat_turn_unmatched_result")
        if not isinstance(outcome.status, str) or outcome.status not in {"completed", "failed", "cancelled", "pending", "unknown"}:
            raise ProtocolError("chat_turn_invalid_result")
        if outcome.content is not None:
            size += _size(outcome.content, limits.max_bytes)
        if size > limits.max_bytes:
            raise ProtocolError("chat_turn_limit_exceeded")
        if outcome.status in {"completed", "failed", "cancelled"} and outcome.content is None:
            raise ProtocolError("chat_turn_missing_result_content")
        if outcome.call_id in by_id and outcome != by_id[outcome.call_id]:
            raise ProtocolError("chat_turn_result_mismatch")
        by_id[outcome.call_id] = outcome
    ordered = tuple(by_id[call.call_id] for call in turn.calls if call.call_id in by_id)
    if any(outcome.status == "unknown" for outcome in ordered):
        return ContinuationDecision("stop", identity, ordered, stop_reason="unknown_result")
    if len(ordered) != len(turn.calls) or any(outcome.status == "pending" for outcome in ordered):
        return ContinuationDecision("stop", identity, ordered, stop_reason="pending_results")
    messages = [GenerationMessage("assistant", turn.text, turn.calls)]
    messages.extend(GenerationMessage(
        "tool", json.dumps({"status": outcome.status, "content": outcome.content}, ensure_ascii=False),
        tool_call_id=outcome.call_id,
    ) for outcome in ordered)
    if sum(_size(message.content, limits.max_bytes) for message in messages) > limits.max_bytes:
        raise ProtocolError("chat_turn_limit_exceeded")
    candidate = replace(request, messages=(*request.messages, *messages))
    return ContinuationDecision("gate_required", identity, ordered, request=candidate)
