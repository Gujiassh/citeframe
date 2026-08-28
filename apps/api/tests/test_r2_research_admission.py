from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ai_pdf_api.models import ResearchEvent, ResearchRun, ResearchStep, ResearchStepAttempt
from ai_pdf_api.services.research.research_idempotency import ResearchError
from citeframe_research_persistence.lease import (
    claim_next_research_step,
    claim_specific_research_step,
)
from research_worker_test_support import add_execution_chain, add_step, assert_research_error, sha256
from sqlalchemy import func, select


def _add_researcher(
    fixture,
    *,
    run: ResearchRun,
    snapshot_id: str,
    step_key: str,
    branch_key: str,
    queued_at: datetime,
) -> ResearchStep:
    step = ResearchStep(
        id=str(uuid4()),
        workspace_id=run.workspace_id,
        run_id=run.id,
        execution_snapshot_id=snapshot_id,
        step_key=step_key,
        step_kind="researcher",
        branch_key=branch_key,
        status="queued",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=0,
        input_sha256=sha256(f"{step_key}-input"),
        queued_at=queued_at,
        created_at=queued_at,
        updated_at=queued_at,
    )
    fixture.db.add(step)
    fixture.db.commit()
    return step


def _row_snapshot(row: object) -> tuple[tuple[str, object], ...]:
    table = getattr(row, "__table__")
    return tuple((column.name, getattr(row, column.name)) for column in table.columns)


def _claim_first_researcher(fixture, *, lease_seconds: int = 3600):
    claimed_at = datetime.now(UTC)
    lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="r2-first",
        lease_seconds=lease_seconds,
        now=claimed_at,
    )
    fixture.db.commit()
    return lease


def test_specific_researcher_cap_uses_database_time_and_mutates_nothing(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.max_parallel_researchers = 1
    second = add_step(
        fixture,
        step_key="researcher:branch-b",
        step_kind="researcher",
        branch_key="branch-b",
    )
    first_lease = _claim_first_researcher(fixture)
    first_attempt = fixture.db.get(ResearchStepAttempt, first_lease.attempt_id)
    assert first_attempt is not None
    assert first_attempt.lease_expires_at is not None
    assert first_attempt.lease_expires_at.replace(tzinfo=UTC) > datetime.now(UTC)

    fixture.db.refresh(fixture.run)
    fixture.db.refresh(second)
    before = {
        "run": _row_snapshot(fixture.run),
        "step": _row_snapshot(second),
        "attempts": fixture.db.scalar(select(func.count(ResearchStepAttempt.id))),
        "events": fixture.db.scalar(select(func.count(ResearchEvent.id))),
    }

    with pytest.raises(ResearchError) as error:
        claim_specific_research_step(
            fixture.db,
            run_id=fixture.run.id,
            step_key=second.step_key,
            branch_key=second.branch_key,
            worker_instance_id="r2-specific-full",
            now=datetime(2099, 1, 1, tzinfo=UTC),
        )
    assert_research_error(error, "research_state_conflict", 409)
    assert error.value.message == "Researcher admission is full."
    fixture.db.rollback()

    persisted_run = fixture.db.get(ResearchRun, fixture.run.id)
    persisted_step = fixture.db.get(ResearchStep, second.id)
    assert persisted_run is not None and persisted_step is not None
    after = {
        "run": _row_snapshot(persisted_run),
        "step": _row_snapshot(persisted_step),
        "attempts": fixture.db.scalar(select(func.count(ResearchStepAttempt.id))),
        "events": fixture.db.scalar(select(func.count(ResearchEvent.id))),
    }
    assert after == before


def test_expired_researcher_attempt_does_not_consume_slot(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.max_parallel_researchers = 1
    second = add_step(
        fixture,
        step_key="researcher:branch-b",
        step_kind="researcher",
        branch_key="branch-b",
    )
    first_lease = _claim_first_researcher(fixture)
    first_attempt = fixture.db.get(ResearchStepAttempt, first_lease.attempt_id)
    assert first_attempt is not None
    first_attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    fixture.db.commit()

    lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=second.step_key,
        branch_key=second.branch_key,
        worker_instance_id="r2-expired-slot",
        now=fixture.now,
    )
    fixture.db.commit()

    assert lease.step_id == second.id


def test_claim_next_rolls_back_cap_full_run_and_claims_next_eligible_run(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.max_parallel_researchers = 1
    blocked = _add_researcher(
        fixture,
        run=fixture.run,
        snapshot_id=fixture.snapshot.id,
        step_key="researcher:blocked",
        branch_key="blocked",
        queued_at=fixture.now - timedelta(seconds=2),
    )
    _claim_first_researcher(fixture)

    eligible_run, eligible_snapshot = add_execution_chain(fixture)
    eligible = _add_researcher(
        fixture,
        run=eligible_run,
        snapshot_id=eligible_snapshot.id,
        step_key="researcher:eligible",
        branch_key="eligible",
        queued_at=fixture.now - timedelta(seconds=1),
    )

    fixture.db.refresh(fixture.run)
    fixture.db.refresh(blocked)
    blocked_before = {
        "run": _row_snapshot(fixture.run),
        "step": _row_snapshot(blocked),
        "attempt_ids": tuple(
            fixture.db.scalars(
                select(ResearchStepAttempt.id)
                .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                .where(ResearchStep.run_id == fixture.run.id)
                .order_by(ResearchStepAttempt.id)
            ).all()
        ),
        "event_ids": tuple(
            fixture.db.scalars(
                select(ResearchEvent.id)
                .where(ResearchEvent.run_id == fixture.run.id)
                .order_by(ResearchEvent.seq)
            ).all()
        ),
    }

    lease = claim_next_research_step(
        fixture.db,
        worker_instance_id="r2-next-eligible",
        now=datetime.now(UTC),
    )
    fixture.db.commit()

    assert lease is not None
    assert lease.run_id == eligible_run.id
    assert lease.step_id == eligible.id
    persisted_run = fixture.db.get(ResearchRun, fixture.run.id)
    persisted_blocked = fixture.db.get(ResearchStep, blocked.id)
    assert persisted_run is not None and persisted_blocked is not None
    blocked_after = {
        "run": _row_snapshot(persisted_run),
        "step": _row_snapshot(persisted_blocked),
        "attempt_ids": tuple(
            fixture.db.scalars(
                select(ResearchStepAttempt.id)
                .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                .where(ResearchStep.run_id == fixture.run.id)
                .order_by(ResearchStepAttempt.id)
            ).all()
        ),
        "event_ids": tuple(
            fixture.db.scalars(
                select(ResearchEvent.id)
                .where(ResearchEvent.run_id == fixture.run.id)
                .order_by(ResearchEvent.seq)
            ).all()
        ),
    }
    assert blocked_after == blocked_before


def test_non_researcher_claim_is_unchanged_when_researcher_cap_is_full(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.max_parallel_researchers = 1
    join = add_step(
        fixture,
        step_key="join",
        step_kind="join",
        queued_at=fixture.now - timedelta(seconds=1),
    )
    _claim_first_researcher(fixture)

    lease = claim_next_research_step(
        fixture.db,
        worker_instance_id="r2-join",
        now=datetime.now(UTC),
    )
    fixture.db.commit()

    assert lease is not None
    assert lease.step_id == join.id
    assert lease.step_kind == "join"
