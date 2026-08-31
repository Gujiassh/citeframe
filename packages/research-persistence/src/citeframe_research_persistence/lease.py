from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from citeframe_persistence.models import (
    ResearchBudgetLedger,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
)
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from .errors import ResearchAdmissionDeferred, ResearchError
from .events import append_research_event
from .locks import (
    locate_attempt,
    lock_attempt_chain,
    lock_attempt_chain_with_steps,
    lock_run,
    lock_step,
)
from .membership import ensure_creator_membership
from .types import ResearchStepLease, StepCompletionCallback

WORKER_EXECUTABLE_STEP_KINDS = (
    "planner",
    "researcher",
    "join",
    "verifier",
    "critic",
    "conflict_decision_gate",
    "synthesizer",
    "artifact_publisher",
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
        # Completion pre-locks every dependent Step before its owning Attempt.
        dependent = db.get(ResearchStep, dependent_id)
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


def _lease_locked_step(
    db: Session,
    run: ResearchRun,
    step: ResearchStep,
    *,
    worker_instance_id: str,
    lease_seconds: int,
    now: datetime,
) -> ResearchStepLease:
    if run.status not in {"planning", "queued", "running"}:
        raise ResearchError("research_state_conflict", "Research run cannot lease work.", 409)
    if step.step_kind not in WORKER_EXECUTABLE_STEP_KINDS:
        raise ResearchError(
            "research_state_conflict",
            "Research step is not Worker-executable.",
            409,
        )
    ensure_creator_membership(db, run, now=now)
    if (
        step.status != "queued"
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
    db.flush()
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


def _lease_step(
    db: Session,
    step: ResearchStep,
    *,
    worker_instance_id: str,
    lease_seconds: int,
    now: datetime,
) -> ResearchStepLease:
    # ``step`` is a locator only. Refresh the mutable aggregate Run-first.
    run = lock_run(db, step.run_id)
    locked_step = (
        lock_step(
            db,
            step.id,
            run_id=run.id,
            workspace_id=run.workspace_id,
        )
        if run is not None
        else None
    )
    if run is None or locked_step is None:
        raise ResearchError("research_state_conflict", "Research step is not queued.", 409)
    return _lease_locked_step(
        db,
        run,
        locked_step,
        worker_instance_id=worker_instance_id,
        lease_seconds=lease_seconds,
        now=now,
    )


def claim_next_research_step(
    db: Session,
    *,
    worker_instance_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
    excluded_run_ids: frozenset[str] = frozenset(),
) -> ResearchStepLease | None:
    claimed_at = now or datetime.now(UTC)
    eligible = (
        ResearchStep.status == "queued",
        ResearchStep.run_id == ResearchRun.id,
        ResearchStep.step_kind.in_(WORKER_EXECUTABLE_STEP_KINDS),
    )
    step_order = (ResearchStep.queued_at, ResearchStep.created_at, ResearchStep.id)
    first_queued_at = (
        select(ResearchStep.queued_at).where(*eligible).order_by(*step_order).limit(1).scalar_subquery()
    )
    first_created_at = (
        select(ResearchStep.created_at).where(*eligible).order_by(*step_order).limit(1).scalar_subquery()
    )
    first_step_id = (
        select(ResearchStep.id).where(*eligible).order_by(*step_order).limit(1).scalar_subquery()
    )
    with db.no_autoflush:
        run = db.scalar(
            select(ResearchRun)
            .where(
                ResearchRun.status.in_(("planning", "queued", "running")),
                ResearchRun.id.not_in(excluded_run_ids),
                exists(select(ResearchStep.id).where(*eligible)),
            )
            .order_by(first_queued_at, first_created_at, first_step_id, ResearchRun.id)
            .with_for_update(of=ResearchRun, skip_locked=True)
            .execution_options(populate_existing=True)
            .limit(1)
        )
    if run is None:
        return None
    snapshot = (
        db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
        if run.approved_execution_snapshot_id is not None
        else None
    )
    cap_full = False
    if snapshot is not None:
        if snapshot.max_parallel_researchers <= 0:
            raise ResearchError(
                "research_state_conflict",
                "Research execution snapshot has an invalid researcher concurrency cap.",
                409,
            )
        active_researchers = db.scalar(
            select(func.count(ResearchStepAttempt.id))
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run.id,
                ResearchStep.step_kind == "researcher",
                ResearchStepAttempt.status == "running",
                ResearchStepAttempt.lease_expires_at > func.now(),
            )
        ) or 0
        cap_full = active_researchers >= snapshot.max_parallel_researchers
    with db.no_autoflush:
        step = db.scalar(
            select(ResearchStep)
            .where(
                ResearchStep.run_id == run.id,
                ResearchStep.status == "queued",
                ResearchStep.step_kind.in_(WORKER_EXECUTABLE_STEP_KINDS),
                *(
                    (ResearchStep.step_kind != "researcher",)
                    if cap_full
                    else ()
                ),
            )
            .order_by(*step_order)
            .with_for_update(of=ResearchStep, skip_locked=True)
            .execution_options(populate_existing=True)
            .limit(1)
        )
    if step is None:
        if cap_full:
            raise ResearchAdmissionDeferred(run.id)
        return None
    return _lease_locked_step(
        db,
        run,
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
    with db.no_autoflush:
        locator = db.execute(
            select(ResearchStep.id, ResearchStep.step_kind).where(
                ResearchStep.run_id == run_id,
                ResearchStep.step_key == step_key,
                branch_predicate,
            )
        ).one_or_none()
    if locator is None:
        raise ResearchError("research_resource_not_found", "Research step not found.", 404)
    step_id, step_kind = locator
    if step_kind not in WORKER_EXECUTABLE_STEP_KINDS:
        raise ResearchError(
            "research_state_conflict",
            "Research step is not Worker-executable.",
            409,
        )
    run = lock_run(db, run_id)
    step = (
        lock_step(
            db,
            step_id,
            run_id=run.id,
            workspace_id=run.workspace_id,
        )
        if run is not None
        else None
    )
    if run is None or step is None:
        raise ResearchError("research_state_conflict", "Research step is not queued.", 409)
    return _lease_locked_step(
        db,
        run,
        step,
        worker_instance_id=worker_instance_id,
        lease_seconds=lease_seconds,
        now=now or datetime.now(UTC),
    )


def _locked_attempt_chain(
    db: Session,
    attempt_id: str,
) -> tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]:
    """Locate parent ids, then lock and refresh Run -> Step -> Attempt."""
    return lock_attempt_chain(db, attempt_id)


def _locked_attempt(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    now: datetime,
    locked_chain: Callable[[Session, str], tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]] | None = None,
) -> tuple[ResearchRun, ResearchStep, ResearchStepAttempt]:
    chain = locked_chain or _locked_attempt_chain
    run, step, attempt = chain(db, attempt_id)
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
    db.flush()
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
    locator = locate_attempt(db, attempt_id)
    with db.no_autoflush:
        dependent_ids = (
            tuple(
                db.scalars(
                    select(ResearchStepDependency.step_id).where(
                        ResearchStepDependency.depends_on_step_id == locator.step_id
                    )
                ).all()
            )
            if locator is not None
            else ()
        )

    def completion_chain(session: Session, located_attempt_id: str):
        return lock_attempt_chain_with_steps(
            session,
            located_attempt_id,
            related_step_ids=dependent_ids,
        )

    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=finished_at,
        locked_chain=completion_chain,
    )
    current_dependent_ids = tuple(
        db.scalars(
            select(ResearchStepDependency.step_id).where(
                ResearchStepDependency.depends_on_step_id == step.id
            )
        ).all()
    )
    if set(current_dependent_ids) != set(dependent_ids):
        raise ResearchError("research_state_conflict", "Research completion dependency chain changed.", 409)
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
        db.flush()
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
            .with_for_update(of=ResearchBudgetLedger)
            .execution_options(populate_existing=True)
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
        .with_for_update(of=ResearchBudgetLedger)
        .execution_options(populate_existing=True)
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
    locked_chain: Callable[[Session, str], tuple[ResearchRun | None, ResearchStep | None, ResearchStepAttempt | None]] | None = None,
) -> tuple[ResearchRun, ResearchStep, ResearchStepAttempt]:
    chain = locked_chain or _locked_attempt_chain
    run, step, attempt = chain(db, attempt_id)
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
