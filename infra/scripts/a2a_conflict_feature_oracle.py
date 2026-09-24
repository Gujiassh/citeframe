"""Issue 25-only projection before frozen F1 and R2 historical oracles."""

from copy import deepcopy
import base64
import json
from a2a_r2_publication_oracle import require
from a2a_feature_history_oracle import compare_historical_feature

COLUMNS = sorted(
    [
        "step_id",
        "operation_number",
        "execution_snapshot_id",
        "created_by_attempt_id",
        "phase",
        "status",
        "request_sha256",
        "request_json",
        "result_sha256",
        "result_json",
    ]
)


def project_historical_f2(candidate):
    projected = deepcopy(candidate)
    require(
        projected["researchTableColumns"].pop("research_conflict_turns") == COLUMNS,
        "F2.journal schema",
    )
    workflow = projected["workflowEvidence"]
    require(
        workflow["currentDefaultWorkflowId"] == "40000000-0000-4000-8000-000000000001",
        "F2.default workflow",
    )
    require(
        workflow["currentDefaultAgentSchema"] == "research-agent-results-v3",
        "F2.default IO",
    )
    workflow["currentDefaultWorkflowId"] = "30000000-0000-4000-8000-000000000001"
    workflow["currentDefaultAgentSchema"] = "research-agent-results-v2"

    def dto(value):
        if not isinstance(value, dict):
            return
        if "conflictInvestigation" in value:
            require(
                {"id", "workspaceId", "question", "status", "stateVersion"}.issubset(
                    value
                ),
                "F2.journal outside run DTO",
            )
            require(
                value.pop("conflictInvestigation") is None,
                "F2.historical run acquired investigation",
            )
        for key in ("run", "payload"):
            if key in value:
                dto(value[key])

    def rows(tables):
        require(
            tables.pop("research_conflict_turns") == [],
            "F2.historical journal not empty",
        )
        for row in tables["research_idempotency_records"]:
            payload = row["response_json"]
            value = json.loads(payload) if isinstance(payload, str) else payload
            dto(value)
            row["response_json"] = (
                json.dumps(value) if isinstance(payload, str) else value
            )

    for groups in (
        projected["semantics"]["normalizedDbRows"],
        projected["rawDatabaseRows"],
    ):
        for tables in groups.values():
            rows(tables)
    for tables in (
        projected["publicationMaintenance"]["before"],
        projected["publicationMaintenance"]["after"],
    ):
        rows(tables)
    for phase in projected["publicationLifecycle"]:
        rows(phase["rows"])

    def wire(encoded):
        value = json.loads(base64.b64decode(encoded))
        dto(value)
        return base64.b64encode(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode()

    exact = projected["semantics"]["exactPayloadBytes"]
    exact["manualRetry"] = wire(exact["manualRetry"])
    exact["processOne"]["apiResponses"] = [
        wire(b) for b in exact["processOne"]["apiResponses"]
    ]
    return projected


def compare_conflict_history(baseline, candidate, *, stored_responses=False):
    try:
        projected = project_historical_f2(candidate)
        result = compare_historical_feature(
            baseline, projected, stored_responses=stored_responses
        )
        return {**result, "f2HistoricalDeltaValid": True}
    except (KeyError, ValueError, TypeError) as error:
        return {
            "accepted": False,
            "f2HistoricalDeltaValid": False,
            "f2Errors": [str(error)],
        }
