"""Manual research step retry recovery."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_pdf_api.models import (
    ResearchBudgetLedger,
    ResearchExecutionSnapshot,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepRetryRequest,
)
from ai_pdf_api.schemas.research import RetryResearchStepRequest
from ai_pdf_api.services.research_constants import RETRYABLE_FAILURE_CODES
from ai_pdf_api.services.research_events import append_research_event
from ai_pdf_api.services.research_idempotency import (
    ResearchError,
    _idempotent_mutation,
    validate_idempotency_key,
)
from ai_pdf_api.services.research_runs import _get_research_run_for_update
from ai_pdf_api.services.research_views import run_detail
from sqlalchemy import select
from sqlalchemy.orm import Session


def retry_research_step(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    run_id: str,
    step_id: str,
    payload: RetryResearchStepRequest,
    idempotency_key: str,
) -> tuple[int, dict[str, object], bool]:
    key = validate_idempotency_key(idempotency_key)
    path = f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/steps/{step_id}/retry"
    body = payload.model_dump(mode="json", by_alias=True)

    def execute() -> tuple[int, dict[str, object], str]:
        run = _get_research_run_for_update(db, workspace_id, run_id)
        if actor_user_id != run.created_by_user_id:
            raise ResearchError("research_permission_denied", "Only the Run creator can retry a branch.", 403)
        step = db.scalar(
            select(ResearchStep).where(
                ResearchStep.id == step_id,
                ResearchStep.run_id == run.id,
                ResearchStep.workspace_id == workspace_id,
            )
        )
        if step is None:
            raise ResearchError("research_resource_not_found", "Research step not found.", 404)
        if run.status != "awaiting_retry" or step.status != "failed":
            raise ResearchError("research_state_conflict", "Research branch is not awaiting retry.", 409)
        if run.state_version != payload.expected_state_version or step.state_version != payload.expected_step_state_version:
            raise ResearchError("stale_state_version", "Research retry state is stale.", 409)
        attempt = db.scalar(
            select(ResearchStepAttempt).where(
                ResearchStepAttempt.step_id == step.id,
                ResearchStepAttempt.attempt_number == payload.failed_attempt,
            )
        )
        if attempt is None or attempt.status not in {"failed", "timed_out", "abandoned"}:
            raise ResearchError("research_state_conflict", "Failed attempt does not match.", 409)
        if payload.failed_attempt != step.current_attempt_number or step.current_attempt_number >= step.max_attempts_snapshot:
            raise ResearchError("research_retry_limit", "The frozen retry limit has been reached.", 409)
        if step.error_code not in RETRYABLE_FAILURE_CODES:
            raise ResearchError("research_retry_forbidden", "This failure is not retryable.", 422)
        snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
        ledger = db.scalar(
            select(ResearchBudgetLedger).where(
                ResearchBudgetLedger.execution_snapshot_id == run.approved_execution_snapshot_id
            )
        )
        if snapshot is None or ledger is None or (
            ledger.actual_provider_calls + ledger.reserved_provider_calls >= snapshot.max_provider_calls
            or ledger.actual_tool_calls + ledger.reserved_tool_calls >= snapshot.max_tool_calls
        ):
            # Cost and cumulative tokens are usage-only; they never block retry.
            raise ResearchError("research_budget_limit", "The frozen Research budget is exhausted.", 422)
        now = datetime.now(UTC)
        retry = ResearchStepRetryRequest(
            workspace_id=workspace_id,
            run_id=run.id,
            step_id=step.id,
            failed_attempt_number=payload.failed_attempt,
            requested_by_user_id=actor_user_id,
            expected_run_state_version=payload.expected_state_version,
            expected_step_state_version=payload.expected_step_state_version,
            requested_at=now,
        )
        db.add(retry)
        step.status = "queued"
        step.state_version += 1
        step.error_code = None
        step.error_message = None
        step.finished_at = None
        step.queued_at = now
        step.updated_at = now
        run.status = "queued"
        run.state_version += 1
        run.failure_code = None
        run.failure_message = None
        run.updated_at = now
        append_research_event(
            db,
            run,
            event_type="step_queued",
            dedupe_key=f"manual-retry:{step.id}:{payload.failed_attempt}",
            step_id=step.id,
            data={
                "stepId": step.id,
                "stepKind": step.step_kind,
                "branchKey": step.branch_key,
                "attemptNumber": step.current_attempt_number,
                "stepStateVersion": step.state_version,
                "runStateVersion": run.state_version,
            },
            now=now,
        )
        db.flush()
        from ai_pdf_api.services.research_views import _step_dto

        return 202, {"run": run_detail(db, run), "step": _step_dto(db, step)}, step.id

    return _idempotent_mutation(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        operation="retry_step",
        resource_path=path,
        key=key,
        request_body=body,
        execute=execute,
    )
