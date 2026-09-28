"""Ordered interval planning and bounded source-data chunks; no persistence authority."""
from dataclasses import asdict, dataclass, replace

from citeframe_contracts.memory import (
    GenerationMessage, GenerationRequest, ModelConnectionSnapshot, TokenCount, TokenCounter,
)
from .policy import (
    Capacity, CompactionError, CompactionPolicy, CounterIdentity, count_request, positive_int, validate_capacity,
)
from .units import ContextUnit, validate_units
import json


@dataclass(frozen=True)
class CompactionPlan:
    original_request: GenerationRequest
    original_count: TokenCount
    compressible: tuple[ContextUnit, ...]
    retained: tuple[ContextUnit, ...]
    reason: str
    original_units: tuple[ContextUnit, ...]
    interval_start: int
    interval_end: int
    before: tuple[ContextUnit, ...]
    capacity: Capacity

    @property
    def should_compact(self) -> bool:
        return self.reason == "compact"


@dataclass(frozen=True)
class SummaryChunk:
    units: tuple[ContextUnit, ...]
    request: GenerationRequest
    count: TokenCount


def assemble_request(template: GenerationRequest, units: tuple[ContextUnit, ...], *,
                     max_units: int = 2048) -> GenerationRequest:
    """Append chronological units to a trusted prefix without changing their order.

    A current user question belongs in its chronological protected unit; the prefix
    is for trusted system framing that already precedes history.
    """
    validate_units(units, max_units=max_units)
    if any(message.tool_calls or message.tool_call_id is not None or message.role == "tool"
           for message in template.messages):
        raise CompactionError("template_tool_batch_requires_unit")
    return replace(template, messages=template.messages + tuple(
        message for unit in units for message in unit.messages))


def plan_compaction(template: GenerationRequest, units: tuple[ContextUnit, ...], *,
                    recent_units: int, new_unit_keys: frozenset[str], policy: CompactionPolicy,
                    capacity: Capacity, connection: ModelConnectionSnapshot,
                    counter: TokenCounter, identity: CounterIdentity,
                    safety_margin: int = 0) -> CompactionPlan:
    """Select one old contiguous unprotected interval without moving retained anchors."""
    if template.purpose != "main":
        raise CompactionError("main_request_required")
    if type(recent_units) is not int or not 0 <= recent_units <= len(units):
        raise CompactionError("invalid_recent_unit_count")
    validate_capacity(capacity, connection, template, safety_margin=safety_margin)
    original = assemble_request(template, units, max_units=policy.max_units)
    if (type(new_unit_keys) is not frozenset
            or not new_unit_keys.issubset({unit.key for unit in units})):
        raise CompactionError("invalid_new_frontier")
    original_count = count_request(original, connection, counter, identity)
    boundary = len(units) - recent_units
    intervals=[]; start=0
    while start<boundary:
        if units[start].protected:
            start+=1;continue
        end=start+1
        while end<boundary and not units[end].protected:end+=1
        remaining=units[:start]+units[end:]
        required_count=count_request(assemble_request(template,remaining,max_units=policy.max_units),
                                     connection,counter,identity)
        intervals.append((required_count.tokens,start,end))
        start=end
    if intervals:
        required_tokens,start,end=min(intervals)
    else:
        required_tokens,start,end=original_count.tokens,0,0
    before,prefix,retained=units[:start],units[start:end],units[end:]
    if required_tokens > capacity.hard:
        raise CompactionError("mandatory_context_limit_exceeded")
    if original_count.tokens < capacity.soft:
        reason = "below_soft"
    elif not prefix:
        reason = "no_compressible_units"
    else:
        fresh = tuple(unit for unit in prefix if unit.key in new_unit_keys)
        base_count = count_request(template, connection, counter, identity)
        fresh_count = count_request(assemble_request(template, fresh, max_units=policy.max_units),
                                    connection, counter, identity)
        reason = ("compact" if fresh_count.tokens - base_count.tokens >= policy.min_new_tokens
                  else "insufficient_new_material")
    if reason != "compact" and original_count.tokens > capacity.hard:
        raise CompactionError("context_limit_exceeded")
    return CompactionPlan(original, original_count, prefix, retained, reason, units, start, end, before, capacity)


