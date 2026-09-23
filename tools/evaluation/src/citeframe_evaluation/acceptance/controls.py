"""Executed oracle mutations on copies of runtime evidence, never database writes."""
from copy import deepcopy
from .oracles import assert_execution_policy, parallel_evidence, parallel_passed, reclaim_passed


def policy_mutations(facts):
    mutated = deepcopy(facts)
    mutated["finals"].append(deepcopy(mutated["finals"][0]))
    yield "duplicate-final", mutated
    mutated = deepcopy(facts)
    mutated["memberships"] = [m for m in mutated["memberships"]
                              if m["user_id"] != mutated["run"]["created_by_user_id"]]
    yield "creator-permission-removed", mutated
    mutated = deepcopy(facts)
    ledger = next(r for r in mutated["ledgers"] if r["execution_snapshot_id"] is not None)
    snapshot = next(r for r in mutated["snapshots"] if r["id"] == ledger["execution_snapshot_id"])
    snapshot["max_provider_calls"] = ledger["actual_provider_calls"] - 1
    yield "provider-cap-exceeded", mutated
    mutated = deepcopy(facts)
    mutated["providerCalls"][0]["reserved_output_tokens"] = 10**12
    yield "single-call-context-exceeded", mutated
    mutated = deepcopy(facts)
    mutated["ledgers"][0]["actual_provider_calls"] += 1
    yield "provider-ledger-mismatch", mutated
    mutated = deepcopy(facts)
    ledger = next(r for r in mutated["ledgers"] if r["execution_snapshot_id"] is not None)
    ledger["reserved_tool_calls"] += 1
    yield "tool-reservation-mismatch", mutated


def mutation_controls(main, reclaim):
    facts, timeline = main["facts"], main["providerTimeline"]
    results = {}
    assert_execution_policy(facts)
    for name, changed in policy_mutations(facts):
        try:
            assert_execution_policy(changed)
        except AssertionError as error:
            results[name] = {"rejected": True, "reason": str(error)}
        else:
            raise AssertionError("negative_control_not_rejected:" + name)
    serial = deepcopy(timeline)
    for index, entry in enumerate(serial["entries"]):
        entry.update(startedAtNs=index * 10, finishedAtNs=index * 10 + 1)
    assert not parallel_passed(parallel_evidence(facts, serial)), "serial_raw_not_rejected"
    results["serial-intervals-with-unchanged-maxActive"] = {"rejected": True}
    expected, observed = reclaim["expected"], reclaim["observed"]
    assert reclaim_passed(expected, observed), "positive_reclaim_required"
    changed = deepcopy(observed)
    old_id = expected["attempts"][-1]["id"]
    other_id = next(s["id"] for s in facts["steps"] if s["id"] != changed["step"]["id"])
    for attempt in changed["attempts"]:
        if attempt["id"] != old_id:
            attempt["step_id"] = other_id
    assert not reclaim_passed(expected, changed), "different_step_not_rejected"
    results["different-step-success-only"] = {"rejected": True}
    changed = deepcopy(observed)
    next(a for a in changed["attempts"] if a["id"] == old_id)["status"] = "running"
    assert not reclaim_passed(expected, changed), "live_old_attempt_not_rejected"
    results["old-attempt-not-abandoned"] = {"rejected": True}
    changed = deepcopy(observed)
    changed["snapshot"]["execution_snapshot_sha256"] = "0" * 64
    assert not reclaim_passed(expected, changed), "snapshot_drift_not_rejected"
    results["snapshot-drift"] = {"rejected": True}
    return {"scope": "mutated copies of raw runtime facts; no database mutations", "checks": results}
