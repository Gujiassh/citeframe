"""Export/restore a fixture created by the frozen production create endpoint."""
import base64
import hashlib
import json
from sqlalchemy import inspect


def export_created_state(engine, *, run_id, response, objects, counters, historical_columns=None):
    statements = []
    column_map = {}
    with engine.connect() as connection:
        inspector = inspect(connection)
        for table in sorted(historical_columns if historical_columns is not None else inspector.get_table_names()):
            columns = historical_columns[table] if historical_columns is not None else [c["name"] for c in inspector.get_columns(table)]
            column_map[table] = columns
            names = ",".join(f'"{c}"' for c in columns)
            quoted = ",".join(f'quote("{c}")' for c in columns)
            values = sorted(connection.exec_driver_sql(f'SELECT {quoted} FROM "{table}"').all())
            statements.extend(f'INSERT INTO "{table}" ({names}) VALUES ({",".join(row)});' for row in values)
    return {"runId": run_id, "createResponseBase64": base64.b64encode(response).decode(),
            "sql": statements, "columns": column_map, "objects": {k: base64.b64encode(v).decode() for k, v in objects.items()},
            "deterministicCounters": dict(counters)}


def restore_created_state(engine, state, objects, counters):
    with engine.begin() as connection:
        for statement in state["sql"]:
            connection.exec_driver_sql(statement)
    objects.update({k: base64.b64decode(v) for k, v in state["objects"].items()})
    counters.update(state["deterministicCounters"])
    observed = export_created_state(engine, run_id=state["runId"],
        response=base64.b64decode(state["createResponseBase64"]), objects=objects, counters=counters, historical_columns=state["columns"])
    assert observed == state, "restored historical creation state differs before candidate execution"
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def assert_historical_rows_preserved(engine, state):
    # Read the exact pre-existing frozen release INSERT values; current installation
    # may add its own fixed IDs but cannot mutate any historical row or prompt byte.
    observed = export_created_state(engine, run_id=state["runId"],
        response=base64.b64decode(state["createResponseBase64"]), objects={}, counters={}, historical_columns=state["columns"])
    for sql in state["sql"]:
        if sql.startswith(('INSERT INTO "workflow_versions"', 'INSERT INTO "prompt_versions"',
                           'INSERT INTO "workflow_prompt_bindings"')):
            assert sql in observed["sql"], "current release installation rewrote frozen history"


def workflow_evidence(db, run):
    from ai_pdf_api.models import ResearchExecutionSnapshot, ResearchExecutionPromptVersion, WorkflowVersion, PromptVersion
    from ai_pdf_api.services.research.research_constants import WORKFLOW_VERSION_ID
    from ai_pdf_api.services.research.research_agent_io_registry import require_current_production_registry
    from sqlalchemy import select
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    workflow = db.get(WorkflowVersion, snapshot.workflow_version_id)
    bindings = list(db.scalars(select(ResearchExecutionPromptVersion).where(
        ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id)))
    return {"workflowId": workflow.id, "workflowVersion": workflow.version_number,
        "releaseId": workflow.created_by_release_id, "manifestSha256": workflow.manifest_sha256,
        "snapshotId": snapshot.id, "snapshotSha256": snapshot.execution_snapshot_sha256,
        "agentResultSchemaVersion": snapshot.agent_result_schema_version,
        "currentDefaultWorkflowId": WORKFLOW_VERSION_ID,
        "currentDefaultAgentSchema": require_current_production_registry().agent_result_schema_version,
        "prompts": sorted([{"id": b.prompt_version_id, "version": db.get(PromptVersion,b.prompt_version_id).version_number,
             "sha256": db.get(PromptVersion,b.prompt_version_id).template_sha256} for b in bindings], key=lambda p:p["id"]),
        "result": run.status}


def verify_stored_replays(client, engine, requests, headers):
    assert len(requests) == 2
    from sqlalchemy import text
    def persisted():
        with engine.connect() as connection:
            return {table: list(connection.execute(text(f'SELECT * FROM "{table}" ORDER BY id')).mappings())
                    for table in ("research_idempotency_records", "research_events", "human_decisions")}
    before = persisted()
    for request in requests:
        response = client.post(request["path"], headers={**headers, "Idempotency-Key": request["key"]}, json=request["body"])
        assert response.status_code == 200, response.text
        expected = base64.b64decode(request["response"])
        assert response.content == expected, ("old idempotency key changed response bytes", response.text, expected.decode())
        assert "decisionOrigin" not in response.json()["decision"]
    assert persisted() == before, "replay rewrote persisted event/idempotency/decision rows"
