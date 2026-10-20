"""Complete, ordered protocol units. These types do not establish source permission."""
from dataclasses import dataclass
import json
from typing import Literal

from citeframe_contracts.memory import GenerationMessage, ToolCall
from .policy import CompactionError, positive_int


@dataclass(frozen=True)
class ContextUnit:
    key: str
    kind: Literal["messages", "tool_group"]
    messages: tuple[GenerationMessage, ...]
    result_states: tuple[str, ...] = ()
    protected: bool = False

    def __post_init__(self) -> None:
        if (not isinstance(self.key, str) or not 1 <= len(self.key) <= 160
                or type(self.messages) is not tuple or not self.messages
                or type(self.result_states) is not tuple or type(self.protected) is not bool):
            raise CompactionError("invalid_context_unit")
        if any(not isinstance(message, GenerationMessage) or not isinstance(message.content, str)
               or type(message.tool_calls) is not tuple for message in self.messages):
            raise CompactionError("invalid_context_message")
        if self.kind == "messages":
            if self.result_states or any(
                m.role not in ("user", "assistant") or m.tool_calls or m.tool_call_id is not None
                for m in self.messages
            ):
                raise CompactionError("mixed_or_orphan_tool_batch")
        elif self.kind == "tool_group":
            self._validate_group()
        else:
            raise CompactionError("invalid_unit_kind")

    def _validate_group(self) -> None:
        assistant, *results = self.messages
        if (assistant.role != "assistant" or not assistant.tool_calls
                or assistant.tool_call_id is not None):
            raise CompactionError("missing_tool_batch")
        for call in assistant.tool_calls:
            if (not isinstance(call, ToolCall) or not isinstance(call.name, str) or not call.name
                    or not isinstance(call.arguments_json, str)):
                raise CompactionError("invalid_tool_call_shape")
            try:
                arguments = json.loads(call.arguments_json)
            except (ValueError, RecursionError):
                raise CompactionError("invalid_tool_arguments") from None
            if not isinstance(arguments, dict):
                raise CompactionError("invalid_tool_arguments")
        ids = tuple(call.call_id for call in assistant.tool_calls)
        if (any(not isinstance(id_, str) or not id_ for id_ in ids)
                or len(set(ids)) != len(ids)):
            raise CompactionError("duplicate_or_empty_tool_id")
        if len(results) != len(ids) or len(self.result_states) != len(ids):
            raise CompactionError("incomplete_tool_batch")
        if any(state not in ("succeeded", "failed", "cancelled") for state in self.result_states):
            raise CompactionError("nonterminal_tool_batch")
        if any(result.role != "tool" or result.tool_calls for result in results):
            raise CompactionError("mixed_or_orphan_tool_batch")
        if tuple(result.tool_call_id for result in results) != ids:
            raise CompactionError("tool_result_order_or_identity")


def validate_units(units: tuple[ContextUnit, ...], *, max_units: int) -> None:
    positive_int(max_units, "invalid_unit_bound")
    if type(units) is not tuple or len(units) > max_units:
        raise CompactionError("context_unit_limit")
    keys: set[str] = set()
    call_ids: set[str] = set()
    for unit in units:
        if not isinstance(unit, ContextUnit):
            raise CompactionError("invalid_context_unit")
        if unit.key in keys:
            raise CompactionError("duplicate_unit_key")
        keys.add(unit.key)
        ids = {call.call_id for message in unit.messages for call in message.tool_calls}
        if call_ids.intersection(ids):
            raise CompactionError("duplicate_tool_id_across_batches")
        call_ids.update(ids)
