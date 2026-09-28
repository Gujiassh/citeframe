"""Pure fixtures only; use the real #43 policy, never a replacement implementation."""
from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest
from citeframe_contracts.compaction import SourceReference
from citeframe_contracts.history import (
    LocatorSpan, SourceSelection, TextSpan, history_member_from_runtime_shape,
    parse_history_policy,
)
from citeframe_contracts.memory import (
    GenerationMessage, GenerationRequest, MemoryError, ModelConnectionSnapshot,
    TokenCount, ToolCall, ToolDefinition,
)
from citeframe_memory.compaction.policy import (
    CompactionError, CompactionPolicy, CounterIdentity, capacity_for,
)
from citeframe_memory.history.ranges import (
    decode_cursor, encode_cursor, fit_page, open_window, request_hash,
)
from citeframe_memory.history.search import parse_query, projected_kinds, project_source_ids

ID = "11111111-1111-4111-8111-111111111111"
KEY = b"deterministic-test-key-not-a-secret" * 2
BINDING = "a" * 64


def selection(body, span=None):
    return SourceSelection(SourceReference(ID, 1, sha256(body.encode("utf-8")).hexdigest()), span)


def connection(profile="profile1"):
    return ModelConnectionSnapshot("anthropic", "https://invalid.example", "test",
                                   "", 1, profile, 40000, 1000)


def request(call="C1", prefix=()):
    return GenerationRequest(prefix + (
        GenerationMessage("system", "exact system framing"),
        GenerationMessage("user", "read original"),
        GenerationMessage("assistant", "", (
            ToolCall(call, "read_source", '{"ref":"fixed"}'),
            ToolCall(call + "-sibling", "other", "{}"),
        )),
        GenerationMessage("tool", "pending", tool_call_id=call),
        GenerationMessage("tool", "sibling body", tool_call_id=call + "-sibling"),
    ), 500, tools=(ToolDefinition("read_source", "description", '{"type":"object"}'),))


class CharacterCounter:
    """Declared estimated fixture: one serialized code point costs one token."""
    def __init__(self, mode="estimated"):
        self.mode = mode
        self.seen = []

    def count(self, request, connection):
        self.seen.append(request)
        tokens = len(json.dumps(asdict(request), ensure_ascii=False, sort_keys=True))
        return TokenCount(tokens, self.mode, "fixture-character", "1",
                          connection.config_fingerprint)


def render(page):
    return json.dumps(asdict(page), ensure_ascii=False, sort_keys=True)


def run_page(body, window, *, req=None, conn=None, counter=None, ceiling=12000, **kwargs):
    req = req or request()
    conn = conn or connection()
    counter = counter or CharacterCounter()
    identity = CounterIdentity("fixture-character", "1", counter.mode, conn.config_fingerprint)
    cap = capacity_for(conn, req, CompactionPolicy(), input_ceiling=ceiling, safety_margin=20)
    defaults = dict(request=req, tool_call_id=req.messages[-2].tool_call_id, render=render,
                    connection=conn, counter=counter, identity=identity, capacity=cap,
                    binding=BINDING, expires_at=900, key=KEY, now=1, safety_margin=20)
    defaults.update(kwargs)
    return fit_page(body, window, **defaults)


def test_source_reference_is_single_canonical_type():
    assert type(selection("body").reference) is SourceReference


def test_legacy_policy_is_unchanged_and_disabled():
    value = dict(schemaVersion="compaction-policy-v1", maxCalls=3, maxInputTokens=4,
                 maxOutputTokens=5, maxSummaryCalls=6, maxEpisodes=7,
                 deadlineAt="2026-09-28T00:00:00Z")
    before = json.dumps(value, sort_keys=True)
    assert not history_member_from_runtime_shape(value).enabled
    assert json.dumps(value, sort_keys=True) == before
    with pytest.raises(MemoryError):
        history_member_from_runtime_shape(dict(value, history={}))
    value["schemaVersion"] = "compaction-policy-v2"
    with pytest.raises(MemoryError):
        history_member_from_runtime_shape(value)
    value["history"] = dict(schemaVersion="history-policy-v1", enabled=False)
    assert not history_member_from_runtime_shape(value).enabled


def enabled():
    return dict(schemaVersion="history-policy-v1", enabled=True, audience="workspace",
                allowedScopes=["current_branch", "workspace_history"],
                sourceKinds=["chat_message", "note"], policyVersion="history-runtime-v1")


def test_enabled_union():
    policy = parse_history_policy(enabled())
    assert policy.source_kinds == ("chat_message", "note")
    assert policy.allowed_scopes == ("current_branch", "workspace_history")


