from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.models import (
    ResearchArtifact,
    ResearchBudgetLedger,
    ResearchExecutionAsset,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
)
from ai_pdf_api.services.research import (
    ResearchError,
    append_research_event,
)
from ai_pdf_api.services.research.research_prompt_provenance import (
    load_execution_prompt_dtos,
    load_planner_prompt_dto,
)
from ai_pdf_api.services.research.research_views import (
    execution_snapshot_dto,
    load_research_plan_artifact,
    planning_input_snapshot,
)
from ai_pdf_api.services.research.research_worker_membership import ensure_creator_membership
from ai_pdf_api.services.research.research_worker_types import (
    ResearchStepLease,
    StepCompletionCallback,
)


def load_planning_input(db: Session, run_id: str) -> dict[str, object]:
    run = db.get(ResearchRun, run_id)
    if run is None or run.current_plan_revision_id is None:
        raise ResearchError("research_run_not_found", "Research run not found.", 404)
    revision = db.get(ResearchPlanRevision, run.current_plan_revision_id)
    if revision is None:
        raise ResearchError("research_resource_not_found", "Research plan revision not found.", 404)
    if revision.run_id != run.id or revision.workspace_id != run.workspace_id:
        raise ResearchError("research_state_conflict", "Research planning chain is invalid.", 409)
    step = db.scalar(
        select(ResearchStep).where(
            ResearchStep.run_id == run.id,
            ResearchStep.plan_revision_id == revision.id,
            ResearchStep.step_kind == "planner",
        )
    )
    if step is None or step.workspace_id != run.workspace_id:
        raise ResearchError("research_resource_not_found", "Research planner step not found.", 404)
    try:
        planner_prompt = load_planner_prompt_dto(db, revision)
    except ValueError as error:
        raise ResearchError("research_state_conflict", "Research Planner Prompt chain is invalid.", 409) from error
    return {
        "runId": run.id,
        "workspaceId": run.workspace_id,
        "runStateVersion": run.state_version,
        "stepId": step.id,
        "stepKey": step.step_key,
        "revisionId": revision.id,
        "inputSnapshot": planning_input_snapshot(db, revision),
        "plannerPrompt": planner_prompt,
    }


def load_approved_execution(db: Session, run_id: str) -> dict[str, object]:
    run = db.get(ResearchRun, run_id)
    if run is None or run.approved_execution_snapshot_id is None:
        raise ResearchError("research_run_not_found", "Approved Research execution not found.", 404)
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    if snapshot is None:
        raise ResearchError("research_resource_not_found", "Research execution snapshot not found.", 404)
    if snapshot.run_id != run.id or snapshot.workspace_id != run.workspace_id:
        raise ResearchError("research_state_conflict", "Research execution chain is invalid.", 409)
    plan_artifact = db.get(ResearchArtifact, snapshot.approved_plan_artifact_id)
    if (
        plan_artifact is None
        or plan_artifact.run_id != run.id
        or plan_artifact.workspace_id != run.workspace_id
        or plan_artifact.content_sha256 != snapshot.approved_plan_artifact_sha256
    ):
        raise ResearchError("research_state_conflict", "Approved Research plan chain is invalid.", 409)
    try:
        plan = load_research_plan_artifact(plan_artifact)
    except (OSError, ValueError) as error:
        raise ResearchError(
            "research_artifact_integrity_mismatch",
            "Approved Research plan bytes failed validation.",
            409,
        ) from error
    steps = list(
        db.scalars(
            select(ResearchStep)
            .where(
                ResearchStep.run_id == run.id,
                ResearchStep.execution_snapshot_id == snapshot.id,
            )
            .order_by(ResearchStep.created_at, ResearchStep.id)
        ).all()
    )
    if any(
        step.workspace_id != run.workspace_id
        or step.run_id != run.id
        or step.execution_snapshot_id != snapshot.id
        for step in steps
    ):
        raise ResearchError("research_state_conflict", "Research execution Step chain is invalid.", 409)
    researchers = {step.branch_key: step for step in steps if step.step_kind == "researcher"}
    if set(researchers) != {item.id for item in plan.subproblems}:
        raise ResearchError("research_state_conflict", "Research plan fan-out does not match its execution DAG.", 409)
    assets = list(
        db.scalars(
            select(ResearchExecutionAsset)
            .where(ResearchExecutionAsset.execution_snapshot_id == snapshot.id)
            .order_by(ResearchExecutionAsset.asset_order)
        ).all()
    )
    try:
        prompts = load_execution_prompt_dtos(db, snapshot)
    except ValueError as error:
        raise ResearchError("research_state_conflict", "Research execution Prompt chain is invalid.", 409) from error
    return {
        "runId": run.id,
        "workspaceId": run.workspace_id,
        "runStatus": run.status,
        "runStateVersion": run.state_version,
        "executionSnapshotId": snapshot.id,
        "executionSnapshotSha256": snapshot.execution_snapshot_sha256,
        "question": snapshot.question_text,
        "workflowVersionId": snapshot.workflow_version_id,
        "promptVersionIds": [str(item["promptVersionId"]) for item in prompts],
        "prompts": prompts,
        "providerConfigFingerprint": snapshot.provider_config_fingerprint,
        "budgetPolicyVersion": snapshot.budget_policy_version,
        "retryPolicyVersion": snapshot.retry_policy_version,
        "maxParallelResearchers": snapshot.max_parallel_researchers,
        "maxProviderCalls": snapshot.max_provider_calls,
        "maxToolCalls": snapshot.max_tool_calls,
        "frozenAssets": [
            {
                "assetId": item.asset_id,
                "assetKind": item.asset_kind_snapshot,
                "assetTitle": item.asset_title_snapshot,
                "processingGeneration": item.processing_generation_snapshot,
                "indexVersion": item.index_version_snapshot,
            }
            for item in assets
        ],
        "subproblems": [
            {
                "stepId": researchers[item.id].id,
                "branchKey": item.id,
                "question": item.question,
                "assetIds": item.asset_ids,
                "expectedEvidence": item.expected_evidence,
            }
            for item in plan.subproblems
        ],
        "snapshot": execution_snapshot_dto(db, snapshot),
        "steps": [
            {
                "id": step.id,
                "key": step.step_key,
                "kind": step.step_kind,
                "branchKey": step.branch_key,
                "status": step.status,
                "stateVersion": step.state_version,
                "currentAttemptNumber": step.current_attempt_number,
            }
            for step in steps
        ],
    }



from citeframe_research_persistence.lease import (
    _active_attempt_chain as _neutral_active_attempt_chain,
    _ledger_and_limits,
    _locked_attempt as _neutral_locked_attempt,
    _locked_attempt_chain as _neutral_locked_attempt_chain,
    claim_next_research_step,
    claim_specific_research_step,
    complete_research_step,
    heartbeat_research_step,
)


def _locked_attempt_chain(db: Session, attempt_id: str):
    return _neutral_locked_attempt_chain(db, attempt_id)


def _locked_attempt(*, db: Session, attempt_id: str, lease_token: str, now: datetime):
    return _neutral_locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=now,
        locked_chain=_locked_attempt_chain,
    )


def _active_attempt_chain(db: Session, attempt_id: str, *, now: datetime):
    return _neutral_active_attempt_chain(
        db,
        attempt_id,
        now=now,
        locked_chain=_locked_attempt_chain,
    )
