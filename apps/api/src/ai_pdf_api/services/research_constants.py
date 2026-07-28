from datetime import timedelta

from ai_pdf_api.services.research_prompt_provenance import (
    V2_PROMPT_SPECS,
    V2_PROMPT_VERSION_IDS,
    V2_RELEASE_ID,
    V2_WORKFLOW_VERSION_ID,
)

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
EVENT_TYPES = {
    "run_created", "run_status_changed", "step_queued", "step_started", "step_waiting",
    "step_succeeded", "step_failed", "attempt_abandoned", "approval_requested",
    "decision_submitted", "cancel_requested", "artifact_published", "run_completed",
    "run_failed", "run_cancelled",
}
EVENT_FIELDS = {
    "run_created": {"status", "createdByUserId", "runStateVersion"},
    "run_status_changed": {"previousStatus", "status", "runStateVersion", "reasonCode"},
    "step_queued": {
        "stepId", "stepKind", "branchKey", "attemptNumber", "stepStateVersion", "runStateVersion",
    },
    "step_started": {
        "stepId", "stepKind", "branchKey", "attemptId", "attemptNumber", "stepStateVersion", "runStateVersion",
    },
    "step_waiting": {
        "stepId", "stepKind", "decisionId", "decisionType", "stepStateVersion",
        "decisionStateVersion", "runStateVersion",
    },
    "step_succeeded": {
        "stepId", "stepKind", "attemptId", "attemptNumber", "evidenceCount", "artifactIds",
        "stepStateVersion", "runStateVersion",
    },
    "step_failed": {
        "stepId", "stepKind", "attemptId", "attemptNumber", "reasonCode", "retryable",
        "stepStateVersion", "runStateVersion",
    },
    "attempt_abandoned": {
        "stepId", "attemptId", "attemptNumber", "reasonCode", "stepStateVersion", "runStateVersion",
    },
    "approval_requested": {
        "decisionId", "decisionType", "inputArtifactId", "inputArtifactSha256",
        "decisionStateVersion", "runStateVersion",
    },
    "decision_submitted": {
        "decisionId", "decisionType", "inputArtifactId", "inputArtifactSha256", "action",
        "actorUserId", "decisionStateVersion", "runStateVersion",
    },
    "cancel_requested": {"actorUserId", "reasonCode", "runStateVersion"},
    "artifact_published": {"artifactId", "artifactKind", "visibility", "byteSize", "sha256", "runStateVersion"},
    "run_completed": {"status", "finalArtifactId", "runStateVersion"},
    "run_failed": {"status", "reasonCode", "retryable", "runStateVersion"},
    "run_cancelled": {"status", "reasonCode", "runStateVersion"},
}
RETRYABLE_FAILURE_CODES = {"provider_timeout", "provider_temporarily_unavailable", "tool_temporarily_unavailable"}
RELEASE_ID = V2_RELEASE_ID
WORKFLOW_KEY = "evidence_research"
WORKFLOW_VERSION_ID = V2_WORKFLOW_VERSION_ID
PROMPT_VERSION_IDS = V2_PROMPT_VERSION_IDS
PROMPT_VERSION_HASHES = {
    node_key: spec.template_sha256 for node_key, spec in V2_PROMPT_SPECS.items()
}
DATA_BOUNDARY_POLICY = "research-data-boundary-v1"
PRICING_VERSION = "research-pricing-v1"
BUDGET_POLICY_VERSION = "research-budget-v1"
RETRY_POLICY_VERSION = "research-retry-v1"
IDEMPOTENCY_TTL = timedelta(hours=24)
