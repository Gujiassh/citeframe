from __future__ import annotations
from collections.abc import Callable
from datetime import UTC, datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from citeframe_persistence.models import ResearchBudgetLedger, ResearchEvidenceHandle, ResearchExecutionSnapshot, ResearchRun, ResearchStep, ResearchStepAttempt, ResearchToolCall
from .errors import ResearchError
from .lease import _active_attempt_chain, _ledger_and_limits, _locked_attempt_chain
from .types import ToolCallReservation

def begin_tool_call(
    db: Session,
    *,
    attempt_id: str,
    tool_call_key: str,
    tool_name: str,
    request_sha256: str,
    now: datetime | None = None,
) -> ToolCallReservation:
    started_at = now or datetime.now(UTC)
    _run, step, attempt = _active_attempt_chain(db, attempt_id, now=started_at)
    if step.execution_snapshot_id is None or step.step_kind != "researcher":
        raise ResearchError("research_state_conflict", "Research tool attempt is not running.", 409)
    if tool_name not in {"evidence.search", "evidence.load"} or not tool_call_key or len(tool_call_key) > 160:
        raise ValueError("invalid Research tool call")
    ledger, _max_calls, max_tools, _max_input, _max_output, _max_cost = _ledger_and_limits(db, step)
    if ledger.actual_tool_calls + ledger.reserved_tool_calls + 1 > max_tools:
        raise ResearchError("research_budget_limit", "Research tool budget is exhausted.", 429)
    call_attempt = (
        db.scalar(
            select(func.coalesce(func.max(ResearchToolCall.call_attempt_number), 0)).where(
                ResearchToolCall.step_id == step.id,
                ResearchToolCall.tool_call_key == tool_call_key,
            )
        )
        or 0
    ) + 1
    max_call_order = db.scalar(
        select(func.max(ResearchToolCall.call_order)).where(
            ResearchToolCall.attempt_id == attempt.id
        )
    )
    call_order = (max_call_order if max_call_order is not None else -1) + 1
    call = ResearchToolCall(
        workspace_id=step.workspace_id,
        run_id=step.run_id,
        execution_snapshot_id=step.execution_snapshot_id,
        step_id=step.id,
        attempt_id=attempt.id,
        tool_call_key=tool_call_key,
        call_attempt_number=call_attempt,
        call_order=call_order,
        tool_name=tool_name,
        tool_version=1,
        status="running",
        request_sha256=request_sha256,
        created_at=started_at,
        started_at=started_at,
    )
    db.add(call)
    ledger.reserved_tool_calls += 1
    ledger.state_version += 1
    ledger.updated_at = started_at
    db.flush()
    return ToolCallReservation(tool_call_id=call.id, budget_ledger_id=ledger.id)


ToolResultCallback = Callable[[Session, ResearchToolCall], int]


