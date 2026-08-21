from __future__ import annotations

from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from citeframe_persistence.models import HumanDecision, ResearchRun, ResearchStep, ResearchStepAttempt, WorkspaceMembership
from .errors import ResearchError
from .events import append_research_event


def finalize_cancel_if_idle(db: Session, run: ResearchRun, *, now: datetime) -> bool:
    active_attempts = db.scalar(select(func.count()).select_from(ResearchStepAttempt).join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id).where(ResearchStep.run_id == run.id, ResearchStepAttempt.status == "running")) or 0
    if active_attempts:
        return False
    steps = list(db.scalars(select(ResearchStep).where(ResearchStep.run_id == run.id, ResearchStep.workspace_id == run.workspace_id)).all())
    for step in steps:
        if step.status != "succeeded" and step.status not in {"cancelled", "skipped"}:
            step.status = "cancelled"
            step.state_version += 1
            step.finished_at = now
            step.updated_at = now
    decisions = list(db.scalars(select(HumanDecision).where(HumanDecision.run_id == run.id, HumanDecision.workspace_id == run.workspace_id, HumanDecision.status == "pending")).all())
    for decision in decisions:
        decision.status = "cancelled"
        decision.state_version += 1
    run.status = "cancelled"
    run.finished_at = now
    run.updated_at = now
    run.state_version += 1
    append_research_event(db, run, event_type="run_cancelled", dedupe_key=f"run-cancelled:{run.state_version}", data={"status": "cancelled", "reasonCode": run.cancel_reason_code or "user_requested", "runStateVersion": run.state_version}, now=now)
    return True


def ensure_creator_membership(db: Session, run: ResearchRun, *, now: datetime) -> None:
    membership = db.scalar(select(WorkspaceMembership.id).where(WorkspaceMembership.workspace_id == run.workspace_id, WorkspaceMembership.user_id == run.created_by_user_id))
    if membership is not None:
        return
    if run.status in {"completed", "failed", "cancelled"}:
        raise ResearchError("research_state_conflict", "Research creator is no longer a Workspace member.", 409)
    if run.status != "cancel_requested":
        run.status = "cancel_requested"
        run.cancel_requested_by_user_id = run.created_by_user_id
        run.cancel_reason_code = "creator_membership_removed"
        run.cancel_requested_at = now
        run.updated_at = now
        run.state_version += 1
        append_research_event(db, run, event_type="cancel_requested", dedupe_key=f"creator-membership-removed:{run.id}", data={"actorUserId": run.created_by_user_id, "reasonCode": "creator_membership_removed", "runStateVersion": run.state_version}, now=now)
    finalize_cancel_if_idle(db, run, now=now)
    db.commit()
    raise ResearchError("research_permission_denied", "Research creator is no longer a Workspace member.", 403)
