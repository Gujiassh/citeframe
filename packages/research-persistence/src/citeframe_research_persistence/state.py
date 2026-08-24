"""Neutral handler-control and expired-attempt recovery commands."""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_
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
from .locks import locate_attempt, lock_attempt, lock_run, lock_step
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



def _expired_attempt_candidate_ids(
    db: Session,
    *,
    reclaimed_at: datetime,
    batch_size: int,
) -> Iterator[str]:
    """Yield the global expiry/id order while allowing locked Runs to be skipped."""
    cursor: tuple[datetime, str] | None = None
    while True:
        query = select(
            ResearchStepAttempt.id,
            ResearchStepAttempt.lease_expires_at,
        ).where(
            ResearchStepAttempt.status == "running",
            ResearchStepAttempt.lease_expires_at <= reclaimed_at,
        )
        if cursor is not None:
            query = query.where(
                tuple_(
                    ResearchStepAttempt.lease_expires_at,
                    ResearchStepAttempt.id,
                ) > tuple_(*cursor)
            )
        with db.no_autoflush:
            rows = list(
                db.execute(
                    query
                    .order_by(ResearchStepAttempt.lease_expires_at, ResearchStepAttempt.id)
                    .limit(batch_size)
                ).all()
            )
        if not rows:
            return
        for row in rows:
            yield row.id
        last = rows[-1]
        cursor = (last.lease_expires_at, last.id)
        if len(rows) < batch_size:
            return

