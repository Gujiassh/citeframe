"""Read persisted release bindings and observe policy transitions without deciding them."""
from time import monotonic, sleep
from sqlalchemy import select
from ai_pdf_api.models import (ResearchRun, ResearchPlanRevision, ResearchExecutionSnapshot,
    HumanDecision, ResearchEvent, ResearchClaim)
from ai_pdf_api.services.research.research_prompt_provenance import (
    load_v2_release, V2_WORKFLOW_VERSION_ID, V2_RELEASE_ID, V2_PROMPT_VERSION_IDS,
    V3_WORKFLOW_VERSION_ID, V3_RELEASE_ID, V3_PROMPT_VERSION_IDS,
)
from .evidence import row, snapshot_proof
from .snapshot_proofs import valid_snapshot


def release_contract(workflow_id):
    contracts = {V2_WORKFLOW_VERSION_ID: (V2_RELEASE_ID, V2_PROMPT_VERSION_IDS),
                 V3_WORKFLOW_VERSION_ID: (V3_RELEASE_ID, V3_PROMPT_VERSION_IDS)}
    assert workflow_id in contracts, "unknown_workflow_release"
    return contracts[workflow_id]


def workflow_facts(sessions, run_id):
    with sessions() as db:
        run = db.get(ResearchRun, run_id)
        assert run is not None
        revision = db.get(ResearchPlanRevision, run.current_plan_revision_id)
        assert revision.run_id == run.id and revision.workspace_id == run.workspace_id
        workflow_id = revision.proposed_workflow_version_id
        release, prompts = release_contract(workflow_id)
        workflow, bound_prompts = load_v2_release(db, workflow_id=workflow_id)
        assert workflow.created_by_release_id == release
        assert {key: p.id for key, p in bound_prompts.items()} == prompts
        assert revision.planner_prompt_version_id == prompts["planner"]
        result = {"runId": run.id, "status": run.status, "workflowId": workflow_id,
                  "release": release, "promptVersions": prompts, "snapshotId": None}
        if run.approved_execution_snapshot_id:
            snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
            assert (snapshot.run_id, snapshot.workspace_id, snapshot.approved_plan_revision_id) == (
                run.id, run.workspace_id, revision.id), "snapshot_request_binding_mismatch"
            proof = snapshot_proof(db, snapshot)
            assert snapshot.workflow_version_id == workflow_id
            assert valid_snapshot({"snapshot": row(snapshot), "snapshotProof": proof})
            assert {p["node_key"]: p["prompt_version_id"] for p in proof["prompts"]} == prompts
            decision = proof["decision"]
            assert (decision["id"], decision["run_id"], decision["workspace_id"],
                    decision["decision_type"], decision["input_snapshot_sha256"]) == (
                snapshot.approval_decision_id, run.id, run.workspace_id,
                "plan_approval", revision.planning_snapshot_sha256), "approval_request_binding_mismatch"
            if workflow_id == V3_WORKFLOW_VERSION_ID:
                assert decision["decision_origin"] == "policy" and decision["decided_by_user_id"] is None
                assert decision["status"] == "submitted" and decision["action"] == "approve"
            result["snapshotId"] = snapshot.id
        return result


def wait_plan_boundary(observe, process_one, *, timeout_seconds=90):
    deadline = monotonic() + timeout_seconds
    while True:
        facts = observe()
        release_contract(facts["workflowId"])
        if facts["workflowId"] == V2_WORKFLOW_VERSION_ID:
            if facts["status"] == "awaiting_plan_approval":
                assert facts["snapshotId"] is None
                return facts
        else:
            assert facts["status"] not in {"awaiting_plan_approval", "awaiting_human_decision"}, "policy_waited_for_human"
            if facts["snapshotId"] is not None:
                return facts
        assert facts["status"] not in {"failed", "cancelled", "completed"}, "plan_did_not_advance"
        if monotonic() >= deadline:
            raise TimeoutError("plan_boundary_timeout")
        if not process_one():
            sleep(0.05)


def assert_policy_completion(sessions, run_id, *, conflict_required=False):
    facts = workflow_facts(sessions, run_id)
    assert facts["workflowId"] == V3_WORKFLOW_VERSION_ID, "default_release_regressed"
    assert facts["status"] == "completed" and facts["snapshotId"] is not None
    with sessions() as db:
        decisions = list(db.scalars(select(HumanDecision).where(HumanDecision.run_id == run_id)))
        types = [d.decision_type for d in decisions]
        assert types.count("plan_approval") == 1
        assert set(types) <= {"plan_approval", "conflict_resolution"}
        assert types.count("conflict_resolution") == int(conflict_required)
        for d in decisions:
            assert d.decision_origin == "policy" and d.decided_by_user_id is None
            assert d.status == "submitted"
            assert d.action == ("approve" if d.decision_type == "plan_approval" else "keep_as_unresolved")
        events = list(db.scalars(select(ResearchEvent).where(
            ResearchEvent.run_id == run_id, ResearchEvent.event_type == "decision_submitted")))
        assert len(events) == len(decisions)
        assert {e.dedupe_key for e in events} == {"decision-submitted:" + d.id for d in decisions}
        for event in events:
            d = next(d for d in decisions if "decision-submitted:" + d.id == event.dedupe_key)
            assert event.event_schema_version == "2"
            assert event.payload_json == {
                "decisionId": d.id, "decisionType": d.decision_type,
                "inputArtifactId": d.input_artifact_id, "inputArtifactSha256": d.input_artifact_sha256,
                "action": d.action, "actorUserId": None, "decisionOrigin": "policy",
                "policyId": "research-autonomy-v1", "decisionStateVersion": d.state_version,
                "runStateVersion": event.payload_json["runStateVersion"],
            }
            assert isinstance(event.payload_json["runStateVersion"], int) and event.payload_json["runStateVersion"] > 0
        facts["decisions"] = [row(d) for d in decisions]
        facts["decisionEvents"] = [row(e) for e in events]
    return facts


def assert_conflict_partition(sessions, run_id, report):
    findings, unresolved = report.split("## Unresolved Evidence Conflicts")
    with sessions() as db:
        claims = list(db.scalars(select(ResearchClaim).where(
            ResearchClaim.run_id == run_id, ResearchClaim.conflict_status == "resolved_unresolved")))
        assert claims, "missing_conflict_claims"
        for claim in claims:
            assert claim.statement_text in unresolved and claim.statement_text not in findings