@pytest.mark.parametrize("change", [
    {"enabled": 1}, {"audience": "private"}, {"extra": True},
    {"allowedScopes": []}, {"allowedScopes": ["thread"]},
    {"sourceKinds": ["note", "note"]}, {"sourceKinds": ["memory_instruction"]},
    {"policyVersion": "unknown"}, {"schemaVersion": "unknown"},
])
def test_policy_rejects_unknown_or_weak_shapes(change):
    with pytest.raises(MemoryError):
        parse_history_policy(dict(enabled(), **change))


@pytest.mark.parametrize("value", [
    {"query": "x", "scope": {"kind": "current_branch", "threadId": ID}},
    {"query": "x", "scope": {"kind": "current_branch"}, "sourceKinds": ["note"]},
    {"query": "x", "scope": {"kind": "thread"}},
    {"query": "x", "scope": {"kind": "workspace_history"}, "limit": True},
    {"query": "x", "scope": {"kind": "workspace_history"}, "unknown": 1},
    {"query": "x", "scope": {"kind": "workspace_history"}, "from": "2026-09-28"},
    {"query": "x", "scope": {"kind": "workspace_history"}, "sourceKinds": []},
])
def test_query_rejects(value):
    with pytest.raises(MemoryError):
        parse_query(value)


def test_workspace_corpus_is_not_replaced_by_query_projection():
    corpus = frozenset(("a", "b", "c"))
    for scope, expected in ((frozenset(("a",)), frozenset(("a",))),
                            (frozenset(("b", "c")), frozenset(("b",)))):
        assert project_source_ids(corpus_source_ids=corpus, authorized_source_ids=frozenset(("a", "b")),
                                  scope_source_ids=scope) == expected
    assert corpus == frozenset(("a", "b", "c"))
    query = parse_query({"query": "words", "scope": {"kind": "current_branch"}})
    assert projected_kinds(query, enabled_kinds=("chat_message", "note")) == ("chat_message",)
    query = parse_query({"query": "words", "scope": {"kind": "workspace_history"}, "sourceKinds": ["note"]})
    with pytest.raises(MemoryError, match="source_kind_not_enabled"):
        projected_kinds(query, enabled_kinds=("chat_message",))


@pytest.mark.parametrize("span,before,after", [
    (TextSpan(1, 5), 0, 0), (TextSpan(1, 5), 2000, 2000), (None, 0, 0),
])
def test_codepoint_exact_fixed_window(span, before, after):
    body = "\ufeff开始\r\n😀e\u0301" * 1700
    window = open_window(body, selection(body, span), before=before, after=after)
    start, end = window.start, window.end
    parts = []
    while True:
        result = run_page(body, window)
        assert result.page.start == window.next_start
        assert result.page.window_end == end
        assert result.page.end > result.page.start
        parts.append(result.page.content)
        if result.page.next_cursor is None:
            break
        window, _ = decode_cursor(result.page.next_cursor, binding=BINDING, key=KEY, now=2)
        assert window.start == start and window.end == end
    assert "".join(parts) == body[start:end]


@pytest.mark.parametrize("span,before,after", [
    (None, 1, 0), (TextSpan(1, 20), 0, 0),
    (LocatorSpan(ID), 0, 0), (TextSpan(0, 2), True, 0),
])
def test_invalid_or_unresolved_window(span, before, after):
    with pytest.raises(MemoryError):
        open_window("abc", selection("abc", span), before=before, after=after)


def test_empty_terminal_and_source_mutation():
    result = run_page("", open_window("", selection("")))
    assert result.page.content == "" and result.page.next_cursor is None
    with pytest.raises(MemoryError, match="source_version_unavailable"):
        run_page("changed", open_window("original", selection("original")))
    with pytest.raises(MemoryError, match="invalid_source_ref"):
        open_window("secret body", None)


def test_cursor_mac_binding_expiry():
    window = open_window("abc", selection("abc"))
    cursor = encode_cursor(window, binding=BINDING, expires_at=900, key=KEY)
    assert decode_cursor(cursor, binding=BINDING, key=KEY, now=1)[0] == window
    for value, binding, now in ((cursor[:-1] + "!", BINDING, 1),
                                (cursor, "b" * 64, 1), (cursor, BINDING, 900)):
        with pytest.raises(MemoryError, match="^invalid_history_cursor$"):
            decode_cursor(value, binding=binding, key=KEY, now=now)


