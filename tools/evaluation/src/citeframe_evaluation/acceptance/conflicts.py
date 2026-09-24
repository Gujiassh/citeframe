"""V4 fixture-specific journal and role proofs, separate from historical R2 equality."""
from hashlib import sha256
import json

from ai_pdf_api.services.research.research_prompt_provenance import V4_WORKFLOW_VERSION_ID


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()



def assert_journal_scope(facts, turn):
    """Journal ownership is established by persisted foreign keys, not extra row fields."""
    def linked(name, identity):
        matches = [r for r in facts[name] if r["id"] == identity]
        assert len(matches) == 1, "journal_missing_or_foreign_" + name
        return matches[0]

    run = facts["run"]
    step = linked("steps", turn["step_id"])
    snapshot = linked("snapshots", turn["execution_snapshot_id"])
    attempt = linked("attempts", turn["created_by_attempt_id"])
    assert step["step_kind"] == "conflict_decision_gate", "journal_wrong_step_kind"
    assert snapshot["id"] == step["execution_snapshot_id"], "journal_snapshot_mismatch"
    assert all(r["run_id"] == run["id"] and r["workspace_id"] == run["workspace_id"]
               for r in (step, snapshot)), "journal_foreign_scope"
    assert attempt["step_id"] == step["id"] and attempt["workspace_id"] == step["workspace_id"], "journal_foreign_attempt"
    expected_input = step["input_sha256"] or sha256(step["id"].encode()).hexdigest()
    assert attempt["input_sha256"] == expected_input, "journal_input_mismatch"
    assert 0 < attempt["attempt_number"] <= step["current_attempt_number"], "journal_future_attempt"
    return step, snapshot, attempt

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
               and t["execution_snapshot_id"] == snapshot["id"]]
    assert len(matches) == 1 and matches[0]["status"] == "succeeded", "unproven_investigator_send"
    assert_journal_scope(facts, matches[0])


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
    for turn in turns:
        assert turn["status"] == "succeeded"
        assert turn["step_id"] == gate["id"] and turn["execution_snapshot_id"] == snapshot["id"]
        _, _, attempt = assert_journal_scope(facts, turn)
        assert attempt["status"] == "succeeded"
        for field in ("request", "result"):
            assert turn[field + "_sha256"] == digest(turn[field + "_json"]), "altered_journal_payload"
    inspected, outcome = (t["result_json"] for t in turns)
    request = turns[0]["request_json"]
    from citeframe_research_persistence.conflict_contract import validate_investigation
    try:
        validate_investigation(inspected, claims=request["claims"], evidence=request["evidence"])
    except (ValueError, KeyError, TypeError) as error:
        raise AssertionError("invalid_investigation_sources:" + str(error)) from error
    claim_ids = [c["id"] for c in request["claims"]]
    assert claim_ids and len(set(claim_ids)) == len(claim_ids), "invalid_original_claim_set"
    assert turns[1]["request_json"] == {"conflictClaimIds": sorted(claim_ids)}, "finish_claims_mismatch"
    assert inspected["revisions"] == [] and inspected["nextQuery"] is None and inspected["gaps"]
    assert outcome["resolved"] is False and outcome["reason"] == "insufficient_evidence", "fixture_false_resolution"
    assert not outcome["revisions"] and not outcome["queries"] and outcome["gaps"]
    assert outcome["inspections"] == inspected["inspections"] and outcome["inspections"]
    assert outcome["originalClaims"] == turns[0]["request_json"]["claims"]
    assert outcome["evidence"] == turns[0]["request_json"]["evidence"]
    return turns
