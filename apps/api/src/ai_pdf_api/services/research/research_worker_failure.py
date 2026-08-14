from __future__ import annotations

from datetime import UTC, datetime

from ai_pdf_api.services.research import append_research_event
from ai_pdf_api.services.research.research_worker_policy import (
    FailureDisposition,
    is_transient_failure,
    normalize_failure_code,
)
from sqlalchemy.orm import Session


def fail_research_step(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    error_code: str,
    now: datetime | None = None,
) -> FailureDisposition:
    from ai_pdf_api.services.research.research_worker_lease import _locked_attempt

    failed_at = now or datetime.now(UTC)
    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=failed_at,
    )
    reason_code = normalize_failure_code(error_code)
    retryable = is_transient_failure(reason_code)
    safe_message = f"Research step failed: {reason_code}."
    attempt.status = "failed"
    attempt.error_code = reason_code
    attempt.error_message = safe_message
    attempt.finished_at = failed_at
    attempt.lease_expires_at = None
    step.status = "failed"
    step.state_version += 1
    step.error_code = reason_code
    step.error_message = safe_message
    step.finished_at = failed_at
    step.updated_at = failed_at
    auto_requeued = retryable and step.current_attempt_number < step.max_attempts_snapshot
    run.status = run.status if auto_requeued else ("awaiting_retry" if retryable else "failed")
    run.state_version += 1
    run.failure_code = reason_code
    run.failure_message = None if auto_requeued else safe_message
    run.updated_at = failed_at
    if not retryable:
        run.finished_at = failed_at
    append_research_event(
        db,
        run,
        event_type="step_failed",
        dedupe_key=f"step-failed:{attempt.id}",
        step_id=step.id,
        attempt_id=attempt.id,
        data={
            "stepId": step.id,
            "stepKind": step.step_kind,
            "attemptId": attempt.id,
            "attemptNumber": attempt.attempt_number,
            "reasonCode": reason_code,
            "retryable": retryable,
            "stepStateVersion": step.state_version,
            "runStateVersion": run.state_version,
        },
        now=failed_at,
    )
    if auto_requeued:
        step.status = "queued"
        step.state_version += 1
        step.error_code = None
        step.error_message = None
        step.queued_at = failed_at
        step.finished_at = None
        run.failure_code = None
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
            now=failed_at,
        )
    elif not retryable:
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="run_failed",
            dedupe_key=f"run-failed:{attempt.id}",
            data={
                "status": "failed",
                "reasonCode": reason_code,
                "retryable": False,
                "runStateVersion": run.state_version,
            },
            now=failed_at,
        )
    db.commit()
    return FailureDisposition(
        reason_code=reason_code,
        retryable=retryable,
        auto_requeued=auto_requeued,
        step_status=step.status,
        run_status=run.status,
    )
