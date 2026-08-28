"""Per-Run researcher admission backed by existing Attempt rows."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from citeframe_persistence.models import (
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)

from .errors import ResearchError


def researcher_admission_is_full(
    db: Session,
    run: ResearchRun,
    *,
    step_workspace_id: str,
    step_execution_snapshot_id: str | None,
) -> bool:
    """Validate the frozen execution chain and evaluate its cap using database time."""
    snapshot_id = run.approved_execution_snapshot_id
    if snapshot_id is None:
        raise ResearchError("research_state_conflict", "Research execution chain is invalid.", 409)
    with db.no_autoflush:
        snapshot = db.scalar(
            select(ResearchExecutionSnapshot)
            .where(ResearchExecutionSnapshot.id == snapshot_id)
            .execution_options(populate_existing=True)
        )
    if (
        snapshot is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or step_workspace_id != run.workspace_id
        or step_execution_snapshot_id != snapshot.id
        or snapshot.max_parallel_researchers < 1
    ):
        raise ResearchError("research_state_conflict", "Research execution chain is invalid.", 409)

    with db.no_autoflush:
        active_attempts = db.scalar(
            select(func.count(ResearchStepAttempt.id))
            .select_from(ResearchStepAttempt)
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run.id,
                ResearchStep.workspace_id == run.workspace_id,
                ResearchStep.execution_snapshot_id == snapshot.id,
                ResearchStep.step_kind == "researcher",
                ResearchStepAttempt.workspace_id == run.workspace_id,
                ResearchStepAttempt.status == "running",
                ResearchStepAttempt.lease_expires_at.is_not(None),
                ResearchStepAttempt.lease_expires_at > func.current_timestamp(),
            )
        )
    return int(active_attempts or 0) >= snapshot.max_parallel_researchers
