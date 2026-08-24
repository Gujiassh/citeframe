from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator

from ai_pdf_api.models import ResearchStepAttempt, ResearchStepDependency
from ai_pdf_api.services.research.research_worker import (
    begin_tool_call,
    claim_next_research_step,
    claim_specific_research_step,
    complete_research_step,
    heartbeat_research_step,
    reclaim_expired_research_steps,
    reserve_provider_call,
)
from citeframe_research_persistence.cancellation import cancel_research_run_transition
from citeframe_research_persistence.retry import retry_research_step_transition
from research_worker_test_support import add_step, lease_default_step, sha256
from sqlalchemy import event
from sqlalchemy.orm import Session


@contextmanager
def _executed_lock_entities(session: Session) -> Iterator[list[str]]:
    """Record mapped entities from lock queries that are actually executed."""
    locked: list[str] = []

    def observe(execute_state):
        statement = execute_state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            descriptions = getattr(statement, "column_descriptions", ())
            entity = descriptions[0].get("entity") if descriptions else None
            locked.append(getattr(entity, "__name__", str(entity)))
        return execute_state.invoke_statement()

    event.listen(session, "do_orm_execute", observe, retval=True)
    try:
        yield locked
    finally:
        event.remove(session, "do_orm_execute", observe)


def test_claim_executes_run_lock_before_step_lock(research_worker_db) -> None:
    fixture = research_worker_db
    add_step(
        fixture,
        step_key="older-join",
        step_kind="join",
        queued_at=fixture.now - timedelta(seconds=1),
    )

    with _executed_lock_entities(fixture.db) as locked:
        lease = claim_next_research_step(
            fixture.db,
            worker_instance_id="r0-claim",
            now=fixture.now,
        )

    assert lease is not None
    assert locked == ["ResearchRun", "ResearchStep"]


def test_attempt_paths_execute_run_step_attempt_order(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)

    with _executed_lock_entities(fixture.db) as locked:
        heartbeat_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            now=fixture.now + timedelta(seconds=1),
        )

    assert locked == ["ResearchRun", "ResearchStep", "ResearchStepAttempt"]


def test_completion_prelocks_dependent_steps_before_attempt(research_worker_db) -> None:
    fixture = research_worker_db
    dependent = add_step(fixture, step_key="dependent-join", step_kind="join")
    dependent.status = "pending"
    fixture.db.add(
        ResearchStepDependency(
            step_id=dependent.id,
            depends_on_step_id=fixture.step.id,
        )
    )
    fixture.db.commit()
    lease = lease_default_step(fixture)

    with _executed_lock_entities(fixture.db) as locked:
        complete_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=sha256("r0-complete"),
            now=fixture.now + timedelta(seconds=1),
        )

    assert locked[0] == "ResearchRun"
    assert locked[1:-1] == ["ResearchStep", "ResearchStep"]
    assert locked[-1] == "ResearchStepAttempt"


def test_cancel_executes_run_then_stable_step_locks(research_worker_db) -> None:
    fixture = research_worker_db
    add_step(fixture, step_key="cancel-second", step_kind="join")

    with _executed_lock_entities(fixture.db) as locked:
        cancel_research_run_transition(
            fixture.db,
            workspace_id=fixture.run.workspace_id,
            actor_user_id=fixture.run.created_by_user_id,
            actor_role="member",
            run_id=fixture.run.id,
            expected_state_version=fixture.run.state_version,
            reason_code="user_requested",
            now=fixture.now + timedelta(seconds=1),
        )

    assert locked == ["ResearchRun", "ResearchStep", "HumanDecision"]


def test_retry_executes_run_step_attempt_ledger_order(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.status = "failed"
    attempt.error_code = "provider_temporarily_unavailable"
    attempt.finished_at = fixture.now + timedelta(seconds=1)
    attempt.lease_expires_at = None
    fixture.step.status = "failed"
    fixture.step.error_code = "provider_temporarily_unavailable"
    fixture.run.status = "awaiting_retry"
    fixture.db.commit()

    with _executed_lock_entities(fixture.db) as locked:
        retry_research_step_transition(
            fixture.db,
            workspace_id=fixture.run.workspace_id,
            actor_user_id=fixture.run.created_by_user_id,
            run_id=fixture.run.id,
            step_id=fixture.step.id,
            failed_attempt=attempt.attempt_number,
            expected_run_state_version=fixture.run.state_version,
            expected_step_state_version=fixture.step.state_version,
            now=fixture.now + timedelta(seconds=2),
        )

    assert locked == [
        "ResearchRun",
        "ResearchStep",
        "ResearchStepAttempt",
        "ResearchBudgetLedger",
    ]


def test_reclaim_locks_all_calls_before_the_shared_ledger(research_worker_db) -> None:
    fixture = research_worker_db
    lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="r0-reclaim",
        lease_seconds=5,
        now=fixture.now,
    )
    reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="r0-provider",
        request_sha256=sha256("r0-provider"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=10,
        reserved_output_tokens=10,
        now=fixture.now + timedelta(seconds=1),
    )
    begin_tool_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        tool_call_key="r0-tool",
        tool_name="evidence.search",
        request_sha256=sha256("r0-tool"),
        now=fixture.now + timedelta(seconds=2),
    )

    with _executed_lock_entities(fixture.db) as locked:
        count = reclaim_expired_research_steps(
            fixture.db,
            now=fixture.now + timedelta(seconds=6),
        )

    assert count == 1
    assert locked == [
        "ResearchRun",
        "ResearchStep",
        "ResearchStepAttempt",
        "ResearchProviderCall",
        "ResearchToolCall",
        "ResearchBudgetLedger",
    ]
