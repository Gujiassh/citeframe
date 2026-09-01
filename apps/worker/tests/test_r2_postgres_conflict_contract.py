"""Source, pure-oracle, and adversarial contracts for the R2-I PostgreSQL proof."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "infra/scripts/run-r2-postgres-multi-worker.py"
SCENARIO = ROOT / "infra/scripts/r2_scenario_i_conflict.py"
WORKER = ROOT / "infra/scripts/r2_scenario_i_worker.py"


def load_scenario():
    spec = importlib.util.spec_from_file_location("r2_i_conflict_contract", SCENARIO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture() -> SimpleNamespace:
    roles = (
        "planner",
        "plan_gate",
        "researcher",
        "verifier",
        "critic",
        "conflict_gate",
        "synthesizer",
        "publisher",
    )
    return SimpleNamespace(
        schema="r2-i-contract",
        workspace_id="workspace",
        actor_user_id="actor",
        run_id="run",
        plan_revision_id="plan-revision",
        snapshot_id="snapshot",
        step_ids={role: role for role in roles},
        step_keys={
            "planner": "planner:r2-i",
            "plan_gate": "plan-approval-gate:r2-i",
            "researcher": "researcher:r2-i",
            "verifier": "verifier:r2-i",
            "critic": "critic:r2-i",
            "conflict_gate": "conflict-decision-gate:r2-i",
            "synthesizer": "synthesizer:r2-i",
            "publisher": "artifact-publisher:r2-i",
        },
        prompt_ids={
            "planner": "prompt-planner",
            "researchers": "prompt-researchers",
            "verifier": "prompt-verifier",
            "critic": "prompt-critic",
            "synthesizer": "prompt-synthesizer",
        },
        workflow_id="workflow",
        claim_id="claim",
        decision_keys_by_worker={
            "i-decision-a": "r2-i-conflict-decision-a",
            "i-decision-b": "r2-i-conflict-decision-b",
        },
    )


def valid_event_state() -> tuple[dict[str, object], SimpleNamespace]:
    fx = fixture()
    kinds = {
        "planner": "planner",
        "plan_gate": "plan_approval_gate",
        "researcher": "researcher",
        "verifier": "verifier",
        "critic": "critic",
        "conflict_gate": "conflict_decision_gate",
        "synthesizer": "synthesizer",
        "publisher": "artifact_publisher",
    }
    steps = [
        {
            "id": fx.step_ids[role],
            "step_kind": kind,
            "status": "queued" if role == "publisher" else "succeeded",
            "current_attempt_number": 0 if role == "publisher" else 1,
        }
        for role, kind in kinds.items()
    ]
    attempts = [
        {
            "id": f"attempt-{role}",
            "step_id": fx.step_ids[role],
            "attempt_number": 1,
            "status": "succeeded",
            "output_sha256": "conflict-sha" if role == "conflict_gate" else f"sha-{role}",
            "checkpoint_artifact_id": "checkpoint" if role == "synthesizer" else None,
        }
        for role in kinds
        if role != "publisher"
    ]
    events: list[dict[str, object]] = []

    def add(
        event_type: str,
        *,
        role: str | None = None,
        attempt_role: str | None = None,
        status: str | None = None,
        decision_id: str | None = None,
        artifact_id: str | None = None,
        artifact_ids: list[str] | None = None,
    ) -> None:
        seq = len(events) + 1
        step_id = fx.step_ids[role] if role else None
        attempt_id = f"attempt-{attempt_role}" if attempt_role else None
        payload: dict[str, object] = {"runStateVersion": seq}
        if role:
            payload.update({"stepId": step_id, "stepKind": kinds[role]})
        if event_type in {"step_started", "step_succeeded"}:
            payload.update({"attemptId": attempt_id, "attemptNumber": 1})
        if event_type == "step_succeeded":
            payload.update({"evidenceCount": 0, "artifactIds": artifact_ids or []})
        if status is not None:
            payload["status"] = status
        if decision_id is not None:
            payload["decisionId"] = decision_id
        if artifact_id is not None:
            payload["artifactId"] = artifact_id
        events.append(
            {
                "seq": seq,
                "event_type": event_type,
                "step_id": step_id,
                "attempt_id": attempt_id,
                "dedupe_key": f"event-{seq}",
                "payload_json": payload,
            }
        )

    add("run_created", status="planning")
    add("step_queued", role="planner")
    add("run_status_changed", status="running")
    add("step_started", role="planner", attempt_role="planner")
    add("artifact_published", artifact_id="plan")
    add("step_succeeded", role="planner", attempt_role="planner", artifact_ids=["plan"])
    add("step_queued", role="plan_gate")
    add("step_started", role="plan_gate", attempt_role="plan_gate")
    add("step_waiting", role="plan_gate", attempt_role="plan_gate", decision_id="plan-decision")
    add("approval_requested", decision_id="plan-decision")
    add("run_status_changed", status="awaiting_plan_approval")
    add("decision_submitted", role="plan_gate", decision_id="plan-decision")
    add("run_status_changed", status="queued")
    add("step_queued", role="researcher")
    add("run_status_changed", status="running")
    add("step_started", role="researcher", attempt_role="researcher")
    add("step_succeeded", role="researcher", attempt_role="researcher")
    add("step_queued", role="verifier")
    add("step_started", role="verifier", attempt_role="verifier")
    add("step_succeeded", role="verifier", attempt_role="verifier")
    add("step_queued", role="critic")
    add("step_started", role="critic", attempt_role="critic")
    add("step_succeeded", role="critic", attempt_role="critic")
    add("step_queued", role="conflict_gate")
    add("step_started", role="conflict_gate", attempt_role="conflict_gate")
    add("artifact_published", artifact_id="conflict")
    add(
        "step_waiting",
        role="conflict_gate",
        attempt_role="conflict_gate",
        decision_id="conflict-decision",
    )
    add("approval_requested", decision_id="conflict-decision")
    add("run_status_changed", status="awaiting_human_decision")
    add("decision_submitted", role="conflict_gate", decision_id="conflict-decision")
    add("run_status_changed", status="queued")
    add("step_queued", role="synthesizer")
    add("run_status_changed", status="running")
    add("step_started", role="synthesizer", attempt_role="synthesizer")
    add(
        "step_succeeded",
        role="synthesizer",
        attempt_role="synthesizer",
        artifact_ids=["checkpoint"],
    )
    add("step_queued", role="publisher")
    dependencies = [
        {"step_id": fx.step_ids[dependent], "depends_on_step_id": fx.step_ids[dependency]}
        for dependent, dependency in (
            ("plan_gate", "planner"),
            ("verifier", "researcher"),
            ("critic", "verifier"),
            ("conflict_gate", "critic"),
            ("synthesizer", "conflict_gate"),
            ("publisher", "synthesizer"),
        )
    ]
    state: dict[str, object] = {
        "run": {
            "state_version": len(events),
            "next_event_seq": len(events) + 1,
            "latest_checkpoint_artifact_id": "checkpoint",
            "created_at": "2026-09-01T00:00:00+00:00",
            "started_at": "2026-09-01T00:00:00+00:00",
            "updated_at": "2026-09-01T00:00:09+00:00",
            "finished_at": None,
        },
        "steps": steps,
        "attempts": attempts,
        "events": events,
        "dependencies": dependencies,
        "decisions": [
            {"id": "plan-decision", "decision_type": "plan_approval"},
            {"id": "conflict-decision", "decision_type": "conflict_resolution"},
        ],
        "artifacts": [
            {"id": "plan", "artifact_kind": "research_plan"},
            {"id": "conflict", "artifact_kind": "conflict_report"},
            {"id": "checkpoint", "artifact_kind": "execution_checkpoint"},
        ],
    }
    scenario = load_scenario()
    base = "2026-09-01T00:00:00+00:00"

    def second(value: int) -> str:
        return f"2026-09-01T00:00:{value:02d}+00:00"

    attempt_ids = {
        "planner": scenario.uid(fx.schema, "plan-attempt"),
        "plan_gate": scenario.uid(fx.schema, "plan-gate-attempt"),
        "researcher": scenario.uid(fx.schema, "researcher-attempt"),
        "verifier": "44444444-4444-4444-8444-444444444444",
        "critic": "55555555-5555-4555-8555-555555555555",
        "conflict_gate": "66666666-6666-4666-8666-666666666666",
        "synthesizer": "77777777-7777-4777-8777-777777777777",
    }
    workers = {
        "planner": "r2-i-seed-planner",
        "plan_gate": "r2-i-seed-plan-gate",
        "researcher": "r2-i-seed-researcher",
        "verifier": "i-verifier",
        "critic": "i-critic",
        "conflict_gate": "i-conflict-gate",
        "synthesizer": "i-synth-a",
    }
    for role, attempt in zip(
        [role for role in kinds if role != "publisher"], attempts, strict=True
    ):
        attempt["id"] = attempt_ids[role]
        attempt["worker_instance_id"] = workers[role]
        attempt["finished_at"] = second(6) if role == "conflict_gate" else base

    step_times = {
        "planner": (base, base, base),
        "plan_gate": (base, base, base),
        "researcher": (base, base, base),
        "verifier": (base, second(1), second(2)),
        "critic": (second(2), second(3), second(4)),
        "conflict_gate": (second(4), second(5), second(7)),
        "synthesizer": (second(7), second(8), second(9)),
        "publisher": (second(9), None, None),
    }
    for step in steps:
        role = step["id"]
        queued_at, started_at, finished_at = step_times[role]
        step.update(
            {
                "branch_key": "r2-i-branch" if role == "researcher" else None,
                "queued_at": queued_at,
                "started_at": started_at,
                "finished_at": finished_at,
            }
        )
    plan_decision = state["decisions"][0]
    plan_decision.update(
        {
            "gate_step_id": fx.step_ids["plan_gate"],
            "input_artifact_id": "plan",
            "input_artifact_sha256": "plan-sha",
            "action": "approve",
            "requested_at": base,
            "decided_at": base,
        }
    )
    conflict_decision = state["decisions"][1]
    conflict_decision.update(
        {
            "gate_step_id": fx.step_ids["conflict_gate"],
            "input_artifact_id": "conflict",
            "input_artifact_sha256": "conflict-sha",
            "action": "keep_as_unresolved",
            "requested_at": second(6),
            "decided_at": second(7),
        }
    )
    state["artifacts"] = [
        {
            "id": "plan",
            "artifact_kind": "research_plan",
            "visibility": "user",
            "byte_size": 10,
            "content_sha256": "plan-sha",
            "created_at": base,
        },
        {
            "id": "conflict",
            "artifact_kind": "conflict_report",
            "visibility": "user",
            "byte_size": 11,
            "content_sha256": "conflict-sha",
            "created_at": second(6),
        },
        {
            "id": "checkpoint",
            "artifact_kind": "execution_checkpoint",
            "visibility": "internal",
            "byte_size": 12,
            "content_sha256": "checkpoint-sha",
            "created_at": second(9),
        },
    ]
    for seq, event in enumerate(events, 1):
        event["id"] = f"00000000-0000-4000-8000-{seq:012d}"
        event["workspace_id"] = fx.workspace_id
        event["run_id"] = fx.run_id
        event["event_schema_version"] = "1"
        event["created_at"] = base
    state["events"] = scenario.event_row_oracle(state, fx)["expectedRows"]
    row_evidence = scenario.step_attempt_row_oracle(state, fx)
    state["steps"] = list(row_evidence["expectedSteps"].values())
    state["attempts"] = list(row_evidence["expectedAttempts"].values())
    return state, fx


def reindex_events(state: dict[str, object]) -> None:
    events = state["events"]
    assert isinstance(events, list)
    for seq, event in enumerate(events, 1):
        event["seq"] = seq
        event["dedupe_key"] = f"event-{seq}"
        event["payload_json"]["runStateVersion"] = seq
    state["run"]["state_version"] = len(events)
    state["run"]["next_event_seq"] = len(events) + 1


def valid_artifact_state() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]], SimpleNamespace]:
    fx = fixture()
    plan = {"id": "plan", "artifact_kind": "research_plan"}
    conflict_id = "11111111-1111-4111-8111-111111111111"
    checkpoint_id = "22222222-2222-4222-8222-222222222222"
    conflict = {
        "id": conflict_id,
        "workspace_id": "workspace",
        "run_id": fx.run_id,
        "generated_by_step_id": fx.step_ids["conflict_gate"],
        "generated_by_attempt_id": "attempt-conflict_gate",
        "artifact_kind": "conflict_report",
        "visibility": "user",
        "logical_key": "conflict-report:1",
        "schema_version": "1",
        "object_key": f"research/workspace/run/{conflict_id}/conflicts.json",
        "content_type": "application/json",
        "byte_size": 10,
        "content_sha256": "conflict-sha",
        "supersedes_artifact_id": None,
        "workflow_version_id": fx.workflow_id,
        "direct_prompt_version_id": fx.prompt_ids["critic"],
        "generation_provider": "test",
        "generation_model": "r2-i-deterministic",
        "retention_class": "workspace_lifetime",
        "expires_at": None,
        "created_at": "2026-09-01T00:00:01+00:00",
    }
    checkpoint = {
        "id": checkpoint_id,
        "workspace_id": "workspace",
        "run_id": fx.run_id,
        "generated_by_step_id": fx.step_ids["synthesizer"],
        "generated_by_attempt_id": "attempt-synthesizer",
        "artifact_kind": "execution_checkpoint",
        "visibility": "internal",
        "logical_key": "checkpoint:synthesis",
        "schema_version": "1",
        "object_key": f"research/workspace/run/{checkpoint_id}/checkpoint.json",
        "content_type": "application/json",
        "byte_size": 11,
        "content_sha256": "checkpoint-sha",
        "supersedes_artifact_id": None,
        "workflow_version_id": fx.workflow_id,
        "direct_prompt_version_id": fx.prompt_ids["synthesizer"],
        "generation_provider": "test",
        "generation_model": "r2-i-deterministic",
        "retention_class": "workspace_lifetime",
        "expires_at": None,
        "created_at": "2026-09-01T00:00:02+00:00",
    }
    baseline_claim = {
        "artifact_id": plan["id"],
        "claim_id": "baseline-claim",
        "claim_order": 0,
        "section_kind": "plan",
    }
    baseline_prompt = {
        "artifact_id": plan["id"],
        "node_key": "planner",
        "prompt_version_id": fx.prompt_ids["planner"],
    }
    before = {
        "artifacts": [plan],
        "artifactClaims": [baseline_claim],
        "artifactPromptVersions": [baseline_prompt],
    }
    after = {
        "run": {"latest_checkpoint_artifact_id": checkpoint["id"]},
        "artifacts": [copy.deepcopy(plan), conflict, checkpoint],
        "attempts": [
            {
                "id": "attempt-conflict_gate",
                "step_id": fx.step_ids["conflict_gate"],
                "output_sha256": conflict["content_sha256"],
                "checkpoint_artifact_id": None,
                "started_at": "2026-09-01T00:00:00+00:00",
                "finished_at": conflict["created_at"],
            },
            {
                "id": "attempt-synthesizer",
                "step_id": fx.step_ids["synthesizer"],
                "output_sha256": "synth-sha",
                "checkpoint_artifact_id": checkpoint["id"],
                "started_at": "2026-09-01T00:00:01+00:00",
                "finished_at": checkpoint["created_at"],
            },
        ],
        "artifactClaims": [
            copy.deepcopy(baseline_claim),
            {
                "artifact_id": conflict["id"],
                "claim_id": fx.claim_id,
                "claim_order": 0,
                "section_kind": "conflict",
            }
        ],
        "artifactPromptVersions": [
            copy.deepcopy(baseline_prompt),
            *[
            {
                "artifact_id": conflict["id"],
                "node_key": node,
                "prompt_version_id": fx.prompt_ids[node],
            }
            for node in sorted(fx.prompt_ids)
            ],
        ],
        "events": [
            {
                "event_type": "artifact_published",
                "step_id": None,
                "payload_json": {"artifactId": conflict["id"]},
            },
            {
                "event_type": "step_succeeded",
                "step_id": fx.step_ids["synthesizer"],
                "payload_json": {"artifactIds": [checkpoint["id"]]},
            },
        ],
    }
    manifest = [
        {"key": conflict["object_key"], "size": 10, "sha256": "conflict-sha"},
        {"key": checkpoint["object_key"], "size": 11, "sha256": "checkpoint-sha"},
    ]
    return before, after, manifest, fx


def valid_idempotency_state(scenario):
    workspace_id = "workspace"
    actor_user_id = "actor"
    run_id = "run"
    decision_id = "decision"
    request = scenario.conflict_decision_request(
        expected_state_version=29,
        expected_decision_state_version=1,
        input_artifact_sha256="a" * 64,
        input_snapshot_sha256="b" * 64,
    )
    request_body = request.model_dump(mode="json", by_alias=True)
    request_sha256 = scenario.canonical_sha256(request_body)
    path = (
        "/v1/workspaces/workspace/research-runs/run/"
        "conflict-decisions/decision"
    )
    winner_key = "r2-i-conflict-decision-a"
    loser_key = "r2-i-conflict-decision-b"
    winner_response = {
        "decision": {"id": decision_id, "status": "submitted"},
        "run": {"id": run_id, "status": "queued", "stateVersion": 31},
    }
    loser_response = {
        "error": {
            "code": "research_state_conflict",
            "message": "Research decision has already been submitted.",
            "requestId": "33333333-3333-4333-8333-333333333333",
            "retryable": False,
        }
    }

    def persisted_record(
        *, key: str, status: str, http_status: int, response: dict[str, object]
    ) -> dict[str, object]:
        return {
            "id": "persisted-winner" if status == "completed" else "persisted-loser",
            "workspace_id": workspace_id,
            "actor_user_id": actor_user_id,
            "operation": "submit_conflict_decision",
            "canonical_resource_path": path,
            "idempotency_key": key,
            "request_sha256": request_sha256,
            "status": status,
            "http_status": http_status,
            "result_resource_id": decision_id if status == "completed" else None,
            "response_schema_version": "1",
            "response_json": copy.deepcopy(response),
            "created_at": "2026-09-01T00:00:00+00:00",
            "completed_at": "2026-09-01T00:00:01+00:00",
            "expires_at": "2026-09-02T00:00:00+00:00",
        }

    def process_record(
        *,
        worker_id: str,
        key: str,
        outcome: str,
        http_status: int,
        response: dict[str, object],
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "workerInstanceId": worker_id,
            "idempotencyKey": key,
            "outcome": outcome,
            "httpStatus": http_status,
            "responseJson": copy.deepcopy(response),
            "responseSha256": scenario.canonical_sha256(response),
        }
        error = response.get("error")
        if isinstance(error, dict):
            record.update(
                {
                    "errorCode": error.get("code"),
                    "errorMessage": error.get("message"),
                    "errorRetryable": error.get("retryable"),
                    "errorRequestId": error.get("requestId"),
                    "errorDetails": error.get("details"),
                }
            )
        return record

    state = {
        "idempotencyRecords": [
            persisted_record(
                key=winner_key,
                status="completed",
                http_status=200,
                response=winner_response,
            ),
            persisted_record(
                key=loser_key,
                status="failed",
                http_status=409,
                response=loser_response,
            ),
        ]
    }
    winner = process_record(
        worker_id="i-decision-a",
        key=winner_key,
        outcome="decided",
        http_status=200,
        response=winner_response,
    )
    loser = process_record(
        worker_id="i-decision-b",
        key=loser_key,
        outcome="fenced",
        http_status=409,
        response=loser_response,
    )
    winner_replay = process_record(
        worker_id="i-decision-replay",
        key=winner_key,
        outcome="replayed",
        http_status=200,
        response=winner_response,
    )
    loser_replay = process_record(
        worker_id="i-decision-loser-replay",
        key=loser_key,
        outcome="fenced",
        http_status=409,
        response=loser_response,
    )
    context = {
        "workspace_id": workspace_id,
        "actor_user_id": actor_user_id,
        "run_id": run_id,
        "decision_id": decision_id,
        "expected_request_body": copy.deepcopy(request_body),
        "expected_winner_response": copy.deepcopy(winner_response),
        "decision_keys_by_worker": fixture().decision_keys_by_worker,
        "winner": winner,
        "loser": loser,
        "winner_replay": winner_replay,
        "loser_replay": loser_replay,
    }
    return state, context


def test_r2_i_is_modular_and_calls_every_required_production_transition() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    scenario = SCENARIO.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    assert 'I_CONFLICT_SCENARIO = ROOT / "infra/scripts/r2_scenario_i_conflict.py"' in runner
    assert '"i_conflict_decision_resume"' in runner
    assert "i_conflict.run_scenario(" in runner
    for call in (
        "complete_research_verification(",
        "complete_research_critique(",
        "wait_for_conflict_decision(",
        "ConflictDecisionRequest(",
        "decide_conflict(",
        "complete_research_synthesis(",
        "claim_next_research_step(",
        "claim_specific_research_step(",
    ):
        assert call in worker
    assert "session_replication_role" not in scenario


def test_r2_i_projects_provenance_decision_idempotency_and_source_rows() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")
    for model_name in (
        "WorkflowVersion",
        "PromptVersion",
        "WorkflowPromptBinding",
        "ResearchExecutionPromptVersion",
        "HumanDecision",
        "HumanDecisionClaim",
        "ResearchClaim",
        "ResearchArtifact",
        "ResearchArtifactClaim",
        "ResearchArtifactPromptVersion",
        "ResearchStepDependency",
        "ResearchIdempotencyRecord",
        "ResearchEvent",
    ):
        assert model_name in scenario
    assert '"losingDecisionFrozenFailureReplayZeroMutation": True' in scenario
    assert '"artifactObjectDeltaAndProvenanceExact": True' in scenario
    assert '"productionSourceSha256"' in scenario
    assert 'environment["CITEFRAME_R2_DATABASE_URL"] = database_url' in scenario
    assert '"--database-url"' not in scenario


def test_event_oracle_accepts_only_complete_legal_history() -> None:
    scenario = load_scenario()
    state, fx = valid_event_state()
    oracle = scenario.event_oracle(state, fx)
    assert oracle["strictPartialOrder"] is True
    assert oracle["requiredLifecycleEventsExactlyOnce"] is True
    assert oracle["terminalAttemptLinksExact"] is True
    assert oracle["dependenciesCommittedBeforeQueued"] is True
    assert oracle["stepSetExact"] is True
    assert oracle["attemptsConsumedExact"] is True
    assert oracle["lifecycleEventsConsumedExact"] is True
    assert oracle["allEventsAccountedExact"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_terminal",
        "missing_event",
        "extra_step",
        "extra_attempt",
        "extra_attempt_unknown_step",
        "wrong_attempt_id",
        "unknown_step_event",
        "extra_event",
        "premature_dependency",
    ],
)
def test_event_oracle_rejects_adversarial_history(mutation: str) -> None:
    scenario = load_scenario()
    state, fx = valid_event_state()
    events = state["events"]
    if mutation == "duplicate_terminal":
        duplicate = copy.deepcopy(
            next(
                event
                for event in events
                if event["event_type"] == "step_succeeded"
                and event["step_id"] == fx.step_ids["verifier"]
            )
        )
        events.append(duplicate)
        reindex_events(state)
    elif mutation == "missing_event":
        events.remove(
            next(
                event
                for event in events
                if event["event_type"] == "approval_requested"
                and event["payload_json"].get("decisionId") == "conflict-decision"
            )
        )
        reindex_events(state)
    elif mutation == "extra_step":
        state["steps"].append(
            {
                "id": "extra-step",
                "step_kind": "researcher",
                "status": "succeeded",
                "current_attempt_number": 0,
            }
        )
    elif mutation == "extra_attempt":
        state["attempts"].append(
            {
                "id": "extra-verifier-attempt",
                "step_id": fx.step_ids["verifier"],
                "attempt_number": 2,
                "status": "succeeded",
            }
        )
    elif mutation == "extra_attempt_unknown_step":
        state["attempts"].append(
            {
                "id": "extra-unknown-attempt",
                "step_id": "unknown-step",
                "attempt_number": 1,
                "status": "succeeded",
            }
        )
    elif mutation == "wrong_attempt_id":
        started = next(
            event
            for event in events
            if event["event_type"] == "step_started"
            and event["step_id"] == fx.step_ids["verifier"]
        )
        started["attempt_id"] = "wrong-attempt"
    elif mutation == "unknown_step_event":
        queued = next(
            event
            for event in events
            if event["event_type"] == "step_queued"
            and event["step_id"] == fx.step_ids["verifier"]
        )
        queued["step_id"] = "unknown-step"
        queued["payload_json"]["stepId"] = "unknown-step"
    elif mutation == "extra_event":
        events.append(
            {
                "seq": len(events) + 1,
                "event_type": "unexpected_proof_event",
                "step_id": None,
                "attempt_id": None,
                "dedupe_key": "extra-event",
                "payload_json": {"runStateVersion": len(events) + 1},
            }
        )
        reindex_events(state)
    else:
        critic_queue = next(
            event
            for event in events
            if event["event_type"] == "step_queued"
            and event["step_id"] == fx.step_ids["critic"]
        )
        verifier_terminal_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "step_succeeded"
            and event["step_id"] == fx.step_ids["verifier"]
        )
        events.remove(critic_queue)
        events.insert(verifier_terminal_index, critic_queue)
        reindex_events(state)
    assert scenario.event_oracle(state, fx)["strictPartialOrder"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "step_workspace",
        "step_branch",
        "step_prompt",
        "step_snapshot",
        "step_input",
        "step_state_version",
        "step_timestamp",
        "dependency_extra_field",
        "attempt_owner",
        "attempt_input",
        "attempt_output",
        "attempt_lease",
        "attempt_timestamp",
        "attempt_error",
        "attempt_usage",
        "event_identity",
        "event_workspace",
        "event_schema",
        "event_dedupe",
        "event_payload_extra",
        "event_payload_state_version",
        "event_timestamp",
    ],
)
def test_projection_row_oracle_rejects_field_drift(mutation: str) -> None:
    scenario = load_scenario()
    state, fx = valid_event_state()
    verifier = next(step for step in state["steps"] if step["id"] == fx.step_ids["verifier"])
    attempt = next(
        row for row in state["attempts"] if row["step_id"] == fx.step_ids["verifier"]
    )
    verifier_started = next(
        event
        for event in state["events"]
        if event["event_type"] == "step_started"
        and event["step_id"] == fx.step_ids["verifier"]
    )
    if mutation == "step_workspace":
        verifier["workspace_id"] = "wrong-workspace"
    elif mutation == "step_branch":
        verifier["branch_key"] = "wrong-branch"
    elif mutation == "step_prompt":
        verifier["prompt_version_id"] = "wrong-prompt"
    elif mutation == "step_snapshot":
        verifier["execution_snapshot_id"] = "wrong-snapshot"
    elif mutation == "step_input":
        verifier["input_sha256"] = "wrong-input"
    elif mutation == "step_state_version":
        verifier["state_version"] += 1
    elif mutation == "step_timestamp":
        verifier["updated_at"] = "2026-09-01T00:00:59+00:00"
    elif mutation == "dependency_extra_field":
        state["dependencies"][0]["unexpected"] = True
    elif mutation == "attempt_owner":
        attempt["worker_instance_id"] = "wrong-worker"
    elif mutation == "attempt_input":
        attempt["input_sha256"] = "wrong-input"
    elif mutation == "attempt_output":
        attempt["output_sha256"] = "wrong-output"
    elif mutation == "attempt_lease":
        attempt["lease_token_hash"] = "wrong-lease"
    elif mutation == "attempt_timestamp":
        attempt["heartbeat_at"] = "2026-09-01T00:00:59+00:00"
    elif mutation == "attempt_error":
        attempt["error_code"] = "forged-error"
    elif mutation == "attempt_usage":
        attempt["provider_call_count"] = 1
    elif mutation == "event_identity":
        verifier_started["id"] = "not-a-uuid"
    elif mutation == "event_workspace":
        verifier_started["workspace_id"] = "wrong-workspace"
    elif mutation == "event_schema":
        verifier_started["event_schema_version"] = "2"
    elif mutation == "event_dedupe":
        verifier_started["dedupe_key"] += ":wrong"
    elif mutation == "event_payload_extra":
        verifier_started["payload_json"]["unexpected"] = True
    elif mutation == "event_payload_state_version":
        verifier_started["payload_json"]["stepStateVersion"] = 99
    else:
        verifier_started["created_at"] = "2026-09-01T00:00:59+00:00"
    assert scenario.event_oracle(state, fx)["strictPartialOrder"] is False


def test_causal_time_oracle_rejects_synchronized_verifier_time_reversal() -> None:
    scenario = load_scenario()
    state, fx = valid_event_state()
    verifier = next(step for step in state["steps"] if step["id"] == fx.step_ids["verifier"])
    attempt = next(
        row for row in state["attempts"] if row["step_id"] == fx.step_ids["verifier"]
    )
    started_event = next(
        event
        for event in state["events"]
        if event["event_type"] == "step_started"
        and event["step_id"] == fx.step_ids["verifier"]
    )
    finished_event = next(
        event
        for event in state["events"]
        if event["event_type"] == "step_succeeded"
        and event["step_id"] == fx.step_ids["verifier"]
    )
    started = "2026-09-01T00:00:59+00:00"
    finished = "2026-09-01T00:00:01+00:00"
    verifier["started_at"] = started
    verifier["finished_at"] = finished
    verifier["updated_at"] = finished
    attempt["started_at"] = started
    attempt["heartbeat_at"] = started
    attempt["finished_at"] = finished
    started_event["created_at"] = started
    finished_event["created_at"] = finished

    oracle = scenario.event_oracle(state, fx)
    assert oracle["causalTimeOracle"]["passed"] is False
    assert oracle["strictPartialOrder"] is False


def test_causal_time_oracle_rejects_synchronized_conflict_artifact_in_1999() -> None:
    scenario = load_scenario()
    state, fx = valid_event_state()
    forged = "1999-01-01T00:00:00+00:00"
    conflict = next(
        artifact
        for artifact in state["artifacts"]
        if artifact["artifact_kind"] == "conflict_report"
    )
    gate_attempt = next(
        attempt
        for attempt in state["attempts"]
        if attempt["step_id"] == fx.step_ids["conflict_gate"]
    )
    conflict["created_at"] = forged
    gate_attempt["finished_at"] = forged
    for event_type in ("artifact_published", "step_waiting"):
        event = next(
            row
            for row in state["events"]
            if row["event_type"] == event_type
            and (
                (row.get("payload_json") or {}).get("artifactId") == conflict["id"]
                or row.get("step_id") == fx.step_ids["conflict_gate"]
            )
        )
        event["created_at"] = forged

    oracle = scenario.event_oracle(state, fx)
    assert oracle["causalTimeOracle"]["passed"] is False
    assert oracle["strictPartialOrder"] is False


def test_artifact_oracle_accepts_exact_real_provenance() -> None:
    scenario = load_scenario()
    before, after, manifest, fx = valid_artifact_state()
    oracle = scenario.artifact_oracle(before, after, manifest, fx)
    assert oracle["passed"] is True
    assert oracle["baselineArtifactsImmutable"] is True
    assert oracle["baselineClaimRowsImmutable"] is True
    assert oracle["baselinePromptRowsImmutable"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_provenance",
        "wrong_workspace_with_matching_object",
        "wrong_supersedes",
        "wrong_expires_at",
        "wrong_created_at",
        "synchronized_conflict_time_before_attempt",
        "artifact_extra_field",
        "extra_artifact",
        "delete_baseline_artifact",
        "tamper_baseline_artifact",
        "add_baseline_claim",
        "remove_baseline_claim",
        "add_baseline_prompt",
        "remove_baseline_prompt",
        "fake_manifest",
        "manifest_extra_field",
        "extra_object",
    ],
)
def test_artifact_oracle_rejects_adversarial_publication(mutation: str) -> None:
    scenario = load_scenario()
    before, after, manifest, fx = valid_artifact_state()
    if mutation == "wrong_provenance":
        next(
            artifact
            for artifact in after["artifacts"]
            if artifact["artifact_kind"] == "conflict_report"
        )["generated_by_step_id"] = fx.step_ids["verifier"]
    elif mutation == "wrong_workspace_with_matching_object":
        artifact = next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "conflict_report"
        )
        old_key = artifact["object_key"]
        artifact["workspace_id"] = "wrong-workspace"
        artifact["object_key"] = old_key.replace(
            "research/workspace/", "research/wrong-workspace/"
        )
        manifest_item = next(item for item in manifest if item["key"] == old_key)
        manifest_item["key"] = artifact["object_key"]
    elif mutation == "wrong_supersedes":
        next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "conflict_report"
        )["supersedes_artifact_id"] = "forged"
    elif mutation == "wrong_expires_at":
        next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "execution_checkpoint"
        )["expires_at"] = "2026-09-02T00:00:00+00:00"
    elif mutation == "wrong_created_at":
        next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "execution_checkpoint"
        )["created_at"] = "2026-09-01T00:00:59+00:00"
    elif mutation == "synchronized_conflict_time_before_attempt":
        forged = "1999-01-01T00:00:00+00:00"
        conflict = next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "conflict_report"
        )
        conflict["created_at"] = forged
        next(
            attempt
            for attempt in after["attempts"]
            if attempt["step_id"] == fx.step_ids["conflict_gate"]
        )["finished_at"] = forged
    elif mutation == "artifact_extra_field":
        next(
            item
            for item in after["artifacts"]
            if item["artifact_kind"] == "conflict_report"
        )["unexpected"] = True
    elif mutation == "extra_artifact":
        after["artifacts"].append({"id": "extra", "artifact_kind": "final_report"})
    elif mutation == "delete_baseline_artifact":
        after["artifacts"] = [
            artifact for artifact in after["artifacts"] if artifact["id"] != "plan"
        ]
    elif mutation == "tamper_baseline_artifact":
        next(artifact for artifact in after["artifacts"] if artifact["id"] == "plan")[
            "artifact_kind"
        ] = "trace_export"
    elif mutation == "add_baseline_claim":
        after["artifactClaims"].append(
            {
                "artifact_id": "plan",
                "claim_id": "forged-claim",
                "claim_order": 1,
                "section_kind": "plan",
            }
        )
    elif mutation == "remove_baseline_claim":
        after["artifactClaims"] = [
            row for row in after["artifactClaims"] if row["artifact_id"] != "plan"
        ]
    elif mutation == "add_baseline_prompt":
        after["artifactPromptVersions"].append(
            {
                "artifact_id": "plan",
                "node_key": "critic",
                "prompt_version_id": fx.prompt_ids["critic"],
            }
        )
    elif mutation == "remove_baseline_prompt":
        after["artifactPromptVersions"] = [
            row
            for row in after["artifactPromptVersions"]
            if row["artifact_id"] != "plan"
        ]
    elif mutation == "fake_manifest":
        manifest[0]["sha256"] = "forged"
    elif mutation == "manifest_extra_field":
        manifest[0]["path"] = "forbidden"
    else:
        manifest.append({"key": "extra/object", "size": 0, "sha256": "empty"})
    assert scenario.artifact_oracle(before, after, manifest, fx)["passed"] is False


def test_idempotency_oracle_binds_aliased_request_and_complete_responses() -> None:
    scenario = load_scenario()
    state, context = valid_idempotency_state(scenario)
    assert set(context["expected_request_body"]) == {
        "expectedStateVersion",
        "expectedDecisionStateVersion",
        "inputArtifactSha256",
        "inputSnapshotSha256",
        "action",
        "comment",
    }
    oracle = scenario.decision_idempotency_oracle(state, **context)
    assert oracle["passed"] is True
    assert oracle["workspaceActorOperationPathKeyRequestHashExact"] is True
    assert oracle["winnerCompleteResponseExact"] is True
    assert oracle["loserFrozenResponseExact"] is True
    assert oracle["loserFrozenErrorFieldsExact"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_request_hash",
        "wrong_workspace",
        "wrong_actor",
        "wrong_operation",
        "wrong_path",
        "wrong_persisted_key",
        "winner_response_truncated",
        "winner_replay_hash",
        "loser_first_message",
        "loser_replay_request_id",
        "loser_replay_details",
        "persisted_frozen_response",
        "synchronized_winner_truncation",
        "synchronized_wrong_run",
        "synchronized_extra_error_details",
        "synchronized_all_keys",
        "extra_wrong_operation_row",
    ],
)
def test_idempotency_oracle_rejects_identity_or_response_drift(mutation: str) -> None:
    scenario = load_scenario()
    state, context = valid_idempotency_state(scenario)
    winner_record, loser_record = state["idempotencyRecords"]
    if mutation == "wrong_request_hash":
        winner_record["request_sha256"] = "f" * 64
    elif mutation == "wrong_workspace":
        winner_record["workspace_id"] = "other-workspace"
    elif mutation == "wrong_actor":
        loser_record["actor_user_id"] = "other-actor"
    elif mutation == "wrong_operation":
        winner_record["operation"] = "submit_plan_decision"
    elif mutation == "wrong_path":
        loser_record["canonical_resource_path"] += "/wrong"
    elif mutation == "wrong_persisted_key":
        loser_record["idempotency_key"] = "r2-i-conflict-decision-c"
    elif mutation == "winner_response_truncated":
        context["winner"]["responseJson"].pop("run")
    elif mutation == "winner_replay_hash":
        context["winner_replay"]["responseSha256"] = "0" * 64
    elif mutation == "loser_first_message":
        context["loser"]["errorMessage"] = "different"
    elif mutation == "loser_replay_request_id":
        context["loser_replay"]["errorRequestId"] = "different-request"
    elif mutation == "loser_replay_details":
        context["loser_replay"]["errorDetails"] = {"forged": True}
    elif mutation == "persisted_frozen_response":
        loser_record["response_json"]["error"]["message"] = "tampered"
    elif mutation == "synchronized_winner_truncation":
        for response_holder, response_key in (
            (winner_record, "response_json"),
            (context["winner"], "responseJson"),
            (context["winner_replay"], "responseJson"),
        ):
            response_holder[response_key].pop("run")
        context["winner"]["responseSha256"] = scenario.canonical_sha256(
            context["winner"]["responseJson"]
        )
        context["winner_replay"]["responseSha256"] = scenario.canonical_sha256(
            context["winner_replay"]["responseJson"]
        )
    elif mutation == "synchronized_wrong_run":
        for response in (
            winner_record["response_json"],
            context["winner"]["responseJson"],
            context["winner_replay"]["responseJson"],
        ):
            response["run"]["id"] = "wrong-run"
        context["winner"]["responseSha256"] = scenario.canonical_sha256(
            context["winner"]["responseJson"]
        )
        context["winner_replay"]["responseSha256"] = scenario.canonical_sha256(
            context["winner_replay"]["responseJson"]
        )
    elif mutation == "synchronized_extra_error_details":
        for response in (
            loser_record["response_json"],
            context["loser"]["responseJson"],
            context["loser_replay"]["responseJson"],
        ):
            response["error"]["details"] = {"forged": True}
        for process in (context["loser"], context["loser_replay"]):
            process["errorDetails"] = {"forged": True}
            process["responseSha256"] = scenario.canonical_sha256(
                process["responseJson"]
            )
    elif mutation == "synchronized_all_keys":
        replacement_keys = ("forged-decision-a", "forged-decision-b")
        winner_record["idempotency_key"], loser_record["idempotency_key"] = replacement_keys
        for process, replacement in (
            (context["winner"], replacement_keys[0]),
            (context["loser"], replacement_keys[1]),
            (context["winner_replay"], replacement_keys[0]),
            (context["loser_replay"], replacement_keys[1]),
        ):
            process["idempotencyKey"] = replacement
    else:
        extra = copy.deepcopy(loser_record)
        extra["id"] = "extra-operation-row"
        extra["operation"] = "submit_conflict_decision_typo"
        state["idempotencyRecords"].append(extra)
    assert scenario.decision_idempotency_oracle(state, **context)["passed"] is False


def test_production_source_proof_matches_head_and_rejects_dirty_blob() -> None:
    scenario = load_scenario()
    proof = scenario.production_source_proof()
    assert proof["matchesBaseSha"] is True
    assert set(proof["productionSourceSha256"]) == set(scenario.PRODUCTION_SOURCE_FILES)
    assert all(len(value) == 64 for value in proof["productionSourceSha256"].values())

    def dirty_git_reader(*args: str) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return b"base\n"
        if args[0] == "rev-parse":
            return b"expected-blob\n"
        if args[0] == "hash-object":
            return b"dirty-blob\n"
        raise AssertionError(f"unexpected git command after dirty mismatch: {args}")

    with pytest.raises(AssertionError, match="production source differs"):
        scenario.production_source_proof(
            git_reader=dirty_git_reader,
            source_files=(scenario.PRODUCTION_SOURCE_FILES[0],),
        )


def test_object_manifest_contains_no_path_or_payload(tmp_path: Path) -> None:
    scenario = load_scenario()
    object_path = tmp_path / "research" / "workspace" / "run" / "artifact.json"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b'{"schemaVersion":1}')
    manifest = scenario.object_manifest(tmp_path)
    assert manifest == [
        {
            "key": "research/workspace/run/artifact.json",
            "size": 19,
            "sha256": scenario.sha_bytes(b'{"schemaVersion":1}'),
        }
    ]
    assert str(tmp_path) not in str(manifest)
    assert "schemaVersion" not in str(manifest)
