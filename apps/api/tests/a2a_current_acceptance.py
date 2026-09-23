"""Current-default feature acceptance, separate from the R2 historical oracle."""
import hashlib
import json


def assert_current_completion(rows, objects, api_payload_bytes, workflow):
    from ai_pdf_api.services.research.research_prompt_provenance import V3_WORKFLOW_VERSION_ID, V3_PROMPT_VERSION_IDS
    assert workflow["workflowId"] == workflow["currentDefaultWorkflowId"] == V3_WORKFLOW_VERSION_ID
    assert workflow["workflowVersion"] == 3
    assert {p["id"] for p in workflow["prompts"]} == set(V3_PROMPT_VERSION_IDS.values())
    assert {p["version"] for p in workflow["prompts"]} == {3}
    assert workflow["agentResultSchemaVersion"] == workflow["currentDefaultAgentSchema"]
    assert workflow["result"] == "completed"
    assert len(api_payload_bytes) == 1, "default new run must use only POST create, never manual decisions"
    decisions = rows["human_decisions"]
    assert len(decisions) == 2
    assert {(d["decision_type"],d["action"]) for d in decisions} == {
        ("plan_approval","approve"),("conflict_resolution","keep_as_unresolved")}
    assert all(d["status"] == "submitted" and d["decision_origin"] == "policy"
               and d["decided_by_user_id"] is None and d["comment_text"] == "research-autonomy-v1" for d in decisions)
    assert len(rows["research_execution_snapshots"]) == 1
    assert rows["research_execution_assets"] and rows["research_budget_ledgers"]
    claims = rows["research_claims"]
    assert len(claims) == 1 and claims[0]["conflict_status"] == "resolved_unresolved"
    final = [a for a in rows["research_artifacts"] if a["artifact_kind"] == "final_report"]
    assert len(final) == 1
    artifact = final[0]
    payload = objects[artifact["object_key"]]
    assert hashlib.sha256(payload).hexdigest() == artifact["content_sha256"]
    assert b"## Unresolved Evidence Conflicts" in payload and b"section=unresolved" in payload
    assert b"## Findings\n- No supported findings." in payload
    assert len(rows["research_publication_intents"]) == 1
    intent = rows["research_publication_intents"][0]
    assert intent["status"] == "committed" and intent["committed_artifact_id"] == artifact["id"]
    assert sum(e["event_type"] == "run_completed" for e in rows["research_events"]) == 1
    events = [e for e in rows["research_events"] if e["event_type"] == "decision_submitted"]
    assert len(events) == 2
    assert all(e["event_schema_version"] == "2" and json.loads(e["payload_json"])["decisionOrigin"] == "policy"
               and json.loads(e["payload_json"])["actorUserId"] is None for e in events)
    assert len(rows["research_adaptive_turns"]) == 1
    assert rows["research_report_edits"] == []