def reclaim_expired_research_steps(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    if not 1 <= limit <= 1000:
        raise ValueError("reclaim limit must be between 1 and 1000")
    reclaimed_at = now or datetime.now(UTC)
    candidate_ids = _expired_attempt_candidate_ids(
        db,
        reclaimed_at=reclaimed_at,
        batch_size=max(100, limit),
    )
    reclaimed: list[tuple[ResearchRun, ResearchStep, ResearchStepAttempt]] = []
    for attempt_id in candidate_ids:
        if len(reclaimed) >= limit:
            break
        locator = locate_attempt(db, attempt_id)
        if locator is None:
            raise ResearchError("research_state_conflict", "Expired Research Attempt chain is invalid.", 409)
        run = lock_run(db, locator.run_id, skip_locked=True)
        if run is None:
            continue
        step = lock_step(
            db,
            locator.step_id,
            run_id=run.id,
            workspace_id=run.workspace_id,
            skip_locked=True,
        )
        attempt = (
            lock_attempt(
                db,
                attempt_id,
                step_id=step.id,
                workspace_id=run.workspace_id,
                skip_locked=True,
            )
            if step is not None
            else None
        )
        expires_at = attempt.lease_expires_at if attempt is not None else None
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            step is None
            or attempt is None
            or locator.run_id != run.id
            or locator.step_id != step.id
            or step.status != "running"
            or attempt.status != "running"
            or expires_at is None
            or expires_at > reclaimed_at
            or attempt.workspace_id != step.workspace_id
            or step.workspace_id != run.workspace_id
        ):
            raise ResearchError("research_state_conflict", "Expired Research Attempt chain is invalid.", 409)

        provider_locators = {
            row.id: row
            for row in db.execute(
                select(
                    ResearchProviderCall.id,
                    ResearchProviderCall.run_id,
                    ResearchProviderCall.step_id,
                    ResearchProviderCall.attempt_id,
                    ResearchProviderCall.budget_ledger_id,
                ).where(
                    ResearchProviderCall.attempt_id == attempt.id,
                    ResearchProviderCall.status.in_(("reserved", "sent")),
                )
            ).all()
        }
        tool_locators = {
            row.id: row
            for row in db.execute(
                select(
                    ResearchToolCall.id,
                    ResearchToolCall.run_id,
                    ResearchToolCall.step_id,
                    ResearchToolCall.attempt_id,
                    ResearchToolCall.execution_snapshot_id,
                ).where(
                    ResearchToolCall.attempt_id == attempt.id,
                    ResearchToolCall.status.in_(("requested", "running")),
                )
            ).all()
        }
        provider_calls = list(
            db.scalars(
                select(ResearchProviderCall)
                .where(
                    ResearchProviderCall.id.in_(provider_locators),
                    ResearchProviderCall.run_id == run.id,
                    ResearchProviderCall.step_id == step.id,
                    ResearchProviderCall.attempt_id == attempt.id,
                )
                .order_by(ResearchProviderCall.id)
                .with_for_update(of=ResearchProviderCall)
                .execution_options(populate_existing=True)
            ).all()
        ) if provider_locators else []
        tool_calls = list(
            db.scalars(
                select(ResearchToolCall)
                .where(
                    ResearchToolCall.id.in_(tool_locators),
                    ResearchToolCall.run_id == run.id,
                    ResearchToolCall.step_id == step.id,
                    ResearchToolCall.attempt_id == attempt.id,
                    ResearchToolCall.execution_snapshot_id == step.execution_snapshot_id,
                )
                .order_by(ResearchToolCall.id)
                .with_for_update(of=ResearchToolCall)
                .execution_options(populate_existing=True)
            ).all()
        ) if tool_locators else []

        if len(provider_calls) != len(provider_locators) or len(tool_calls) != len(tool_locators):
            raise ResearchError("research_state_conflict", "Expired call chain is invalid.", 409)
        if any(
            provider_locators[call.id].budget_ledger_id != call.budget_ledger_id
            for call in provider_calls
        ) or any(
            tool_locators[call.id].execution_snapshot_id != call.execution_snapshot_id
            for call in tool_calls
        ):
            raise ResearchError("research_state_conflict", "Expired call locator changed.", 409)

        provider_ledger_ids = {call.budget_ledger_id for call in provider_calls}
        tool_snapshot_ids = {call.execution_snapshot_id for call in tool_calls}
        ledger_query = select(ResearchBudgetLedger).where(
            (ResearchBudgetLedger.id.in_(provider_ledger_ids))
            | (ResearchBudgetLedger.execution_snapshot_id.in_(tool_snapshot_ids))
        )
        ledgers = list(
            db.scalars(
                ledger_query
                .order_by(ResearchBudgetLedger.id)
                .with_for_update(of=ResearchBudgetLedger)
                .execution_options(populate_existing=True)
            ).all()
        ) if provider_ledger_ids or tool_snapshot_ids else []
        ledger_by_id = {ledger.id: ledger for ledger in ledgers}
        ledger_by_snapshot = {ledger.execution_snapshot_id: ledger for ledger in ledgers}

        for call in provider_calls:
            hint = provider_locators[call.id]
            ledger = ledger_by_id.get(call.budget_ledger_id)
            if (
                ledger is None
                or hint.run_id != run.id
                or hint.step_id != step.id
                or hint.attempt_id != attempt.id
                or hint.budget_ledger_id != ledger.id
                or call.run_id != run.id
                or call.step_id != step.id
                or call.attempt_id != attempt.id
                or call.workspace_id != run.workspace_id
                or ledger.run_id != run.id
                or ledger.workspace_id != run.workspace_id
            ):
                raise ResearchError("research_state_conflict", "Expired provider call chain is invalid.", 409)
        for call in tool_calls:
            hint = tool_locators[call.id]
            ledger = ledger_by_snapshot.get(call.execution_snapshot_id)
            if (
                ledger is None
                or hint.run_id != run.id
                or hint.step_id != step.id
                or hint.attempt_id != attempt.id
                or hint.execution_snapshot_id != call.execution_snapshot_id
                or call.run_id != run.id
                or call.step_id != step.id
                or call.attempt_id != attempt.id
                or call.workspace_id != run.workspace_id
                or ledger.run_id != run.id
                or ledger.workspace_id != run.workspace_id
            ):
                raise ResearchError("research_state_conflict", "Expired tool call chain is invalid.", 409)

        for call in provider_calls:
            ledger = ledger_by_id[call.budget_ledger_id]
            if call.status == "reserved":
                call.status = "cancelled"
                call.usage_final = True
                ledger.reserved_provider_calls -= 1
                ledger.reserved_input_tokens -= call.reserved_input_tokens
                ledger.reserved_output_tokens -= call.reserved_output_tokens
                ledger.reserved_cost_microunits = subtract_optional_cost(
                    ledger.reserved_cost_microunits, call.reserved_cost_microunits
                )
            elif call.status == "sent":
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
                    ledger.reserved_cost_microunits, call.reserved_cost_microunits
                )
                ledger.actual_input_tokens += call.reserved_input_tokens
                ledger.actual_output_tokens += call.reserved_output_tokens
                ledger.actual_cost_microunits = add_optional_cost(
                    ledger.actual_cost_microunits, call.reserved_cost_microunits
                )
                ledger.usage_final = False
                attempt.provider_call_count += 1
                attempt.input_tokens += call.reserved_input_tokens
                attempt.output_tokens += call.reserved_output_tokens
                attempt.cost_microunits = add_optional_cost(
                    attempt.cost_microunits, call.reserved_cost_microunits
                )
            else:
                raise ResearchError("research_state_conflict", "Expired provider call chain is invalid.", 409)
            call.finished_at = reclaimed_at
            ledger.state_version += 1
            ledger.updated_at = reclaimed_at
        for call in tool_calls:
            if call.status not in {"requested", "running"}:
                raise ResearchError("research_state_conflict", "Expired tool call chain is invalid.", 409)
            ledger = ledger_by_snapshot[call.execution_snapshot_id]
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
        reclaimed.append((run, step, attempt))

    if reclaimed:
        db.flush()
        cancel_runs = {run.id: run for run, _step, _attempt in reclaimed}
        for run in cancel_runs.values():
            if run.status != "cancel_requested":
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
    return len(reclaimed)
