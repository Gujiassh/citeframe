"""Explicit current-Step retry error delta; historical attempts/events remain strict."""

from __future__ import annotations

import json

from a2a_r2_publication_oracle import one, require


def validate_retry_step_error_delta(baseline, candidate, projected):
    old = baseline["rawDatabaseRows"]["transitions"]
    new = candidate["rawDatabaseRows"]["transitions"]
    historical = [
        s
        for s in old["research_steps"]
        if s["status"] == "running"
        and s["current_attempt_number"] == 2
        and s["error_code"] == "lease_expired"
        and s["error_message"] == "Research Attempt lease expired."
    ]
    require(len(historical) == 1, "retryStepErrorDelta.exact historical source")
    before = historical[0]
    after = one(new["research_steps"], id=before["id"], run_id=before["run_id"])
    require(
        after == {**before, "error_code": None, "error_message": None},
        "retryStepErrorDelta.only two current Step fields",
    )
    require(
        new["research_step_attempts"] == old["research_step_attempts"],
        "retryStepErrorDelta.immutable attempt history",
    )
    require(
        new["research_events"] == old["research_events"],
        "retryStepErrorDelta.immutable event history",
    )
    run = one(
        new["research_runs"], id=after["run_id"], workspace_id=after["workspace_id"]
    )
    require(
        run["status"] == "running"
        and run["approved_execution_snapshot_id"] == after["execution_snapshot_id"],
        "retryStepErrorDelta.run/snapshot binding",
    )
    attempts = [a for a in new["research_step_attempts"] if a["step_id"] == after["id"]]
    require(len(attempts) == 2, "retryStepErrorDelta.exact attempts")
    prior = one(attempts, attempt_number=1, status="abandoned")
    current = one(attempts, attempt_number=2, status="running")
    require(
        prior["workspace_id"] == current["workspace_id"] == after["workspace_id"]
        and prior["input_sha256"] == current["input_sha256"] == after["input_sha256"],
        "retryStepErrorDelta.scope/input binding",
    )
    require(
        prior["error_code"] == "lease_expired"
        and prior["error_message"] == "Research Attempt lease expired."
        and prior["finished_at"] is not None
        and prior["lease_expires_at"] is None,
        "retryStepErrorDelta.prior expired attempt",
    )
    require(
        current["error_code"] is None
        and current["error_message"] is None
        and current["finished_at"] is None
        and current["output_sha256"] is None
        and current["lease_token_hash"]
        and current["worker_instance_id"]
        and prior["finished_at"]
        < current["started_at"]
        == current["heartbeat_at"]
        == after["updated_at"]
        < current["lease_expires_at"],
        "retryStepErrorDelta.current successful lease",
    )
    events = [e for e in new["research_events"] if e["run_id"] == run["id"]]
    abandoned = one(
        events,
        event_type="attempt_abandoned",
        attempt_id=prior["id"],
        step_id=after["id"],
    )
    started = one(
        events, event_type="step_started", attempt_id=current["id"], step_id=after["id"]
    )
    queued = one(events, event_type="step_queued", step_id=after["id"])
    require(
        abandoned["created_at"] == prior["finished_at"] == queued["created_at"]
        and started["created_at"] == current["started_at"]
        and abandoned["seq"] + 1 == queued["seq"] == started["seq"] - 1,
        "retryStepErrorDelta.event sequence",
    )
    a, s = json.loads(abandoned["payload_json"]), json.loads(started["payload_json"])
    require(
        a["reasonCode"] == "lease_expired"
        and a["attemptNumber"] == 1
        and a["stepId"] == s["stepId"] == after["id"]
        and a["attemptId"] == prior["id"]
        and s["attemptId"] == current["id"]
        and s["attemptNumber"] == 2
        and s["stepStateVersion"] == after["state_version"]
        and s["runStateVersion"] == run["state_version"],
        "retryStepErrorDelta.event references",
    )
    # Alter only the comparison copy after proving the exact raw transition.
    target = one(
        projected["normalizedDbRows"]["transitions"]["research_steps"], id=after["id"]
    )
    target["error_code"], target["error_message"] = (
        before["error_code"],
        before["error_message"],
    )
    return [
        {
            "runId": run["id"],
            "stepId": after["id"],
            "priorAttemptId": prior["id"],
            "currentAttemptId": current["id"],
            "fields": ["error_code", "error_message"],
            "before": [before["error_code"], before["error_message"]],
            "after": [None, None],
        }
    ]
