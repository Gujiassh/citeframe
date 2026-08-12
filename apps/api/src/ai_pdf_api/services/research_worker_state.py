from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ai_pdf_api.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionSnapshot,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
)
from ai_pdf_api.services.research import ResearchError, append_research_event
from ai_pdf_api.services.research_worker_policy import add_optional_cost, subtract_optional_cost
from sqlalchemy import func, select
from sqlalchemy.orm import Session

_EXECUTION_NODE_ORDER = (
    "researchers",
    "join",
    "verifier",
    "critic",
    "conflict_decision_gate",
    "synthesizer",
    "artifact_publisher",
)


def load_execution_state(db: Session, run_id: str) -> dict[str, object] | None:
    from ai_pdf_api.services.research_worker_lease import load_approved_execution

    execution = load_approved_execution(db, run_id)
    snapshot_id = str(execution["executionSnapshotId"])
    snapshot = db.get(ResearchExecutionSnapshot, snapshot_id)
    if snapshot is None:
        raise ResearchError("research_state_conflict", "Research execution snapshot is missing.", 409)
    steps = list(
        db.scalars(
            select(ResearchStep)
            .where(
                ResearchStep.run_id == run_id,
                ResearchStep.execution_snapshot_id == snapshot.id,
            )
            .order_by(ResearchStep.created_at, ResearchStep.id)
        ).all()
    )
    if not steps:
        return None
    by_key = {step.step_key: step for step in steps}
    researcher_steps = [step for step in steps if step.step_kind == "researcher"]
    completed: list[str] = []
    if researcher_steps and all(step.status == "succeeded" for step in researcher_steps):
        completed.append("researchers")
    for node in _EXECUTION_NODE_ORDER[1:]:
        step = by_key.get(node)
        if len(completed) != _EXECUTION_NODE_ORDER.index(node) or step is None or step.status != "succeeded":
            break
        completed.append(node)
    claims = list(
        db.scalars(
            select(ResearchClaim)
            .where(ResearchClaim.run_id == run_id, ResearchClaim.workspace_id == snapshot.workspace_id)
            .order_by(ResearchClaim.claim_order)
        ).all()
    )
    claim_evidence = list(
        db.execute(
            select(ResearchClaimEvidence, ResearchEvidenceSnapshot)
            .join(
                ResearchEvidenceSnapshot,
                ResearchEvidenceSnapshot.id == ResearchClaimEvidence.evidence_snapshot_id,
            )
            .where(ResearchEvidenceSnapshot.run_id == run_id)
            .order_by(ResearchClaimEvidence.claim_id, ResearchClaimEvidence.evidence_order)
        ).all()
    )
    handle_rows = list(
        db.scalars(
            select(ResearchEvidenceHandle).where(
                ResearchEvidenceHandle.run_id == run_id,
                ResearchEvidenceHandle.workspace_id == snapshot.workspace_id,
            )
        ).all()
    )
    handle_by_snapshot_and_step = {
        (handle.evidence_snapshot_id, handle.owner_step_id): handle.id for handle in handle_rows
    }
    evidence_by_claim: dict[str, list[str]] = {}
    for relation, evidence in claim_evidence:
        claim = next((item for item in claims if item.id == relation.claim_id), None)
        handle_id = (
            handle_by_snapshot_and_step.get((evidence.id, claim.produced_by_step_id))
            if claim is not None
            else None
        )
        if handle_id is not None:
            evidence_by_claim.setdefault(relation.claim_id, []).append(handle_id)
    final_artifact = db.scalar(
        select(ResearchArtifact).where(
            ResearchArtifact.run_id == run_id,
            ResearchArtifact.workspace_id == snapshot.workspace_id,
            ResearchArtifact.artifact_kind == "final_report",
        )
    )
    final_claims = (
        list(
            db.execute(
                select(ResearchArtifactClaim.claim_id, ResearchArtifactClaim.section_kind)
                .where(ResearchArtifactClaim.artifact_id == final_artifact.id)
                .order_by(ResearchArtifactClaim.claim_order)
            ).all()
        )
        if final_artifact
        else []
    )
    return {
        "execution": execution,
        "completedNodes": completed,
        "status": execution["runStatus"],
        "claims": [
            {
                "id": claim.id,
                "text": claim.statement_text,
                "producedByStepId": claim.produced_by_step_id,
                "evidenceHandleIds": evidence_by_claim.get(claim.id, []),
                "verificationStatus": claim.verification_status,
                "conflictStatus": claim.conflict_status,
            }
            for claim in claims
        ],
        "finalArtifactId": final_artifact.id if final_artifact else None,
        "synthesisSelection": {
            "factClaimIds": [claim_id for claim_id, section in final_claims if section in {"fact", "conclusion"}],
            "unresolvedClaimIds": [claim_id for claim_id, section in final_claims if section == "unresolved"],
        }
        if final_artifact
        else None,
    }


