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
    # Synthetic unit inputs only; runtime proofs are captured from received bytes by the test server.
    from hashlib import sha256
    from citeframe_evaluation.acceptance.request_proofs import canonical_request
    steps = {s["id"]: s for s in facts["steps"]}
    timeline = {"maxActive": 2, "entries": [], "requestProofs": {"epoch": 1, "entries": []}}
    for index, a in enumerate(facts["attempts"]):
        a.update(worker_instance_id=f"test-consumer-{index}", started_at="2026-09-24T00:00:00+00:00",
                 finished_at="2026-09-24T00:00:01+00:00")
    for a in facts["attempts"]:
        if a["status"] != "succeeded":
            a.update(started_at="2026-09-23T23:59:58+00:00", finished_at="2026-09-23T23:59:59+00:00")
    for index, c in enumerate(facts["providerCalls"]):
        node = steps[c["step_id"]]["step_kind"]
        body = {"model": c["model"], "input": [{"role": "user", "content": "synthetic-" + c["id"]}],
                "max_output_tokens": c["reserved_output_tokens"]}
        digest = canonical_request(node, body)
        c.update(request_sha256=digest, logical_call_key=node + ":" + digest,
                 sent_at="2026-09-24T00:00:00+00:00", finished_at="2026-09-24T00:00:01+00:00")
        attempt = next(a for a in facts["attempts"] if a["id"] == c["attempt_id"])
        c.update(sent_at=attempt["started_at"], finished_at=attempt["finished_at"])
        failed = attempt["status"] != "succeeded"
        raw = json.dumps(body)
        entry = {"node": node, "sequence": index + 1, "requestSha256": sha256(raw.encode()).hexdigest(),
                 "startedAtNs": 100 + index, "finishedAtNs": 200 + index}
        timeline["entries"].append(entry)
        timeline["requestProofs"]["entries"].append({**entry, "epoch": 1, "rawBody": raw,
            "path": "/v1/responses", "receivedAtUnixNs": 1790208000500000000 - (2000000000 if failed else 0)})
    return timeline


def reclaim_pair(facts):
    step = next(s for s in facts["steps"] if s["step_kind"] == "researcher")
    attempt = deepcopy(next(a for a in facts["attempts"] if a["step_id"] == step["id"]))
    attempt.update(status="running", attempt_number=1)
    snapshot = next(s for s in facts["snapshots"] if s["id"] == step["execution_snapshot_id"])
    expected = {"step": deepcopy(step), "snapshot": deepcopy(snapshot), "snapshotProof": json.loads((Path(__file__).parent / "fixtures/snapshot-proof.json").read_text())["snapshotProof"], "attempts": [attempt]}
    observed = deepcopy(expected)
    observed["attempts"][0]["status"] = "abandoned"
    second = {**attempt, "id": "test-new-attempt", "attempt_number": 2, "status": "succeeded"}
    observed["attempts"].append(second)
    return expected, observed


def test_concurrency_requires_raw_overlap_and_distinct_consumers(facts):
    timeline = overlapping(facts)
    assert parallel_passed(parallel_evidence(facts, timeline))
    for index, entry in enumerate(timeline["entries"]):
        entry.update(startedAtNs=index * 10, finishedAtNs=index * 10 + 1)
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
    assert len(result["checks"]) >= 20
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
