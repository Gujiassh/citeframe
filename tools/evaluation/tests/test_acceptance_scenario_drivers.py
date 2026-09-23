"""Executable negative controls for the raw-evidence acceptance contract."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from citeframe_evaluation.acceptance import drivers
from citeframe_evaluation.acceptance.controls import mutation_controls, policy_mutations
from citeframe_evaluation.acceptance.oracles import (
    assert_execution_policy, parallel_evidence, parallel_passed, reclaim_passed,
)


@pytest.fixture
def facts():
    return json.loads((Path(__file__).parent / "fixtures/scenario-policy-facts.json").read_text(encoding="utf-8"))


def test_policy_uses_real_call_caps_not_cumulative_token_usage(facts):
    ledger = next(r for r in facts["ledgers"] if r["execution_snapshot_id"] is not None)
    snapshot = next(r for r in facts["snapshots"] if r["id"] == ledger["execution_snapshot_id"])
    assert ledger["actual_output_tokens"] > snapshot["max_output_tokens"]
    assert_execution_policy(facts)
    for name, mutated in policy_mutations(facts):
        with pytest.raises(AssertionError):
            assert_execution_policy(mutated)
        assert name


def overlapping(facts):
    steps = {s["id"]: s for s in facts["steps"]}
    candidates = [a for a in facts["attempts"] if steps[a["step_id"]]["step_kind"] == "researcher"
                  and a["status"] == "succeeded"]
    for index, a in enumerate(candidates):
        a.update(worker_instance_id=f"test-consumer-{index}", started_at="2026-09-24T00:00:00+00:00",
                 finished_at="2026-09-24T00:00:01+00:00")
    timeline = {"maxActive": 2, "entries": [
        {"node": "researcher", "sequence": 1, "startedAtNs": 1, "finishedAtNs": 4},
        {"node": "researcher", "sequence": 2, "startedAtNs": 2, "finishedAtNs": 5},
    ]}
    return timeline


def reclaim_pair(facts):
    step = next(s for s in facts["steps"] if s["step_kind"] == "researcher")
    attempt = deepcopy(next(a for a in facts["attempts"] if a["step_id"] == step["id"]))
    attempt.update(status="running", attempt_number=1)
    snapshot = next(s for s in facts["snapshots"] if s["id"] == step["execution_snapshot_id"])
    expected = {"step": deepcopy(step), "snapshot": deepcopy(snapshot), "attempts": [attempt]}
    observed = deepcopy(expected)
    observed["attempts"][0]["status"] = "abandoned"
    second = {**attempt, "id": "test-new-attempt", "attempt_number": 2, "status": "succeeded"}
    observed["attempts"].append(second)
    return expected, observed


def test_concurrency_requires_raw_overlap_and_distinct_consumers(facts):
    timeline = overlapping(facts)
    assert parallel_passed(parallel_evidence(facts, timeline))
    timeline["entries"][1].update(startedAtNs=6, finishedAtNs=8)
    assert not parallel_passed(parallel_evidence(facts, timeline))
    timeline = overlapping(facts)
    for a in facts["attempts"]:
        a["worker_instance_id"] = "same-consumer"
    assert not parallel_passed(parallel_evidence(facts, timeline))


def test_mutation_controls_execute_all_rejections(facts):
    timeline = overlapping(facts)
    expected, observed = reclaim_pair(facts)
    result = mutation_controls({"facts": facts, "providerTimeline": timeline},
                               {"expected": expected, "observed": observed})
    assert len(result["checks"]) == 10
    assert all(c["rejected"] for c in result["checks"].values())


@pytest.mark.parametrize("key", ["id", "run_id", "workspace_id", "execution_snapshot_id", "input_sha256"])
def test_reclaim_rejects_identity_drift(facts, key):
    expected, observed = reclaim_pair(facts)
    assert reclaim_passed(expected, observed)
    observed["step"][key] = "foreign"
    assert not reclaim_passed(expected, observed)


def test_bounded_wait_does_not_accept_other_step_success(monkeypatch, facts):
    expected, observed = reclaim_pair(facts)
    current = deepcopy(expected)
    current["attempts"][0]["status"] = "abandoned"
    class Processor:
        calls = 0
        def process_one(self):
            self.calls += 1
            return True  # a different step finished, original-step observation unchanged
    processor = Processor()
    monkeypatch.setattr(drivers.time, "monotonic", lambda: float(processor.calls))
    result, observations = drivers.wait_for_reclaim(processor, lambda: current,
        lambda f: reclaim_passed(expected, f), timeout_seconds=2)
    assert processor.calls == 2 and observations == 3
    assert not reclaim_passed(expected, result)
    processor.calls = 0
    result, _ = drivers.wait_for_reclaim(processor,
        lambda: observed if processor.calls >= 2 else current,
        lambda f: reclaim_passed(expected, f), timeout_seconds=3)
    assert processor.calls == 2 and reclaim_passed(expected, result)