def _tool_call_chain(
    db: Session,
    tool_call_id: str,
) -> tuple[ResearchToolCall, ResearchBudgetLedger, ResearchStepAttempt, ResearchStep, ResearchRun]:
    # Locate without locks, then refresh the complete aggregate chain in R0 order.
    with db.no_autoflush:
        locator = db.execute(
            select(
                ResearchToolCall.run_id,
                ResearchToolCall.step_id,
                ResearchToolCall.attempt_id,
                ResearchToolCall.execution_snapshot_id,
            ).where(ResearchToolCall.id == tool_call_id)
        ).one_or_none()
    if locator is None:
        raise ResearchError("research_state_conflict", "Research tool call chain is invalid.", 409)
    run, step, attempt = _locked_attempt_chain(db, locator.attempt_id)
    call = db.scalar(
        select(ResearchToolCall)
        .where(
            ResearchToolCall.id == tool_call_id,
            ResearchToolCall.run_id == locator.run_id,
            ResearchToolCall.step_id == locator.step_id,
            ResearchToolCall.attempt_id == locator.attempt_id,
            ResearchToolCall.execution_snapshot_id == locator.execution_snapshot_id,
        )
        .with_for_update(of=ResearchToolCall)
        .execution_options(populate_existing=True)
    )
    ledger = (
        db.scalar(
            select(ResearchBudgetLedger)
            .where(ResearchBudgetLedger.execution_snapshot_id == call.execution_snapshot_id)
            .with_for_update(of=ResearchBudgetLedger)
            .execution_options(populate_existing=True)
        )
        if call
        else None
    )
    snapshot = db.get(ResearchExecutionSnapshot, call.execution_snapshot_id) if call else None
    if (
        call is None
        or ledger is None
        or attempt is None
        or step is None
        or run is None
        or snapshot is None
        or locator.run_id != run.id
        or locator.step_id != step.id
        or locator.attempt_id != attempt.id
        or locator.execution_snapshot_id != snapshot.id
        or attempt.step_id != step.id
        or call.attempt_id != attempt.id
        or call.step_id != step.id
        or step.run_id != run.id
        or call.run_id != run.id
        or snapshot.run_id != run.id
        or step.execution_snapshot_id != snapshot.id
        or call.workspace_id != run.workspace_id
        or step.workspace_id != run.workspace_id
        or attempt.workspace_id != run.workspace_id
        or snapshot.workspace_id != run.workspace_id
        or ledger.workspace_id != run.workspace_id
        or ledger.run_id != run.id
    ):
        raise ResearchError("research_state_conflict", "Research tool call chain is invalid.", 409)
    return call, ledger, attempt, step, run


def complete_tool_call(
    db: Session,
    *,
    tool_call_id: str,
    status: str,
    complete: ToolResultCallback | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> None:
    if status not in {"succeeded", "failed", "cancelled", "abandoned"}:
        raise ValueError("invalid tool terminal status")
    call, ledger, attempt, _step, _run = _tool_call_chain(db, tool_call_id)
    if call.status not in {"requested", "running"}:
        raise ResearchError("research_state_conflict", "Research tool call cannot be completed.", 409)
    try:
        result_count = complete(db, call) if complete else 0
        call.status = status
        call.result_count = result_count
        call.error_code = error_code
        call.error_message = error_message
        call.finished_at = now or datetime.now(UTC)
        ledger.reserved_tool_calls -= 1
        ledger.actual_tool_calls += 1
        ledger.state_version += 1
        ledger.updated_at = call.finished_at
        attempt.tool_call_count += 1
        db.flush()
    except Exception:
        db.rollback()
        raise


def restore_evidence_handles(
    db: Session,
    *,
    run_id: str,
    execution_snapshot_id: str,
    owner_step_id: str,
) -> list[ResearchEvidenceHandle]:
    run = db.get(ResearchRun, run_id)
    snapshot = db.get(ResearchExecutionSnapshot, execution_snapshot_id)
    step = db.get(ResearchStep, owner_step_id)
    if (
        run is None
        or snapshot is None
        or step is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or step.run_id != run.id
        or step.workspace_id != run.workspace_id
        or step.execution_snapshot_id != snapshot.id
        or step.step_kind != "researcher"
    ):
        raise ResearchError("research_state_conflict", "Research Evidence handle chain is invalid.", 409)
    handles = list(
        db.scalars(
            select(ResearchEvidenceHandle)
            .where(
                ResearchEvidenceHandle.run_id == run_id,
                ResearchEvidenceHandle.execution_snapshot_id == execution_snapshot_id,
                ResearchEvidenceHandle.owner_step_id == owner_step_id,
            )
            .order_by(ResearchEvidenceHandle.created_at, ResearchEvidenceHandle.result_order)
        ).all()
    )
    if any(handle.workspace_id != run.workspace_id for handle in handles):
        raise ResearchError("research_state_conflict", "Research Evidence handle scope is invalid.", 409)
    return handles
