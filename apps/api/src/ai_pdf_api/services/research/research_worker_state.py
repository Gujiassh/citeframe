from __future__ import annotations

import hashlib
import json
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
    ResearchStepDependency,
    ResearchToolCall,
)
from ai_pdf_api.services.research import ResearchError, append_research_event
from ai_pdf_api.services.research.research_worker_policy import add_optional_cost, subtract_optional_cost
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
    from ai_pdf_api.services.research.research_worker_lease import load_approved_execution

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
    by_id = {step.id: step for step in steps}
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
        producer = by_id.get(claim.produced_by_step_id) if claim is not None else None
        if (
            claim is None
            or producer is None
            or producer.step_kind != "researcher"
            or producer.status != "succeeded"
            or evidence.run_id != run_id
            or evidence.workspace_id != snapshot.workspace_id
            or evidence.captured_by_step_id != producer.id
            or handle_id is None
        ):
            raise ResearchError("research_state_conflict", "Research Claim Evidence provenance is invalid.", 409)
        evidence_by_claim.setdefault(relation.claim_id, []).append(handle_id)
    if any(
        claim.workspace_id != snapshot.workspace_id
        or claim.run_id != run_id
        or claim.statement_sha256
        != hashlib.sha256(claim.statement_text.encode("utf-8")).hexdigest()
        or claim.produced_by_step_id not in by_id
        or by_id[claim.produced_by_step_id].step_kind != "researcher"
        or by_id[claim.produced_by_step_id].status != "succeeded"
        or not evidence_by_claim.get(claim.id)
        or (
            claim.verification_status == "pending"
            and claim.verified_by_step_id is not None
        )
        or (
            claim.verification_status != "pending"
            and (
                claim.verified_by_step_id not in by_id
                or by_id[claim.verified_by_step_id].step_kind != "verifier"
                or by_id[claim.verified_by_step_id].status != "succeeded"
            )
        )
        or (
            claim.conflict_status != "none"
            and (
                claim.critic_step_id not in by_id
                or by_id[claim.critic_step_id].step_kind != "critic"
                or by_id[claim.critic_step_id].status != "succeeded"
            )
        )
        for claim in claims
    ):
        raise ResearchError("research_state_conflict", "Research Claim provenance is invalid.", 409)
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
    synthesis_selection = (
        {
            "factClaimIds": [claim_id for claim_id, section in final_claims if section in {"fact", "conclusion"}],
            "unresolvedClaimIds": [claim_id for claim_id, section in final_claims if section == "unresolved"],
        }
        if final_artifact
        else _load_synthesis_selection(db, run_id=run_id, snapshot=snapshot, steps=steps)
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
        "synthesisSelection": synthesis_selection,
    }


def _load_synthesis_selection(
    db: Session,
    *,
    run_id: str,
    snapshot: ResearchExecutionSnapshot,
    steps: list[ResearchStep],
) -> dict[str, object] | None:
    synthesizer = next((step for step in steps if step.step_kind == "synthesizer"), None)
    if synthesizer is None or synthesizer.status != "succeeded":
        return None
    attempt = db.scalar(
        select(ResearchStepAttempt).where(
            ResearchStepAttempt.step_id == synthesizer.id,
            ResearchStepAttempt.attempt_number == synthesizer.current_attempt_number,
            ResearchStepAttempt.status == "succeeded",
        )
    )
    artifact = db.get(ResearchArtifact, attempt.checkpoint_artifact_id) if attempt else None
    if (
        attempt is None
        or artifact is None
        or artifact.workspace_id != snapshot.workspace_id
        or artifact.run_id != run_id
        or artifact.generated_by_step_id != synthesizer.id
        or artifact.generated_by_attempt_id != attempt.id
        or artifact.artifact_kind != "execution_checkpoint"
        or artifact.logical_key != "checkpoint:synthesis"
        or artifact.schema_version != "1"
        or artifact.content_type != "application/json"
    ):
        raise ResearchError("research_state_conflict", "Research synthesis checkpoint provenance is invalid.", 409)
    from ai_pdf_api.services.research.research_views import verified_artifact_bytes

    try:
        payload = json.loads(verified_artifact_bytes(artifact))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ResearchError(
            "research_artifact_integrity_mismatch",
            "Research synthesis checkpoint bytes failed validation.",
            409,
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != 1
        or payload.get("runId") != run_id
        or payload.get("stepId") != synthesizer.id
        or payload.get("attemptId") != attempt.id
        or not isinstance(payload.get("factClaimIds"), list)
        or not isinstance(payload.get("unresolvedClaimIds"), list)
    ):
        raise ResearchError("research_state_conflict", "Research synthesis checkpoint contract is invalid.", 409)
    fact_ids = [str(item) for item in payload["factClaimIds"]]
    unresolved_ids = [str(item) for item in payload["unresolvedClaimIds"]]
    if (
        len(fact_ids) != len(set(fact_ids))
        or len(unresolved_ids) != len(set(unresolved_ids))
        or set(fact_ids).intersection(unresolved_ids)
    ):
        raise ResearchError("research_state_conflict", "Research synthesis checkpoint selection is invalid.", 409)
    return {"factClaimIds": fact_ids, "unresolvedClaimIds": unresolved_ids}


