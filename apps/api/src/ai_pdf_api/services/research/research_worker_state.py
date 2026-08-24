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
    "reclaim_expired_research_steps",
]
