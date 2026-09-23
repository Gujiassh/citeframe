"""Policy decisions have explicit provenance and never impersonate a user."""
from .events import append_research_event


def submit_policy_decision(db, run, decision, *, action, now):
    decision.decision_origin = "policy"
    decision.status = "submitted"
    decision.action = action
    decision.decided_at = now
    decision.decided_by_user_id = None
    decision.comment_text = "research-autonomy-v1"
    decision.state_version += 1
    run.state_version += 1
    run.updated_at = now
    append_research_event(db, run, event_type="decision_submitted",
        dedupe_key=f"decision-submitted:{decision.id}", step_id=decision.gate_step_id,
        data={"decisionId": decision.id, "decisionType": decision.decision_type,
              "inputArtifactId": decision.input_artifact_id,
              "inputArtifactSha256": decision.input_artifact_sha256, "action": action,
              "actorUserId": None, "decisionOrigin": "policy", "policyId": "research-autonomy-v1", "decisionStateVersion": decision.state_version,
              "runStateVersion": run.state_version}, now=now)


def decision_origin_is_valid(decision, workflow_version_id):
    from .autonomy import AUTONOMOUS_WORKFLOW_ID
    from .conflict_policy import INVESTIGATION_WORKFLOW_ID
    if decision.decision_origin == "human":
        return bool(decision.decided_by_user_id)
    return (decision.decision_origin == "policy"
            and workflow_version_id in {AUTONOMOUS_WORKFLOW_ID, INVESTIGATION_WORKFLOW_ID}
            and decision.decided_by_user_id is None
            and decision.comment_text == "research-autonomy-v1")
