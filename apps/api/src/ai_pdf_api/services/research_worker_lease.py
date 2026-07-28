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
from ai_pdf_api.services.research_prompt_provenance import (
    load_execution_prompt_dtos,
    load_planner_prompt_dto,
)
from ai_pdf_api.services.research_views import (
    execution_snapshot_dto,
    load_research_plan_artifact,
    planning_input_snapshot,
)
from ai_pdf_api.services.research_worker_membership import ensure_creator_membership
from ai_pdf_api.services.research_worker_types import (
    ResearchStepLease,
    StepCompletionCallback,
)


def _queue_ready_dependents(db: Session, run: ResearchRun, completed_step: ResearchStep, now: datetime) -> None:
    dependent_ids = list(
        db.scalars(
            select(ResearchStepDependency.step_id).where(
                ResearchStepDependency.depends_on_step_id == completed_step.id
            )
        ).all()
    )
    for dependent_id in dependent_ids:
        dependent = db.scalar(
            select(ResearchStep).where(ResearchStep.id == dependent_id).with_for_update()
        )
        if (
            dependent is None
            or dependent.status != "pending"
            or dependent.run_id != run.id
            or dependent.workspace_id != run.workspace_id
        ):
            continue
        dependencies = list(
            db.scalars(
                select(ResearchStep)
                .join(
                    ResearchStepDependency,
                    ResearchStepDependency.depends_on_step_id == ResearchStep.id,
                )
                .where(ResearchStepDependency.step_id == dependent.id)
            ).all()
        )
        if not dependencies or any(
            item.status != "succeeded"
            or item.run_id != run.id
            or item.workspace_id != run.workspace_id
            for item in dependencies
        ):
            continue
        dependent.status = "queued"
        dependent.state_version += 1
        dependent.queued_at = now
        dependent.updated_at = now
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="step_queued",
            dedupe_key=f"step-queued:{dependent.id}:{dependent.current_attempt_number}",
            step_id=dependent.id,
            data={
                "stepId": dependent.id,
                "stepKind": dependent.step_kind,
                "branchKey": dependent.branch_key,
                "attemptNumber": dependent.current_attempt_number,
                "stepStateVersion": dependent.state_version,
                "runStateVersion": run.state_version,
            },
            now=now,
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


def _lease_step(
    db: Session,
    step: ResearchStep,
    *,
    worker_instance_id: str,
    lease_seconds: int,
    now: datetime,
) -> ResearchStepLease:
    run = db.scalar(select(ResearchRun).where(ResearchRun.id == step.run_id).with_for_update())
    if run is None or run.status not in {"planning", "queued", "running"}:
        raise ResearchError("research_state_conflict", "Research run cannot lease work.", 409)
    ensure_creator_membership(db, run, now=now)
    step = db.scalar(select(ResearchStep).where(ResearchStep.id == step.id).with_for_update())
    if (
        step is None
        or step.status != "queued"
        or step.run_id != run.id
        or step.workspace_id != run.workspace_id
    ):
        raise ResearchError("research_state_conflict", "Research step is not queued.", 409)
    if step.step_kind == "planner":
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        if revision is None or revision.run_id != run.id or revision.workspace_id != run.workspace_id:
            raise ResearchError("research_state_conflict", "Research planning Step chain is invalid.", 409)
    else:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        if snapshot is None or snapshot.run_id != run.id or snapshot.workspace_id != run.workspace_id:
            raise ResearchError("research_state_conflict", "Research execution Step chain is invalid.", 409)
    if step.current_attempt_number >= step.max_attempts_snapshot:
        raise ResearchError("research_retry_limit", "Research step attempt limit is exhausted.", 409)
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=lease_seconds)
    attempt = ResearchStepAttempt(
        workspace_id=step.workspace_id,
        step_id=step.id,
        attempt_number=step.current_attempt_number + 1,
        status="running",
        lease_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        worker_instance_id=worker_instance_id,
        lease_expires_at=expires_at,
        heartbeat_at=now,
        input_sha256=step.input_sha256 or hashlib.sha256(step.id.encode("utf-8")).hexdigest(),
        started_at=now,
    )
    db.add(attempt)
    db.flush()
    previous_status = run.status
    if run.status != "running":
        run.status = "running"
        run.state_version += 1
        if run.started_at is None:
            run.started_at = now
        append_research_event(
            db,
            run,
            event_type="run_status_changed",
            dedupe_key=f"worker-run-started:{attempt.id}",
            data={
                "previousStatus": previous_status,
                "status": "running",
                "runStateVersion": run.state_version,
                "reasonCode": None,
            },
            now=now,
        )
    step.status = "running"
    step.current_attempt_number = attempt.attempt_number
    step.state_version += 1
    step.started_at = step.started_at or now
    step.updated_at = now
    run.state_version += 1
    run.updated_at = now
    append_research_event(
        db,
        run,
        event_type="step_started",
        dedupe_key=f"step-started:{attempt.id}",
        step_id=step.id,
        attempt_id=attempt.id,
        data={
            "stepId": step.id,
            "stepKind": step.step_kind,
            "branchKey": step.branch_key,
            "attemptId": attempt.id,
            "attemptNumber": attempt.attempt_number,
            "stepStateVersion": step.state_version,
            "runStateVersion": run.state_version,
        },
        now=now,
    )
    db.commit()
    return ResearchStepLease(
        workspace_id=step.workspace_id,
        run_id=run.id,
        step_id=step.id,
        step_key=step.step_key,
        step_kind=step.step_kind,
        branch_key=step.branch_key,
        attempt_id=attempt.id,
        attempt_number=attempt.attempt_number,
        lease_token=token,
        lease_expires_at=expires_at,
    )


