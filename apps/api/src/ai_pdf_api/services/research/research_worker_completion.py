from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ai_pdf_api.models import (
    ResearchArtifact,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceHandle,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
)
from ai_pdf_api.services.research import ResearchError, canonical_json, canonical_sha256
from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class BranchClaimDraft:
    id: str
    text: str
    evidence_handle_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerificationResult:
    claim_id: str
    status: str
    reason_code: str | None = None


def _checkpoint_artifact(
    db: Session,
    *,
    run,
    step,
    attempt,
    logical_key: str,
    payload: dict[str, object],
    now: datetime,
    store_bytes: Callable[[str, bytes, str], None],
) -> tuple[ResearchArtifact, str]:
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    if snapshot is None or snapshot.run_id != run.id or snapshot.workspace_id != run.workspace_id:
        raise ResearchError("research_state_conflict", "Research checkpoint chain is invalid.", 409)
    prompt = db.scalar(
        select(ResearchExecutionPromptVersion.prompt_version_id).where(
            ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id,
            ResearchExecutionPromptVersion.node_key
            == ("researchers" if step.step_kind == "researcher" else step.step_kind),
        )
    )
    content = canonical_json(payload)
    artifact_id = str(uuid4())
    object_key = f"research/{run.workspace_id}/{run.id}/{artifact_id}/checkpoint.json"
    store_bytes(object_key, content, "application/json")
    artifact = ResearchArtifact(
        id=artifact_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        generated_by_step_id=step.id,
        generated_by_attempt_id=attempt.id,
        artifact_kind="execution_checkpoint",
        visibility="internal",
        logical_key=logical_key,
        schema_version="1",
        object_key=object_key,
        content_type="application/json",
        byte_size=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
        workflow_version_id=snapshot.workflow_version_id,
        direct_prompt_version_id=prompt,
        generation_provider=snapshot.generation_provider if prompt else None,
        generation_model=snapshot.generation_model if prompt else None,
        retention_class="workspace_lifetime",
        created_at=now,
    )
    db.add(artifact)
    db.flush()
    return artifact, object_key


