"""Issue 25 version-default and journal oracle, independent of the R2 delta."""

from copy import deepcopy
import hashlib
import json
from a2a_current_acceptance import assert_current_completion
from ai_pdf_api.services.research.research_prompt_provenance import (
    V3_WORKFLOW_VERSION_ID,
    V3_PROMPT_VERSION_IDS,
    V4_WORKFLOW_VERSION_ID,
    V4_PROMPT_VERSION_IDS,
)


def assert_v3_restored(rows, objects, api_payload_bytes, workflow, source):
    assert source["sourceHead"] == "b1f7423e5595d81d408d89de4ca565825e5c4e3b"
    assert workflow["workflowId"] == V3_WORKFLOW_VERSION_ID
    assert workflow["currentDefaultWorkflowId"] == V4_WORKFLOW_VERSION_ID
    assert workflow["currentDefaultAgentSchema"] == "research-agent-results-v3"
    for key in (
        "workflowId",
        "workflowVersion",
        "releaseId",
        "manifestSha256",
        "agentResultSchemaVersion",
        "prompts",
    ):
        assert workflow[key] == source["workflowEvidence"][key], key
    assert rows["research_conflict_turns"] == []
    projected = deepcopy(workflow)
    projected["currentDefaultWorkflowId"] = V3_WORKFLOW_VERSION_ID
    projected["currentDefaultAgentSchema"] = workflow["agentResultSchemaVersion"]
    assert_current_completion(rows, objects, api_payload_bytes, projected)


def assert_v4_completion(rows, objects, api_payload_bytes, workflow):
    assert (
        workflow["workflowId"]
        == workflow["currentDefaultWorkflowId"]
        == V4_WORKFLOW_VERSION_ID
    )
    assert workflow["workflowVersion"] == 4
    assert {p["id"] for p in workflow["prompts"]} == set(V4_PROMPT_VERSION_IDS.values())
    assert {p["version"] for p in workflow["prompts"]} == {4}
    assert (
        workflow["agentResultSchemaVersion"]
        == workflow["currentDefaultAgentSchema"]
        == "research-agent-results-v3"
    )
    assert workflow["result"] == "completed" and len(api_payload_bytes) == 1
    turns = sorted(rows["research_conflict_turns"], key=lambda r: r["operation_number"])
    assert [t["phase"] for t in turns] == ["inspect", "search", "finish"]
    assert all(t["status"] == "succeeded" for t in turns)
    assert [t["operation_number"] for t in turns] == [0, 1, 2]
    gate = next(
        s for s in rows["research_steps"] if s["step_kind"] == "conflict_decision_gate"
    )
    attempts = {a["id"]: a for a in rows["research_step_attempts"]}
    assert all(
        t["step_id"] == gate["id"]
        and t["execution_snapshot_id"] == gate["execution_snapshot_id"]
        and attempts[t["created_by_attempt_id"]]["step_id"] == gate["id"]
        and attempts[t["created_by_attempt_id"]]["status"] == "succeeded"
        for t in turns
    )

    def decode(v):
        return json.loads(v) if isinstance(v, str) else v

    for t in turns:
        for field in ("request", "result"):
            value = decode(t[field + "_json"])
            canonical = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            assert hashlib.sha256(canonical).hexdigest() == t[field + "_sha256"]
    outcome = decode(turns[-1]["result_json"])
    assert outcome["resolved"] is False and outcome["reason"] == "no_new_evidence"
    assert outcome["gaps"] and outcome["queries"] and not outcome["revisions"]
    assert outcome["evidence"] and outcome["inspections"]
    handles = {h["id"]: h for h in rows["research_evidence_handles"]}
    sources = {e["id"]: e for e in rows["research_evidence_snapshots"]}
    for evidence in outcome["evidence"]:
        handle = handles[evidence["id"]]
        source = sources[handle["evidence_snapshot_id"]]
        assert evidence["excerpt"] == source["excerpt_snapshot"]
        assert (
            evidence["source_fingerprint_sha256"] == source["source_fingerprint_sha256"]
        )
        assert handle["execution_snapshot_id"] == gate["execution_snapshot_id"]
    assert outcome["queries"] == [
        " ".join(decode(turns[1]["request_json"])["query"].split()).casefold()
    ]
    assert all(
        i[k] is None
        for i in outcome["inspections"]
        for k in ("version", "environment", "time", "conditions")
    )
    assert {c["id"] for c in outcome["originalClaims"]} == {
        c["id"] for c in rows["research_claims"]
    }
    projected = deepcopy(workflow)
    projected.update(
        workflowId=V3_WORKFLOW_VERSION_ID,
        currentDefaultWorkflowId=V3_WORKFLOW_VERSION_ID,
        workflowVersion=3,
        prompts=[{"id": v, "version": 3} for v in V3_PROMPT_VERSION_IDS.values()],
    )
    # The v3 completion assertions cover unchanged policy decisions/publication;
    # all v4 identities and journal changes are asserted above before projection.
    assert_current_completion(rows, objects, api_payload_bytes, projected)
    artifact = next(
        a for a in rows["research_artifacts"] if a["artifact_kind"] == "final_report"
    )
    payload = objects[artifact["object_key"]]
    assert b"## Conflict investigation" in payload and b"no_new_evidence" in payload
    assert b"### Sources inspected" in payload and b"### Important gaps" in payload
