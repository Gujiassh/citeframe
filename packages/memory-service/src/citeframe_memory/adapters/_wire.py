"""Bounded JSON and streaming primitives shared by provider wire adapters."""

import json
import math
from dataclasses import dataclass
from collections.abc import Iterable, Iterator


@dataclass(frozen=True)
class WireLimits:
    max_events: int = 10000
    max_event_bytes: int = 262144
    max_text_bytes: int = 1048576
    max_argument_bytes: int = 16384
    max_calls: int = 16
    max_id_bytes: int = 255

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("wire limits must be positive integers")


def strict_json(value: str):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def constant(_value):
        raise ValueError("non-finite JSON number")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid JSON") from exc


def bounded_text(value, limit: int, label: str, *, empty=True) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ValueError(f"invalid {label}")
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{label} exceeds byte limit")
    return value


def sse_events(lines: Iterable[str], limits: WireLimits) -> Iterator[dict | str]:
    """Consume decoded SSE lines; transport owns decoding and connection lifetime."""
    data = []
    size = 0
    count = 0
    total = 0
    for line in lines:
        total += len(line.encode("utf-8")) + 1
        if total > limits.max_text_bytes:
            raise ValueError("SSE turn exceeds byte limit")
        bounded_text(line, limits.max_event_bytes, "SSE line")
        if line == "":
            if data:
                count += 1
                if count > limits.max_events:
                    raise ValueError("event limit exceeded")
                body = "\n".join(data)
                event = "[DONE]" if body == "[DONE]" else strict_json(body)
                if not isinstance(event, dict) and event != "[DONE]":
                    raise ValueError("SSE data must be an object")
                yield event
                data = []
                size = 0
        elif line.startswith("data:"):
            fragment = line[5:]
            if fragment.startswith(" "):
                fragment = fragment[1:]
            size += len(fragment.encode("utf-8")) + 1
            if size > limits.max_event_bytes:
                raise ValueError("SSE event exceeds byte limit")
            data.append(fragment)
        elif line.startswith(":") or line.startswith(("event:", "id:", "retry:")):
            continue
        else:
            raise ValueError("invalid SSE line")
    if data:
        raise ValueError("unterminated SSE event")


class CallBuffer:
    def __init__(self, limits: WireLimits):
        self.limits = limits
        self.calls = {}

    def start(self, key, call_id="", name=""):
        self.key(key)
        if key in self.calls or len(self.calls) >= self.limits.max_calls:
            raise ValueError("duplicate tool index or tool count limit")
        self.calls[key] = {"id": "", "name": "", "arguments": "", "done": False}
        self.append(key, call_id=call_id, name=name)

    def append(self, key, *, call_id="", name="", arguments=""):
        self.key(key)
        if key not in self.calls or self.calls[key]["done"]:
            raise ValueError("unknown or completed tool index")
        call = self.calls[key]
        for field, value, limit in (
            ("id", call_id, self.limits.max_id_bytes),
            ("name", name, self.limits.max_id_bytes),
            ("arguments", arguments, self.limits.max_argument_bytes),
        ):
            bounded_text(value, limit, field)
            call[field] = bounded_text(call[field] + value, limit, field)

    def finish(self, key):
        self.key(key)
        if key not in self.calls or self.calls[key]["done"]:
            raise ValueError("unknown or duplicate tool completion")
        self.calls[key]["done"] = True

    @staticmethod
    def key(key):
        if type(key) is not int or key < 0:
            raise ValueError("invalid tool index")

    def complete(self, *, require_done=False):
        result = []
        ids = set()
        for index in sorted(self.calls):
            call = self.calls[index]
            if require_done and not call["done"]:
                raise ValueError("incomplete tool call")
            if not call["id"] or not call["name"] or call["id"] in ids:
                raise ValueError("missing or duplicate tool identity")
            arguments = strict_json(call["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            ids.add(call["id"])
            result.append((call["id"], call["name"], arguments))
        return result
