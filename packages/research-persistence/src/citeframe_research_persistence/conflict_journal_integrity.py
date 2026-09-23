"""Bind journal payloads to their frozen step and producing attempt."""

import hashlib
from sqlalchemy import select
from citeframe_persistence.models import ResearchExecutionSnapshot, ResearchStepAttempt
from .conflict_policy import investigation_step
from .errors import ResearchError, canonical_sha256


def invalid():
    raise ResearchError(
        "research_state_conflict", "Investigation attempt provenance changed.", 409
    )


def current_attempt(db, step):
    snapshot = db.get(
        ResearchExecutionSnapshot, step.execution_snapshot_id, populate_existing=True
    )
    current = db.scalar(
        select(ResearchStepAttempt)
        .where(
            ResearchStepAttempt.step_id == step.id,
            ResearchStepAttempt.attempt_number == step.current_attempt_number,
        )
        .execution_options(populate_existing=True)
    )
    expected = step.input_sha256 or hashlib.sha256(step.id.encode()).hexdigest()
    if (
        not investigation_step(step, snapshot)
        or snapshot.run_id != step.run_id
        or snapshot.workspace_id != step.workspace_id
        or current is None
        or current.workspace_id != step.workspace_id
        or current.input_sha256 != expected
    ):
        invalid()
    return current


def validate_record(db, step, row, current=None):
    current = current or current_attempt(db, step)
    origin = db.get(
        ResearchStepAttempt, row.created_by_attempt_id, populate_existing=True
    )
    if (
        row.step_id != step.id
        or row.execution_snapshot_id != step.execution_snapshot_id
        or origin is None
        or origin.workspace_id != step.workspace_id
        or origin.step_id != step.id
        or origin.input_sha256 != current.input_sha256
        or not 0 < origin.attempt_number <= current.attempt_number
        or (
            origin.id != current.id
            and (
                origin.attempt_number >= current.attempt_number
                or origin.status not in {"failed", "timed_out", "abandoned"}
                or origin.finished_at is None
            )
        )
        or (
            origin.id == current.id
            and origin.status
            not in {
                "running",
                "succeeded",
                "failed",
                "timed_out",
                "abandoned",
                "cancelled",
            }
        )
        or canonical_sha256(row.request_json) != row.request_sha256
        or (
            row.result_json is not None
            and canonical_sha256(row.result_json) != row.result_sha256
        )
    ):
        invalid()
