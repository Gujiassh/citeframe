"""Link received wire bytes to one persisted send, then to local attempt pairs."""
from datetime import datetime
from hashlib import sha256
from itertools import combinations
import json


def _unix_ns(value):
    instant = datetime.fromisoformat(value)
    return int(instant.timestamp()) * 1_000_000_000 + instant.microsecond * 1000


def canonical_request(node, body):
    payload = {"nodeKey": node, "messages": body["input"], "maxOutputTokens": body["max_output_tokens"]}
    return sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def linked_parallel_evidence(facts, timeline):
    result = {"maxActive": timeline.get("maxActive", 0), "providerEntries": len(timeline.get("entries", [])),
              "consumerAttemptPairs": [], "providerOverlapPairs": [], "requestLinks": [], "linkErrors": []}
    try:
        _link(facts, timeline, result)
    except (KeyError, TypeError, ValueError, AssertionError) as error:
        result["linkErrors"].append(str(error))
        result["consumerAttemptPairs"] = []
        result["providerOverlapPairs"] = []
    return result


def _link(facts, timeline, result):
    from .oracles import assert_execution_policy
    assert_execution_policy(facts)
    run = facts["run"]
    steps = {s["id"]: s for s in facts["steps"]}
    attempts = {a["id"]: a for a in facts["attempts"]}
    calls = [c for c in facts["providerCalls"] if c["sent_at"] is not None]
    entries = {e["sequence"]: e for e in timeline["entries"]}
    assert len(entries) == len(timeline["entries"]), "duplicate_timeline_sequence"
    proofs = timeline["requestProofs"]
    assert len({p["sequence"] for p in proofs["entries"]}) == len(proofs["entries"]), "duplicate_request_proof"
    assert set(entries) == {p["sequence"] for p in proofs["entries"]}, "missing_request_proof"
    used = set()
    linked = []
    for proof in proofs["entries"]:
        entry = entries[proof["sequence"]]
        assert proof["epoch"] == proofs["epoch"], "foreign_proof_epoch"
        for key in ("node", "requestSha256", "startedAtNs"):
            assert proof[key] == entry[key], "wire_timeline_mismatch"
        body = json.loads(proof["rawBody"])
        assert sha256(proof["rawBody"].encode()).hexdigest() == entry["requestSha256"], "wire_hash_mismatch"
        assert entry["startedAtNs"] < entry["finishedAtNs"], "invalid_interval"
        if entry["node"] == "embedding":
            assert proof["path"] in {"/api/embed", "/api/embeddings"}, "generation_mislabeled_embedding"
            continue
        assert proof["path"] == "/v1/responses", "unexpected_generation_protocol"
        digest = canonical_request(entry["node"], body)
        candidates = [c for c in calls if c["request_sha256"] == digest
            and c["logical_call_key"] == entry["node"] + ":" + digest
            and c["model"] == body["model"] and c["reserved_output_tokens"] == body["max_output_tokens"]
            and _unix_ns(c["sent_at"]) <= proof["receivedAtUnixNs"] <= _unix_ns(c["finished_at"])]
        assert len(candidates) == 1, "missing_or_ambiguous_persisted_send"
        call = candidates[0]
        assert call["id"] not in used, "duplicate_send_mapping"
        used.add(call["id"])
        attempt, step = attempts[call["attempt_id"]], steps[call["step_id"]]
        assert attempt["step_id"] == step["id"] and step["step_kind"] == entry["node"], "request_attempt_step_mismatch"
        assert all(r["run_id"] == run["id"] and r["workspace_id"] == run["workspace_id"] for r in (call, step)), "foreign_request_scope"
        assert attempt["workspace_id"] == run["workspace_id"], "foreign_attempt_scope"
        assert _unix_ns(attempt["started_at"]) <= proof["receivedAtUnixNs"] <= _unix_ns(attempt["finished_at"]), "request_outside_attempt"
        result["requestLinks"].append({"sequence": entry["sequence"], "wireSha256": entry["requestSha256"],
            "ledgerSha256": digest, "providerCallId": call["id"], "attemptId": attempt["id"],
            "stepId": step["id"], "runId": run["id"]})
        if entry["node"] == "researcher":
            linked.append((entry, attempt, step))
    assert used == {c["id"] for c in calls} and used, "unproven_persisted_sends"
    for (ea, a, sa), (eb, b, sb) in combinations(linked, 2):
        if (a["worker_instance_id"] != b["worker_instance_id"] and a["id"] != b["id"]
            and sa["branch_key"] != sb["branch_key"]
            and max(_unix_ns(a["started_at"]), _unix_ns(b["started_at"]))
                < min(_unix_ns(a["finished_at"]), _unix_ns(b["finished_at"]))
            and max(ea["startedAtNs"], eb["startedAtNs"]) < min(ea["finishedAtNs"], eb["finishedAtNs"])):
            result["consumerAttemptPairs"].append([a["id"], b["id"]])
            result["providerOverlapPairs"].append([ea["sequence"], eb["sequence"]])
