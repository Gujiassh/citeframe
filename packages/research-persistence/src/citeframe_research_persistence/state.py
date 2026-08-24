"""Neutral handler-control and expired-attempt recovery commands."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from citeframe_persistence.models import (
    ResearchBudgetLedger,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
)

from .errors import ResearchError
from .events import append_research_event
from .lease import complete_research_step
from .policy import add_optional_cost, subtract_optional_cost

def complete_control_step(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
) -> None:
    complete_research_step(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        output_sha256=hashlib.sha256(attempt_id.encode("utf-8")).hexdigest(),
    )


def reclaim_expired_research_steps(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    if not 1 <= limit <= 1000:
        raise ValueError("reclaim limit must be between 1 and 1000")
    reclaimed_at = now or datetime.now(UTC)
    attempts = list(
        db.scalars(
            select(ResearchStepAttempt)
            .where(
                ResearchStepAttempt.status == "running",
                ResearchStepAttempt.lease_expires_at <= reclaimed_at,
            )
            .order_by(ResearchStepAttempt.lease_expires_at, ResearchStepAttempt.id)
            .with_for_update(skip_locked=True)
            .limit(limit)
        ).all()
    )
    for attempt in attempts:
        step = db.scalar(select(ResearchStep).where(ResearchStep.id == attempt.step_id).with_for_update())
        run = (
            db.scalar(select(ResearchRun).where(ResearchRun.id == step.run_id).with_for_update())
            if step
            else None
        )
        if (
            step is None
            or run is None
            or step.status != "running"
            or attempt.workspace_id != step.workspace_id
            or step.workspace_id != run.workspace_id
        ):
            raise ResearchError("research_state_conflict", "Expired Research Attempt chain is invalid.", 409)
        provider_calls = list(
            db.scalars(
                select(ResearchProviderCall)
                .where(
                    ResearchProviderCall.attempt_id == attempt.id,
                    ResearchProviderCall.status.in_(("reserved", "sent")),
                )
                .with_for_update()
            ).all()
        )
        for call in provider_calls:
            ledger = db.scalar(
                select(ResearchBudgetLedger)
                .where(ResearchBudgetLedger.id == call.budget_ledger_id)
                .with_for_update()
            )
            if ledger is None or ledger.run_id != run.id or ledger.workspace_id != run.workspace_id:
                raise ResearchError("research_state_conflict", "Expired provider call chain is invalid.", 409)
            if call.status == "reserved":
                call.status = "cancelled"
                call.usage_final = True
                ledger.reserved_provider_calls -= 1
                ledger.reserved_input_tokens -= call.reserved_input_tokens
                ledger.reserved_output_tokens -= call.reserved_output_tokens
                ledger.reserved_cost_microunits = subtract_optional_cost(
                    ledger.reserved_cost_microunits,
                    call.reserved_cost_microunits,
                )
            else:
                call.status = "outcome_unknown"
                call.actual_input_tokens = call.reserved_input_tokens
                call.actual_output_tokens = call.reserved_output_tokens
                call.actual_cost_microunits = call.reserved_cost_microunits
                call.usage_source = "estimated"
                call.usage_final = False
                call.error_code = "provider_outcome_unknown"
                ledger.reserved_input_tokens -= call.reserved_input_tokens
                ledger.reserved_output_tokens -= call.reserved_output_tokens
                ledger.reserved_cost_microunits = subtract_optional_cost(
                    ledger.reserved_cost_microunits,
                    call.reserved_cost_microunits,
                )
                ledger.actual_input_tokens += call.reserved_input_tokens
                ledger.actual_output_tokens += call.reserved_output_tokens
                ledger.actual_cost_microunits = add_optional_cost(
                    ledger.actual_cost_microunits,
                    call.reserved_cost_microunits,
                )
                ledger.usage_final = False
                attempt.provider_call_count += 1
                attempt.input_tokens += call.reserved_input_tokens
                attempt.output_tokens += call.reserved_output_tokens
                attempt.cost_microunits = add_optional_cost(
                    attempt.cost_microunits,
                    call.reserved_cost_microunits,
                )
            call.finished_at = reclaimed_at
            ledger.state_version += 1
            ledger.updated_at = reclaimed_at
        tool_calls = list(
            db.scalars(
                select(ResearchToolCall)
                .where(
                    ResearchToolCall.attempt_id == attempt.id,
                    ResearchToolCall.status.in_(("requested", "running")),
                )
                .with_for_update()
            ).all()
        )
        for call in tool_calls:
            ledger = db.scalar(
                select(ResearchBudgetLedger)
                .where(ResearchBudgetLedger.execution_snapshot_id == call.execution_snapshot_id)
                .with_for_update()
            )
            if ledger is None or ledger.run_id != run.id or ledger.workspace_id != run.workspace_id:
                raise ResearchError("research_state_conflict", "Expired tool call chain is invalid.", 409)
            call.status = "abandoned"
            call.error_code = "lease_expired"
            call.error_message = "The owning Research Attempt lease expired."
            call.finished_at = reclaimed_at
            ledger.reserved_tool_calls -= 1
            ledger.actual_tool_calls += 1
            ledger.state_version += 1
            ledger.updated_at = reclaimed_at
            attempt.tool_call_count += 1
        attempt.status = "abandoned"
        attempt.error_code = "lease_expired"
        attempt.error_message = "Research Attempt lease expired."
        attempt.finished_at = reclaimed_at
        attempt.lease_expires_at = None
        step.status = "failed"
        step.state_version += 1
        step.error_code = "lease_expired"
        step.error_message = "Research Attempt lease expired."
        step.finished_at = reclaimed_at
        step.updated_at = reclaimed_at
        run.state_version += 1
        run.updated_at = reclaimed_at
        append_research_event(
            db,
            run,
            event_type="attempt_abandoned",
            dedupe_key=f"attempt-abandoned:{attempt.id}",
            step_id=step.id,
            attempt_id=attempt.id,
            data={
                "stepId": step.id,
                "attemptId": attempt.id,
                "attemptNumber": attempt.attempt_number,
                "reasonCode": "lease_expired",
                "stepStateVersion": step.state_version,
                "runStateVersion": run.state_version,
            },
            now=reclaimed_at,
        )
        if run.status == "cancel_requested":
            step.status = "cancelled"
        elif step.current_attempt_number < step.max_attempts_snapshot:
            step.status = "queued"
            step.state_version += 1
            step.queued_at = reclaimed_at
            step.finished_at = None
            run.state_version += 1
            append_research_event(
                db,
                run,
                event_type="step_queued",
                dedupe_key=f"step-queued:{step.id}:{step.current_attempt_number}",
                step_id=step.id,
                data={
                    "stepId": step.id,
                    "stepKind": step.step_kind,
                    "branchKey": step.branch_key,
                    "attemptNumber": step.current_attempt_number,
                    "stepStateVersion": step.state_version,
                    "runStateVersion": run.state_version,
                },
                now=reclaimed_at,
            )
        else:
            run.status = "awaiting_retry"
            run.failure_code = "lease_expired"
            run.failure_message = "A Research Step exhausted its automatic retry allowance."
    if attempts:
        db.flush()
        cancel_run_ids = {db.get(ResearchStep, attempt.step_id).run_id for attempt in attempts}
        for run_id in cancel_run_ids:
            run = db.get(ResearchRun, run_id)
            if run is None or run.status != "cancel_requested":
                continue
            active_count = db.scalar(
                select(func.count())
                .select_from(ResearchStepAttempt)
                .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                .where(ResearchStep.run_id == run.id, ResearchStepAttempt.status == "running")
            ) or 0
            if active_count == 0:
                run.status = "cancelled"
                run.finished_at = reclaimed_at
                run.state_version += 1
                append_research_event(
                    db,
                    run,
                    event_type="run_cancelled",
                    dedupe_key=f"run-cancelled:{run.id}",
                    data={
                        "status": "cancelled",
                        "reasonCode": run.cancel_reason_code or "user_requested",
                        "runStateVersion": run.state_version,
                    },
                    now=reclaimed_at,
                )
        db.flush()
    return len(attempts)
