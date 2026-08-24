"""Ordered Research aggregate row-lock primitives."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from citeframe_persistence.models import ResearchRun, ResearchStep, ResearchStepAttempt


@dataclass(frozen=True)
class AttemptLocator:
    run_id: str
    step_id: str


def locate_attempt(db: Session, attempt_id: str) -> AttemptLocator | None:
    """Read parent ids without locks; callers must treat them only as location hints."""
    with db.no_autoflush:
        row = db.execute(
            select(ResearchStep.run_id, ResearchStepAttempt.step_id)
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(ResearchStepAttempt.id == attempt_id)
        ).one_or_none()
    return AttemptLocator(run_id=row.run_id, step_id=row.step_id) if row is not None else None


def lock_run(
    db: Session,
    run_id: str,
    *,
    workspace_id: str | None = None,
    skip_locked: bool = False,
) -> ResearchRun | None:
    query = select(ResearchRun).where(ResearchRun.id == run_id)
    if workspace_id is not None:
        query = query.where(ResearchRun.workspace_id == workspace_id)
    with db.no_autoflush:
        return db.scalar(
            query.with_for_update(of=ResearchRun, skip_locked=skip_locked).execution_options(
                populate_existing=True
            )
        )


def lock_step(
    db: Session,
    step_id: str,
    *,
    run_id: str,
    workspace_id: str | None = None,
    skip_locked: bool = False,
) -> ResearchStep | None:
    query = select(ResearchStep).where(
        ResearchStep.id == step_id,
        ResearchStep.run_id == run_id,
    )
    if workspace_id is not None:
        query = query.where(ResearchStep.workspace_id == workspace_id)
    with db.no_autoflush:
        return db.scalar(
            query.with_for_update(of=ResearchStep, skip_locked=skip_locked).execution_options(
                populate_existing=True
            )
        )


def lock_attempt(
    db: Session,
    attempt_id: str,
    *,
    step_id: str,
    workspace_id: str | None = None,
    skip_locked: bool = False,
) -> ResearchStepAttempt | None:
    query = select(ResearchStepAttempt).where(
        ResearchStepAttempt.id == attempt_id,
        ResearchStepAttempt.step_id == step_id,
    )
    if workspace_id is not None:
        query = query.where(ResearchStepAttempt.workspace_id == workspace_id)
    with db.no_autoflush:
        return db.scalar(
            query.with_for_update(
                of=ResearchStepAttempt,
                skip_locked=skip_locked,
            ).execution_options(populate_existing=True)
        )


def lock_attempt_chain(
    db: Session,
    attempt_id: str,
    *,
    skip_locked: bool = False,
) -> tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]:
    """Locate, then lock and refresh Run -> Step -> Attempt, failing closed on drift."""
    locator = locate_attempt(db, attempt_id)
    if locator is None:
        return None, None, None
    run = lock_run(db, locator.run_id, skip_locked=skip_locked)
    if run is None:
        return None, None, None
    step = lock_step(
        db,
        locator.step_id,
        run_id=run.id,
        workspace_id=run.workspace_id,
        skip_locked=skip_locked,
    )
    if step is None:
        return run, None, None
    attempt = lock_attempt(
        db,
        attempt_id,
        step_id=step.id,
        workspace_id=run.workspace_id,
        skip_locked=skip_locked,
    )
    if (
        attempt is None
        or locator.run_id != run.id
        or locator.step_id != step.id
        or step.run_id != run.id
        or step.workspace_id != run.workspace_id
        or attempt.step_id != step.id
        or attempt.workspace_id != run.workspace_id
    ):
        return run, step, None
    return run, step, attempt


def lock_attempt_chain_with_steps(
    db: Session,
    attempt_id: str,
    *,
    related_step_ids: tuple[str, ...],
) -> tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]:
    """Lock every known Step in an Attempt mutation before locking its Attempt."""
    locator = locate_attempt(db, attempt_id)
    if locator is None:
        return None, None, None
    run = lock_run(db, locator.run_id)
    if run is None:
        return None, None, None
    locked_steps: dict[str, ResearchStep] = {}
    for step_id in sorted({locator.step_id, *related_step_ids}):
        step = lock_step(
            db,
            step_id,
            run_id=run.id,
            workspace_id=run.workspace_id,
        )
        if step is None:
            return run, locked_steps.get(locator.step_id), None
        locked_steps[step.id] = step
    owner_step = locked_steps[locator.step_id]
    attempt = lock_attempt(
        db,
        attempt_id,
        step_id=owner_step.id,
        workspace_id=run.workspace_id,
    )
    if attempt is None or attempt.step_id != owner_step.id:
        return run, owner_step, None
    return run, owner_step, attempt


_LEGACY_LEASE_EXPORTS = {"_active_attempt_chain", "_locked_attempt", "_locked_attempt_chain"}


def __getattr__(name: str):
    if name in _LEGACY_LEASE_EXPORTS:
        from . import lease

        return getattr(lease, name)
    raise AttributeError(name)


__all__ = [
    "_active_attempt_chain",
    "_locked_attempt",
    "_locked_attempt_chain",
    "AttemptLocator",
    "locate_attempt",
    "lock_attempt",
    "lock_attempt_chain",
    "lock_attempt_chain_with_steps",
    "lock_run",
    "lock_step",
]
