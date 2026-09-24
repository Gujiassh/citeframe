"""Version/role/journal rejection controls for the default-v4 deployment fixture."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from citeframe_evaluation.acceptance.conflicts import assert_fixture_investigation, assert_role_step, digest
from citeframe_evaluation.acceptance.workflow import release_contract, wait_plan_boundary
from ai_pdf_api.services.research.research_prompt_provenance import (
    V2_WORKFLOW_VERSION_ID, V3_WORKFLOW_VERSION_ID, V4_WORKFLOW_VERSION_ID,
    V2_RELEASE_ID, V3_RELEASE_ID, V4_RELEASE_ID, V4_PROMPT_VERSION_IDS,
)


def test_current_release_is_explicit_and_historical_contracts_remain():
    assert release_contract(V2_WORKFLOW_VERSION_ID)[0] == V2_RELEASE_ID
    assert release_contract(V3_WORKFLOW_VERSION_ID)[0] == V3_RELEASE_ID
    assert release_contract(V4_WORKFLOW_VERSION_ID) == (V4_RELEASE_ID, V4_PROMPT_VERSION_IDS)
    with pytest.raises(AssertionError, match="unknown_workflow_release"):
        release_contract("unknown")


@pytest.mark.parametrize("status", ["awaiting_plan_approval", "awaiting_human_decision", "failed"])
def test_v4_never_substitutes_human_approval(status):
    with pytest.raises(AssertionError):
        wait_plan_boundary(lambda: dict(workflowId=V4_WORKFLOW_VERSION_ID, status=status, snapshotId=None),
                           lambda: pytest.fail("must not consume another step"))


def test_v4_boundary_needs_real_snapshot():
    with pytest.raises(TimeoutError):
        wait_plan_boundary(lambda: dict(workflowId=V4_WORKFLOW_VERSION_ID, status="queued", snapshotId=None),
                           lambda: pytest.fail("expired"), timeout_seconds=0)
    facts = dict(workflowId=V4_WORKFLOW_VERSION_ID, status="queued", snapshotId="approved")
    assert wait_plan_boundary(lambda: facts, lambda: pytest.fail("already approved")) == facts


@pytest.fixture
def proof():
    request = {"claims": [{"id": "claim", "text": "Conflicting", "evidenceHandleIds": ["source"]}],
               "evidence": [{"id": "source", "excerpt": "Immutable source"}]}
    result = {"inspections": [{"evidenceHandleId": "source", "quote": "Immutable source",
              "version": None, "environment": None, "time": None, "conditions": None}],
              "revisions": [], "nextQuery": None, "gaps": ["missing conditions"], "reason": "Source conditions remain unknown."}
    outcome = {"resolved": False, "reason": "insufficient_evidence", "revisions": [], "queries": [],
               "gaps": result["gaps"], "inspections": result["inspections"],
               "originalClaims": request["claims"], "evidence": request["evidence"]}
    common = dict(step_id="gate", execution_snapshot_id="snapshot",
                  created_by_attempt_id="attempt", status="succeeded")
    turns = []
    for n,(phase,req,res) in enumerate([("inspect",request,result),("finish",{"conflictClaimIds":["claim"]},outcome)]):
        turns.append(dict(common, phase=phase,operation_number=n,request_json=req,result_json=res,
                          request_sha256=digest(req),result_sha256=digest(res)))
    return dict(run=dict(id="run", workspace_id="workspace"), conflictTurns=turns,
        snapshots=[dict(id="snapshot", workflow_version_id=V4_WORKFLOW_VERSION_ID, run_id="run", workspace_id="workspace")],
        steps=[dict(id="gate", step_kind="conflict_decision_gate", status="succeeded",run_id="run",workspace_id="workspace",
                    execution_snapshot_id="snapshot",input_sha256="input",current_attempt_number=1)],
        attempts=[dict(id="attempt",step_id="gate",workspace_id="workspace",status="succeeded",input_sha256="input",attempt_number=1)])


def test_fixture_journal_and_actual_role_link(proof):
    assert len(assert_fixture_investigation(proof, required=True)) == 2
    body = {"input": [{"role": "user", "content": json.dumps({"investigation": proof["conflictTurns"][0]["request_json"]})}]}
    assert_role_step(proof, proof["steps"][0], proof["attempts"][0], "investigator", body)
    for field in ("created_by_attempt_id", "step_id", "execution_snapshot_id", "request_sha256"):
        changed = deepcopy(proof)
        changed["conflictTurns"][0][field] = "foreign"
        with pytest.raises(AssertionError, match="unproven_investigator_send"):
            assert_role_step(changed, changed["steps"][0], changed["attempts"][0], "investigator", body)
    with pytest.raises(AssertionError, match="request_attempt_step_mismatch"):
        assert_role_step(proof, proof["steps"][0], proof["attempts"][0], "critic", body)
    proof["snapshots"][0]["workflow_version_id"] = V3_WORKFLOW_VERSION_ID
    with pytest.raises(AssertionError, match="investigator_wrong_release"):
        assert_role_step(proof, proof["steps"][0], proof["attempts"][0], "investigator", body)


@pytest.mark.parametrize("mutation", ["missing", "hash", "origin", "release", "resolved", "input", "phase"])
def test_fixture_journal_rejects_missing_or_forged_completion(proof, mutation):
    if mutation == "missing": proof["conflictTurns"] = []
    elif mutation == "hash": proof["conflictTurns"][0]["result_json"]["gaps"] = []
    elif mutation == "origin": proof["attempts"][0]["step_id"] = "foreign"
    elif mutation == "release": proof["snapshots"][0]["workflow_version_id"] = V3_WORKFLOW_VERSION_ID
    elif mutation == "resolved":
        turn = proof["conflictTurns"][-1]
        turn["result_json"]["resolved"] = True
        turn["result_sha256"] = digest(turn["result_json"])
    elif mutation == "input": proof["attempts"][0]["input_sha256"] = "foreign"
    else: proof["conflictTurns"][0]["phase"] = "verify"
    with pytest.raises(AssertionError):
        assert_fixture_investigation(proof, required=True)


def test_http_fixture_investigator_contract_is_source_backed_and_bounded(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "apps/api/scripts"))
    monkeypatch.syspath_prepend(str(root / "infra/testing"))
    from r800_provider_proofs import ProofHandler, stub
    from citeframe_research_persistence.conflict_contract import INVESTIGATOR_SCHEMA, validate_investigation
    request = {"claims": [{"id":"claim","evidenceHandleIds":["source"]}], "evidence": [{"id":"source","excerpt":"Original excerpt"}]}
    payload = {"investigation":request, "resultSchema":INVESTIGATOR_SCHEMA}
    body = {"input":[{"role":"user","content":json.dumps(payload)}]}
    result = json.loads(ProofHandler._generation_output(body)["output_text"])
    validate_investigation(result,claims=request["claims"],evidence=request["evidence"])
    assert result["revisions"] == [] and result["nextQuery"] is None and result["gaps"]
    assert result["inspections"][0]["quote"] == "Original excerpt"
    payload["resultSchema"] = {"required":["unknown"]}
    body["input"][0]["content"] = json.dumps(payload)
    with pytest.raises(AssertionError, match="unknown_investigator_contract"):
        ProofHandler._generation_output(body)


@pytest.mark.parametrize("mutation", ["quote", "conditions", "missing_source", "unknown_field", "finish_claims"])
def test_fixture_journal_rejects_rehashed_semantic_forgery(proof, mutation):
    inspect, finish = proof["conflictTurns"]
    if mutation == "finish_claims":
        finish["request_json"] = {"conflictClaimIds": ["foreign"]}
        finish["request_sha256"] = digest(finish["request_json"])
    elif mutation in {"quote", "conditions"}:
        for turn in (inspect, finish):
            turn["result_json"]["inspections"][0][mutation] = "FABRICATED NOT IN SOURCE"
    elif mutation == "missing_source":
        for turn in (inspect, finish):
            turn["result_json"]["inspections"] = []
    else:
        inspect["result_json"]["unrecognized"] = True
    for turn in (inspect, finish):
        turn["result_sha256"] = digest(turn["result_json"])
    with pytest.raises(AssertionError):
        assert_fixture_investigation(proof, required=True)


def test_nullable_step_input_uses_the_persisted_attempt_fallback(proof):
    from hashlib import sha256
    proof["steps"][0]["input_sha256"] = None
    proof["attempts"][0]["input_sha256"] = sha256(b"gate").hexdigest()
    assert_fixture_investigation(proof, required=True)
