"""Frozen capacity and counter checks for complete provider requests."""
from dataclasses import dataclass
from math import floor, isfinite

from citeframe_contracts.memory import (
    GenerationRequest, ModelConnectionSnapshot, TokenCount, TokenCounter,
)


class CompactionError(ValueError):
    """Stable error code, without source or provider payloads."""


def positive_int(value: int, code: str) -> None:
    if type(value) is not int or value <= 0:
        raise CompactionError(code)


@dataclass(frozen=True)
class CompactionPolicy:
    soft_ratio: float = 0.80
    target_ratio: float = 0.60
    min_new_tokens: int = 256
    min_gain_tokens: int = 128
    max_chunk_calls: int = 8
    max_units: int = 2048

    def __post_init__(self) -> None:
        if (type(self.soft_ratio) not in (int, float)
                or type(self.target_ratio) not in (int, float)
                or not isfinite(self.soft_ratio) or not isfinite(self.target_ratio)
                or not 0 < self.target_ratio < self.soft_ratio < 1):
            raise CompactionError("invalid_compaction_watermarks")
        for value in (self.min_new_tokens, self.min_gain_tokens,
                      self.max_chunk_calls, self.max_units):
            positive_int(value, "invalid_compaction_bound")


@dataclass(frozen=True)
class CounterIdentity:
    counter_id: str
    counter_version: str
    mode: str
    config_fingerprint: str

    def __post_init__(self) -> None:
        if (any(not isinstance(value, str) or not value for value in
                (self.counter_id, self.counter_version, self.config_fingerprint))
                or self.mode not in ("exact", "estimated")):
            raise CompactionError("invalid_counter_identity")


@dataclass(frozen=True)
class Capacity:
    hard: int
    soft: int
    target: int

    def __post_init__(self) -> None:
        if (any(type(value) is not int for value in (self.hard, self.soft, self.target))
                or not 0 < self.target < self.soft < self.hard):
            raise CompactionError("context_capacity_too_small")


def capacity_for(connection: ModelConnectionSnapshot, request: GenerationRequest,
                 policy: CompactionPolicy, *, input_ceiling: int,
                 safety_margin: int) -> Capacity:
    positive_int(input_ceiling, "invalid_input_ceiling")
    positive_int(connection.context_window_tokens, "context_capacity_unknown")
    positive_int(request.max_output_tokens, "invalid_output_reserve")
    if (type(safety_margin) is not int or safety_margin < 0
            or request.max_output_tokens > connection.max_output_tokens):
        raise CompactionError("invalid_capacity_reserve")
    # Protocol framing and tool definitions are already in the full-request count.
    hard = min(input_ceiling,
               connection.context_window_tokens - request.max_output_tokens - safety_margin)
    return Capacity(hard, floor(hard * policy.soft_ratio), floor(hard * policy.target_ratio))


def count_request(request: GenerationRequest, connection: ModelConnectionSnapshot,
                  counter: TokenCounter, identity: CounterIdentity) -> TokenCount:
    if connection.config_fingerprint != identity.config_fingerprint:
        raise CompactionError("profile_changed")
    count = counter.count(request, connection)
    if (type(count.tokens) is not int or count.tokens < 0
            or (count.counter_id, count.counter_version, count.mode, count.config_fingerprint)
            != (identity.counter_id, identity.counter_version, identity.mode,
                identity.config_fingerprint)):
        raise CompactionError("counter_changed_or_invalid")
    return count


def validate_capacity(capacity: Capacity, connection: ModelConnectionSnapshot,
                      request: GenerationRequest, *, safety_margin: int = 0) -> None:
    positive_int(connection.context_window_tokens, "context_capacity_unknown")
    positive_int(request.max_output_tokens, "invalid_output_reserve")
    if (type(safety_margin) is not int or safety_margin < 0
            or request.max_output_tokens > connection.max_output_tokens):
        raise CompactionError("invalid_capacity_reserve")
    if capacity.hard > connection.context_window_tokens - request.max_output_tokens - safety_margin:
        raise CompactionError("capacity_profile_mismatch")
