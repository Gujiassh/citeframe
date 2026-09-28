"""Deterministic pure algorithms; no persistence, authorization or model-quality claims."""
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import subprocess
import sys

import pytest

from citeframe_contracts.memory import (
    GenerationMessage as Message, GenerationRequest as Request, ModelConnectionSnapshot,
    TokenCount, ToolCall, ToolDefinition,
)
from citeframe_memory.compaction.policy import (
    Capacity, CompactionError, CompactionPolicy, CounterIdentity, capacity_for, count_request,
)
from citeframe_memory.compaction.units import ContextUnit, validate_units
from citeframe_memory.compaction.packing import (
    assemble_request, candidate_has_gain, partition_summary_chunks, plan_compaction, replace_prefix, summary_request,
)


PROFILE = ModelConnectionSnapshot("openai_responses", "https://fixture.invalid", "fixture",
                                  "not-a-secret", 10, "profile-v1", 1000, 100)
IDENTITY = CounterIdentity("fixture", "v1", "estimated", "profile-v1")
POLICY = CompactionPolicy(min_new_tokens=1, min_gain_tokens=10)
FRAME = Request((Message("system", "trusted rules"),), 50)


class Counter:
    """Fixture framing units are deterministic estimates, not a tokenizer."""
    def __init__(self):
        self.requests = []

    def count(self, request, connection):
        self.requests.append(request)
        tokens = 3 + sum(7 + len(m.content) + len(m.tool_call_id or "") + sum(
            len(c.call_id) + len(c.name) + len(c.arguments_json) + 5 for c in m.tool_calls
        ) for m in request.messages)
        tokens += sum(len(t.name) + len(t.description) + len(t.parameters_json) + 11
                      for t in request.tools)
        return TokenCount(tokens, "estimated", "fixture", "v1", connection.config_fingerprint)


def unit(key, length=100, protected=False):
    return ContextUnit(key, "messages", (Message("user", "x" * length),), protected=protected)


def group(key="batch", ids=("call:a", "call:b"), states=("succeeded", "failed")):
    calls = tuple(ToolCall(id_, "read_source", '{"id":"source"}') for id_ in ids)
    return ContextUnit(key, "tool_group", (
        Message("assistant", "", calls),
        *(Message("tool", "original result " + id_, tool_call_id=id_) for id_ in ids),
    ), states)


def plan(units, *, capacity=Capacity(900, 720, 540), recent=1, keys=None, counter=None):
    return plan_compaction(FRAME, units, recent_units=recent,
                           new_unit_keys=frozenset(u.key for u in units) if keys is None else keys,
                           policy=POLICY, capacity=capacity, connection=PROFILE,
                           counter=counter or Counter(), identity=IDENTITY)


@pytest.mark.parametrize("soft,target", [(1, .5), (.8, .8), (.4, .5), (0, 0),
                                           (float("nan"), .5), (.8, float("inf")), (True, .5)])
def test_invalid_watermarks(soft, target):
    with pytest.raises(CompactionError, match="invalid_compaction_watermarks"):
        CompactionPolicy(soft_ratio=soft, target_ratio=target)


