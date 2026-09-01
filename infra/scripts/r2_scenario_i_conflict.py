"""R2-I persisted conflict decision and exact-once resume proof.

The fixture has real workflow/prompt/plan provenance foreign keys. Every mutable
transition under proof is executed by a separate OS process through production
commands; this module only seeds, coordinates, projects, and asserts the oracle.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ai_pdf_api.schemas.research import ConflictDecisionRequest
from citeframe_persistence.models import (
    HumanDecision,
    HumanDecisionClaim,
    PromptVersion,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchEvent,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchIdempotencyRecord,
    ResearchPlanRevision,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
    WorkflowPromptBinding,
    WorkflowVersion,
)
from citeframe_research_persistence.errors import canonical_sha256
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
WORKER_ENTRY = ROOT / "infra/scripts/r2_scenario_i_worker.py"
SCENARIO = "i_conflict_decision_resume"
NODE_KINDS = {
    "planner": "planner",
    "researchers": "researcher",
    "verifier": "verifier",
    "critic": "critic",
    "synthesizer": "synthesizer",
}
PRODUCTION_SOURCE_FILES = (
    "apps/api/src/ai_pdf_api/schemas/research.py",
    "apps/api/src/ai_pdf_api/services/research/research_decisions.py",
    "apps/api/src/ai_pdf_api/services/research/research_events.py",
    "apps/api/src/ai_pdf_api/services/research/research_idempotency.py",
    "apps/api/src/ai_pdf_api/services/research/research_runs.py",
    "apps/api/src/ai_pdf_api/services/research/research_views.py",
    "packages/research-persistence/src/citeframe_research_persistence/completion.py",
    "packages/research-persistence/src/citeframe_research_persistence/errors.py",
    "packages/research-persistence/src/citeframe_research_persistence/events.py",
    "packages/research-persistence/src/citeframe_research_persistence/idempotency.py",
    "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    "packages/research-persistence/src/citeframe_research_persistence/locks.py",
    "packages/research-persistence/src/citeframe_research_persistence/membership.py",
    "packages/research-persistence/src/citeframe_research_persistence/publication.py",
    "packages/research-persistence/src/citeframe_research_persistence/types.py",
)

DECISION_KEYS_BY_WORKER = {
    "i-decision-a": "r2-i-conflict-decision-a",
    "i-decision-b": "r2-i-conflict-decision-b",
}


@dataclass(frozen=True)
class ConflictFixture:
    schema: str
    workspace_id: str
    actor_user_id: str
    run_id: str
    plan_revision_id: str
    snapshot_id: str
    workflow_id: str
    prompt_ids: dict[str, str]
    claim_id: str
    step_ids: dict[str, str]
    step_keys: dict[str, str]
    decision_keys_by_worker: dict[str, str]


def uid(schema: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"citeframe-r2-i/{schema}/{key}"))


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return sha_bytes(value.encode("utf-8"))


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def conflict_decision_request(
    *,
    expected_state_version: int,
    expected_decision_state_version: int,
    input_artifact_sha256: str,
    input_snapshot_sha256: str,
) -> ConflictDecisionRequest:
    """Build the exact aliased request body hashed by production idempotency."""
    return ConflictDecisionRequest(
        expected_state_version=expected_state_version,
        expected_decision_state_version=expected_decision_state_version,
        input_artifact_sha256=input_artifact_sha256,
        input_snapshot_sha256=input_snapshot_sha256,
        action="keep_as_unresolved",
        comment="R2-I persisted conflict resume proof.",
    )


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def production_source_proof(
    *,
    git_reader: Callable[..., bytes] = git_bytes,
    source_files: tuple[str, ...] = PRODUCTION_SOURCE_FILES,
) -> dict[str, Any]:
    """Bind every production entry used by R2-I to the checked-out HEAD tree.

    ``git hash-object --path`` applies repository clean filters, so this remains exact
    on Windows even when ``core.autocrlf`` materializes CRLF in the worktree.
    """
    base_sha = git_reader("rev-parse", "HEAD").decode("ascii").strip()
    hashes: dict[str, str] = {}
    blob_ids: dict[str, str] = {}
    for relative in source_files:
        expected_blob = git_reader("rev-parse", f"{base_sha}:{relative}").decode("ascii").strip()
        current_blob = git_reader(
            "hash-object", f"--path={relative}", relative
        ).decode("ascii").strip()
        if current_blob != expected_blob:
            raise AssertionError(
                f"R2-I production source differs from baseSha: {relative}"
            )
        canonical_source = git_reader("show", f"{base_sha}:{relative}")
        hashes[relative] = sha_bytes(canonical_source)
        blob_ids[relative] = expected_blob
    return {
        "baseSha": base_sha,
        "productionSourceSha256": hashes,
        "productionSourceGitBlobIds": blob_ids,
        "aggregateSha256": sha_bytes(canonical_bytes(hashes)),
        "matchesBaseSha": True,
    }


def step_by_kind(state: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [step for step in state["steps"] if step["step_kind"] == kind]
    if len(matches) != 1:
        raise AssertionError(f"expected one {kind} Step, found {len(matches)}")
    return matches[0]


def attempts_for_step(state: dict[str, Any], step_id: str) -> list[dict[str, Any]]:
    return [attempt for attempt in state["attempts"] if attempt["step_id"] == step_id]


def event_for(
    state: dict[str, Any],
    *,
    event_type: str,
    step_id: str,
) -> dict[str, Any]:
    matches = [
        event
        for event in state["events"]
        if event["event_type"] == event_type and event["step_id"] == step_id
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {event_type} event for {step_id}, found {len(matches)}"
        )
    return matches[0]


def row_value(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            value = value.astimezone(UTC).isoformat()
        result[column.name] = value
    return result


def ordered_rows(db: Any, model: Any, *filters: Any) -> list[dict[str, Any]]:
    primary_keys = tuple(model.__table__.primary_key.columns)
    statement = select(model).where(*filters).order_by(*primary_keys)
    return [row_value(row) for row in db.scalars(statement).all()]


def full_projection(
    harness: Any,
    fixture: ConflictFixture,
    base_projection: Callable[[Any, str], dict[str, Any]],
) -> dict[str, Any]:
    state = base_projection(harness, fixture.run_id)
    with harness.sessions() as db:
        state.update(
            {
                "executionSnapshots": ordered_rows(
                    db,
                    ResearchExecutionSnapshot,
                    ResearchExecutionSnapshot.run_id == fixture.run_id,
                ),
                "executionPromptVersions": ordered_rows(
                    db,
                    ResearchExecutionPromptVersion,
                    ResearchExecutionPromptVersion.execution_snapshot_id
                    == fixture.snapshot_id,
                ),
                "decisions": ordered_rows(
                    db, HumanDecision, HumanDecision.run_id == fixture.run_id
                ),
                "decisionClaims": [
                    row_value(row)
                    for row in db.scalars(
                        select(HumanDecisionClaim)
                        .join(
                            HumanDecision,
                            HumanDecision.id == HumanDecisionClaim.decision_id,
                        )
                        .where(HumanDecision.run_id == fixture.run_id)
                        .order_by(
                            HumanDecisionClaim.decision_id,
                            HumanDecisionClaim.claim_id,
                        )
                    ).all()
                ],
                "claims": ordered_rows(
                    db, ResearchClaim, ResearchClaim.run_id == fixture.run_id
                ),
                "artifacts": ordered_rows(
                    db, ResearchArtifact, ResearchArtifact.run_id == fixture.run_id
                ),
                "artifactClaims": [
                    row_value(row)
                    for row in db.scalars(
                        select(ResearchArtifactClaim)
                        .join(
                            ResearchArtifact,
                            ResearchArtifact.id == ResearchArtifactClaim.artifact_id,
                        )
                        .where(ResearchArtifact.run_id == fixture.run_id)
                        .order_by(
                            ResearchArtifactClaim.artifact_id,
                            ResearchArtifactClaim.claim_id,
                        )
                    ).all()
                ],
                "artifactPromptVersions": [
                    row_value(row)
                    for row in db.scalars(
                        select(ResearchArtifactPromptVersion)
                        .join(
                            ResearchArtifact,
                            ResearchArtifact.id
                            == ResearchArtifactPromptVersion.artifact_id,
                        )
                        .where(ResearchArtifact.run_id == fixture.run_id)
                        .order_by(
                            ResearchArtifactPromptVersion.artifact_id,
                            ResearchArtifactPromptVersion.node_key,
                        )
                    ).all()
                ],
                "dependencies": [
                    row_value(row)
                    for row in db.scalars(
                        select(ResearchStepDependency)
                        .join(
                            ResearchStep,
                            ResearchStep.id == ResearchStepDependency.step_id,
                        )
                        .where(ResearchStep.run_id == fixture.run_id)
                        .order_by(
                            ResearchStepDependency.step_id,
                            ResearchStepDependency.depends_on_step_id,
                        )
                    ).all()
                ],
                "idempotencyRecords": ordered_rows(
                    db,
                    ResearchIdempotencyRecord,
                    ResearchIdempotencyRecord.workspace_id == harness.workspace_id,
                ),
                "workflowVersions": ordered_rows(
                    db, WorkflowVersion, WorkflowVersion.id == fixture.workflow_id
                ),
                "workflowPromptBindings": ordered_rows(
                    db,
                    WorkflowPromptBinding,
                    WorkflowPromptBinding.workflow_version_id == fixture.workflow_id,
                ),
                "promptVersions": ordered_rows(
                    db,
                    PromptVersion,
                    PromptVersion.id.in_(tuple(fixture.prompt_ids.values())),
                ),
            }
        )
    return state


def make_step(
    harness: Any,
    *,
    run_id: str,
    step_id: str,
    step_key: str,
    step_kind: str,
    status: str,
    created_at: datetime,
    snapshot_id: str | None = None,
    revision_id: str | None = None,
    prompt_id: str | None = None,
    branch_key: str | None = None,
    current_attempt_number: int = 0,
) -> ResearchStep:
    return ResearchStep(
        id=step_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        plan_revision_id=revision_id,
        execution_snapshot_id=snapshot_id,
        step_key=step_key,
        step_kind=step_kind,
        branch_key=branch_key,
        status=status,
        state_version=1,
        prompt_version_id=prompt_id,
        max_attempts_snapshot=3,
        current_attempt_number=current_attempt_number,
        input_sha256=sha_text(f"{run_id}:{step_key}:input"),
        queued_at=created_at if status in {"queued", "succeeded"} else None,
        started_at=created_at if status == "succeeded" else None,
        finished_at=created_at if status == "succeeded" else None,
        created_at=created_at,
        updated_at=created_at,
    )


def make_seed_event(
    harness: Any,
    *,
    run_id: str,
    seq: int,
    event_type: str,
    dedupe_key: str,
    payload: dict[str, object],
    created_at: datetime,
    step_id: str | None = None,
    attempt_id: str | None = None,
) -> ResearchEvent:
    return ResearchEvent(
        id=uid(harness.schema, f"event:{seq}:{dedupe_key}"),
        workspace_id=harness.workspace_id,
        run_id=run_id,
        seq=seq,
        event_type=event_type,
        event_schema_version="1",
        step_id=step_id,
        attempt_id=attempt_id,
        dedupe_key=dedupe_key,
        payload_json=payload,
        created_at=created_at,
    )


def baseline_lifecycle_events(
    harness: Any,
    *,
    run: ResearchRun,
    planner: ResearchStep,
    plan_gate: ResearchStep,
    researcher: ResearchStep,
    verifier: ResearchStep,
    plan_attempt: ResearchStepAttempt,
    plan_gate_attempt: ResearchStepAttempt,
    researcher_attempt: ResearchStepAttempt,
    plan_artifact: ResearchArtifact,
    plan_decision: HumanDecision,
    now: datetime,
) -> list[ResearchEvent]:
    events: list[ResearchEvent] = []

    def add(
        event_type: str,
        dedupe_key: str,
        payload: dict[str, object],
        *,
        step_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        seq = len(events) + 1
        events.append(
            make_seed_event(
                harness,
                run_id=run.id,
                seq=seq,
                event_type=event_type,
                dedupe_key=dedupe_key,
                payload=payload,
                created_at=now + timedelta(microseconds=seq),
                step_id=step_id,
                attempt_id=attempt_id,
            )
        )

    def queued(step: ResearchStep, *, step_state_version: int) -> None:
        seq = len(events) + 1
        add(
            "step_queued",
            f"step-queued:{step.id}:0",
            {
                "stepId": step.id,
                "stepKind": step.step_kind,
                "branchKey": step.branch_key,
                "attemptNumber": 0,
                "stepStateVersion": step_state_version,
                "runStateVersion": seq,
            },
            step_id=step.id,
        )

    def started(step: ResearchStep, attempt: ResearchStepAttempt, *, step_state_version: int) -> None:
        seq = len(events) + 1
        add(
            "step_started",
            f"step-started:{attempt.id}",
            {
                "stepId": step.id,
                "stepKind": step.step_kind,
                "branchKey": step.branch_key,
                "attemptId": attempt.id,
                "attemptNumber": attempt.attempt_number,
                "stepStateVersion": step_state_version,
                "runStateVersion": seq,
            },
            step_id=step.id,
            attempt_id=attempt.id,
        )

    def succeeded(step: ResearchStep, attempt: ResearchStepAttempt, *, step_state_version: int) -> None:
        seq = len(events) + 1
        add(
            "step_succeeded",
            f"step-succeeded:{attempt.id}",
            {
                "stepId": step.id,
                "stepKind": step.step_kind,
                "attemptId": attempt.id,
                "attemptNumber": attempt.attempt_number,
                "evidenceCount": 0,
                "artifactIds": [plan_artifact.id] if step.id == planner.id else [],
                "stepStateVersion": step_state_version,
                "runStateVersion": seq,
            },
            step_id=step.id,
            attempt_id=attempt.id,
        )

    add(
        "run_created",
        f"run-created:{run.id}",
        {
            "status": "planning",
            "createdByUserId": run.created_by_user_id,
            "runStateVersion": 1,
        },
    )
    queued(planner, step_state_version=1)
    add(
        "run_status_changed",
        f"worker-run-started:{plan_attempt.id}",
        {
            "previousStatus": "planning",
            "status": "running",
            "runStateVersion": 3,
            "reasonCode": None,
        },
    )
    started(planner, plan_attempt, step_state_version=2)
    add(
        "artifact_published",
        f"artifact-published:{plan_artifact.id}",
        {
            "artifactId": plan_artifact.id,
            "artifactKind": plan_artifact.artifact_kind,
            "visibility": plan_artifact.visibility,
            "byteSize": plan_artifact.byte_size,
            "sha256": plan_artifact.content_sha256,
            "runStateVersion": 5,
        },
    )
    succeeded(planner, plan_attempt, step_state_version=3)
    queued(plan_gate, step_state_version=1)
    started(plan_gate, plan_gate_attempt, step_state_version=2)
    add(
        "step_waiting",
        f"step-waiting:{plan_gate.id}:{plan_decision.id}",
        {
            "stepId": plan_gate.id,
            "stepKind": plan_gate.step_kind,
            "decisionId": plan_decision.id,
            "decisionType": plan_decision.decision_type,
            "stepStateVersion": 3,
            "decisionStateVersion": 1,
            "runStateVersion": 9,
        },
        step_id=plan_gate.id,
        attempt_id=plan_gate_attempt.id,
    )
    add(
        "approval_requested",
        f"approval-requested:{plan_decision.id}",
        {
            "decisionId": plan_decision.id,
            "decisionType": plan_decision.decision_type,
            "inputArtifactId": plan_artifact.id,
            "inputArtifactSha256": plan_artifact.content_sha256,
            "decisionStateVersion": 1,
            "runStateVersion": 10,
        },
    )
    add(
        "run_status_changed",
        f"plan-waiting:{plan_decision.id}",
        {
            "previousStatus": "running",
            "status": "awaiting_plan_approval",
            "runStateVersion": 11,
            "reasonCode": None,
        },
    )
    add(
        "decision_submitted",
        f"decision-submitted:{plan_decision.id}",
        {
            "decisionId": plan_decision.id,
            "decisionType": plan_decision.decision_type,
            "inputArtifactId": plan_artifact.id,
            "inputArtifactSha256": plan_artifact.content_sha256,
            "action": "approve",
            "actorUserId": harness.user_id,
            "decisionStateVersion": 2,
            "runStateVersion": 12,
        },
        step_id=plan_gate.id,
    )
    add(
        "run_status_changed",
        f"plan-status:{plan_decision.id}",
        {
            "previousStatus": "awaiting_plan_approval",
            "status": "queued",
            "runStateVersion": 13,
            "reasonCode": None,
        },
    )
    queued(researcher, step_state_version=1)
    add(
        "run_status_changed",
        f"worker-run-started:{researcher_attempt.id}",
        {
            "previousStatus": "queued",
            "status": "running",
            "runStateVersion": 15,
            "reasonCode": None,
        },
    )
    started(researcher, researcher_attempt, step_state_version=2)
    succeeded(researcher, researcher_attempt, step_state_version=3)
    queued(verifier, step_state_version=2)
    assert len(events) == 18
    return events


def seed_fixture(harness: Any) -> ConflictFixture:
    now = datetime.now(UTC) - timedelta(seconds=2)
    run_id = uid(harness.schema, "run")
    workflow_id = uid(harness.schema, "workflow")
    revision_id = uid(harness.schema, "plan-revision")
    plan_decision_id = uid(harness.schema, "plan-decision")
    snapshot_id = uid(harness.schema, "execution-snapshot")
    ledger_id = uid(harness.schema, "execution-ledger")
    plan_artifact_id = uid(harness.schema, "plan-artifact")
    plan_attempt_id = uid(harness.schema, "plan-attempt")
    plan_gate_attempt_id = uid(harness.schema, "plan-gate-attempt")
    researcher_attempt_id = uid(harness.schema, "researcher-attempt")
    prompt_ids = {
        node: uid(harness.schema, f"prompt:{node}") for node in NODE_KINDS
    }
    step_keys = {
        "planner": "planner:r2-i",
        "plan_gate": "plan-approval-gate:r2-i",
        "researcher": "researcher:r2-i",
        "verifier": "verifier:r2-i",
        "critic": "critic:r2-i",
        "conflict_gate": "conflict-decision-gate:r2-i",
        "synthesizer": "synthesizer:r2-i",
        "publisher": "artifact-publisher:r2-i",
    }
    step_ids = {key: uid(harness.schema, f"step:{key}") for key in step_keys}
    claim_id = uid(harness.schema, "claim:conflicted")

    manifest = {
        "schemaVersion": "research-workflow-v1",
        "nodes": list(NODE_KINDS),
    }
    workflow = WorkflowVersion(
        id=workflow_id,
        workflow_key=f"r2-i-{harness.schema}",
        version_number=1,
        availability="active",
        manifest_schema_version="research-workflow-v1",
        manifest_json=manifest,
        manifest_sha256=sha_bytes(canonical_bytes(manifest)),
        created_by_user_id=harness.user_id,
        created_at=now,
    )
    prompts: list[PromptVersion] = []
    bindings: list[WorkflowPromptBinding] = []
    for node, step_kind in NODE_KINDS.items():
        template = f"R2-I {node} deterministic proof prompt."
        prompts.append(
            PromptVersion(
                id=prompt_ids[node],
                prompt_key=f"r2-i-{harness.schema}-{node}",
                version_number=1,
                step_kind=step_kind,
                availability="active",
                template_text=template,
                variables_schema_version="1",
                variables_schema_json={"type": "object"},
                template_sha256=sha_text(template),
                created_by_user_id=harness.user_id,
                created_at=now,
            )
        )
        bindings.append(
            WorkflowPromptBinding(
                workflow_version_id=workflow_id,
                node_key=node,
                prompt_version_id=prompt_ids[node],
            )
        )

    run = ResearchRun(
        id=run_id,
        workspace_id=harness.workspace_id,
        created_by_user_id=harness.user_id,
        status="running",
        state_version=18,
        next_event_seq=19,
        cost_currency="USD",
        created_at=now,
        started_at=now,
        updated_at=now + timedelta(microseconds=18),
    )
    revision = ResearchPlanRevision(
        id=revision_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        revision_number=1,
        created_by_user_id=harness.user_id,
        question_text="R2-I conflict decision proof",
        scope_mode="all_ready",
        proposed_workflow_version_id=workflow_id,
        planner_prompt_version_id=prompt_ids["planner"],
        proposed_generation_provider="test",
        proposed_generation_model="r2-i-deterministic",
        proposed_provider_config_fingerprint=sha_text("r2-i-provider"),
        proposed_pricing_version="r2-i-pricing-v1",
        proposed_data_boundary_policy_version="r2-i-boundary-v1",
        proposed_embedding_provider="test",
        proposed_embedding_model="r2-i-embedding",
        proposed_embedding_version="1",
        proposed_retrieval_strategy="hybrid",
        proposed_retrieval_top_k=6,
        planning_max_provider_calls=2,
        planning_max_input_tokens=1_000,
        planning_max_output_tokens=1_000,
        planning_max_cost_microunits=10_000,
        planning_cost_currency="USD",
        planning_max_step_attempts=2,
        planning_budget_policy_version="r2-i-plan-budget-v1",
        planning_retry_policy_version="r2-i-plan-retry-v1",
        planning_max_step_timeout_seconds=120,
        planning_max_provider_timeout_seconds=60,
        proposed_max_parallel_researchers=2,
        proposed_max_step_attempts=3,
        proposed_max_provider_calls=10,
        proposed_max_tool_calls=10,
        proposed_max_input_tokens=10_000,
        proposed_max_output_tokens=10_000,
        proposed_max_cost_microunits=100_000,
        proposed_cost_currency="USD",
        proposed_budget_policy_version="r2-i-budget-v1",
        proposed_retry_policy_version="r2-i-retry-v1",
        proposed_max_run_timeout_seconds=3_600,
        proposed_max_step_timeout_seconds=600,
        proposed_max_provider_timeout_seconds=120,
        planning_snapshot_sha256=sha_text("r2-i-planning-snapshot"),
        created_at=now,
    )
    planner = make_step(
        harness,
        run_id=run_id,
        step_id=step_ids["planner"],
        step_key=step_keys["planner"],
        step_kind="planner",
        status="succeeded",
        created_at=now,
        revision_id=revision_id,
        prompt_id=prompt_ids["planner"],
        current_attempt_number=1,
    )
    planner.state_version = 3
    plan_gate = make_step(
        harness,
        run_id=run_id,
        step_id=step_ids["plan_gate"],
        step_key=step_keys["plan_gate"],
        step_kind="plan_approval_gate",
        status="succeeded",
        created_at=now + timedelta(microseconds=1),
        revision_id=revision_id,
        current_attempt_number=1,
    )
    plan_gate.state_version = 4
    plan_payload = canonical_bytes(
        {
            "summary": "R2-I deterministic plan",
            "subproblems": [],
            "knownGaps": [],
            "estimatedProviderCalls": 1,
        }
    )
    plan_sha = sha_bytes(plan_payload)
    plan_attempt = ResearchStepAttempt(
        id=plan_attempt_id,
        workspace_id=harness.workspace_id,
        step_id=planner.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=planner.input_sha256,
        output_sha256=plan_sha,
        worker_instance_id="r2-i-seed-planner",
        started_at=now,
        finished_at=now,
    )
    plan_artifact = ResearchArtifact(
        id=plan_artifact_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        generated_by_step_id=planner.id,
        generated_by_attempt_id=plan_attempt.id,
        artifact_kind="research_plan",
        visibility="user",
        logical_key="research-plan:1",
        schema_version="1",
        object_key=f"research/{harness.workspace_id}/{run_id}/plan/plan.json",
        content_type="application/json",
        byte_size=len(plan_payload),
        content_sha256=plan_sha,
        workflow_version_id=workflow_id,
        direct_prompt_version_id=prompt_ids["planner"],
        generation_provider="test",
        generation_model="r2-i-deterministic",
        retention_class="workspace_lifetime",
        created_at=now,
    )
    plan_decision = HumanDecision(
        id=plan_decision_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        gate_step_id=plan_gate.id,
        decision_type="plan_approval",
        request_number=1,
        status="submitted",
        state_version=2,
        input_artifact_id=plan_artifact.id,
        input_artifact_sha256=plan_sha,
        input_snapshot_sha256=revision.planning_snapshot_sha256,
        requested_at=now,
        decided_by_user_id=harness.user_id,
        action="approve",
        comment_text="R2-I fixture approval.",
        decided_at=now,
    )
    snapshot = ResearchExecutionSnapshot(
        id=snapshot_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        approved_plan_revision_id=revision_id,
        approval_decision_id=plan_decision_id,
        approved_plan_artifact_id=plan_artifact_id,
        approved_plan_artifact_sha256=plan_sha,
        input_version=1,
        question_text=revision.question_text,
        scope_mode="all_ready",
        workflow_version_id=workflow_id,
        generation_provider="test",
        generation_model="r2-i-deterministic",
        provider_config_fingerprint=revision.proposed_provider_config_fingerprint,
        pricing_version="r2-i-pricing-v1",
        data_boundary_policy_version="r2-i-boundary-v1",
        embedding_provider="test",
        embedding_model="r2-i-embedding",
        embedding_version="1",
        retrieval_strategy="hybrid",
        retrieval_top_k=6,
        max_parallel_researchers=2,
        max_step_attempts=3,
        max_provider_calls=10,
        max_tool_calls=10,
        max_input_tokens=10_000,
        max_output_tokens=10_000,
        max_cost_microunits=100_000,
        cost_currency="USD",
        budget_policy_version="r2-i-budget-v1",
        retry_policy_version="r2-i-retry-v1",
        max_run_timeout_seconds=3_600,
        max_step_timeout_seconds=600,
        max_provider_timeout_seconds=120,
        execution_snapshot_sha256=sha_text("r2-i-execution-snapshot"),
        created_at=now,
    )
    ledger = ResearchBudgetLedger(
        id=ledger_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        execution_snapshot_id=snapshot_id,
        currency="USD",
        state_version=1,
        usage_final=True,
        updated_at=now,
    )
    execution_steps = [
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["researcher"],
            step_key=step_keys["researcher"],
            step_kind="researcher",
            branch_key="r2-i-branch",
            status="succeeded",
            created_at=now + timedelta(microseconds=2),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["researchers"],
            current_attempt_number=1,
        ),
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["verifier"],
            step_key=step_keys["verifier"],
            step_kind="verifier",
            status="queued",
            created_at=now + timedelta(microseconds=3),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["verifier"],
        ),
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["critic"],
            step_key=step_keys["critic"],
            step_kind="critic",
            status="pending",
            created_at=now + timedelta(microseconds=4),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["critic"],
        ),
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["conflict_gate"],
            step_key=step_keys["conflict_gate"],
            step_kind="conflict_decision_gate",
            status="pending",
            created_at=now + timedelta(microseconds=5),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["critic"],
        ),
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["synthesizer"],
            step_key=step_keys["synthesizer"],
            step_kind="synthesizer",
            status="pending",
            created_at=now + timedelta(microseconds=6),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["synthesizer"],
        ),
        make_step(
            harness,
            run_id=run_id,
            step_id=step_ids["publisher"],
            step_key=step_keys["publisher"],
            step_kind="artifact_publisher",
            status="pending",
            created_at=now + timedelta(microseconds=7),
            snapshot_id=snapshot_id,
            prompt_id=prompt_ids["synthesizer"],
        ),
    ]
    researcher = execution_steps[0]
    verifier = execution_steps[1]
    researcher.state_version = 3
    verifier.state_version = 2
    dependencies = [
        ResearchStepDependency(
            step_id=plan_gate.id,
            depends_on_step_id=planner.id,
        ),
        ResearchStepDependency(
            step_id=step_ids["verifier"],
            depends_on_step_id=step_ids["researcher"],
        ),
        ResearchStepDependency(
            step_id=step_ids["critic"],
            depends_on_step_id=step_ids["verifier"],
        ),
        ResearchStepDependency(
            step_id=step_ids["conflict_gate"],
            depends_on_step_id=step_ids["critic"],
        ),
        ResearchStepDependency(
            step_id=step_ids["synthesizer"],
            depends_on_step_id=step_ids["conflict_gate"],
        ),
        ResearchStepDependency(
            step_id=step_ids["publisher"],
            depends_on_step_id=step_ids["synthesizer"],
        ),
    ]
    claim_text = "The deterministic R2-I Claim remains visible as unresolved."
    claim = ResearchClaim(
        id=claim_id,
        workspace_id=harness.workspace_id,
        run_id=run_id,
        claim_key="r2-i-conflicted-claim",
        claim_order=0,
        statement_text=claim_text,
        statement_sha256=sha_text(claim_text),
        produced_by_step_id=step_ids["researcher"],
        verification_status="pending",
        conflict_status="none",
        created_at=now,
    )
    plan_gate_attempt = ResearchStepAttempt(
        id=plan_gate_attempt_id,
        workspace_id=harness.workspace_id,
        step_id=plan_gate.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=plan_gate.input_sha256,
        output_sha256=plan_sha,
        worker_instance_id="r2-i-seed-plan-gate",
        started_at=now + timedelta(microseconds=8),
        finished_at=now + timedelta(microseconds=9),
    )
    researcher_output_sha = sha_text("r2-i-researcher-output")
    researcher_attempt = ResearchStepAttempt(
        id=researcher_attempt_id,
        workspace_id=harness.workspace_id,
        step_id=researcher.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=researcher.input_sha256,
        output_sha256=researcher_output_sha,
        worker_instance_id="r2-i-seed-researcher",
        started_at=now + timedelta(microseconds=16),
        finished_at=now + timedelta(microseconds=17),
    )
    seed_events = baseline_lifecycle_events(
        harness,
        run=run,
        planner=planner,
        plan_gate=plan_gate,
        researcher=researcher,
        verifier=verifier,
        plan_attempt=plan_attempt,
        plan_gate_attempt=plan_gate_attempt,
        researcher_attempt=researcher_attempt,
        plan_artifact=plan_artifact,
        plan_decision=plan_decision,
        now=now,
    )

    with harness.sessions() as db:
        db.add_all([workflow, *prompts])
        db.flush()
        db.add_all(bindings)
        db.add(run)
        db.flush()
        db.add(revision)
        db.flush()
        db.add_all([planner, plan_gate])
        db.flush()
        db.add_all([plan_attempt, plan_gate_attempt])
        db.flush()
        db.add(plan_artifact)
        db.flush()
        db.add(
            ResearchArtifactPromptVersion(
                artifact_id=plan_artifact.id,
                node_key="planner",
                prompt_version_id=prompt_ids["planner"],
            )
        )
        db.add(plan_decision)
        db.flush()
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ResearchExecutionPromptVersion(
                    execution_snapshot_id=snapshot_id,
                    node_key=node,
                    prompt_version_id=prompt_ids[node],
                )
                for node in NODE_KINDS
            ]
        )
        db.add(ledger)
        db.add_all(execution_steps)
        db.flush()
        db.add(researcher_attempt)
        db.flush()
        db.add_all(dependencies)
        db.add(claim)
        db.add_all(seed_events)
        run.approved_execution_snapshot_id = snapshot_id
        db.commit()

    return ConflictFixture(
        schema=harness.schema,
        workspace_id=harness.workspace_id,
        actor_user_id=harness.user_id,
        run_id=run_id,
        plan_revision_id=revision_id,
        snapshot_id=snapshot_id,
        workflow_id=workflow_id,
        prompt_ids=prompt_ids,
        claim_id=claim_id,
        step_ids=step_ids,
        step_keys=step_keys,
        decision_keys_by_worker=dict(DECISION_KEYS_BY_WORKER),
    )


def read_ready_records(paths: list[Path], timeout_seconds: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(path.is_file() for path in paths):
            return [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        time.sleep(0.02)
    raise TimeoutError("R2-I workers did not reach the ready barrier")


def parse_worker_output(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    stdout, stderr = process.communicate(timeout=timeout_seconds)
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(
            f"R2-I worker {process.pid} emitted {len(lines)} JSON records: {stderr!r}"
        )
    record = json.loads(lines[0])
    record["controllerObservedExitStatus"] = process.returncode
    record["stderr"] = stderr
    return record


def terminate_workers(workers: list[subprocess.Popen[str]]) -> None:
    for worker in workers:
        if worker.poll() is None:
            worker.terminate()
    for worker in workers:
        if worker.poll() is None:
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)


def launch_workers(
    *,
    harness: Any,
    database_url: str,
    object_root: Path,
    specs: list[dict[str, object]],
    timeout_seconds: float,
    observe_ready_worker_backends: Callable[
        [str, list[dict[str, Any]]], dict[str, Any]
    ],
) -> dict[str, Any]:
    workers: list[subprocess.Popen[str]] = []
    commands: dict[str, list[str]] = {}
    option_names = {
        "runId": "--run-id",
        "stepKey": "--step-key",
        "claimId": "--claim-id",
        "workspaceId": "--workspace-id",
        "actorUserId": "--actor-user-id",
        "decisionId": "--decision-id",
        "expectedStateVersion": "--expected-state-version",
        "expectedDecisionStateVersion": "--expected-decision-state-version",
        "inputArtifactSha256": "--input-artifact-sha256",
        "inputSnapshotSha256": "--input-snapshot-sha256",
        "idempotencyKey": "--idempotency-key",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="citeframe-r2-i-barrier-") as directory:
            barrier_root = Path(directory)
            ready_paths = [barrier_root / f"ready-{index}.json" for index in range(len(specs))]
            release_paths = [barrier_root / f"release-{index}" for index in range(len(specs))]
            for index, spec in enumerate(specs):
                worker_id = str(spec["workerInstanceId"])
                command = [
                    sys.executable,
                    str(WORKER_ENTRY),
                    "--operation",
                    str(spec["operation"]),
                    "--database-url-env",
                    "CITEFRAME_R2_DATABASE_URL",
                    "--object-root-env",
                    "CITEFRAME_R2_OBJECT_ROOT",
                    "--schema",
                    harness.schema,
                    "--worker-instance-id",
                    worker_id,
                    "--ready-file",
                    str(ready_paths[index]),
                    "--release-file",
                    str(release_paths[index]),
                    "--wait-timeout-seconds",
                    str(timeout_seconds),
                ]
                for name, option in option_names.items():
                    if name in spec:
                        command.extend((option, str(spec[name])))
                environment = os.environ.copy()
                environment["CITEFRAME_R2_DATABASE_URL"] = database_url
                environment["CITEFRAME_R2_OBJECT_ROOT"] = str(object_root)
                commands[worker_id] = command
                workers.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=environment,
                    )
                )
            ready = read_ready_records(ready_paths, timeout_seconds)
            backend_observation = observe_ready_worker_backends(database_url, ready)
            for release in release_paths:
                release.write_text("release\n", encoding="utf-8")
            records = [
                parse_worker_output(worker, timeout_seconds=timeout_seconds)
                for worker in workers
            ]
            if len(records) > 1:
                assert len({record["osPid"] for record in records}) == len(records)
                assert len({record["pgBackendPid"] for record in records}) == len(records)
            for record in records:
                worker_id = str(record["workerInstanceId"])
                assert record["scenario"] == SCENARIO
                assert record["exitStatus"] == 0
                assert record["controllerObservedExitStatus"] == 0
                assert record["argv"] == commands[worker_id][2:]
                assert database_url not in json.dumps(record, sort_keys=True)
            return {
                "readyRecords": ready,
                "readyBarrierBackendObservation": backend_observation,
                "processRecords": records,
            }
    finally:
        terminate_workers(workers)


def object_manifest(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        records.append(
            {
                "key": path.relative_to(root).as_posix(),
                "size": len(payload),
                "sha256": sha_bytes(payload),
            }
        )
    return records


STEP_LIFECYCLES = {
    "planner": ("step_queued", "step_started", "step_succeeded"),
    "plan_gate": ("step_queued", "step_started", "step_waiting", "decision_submitted"),
    "researcher": ("step_queued", "step_started", "step_succeeded"),
    "verifier": ("step_queued", "step_started", "step_succeeded"),
    "critic": ("step_queued", "step_started", "step_succeeded"),
    "conflict_gate": (
        "step_queued",
        "step_started",
        "step_waiting",
        "decision_submitted",
    ),
    "synthesizer": ("step_queued", "step_started", "step_succeeded"),
    "publisher": ("step_queued",),
}


def _events_for_step(
    state: dict[str, Any], step_id: str, event_type: str
) -> list[dict[str, Any]]:
    return [
        event
        for event in state["events"]
        if event["event_type"] == event_type and event.get("step_id") == step_id
    ]


STEP_ROW_FIELDS = {
    "id",
    "workspace_id",
    "run_id",
    "plan_revision_id",
    "execution_snapshot_id",
    "step_key",
    "step_kind",
    "branch_key",
    "status",
    "state_version",
    "prompt_version_id",
    "max_attempts_snapshot",
    "current_attempt_number",
    "input_sha256",
    "queued_at",
    "started_at",
    "finished_at",
    "error_code",
    "error_message",
    "created_at",
    "updated_at",
}
ATTEMPT_ROW_FIELDS = {
    "id",
    "workspace_id",
    "step_id",
    "attempt_number",
    "status",
    "worker_instance_id",
    "lease_token_hash",
    "lease_expires_at",
    "heartbeat_at",
    "input_sha256",
    "output_sha256",
    "checkpoint_artifact_id",
    "provider_call_count",
    "tool_call_count",
    "input_tokens",
    "output_tokens",
    "cost_microunits",
    "error_code",
    "error_message",
    "started_at",
    "finished_at",
}
EVENT_ROW_FIELDS = {
    "id",
    "workspace_id",
    "run_id",
    "seq",
    "event_type",
    "event_schema_version",
    "step_id",
    "attempt_id",
    "dedupe_key",
    "payload_json",
    "created_at",
}
ARTIFACT_ROW_FIELDS = {
    "id",
    "workspace_id",
    "run_id",
    "generated_by_step_id",
    "generated_by_attempt_id",
    "artifact_kind",
    "visibility",
    "logical_key",
    "schema_version",
    "object_key",
    "content_type",
    "byte_size",
    "content_sha256",
    "supersedes_artifact_id",
    "workflow_version_id",
    "direct_prompt_version_id",
    "generation_provider",
    "generation_model",
    "retention_class",
    "expires_at",
    "created_at",
}


def _iso_add(value: str, *, microseconds: int) -> str:
    return (datetime.fromisoformat(value) + timedelta(microseconds=microseconds)).isoformat()


def _is_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def step_attempt_row_oracle(
    state: dict[str, Any], fixture: ConflictFixture
) -> dict[str, Any]:
    steps = {step["id"]: step for step in state["steps"]}
    artifacts_by_kind = {
        artifact["artifact_kind"]: artifact for artifact in state["artifacts"]
    }
    run_created_at = state["run"]["created_at"]
    role_offsets = {
        "planner": 0,
        "plan_gate": 1,
        "researcher": 2,
        "verifier": 3,
        "critic": 4,
        "conflict_gate": 5,
        "synthesizer": 6,
        "publisher": 7,
    }
    role_kinds = {
        "planner": "planner",
        "plan_gate": "plan_approval_gate",
        "researcher": "researcher",
        "verifier": "verifier",
        "critic": "critic",
        "conflict_gate": "conflict_decision_gate",
        "synthesizer": "synthesizer",
        "publisher": "artifact_publisher",
    }
    role_prompts = {
        "planner": fixture.prompt_ids["planner"],
        "plan_gate": None,
        "researcher": fixture.prompt_ids["researchers"],
        "verifier": fixture.prompt_ids["verifier"],
        "critic": fixture.prompt_ids["critic"],
        "conflict_gate": fixture.prompt_ids["critic"],
        "synthesizer": fixture.prompt_ids["synthesizer"],
        "publisher": fixture.prompt_ids["synthesizer"],
    }
    role_branches = {role: None for role in role_kinds}
    role_branches["researcher"] = "r2-i-branch"
    final_statuses = {role: "succeeded" for role in role_kinds}
    final_statuses["publisher"] = "queued"
    final_versions = {
        "planner": 3,
        "plan_gate": 4,
        "researcher": 3,
        "verifier": 4,
        "critic": 4,
        "conflict_gate": 5,
        "synthesizer": 4,
        "publisher": 2,
    }

    expected_steps: dict[str, dict[str, Any]] = {}
    for role, step_kind in role_kinds.items():
        step_id = fixture.step_ids[role]
        created_at = _iso_add(run_created_at, microseconds=role_offsets[role])
        queued_event = event_for(state, event_type="step_queued", step_id=step_id)
        started_events = _events_for_step(state, step_id, "step_started")
        terminal_type = (
            "decision_submitted"
            if role in {"plan_gate", "conflict_gate"}
            else "step_succeeded"
        )
        terminal_events = _events_for_step(state, step_id, terminal_type)
        queued_at = created_at if role in {"planner", "plan_gate", "researcher", "verifier"} else queued_event["created_at"]
        started_at = (
            created_at
            if role in {"planner", "plan_gate", "researcher"}
            else started_events[0]["created_at"]
            if started_events
            else None
        )
        finished_at = (
            created_at
            if role in {"planner", "plan_gate", "researcher"}
            else terminal_events[0]["created_at"]
            if terminal_events
            else None
        )
        updated_at = finished_at or queued_at
        expected_steps[step_id] = {
            "id": step_id,
            "workspace_id": fixture.workspace_id,
            "run_id": fixture.run_id,
            "plan_revision_id": fixture.plan_revision_id
            if role in {"planner", "plan_gate"}
            else None,
            "execution_snapshot_id": None
            if role in {"planner", "plan_gate"}
            else fixture.snapshot_id,
            "step_key": fixture.step_keys[role],
            "step_kind": step_kind,
            "branch_key": role_branches[role],
            "status": final_statuses[role],
            "state_version": final_versions[role],
            "prompt_version_id": role_prompts[role],
            "max_attempts_snapshot": 3,
            "current_attempt_number": 0 if role == "publisher" else 1,
            "input_sha256": sha_text(f"{fixture.run_id}:{fixture.step_keys[role]}:input"),
            "queued_at": queued_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_code": None,
            "error_message": None,
            "created_at": created_at,
            "updated_at": updated_at,
        }
    step_rows_exact = (
        set(steps) == set(expected_steps)
        and all(set(row) == STEP_ROW_FIELDS for row in steps.values())
        and steps == expected_steps
    )

    attempt_roles = [role for role in role_kinds if role != "publisher"]
    attempts_by_role = {
        role: attempts_for_step(state, fixture.step_ids[role]) for role in attempt_roles
    }
    attempt_identity_exact = all(len(rows) == 1 for rows in attempts_by_role.values())
    expected_attempts: dict[str, dict[str, Any]] = {}
    plan_artifact = artifacts_by_kind.get("research_plan")
    conflict_artifact = artifacts_by_kind.get("conflict_report")
    checkpoint = artifacts_by_kind.get("execution_checkpoint")
    output_hashes = {
        "planner": plan_artifact["content_sha256"] if plan_artifact else None,
        "plan_gate": plan_artifact["content_sha256"] if plan_artifact else None,
        "researcher": sha_text("r2-i-researcher-output"),
        "verifier": canonical_sha256(
            [
                {
                    "claimId": fixture.claim_id,
                    "status": "supported",
                    "reasonCode": None,
                }
            ]
        ),
        "critic": canonical_sha256({"conflictClaimIds": [fixture.claim_id]}),
        "conflict_gate": conflict_artifact["content_sha256"]
        if conflict_artifact
        else None,
        "synthesizer": canonical_sha256(
            {"factClaimIds": [], "unresolvedClaimIds": [fixture.claim_id]}
        ),
    }
    workers: dict[str, object] = {
        "planner": "r2-i-seed-planner",
        "plan_gate": "r2-i-seed-plan-gate",
        "researcher": "r2-i-seed-researcher",
        "verifier": "i-verifier",
        "critic": "i-critic",
        "conflict_gate": "i-conflict-gate",
        "synthesizer": {"i-synth-a", "i-synth-b"},
    }
    for role, rows in attempts_by_role.items():
        if len(rows) != 1:
            continue
        actual = rows[0]
        attempt_id = actual["id"]
        step = expected_steps[fixture.step_ids[role]]
        if role == "planner":
            started_at = finished_at = run_created_at
        elif role == "plan_gate":
            started_at = _iso_add(run_created_at, microseconds=8)
            finished_at = _iso_add(run_created_at, microseconds=9)
        elif role == "researcher":
            started_at = _iso_add(run_created_at, microseconds=16)
            finished_at = _iso_add(run_created_at, microseconds=17)
        else:
            started_at = step["started_at"]
            finished_at = (
                conflict_artifact["created_at"]
                if role == "conflict_gate" and conflict_artifact
                else step["finished_at"]
            )
        expected_worker = workers[role]
        worker_exact = (
            actual["worker_instance_id"] in expected_worker
            if isinstance(expected_worker, set)
            else actual["worker_instance_id"] == expected_worker
        )
        attempt_identity_exact = attempt_identity_exact and worker_exact and (
            attempt_id
            == {
                "planner": uid(fixture.schema, "plan-attempt"),
                "plan_gate": uid(fixture.schema, "plan-gate-attempt"),
                "researcher": uid(fixture.schema, "researcher-attempt"),
            }.get(role, attempt_id)
        ) and (role in {"planner", "plan_gate", "researcher"} or _is_uuid(attempt_id))
        expected_attempts[attempt_id] = {
            "id": attempt_id,
            "workspace_id": fixture.workspace_id,
            "step_id": fixture.step_ids[role],
            "attempt_number": 1,
            "status": "succeeded",
            "worker_instance_id": actual["worker_instance_id"] if worker_exact else None,
            "lease_token_hash": None
            if role in {"planner", "plan_gate", "researcher"}
            else "[redacted]",
            "lease_expires_at": None,
            "heartbeat_at": None
            if role in {"planner", "plan_gate", "researcher"}
            else started_at,
            "input_sha256": step["input_sha256"],
            "output_sha256": output_hashes[role],
            "checkpoint_artifact_id": checkpoint["id"]
            if role == "synthesizer" and checkpoint
            else None,
            "provider_call_count": 0,
            "tool_call_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_microunits": 0,
            "error_code": None,
            "error_message": None,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    actual_attempts = {attempt["id"]: attempt for attempt in state["attempts"]}
    attempt_rows_exact = (
        attempt_identity_exact
        and set(actual_attempts) == set(expected_attempts)
        and all(set(row) == ATTEMPT_ROW_FIELDS for row in actual_attempts.values())
        and actual_attempts == expected_attempts
    )
    return {
        "stepRowsExact": step_rows_exact,
        "attemptRowsExact": attempt_rows_exact,
        "expectedSteps": expected_steps,
        "expectedAttempts": expected_attempts,
    }


def event_row_oracle(
    state: dict[str, Any], fixture: ConflictFixture
) -> dict[str, Any]:
    events = state["events"]
    steps = {step["id"]: step for step in state["steps"]}
    attempts = {attempt["step_id"]: attempt for attempt in state["attempts"]}
    decisions = {item["decision_type"]: item for item in state["decisions"]}
    artifacts = {item["artifact_kind"]: item for item in state["artifacts"]}
    plan_decision = decisions.get("plan_approval")
    conflict_decision = decisions.get("conflict_resolution")
    plan_artifact = artifacts.get("research_plan")
    conflict_artifact = artifacts.get("conflict_report")
    checkpoint = artifacts.get("execution_checkpoint")
    if any(
        item is None
        for item in (plan_decision, conflict_decision, plan_artifact, conflict_artifact, checkpoint)
    ):
        return {"eventRowsExact": False, "eventIdsExact": False, "expectedRows": []}

    descriptors = [
        ("run_created", None),
        ("step_queued", "planner"),
        ("run_status_changed", None),
        ("step_started", "planner"),
        ("artifact_published", None),
        ("step_succeeded", "planner"),
        ("step_queued", "plan_gate"),
        ("step_started", "plan_gate"),
        ("step_waiting", "plan_gate"),
        ("approval_requested", None),
        ("run_status_changed", None),
        ("decision_submitted", "plan_gate"),
        ("run_status_changed", None),
        ("step_queued", "researcher"),
        ("run_status_changed", None),
        ("step_started", "researcher"),
        ("step_succeeded", "researcher"),
        ("step_queued", "verifier"),
        ("step_started", "verifier"),
        ("step_succeeded", "verifier"),
        ("step_queued", "critic"),
        ("step_started", "critic"),
        ("step_succeeded", "critic"),
        ("step_queued", "conflict_gate"),
        ("step_started", "conflict_gate"),
        ("artifact_published", None),
        ("step_waiting", "conflict_gate"),
        ("approval_requested", None),
        ("run_status_changed", None),
        ("decision_submitted", "conflict_gate"),
        ("run_status_changed", None),
        ("step_queued", "synthesizer"),
        ("run_status_changed", None),
        ("step_started", "synthesizer"),
        ("step_succeeded", "synthesizer"),
        ("step_queued", "publisher"),
    ]
    if len(events) != len(descriptors):
        return {"eventRowsExact": False, "eventIdsExact": False, "expectedRows": []}

    queued_versions = {
        "planner": 1,
        "plan_gate": 1,
        "researcher": 1,
        "verifier": 2,
        "critic": 2,
        "conflict_gate": 2,
        "synthesizer": 2,
        "publisher": 2,
    }
    run_statuses = {
        3: ("planning", "running", f"worker-run-started:{attempts[fixture.step_ids['planner']]['id']}"),
        11: ("running", "awaiting_plan_approval", f"plan-waiting:{plan_decision['id']}"),
        13: ("awaiting_plan_approval", "queued", f"plan-status:{plan_decision['id']}"),
        15: ("queued", "running", f"worker-run-started:{attempts[fixture.step_ids['researcher']]['id']}"),
        29: ("running", "awaiting_human_decision", f"conflict-waiting:{conflict_decision['id']}"),
        31: ("awaiting_human_decision", "queued", f"conflict-status:{conflict_decision['id']}"),
        33: ("queued", "running", f"worker-run-started:{attempts[fixture.step_ids['synthesizer']]['id']}"),
    }
    created_times = {
        19: steps[fixture.step_ids["verifier"]]["started_at"],
        20: steps[fixture.step_ids["verifier"]]["finished_at"],
        21: steps[fixture.step_ids["critic"]]["queued_at"],
        22: steps[fixture.step_ids["critic"]]["started_at"],
        23: steps[fixture.step_ids["critic"]]["finished_at"],
        24: steps[fixture.step_ids["conflict_gate"]]["queued_at"],
        25: steps[fixture.step_ids["conflict_gate"]]["started_at"],
        26: conflict_artifact["created_at"],
        27: attempts[fixture.step_ids["conflict_gate"]]["finished_at"],
        28: conflict_decision["requested_at"],
        29: conflict_decision["requested_at"],
        30: conflict_decision["decided_at"],
        31: conflict_decision["decided_at"],
        32: steps[fixture.step_ids["synthesizer"]]["queued_at"],
        33: steps[fixture.step_ids["synthesizer"]]["started_at"],
        34: steps[fixture.step_ids["synthesizer"]]["started_at"],
        35: steps[fixture.step_ids["synthesizer"]]["finished_at"],
        36: steps[fixture.step_ids["publisher"]]["queued_at"],
    }
    rows_exact = True
    ids_exact = True
    seen_ids: set[str] = set()
    expected_rows: list[dict[str, Any]] = []
    for seq, (event, descriptor) in enumerate(zip(events, descriptors, strict=True), 1):
        event_type, role = descriptor
        step = steps[fixture.step_ids[role]] if role else None
        attempt = attempts.get(step["id"]) if step else None
        expected_step_id = step["id"] if step else None
        expected_attempt_id = (
            attempt["id"]
            if event_type in {"step_started", "step_succeeded", "step_waiting"}
            else None
        )
        if event_type == "run_created":
            payload = {
                "status": "planning",
                "createdByUserId": fixture.actor_user_id,
                "runStateVersion": seq,
            }
            dedupe = f"run-created:{fixture.run_id}"
        elif event_type == "run_status_changed":
            previous, status, dedupe = run_statuses[seq]
            payload = {
                "previousStatus": previous,
                "status": status,
                "runStateVersion": seq,
                "reasonCode": None,
            }
        elif event_type == "step_queued":
            payload = {
                "stepId": step["id"],
                "stepKind": step["step_kind"],
                "branchKey": step["branch_key"],
                "attemptNumber": 0,
                "stepStateVersion": queued_versions[role],
                "runStateVersion": seq,
            }
            dedupe = f"step-queued:{step['id']}:0"
        elif event_type == "step_started":
            payload = {
                "stepId": step["id"],
                "stepKind": step["step_kind"],
                "branchKey": step["branch_key"],
                "attemptId": attempt["id"],
                "attemptNumber": 1,
                "stepStateVersion": queued_versions[role] + 1,
                "runStateVersion": seq,
            }
            dedupe = f"step-started:{attempt['id']}"
        elif event_type == "step_succeeded":
            artifact_ids = (
                [plan_artifact["id"]]
                if role == "planner"
                else [checkpoint["id"]]
                if role == "synthesizer"
                else []
            )
            payload = {
                "stepId": step["id"],
                "stepKind": step["step_kind"],
                "attemptId": attempt["id"],
                "attemptNumber": 1,
                "evidenceCount": 0,
                "artifactIds": artifact_ids,
                "stepStateVersion": queued_versions[role] + 2,
                "runStateVersion": seq,
            }
            dedupe = f"step-succeeded:{attempt['id']}"
        elif event_type == "step_waiting":
            decision = plan_decision if role == "plan_gate" else conflict_decision
            payload = {
                "stepId": step["id"],
                "stepKind": step["step_kind"],
                "decisionId": decision["id"],
                "decisionType": decision["decision_type"],
                "stepStateVersion": queued_versions[role] + 2,
                "decisionStateVersion": 1,
                "runStateVersion": seq,
            }
            dedupe = f"step-waiting:{step['id']}:{decision['id']}"
        elif event_type == "artifact_published":
            artifact = plan_artifact if seq == 5 else conflict_artifact
            payload = {
                "artifactId": artifact["id"],
                "artifactKind": artifact["artifact_kind"],
                "visibility": artifact["visibility"],
                "byteSize": artifact["byte_size"],
                "sha256": artifact["content_sha256"],
                "runStateVersion": seq,
            }
            dedupe = f"artifact-published:{artifact['id']}"
        elif event_type == "approval_requested":
            decision = plan_decision if seq == 10 else conflict_decision
            payload = {
                "decisionId": decision["id"],
                "decisionType": decision["decision_type"],
                "inputArtifactId": decision["input_artifact_id"],
                "inputArtifactSha256": decision["input_artifact_sha256"],
                "decisionStateVersion": 1,
                "runStateVersion": seq,
            }
            dedupe = f"approval-requested:{decision['id']}"
        else:
            decision = plan_decision if role == "plan_gate" else conflict_decision
            payload = {
                "decisionId": decision["id"],
                "decisionType": decision["decision_type"],
                "inputArtifactId": decision["input_artifact_id"],
                "inputArtifactSha256": decision["input_artifact_sha256"],
                "action": decision["action"],
                "actorUserId": fixture.actor_user_id,
                "decisionStateVersion": 2,
                "runStateVersion": seq,
            }
            dedupe = f"decision-submitted:{decision['id']}"
        expected_created_at = (
            _iso_add(state["run"]["created_at"], microseconds=seq)
            if seq <= 18
            else created_times[seq]
        )
        expected_without_id = {
            "workspace_id": fixture.workspace_id,
            "run_id": fixture.run_id,
            "seq": seq,
            "event_type": event_type,
            "event_schema_version": "1",
            "step_id": expected_step_id,
            "attempt_id": expected_attempt_id,
            "dedupe_key": dedupe,
            "payload_json": payload,
            "created_at": expected_created_at,
        }
        expected_event_id = (
            uid(fixture.schema, f"event:{seq}:{dedupe}")
            if seq <= 18
            else event.get("id")
        )
        expected_rows.append({"id": expected_event_id, **expected_without_id})
        rows_exact = rows_exact and set(event) == EVENT_ROW_FIELDS and all(
            event.get(key) == value for key, value in expected_without_id.items()
        )
        event_id = event.get("id")
        expected_seed_id = uid(fixture.schema, f"event:{seq}:{dedupe}")
        id_valid = (
            event_id == expected_seed_id if seq <= 18 else _is_uuid(event_id)
        )
        ids_exact = ids_exact and id_valid and event_id not in seen_ids
        if isinstance(event_id, str):
            seen_ids.add(event_id)
    return {
        "eventRowsExact": rows_exact,
        "eventIdsExact": ids_exact,
        "expectedRows": expected_rows,
    }


def causal_time_oracle(
    state: dict[str, Any], fixture: ConflictFixture
) -> dict[str, Any]:
    """Validate time from fixed seed rules and business causality, never circular rows."""

    checks: dict[str, bool] = {}
    try:
        run = state["run"]
        run_created_at = datetime.fromisoformat(run["created_at"])

        def moment(value: object) -> datetime:
            if not isinstance(value, str):
                raise TypeError("timestamp must be an ISO string")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError("timestamp must be timezone-aware")
            return parsed

        events_by_seq = {int(event["seq"]): event for event in state["events"]}
        ordered_event_times = [
            moment(events_by_seq[seq]["created_at"])
            for seq in range(1, len(state["events"]) + 1)
        ]
        checks["eventTimesMonotonicBySequence"] = all(
            earlier <= later
            for earlier, later in pairwise(ordered_event_times)
        )
        checks["baselineEventTimesFixtureExact"] = len(events_by_seq) >= 18 and all(
            moment(events_by_seq[seq]["created_at"])
            == run_created_at + timedelta(microseconds=seq)
            for seq in range(1, 19)
        )

        role_order = (
            "planner",
            "plan_gate",
            "researcher",
            "verifier",
            "critic",
            "conflict_gate",
            "synthesizer",
            "publisher",
        )
        steps = {
            role: next(
                step for step in state["steps"] if step["id"] == fixture.step_ids[role]
            )
            for role in role_order
        }
        attempts = {
            role: next(
                attempt
                for attempt in state["attempts"]
                if attempt["step_id"] == fixture.step_ids[role]
            )
            for role in role_order
            if role != "publisher"
        }
        decisions = {
            decision["decision_type"]: decision for decision in state["decisions"]
        }
        artifacts = {
            artifact["artifact_kind"]: artifact for artifact in state["artifacts"]
        }

        checks["runTimesExact"] = all(
            (
                moment(run["started_at"]) == run_created_at,
                run.get("finished_at") is None,
                moment(run["updated_at"])
                == moment(events_by_seq[len(state["events"])]["created_at"]),
            )
        )
        checks["stepCreatedTimesFixtureExact"] = all(
            moment(steps[role]["created_at"])
            == run_created_at + timedelta(microseconds=offset)
            for offset, role in enumerate(role_order)
        )

        step_self_consistent = True
        step_updated_exact = True
        for role, step in steps.items():
            created_at = moment(step["created_at"])
            queued_at = moment(step["queued_at"])
            started_at = step.get("started_at")
            finished_at = step.get("finished_at")
            if step["status"] == "queued":
                step_self_consistent = step_self_consistent and all(
                    (created_at <= queued_at, started_at is None, finished_at is None)
                )
                expected_updated_at = queued_at
            else:
                step_self_consistent = step_self_consistent and all(
                    (
                        started_at is not None,
                        finished_at is not None,
                        created_at <= queued_at,
                        queued_at <= moment(started_at),
                        moment(started_at) <= moment(finished_at),
                    )
                )
                expected_updated_at = moment(finished_at)
            step_updated_exact = step_updated_exact and (
                moment(step["updated_at"]) == expected_updated_at
            )
        checks["stepLifecycleTimesCausal"] = step_self_consistent
        checks["stepUpdatedAtLastTransitionExact"] = step_updated_exact

        checks["baselineStepTimesFixtureExact"] = all(
            moment(steps[role][field])
            == run_created_at + timedelta(microseconds=offset)
            for role, offset in (("planner", 0), ("plan_gate", 1), ("researcher", 2))
            for field in ("queued_at", "started_at", "finished_at", "updated_at")
        ) and moment(steps["verifier"]["queued_at"]) == run_created_at + timedelta(
            microseconds=3
        )

        baseline_attempt_offsets = {
            "planner": (0, 0),
            "plan_gate": (8, 9),
            "researcher": (16, 17),
        }
        checks["baselineAttemptTimesFixtureExact"] = all(
            all(
                (
                    moment(attempts[role]["started_at"])
                    == run_created_at + timedelta(microseconds=offsets[0]),
                    moment(attempts[role]["finished_at"])
                    == run_created_at + timedelta(microseconds=offsets[1]),
                    attempts[role].get("heartbeat_at") is None,
                    attempts[role].get("lease_expires_at") is None,
                )
            )
            for role, offsets in baseline_attempt_offsets.items()
        )
        dynamic_attempt_times_causal = True
        for role in ("verifier", "critic", "conflict_gate", "synthesizer"):
            attempt = attempts[role]
            step = steps[role]
            attempt_started = moment(attempt["started_at"])
            attempt_heartbeat = moment(attempt["heartbeat_at"])
            attempt_finished = moment(attempt["finished_at"])
            dynamic_attempt_times_causal = dynamic_attempt_times_causal and all(
                (
                    attempt_started <= attempt_heartbeat <= attempt_finished,
                    attempt_heartbeat == attempt_started,
                    attempt.get("lease_expires_at") is None,
                    moment(step["started_at"]) <= attempt_started,
                    attempt_finished <= moment(step["finished_at"]),
                )
            )
        checks["dynamicAttemptTimesCausal"] = dynamic_attempt_times_causal

        dependency_times_causal = True
        step_by_id = {step["id"]: step for step in state["steps"]}
        for dependency in state["dependencies"]:
            dependent = step_by_id[dependency["step_id"]]
            prerequisite = step_by_id[dependency["depends_on_step_id"]]
            dependency_times_causal = dependency_times_causal and (
                moment(prerequisite["finished_at"]) <= moment(dependent["queued_at"])
            )
        checks["dependencyTimesCausal"] = dependency_times_causal

        verifier = steps["verifier"]
        critic = steps["critic"]
        gate = steps["conflict_gate"]
        synthesizer = steps["synthesizer"]
        publisher = steps["publisher"]
        conflict_decision = decisions["conflict_resolution"]
        conflict_artifact = artifacts["conflict_report"]
        checkpoint = artifacts["execution_checkpoint"]
        verifier_started = moment(verifier["started_at"])
        verifier_finished = moment(verifier["finished_at"])
        critic_queued = moment(critic["queued_at"])
        critic_started = moment(critic["started_at"])
        critic_finished = moment(critic["finished_at"])
        gate_queued = moment(gate["queued_at"])
        gate_started = moment(gate["started_at"])
        conflict_reported = moment(conflict_artifact["created_at"])
        requested_at = moment(conflict_decision["requested_at"])
        decided_at = moment(conflict_decision["decided_at"])
        synth_queued = moment(synthesizer["queued_at"])
        synth_started = moment(synthesizer["started_at"])
        synth_finished = moment(synthesizer["finished_at"])
        checks["dynamicBusinessChainCausal"] = all(
            (
                verifier_started <= verifier_finished,
                verifier_finished == critic_queued,
                critic_queued <= critic_started <= critic_finished,
                critic_finished == gate_queued,
                gate_queued <= gate_started <= conflict_reported,
                conflict_reported == moment(attempts["conflict_gate"]["finished_at"]),
                conflict_reported == requested_at,
                gate_started <= requested_at <= decided_at,
                synth_queued == decided_at,
                synth_queued <= synth_started <= synth_finished,
                moment(checkpoint["created_at"]) == synth_finished,
                moment(publisher["queued_at"]) == synth_finished,
            )
        )

        checks["baselineArtifactDecisionTimesFixtureExact"] = all(
            (
                moment(artifacts["research_plan"]["created_at"]) == run_created_at,
                moment(decisions["plan_approval"]["requested_at"]) == run_created_at,
                moment(decisions["plan_approval"]["decided_at"]) == run_created_at,
            )
        )
        checks["dynamicEventEntityTimesExact"] = all(
            (
                moment(events_by_seq[19]["created_at"]) == verifier_started,
                moment(events_by_seq[20]["created_at"]) == verifier_finished,
                moment(events_by_seq[21]["created_at"]) == critic_queued,
                moment(events_by_seq[22]["created_at"]) == critic_started,
                moment(events_by_seq[23]["created_at"]) == critic_finished,
                moment(events_by_seq[24]["created_at"]) == gate_queued,
                moment(events_by_seq[25]["created_at"]) == gate_started,
                moment(events_by_seq[26]["created_at"]) == conflict_reported,
                moment(events_by_seq[27]["created_at"])
                == moment(attempts["conflict_gate"]["finished_at"]),
                moment(events_by_seq[28]["created_at"]) == requested_at,
                moment(events_by_seq[29]["created_at"]) == requested_at,
                moment(events_by_seq[30]["created_at"]) == decided_at,
                moment(events_by_seq[31]["created_at"]) == decided_at,
                moment(events_by_seq[32]["created_at"]) == synth_queued,
                moment(events_by_seq[33]["created_at"]) == synth_started,
                moment(events_by_seq[34]["created_at"])
                == moment(attempts["synthesizer"]["started_at"])
                == synth_started,
                moment(events_by_seq[35]["created_at"])
                == moment(attempts["synthesizer"]["finished_at"])
                == synth_finished,
                moment(events_by_seq[36]["created_at"])
                == moment(publisher["queued_at"]),
            )
        )
    except (KeyError, StopIteration, TypeError, ValueError, IndexError):
        checks["oracleInputComplete"] = False

    passed = bool(checks) and all(checks.values())
    return {**checks, "passed": passed}


def event_oracle(state: dict[str, Any], fixture: ConflictFixture) -> dict[str, Any]:
    events = state["events"]
    try:
        step_attempt_evidence = step_attempt_row_oracle(state, fixture)
        projection_row_evidence = {
            "stepRowsExact": step_attempt_evidence["stepRowsExact"],
            "attemptRowsExact": step_attempt_evidence["attemptRowsExact"],
        }
        event_row_evidence = event_row_oracle(state, fixture)
        causal_time_evidence = causal_time_oracle(state, fixture)
        projection_row_evidence.update(
            {
                "eventRowsExact": event_row_evidence["eventRowsExact"],
                "eventIdsExact": event_row_evidence["eventIdsExact"],
                "causalTimesExact": causal_time_evidence["passed"],
            }
        )
    except (AssertionError, KeyError, TypeError, ValueError, IndexError):
        projection_row_evidence = {
            "stepRowsExact": False,
            "attemptRowsExact": False,
            "eventRowsExact": False,
            "eventIdsExact": False,
            "causalTimesExact": False,
        }
        causal_time_evidence = {"passed": False, "oracleInputComplete": False}
    sequences = [int(event["seq"]) for event in events]
    dedupe_keys = [event["dedupe_key"] for event in events]
    step_by_id = {step["id"]: step for step in state["steps"]}
    expected_step_ids = set(fixture.step_ids.values())
    actual_step_ids = [step["id"] for step in state["steps"]]
    step_set_exact = (
        len(actual_step_ids) == len(expected_step_ids)
        and set(actual_step_ids) == expected_step_ids
    )
    attempt_step_ids = {attempt.get("step_id") for attempt in state["attempts"]}
    event_step_ids = {
        event.get("step_id") for event in events if event.get("step_id") is not None
    }
    related_step_ids_exact = (
        attempt_step_ids <= expected_step_ids and event_step_ids <= expected_step_ids
    )
    attempts_by_step = {
        step_id: attempts_for_step(state, step_id) for step_id in fixture.step_ids.values()
    }

    exact_lifecycle = True
    lifecycle_order = True
    attempt_links = True
    payload_links = True
    lifecycle_sequences: dict[str, dict[str, int]] = {}
    consumed_lifecycle_sequences: set[int] = set()
    consumed_attempt_ids: set[str] = set()
    expected_attempt_roles = set(STEP_LIFECYCLES) - {"publisher"}
    for role, lifecycle in STEP_LIFECYCLES.items():
        step_id = fixture.step_ids[role]
        step = step_by_id.get(step_id)
        role_sequences: dict[str, int] = {}
        if step is None:
            exact_lifecycle = False
            lifecycle_order = False
            attempt_links = False
            payload_links = False
            continue
        for event_type in lifecycle:
            matches = _events_for_step(state, step_id, event_type)
            if len(matches) != 1:
                exact_lifecycle = False
                continue
            event = matches[0]
            event_sequence = int(event["seq"])
            role_sequences[event_type] = event_sequence
            consumed_lifecycle_sequences.add(event_sequence)
            payload = event.get("payload_json") or {}
            if event_type in {
                "step_queued",
                "step_started",
                "step_waiting",
                "step_succeeded",
            } and (
                payload.get("stepId") != step_id
                or payload.get("stepKind") != step["step_kind"]
            ):
                payload_links = False
        if len(role_sequences) == len(lifecycle):
            lifecycle_order = lifecycle_order and list(role_sequences.values()) == sorted(
                role_sequences.values()
            )
        else:
            lifecycle_order = False
        lifecycle_sequences[role] = role_sequences

        attempts = attempts_by_step[step_id]
        if role in expected_attempt_roles:
            if (
                len(attempts) != 1
                or attempts[0]["status"] != "succeeded"
                or int(attempts[0]["attempt_number"]) != 1
                or int(step["current_attempt_number"]) != 1
            ):
                attempt_links = False
                continue
            attempt = attempts[0]
            consumed_attempt_ids.add(attempt["id"])
            for event_type in ("step_started", "step_succeeded", "step_waiting"):
                if event_type not in lifecycle:
                    continue
                matches = _events_for_step(state, step_id, event_type)
                if len(matches) != 1:
                    attempt_links = False
                    continue
                event = matches[0]
                payload = event.get("payload_json") or {}
                if event.get("attempt_id") != attempt["id"]:
                    attempt_links = False
                if event_type in {"step_started", "step_succeeded"} and (
                    payload.get("attemptId") != attempt["id"]
                    or int(payload.get("attemptNumber", -1)) != 1
                ):
                    attempt_links = False
        elif attempts:
            attempt_links = False

        for event_type in ("step_queued", "decision_submitted"):
            if event_type not in lifecycle:
                continue
            matches = _events_for_step(state, step_id, event_type)
            if len(matches) == 1 and matches[0].get("attempt_id") is not None:
                attempt_links = False

        unexpected = {
            "step_queued",
            "step_started",
            "step_waiting",
            "step_succeeded",
            "step_failed",
            "attempt_abandoned",
            "decision_submitted",
        } - set(lifecycle)
        if any(_events_for_step(state, step_id, event_type) for event_type in unexpected):
            exact_lifecycle = False

    actual_attempt_ids = [attempt["id"] for attempt in state["attempts"]]
    attempts_consumed_exact = (
        len(actual_attempt_ids) == len(expected_attempt_roles)
        and len(actual_attempt_ids) == len(set(actual_attempt_ids))
        and set(actual_attempt_ids) == consumed_attempt_ids
    )
    lifecycle_event_types = {
        event_type for lifecycle in STEP_LIFECYCLES.values() for event_type in lifecycle
    }
    actual_lifecycle_sequences = {
        int(event["seq"])
        for event in events
        if event["event_type"] in lifecycle_event_types
    }
    lifecycle_events_consumed_exact = (
        actual_lifecycle_sequences == consumed_lifecycle_sequences
    )

    expected_dependencies = {
        (fixture.step_ids["plan_gate"], fixture.step_ids["planner"]),
        (fixture.step_ids["verifier"], fixture.step_ids["researcher"]),
        (fixture.step_ids["critic"], fixture.step_ids["verifier"]),
        (fixture.step_ids["conflict_gate"], fixture.step_ids["critic"]),
        (fixture.step_ids["synthesizer"], fixture.step_ids["conflict_gate"]),
        (fixture.step_ids["publisher"], fixture.step_ids["synthesizer"]),
    }
    actual_dependencies = {
        (item["step_id"], item["depends_on_step_id"])
        for item in state["dependencies"]
    }
    dependency_order = (
        len(state["dependencies"]) == len(expected_dependencies)
        and all(
            set(item) == {"step_id", "depends_on_step_id"}
            for item in state["dependencies"]
        )
        and actual_dependencies == expected_dependencies
    )
    completion_sequences: dict[str, int] = {}
    queue_sequences: dict[str, int] = {}
    for role, lifecycle in STEP_LIFECYCLES.items():
        role_events = lifecycle_sequences.get(role, {})
        step_id = fixture.step_ids[role]
        if "step_queued" in role_events:
            queue_sequences[step_id] = role_events["step_queued"]
        terminal_type = (
            "decision_submitted"
            if role in {"plan_gate", "conflict_gate"}
            else "step_succeeded"
        )
        if terminal_type in lifecycle and terminal_type in role_events:
            completion_sequences[step_id] = role_events[terminal_type]
    for dependent_id, dependency_id in expected_dependencies:
        if (
            dependent_id not in queue_sequences
            or dependency_id not in completion_sequences
            or completion_sequences[dependency_id] >= queue_sequences[dependent_id]
            or step_by_id.get(dependency_id, {}).get("status") != "succeeded"
        ):
            dependency_order = False

    decisions = [
        decision
        for decision in state["decisions"]
        if decision["decision_type"] in {"plan_approval", "conflict_resolution"}
    ]
    decision_events_exact = len(decisions) == len(state["decisions"]) == 2
    for decision in decisions:
        approvals = [
            event
            for event in events
            if event["event_type"] == "approval_requested"
            and (event.get("payload_json") or {}).get("decisionId") == decision["id"]
        ]
        submitted = [
            event
            for event in events
            if event["event_type"] == "decision_submitted"
            and (event.get("payload_json") or {}).get("decisionId") == decision["id"]
        ]
        if len(approvals) != 1 or len(submitted) != 1:
            decision_events_exact = False

    artifacts_requiring_publication_event = [
        artifact
        for artifact in state["artifacts"]
        if artifact["artifact_kind"] in {"research_plan", "conflict_report"}
    ]
    artifact_events_exact = len(artifacts_requiring_publication_event) == 2
    for artifact in artifacts_requiring_publication_event:
        matches = [
            event
            for event in events
            if event["event_type"] == "artifact_published"
            and (event.get("payload_json") or {}).get("artifactId") == artifact["id"]
        ]
        if len(matches) != 1:
            artifact_events_exact = False

    status_path = [
        (event.get("payload_json") or {}).get("status")
        for event in events
        if event["event_type"] in {"run_created", "run_status_changed"}
    ]
    expected_status_path = [
        "planning",
        "running",
        "awaiting_plan_approval",
        "queued",
        "running",
        "awaiting_human_decision",
        "queued",
        "running",
    ]
    run_status_path_exact = status_path == expected_status_path
    run_versions = [
        int((event.get("payload_json") or {}).get("runStateVersion", -1))
        for event in events
    ]
    run_versions_match = (
        run_versions == list(range(1, len(events) + 1))
        and int(state["run"]["state_version"]) == len(events)
        and int(state["run"]["next_event_seq"]) == len(events) + 1
    )
    expected_final_status = {
        **{role: "succeeded" for role in STEP_LIFECYCLES if role != "publisher"},
        "publisher": "queued",
    }
    final_step_statuses = all(
        step_by_id.get(fixture.step_ids[role], {}).get("status") == expected_status
        for role, expected_status in expected_final_status.items()
    )

    expected_event_type_counts = Counter(
        {
            "run_created": 1,
            "run_status_changed": 7,
            "step_queued": 8,
            "step_started": 7,
            "step_waiting": 2,
            "step_succeeded": 5,
            "approval_requested": 2,
            "decision_submitted": 2,
            "artifact_published": 2,
        }
    )
    actual_event_type_counts = Counter(event["event_type"] for event in events)
    event_type_counts_exact = actual_event_type_counts == expected_event_type_counts
    non_step_event_types = {
        "run_created",
        "run_status_changed",
        "approval_requested",
        "artifact_published",
    }
    non_step_event_links_exact = all(
        event.get("step_id") is None and event.get("attempt_id") is None
        for event in events
        if event["event_type"] in non_step_event_types
    )
    actual_attempt_id_set = set(actual_attempt_ids)
    event_attempt_ids = {
        event.get("attempt_id")
        for event in events
        if event.get("attempt_id") is not None
    }
    related_attempt_ids_exact = event_attempt_ids <= actual_attempt_id_set
    all_events_accounted_exact = all(
        (
            event_type_counts_exact,
            lifecycle_events_consumed_exact,
            non_step_event_links_exact,
            related_step_ids_exact,
            related_attempt_ids_exact,
        )
    )

    sequences_contiguous = sequences == list(range(1, len(sequences) + 1))
    dedupe_unique = len(dedupe_keys) == len(set(dedupe_keys))
    strict_order = all(
        (
            sequences_contiguous,
            dedupe_unique,
            exact_lifecycle,
            lifecycle_order,
            step_set_exact,
            attempts_consumed_exact,
            all_events_accounted_exact,
            projection_row_evidence["stepRowsExact"],
            projection_row_evidence["attemptRowsExact"],
            projection_row_evidence["eventRowsExact"],
            projection_row_evidence["eventIdsExact"],
            projection_row_evidence["causalTimesExact"],
            attempt_links,
            payload_links,
            dependency_order,
            decision_events_exact,
            artifact_events_exact,
            run_status_path_exact,
            run_versions_match,
            final_step_statuses,
        )
    )
    return {
        "eventSequences": sequences,
        "sequencesContiguousFromOne": sequences_contiguous,
        "dedupeKeysUnique": dedupe_unique,
        "requiredLifecycleEventsExactlyOnce": exact_lifecycle,
        "allStepLifecyclesStrict": lifecycle_order,
        "stepSetExact": step_set_exact,
        "relatedStepIdsExact": related_step_ids_exact,
        "attemptsConsumedExact": attempts_consumed_exact,
        "lifecycleEventsConsumedExact": lifecycle_events_consumed_exact,
        "eventTypeCountsExact": event_type_counts_exact,
        "nonStepEventLinksExact": non_step_event_links_exact,
        "relatedAttemptIdsExact": related_attempt_ids_exact,
        "allEventsAccountedExact": all_events_accounted_exact,
        **projection_row_evidence,
        "causalTimeOracle": causal_time_evidence,
        "terminalAttemptLinksExact": attempt_links,
        "eventPayloadStepLinksExact": payload_links,
        "dependenciesCommittedBeforeQueued": dependency_order,
        "decisionEventsExactlyOnce": decision_events_exact,
        "artifactPublicationEventsExactlyOnce": artifact_events_exact,
        "runStatusPathExact": run_status_path_exact,
        "runStateVersionsMatchEvents": run_versions_match,
        "finalStepStatusesExact": final_step_statuses,
        "strictPartialOrder": strict_order,
        "lifecycleSequences": lifecycle_sequences,
        "runStatusPath": status_path,
        "actualStepIds": sorted(actual_step_ids),
        "expectedStepIds": sorted(expected_step_ids),
        "eventTypeCounts": dict(sorted(actual_event_type_counts.items())),
    }


def expected_decision_dto(decision: dict[str, Any]) -> dict[str, object]:
    """Independent DTO construction; never reuse a persisted response payload."""
    return {
        "id": decision["id"],
        "runId": decision["run_id"],
        "gateStepId": decision["gate_step_id"],
        "type": decision["decision_type"],
        "status": decision["status"],
        "requestNumber": decision["request_number"],
        "stateVersion": decision["state_version"],
        "inputArtifactId": decision["input_artifact_id"],
        "inputArtifactSha256": decision["input_artifact_sha256"],
        "inputSnapshotSha256": decision["input_snapshot_sha256"],
        "requestedAt": decision["requested_at"],
        "expiresAt": decision["expires_at"],
        "decidedByUserId": decision["decided_by_user_id"],
        "action": decision["action"],
        "comment": decision["comment_text"],
        "decidedAt": decision["decided_at"],
    }


def expected_usage(
    state: dict[str, Any],
    ledgers: list[dict[str, Any]],
    measured_at: str,
) -> dict[str, object]:
    ledger_ids = {ledger["id"] for ledger in ledgers}
    sources = {
        call["usage_source"]
        for call in state.get("providerCalls", [])
        if call.get("budget_ledger_id") in ledger_ids
        and call.get("usage_source") in {"actual", "estimated"}
    }
    usage_source = (
        "actual"
        if sources == {"actual"}
        else "estimated"
        if sources == {"estimated"}
        else "mixed"
        if sources == {"actual", "estimated"}
        else None
    )
    return {
        "providerCalls": sum(int(row["actual_provider_calls"]) for row in ledgers),
        "toolCalls": sum(int(row["actual_tool_calls"]) for row in ledgers),
        "inputTokens": sum(int(row["actual_input_tokens"]) for row in ledgers),
        "outputTokens": sum(int(row["actual_output_tokens"]) for row in ledgers),
        "usageFinal": all(bool(row["usage_final"]) for row in ledgers)
        if ledgers
        else True,
        "measuredAt": max(
            (str(row["updated_at"]) for row in ledgers), default=measured_at
        ),
        "usageSource": usage_source,
    }


def expected_step_dto(state: dict[str, Any], step: dict[str, Any]) -> dict[str, object]:
    dependencies = sorted(
        item["depends_on_step_id"]
        for item in state["dependencies"]
        if item["step_id"] == step["id"]
    )
    attempts = [
        attempt for attempt in state["attempts"] if attempt["step_id"] == step["id"]
    ]
    failure = None
    if step["error_code"]:
        failure = {
            "code": step["error_code"],
            "message": step["error_message"] or "Research step failed.",
            "retryable": step["status"] == "failed"
            and int(step["current_attempt_number"]) < int(step["max_attempts_snapshot"]),
            "failedAt": step["finished_at"] or step["updated_at"],
        }
    return {
        "id": step["id"],
        "runId": step["run_id"],
        "kind": step["step_kind"],
        "key": step["step_key"],
        "branchKey": step["branch_key"],
        "status": step["status"],
        "stateVersion": step["state_version"],
        "currentAttemptNumber": step["current_attempt_number"],
        "maxAttempts": step["max_attempts_snapshot"],
        "dependsOnStepIds": dependencies,
        "evidenceCount": 0,
        "providerCalls": sum(int(item["provider_call_count"]) for item in attempts),
        "toolCalls": sum(int(item["tool_call_count"]) for item in attempts),
        "startedAt": step["started_at"],
        "finishedAt": step["finished_at"],
        "failure": failure,
    }


def expected_execution_snapshot_dto(
    state: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, object]:
    prompts = sorted(
        (
            {
                "nodeKey": row["node_key"],
                "promptVersionId": row["prompt_version_id"],
            }
            for row in state["executionPromptVersions"]
            if row["execution_snapshot_id"] == snapshot["id"]
        ),
        key=lambda row: str(row["nodeKey"]),
    )
    return {
        "id": snapshot["id"],
        "inputVersion": snapshot["input_version"],
        "approvalDecisionId": snapshot["approval_decision_id"],
        "approvedPlanArtifactId": snapshot["approved_plan_artifact_id"],
        "approvedPlanArtifactSha256": snapshot["approved_plan_artifact_sha256"],
        "question": snapshot["question_text"],
        "frozenAssetScope": {"frozenAt": snapshot["created_at"], "assets": []},
        "execution": {
            "workflowVersionId": snapshot["workflow_version_id"],
            "promptVersions": prompts,
            "provider": {
                "generationProvider": snapshot["generation_provider"],
                "generationModel": snapshot["generation_model"],
                "embeddingProvider": snapshot["embedding_provider"],
                "embeddingModel": snapshot["embedding_model"],
                "embeddingVersion": snapshot["embedding_version"],
                "retrievalStrategy": snapshot["retrieval_strategy"],
                "retrievalTopK": snapshot["retrieval_top_k"],
                "providerConfigFingerprint": snapshot["provider_config_fingerprint"],
                "pricingVersion": snapshot["pricing_version"],
                "dataBoundaryPolicyVersion": snapshot["data_boundary_policy_version"],
            },
            "budgetPolicyVersion": snapshot["budget_policy_version"],
            "retryPolicyVersion": snapshot["retry_policy_version"],
            "limits": {
                "maxProviderCalls": snapshot["max_provider_calls"],
                "maxToolCalls": snapshot["max_tool_calls"],
                "maxInputTokens": snapshot["max_input_tokens"],
                "maxOutputTokens": snapshot["max_output_tokens"],
                "maxParallelResearchers": snapshot["max_parallel_researchers"],
                "runTimeoutSeconds": snapshot["max_run_timeout_seconds"],
                "stepTimeoutSeconds": snapshot["max_step_timeout_seconds"],
                "providerTimeoutSeconds": snapshot["max_provider_timeout_seconds"],
                "maxAttemptsPerStep": snapshot["max_step_attempts"],
            },
            "agentResultSchemaVersion": snapshot["agent_result_schema_version"],
            "contextPolicyVersion": snapshot["context_policy_version"],
            "compactPolicyVersion": snapshot["compact_policy_version"],
        },
        "snapshotSha256": snapshot["execution_snapshot_sha256"],
        "createdAt": snapshot["created_at"],
    }


def expected_conflict_decision_response(
    state: dict[str, Any], decision_id: str
) -> dict[str, object]:
    """Construct the complete expected response solely from projected database rows."""
    run = state["run"]
    assert run["current_plan_revision_id"] is None
    decision = next(item for item in state["decisions"] if item["id"] == decision_id)
    snapshot = next(
        item
        for item in state["executionSnapshots"]
        if item["id"] == run["approved_execution_snapshot_id"]
    )
    decisions = sorted(
        state["decisions"], key=lambda row: (row["requested_at"], row["id"])
    )
    steps = sorted(state["steps"], key=lambda row: (row["created_at"], row["id"]))
    planning_ledgers = [
        row for row in state["budgetLedgers"] if row["plan_revision_id"] is not None
    ]
    research_ledgers = [
        row
        for row in state["budgetLedgers"]
        if row["execution_snapshot_id"] == run["approved_execution_snapshot_id"]
    ]
    run_response: dict[str, object] = {
        "id": run["id"],
        "workspaceId": run["workspace_id"],
        "createdByUserId": run["created_by_user_id"],
        "question": "",
        "status": run["status"],
        "stateVersion": run["state_version"],
        "requestedAssetScope": {"mode": "all_ready"},
        "frozenAssetCount": 0,
        "currentPlanRevisionNumber": None,
        "currentEventSeq": int(run["next_event_seq"]) - 1,
        "createdAt": run["created_at"],
        "updatedAt": run["updated_at"],
        "finishedAt": run["finished_at"],
        "frozenAssetScope": None,
        "plan": None,
        "researchExecution": expected_execution_snapshot_dto(state, snapshot),
        "planningUsage": expected_usage(state, planning_ledgers, run["updated_at"]),
        "researchUsage": expected_usage(state, research_ledgers, run["updated_at"]),
        "steps": [expected_step_dto(state, step) for step in steps],
        "pendingDecisions": [
            expected_decision_dto(item) for item in decisions if item["status"] == "pending"
        ],
        "submittedDecisions": [
            expected_decision_dto(item) for item in decisions if item["status"] != "pending"
        ],
        "artifactCount": sum(
            artifact["visibility"] == "user" for artifact in state["artifacts"]
        ),
        "failure": None,
        "startedAt": run["started_at"],
        "cancelRequestedAt": run["cancel_requested_at"],
        "cancelledAt": None,
    }
    return {"decision": expected_decision_dto(decision), "run": run_response}


def decision_idempotency_oracle(
    state: dict[str, Any],
    *,
    workspace_id: str,
    actor_user_id: str,
    run_id: str,
    decision_id: str,
    expected_request_body: dict[str, object],
    expected_winner_response: dict[str, object],
    decision_keys_by_worker: dict[str, str],
    winner: dict[str, Any],
    loser: dict[str, Any],
    winner_replay: dict[str, Any],
    loser_replay: dict[str, Any],
) -> dict[str, Any]:
    """Prove exact idempotency identity plus complete frozen responses."""
    expected_path = (
        f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/"
        f"conflict-decisions/{decision_id}"
    )
    expected_request_sha256 = canonical_sha256(expected_request_body)
    expected_winner_response_sha256 = canonical_sha256(expected_winner_response)
    expected_worker_ids = set(DECISION_KEYS_BY_WORKER)
    process_worker_ids = {
        winner.get("workerInstanceId"),
        loser.get("workerInstanceId"),
    }
    fixture_keys_exact = (
        decision_keys_by_worker == DECISION_KEYS_BY_WORKER
        and process_worker_ids == expected_worker_ids
    )
    expected_winner_key = decision_keys_by_worker.get(winner.get("workerInstanceId"))
    expected_loser_key = decision_keys_by_worker.get(loser.get("workerInstanceId"))
    expected_keys = set(decision_keys_by_worker.values())
    scope_records = state["idempotencyRecords"]
    idempotency_by_key = {
        record["idempotency_key"]: record for record in scope_records
    }
    row_keys_exact = (
        fixture_keys_exact
        and None not in {expected_winner_key, expected_loser_key}
        and len(expected_keys) == 2
        and len(scope_records) == 2
        and len(idempotency_by_key) == 2
        and set(idempotency_by_key) == expected_keys
    )
    winner_record = idempotency_by_key.get(expected_winner_key)
    loser_record = idempotency_by_key.get(expected_loser_key)

    idempotency_row_fields = {
        "id",
        "workspace_id",
        "actor_user_id",
        "operation",
        "canonical_resource_path",
        "idempotency_key",
        "request_sha256",
        "status",
        "http_status",
        "result_resource_id",
        "response_schema_version",
        "response_json",
        "created_at",
        "completed_at",
        "expires_at",
    }
    row_shapes_exact = all(
        set(record) == idempotency_row_fields
        and isinstance(record.get("id"), str)
        and isinstance(record.get("created_at"), str)
        and isinstance(record.get("completed_at"), str)
        and isinstance(record.get("expires_at"), str)
        and record["created_at"] <= record["completed_at"] < record["expires_at"]
        for record in scope_records
    )
    identity_fields_exact = row_keys_exact and row_shapes_exact
    if winner_record is not None and loser_record is not None:
        for process_record, persisted_record, expected_key in (
            (winner, winner_record, expected_winner_key),
            (loser, loser_record, expected_loser_key),
        ):
            identity_fields_exact = identity_fields_exact and all(
                (
                    persisted_record.get("workspace_id") == workspace_id,
                    persisted_record.get("actor_user_id") == actor_user_id,
                    persisted_record.get("operation") == "submit_conflict_decision",
                    persisted_record.get("canonical_resource_path") == expected_path,
                    persisted_record.get("idempotency_key") == expected_key,
                    process_record.get("idempotencyKey") == expected_key,
                    persisted_record.get("request_sha256") == expected_request_sha256,
                )
            )
    else:
        identity_fields_exact = False

    def response_matches(
        process_record: dict[str, Any], expected_response: dict[str, object]
    ) -> bool:
        return (
            process_record.get("responseJson") == expected_response
            and process_record.get("responseSha256")
            == canonical_sha256(expected_response)
        )

    winner_response_exact = False
    if winner_record is not None:
        winner_response = winner_record.get("response_json")
        winner_response_exact = all(
            (
                winner.get("outcome") == "decided",
                winner.get("httpStatus") == 200,
                winner_record.get("status") == "completed",
                winner_record.get("http_status") == 200,
                winner_record.get("result_resource_id") == decision_id,
                winner_record.get("response_schema_version") == "1",
                winner_response == expected_winner_response,
                response_matches(winner, expected_winner_response),
                winner_replay.get("outcome") == "replayed",
                winner_replay.get("httpStatus") == 200,
                winner_replay.get("idempotencyKey") == expected_winner_key,
                response_matches(winner_replay, expected_winner_response),
            )
        )

    loser_response_exact = False
    loser_error_fields_exact = False
    if loser_record is not None:
        loser_response = loser_record.get("response_json")
        persisted_error = (
            loser_response.get("error") if isinstance(loser_response, dict) else None
        )
        request_id_valid = False
        expected_loser_response: dict[str, object] | None = None
        if isinstance(persisted_error, dict):
            request_id = persisted_error.get("requestId")
            try:
                request_id_valid = isinstance(request_id, str) and str(
                    UUID(request_id)
                ) == request_id
            except (ValueError, TypeError, AttributeError):
                request_id_valid = False
            if request_id_valid:
                expected_loser_response = {
                    "error": {
                        "code": "research_state_conflict",
                        "message": "Research decision has already been submitted.",
                        "requestId": request_id,
                        "retryable": False,
                    }
                }
        loser_response_exact = all(
            (
                loser.get("outcome") == "fenced",
                loser.get("httpStatus") == 409,
                loser_record.get("status") == "failed",
                loser_record.get("http_status") == 409,
                loser_record.get("result_resource_id") is None,
                loser_record.get("response_schema_version") == "1",
                isinstance(persisted_error, dict),
                loser_response == expected_loser_response,
                expected_loser_response is not None
                and response_matches(loser, expected_loser_response),
                loser_replay.get("outcome") == "fenced",
                loser_replay.get("httpStatus") == 409,
                loser_replay.get("idempotencyKey") == expected_loser_key,
                expected_loser_response is not None
                and response_matches(loser_replay, expected_loser_response),
            )
        )
        if isinstance(persisted_error, dict):
            loser_error_fields_exact = all(
                (
                    set(persisted_error)
                    == {"code", "message", "requestId", "retryable"},
                    persisted_error.get("code") == "research_state_conflict",
                    persisted_error.get("message")
                    == "Research decision has already been submitted.",
                    persisted_error.get("retryable") is False,
                    request_id_valid,
                    loser.get("errorCode") == persisted_error.get("code"),
                    loser.get("errorMessage") == persisted_error.get("message"),
                    loser.get("errorRetryable") == persisted_error.get("retryable"),
                    loser.get("errorRequestId") == persisted_error.get("requestId"),
                    loser.get("errorDetails") == persisted_error.get("details"),
                    loser_replay.get("errorCode") == persisted_error.get("code"),
                    loser_replay.get("errorMessage") == persisted_error.get("message"),
                    loser_replay.get("errorRetryable")
                    == persisted_error.get("retryable"),
                    loser_replay.get("errorRequestId")
                    == persisted_error.get("requestId"),
                    loser_replay.get("errorDetails") == persisted_error.get("details"),
                )
            )

    passed = all(
        (
            row_keys_exact,
            row_shapes_exact,
            identity_fields_exact,
            winner_response_exact,
            loser_response_exact,
            loser_error_fields_exact,
        )
    )
    return {
        "rowKeysExact": row_keys_exact,
        "fixtureDecisionKeysExact": fixture_keys_exact,
        "firstDecisionWorkerIdsExact": process_worker_ids == expected_worker_ids,
        "rowShapesExact": row_shapes_exact,
        "workspaceActorOperationPathKeyRequestHashExact": identity_fields_exact,
        "winnerCompleteResponseExact": winner_response_exact,
        "loserFrozenResponseExact": loser_response_exact,
        "loserFrozenErrorFieldsExact": loser_error_fields_exact,
        "expectedCanonicalResourcePath": expected_path,
        "expectedRequestSha256": expected_request_sha256,
        "expectedWinnerResponseSha256": expected_winner_response_sha256,
        "passed": passed,
    }


def artifact_oracle(
    before: dict[str, Any],
    after: dict[str, Any],
    manifest: list[dict[str, object]],
    fixture: ConflictFixture,
) -> dict[str, Any]:
    before_artifact_ids = {artifact["id"] for artifact in before["artifacts"]}
    after_by_id = {artifact["id"]: artifact for artifact in after["artifacts"]}
    after_baseline_artifacts = [
        artifact
        for artifact in after["artifacts"]
        if artifact["id"] in before_artifact_ids
    ]
    baseline_artifacts_immutable = after_baseline_artifacts == before["artifacts"]
    new_artifacts = [
        artifact for artifact in after["artifacts"] if artifact["id"] not in before_artifact_ids
    ]
    new_by_kind = {artifact["artifact_kind"]: artifact for artifact in new_artifacts}
    expected_kinds = {"conflict_report", "execution_checkpoint"}
    artifact_delta_exact = (
        baseline_artifacts_immutable
        and before_artifact_ids <= set(after_by_id)
        and len(new_artifacts) == 2
        and set(new_by_kind) == expected_kinds
    )

    gate_attempts = attempts_for_step(after, fixture.step_ids["conflict_gate"])
    synth_attempts = attempts_for_step(after, fixture.step_ids["synthesizer"])
    provenance_exact = artifact_delta_exact and len(gate_attempts) == len(synth_attempts) == 1
    artifact_times_causal = provenance_exact
    conflict = new_by_kind.get("conflict_report")
    checkpoint = new_by_kind.get("execution_checkpoint")
    if provenance_exact and conflict is not None and checkpoint is not None:
        try:
            artifact_times_causal = all(
                (
                    datetime.fromisoformat(gate_attempts[0]["started_at"])
                    <= datetime.fromisoformat(conflict["created_at"])
                    == datetime.fromisoformat(gate_attempts[0]["finished_at"]),
                    datetime.fromisoformat(synth_attempts[0]["started_at"])
                    <= datetime.fromisoformat(checkpoint["created_at"])
                    == datetime.fromisoformat(synth_attempts[0]["finished_at"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            artifact_times_causal = False
        expected_rows = (
            (
                conflict,
                fixture.step_ids["conflict_gate"],
                gate_attempts[0]["id"],
                "user",
                "conflict-report:1",
                fixture.prompt_ids["critic"],
                "conflicts.json",
                "conflict_report",
                conflict["content_sha256"],
                conflict["byte_size"],
            ),
            (
                checkpoint,
                fixture.step_ids["synthesizer"],
                synth_attempts[0]["id"],
                "internal",
                "checkpoint:synthesis",
                fixture.prompt_ids["synthesizer"],
                "checkpoint.json",
                "execution_checkpoint",
                checkpoint["content_sha256"],
                checkpoint["byte_size"],
            ),
        )
        for (
            artifact,
            step_id,
            attempt_id,
            visibility,
            logical_key,
            prompt_id,
            suffix,
            artifact_kind,
            content_sha256,
            byte_size,
        ) in expected_rows:
            expected_key = (
                f"research/{fixture.workspace_id}/{fixture.run_id}/"
                f"{artifact['id']}/{suffix}"
            )
            expected_artifact = {
                "id": artifact["id"],
                "workspace_id": fixture.workspace_id,
                "run_id": fixture.run_id,
                "generated_by_step_id": step_id,
                "generated_by_attempt_id": attempt_id,
                "artifact_kind": artifact_kind,
                "visibility": visibility,
                "logical_key": logical_key,
                "schema_version": "1",
                "object_key": expected_key,
                "content_type": "application/json",
                "byte_size": byte_size,
                "content_sha256": content_sha256,
                "supersedes_artifact_id": None,
                "workflow_version_id": fixture.workflow_id,
                "direct_prompt_version_id": prompt_id,
                "generation_provider": "test",
                "generation_model": "r2-i-deterministic",
                "retention_class": "workspace_lifetime",
                "expires_at": None,
                "created_at": next(
                    attempt["finished_at"]
                    for attempt in after["attempts"]
                    if attempt["id"] == attempt_id
                ),
            }
            if (
                set(artifact) != ARTIFACT_ROW_FIELDS
                or artifact != expected_artifact
                or not _is_uuid(artifact["id"])
            ):
                provenance_exact = False
        if (
            gate_attempts[0]["output_sha256"] != conflict["content_sha256"]
            or synth_attempts[0]["checkpoint_artifact_id"] != checkpoint["id"]
            or after["run"]["latest_checkpoint_artifact_id"] != checkpoint["id"]
        ):
            provenance_exact = False

    new_ids = {artifact["id"] for artifact in new_artifacts}
    before_claim_rows = before.get("artifactClaims", [])
    after_baseline_claim_rows = [
        row for row in after["artifactClaims"] if row["artifact_id"] in before_artifact_ids
    ]
    baseline_claim_rows_immutable = after_baseline_claim_rows == before_claim_rows
    new_claim_rows = [
        row for row in after["artifactClaims"] if row["artifact_id"] in new_ids
    ]
    claim_provenance_exact = (
        baseline_claim_rows_immutable
        and conflict is not None
        and new_claim_rows
        == [
            {
                "artifact_id": conflict["id"],
                "claim_id": fixture.claim_id,
                "claim_order": 0,
                "section_kind": "conflict",
            }
        ]
    )
    before_prompt_rows = before.get("artifactPromptVersions", [])
    after_baseline_prompt_rows = [
        row
        for row in after["artifactPromptVersions"]
        if row["artifact_id"] in before_artifact_ids
    ]
    baseline_prompt_rows_immutable = after_baseline_prompt_rows == before_prompt_rows
    new_prompt_rows = [
        row for row in after["artifactPromptVersions"] if row["artifact_id"] in new_ids
    ]
    expected_prompt_rows = (
        [
            {
                "artifact_id": conflict["id"],
                "node_key": node,
                "prompt_version_id": fixture.prompt_ids[node],
            }
            for node in sorted(fixture.prompt_ids)
        ]
        if conflict is not None
        else []
    )
    prompt_provenance_exact = sorted(
        new_prompt_rows, key=lambda row: (row["artifact_id"], row["node_key"])
    ) == expected_prompt_rows and baseline_prompt_rows_immutable

    manifest_keys = [str(item.get("key")) for item in manifest]
    manifest_by_key = {str(item.get("key")): item for item in manifest}
    manifest_shape_exact = (
        len(manifest_keys) == len(set(manifest_keys)) == 2
        and all(set(item) == {"key", "size", "sha256"} for item in manifest)
    )
    expected_object_keys = {
        artifact["object_key"] for artifact in new_artifacts
    } if artifact_delta_exact else set()
    object_manifest_exact = (
        manifest_shape_exact and set(manifest_by_key) == expected_object_keys
    )
    if object_manifest_exact:
        object_manifest_exact = all(
            int(manifest_by_key[artifact["object_key"]]["size"]) == int(artifact["byte_size"])
            and manifest_by_key[artifact["object_key"]]["sha256"]
            == artifact["content_sha256"]
            for artifact in new_artifacts
        )

    event_artifact_links_exact = artifact_delta_exact
    if artifact_delta_exact and conflict is not None and checkpoint is not None:
        conflict_events = [
            event
            for event in after["events"]
            if event["event_type"] == "artifact_published"
            and (event.get("payload_json") or {}).get("artifactId") == conflict["id"]
        ]
        synth_events = _events_for_step(
            after, fixture.step_ids["synthesizer"], "step_succeeded"
        )
        event_artifact_links_exact = (
            len(conflict_events) == 1
            and len(synth_events) == 1
            and (synth_events[0].get("payload_json") or {}).get("artifactIds")
            == [checkpoint["id"]]
        )

    passed = all(
        (
            artifact_delta_exact,
            baseline_artifacts_immutable,
            baseline_claim_rows_immutable,
            baseline_prompt_rows_immutable,
            provenance_exact,
            artifact_times_causal,
            claim_provenance_exact,
            prompt_provenance_exact,
            object_manifest_exact,
            event_artifact_links_exact,
        )
    )
    return {
        "artifactDeltaExact": artifact_delta_exact,
        "newArtifactRowsExact": provenance_exact,
        "artifactTimesCausal": artifact_times_causal,
        "baselineArtifactsImmutable": baseline_artifacts_immutable,
        "baselineClaimRowsImmutable": baseline_claim_rows_immutable,
        "baselinePromptRowsImmutable": baseline_prompt_rows_immutable,
        "stepAttemptWorkflowPromptProvenanceExact": provenance_exact,
        "claimProvenanceExact": claim_provenance_exact,
        "promptProvenanceExact": prompt_provenance_exact,
        "objectManifestExact": object_manifest_exact,
        "eventArtifactLinksExact": event_artifact_links_exact,
        "newArtifactIds": sorted(new_ids),
        "passed": passed,
    }


def run_scenario(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    projection: Callable[[Any, str], dict[str, Any]],
    lock_projection: Callable[[Any], dict[str, Any]],
    observe_ready_worker_backends: Callable[
        [str, list[dict[str, Any]]], dict[str, Any]
    ],
) -> dict[str, Any]:
    production_sources = production_source_proof()
    fixture = seed_fixture(harness)
    before = full_projection(harness, fixture, projection)
    assert before["run"]["status"] == "running"
    assert step_by_kind(before, "verifier")["status"] == "queued"
    assert step_by_kind(before, "critic")["status"] == "pending"

    with tempfile.TemporaryDirectory(prefix="citeframe-r2-i-objects-") as directory:
        objects = Path(directory)
        launch = lambda specs: launch_workers(
            harness=harness,
            database_url=database_url,
            object_root=objects,
            specs=specs,
            timeout_seconds=timeout_seconds,
            observe_ready_worker_backends=observe_ready_worker_backends,
        )
        verification = launch(
            [
                {
                    "workerInstanceId": "i-verifier",
                    "operation": "verify",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["verifier"],
                    "claimId": fixture.claim_id,
                }
            ]
        )
        assert verification["processRecords"][0]["outcome"] == "completed"
        after_verification = full_projection(harness, fixture, projection)
        assert step_by_kind(after_verification, "verifier")["status"] == "succeeded"
        assert step_by_kind(after_verification, "critic")["status"] == "queued"
        assert after_verification["claims"][0]["verification_status"] == "supported"

        critique = launch(
            [
                {
                    "workerInstanceId": "i-critic",
                    "operation": "critique",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["critic"],
                    "claimId": fixture.claim_id,
                }
            ]
        )
        assert critique["processRecords"][0]["outcome"] == "completed"
        after_critique = full_projection(harness, fixture, projection)
        assert step_by_kind(after_critique, "critic")["status"] == "succeeded"
        assert step_by_kind(after_critique, "conflict_decision_gate")["status"] == "queued"
        assert after_critique["claims"][0]["conflict_status"] == "conflicted"

        gate_wait = launch(
            [
                {
                    "workerInstanceId": "i-conflict-gate",
                    "operation": "wait_gate",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["conflict_gate"],
                    "claimId": fixture.claim_id,
                }
            ]
        )
        assert gate_wait["processRecords"][0]["outcome"] == "waiting"
        after_wait = full_projection(harness, fixture, projection)
        gate = step_by_kind(after_wait, "conflict_decision_gate")
        synth = step_by_kind(after_wait, "synthesizer")
        publisher = step_by_kind(after_wait, "artifact_publisher")
        pending_decisions = [
            decision
            for decision in after_wait["decisions"]
            if decision["decision_type"] == "conflict_resolution"
            and decision["status"] == "pending"
        ]
        assert after_wait["run"]["status"] == "awaiting_human_decision"
        assert gate["status"] == "waiting"
        assert len(attempts_for_step(after_wait, gate["id"])) == 1
        assert attempts_for_step(after_wait, gate["id"])[0]["status"] == "succeeded"
        assert synth["status"] == "pending"
        assert publisher["status"] == "pending"
        assert attempts_for_step(after_wait, synth["id"]) == []
        assert attempts_for_step(after_wait, publisher["id"]) == []
        assert len(pending_decisions) == 1
        decision = pending_decisions[0]

        before_probes = after_wait
        predecision_probes = launch(
            [
                {
                    "workerInstanceId": "i-before-decision-next",
                    "operation": "claim_next_probe",
                },
                {
                    "workerInstanceId": "i-before-decision-synth",
                    "operation": "claim_specific_probe",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["synthesizer"],
                },
            ]
        )
        probe_by_operation = {
            record["operation"]: record
            for record in predecision_probes["processRecords"]
        }
        assert probe_by_operation["claim_next_probe"]["outcome"] == "none"
        assert probe_by_operation["claim_specific_probe"]["outcome"] == "fenced"
        assert (
            probe_by_operation["claim_specific_probe"]["errorCode"]
            == "research_state_conflict"
        )
        after_probes = full_projection(harness, fixture, projection)
        assert before_probes == after_probes

        decision_request = conflict_decision_request(
            expected_state_version=after_wait["run"]["state_version"],
            expected_decision_state_version=decision["state_version"],
            input_artifact_sha256=decision["input_artifact_sha256"],
            input_snapshot_sha256=decision["input_snapshot_sha256"],
        )
        decision_request_body = decision_request.model_dump(mode="json", by_alias=True)
        expected_decision_request_body = {
            "expectedStateVersion": after_wait["run"]["state_version"],
            "expectedDecisionStateVersion": decision["state_version"],
            "inputArtifactSha256": decision["input_artifact_sha256"],
            "inputSnapshotSha256": decision["input_snapshot_sha256"],
            "action": "keep_as_unresolved",
            "comment": "R2-I persisted conflict resume proof.",
        }
        assert decision_request_body == expected_decision_request_body
        decision_common = {
            "operation": "decide_conflict",
            "workspaceId": harness.workspace_id,
            "actorUserId": harness.user_id,
            "runId": fixture.run_id,
            "decisionId": decision["id"],
            "expectedStateVersion": after_wait["run"]["state_version"],
            "expectedDecisionStateVersion": decision["state_version"],
            "inputArtifactSha256": decision["input_artifact_sha256"],
            "inputSnapshotSha256": decision["input_snapshot_sha256"],
        }
        decision_race = launch(
            [
                {
                    **decision_common,
                    "workerInstanceId": "i-decision-a",
                    "idempotencyKey": fixture.decision_keys_by_worker["i-decision-a"],
                },
                {
                    **decision_common,
                    "workerInstanceId": "i-decision-b",
                    "idempotencyKey": fixture.decision_keys_by_worker["i-decision-b"],
                },
            ]
        )
        decision_outcomes = sorted(
            record["outcome"] for record in decision_race["processRecords"]
        )
        assert decision_outcomes == ["decided", "fenced"]
        loser = next(
            record
            for record in decision_race["processRecords"]
            if record["outcome"] == "fenced"
        )
        winner = next(
            record
            for record in decision_race["processRecords"]
            if record["outcome"] == "decided"
        )
        assert loser["errorCode"] == "research_state_conflict"
        expected_winner_key = fixture.decision_keys_by_worker[winner["workerInstanceId"]]
        expected_loser_key = fixture.decision_keys_by_worker[loser["workerInstanceId"]]
        assert winner["idempotencyKey"] == expected_winner_key
        assert loser["idempotencyKey"] == expected_loser_key
        after_decision = full_projection(harness, fixture, projection)
        expected_winner_response = expected_conflict_decision_response(
            after_decision, decision["id"]
        )
        assert after_decision["run"]["status"] == "queued"
        assert step_by_kind(after_decision, "conflict_decision_gate")["status"] == "succeeded"
        assert step_by_kind(after_decision, "synthesizer")["status"] == "queued"
        assert after_decision["claims"][0]["conflict_status"] == "resolved_unresolved"
        idempotency_by_key = {
            record["idempotency_key"]: record
            for record in after_decision["idempotencyRecords"]
        }
        assert set(idempotency_by_key) == {
            expected_winner_key,
            expected_loser_key,
        }
        winner_record = idempotency_by_key[expected_winner_key]
        loser_record = idempotency_by_key[expected_loser_key]
        expected_path = (
            f"/v1/workspaces/{harness.workspace_id}/research-runs/{fixture.run_id}/"
            f"conflict-decisions/{decision['id']}"
        )
        assert winner_record["status"] == "completed"
        assert winner_record["http_status"] == 200
        assert winner_record["workspace_id"] == harness.workspace_id
        assert winner_record["actor_user_id"] == harness.user_id
        assert winner_record["operation"] == "submit_conflict_decision"
        assert winner_record["canonical_resource_path"] == expected_path
        assert winner_record["result_resource_id"] == decision["id"]
        assert winner_record["response_schema_version"] == "1"
        assert winner_record["response_json"]["decision"]["id"] == decision["id"]
        assert winner_record["response_json"]["decision"]["status"] == "submitted"
        assert loser_record["status"] == "failed"
        assert loser_record["http_status"] == 409
        assert loser_record["workspace_id"] == harness.workspace_id
        assert loser_record["actor_user_id"] == harness.user_id
        assert loser_record["operation"] == "submit_conflict_decision"
        assert loser_record["canonical_resource_path"] == expected_path
        assert loser_record["result_resource_id"] is None
        assert loser_record["response_schema_version"] == "1"
        assert loser_record["response_json"]["error"]["code"] == "research_state_conflict"
        assert loser_record["response_json"]["error"]["retryable"] is False
        assert loser_record["response_json"]["error"]["message"] == (
            "Research decision has already been submitted."
        )
        assert isinstance(loser_record["response_json"]["error"]["requestId"], str)
        expected_request_sha256 = canonical_sha256(expected_decision_request_body)
        assert winner_record["request_sha256"] == expected_request_sha256
        assert loser_record["request_sha256"] == expected_request_sha256
        assert len(after_decision["decisionClaims"]) == 1
        assert after_decision["decisionClaims"][0]["disposition"] == "leave_unresolved"

        before_replay = after_decision
        replay = launch(
            [
                {
                    **decision_common,
                    "workerInstanceId": "i-decision-replay",
                    "idempotencyKey": expected_winner_key,
                }
            ]
        )
        assert replay["processRecords"][0]["outcome"] == "replayed"
        after_replay = full_projection(harness, fixture, projection)
        assert before_replay == after_replay

        before_loser_replay = after_replay
        loser_replay = launch(
            [
                {
                    **decision_common,
                    "workerInstanceId": "i-decision-loser-replay",
                    "idempotencyKey": expected_loser_key,
                }
            ]
        )
        frozen = loser_replay["processRecords"][0]
        assert frozen["outcome"] == "fenced"
        assert frozen["errorCode"] == "research_state_conflict"
        assert frozen["httpStatus"] == 409
        assert frozen["idempotencyKey"] == expected_loser_key
        after_loser_replay = full_projection(harness, fixture, projection)
        assert before_loser_replay == after_loser_replay
        idempotency_evidence = decision_idempotency_oracle(
            after_loser_replay,
            workspace_id=harness.workspace_id,
            actor_user_id=harness.user_id,
            run_id=fixture.run_id,
            decision_id=decision["id"],
            expected_request_body=expected_decision_request_body,
            expected_winner_response=expected_winner_response,
            decision_keys_by_worker=fixture.decision_keys_by_worker,
            winner=winner,
            loser=loser,
            winner_replay=replay["processRecords"][0],
            loser_replay=frozen,
        )
        assert idempotency_evidence["passed"], idempotency_evidence

        before_synthesis = after_loser_replay
        assert step_by_kind(before_synthesis, "artifact_publisher")["status"] == "pending"
        synthesis_race = launch(
            [
                {
                    "workerInstanceId": "i-synth-a",
                    "operation": "synthesize",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["synthesizer"],
                    "claimId": fixture.claim_id,
                },
                {
                    "workerInstanceId": "i-synth-b",
                    "operation": "synthesize",
                    "runId": fixture.run_id,
                    "stepKey": fixture.step_keys["synthesizer"],
                    "claimId": fixture.claim_id,
                },
            ]
        )
        assert sorted(
            record["outcome"] for record in synthesis_race["processRecords"]
        ) == ["completed", "conflict"]
        synth_loser = next(
            record
            for record in synthesis_race["processRecords"]
            if record["outcome"] == "conflict"
        )
        assert synth_loser["errorCode"] == "research_state_conflict"
        after = full_projection(harness, fixture, projection)
        synth = step_by_kind(after, "synthesizer")
        publisher = step_by_kind(after, "artifact_publisher")
        assert synth["status"] == "succeeded"
        assert len(attempts_for_step(after, synth["id"])) == 1
        assert attempts_for_step(after, synth["id"])[0]["status"] == "succeeded"
        assert publisher["status"] == "queued"
        assert attempts_for_step(after, publisher["id"]) == []

        objects_manifest = object_manifest(objects)
        artifact_evidence = artifact_oracle(before, after, objects_manifest, fixture)
        assert artifact_evidence["passed"]
        assert str(objects.resolve()) not in json.dumps(objects_manifest, sort_keys=True)

        oracle = event_oracle(after, fixture)
        assert oracle["sequencesContiguousFromOne"]
        assert oracle["dedupeKeysUnique"]
        assert oracle["causalTimeOracle"]["passed"], oracle["causalTimeOracle"]
        assert oracle["strictPartialOrder"], oracle
        live_barriers = [
            evidence["readyBarrierBackendObservation"]
            for evidence in (
                verification,
                critique,
                gate_wait,
                predecision_probes,
                decision_race,
                replay,
                loser_replay,
                synthesis_race,
            )
        ]
        assert all(item["records"] for item in live_barriers)
        return {
            "productionSourceBaseSha": production_sources["baseSha"],
            "productionSourceSha256": production_sources["productionSourceSha256"],
            "productionSourceGitBlobIds": production_sources["productionSourceGitBlobIds"],
            "productionSourceAggregateSha256": production_sources["aggregateSha256"],
            "topology": {
                "runId": fixture.run_id,
                "stepIds": fixture.step_ids,
                "claimId": fixture.claim_id,
                "workflowVersionId": fixture.workflow_id,
                "promptVersionIds": fixture.prompt_ids,
            },
            "before": before,
            "verification": verification,
            "afterVerification": after_verification,
            "critique": critique,
            "afterCritique": after_critique,
            "gateWait": gate_wait,
            "afterWait": after_wait,
            "predecisionProbes": predecision_probes,
            "afterPredecisionProbes": after_probes,
            "decisionRace": decision_race,
            "afterDecision": after_decision,
            "winnerReplay": replay,
            "afterReplay": after_replay,
            "loserFrozenFailureReplay": loser_replay,
            "afterLoserReplay": after_loser_replay,
            "decisionIdempotencyOracle": idempotency_evidence,
            "synthesisRace": synthesis_race,
            "after": after,
            "objectManifest": objects_manifest,
            "artifactOracle": artifact_evidence,
            "eventOracle": oracle,
            "locks": {
                "liveBackendBarrierEvidence": live_barriers,
                "controllerMonitorDiagnostic": lock_projection(harness),
            },
            "assertions": {
                "realWorkflowAndPromptForeignKeys": True,
                "verificationCritiqueGateAndSynthesisProductionCommands": True,
                "persistedWaitingGate": True,
                "claimNextNoneBeforeDecision": True,
                "specificSynthesizerClaimFencedBeforeDecision": True,
                "predecisionProbesZeroMutation": True,
                "differentIdempotencyKeysExactlyOneDecision": True,
                "losingDecisionPersistedFailedAndFenced": True,
                "losingDecisionFrozenFailureReplayZeroMutation": True,
                "winnerSameKeyReplayZeroMutation": True,
                "decisionIdempotencyIdentityAndFrozenResponsesExact": True,
                "decisionIdempotencyIndependentExpectedResponsesExact": True,
                "synthesisResumeCompletedExactlyOnce": True,
                "competingSynthesizerFenced": True,
                "publisherQueuedOnlyAfterCommittedSynthesis": True,
                "publisherHasNoAttempt": True,
                "fullDecisionClaimArtifactDependencyIdempotencyProjection": True,
                "artifactObjectDeltaAndProvenanceExact": True,
                "eventSequenceLifecycleAttemptDependencyOracle": True,
                "stepAttemptEventFullRowsAndPayloadsExact": True,
                "causalBusinessTimeOracleExact": True,
                "newArtifactFullRowsAndNullableProvenanceExact": True,
                "productionSourcesMatchBaseSha": True,
                "livePostgresBackendEvidence": True,
            },
        }
