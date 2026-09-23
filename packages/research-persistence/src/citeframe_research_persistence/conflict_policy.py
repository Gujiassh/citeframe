"""Frozen v4 conflict investigation bounds."""
INVESTIGATION_WORKFLOW_ID = "40000000-0000-4000-8000-000000000001"
INVESTIGATION_SCHEMA_VERSION = "research-agent-results-v3"
MAX_INVESTIGATION_SEARCHES = 2
MAX_INVESTIGATION_OPERATIONS = 12


def investigation_step(step, snapshot):
    return (snapshot is not None and snapshot.workflow_version_id == INVESTIGATION_WORKFLOW_ID
            and step.step_kind == "conflict_decision_gate" and step.branch_key is None)