@pytest.mark.parametrize("field", ["min_new_tokens", "min_gain_tokens", "max_chunk_calls", "max_units"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_positive_finite_integer_bounds(field, value):
    with pytest.raises(CompactionError):
        replace(POLICY, **{field: value})


def test_policy_frozen_and_capacity_reserves():
    with pytest.raises(FrozenInstanceError):
        POLICY.soft_ratio = .9
    assert capacity_for(PROFILE, FRAME, POLICY, input_ceiling=800, safety_margin=100) == Capacity(800, 640, 480)
    assert capacity_for(PROFILE, FRAME, POLICY, input_ceiling=9999, safety_margin=100).hard == 850
    with pytest.raises(CompactionError):
        capacity_for(PROFILE, FRAME, POLICY, input_ceiling=1, safety_margin=0)
    with pytest.raises(CompactionError):
        capacity_for(PROFILE, replace(FRAME, max_output_tokens=101), POLICY,
                     input_ceiling=900, safety_margin=0)
    with pytest.raises(CompactionError):
        capacity_for(PROFILE, FRAME, POLICY, input_ceiling=900, safety_margin=-1)


def test_full_request_preserves_tools_and_temperature():
    template = replace(FRAME, tools=(ToolDefinition("read_source", "description", '{"type":"object"}'),),
                       temperature=.2)
    request = assemble_request(template, (group(), unit("recent", 7)))
    counter = Counter()
    count = count_request(request, PROFILE, counter, IDENTITY)
    assert counter.requests == [request]
    assert request.tools == template.tools and request.temperature == .2
    assert request.max_output_tokens == 50 and request.messages[:len(FRAME.messages)] == FRAME.messages
    assert count.mode == "estimated"
    assert count.tokens > Counter().count(replace(request, tools=()), PROFILE).tokens


@pytest.mark.parametrize("field,value", [("counter_id", "other"), ("counter_version", "v2"),
                                         ("mode", "exact"), ("config_fingerprint", "other"),
                                         ("tokens", -1), ("tokens", True), ("tokens", 1.5)])
def test_counter_drift_or_invalid_result(field, value):
    class Changed(Counter):
        def count(self, request, connection):
            return replace(super().count(request, connection), **{field: value})
    with pytest.raises(CompactionError, match="counter_changed_or_invalid"):
        count_request(FRAME, PROFILE, Changed(), IDENTITY)


def test_profile_drift_fails_before_counter():
    counter = Counter()
    with pytest.raises(CompactionError, match="profile_changed"):
        count_request(FRAME, replace(PROFILE, config_fingerprint="v2"), counter, IDENTITY)
    assert not counter.requests


def test_complete_group_preserves_failed_cancelled_results_and_order():
    batch = group(states=("failed", "cancelled"))
    request = assemble_request(FRAME, (batch,))
    assert request.messages[-3:] == batch.messages
    assert tuple(m.tool_call_id for m in batch.messages[1:]) == ("call:a", "call:b")


@pytest.mark.parametrize("states", [("pending", "succeeded"), ("outcome_unknown", "failed"),
                                     ("unknown", "cancelled"), ("succeeded",)])
def test_pending_unknown_missing_result_state_rejected(states):
    with pytest.raises(CompactionError):
        group(states=states)


@pytest.mark.parametrize("change", ["missing", "duplicate", "orphan", "reorder", "mixed", "nested"])
def test_illegal_parallel_batch_rejected(change):
    batch = group()
    messages = list(batch.messages)
    if change == "missing":
        messages.pop()
    elif change == "duplicate":
        messages[2] = messages[1]
    elif change == "orphan":
        messages[2] = replace(messages[2], tool_call_id="unknown")
    elif change == "reorder":
        messages[1], messages[2] = messages[2], messages[1]
    elif change == "mixed":
        messages[2] = Message("assistant", "next batch")
    else:
        messages[1] = replace(messages[1], tool_calls=messages[0].tool_calls)
    with pytest.raises(CompactionError):
        replace(batch, messages=tuple(messages))


def test_duplicate_calls_and_cross_batch_identity_rejected():
    with pytest.raises(CompactionError):
        group(ids=("same", "same"))
    with pytest.raises(CompactionError, match="duplicate_tool_id_across_batches"):
        validate_units((group("one"), group("two")), max_units=2)
    with pytest.raises(CompactionError, match="duplicate_unit_key"):
        validate_units((unit("same"), unit("same")), max_units=2)
    with pytest.raises(CompactionError, match="context_unit_limit"):
        validate_units((unit("a"), unit("b")), max_units=1)


@pytest.mark.parametrize("message", [Message("system", "untrusted history"), Message("tool", "orphan"),
                                      Message("assistant", "", (ToolCall("a", "read", "{}"),))])
def test_messages_cannot_hide_tool_or_system_roles(message):
    with pytest.raises(CompactionError):
        ContextUnit("bad", "messages", (message,))


def test_template_cannot_hide_partial_batch():
    with pytest.raises(CompactionError, match="template_tool_batch_requires_unit"):
        assemble_request(replace(FRAME, messages=(group().messages[0],)), ())


def test_prefix_plan_retains_recent_and_protected_units_without_holes():
    units = (unit("old1", 400), unit("old2", 300), unit("constraint", 10, True), unit("recent", 10))
    result = plan(units)
    assert result.should_compact
    assert result.compressible == units[:2] and result.retained == units[2:]
    assert result.original_request.messages == FRAME.messages + tuple(m for u in units for m in u.messages)
    candidate = replace_prefix(FRAME, result, Message("assistant", "source-backed candidate"))
    assert candidate.messages[:len(FRAME.messages)] == FRAME.messages
    assert candidate.messages[-2:] == tuple(m for u in units[2:] for m in u.messages)
    assert units[0].messages[0].content == "x" * 400
    with pytest.raises(CompactionError, match="plan_template_changed"):
        replace_prefix(replace(FRAME, temperature=.5), result, Message("assistant", "summary"))


def test_protected_middle_preserves_anchor_while_selecting_later_interval():
    units = (unit("first", 5), unit("protected", 5, True), unit("later", 700), unit("recent", 5))
    result = plan(units)
    assert result.compressible == units[2:3]
    assert result.before == units[:2] and result.retained == units[3:]
    assert (result.interval_start,result.interval_end)==(2,3)


def test_soft_boundary_triggers_and_lower_target_required():
    units = (unit("old", 400), unit("recent", 10))
    n = Counter().count(assemble_request(FRAME, units), PROFILE).tokens
    result = plan(units, capacity=Capacity(n + 100, n, n - 100))
    assert result.should_compact
    before = result.original_count
    assert candidate_has_gain(before, replace(before, tokens=n - 100), policy=POLICY,
                              capacity=Capacity(n + 100, n, n - 100))
    assert not candidate_has_gain(before, replace(before, tokens=n - 99), policy=POLICY,
                                  capacity=Capacity(n + 100, n, n - 100))
    assert not candidate_has_gain(before, replace(before, tokens=n - 1), policy=POLICY,
                                  capacity=Capacity(n + 100, n, n - 100))


def test_no_progress_decision_is_pure_and_hard_overflow_fails():
    units = (unit("old", 700), unit("recent", 10))
    assert plan(units, keys=frozenset()).reason == "insufficient_new_material"
    with pytest.raises(CompactionError, match="context_limit_exceeded"):
        plan(units, keys=frozenset(), capacity=Capacity(600, 480, 360))
    with pytest.raises(CompactionError, match="mandatory_context_limit_exceeded"):
        plan((unit("huge", 950),), recent=1)
    assert plan((unit("tiny", 1),)).reason == "below_soft"
    result = plan((unit("protected", 700, True),), capacity=Capacity(900, 600, 400))
    assert result.reason == "no_compressible_units"


def test_unknown_frontier_and_summary_not_data_role_rejected():
    with pytest.raises(CompactionError, match="invalid_new_frontier"):
        plan((unit("a"),), keys=frozenset({"foreign"}))
    result = plan((unit("old", 750), unit("recent", 5)))
    for message in (Message("system", "summary"), Message("assistant", " ")):
        with pytest.raises(CompactionError, match="invalid_summary_candidate"):
            replace_prefix(FRAME, result, message)


def chunks(units, *, limit=400, policy=POLICY, counter=None, profile=PROFILE, **kwargs):
    return partition_summary_chunks(replace(FRAME, purpose="compact_chunk"), units,
                                    input_limit=limit, policy=policy, connection=profile,
                                    counter=counter or Counter(), identity=IDENTITY, **kwargs)


def test_chunk_boundaries_keep_complete_groups_and_exact_originals():
    units = (unit("a", 130), group(), unit("c", 130))
    counter = Counter()
    limit=max(Counter().count(summary_request(replace(FRAME,purpose="compact_chunk"),(u,)),PROFILE).tokens for u in units)
    result = chunks(units, counter=counter,limit=limit)
    assert tuple(u for chunk in result for u in chunk.units) == units
    assert len(result) == 3
    assert all(chunk.count.tokens <= limit and chunk.request.purpose == "compact_chunk"
               and not chunk.request.tools for chunk in result)
    import json
    source=json.loads(result[1].request.messages[-1].content)["sourceUnit"]
    assert source["key"]==units[1].key and source["resultStates"]==list(units[1].result_states)
    assert source["messages"][1]["content"]==units[1].messages[1].content
    assert len(counter.requests) <= 2 * len(units)


def test_oversized_unit_raises_without_truncating_or_mutating():
    huge = unit("large-original", 5000)
    with pytest.raises(CompactionError, match="oversized_indivisible_summary_unit"):
        chunks((huge,))
    assert huge.messages[0].content == "x" * 5000
    with pytest.raises(CompactionError, match="oversized_indivisible_summary_unit"):
        chunks((unit("ok", 5), huge))


def test_chunk_call_cap_and_model_capacity_are_enforced():
    units = tuple(unit(str(i), 150) for i in range(3))
    with pytest.raises(CompactionError, match="summary_chunk_call_limit"):
        chunks(units, policy=replace(POLICY, max_chunk_calls=2))
    assert len(chunks(units[:2], policy=replace(POLICY, max_chunk_calls=2))) == 2
    with pytest.raises(CompactionError, match="oversized_indivisible_summary_unit"):
        chunks((unit("large", 900),), limit=5000, safety_margin=100)
    with pytest.raises(CompactionError, match="protected_unit"):
        chunks((unit("protected", 1, True),))
    assert chunks(()) == ()


def test_chunk_path_requires_nonrecursive_purpose():
    with pytest.raises(CompactionError, match="nonrecursive_chunk_request_required"):
        partition_summary_chunks(FRAME, (unit("old"),), input_limit=300,
                                 policy=POLICY, connection=PROFILE, counter=Counter(), identity=IDENTITY)


def test_neutral_import_denies_apps_and_persistence():
    root = Path(__file__).resolve().parents[3]
    paths = [str(root / "packages" / name / "src") for name in ("backend-contracts", "memory-service")]
    code = """
import importlib.abc, sys
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('ai_pdf_api', 'ai_pdf_worker', 'citeframe_persistence'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Deny())
import citeframe_memory.compaction.policy
import citeframe_memory.compaction.units
import citeframe_memory.compaction.packing
print('pure-import-pass')
"""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONDONTWRITEBYTECODE": "1"}
    assert "pure-import-pass" in subprocess.check_output([sys.executable, "-c", code], env=env, text=True)


@pytest.mark.parametrize("call", [None, "bad", ToolCall("a", None, "{}"),
                                    ToolCall("a", "", "{}"), ToolCall("a", "read", None),
                                    ToolCall("a", "read", "[1]"), ToolCall("a", "read", "bad json")])
def test_malformed_tool_call_has_stable_structural_error(call):
    with pytest.raises(CompactionError, match="invalid_tool_"):
        ContextUnit("batch", "tool_group", (
            Message("assistant", "", (call,)), Message("tool", "result", tool_call_id="a"),
        ), ("succeeded",))


def test_current_question_remains_after_history_in_original_and_candidate():
    old = ContextUnit("old", "messages", (Message("user", "historical question " * 40),))
    current = ContextUnit("current", "messages", (Message("user", "current question"),), protected=True)
    result = plan((old, current))
    assert result.should_compact
    assert result.original_request.messages == FRAME.messages + old.messages + current.messages
    candidate = replace_prefix(FRAME, result, Message("assistant", "historical summary data"))
    assert candidate.messages == FRAME.messages + (Message("assistant", "historical summary data"),) + current.messages


def test_chunk_output_ceiling_is_checked_before_counting():
    counter = Counter()
    with pytest.raises(CompactionError, match="invalid_capacity_reserve"):
        partition_summary_chunks(replace(FRAME, purpose="compact_chunk", max_output_tokens=101),
                                 (unit("old"),), input_limit=10000, policy=POLICY, connection=PROFILE,
                                 counter=counter, identity=IDENTITY)
    assert not counter.requests



def test_same_submission_protected_question_allows_two_complete_tool_intervals():
    question=unit("current",15,True)
    batches=tuple(group(f"batch-{i}",ids=(f"{i}:a",f"{i}:b")) for i in range(9))
    first_units=(question,)+batches[:6]
    first=plan(first_units)
    assert first.should_compact and first.before==(question,)
    assert (first.interval_start,first.interval_end)==(1,6)
    assert first.compressible==batches[:5] and first.retained==batches[5:6]
    candidate=replace_prefix(FRAME,first,Message("assistant","summary data"))
    assert candidate.messages==FRAME.messages+question.messages+(Message("assistant","summary data"),)+batches[5].messages
    second_units=(question,)+batches
    second=plan(second_units,keys=frozenset(b.key for b in batches[5:]))
    assert second.should_compact and second.original_count.tokens>second.capacity.hard
    assert (second.interval_start,second.interval_end)==(1,9)
    assert second.compressible==batches[:8] and second.retained==batches[8:]
    assert second.before+second.compressible+second.retained==second_units
    assert set(b.key for b in first.compressible)<set(b.key for b in second.compressible)


def test_protected_constraint_stays_between_older_history_and_selected_interval():
    current=unit("current",15,True);constraint=unit("constraint",12,True)
    batches=tuple(group(f"batch-{i}",ids=(f"{i}:a",f"{i}:b")) for i in range(7))
    originals=(unit("earlier",20),current,batches[0],constraint)+batches[1:]
    selected=plan(originals)
    assert selected.should_compact and selected.before==originals[:4]
    assert selected.compressible==batches[1:-1] and selected.retained==batches[-1:]
    candidate=replace_prefix(FRAME,selected,Message("assistant","interval summary"))
    assert candidate.messages==FRAME.messages+tuple(m for u in originals[:4] for m in u.messages)+(Message("assistant","interval summary"),)+batches[-1].messages
    assert selected.before+selected.compressible+selected.retained==originals
