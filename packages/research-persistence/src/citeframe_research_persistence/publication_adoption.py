"""Permission and replay provenance checks at publication adoption."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from citeframe_persistence.models import ResearchStep, ResearchStepAttempt, ResearchToolCall, WorkspaceMembership


def lock_creator_membership(db: Session, run) -> bool:
    # Held until adoption commits: a concurrent DELETE either wins before this
    # check or waits until the authorized publication has committed.
    return db.scalar(
        select(WorkspaceMembership.id)
        .where(WorkspaceMembership.workspace_id == run.workspace_id,
               WorkspaceMembership.user_id == run.created_by_user_id)
        .with_for_update(of=WorkspaceMembership)
    ) is not None


def tool_attempt_is_replayable(
    db: Session, tool: ResearchToolCall, producer: ResearchStep,
    current: ResearchStepAttempt,
) -> bool:
    origin = db.scalar(select(ResearchStepAttempt)
        .where(ResearchStepAttempt.id == tool.attempt_id)
        .execution_options(populate_existing=True))
    return bool(
        origin is not None
        and origin.workspace_id == producer.workspace_id
        and origin.step_id == producer.id
        and origin.input_sha256 == producer.input_sha256 == current.input_sha256
        and origin.finished_at is not None
        and tool.tool_name == "evidence.search" and tool.tool_version == 1
        and tool.error_code is None and tool.error_message is None
        and (
            origin.id == current.id
            or (0 < origin.attempt_number < current.attempt_number
                and origin.status in {"failed", "timed_out", "abandoned"})
        )
    )
