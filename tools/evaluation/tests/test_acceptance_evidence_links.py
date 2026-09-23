"""Hubble counterexamples plus complete, non-vacuous positive controls."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from test_acceptance_scenario_drivers import facts, overlapping, reclaim_pair
from citeframe_evaluation.acceptance.oracles import (
    assert_execution_policy, parallel_evidence, parallel_passed, reclaim_passed,
)
from citeframe_evaluation.acceptance.controls import parallel_mutations


def test_hubble_all_ledgers_and_calls_removed(facts):
    assert_execution_policy(facts)
    changed = deepcopy(facts)
    for key in ("ledgers", "providerCalls", "toolCalls"):
        changed[key] = []
    with pytest.raises(AssertionError, match="missing_ledgers"):
        assert_execution_policy(changed)


def test_hubble_frozen_body_changed_hash_unchanged(facts):
    expected, observed = reclaim_pair(facts)
    assert reclaim_passed(expected, observed)
    observed["snapshot"]["max_provider_calls"] += 1000
    assert not reclaim_passed(expected, observed)


def test_snapshot_hash_is_recomputed_even_when_both_copies_match(facts):
    expected, observed = reclaim_pair(facts)
    for obj in (expected, observed):
        obj["snapshot"]["execution_snapshot_sha256"] = "0" * 64
    assert not reclaim_passed(expected, observed)
    expected, observed = reclaim_pair(facts)
    for obj in (expected, observed):
        obj["snapshot"]["max_provider_calls"] += 1
        obj["snapshotProof"]["revision"]["proposed_max_provider_calls"] += 1
    assert not reclaim_passed(expected, observed)


def test_snapshot_requires_complete_children_and_fields(facts):
    for key in ("snapshotProof", "snapshot"):
        expected, observed = reclaim_pair(facts)
        observed.pop(key)
        assert not reclaim_passed(expected, observed)
    for child in ("assets", "prompts"):
        expected, observed = reclaim_pair(facts)
        for obj in (expected, observed):
            obj["snapshotProof"][child] = []
        assert not reclaim_passed(expected, observed)


def test_hubble_foreign_requests_cannot_supply_local_overlap(facts):
    local = overlapping(facts)
    assert parallel_passed(parallel_evidence(facts, local))
    foreign = {"maxActive": 2, "entries": [
        {"node": "researcher", "sequence": 1, "requestSha256": "foreign-request-A", "startedAtNs": 1, "finishedAtNs": 4},
        {"node": "researcher", "sequence": 2, "requestSha256": "foreign-request-B", "startedAtNs": 2, "finishedAtNs": 5}]}
    assert not parallel_passed(parallel_evidence(facts, foreign))
    for name, changed in parallel_mutations(local):
        assert not parallel_passed(parallel_evidence(facts, changed)), name


def test_identical_retry_digest_requires_unique_time_window(facts):
    timeline = overlapping(facts)
    steps = {s["id"]: s for s in facts["steps"]}
    calls = [c for c in facts["providerCalls"] if steps[c["step_id"]]["step_kind"] == "researcher"]
    first, second = calls[:2]
    p1, p2 = [next(p for p in timeline["requestProofs"]["entries"]
                  if json.loads(p["rawBody"])["input"][0]["content"] == "synthetic-" + c["id"])
              for c in (first, second)]
    second.update(request_sha256=first["request_sha256"], logical_call_key=first["logical_call_key"])
    p2.update(rawBody=p1["rawBody"], requestSha256=p1["requestSha256"])
    next(e for e in timeline["entries"] if e["sequence"] == p2["sequence"])["requestSha256"] = p2["requestSha256"]
    # Distinct windows map identical payloads; overlapping windows must be rejected, not assigned by list order.
    second.update(sent_at=first["sent_at"], finished_at=first["finished_at"])
    p2["receivedAtUnixNs"] = p1["receivedAtUnixNs"]
    result = parallel_evidence(facts, timeline)
    assert not parallel_passed(result)
    assert "missing_or_ambiguous_persisted_send" in result["linkErrors"]


def test_proof_server_captures_exact_wire_without_headers(monkeypatch):
    import sys
    import threading
    import urllib.request
    import time
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "apps/api/scripts"))
    monkeypatch.syspath_prepend(str(root / "infra/testing"))
    from r800_provider_proofs import create_server
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = "http://127.0.0.1:" + str(server.server_port)
    raw = b'{"model":"synthetic","input":["fixture"]}'
    try:
        urllib.request.urlopen(urllib.request.Request(origin + "/api/embed", data=raw,
            headers={"Content-Type": "application/json", "Authorization": "test-header-must-not-be-recorded"}), timeout=5).read()
        for _ in range(20):
            timeline = json.load(urllib.request.urlopen(origin + "/__r800__/control/timeline", timeout=5))
            if timeline["entries"]:
                break
            time.sleep(.01)
        proofs = json.load(urllib.request.urlopen(origin + "/__r800__/request-proofs", timeout=5))
        assert len(proofs["entries"]) == 1
        proof = proofs["entries"][0]
        assert proof["rawBody"].encode() == raw
        assert proof["requestSha256"] == timeline["entries"][0]["requestSha256"]
        assert proof["startedAtNs"] == timeline["entries"][0]["startedAtNs"]
        assert "test-header-must-not-be-recorded" not in json.dumps(proofs)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
