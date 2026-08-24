"""Canonical Research cancellation transitions."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from citeframe_persistence.models import ResearchRun

from .constants import TERMINAL_RUN_STATUSES
from .errors import ResearchError
from .events import append_research_event
from .membership import finalize_cancel_if_idle


def cancel_research_run_transition(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    actor_role: str,
    run_id: str,
    expected_state_version: int,
    reason_code: str,
    now: datetime,
) -> ResearchRun:
    run = db.scalar(
        select(ResearchRun)
        .where(ResearchRun.id == run_id, ResearchRun.workspace_id == workspace_id)
        .with_for_update()
    )
    if run is None:
        raise ResearchError("research_run_not_found", "Research run not found.", 404)
    if actor_user_id != run.created_by_user_id and not (
        actor_role == "owner" and reason_code in {"cost", "security"}
    ):
        raise ResearchError("research_permission_denied", "You cannot cancel this Research run.", 403)
    if run.status in TERMINAL_RUN_STATUSES or run.status == "cancel_requested":
        raise ResearchError(
            "research_state_conflict",
            "Research run cannot be cancelled in its current state.",
            409,
        )
    if run.state_version != expected_state_version:
        raise ResearchError("stale_state_version", "Research run state version is stale.", 409)
    run.status = "cancel_requested"
    run.cancel_requested_by_user_id = actor_user_id
    run.cancel_reason_code = reason_code
    run.cancel_requested_at = now
    run.state_version += 1
    run.updated_at = now
    append_research_event(
        db,
        run,
        event_type="cancel_requested",
        dedupe_key=f"cancel-requested:{run.state_version}",
        data={
            "actorUserId": actor_user_id,
            "reasonCode": reason_code,
            "runStateVersion": run.state_version,
        },
        now=now,
    )
    finalize_cancel_if_idle(db, run, now=now)
    db.flush()
    return run