def complete_research_branch(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    result: object,
    output_sha256: str,
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> None:
    from ai_pdf_api.services.research.research_worker_lease import complete_research_step

    completed_at = now or datetime.now(UTC)
    branch_key = str(result.branch_key)
    claims = [
        BranchClaimDraft(
            id=str(claim.id),
            text=str(claim.text),
            evidence_handle_ids=tuple(claim.evidence_handle_ids),
        )
        for claim in result.claims
    ]
    if len({claim.id for claim in claims}) != len(claims):
        raise ValueError("Branch Claim ids must be unique")
    try:
        if any(str(UUID(claim.id)) != claim.id for claim in claims):
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise ResearchError("research_state_conflict", "Research Claim ids must be canonical UUIDs.", 409) from error
    stored_key: str | None = None

    def persist(session: Session, run, step, attempt) -> tuple[int, list[str]]:
        nonlocal stored_key
        if step.step_kind != "researcher" or step.branch_key != branch_key:
            raise ResearchError("research_state_conflict", "Research branch result does not match its Step.", 409)
        handle_ids = list(dict.fromkeys(handle_id for claim in claims for handle_id in claim.evidence_handle_ids))
        handles = list(
            session.scalars(
                select(ResearchEvidenceHandle).where(ResearchEvidenceHandle.id.in_(handle_ids))
            ).all()
        ) if handle_ids else []
        by_id = {handle.id: handle for handle in handles}
        if any(
            not claim.text.strip()
            or not claim.evidence_handle_ids
            or len(claim.evidence_handle_ids) != len(set(claim.evidence_handle_ids))
            or any(
                handle_id not in by_id
                or by_id[handle_id].run_id != run.id
                or by_id[handle_id].workspace_id != run.workspace_id
                or by_id[handle_id].execution_snapshot_id != step.execution_snapshot_id
                or by_id[handle_id].owner_step_id != step.id
                for handle_id in claim.evidence_handle_ids
            )
            for claim in claims
        ):
            raise ResearchError("research_state_conflict", "Research branch Claim provenance is invalid.", 409)
        max_claim_order = session.scalar(
            select(func.max(ResearchClaim.claim_order)).where(ResearchClaim.run_id == run.id)
        )
        next_order = (int(max_claim_order) if max_claim_order is not None else -1) + 1
        for offset, claim in enumerate(claims):
            claim_row = ResearchClaim(
                    id=claim.id,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    claim_key=f"branch:{branch_key}:{claim.id}",
                    claim_order=next_order + offset,
                    statement_text=claim.text,
                    statement_sha256=hashlib.sha256(claim.text.encode("utf-8")).hexdigest(),
                    produced_by_step_id=step.id,
                    verification_status="pending",
                    conflict_status="none",
                    created_at=completed_at,
                )
            session.add(claim_row)
            session.flush()
            for evidence_order, handle_id in enumerate(claim.evidence_handle_ids):
                session.add(
                    ResearchClaimEvidence(
                        claim_id=claim.id,
                        evidence_snapshot_id=by_id[handle_id].evidence_snapshot_id,
                        evidence_order=evidence_order,
                        relationship="supports",
                        assessed_by_step_id=step.id,
                    )
                )
        checkpoint, stored_key = _checkpoint_artifact(
            session,
            run=run,
            step=step,
            attempt=attempt,
            logical_key=f"checkpoint:branch:{branch_key}",
            payload={
                "schemaVersion": 1,
                "runId": run.id,
                "stepId": step.id,
                "attemptId": attempt.id,
                "branchKey": branch_key,
                "claims": [
                    {"claimId": claim.id, "evidenceHandleIds": list(claim.evidence_handle_ids)}
                    for claim in claims
                ],
            },
            now=completed_at,
            store_bytes=store_bytes,
        )
        attempt.checkpoint_artifact_id = checkpoint.id
        run.latest_checkpoint_artifact_id = checkpoint.id
        return len(handle_ids), [checkpoint.id]

    try:
        complete_research_step(
            db,
            attempt_id=attempt_id,
            lease_token=lease_token,
            output_sha256=output_sha256,
            complete=persist,
            now=completed_at,
        )
    except Exception:
        if stored_key:
            cleanup_bytes(stored_key)
        raise


def complete_research_verification(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    results: Sequence[VerificationResult],
    now: datetime | None = None,
) -> None:
    from ai_pdf_api.services.research.research_worker_lease import complete_research_step

    completed_at = now or datetime.now(UTC)

    def persist(session: Session, run, step, _attempt) -> tuple[int, list[str]]:
        if step.step_kind != "verifier" or len({item.claim_id for item in results}) != len(results):
            raise ResearchError("research_state_conflict", "Research verification result is invalid.", 409)
        claims = list(
            session.scalars(
                select(ResearchClaim).where(
                    ResearchClaim.id.in_([item.claim_id for item in results]),
                    ResearchClaim.run_id == run.id,
                    ResearchClaim.workspace_id == run.workspace_id,
                )
            ).all()
        )
        by_id = {claim.id: claim for claim in claims}
        pending_claims = list(
            session.scalars(
                select(ResearchClaim).where(
                    ResearchClaim.run_id == run.id,
                    ResearchClaim.workspace_id == run.workspace_id,
                    ResearchClaim.verification_status == "pending",
                )
            ).all()
        )
        if (
            set(by_id) != {item.claim_id for item in results}
            or set(by_id) != {claim.id for claim in pending_claims}
        ):
            raise ResearchError("research_state_conflict", "Research verification Claim scope is invalid.", 409)
        for item in results:
            if item.status not in {"supported", "unsupported"} or by_id[item.claim_id].verification_status != "pending":
                raise ResearchError("research_state_conflict", "Research Claim cannot be verified.", 409)
            claim = by_id[item.claim_id]
            claim.verification_status = item.status
            claim.verified_by_step_id = step.id
            claim.verification_reason_code = item.reason_code
            claim.verified_at = completed_at
            relations = list(
                session.scalars(
                    select(ResearchClaimEvidence).where(ResearchClaimEvidence.claim_id == claim.id)
                ).all()
            )
            for relation in relations:
                relation.assessed_by_step_id = step.id
        return 0, []

    complete_research_step(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        output_sha256=canonical_sha256(
            [{"claimId": item.claim_id, "status": item.status, "reasonCode": item.reason_code} for item in results]
        ),
        complete=persist,
        now=completed_at,
    )


def complete_research_critique(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    conflict_claim_ids: Sequence[str],
    now: datetime | None = None,
) -> None:
    from ai_pdf_api.services.research.research_worker_lease import complete_research_step

    completed_at = now or datetime.now(UTC)
    conflict_ids = list(conflict_claim_ids)

    def persist(session: Session, run, step, _attempt) -> tuple[int, list[str]]:
        if step.step_kind != "critic" or len(conflict_ids) != len(set(conflict_ids)):
            raise ResearchError("research_state_conflict", "Research critique result is invalid.", 409)
        claims = list(
            session.scalars(
                select(ResearchClaim).where(
                    ResearchClaim.id.in_(conflict_ids),
                    ResearchClaim.run_id == run.id,
                    ResearchClaim.workspace_id == run.workspace_id,
                )
            ).all()
        ) if conflict_ids else []
        if {claim.id for claim in claims} != set(conflict_ids) or any(
            claim.verification_status != "supported" or claim.conflict_status != "none"
            for claim in claims
        ):
            raise ResearchError("research_state_conflict", "Research critique Claim scope is invalid.", 409)
        for claim in claims:
            claim.conflict_status = "conflicted"
            claim.critic_step_id = step.id
        return 0, []

    complete_research_step(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        output_sha256=canonical_sha256({"conflictClaimIds": conflict_ids}),
        complete=persist,
        now=completed_at,
    )


def complete_research_synthesis(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> None:
    from ai_pdf_api.services.research.research_worker_lease import complete_research_step

    completed_at = now or datetime.now(UTC)
    fact_ids = list(fact_claim_ids)
    unresolved_ids = list(unresolved_claim_ids)
    stored_key: str | None = None

    def persist(session: Session, run, step, attempt) -> tuple[int, list[str]]:
        nonlocal stored_key
        selected = [*fact_ids, *unresolved_ids]
        if (
            step.step_kind != "synthesizer"
            or len(selected) != len(set(selected))
        ):
            raise ResearchError("research_state_conflict", "Research synthesis selection is invalid.", 409)
        claims = list(
            session.scalars(
                select(ResearchClaim).where(
                    ResearchClaim.id.in_(selected),
                    ResearchClaim.run_id == run.id,
                    ResearchClaim.workspace_id == run.workspace_id,
                )
            ).all()
        ) if selected else []
        by_id = {claim.id: claim for claim in claims}
        if set(by_id) != set(selected) or any(
            by_id[claim_id].verification_status != "supported"
            or by_id[claim_id].conflict_status != "none"
            for claim_id in fact_ids
        ) or any(
            by_id[claim_id].verification_status != "supported"
            or by_id[claim_id].conflict_status != "resolved_unresolved"
            for claim_id in unresolved_ids
        ):
            raise ResearchError("research_state_conflict", "Research synthesis Claim scope is invalid.", 409)
        checkpoint, stored_key = _checkpoint_artifact(
            session,
            run=run,
            step=step,
            attempt=attempt,
            logical_key="checkpoint:synthesis",
            payload={
                "schemaVersion": 1,
                "runId": run.id,
                "stepId": step.id,
                "attemptId": attempt.id,
                "factClaimIds": fact_ids,
                "unresolvedClaimIds": unresolved_ids,
            },
            now=completed_at,
            store_bytes=store_bytes,
        )
        attempt.checkpoint_artifact_id = checkpoint.id
        run.latest_checkpoint_artifact_id = checkpoint.id
        return 0, [checkpoint.id]

    try:
        complete_research_step(
            db,
            attempt_id=attempt_id,
            lease_token=lease_token,
            output_sha256=canonical_sha256(
                {"factClaimIds": fact_ids, "unresolvedClaimIds": unresolved_ids}
            ),
            complete=persist,
            now=completed_at,
        )
    except Exception:
        if stored_key:
            cleanup_bytes(stored_key)
        raise
