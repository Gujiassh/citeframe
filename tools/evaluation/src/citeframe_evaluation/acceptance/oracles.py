"""Acceptance decisions derived from raw intervals and persisted identity chains."""
from datetime import datetime
from itertools import combinations


def parallel_evidence(facts, timeline):
    run = facts["run"]
    steps = {r["id"]: r for r in facts["steps"]}
    attempts = [a for a in facts["attempts"] if steps[a["step_id"]]["step_kind"] == "researcher"]
    pairs = []
    for a, b in combinations(attempts, 2):
        sa, sb = steps[a["step_id"]], steps[b["step_id"]]
        if (a["worker_instance_id"] != b["worker_instance_id"]
            and sa["branch_key"] != sb["branch_key"] and a["finished_at"] and b["finished_at"]
            and all(s["run_id"] == run["id"] and s["workspace_id"] == run["workspace_id"] for s in (sa, sb))
            and all(x["workspace_id"] == run["workspace_id"] for x in (a, b))
            and max(datetime.fromisoformat(a["started_at"]), datetime.fromisoformat(b["started_at"]))
                < min(datetime.fromisoformat(a["finished_at"]), datetime.fromisoformat(b["finished_at"]))):
            pairs.append([a["id"], b["id"]])
    entries = [e for e in timeline["entries"] if e["node"] == "researcher"]
    overlaps = [[a["sequence"], b["sequence"]] for a, b in combinations(entries, 2)
                if max(a["startedAtNs"], b["startedAtNs"]) < min(a["finishedAtNs"], b["finishedAtNs"])]
    return {"maxActive": timeline["maxActive"], "providerEntries": len(timeline["entries"]),
            "consumerAttemptPairs": pairs, "providerOverlapPairs": overlaps}


def parallel_passed(evidence):
    return (evidence["maxActive"] >= 2 and bool(evidence["consumerAttemptPairs"])
            and bool(evidence["providerOverlapPairs"]))


def reclaim_passed(expected, facts):
    before, after = expected["step"], facts["step"]
    for key in ("id", "run_id", "workspace_id", "execution_snapshot_id", "input_sha256"):
        if before[key] != after[key]:
            return False
    old_snapshot, snapshot = expected["snapshot"], facts["snapshot"]
    if any(old_snapshot[k] != snapshot[k] for k in ("id", "run_id", "workspace_id", "execution_snapshot_sha256")):
        return False
    if (snapshot["id"] != after["execution_snapshot_id"] or snapshot["run_id"] != after["run_id"]
        or snapshot["workspace_id"] != after["workspace_id"]):
        return False
    original = expected["attempts"][-1]
    attempts = facts["attempts"]
    old = next((a for a in attempts if a["id"] == original["id"]), None)
    if old is None or old["status"] != "abandoned" or old["attempt_number"] != original["attempt_number"]:
        return False
    if any(a["step_id"] != after["id"] or a["workspace_id"] != after["workspace_id"]
           or a["input_sha256"] != original["input_sha256"] for a in attempts):
        return False
    return any(a["id"] != old["id"] and a["attempt_number"] == old["attempt_number"] + 1
               and a["status"] == "succeeded" and a["attempt_number"] <= after["max_attempts_snapshot"]
               for a in attempts)


def assert_execution_policy(facts):
    """C4 limits calls and per-call context; cumulative tokens are usage only."""
    run = facts["run"]
    assert run["status"] == "completed", "run_not_completed"
    assert len(facts["finals"]) == 1, "duplicate_or_missing_final"
    assert any(m["user_id"] == run["created_by_user_id"] and m["workspace_id"] == run["workspace_id"]
               for m in facts["memberships"]), "creator_permission_missing"
    steps = {s["id"]: s for s in facts["steps"]}
    attempts = {a["id"]: a for a in facts["attempts"]}
    snapshots = {s["id"]: s for s in facts["snapshots"]}
    plans = {p["id"]: p for p in facts["plans"]}
    for name in ("steps", "snapshots", "plans", "ledgers", "providerCalls", "toolCalls", "finals"):
        assert all(r["run_id"] == run["id"] and r["workspace_id"] == run["workspace_id"]
                   for r in facts[name]), "cross_scope_" + name
    for a in attempts.values():
        s = steps[a["step_id"]]
        assert a["workspace_id"] == s["workspace_id"], "attempt_workspace_mismatch"
        assert 1 <= a["attempt_number"] <= s["max_attempts_snapshot"], "attempt_cap_exceeded"
    for calls in (facts["providerCalls"], facts["toolCalls"]):
        for c in calls:
            assert c["attempt_id"] in attempts and c["step_id"] == attempts[c["attempt_id"]]["step_id"], "call_attempt_mismatch"
    for ledger in facts["ledgers"]:
        if ledger["execution_snapshot_id"] is not None:
            limits = snapshots[ledger["execution_snapshot_id"]]
            prefix = ""
            tools = [c for c in facts["toolCalls"] if c["execution_snapshot_id"] == limits["id"]]
            assert ledger["actual_tool_calls"] == sum(c["status"] not in {"requested", "running"} for c in tools), "tool_accounting_mismatch"
            assert ledger["reserved_tool_calls"] == sum(c["status"] in {"requested", "running"} for c in tools), "tool_reservation_mismatch"
            assert ledger["actual_tool_calls"] + ledger["reserved_tool_calls"] <= limits["max_tool_calls"], "tool_cap_exceeded"
        else:
            limits = plans[ledger["plan_revision_id"]]
            prefix = "planning_"
        calls = [c for c in facts["providerCalls"] if c["budget_ledger_id"] == ledger["id"]]
        assert ledger["actual_provider_calls"] == sum(c["sent_at"] is not None for c in calls), "provider_accounting_mismatch"
        assert ledger["reserved_provider_calls"] == sum(c["status"] == "reserved" for c in calls), "provider_reservation_mismatch"
        assert ledger["actual_provider_calls"] + ledger["reserved_provider_calls"] <= limits[prefix + "max_provider_calls"], "provider_cap_exceeded"
        for kind in ("input", "output"):
            key = kind + "_tokens"
            assert ledger["reserved_" + key] == sum(c["reserved_" + key] for c in calls if c["status"] in {"reserved", "sent"}), "token_reservation_mismatch"
            assert ledger["actual_" + key] == sum(c["actual_" + key] for c in calls if c["status"] in {"succeeded", "failed", "outcome_unknown"}), "token_accounting_mismatch"
            for c in calls:
                assert 0 <= c["reserved_" + key] <= limits[prefix + "max_" + key], "per_call_context_exceeded"
                if c["status"] == "succeeded":
                    assert 0 <= c["actual_" + key] <= limits[prefix + "max_" + key], "per_call_usage_exceeded"
    for s in snapshots.values():
        active = []
        for a in attempts.values():
            step = steps[a["step_id"]]
            if step["step_kind"] == "researcher" and step["execution_snapshot_id"] == s["id"]:
                assert a["finished_at"] is not None, "unfinished_researcher"
                active.extend([(datetime.fromisoformat(a["started_at"]), 1),
                               (datetime.fromisoformat(a["finished_at"]), -1)])
        count = 0
        for _, change in sorted(active):
            count += change
            assert count <= s["max_parallel_researchers"], "parallel_cap_exceeded"