def load_step_handler_input(
    db: Session,
    *,
    run_id: str,
    step_id: str,
    attempt_id: str,
    lease_token: str,
    now: datetime,
) -> dict[str, object]:
    """Rebuild and validate the persisted input for one claimed Attempt."""

    from ai_pdf_api.services.research.research_worker_lease import load_approved_execution

    execution = load_approved_execution(db, run_id)
    step = db.get(ResearchStep, step_id)
    attempt = db.get(ResearchStepAttempt, attempt_id)
    lease_expires_at = attempt.lease_expires_at if attempt is not None else None
    if lease_expires_at is not None and lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
    if (
        step is None
        or attempt is None
        or step.run_id != run_id
        or step.workspace_id != execution["workspaceId"]
        or step.execution_snapshot_id != execution["executionSnapshotId"]
        or step.status != "running"
        or attempt.step_id != step.id
        or attempt.workspace_id != step.workspace_id
        or attempt.status != "running"
        or attempt.lease_token_hash
        != hashlib.sha256(lease_token.encode("utf-8")).hexdigest()
        or lease_expires_at is None
        or lease_expires_at <= now
        or attempt.attempt_number != step.current_attempt_number
        or attempt.input_sha256
        != (step.input_sha256 or hashlib.sha256(step.id.encode("utf-8")).hexdigest())
    ):
        raise ResearchError("research_state_conflict", "Research claimed Attempt chain is invalid.", 409)
    dependencies = list(
        db.execute(
            select(ResearchStepDependency, ResearchStep)
            .join(
                ResearchStep,
                ResearchStep.id == ResearchStepDependency.depends_on_step_id,
            )
            .where(ResearchStepDependency.step_id == step.id)
            .order_by(ResearchStep.id)
        ).all()
    )
    if any(
        dependency.step_id != step.id
        or upstream.run_id != run_id
        or upstream.workspace_id != step.workspace_id
        or upstream.execution_snapshot_id != step.execution_snapshot_id
        or upstream.status != "succeeded"
        for dependency, upstream in dependencies
    ):
        raise ResearchError("research_state_conflict", "Research Step dependency is not satisfied.", 409)
    state = load_execution_state(db, run_id)
    if state is None:
        raise ResearchError("research_state_conflict", "Research execution state is missing.", 409)
    return {
        "execution": execution,
        "step": {
            "id": step.id,
            "key": step.step_key,
            "kind": step.step_kind,
            "branchKey": step.branch_key,
            "inputSha256": step.input_sha256,
        },
        "attempt": {
            "id": attempt.id,
            "number": attempt.attempt_number,
            "inputSha256": attempt.input_sha256,
        },
        "dependencies": [upstream.id for _dependency, upstream in dependencies],
        "state": state,
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


from functools import wraps

from citeframe_research_persistence.state import (
    complete_control_step as _complete_control_step,
    reclaim_expired_research_steps as _reclaim_expired_research_steps,
)


def _commit_command(db: Session, command, /, **kwargs):
    try:
        result = command(db, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@wraps(_complete_control_step)
def complete_control_step(db: Session, **kwargs):
    return _commit_command(db, _complete_control_step, **kwargs)


@wraps(_reclaim_expired_research_steps)
def reclaim_expired_research_steps(db: Session, **kwargs):
    return _commit_command(db, _reclaim_expired_research_steps, **kwargs)

__all__ = [
    "complete_control_step",
    "load_completed_branch",
    "load_conflict_resume_state",
    "load_execution_state",
    "load_step_handler_input",
    "reclaim_expired_research_steps",
]