def claim_next_research_step(
    db: Session,
    *,
    worker_instance_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> ResearchStepLease | None:
    claimed_at = now or datetime.now(UTC)
    step = db.scalar(
        select(ResearchStep)
        .join(ResearchRun, ResearchRun.id == ResearchStep.run_id)
        .where(
            ResearchStep.status == "queued",
            ResearchRun.status.in_(("planning", "queued", "running")),
        )
        .order_by(ResearchStep.queued_at, ResearchStep.created_at, ResearchStep.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if step is None:
        return None
    return _lease_step(
        db,
        step,
        worker_instance_id=worker_instance_id,
        lease_seconds=lease_seconds,
        now=claimed_at,
    )


def claim_specific_research_step(
    db: Session,
    *,
    run_id: str,
    step_key: str,
    branch_key: str | None,
    worker_instance_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> ResearchStepLease:
    branch_predicate = (
        ResearchStep.branch_key.is_(None)
        if branch_key is None
        else ResearchStep.branch_key == branch_key
    )
    step = db.scalar(
        select(ResearchStep)
        .where(
            ResearchStep.run_id == run_id,
            ResearchStep.step_key == step_key,
            branch_predicate,
        )
        .with_for_update()
    )
    if step is None:
        raise ResearchError("research_resource_not_found", "Research step not found.", 404)
    return _lease_step(
        db,
        step,
        worker_instance_id=worker_instance_id,
        lease_seconds=lease_seconds,
        now=now or datetime.now(UTC),
    )


def _locked_attempt_chain(
    db: Session,
    attempt_id: str,
) -> tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]:
    """Lock attempt -> step -> run without requiring active run/attempt state."""
    attempt = db.scalar(
        select(ResearchStepAttempt)
        .where(ResearchStepAttempt.id == attempt_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        return None, None, None
    step = db.scalar(
        select(ResearchStep)
        .where(ResearchStep.id == attempt.step_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if step is None:
        return None, None, attempt
    run = db.scalar(
        select(ResearchRun)
        .where(ResearchRun.id == step.run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return run, step, attempt


def _locked_attempt(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    now: datetime,
) -> tuple[ResearchRun, ResearchStep, ResearchStepAttempt]:
    run, step, attempt = _locked_attempt_chain(db, attempt_id)
    if attempt is None:
        raise ResearchError("research_resource_not_found", "Research step attempt not found.", 404)
    token_hash = hashlib.sha256(lease_token.encode("utf-8")).hexdigest()
    expires_at = attempt.lease_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        attempt.status != "running"
        or attempt.lease_token_hash != token_hash
        or expires_at is None
        or expires_at <= now
    ):
        raise ResearchError("research_state_conflict", "Research step lease is not valid.", 409)
    if step is None or step.status != "running" or attempt.workspace_id != step.workspace_id:
        raise ResearchError("research_state_conflict", "Research step is not running.", 409)
    if (
        run is None
        or step.workspace_id != run.workspace_id
        or run.status in {"cancel_requested", "completed", "failed", "cancelled"}
    ):
        raise ResearchError("research_state_conflict", "Research run no longer accepts this result.", 409)
    if step.step_kind == "planner":
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        chain_valid = revision is not None and revision.run_id == run.id and revision.workspace_id == run.workspace_id
    else:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        chain_valid = snapshot is not None and snapshot.run_id == run.id and snapshot.workspace_id == run.workspace_id
    if not chain_valid:
        raise ResearchError("research_state_conflict", "Research Attempt chain is invalid.", 409)
    ensure_creator_membership(db, run, now=now)
    return run, step, attempt


def heartbeat_research_step(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> datetime:
    heartbeat_at = now or datetime.now(UTC)
    _run, _step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=heartbeat_at,
    )
    attempt.heartbeat_at = heartbeat_at
    attempt.lease_expires_at = heartbeat_at + timedelta(seconds=lease_seconds)
    db.commit()
    return attempt.lease_expires_at


def complete_research_step(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    output_sha256: str,
    complete: StepCompletionCallback | None = None,
    now: datetime | None = None,
) -> None:
    finished_at = now or datetime.now(UTC)
    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=finished_at,
    )
    try:
        evidence_count, artifact_ids = complete(db, run, step, attempt) if complete else (0, [])
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact_ids must be unique")
        attempt.status = "succeeded"
        attempt.output_sha256 = output_sha256
        attempt.finished_at = finished_at
        attempt.lease_expires_at = None
        step.status = "succeeded"
        step.state_version += 1
        step.finished_at = finished_at
        step.updated_at = finished_at
        run.state_version += 1
        run.updated_at = finished_at
        append_research_event(
            db,
            run,
            event_type="step_succeeded",
            dedupe_key=f"step-succeeded:{attempt.id}",
            step_id=step.id,
            attempt_id=attempt.id,
            data={
                "stepId": step.id,
                "stepKind": step.step_kind,
                "attemptId": attempt.id,
                "attemptNumber": attempt.attempt_number,
                "evidenceCount": evidence_count,
                "artifactIds": artifact_ids,
                "stepStateVersion": step.state_version,
                "runStateVersion": run.state_version,
            },
            now=finished_at,
        )
        _queue_ready_dependents(db, run, step, finished_at)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _ledger_and_limits(
    db: Session,
    step: ResearchStep,
) -> tuple[ResearchBudgetLedger, int, int, int, int, int]:
    if step.plan_revision_id is not None:
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        ledger = db.scalar(
            select(ResearchBudgetLedger)
            .where(ResearchBudgetLedger.plan_revision_id == step.plan_revision_id)
            .with_for_update()
        )
        if (
            revision is None
            or ledger is None
            or revision.run_id != step.run_id
            or revision.workspace_id != step.workspace_id
            or ledger.run_id != step.run_id
            or ledger.workspace_id != step.workspace_id
        ):
            raise ResearchError("research_resource_not_found", "Planning budget ledger not found.", 404)
        return (
            ledger,
            revision.planning_max_provider_calls,
            0,
            revision.planning_max_input_tokens,
            revision.planning_max_output_tokens,
            revision.planning_max_cost_microunits,
        )
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    ledger = db.scalar(
        select(ResearchBudgetLedger)
        .where(ResearchBudgetLedger.execution_snapshot_id == step.execution_snapshot_id)
        .with_for_update()
    )
    if (
        snapshot is None
        or ledger is None
        or snapshot.run_id != step.run_id
        or snapshot.workspace_id != step.workspace_id
        or ledger.run_id != step.run_id
        or ledger.workspace_id != step.workspace_id
    ):
        raise ResearchError("research_resource_not_found", "Execution budget ledger not found.", 404)
    return (
        ledger,
        snapshot.max_provider_calls,
        snapshot.max_tool_calls,
        snapshot.max_input_tokens,
        snapshot.max_output_tokens,
        snapshot.max_cost_microunits,
    )


def _active_attempt_chain(
    db: Session,
    attempt_id: str,
    *,
    now: datetime,
) -> tuple[ResearchRun, ResearchStep, ResearchStepAttempt]:
    run, step, attempt = _locked_attempt_chain(db, attempt_id)
    expires_at = attempt.lease_expires_at if attempt else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        attempt is None
        or step is None
        or run is None
        or attempt.status != "running"
        or step.status != "running"
        or expires_at is None
        or expires_at <= now
        or attempt.workspace_id != step.workspace_id
        or step.workspace_id != run.workspace_id
        or run.status not in {"planning", "running"}
    ):
        raise ResearchError("research_state_conflict", "Research attempt is not active.", 409)
    ensure_creator_membership(db, run, now=now)
    return run, step, attempt
