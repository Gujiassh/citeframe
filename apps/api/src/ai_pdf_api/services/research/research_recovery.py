"""Manual research step retry recovery."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_pdf_api.schemas.research import RetryResearchStepRequest
from citeframe_research_persistence.retry import retry_research_step_transition
from ai_pdf_api.services.research.research_idempotency import (
    _idempotent_mutation,
    validate_idempotency_key,
)
from ai_pdf_api.services.research.research_views import run_detail
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
        run, step = retry_research_step_transition(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            run_id=run_id,
            step_id=step_id,
            failed_attempt=payload.failed_attempt,
            expected_run_state_version=payload.expected_state_version,
            expected_step_state_version=payload.expected_step_state_version,
            now=datetime.now(UTC),
        )
        from ai_pdf_api.services.research.research_views import _step_dto

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
