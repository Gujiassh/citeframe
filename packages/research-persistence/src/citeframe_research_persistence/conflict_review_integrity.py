"""Require conflict review of verified revisions and every unaffected fact."""

from citeframe_persistence.models import (
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceHandle,
)
from sqlalchemy import select

from .errors import ResearchError, canonical_sha256


def validate_combined_review(db, step, reviewed, revisions):
    facts = list(
        db.scalars(
            select(ResearchClaim).where(
                ResearchClaim.run_id == step.run_id,
                ResearchClaim.workspace_id == step.workspace_id,
                ResearchClaim.verification_status == "supported",
                ResearchClaim.conflict_status == "none",
            )
        )
    )
    expected = list(revisions)
    for claim in facts:
        handles = list(
            db.scalars(
                select(ResearchEvidenceHandle.id)
                .join(
                    ResearchClaimEvidence,
                    ResearchClaimEvidence.evidence_snapshot_id
                    == ResearchEvidenceHandle.evidence_snapshot_id,
                )
                .where(
                    ResearchClaimEvidence.claim_id == claim.id,
                    ResearchEvidenceHandle.owner_step_id == claim.produced_by_step_id,
                    ResearchEvidenceHandle.run_id == step.run_id,
                    ResearchEvidenceHandle.workspace_id == step.workspace_id,
                    ResearchEvidenceHandle.execution_snapshot_id
                    == step.execution_snapshot_id,
                )
                .order_by(ResearchClaimEvidence.evidence_order)
            )
        )
        expected.append(
            {
                "id": claim.id,
                "text": claim.statement_text,
                "evidence_handle_ids": handles,
                "verification_status": "supported",
                "conflict_status": "none",
            }
        )
    if len({c["id"] for c in reviewed}) != len(reviewed) or canonical_sha256(
        sorted(reviewed, key=lambda c: c["id"])
    ) != canonical_sha256(sorted(expected, key=lambda c: c["id"])):
        raise ResearchError(
            "research_state_conflict",
            "Conflict review omitted or changed the combined claim set.",
            409,
        )