def replace_prefix(template: GenerationRequest, plan: CompactionPlan,
                   summary: GenerationMessage, *, max_units: int = 2048) -> GenerationRequest:
    """Build a candidate only; external validation and atomic adoption remain mandatory."""
    if (not plan.should_compact or not plan.compressible or summary.role != "assistant"
            or not summary.content.strip() or summary.tool_calls or summary.tool_call_id is not None):
        raise CompactionError("invalid_summary_candidate")
    if (plan.original_units != plan.before + plan.compressible + plan.retained
            or plan.original_units[plan.interval_start:plan.interval_end] != plan.compressible):
        raise CompactionError("plan_interval_changed")
    if assemble_request(template, plan.original_units,
                        max_units=max_units) != plan.original_request:
        raise CompactionError("plan_template_changed")
    return replace(template,messages=template.messages+tuple(m for u in plan.before for m in u.messages)
                   +(summary,)+tuple(m for u in plan.retained for m in u.messages))


def candidate_has_gain(before: TokenCount, after: TokenCount, *, policy: CompactionPolicy,
                       capacity: Capacity) -> bool:
    if ((before.counter_id, before.counter_version, before.mode, before.config_fingerprint)
            != (after.counter_id, after.counter_version, after.mode, after.config_fingerprint)
            or any(type(c.tokens) is not int or c.tokens < 0 for c in (before, after))):
        raise CompactionError("candidate_counter_changed_or_invalid")
    return (after.tokens <= capacity.target
            and before.tokens - after.tokens >= policy.min_gain_tokens)


def summary_request(template: GenerationRequest, units: tuple[ContextUnit, ...], *, max_units: int = 2048) -> GenerationRequest:
    validate_units(units,max_units=max_units)
    return replace(template,messages=template.messages+tuple(GenerationMessage("user",json.dumps({"sourceUnit":{
        "key":unit.key,"kind":unit.kind,"messages":[asdict(message) for message in unit.messages],
        "resultStates":list(unit.result_states)}},ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)) for unit in units))


def partition_summary_chunks(template: GenerationRequest, units: tuple[ContextUnit, ...], *,
                             input_limit: int, policy: CompactionPolicy,
                             connection: ModelConnectionSnapshot, counter: TokenCounter,
                             identity: CounterIdentity, safety_margin: int = 0) -> tuple[SummaryChunk, ...]:
    positive_int(input_limit, "invalid_summary_input_limit")
    if template.purpose != "compact_chunk" or template.tools:
        raise CompactionError("nonrecursive_chunk_request_required")
    if (type(safety_margin) is not int or safety_margin < 0
            or template.max_output_tokens > connection.max_output_tokens):
        raise CompactionError("invalid_capacity_reserve")
    input_limit = min(input_limit, connection.context_window_tokens
                      - template.max_output_tokens - safety_margin)
    positive_int(input_limit, "context_capacity_unknown")
    validate_units(units, max_units=policy.max_units)
    if any(unit.protected for unit in units):
        raise CompactionError("protected_unit_in_summary_chunks")
    chunks: list[SummaryChunk] = []
    current: tuple[ContextUnit, ...] = ()
    last: SummaryChunk | None = None
    for unit in units:
        trial = current + (unit,)
        request = summary_request(template, trial, max_units=policy.max_units)
        count = count_request(request, connection, counter, identity)
        if count.tokens > input_limit:
            if last is None:
                raise CompactionError("oversized_indivisible_summary_unit")
            chunks.append(last)
            if len(chunks) >= policy.max_chunk_calls:
                raise CompactionError("summary_chunk_call_limit")
            trial = (unit,)
            request = summary_request(template, trial, max_units=policy.max_units)
            count = count_request(request, connection, counter, identity)
            if count.tokens > input_limit:
                raise CompactionError("oversized_indivisible_summary_unit")
        current = trial
        last = SummaryChunk(trial, request, count)
    if last is not None:
        chunks.append(last)
    return tuple(chunks)
