from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.models import ResearchRun, WorkspaceMembership
from ai_pdf_api.services.research import (
    ResearchError,
    append_research_event,
    finalize_cancel_if_idle,
)


def ensure_creator_membership(db: Session, run: ResearchRun, *, now: datetime) -> None:
    membership = db.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == run.workspace_id,
            WorkspaceMembership.user_id == run.created_by_user_id,
        )
    )
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
        append_research_event(
            db,
            run,
            event_type="cancel_requested",
            dedupe_key=f"creator-membership-removed:{run.id}",
            data={
                "actorUserId": run.created_by_user_id,
                "reasonCode": "creator_membership_removed",
                "runStateVersion": run.state_version,
            },
            now=now,
        )
    finalize_cancel_if_idle(db, run, now=now)
    db.commit()
    raise ResearchError("research_permission_denied", "Research creator is no longer a Workspace member.", 403)
