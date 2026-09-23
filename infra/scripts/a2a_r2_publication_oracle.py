"""Field-complete R2 publication intent oracle for the frozen A2 workload."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from uuid import UUID

INTENTS = "research_publication_intents"
NOW = "2026-08-24 04:00:00.000000"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def require(condition, path):
    if not condition:
        raise ValueError(path)


def one(rows, **identity):
    found = [r for r in rows if all(r.get(k) == v for k, v in identity.items())]
    require(len(found) == 1, f"unique relationship: {identity}")
    return found[0]


def validate_publication(report):
    rows = report["semantics"]["normalizedDbRows"]["processOne"]
    final = one(rows["research_artifacts"], artifact_kind="final_report")
    run = one(rows["research_runs"], id=final["run_id"])
    step = one(rows["research_steps"], id=final["generated_by_step_id"])
    attempt = one(rows["research_step_attempts"], id=final["generated_by_attempt_id"])
    snapshot = one(rows["research_execution_snapshots"], id=run["approved_execution_snapshot_id"])
    require(run["status"] == "completed" and run["cancel_reason_code"] is None, "publication.run")
    require(step["step_kind"] == "artifact_publisher" and step["status"] == "succeeded", "publication.step")
    require(attempt["step_id"] == step["id"] and attempt["status"] == "succeeded", "publication.attempt")
    for obj in (step, snapshot, final):
        require(obj["run_id"] == run["id"] and obj["workspace_id"] == run["workspace_id"], "publication.scope")
    require(step["execution_snapshot_id"] == snapshot["id"], "publication.snapshot")
    intent = one(rows[INTENTS], artifact_id=final["id"])
    require(len(rows[INTENTS]) == 1, "publication.intent cardinality")
    require(str(UUID(intent["id"])) == intent["id"], "publication.intent UUID")
    require(not any(r.get("id") == intent["id"] for t, rs in rows.items() if t != INTENTS for r in rs), "publication.intent ID collision")
    prefix = f"research/{run['workspace_id']}/{run['id']}/{final['id']}"
    key = prefix + "/publication/1/final.md"
    require(final["object_key"] == key, "publication.generation object owner")
    objects = report["semantics"]["exactPayloadBytes"]["processOne"]["objectPayloads"]
    payload = base64.b64decode(objects[key], validate=True)
    sha = hashlib.sha256(payload).hexdigest()
    require(final["content_sha256"] == sha and final["byte_size"] == len(payload), "publication.object hash/size")
    require({a["object_key"] for a in rows["research_artifacts"]} == set(objects), "publication.orphan/missing objects")
    relations = [r for r in rows["research_artifact_claims"] if r["artifact_id"] == final["id"]]
    # This fixed workload deliberately publishes its sole supported claim as unresolved.
    claim = one(rows["research_claims"], run_id=run["id"])
    require(claim["verification_status"] == "supported" and claim["conflict_status"] == "resolved_unresolved", "publication.claim partition")
    require(len(relations) == 1 and relations[0]["claim_id"] == claim["id"], "publication.claim relation")
    selection = {"factClaimIds": [], "unresolvedClaimIds": [claim["id"]]}
    selection_json = json.dumps(selection)
    expected = {
        "id": intent["id"], "workspace_id": run["workspace_id"], "run_id": run["id"],
        "step_id": step["id"], "attempt_id": attempt["id"], "execution_snapshot_id": snapshot["id"],
        "artifact_id": final["id"], "committed_artifact_id": final["id"],
        "logical_key": "final-report", "object_prefix": prefix,
        "current_object_generation": None, "current_object_key": None,
        "adopted_object_generation": 1, "adopted_object_key": key,
        "content_type": "text/markdown", "render_schema_version": "final-report-v1",
        "payload_bytes": {"bytesBase64": objects[key]}, "byte_size": len(payload), "content_sha256": sha,
        "selection_json": selection_json, "selection_sha256": hashlib.sha256(canonical(selection)).hexdigest(),
        "status": "committed", "state_version": 4, "claim_generation": 1,
        "claim_owner": None, "claim_token_hash": None, "claim_expires_at": None, "claim_heartbeat_at": None,
        "next_reconcile_at": NOW, "reconcile_attempt_count": 1,
        "last_error_code": "publication_terminal_sweep_pending",
        "orphan_sweep_after": "2026-08-24 04:00:30.000000",
        "created_at": NOW, "updated_at": NOW, "resolved_at": NOW,
    }
    require(intent == expected, "publication.intent fields")
    maintenance = report["publicationMaintenance"]
    require(maintenance["after"] == rows, "maintenance.final rows")
    before = json.loads(json.dumps(rows))
    before[INTENTS][0].update(last_error_code=None, orphan_sweep_after=NOW)
    require(maintenance["before"] == before, "maintenance.business mutation")
    require(maintenance["outputs"] == [True, False], "maintenance.exact schedule")
    nodes = report["semantics"]["terminalProcessSemantics"]["providerNodes"]
    require(maintenance["providerCallsBefore"] == maintenance["providerCallsAfter"] == nodes,
            "maintenance.provider calls")
    validate_lifecycle(report, expected, before, objects, key, attempt, run)
    return final, prefix + "/final.md", key


def validate_lifecycle(report, committed, before, objects, key, attempt, run):
    lifecycle = report["publicationLifecycle"]
    require(len(lifecycle) == 5, "lifecycle.exact transitions")
    prepared = dict(committed)
    owner = lifecycle[0]["producerWorkerInstanceId"]
    raw_attempt = one(report["rawDatabaseRows"]["processOne"]["research_step_attempts"], id=attempt["id"])
    require(owner == raw_attempt["worker_instance_id"] and isinstance(owner, str), "lifecycle.actual persisted owner")
    # The raw owner is captured from the originating persisted attempt, not inferred from UUID order.
    prepared.update(status="prepared", state_version=1, committed_artifact_id=None,
                    adopted_object_generation=None, adopted_object_key=None,
                    current_object_generation=1, current_object_key=key, claim_owner=owner,
                    claim_token_hash=hashlib.sha256(b"a2a-lease-token-009").hexdigest(),
                    claim_expires_at="2026-08-24 04:01:00.000000", claim_heartbeat_at=NOW,
                    last_error_code=None, orphan_sweep_after=None, resolved_at=None)
    # The token is captured from the actual deterministic token generator; the fixed
    # workload issues eight attempt leases and then one publication claim.
    expected_intents = [prepared, {**prepared, "status": "uploaded", "state_version": 2},
                        {**prepared, "status": "committing", "state_version": 3},
                        before[INTENTS][0], committed]
    precommit_rows = expected_precommit_rows(before, committed, attempt, run)
    for phase, expected in zip(lifecycle, expected_intents, strict=True):
        require(phase["rows"][INTENTS] == [expected], f"lifecycle.{expected['status']} fields")
        if expected["status"] != "committed":
            expected_rows = deepcopy(precommit_rows)
            expected_rows[INTENTS] = [expected]
            require(phase["rows"] == expected_rows, f"lifecycle.{expected['status']} complete precommit graph")
        require(phase["producerWorkerInstanceId"] == owner, "lifecycle.owner drift")
        require(phase["authorization"] == {"creatorId": run["created_by_user_id"], "role": "member"}, "lifecycle.authorization")
        current_attempt = one(phase["rows"]["research_step_attempts"], id=attempt["id"])
        require(current_attempt["worker_instance_id"] == "<process-worker-instance-id>", "lifecycle.attempt owner")
        expected_objects = dict(objects)
        if expected["status"] == "prepared":
            del expected_objects[key]
        require(phase["objectPayloads"] == expected_objects, "lifecycle.storage bytes")
    require(lifecycle[3]["rows"] == before, "lifecycle.committed snapshot")
    require(lifecycle[4]["rows"] == report["publicationMaintenance"]["after"], "lifecycle.sweep snapshot")
    # Upload and committing phases cannot create business work, ledger entries or events.
    for previous, current in zip(lifecycle[:2], lifecycle[1:3], strict=True):
        expected_rows = json.loads(json.dumps(previous["rows"]))
        expected_rows[INTENTS] = current["rows"][INTENTS]
        require(current["rows"] == expected_rows, "lifecycle.precommit business mutation")


def expected_precommit_rows(committed_rows, intent, attempt, run):
    """Reverse only the exact final adoption writes, leaving the full graph strict."""
    expected = deepcopy(committed_rows)
    artifact_id = intent["artifact_id"]
    for table in ("research_artifact_claims", "research_artifact_prompt_versions"):
        expected[table] = [row for row in expected[table] if row["artifact_id"] != artifact_id]
    expected["research_artifacts"] = [row for row in expected["research_artifacts"] if row["id"] != artifact_id]
    terminal_keys = {"step-succeeded:" + attempt["id"], "artifact-published:" + artifact_id,
                     "run-completed:" + artifact_id}
    terminal = [row for row in expected["research_events"] if row["run_id"] == run["id"] and row["dedupe_key"] in terminal_keys]
    require(len(terminal) == 3, "lifecycle.unique terminal adoption events")
    expected["research_events"] = [row for row in expected["research_events"] if row not in terminal]
    one(expected["research_runs"], id=run["id"]).update(
        status="running", state_version=37, next_event_seq=38, finished_at=None)
    one(expected["research_steps"], id=intent["step_id"]).update(
        status="running", state_version=3, finished_at=None)
    one(expected["research_step_attempts"], id=attempt["id"]).update(
        status="running", finished_at=None, output_sha256=None,
        lease_expires_at="2026-08-24 04:05:00.000000")
    for rows in expected.values():
        rows.sort(key=canonical)
    return expected
