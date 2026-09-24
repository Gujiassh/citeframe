"""A recovered step exposes current-attempt state without rewriting its history."""

from datetime import timedelta

from ai_pdf_api.models import ResearchEvent, ResearchStepAttempt
from ai_pdf_api.services.research.research_worker import (
    claim_specific_research_step,
    complete_research_step,
    reclaim_expired_research_steps,
)
from research_worker_test_support import lease_default_step, sha256
from sqlalchemy import select


def test_recovered_attempt_clears_only_step_error(research_worker_db):
    fixture = research_worker_db
    first = lease_default_step(fixture)
    expired = fixture.now + timedelta(seconds=61)
    assert reclaim_expired_research_steps(fixture.db, now=expired) == 1
    fixture.db.commit()
    attempt = fixture.db.get(ResearchStepAttempt, first.attempt_id)
    history = {
        column.name: getattr(attempt, column.name)
        for column in attempt.__table__.columns
    }
    abandoned = fixture.db.scalar(
        select(ResearchEvent).where(
            ResearchEvent.attempt_id == first.attempt_id,
            ResearchEvent.event_type == "attempt_abandoned",
        )
    )
    payload = dict(abandoned.payload_json)
    assert fixture.step.error_code == "lease_expired"
    second = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="restarted-worker",
        lease_seconds=60,
        now=expired,
    )
    assert second.attempt_number == 2
    assert fixture.step.error_code is None and fixture.step.error_message is None
    complete_research_step(
        fixture.db,
        attempt_id=second.attempt_id,
        lease_token=second.lease_token,
        output_sha256=sha256("recovered output"),
        now=expired + timedelta(seconds=1),
    )
    fixture.db.commit()
    fixture.db.refresh(attempt)
    assert fixture.step.status == "succeeded"
    assert fixture.step.error_code is None and fixture.step.error_message is None
    assert {
        column.name: getattr(attempt, column.name)
        for column in attempt.__table__.columns
    } == history
    fixture.db.refresh(abandoned)
    assert (
        abandoned.payload_json == payload and payload["reasonCode"] == "lease_expired"
    )


def test_rejected_lease_keeps_error_and_new_failure_replaces_it(research_worker_db):
    import pytest
    from ai_pdf_api.services.research.research_idempotency import ResearchError
    from ai_pdf_api.services.research.research_worker import fail_research_step

    fixture = research_worker_db
    first = lease_default_step(fixture)
    now = fixture.now + timedelta(seconds=61)
    reclaim_expired_research_steps(fixture.db, now=now)
    fixture.step.max_attempts_snapshot = 1
    fixture.db.commit()
    with pytest.raises(ResearchError, match="attempt limit"):
        claim_specific_research_step(
            fixture.db,
            run_id=fixture.run.id,
            step_key=fixture.step.step_key,
            branch_key=fixture.step.branch_key,
            worker_instance_id="rejected-worker",
            lease_seconds=60,
            now=now,
        )
    assert fixture.step.error_code == "lease_expired"
    assert fixture.step.error_message == "Research Attempt lease expired."
    assert fixture.step.current_attempt_number == 1
    fixture.step.max_attempts_snapshot = 3
    fixture.db.commit()
    second = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="accepted-worker",
        lease_seconds=60,
        now=now,
    )
    fail_research_step(
        fixture.db,
        attempt_id=second.attempt_id,
        lease_token=second.lease_token,
        error_code="tool_scope_violation",
        now=now + timedelta(seconds=1),
    )
    fixture.db.commit()
    assert fixture.step.error_code == "tool_scope_violation"
    assert fixture.step.error_message == "Research step failed: tool_scope_violation."
    assert (
        fixture.db.get(ResearchStepAttempt, first.attempt_id).error_code
        == "lease_expired"
    )
    assert (
        fixture.db.get(ResearchStepAttempt, second.attempt_id).error_code
        == "tool_scope_violation"
    )