def test_current_c1_to_c2_profile_and_framing_change_continues_and_shrinks():
    body = "z" * 12000
    first = run_page(body, open_window(body, selection(body)))
    cursor = first.page.next_cursor
    window, _ = decode_cursor(cursor, binding=BINDING, key=KEY, now=2)
    req = request("C2", (GenerationMessage("user", "additional prompt" * 20),))
    second = run_page(body, window, req=req, conn=connection("profile2"),
                      page_token_limit=200, now=2)
    assert second.page.start == first.page.end
    assert 0 < len(second.page.content) < len(first.page.content)
    assert second.count.config_fingerprint == "profile2"
    assert second.request_sha256 != first.request_sha256
    assert second.request_sha256 == request_hash(second.request)
    assert second.request.messages[:-2] == req.messages[:-2]
    assert second.request.messages[-1] == req.messages[-1]
    assert second.request.tools == req.tools
    assert second.count.mode == "estimated"
    assert second.count.tokens > len(second.page.content) + len("sibling body")


def test_no_fit_does_not_consume_cursor_and_retry_progresses():
    body = "x" * 10000
    first = run_page(body, open_window(body, selection(body)))
    cursor = first.page.next_cursor
    window, _ = decode_cursor(cursor, binding=BINDING, key=KEY, now=2)
    with pytest.raises(MemoryError, match="^context_capacity_too_small$"):
        run_page(body, window, ceiling=100)
    assert decode_cursor(cursor, binding=BINDING, key=KEY, now=2)[0] == window
    retry = run_page(body, window)
    assert retry.page.start == first.page.end and retry.page.end > first.page.end


def test_current_counter_and_profile_mismatch_fail_closed():
    body = "abc"
    window = open_window(body, selection(body))
    bad_identity = CounterIdentity("fixture-character", "1", "estimated", "other-profile")
    with pytest.raises(CompactionError, match="^profile_changed$"):
        run_page(body, window, identity=bad_identity)

    class ForgedCounter(CharacterCounter):
        def count(self, req, conn):
            return replace(super().count(req, conn), counter_version="forged")

    with pytest.raises(CompactionError, match="^counter_changed_or_invalid$"):
        run_page(body, window, counter=ForgedCounter())


def test_full_batch_and_output_capacity_validation():
    req = request()
    body = "abc"
    window = open_window(body, selection(body))
    with pytest.raises(MemoryError, match="invalid_history_framing"):
        run_page(body, window, req=replace(req, messages=req.messages[:-1]), tool_call_id="C1")
    with pytest.raises(CompactionError, match="capacity_profile_mismatch"):
        run_page(body, window, conn=replace(connection(), context_window_tokens=1000),
                 capacity=capacity_for(connection(), req, CompactionPolicy(),
                                       input_ceiling=2000, safety_margin=0))


def test_nonmonotonic_counter_recounts_every_candidate():
    class Nonmonotonic(CharacterCounter):
        def count(self, req, conn):
            counted = super().count(req, conn)
            size = len(json.loads(req.messages[-2].content)["content"])
            return replace(counted, tokens=counted.tokens + (5000 if size == 1500 else 0))
    counter = Nonmonotonic()
    body = "x" * 6000
    result = run_page(body, open_window(body, selection(body)), counter=counter)
    assert len(result.page.content) == 750
    assert result.count.tokens <= 12000
    assert result.count.tokens - result.baseline_count.tokens <= 2000
    assert len(counter.seen) == 8


def test_budget_record_changes_per_dispatch_without_secret_fingerprint():
    body = "x" * 4000
    window = open_window(body, selection(body))
    one = run_page(body, window)
    two = run_page(body, window, req=request("C2"), conn=connection("profile2"))
    assert one.tool_call_id == "C1" and two.tool_call_id == "C2"
    assert one.counting_profile_sha256 != two.counting_profile_sha256
    secret_only = replace(connection(), api_key="credential-must-not-enter-profile")
    assert run_page(body, window, conn=secret_only).counting_profile_sha256 == one.counting_profile_sha256


def test_codepoint_ceiling_and_exhausted_terminal_window():
    class LowCostCounter(CharacterCounter):
        def count(self, req, conn):
            value = super().count(req, conn)
            return replace(value, tokens=value.tokens // 100)
    body = "😀" * 40000
    window = open_window(body, selection(body))
    result = run_page(body, window, counter=LowCostCounter())
    assert result.page.end == 16000
    assert len(result.page.content.encode("utf-8")) == 64000
    with pytest.raises(MemoryError, match="history_window_complete"):
        run_page(body, replace(window, next_start=len(body)))


@pytest.mark.parametrize("start,end", [(True, 2), (0, False), (-1, 2), (2, 2), (3, 2)])
def test_strict_span_integer_bounds(start, end):
    with pytest.raises(MemoryError):
        TextSpan(start, end)


def test_identical_cursor_retry_is_deterministic():
    body = "original\r\n" * 1000
    one = run_page(body, open_window(body, selection(body)))
    window, expiry = decode_cursor(one.page.next_cursor, binding=BINDING, key=KEY, now=2)
    a = run_page(body, window, expires_at=expiry)
    b = run_page(body, window, expires_at=expiry)
    assert a == b
    assert a.page.selection == one.page.selection