def load_conflict_resume_state(
    db: Session,
    run_id: str,
    action: str,
) -> dict[str, object]:
    if action not in {"exclude_conflicted_claims", "keep_as_unresolved"}:
        raise ValueError("invalid conflict decision action")
    decision = db.scalar(
        select(HumanDecision)
        .where(
            HumanDecision.run_id == run_id,
            HumanDecision.decision_type == "conflict_resolution",
            HumanDecision.status == "submitted",
            HumanDecision.action == action,
        )
        .order_by(HumanDecision.decided_at.desc())
        .limit(1)
    )
    state = load_execution_state(db, run_id)
    if decision is None or state is None:
        raise ResearchError("research_state_conflict", "Committed conflict decision was not found.", 409)
    gate = db.get(ResearchStep, decision.gate_step_id)
    if gate is None or gate.run_id != run_id or gate.status != "succeeded":
        raise ResearchError("research_state_conflict", "Conflict decision gate is not committed.", 409)
    completed = list(state["completedNodes"])
    if "conflict_decision_gate" not in completed:
        completed.append("conflict_decision_gate")
    state["completedNodes"] = completed
    state["conflictAction"] = action
    return state


def load_completed_branch(db: Session, run_id: str, branch_key: str) -> dict[str, object] | None:
    step = db.scalar(
        select(ResearchStep).where(
            ResearchStep.run_id == run_id,
            ResearchStep.branch_key == branch_key,
            ResearchStep.step_kind == "researcher",
        )
    )
    if step is None or step.status != "succeeded":
        return None
    claims = list(
        db.scalars(
            select(ResearchClaim)
            .where(ResearchClaim.run_id == run_id, ResearchClaim.produced_by_step_id == step.id)
            .order_by(ResearchClaim.claim_order)
        ).all()
    )
    evidence_handles = list(
        db.scalars(
            select(ResearchEvidenceHandle)
            .where(ResearchEvidenceHandle.run_id == run_id, ResearchEvidenceHandle.owner_step_id == step.id)
            .order_by(ResearchEvidenceHandle.created_at, ResearchEvidenceHandle.result_order)
        ).all()
    )
    handle_by_snapshot = {item.evidence_snapshot_id: item.id for item in evidence_handles}
    relations = list(
        db.scalars(
            select(ResearchClaimEvidence)
            .where(ResearchClaimEvidence.claim_id.in_([claim.id for claim in claims]))
            .order_by(ResearchClaimEvidence.claim_id, ResearchClaimEvidence.evidence_order)
        ).all()
    ) if claims else []
    handles_by_claim: dict[str, list[str]] = {}
    for relation in relations:
        handle_id = handle_by_snapshot.get(relation.evidence_snapshot_id)
        if handle_id is not None:
            handles_by_claim.setdefault(relation.claim_id, []).append(handle_id)
    return {
        "stepId": step.id,
        "branchKey": branch_key,
        "claims": [
            {
                "id": claim.id,
                "text": claim.statement_text,
                "evidenceHandleIds": handles_by_claim.get(claim.id, []),
            }
            for claim in claims
        ],
        "evidenceHandleIds": [item.id for item in evidence_handles],
    }


def complete_control_step(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
) -> None:
    from ai_pdf_api.services.research_worker_lease import complete_research_step

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
        db.commit()
    return len(attempts)
