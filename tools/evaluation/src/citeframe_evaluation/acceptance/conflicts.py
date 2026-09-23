"""V4 fixture-specific journal and role proofs, separate from historical R2 equality."""
from hashlib import sha256
import json

from ai_pdf_api.services.research.research_prompt_provenance import V4_WORKFLOW_VERSION_ID


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def assert_role_step(facts, step, attempt, node, body):
    if step["step_kind"] == node:
        return
    assert step["step_kind"] == "conflict_decision_gate" and node == "investigator", "request_attempt_step_mismatch"
    snapshot = next(s for s in facts["snapshots"] if s["id"] == step["execution_snapshot_id"])
    assert snapshot["workflow_version_id"] == V4_WORKFLOW_VERSION_ID, "investigator_wrong_release"
    payload = json.loads(next(m["content"] for m in reversed(body["input"]) if m["role"] == "user"))
    request = payload["investigation"]
    matches = [t for t in facts["conflictTurns"] if t["step_id"] == step["id"]
               and t["phase"] == "inspect" and t["created_by_attempt_id"] == attempt["id"]
               and t["request_json"] == request and t["request_sha256"] == digest(request)
               and t["workspace_id"] == step["workspace_id"]
               and t["run_id"] == step["run_id"] and t["execution_snapshot_id"] == snapshot["id"]]
    assert len(matches) == 1 and matches[0]["status"] == "succeeded", "unproven_investigator_send"


def assert_fixture_investigation(facts, *, required):
    turns = sorted(facts["conflictTurns"], key=lambda t: t["operation_number"])
    if not required:
        assert not turns, "unexpected_fixture_investigation"
        return turns
    assert [t["phase"] for t in turns] == ["inspect", "finish"], "missing_fixture_journal"
    assert [t["operation_number"] for t in turns] == [0, 1]
    gate = next(s for s in facts["steps"] if s["step_kind"] == "conflict_decision_gate")
    assert gate["status"] == "succeeded"
    snapshot = next(s for s in facts["snapshots"] if s["id"] == gate["execution_snapshot_id"])
    assert snapshot["workflow_version_id"] == V4_WORKFLOW_VERSION_ID
    attempts = {a["id"]: a for a in facts["attempts"]}
    for turn in turns:
        assert turn["status"] == "succeeded"
        assert turn["step_id"] == gate["id"] and turn["execution_snapshot_id"] == snapshot["id"]
        assert turn["run_id"] == gate["run_id"] and turn["workspace_id"] == gate["workspace_id"]
        attempt = attempts[turn["created_by_attempt_id"]]
        assert attempt["step_id"] == gate["id"] and attempt["workspace_id"] == gate["workspace_id"]
        assert attempt["status"] == "succeeded" and attempt["input_sha256"] == gate["input_sha256"]
        for field in ("request", "result"):
            assert turn[field + "_sha256"] == digest(turn[field + "_json"]), "altered_journal_payload"
    inspected, outcome = (t["result_json"] for t in turns)
    assert inspected["revisions"] == [] and inspected["nextQuery"] is None and inspected["gaps"]
    assert outcome["resolved"] is False and outcome["reason"] == "insufficient_evidence", "fixture_false_resolution"
    assert not outcome["revisions"] and not outcome["queries"] and outcome["gaps"]
    assert outcome["inspections"] == inspected["inspections"] and outcome["inspections"]
    assert outcome["originalClaims"] == turns[0]["request_json"]["claims"]
    assert outcome["evidence"] == turns[0]["request_json"]["evidence"]
    return turns
