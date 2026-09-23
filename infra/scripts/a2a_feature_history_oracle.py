"""Issue 23/F1 historical compatibility delta, independent of the R2 whitelist."""
import base64
from copy import deepcopy
import json

from a2a_r2_delta import compare
from a2a_r2_publication_oracle import canonical, require

FEATURE_TABLES = {
    "research_adaptive_turns": sorted(["step_id", "turn_number", "execution_snapshot_id", "created_by_attempt_id", "query", "request_sha256", "result_sha256", "result_json"]),
    "research_report_edits": sorted(["run_id", "workspace_id", "version", "actor_user_id", "base_artifact_id", "base_artifact_sha256", "markdown", "updated_at"]),
}


def project_historical_f1(candidate, *, stored_responses=False):
    projected = deepcopy(candidate)
    columns = projected["researchTableColumns"]
    for table, expected in FEATURE_TABLES.items():
        require(columns.pop(table) == expected, f"F1.{table}.schema")
    require("decision_origin" in columns["human_decisions"], "F1.decision origin column")
    columns["human_decisions"].remove("decision_origin")

    def old_response(payload):
        # Only new human-decision response DTOs may add this field. Existing
        # stored response bytes are required to have no added field at all.
        decisions = [payload["decision"], *payload["run"]["submittedDecisions"], *payload["run"]["pendingDecisions"]]
        for decision in decisions:
            if stored_responses:
                require("decisionOrigin" not in decision, "F1.stored response modified")
            else:
                require(decision.pop("decisionOrigin") == "human", "F1.new human response source")
            require(decision["decidedByUserId"] is not None, "F1.human response actor")
        return payload

    def old_event(event):
        if event["event_type"] != "decision_submitted":
            return
        payload = json.loads(event["payload_json"])
        if stored_responses:
            require(event["event_schema_version"] == "1" and "decisionOrigin" not in payload, "F1.stored event modified")
        else:
            require(event["event_schema_version"] == "2", "F1.new event schema")
            require(payload.pop("decisionOrigin") == "human", "F1.new event source")
            require(payload.pop("policyId") is None, "F1.human policy ID")
            event["event_schema_version"] = "1"
        require(payload["actorUserId"] is not None, "F1.human event actor")
        event["payload_json"] = canonical(payload).decode()

    def rows_projection(tables, *, raw=False):
        for table in FEATURE_TABLES:
            require(tables.pop(table) == [], f"F1.historical {table} must stay empty")
        for decision in tables["human_decisions"]:
            require(decision.pop("decision_origin") == "human", "F1.historical decision source")
            require(decision["decided_by_user_id"] is not None, "F1.historical decision actor")
        for event in tables["research_events"]:
            old_event(event)
        for record in tables["research_idempotency_records"]:
            payload = json.loads(record["response_json"]) if isinstance(record["response_json"], str) else record["response_json"]
            if isinstance(payload, dict) and "decision" in payload:
                old_response(payload)
                record["response_json"] = json.dumps(payload)
        # Canonical row order is part of the original probe projection.
        for rows in tables.values():
            rows.sort(key=canonical)

    for tables in projected["semantics"]["normalizedDbRows"].values():
        rows_projection(tables)
    for tables in projected["rawDatabaseRows"].values():
        rows_projection(tables, raw=True)
    for tables in (projected["publicationMaintenance"]["before"], projected["publicationMaintenance"]["after"]):
        rows_projection(tables)
    for state in projected["publicationLifecycle"]:
        rows_projection(state["rows"])
    responses = projected["semantics"]["exactPayloadBytes"]["processOne"]["apiResponses"]
    for i, encoded in enumerate(responses):
        payload = json.loads(base64.b64decode(encoded))
        if "decision" in payload:
            old_response(payload)
            responses[i] = base64.b64encode(json.dumps(payload,ensure_ascii=False,separators=(",", ":")).encode()).decode()
    events = projected["semantics"]["exactEventBytes"]["processOne"]
    for i, encoded in enumerate(events):
        event = json.loads(base64.b64decode(encoded))
        if event["type"] == "decision_submitted":
            if stored_responses:
                require(event["schemaVersion"] == "1" and "decisionOrigin" not in event["payload"], "F1.stored wire event modified")
            else:
                require(event["schemaVersion"] == "2" and event["payload"].pop("decisionOrigin") == "human", "F1.new wire source")
                require(event["payload"].pop("policyId") is None, "F1.human wire policy ID")
                event["schemaVersion"] = "1"
            require(event["payload"]["actorUserId"] is not None, "F1.wire actor")
            events[i] = base64.b64encode(canonical(event)).decode()
    return projected


def compare_historical_feature(baseline, candidate, *, stored_responses=False):
    try:
        projected = project_historical_f1(candidate, stored_responses=stored_responses)
        if stored_responses:
            historical_nodes = ["planner", "researcher", "verifier", "critic", "synthesizer"]
            require(baseline["semantics"]["terminalProcessSemantics"]["providerNodes"] == historical_nodes, "F1.baseline calls")
            require(projected["semantics"]["terminalProcessSemantics"]["providerNodes"] == ["synthesizer"], "F1.recovery reran historical model work")
            require(projected["publicationMaintenance"]["providerCallsBefore"] == projected["publicationMaintenance"]["providerCallsAfter"] == ["synthesizer"], "F1.recovery maintenance provider work")
            projected["semantics"]["terminalProcessSemantics"]["providerNodes"] = historical_nodes
            projected["publicationMaintenance"]["providerCallsBefore"] = historical_nodes
            projected["publicationMaintenance"]["providerCallsAfter"] = historical_nodes
        result = compare(baseline, projected, candidate_business_calls=2 if stored_responses else 8)
        workflow = candidate["workflowEvidence"]
        require(workflow["workflowId"] == "20000000-0000-4000-8000-000000000001" and workflow["workflowVersion"] == 2, "F1.frozen workflow identity")
        require(workflow["currentDefaultWorkflowId"] == "30000000-0000-4000-8000-000000000001", "F1.default workflow not restored")
        require(workflow["prompts"] == baseline["workflowEvidence"]["prompts"], "F1.frozen prompt identity/hash")
        require(candidate["restoredHistoricalStateSha256"] is not None, "F1.missing restored historical state")
        return {**result, "f1HistoricalDeltaValid": True}
    except (KeyError, ValueError, TypeError) as error:
        return {"accepted": False, "f1HistoricalDeltaValid": False, "f1Errors": [str(error)]}
